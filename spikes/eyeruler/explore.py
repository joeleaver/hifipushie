"""explore.py <tag> ...: eye-frame patches (0.05 mm) of shots and their colour features, to design the reader."""
import json
import os
import sys

import numpy as np
from PIL import Image

from hifipushie import blockin_brows as bb, blockin_eyes as be, likeness, lidfold

G = os.environ["G"] + "/out"
bx = json.load(open(G + "/box.json"))
K, box = bx["K"], bx["box"]
q = bb._inputs("gd_T12")
mm = q["mm"] / K
Pp = (q["P"] - box[:2]) * K
for tag in sys.argv[1:]:
    im = Image.open(f"{G}/s_{tag}.png").convert("RGB")
    P = likeness.detect([im])[0]
    print(tag, "detected" if P is not None else "NOT detected")
    P = Pp if P is None else np.asarray(P, float)[:, :2]
    lb = be.limbus(im, P)
    ex, ey = bb._frame(P)
    A = np.asarray(im, float) / 255
    for s in (0, 1):
        c = np.asarray(lb[s]["centre"])
        sg = -1 if s == 0 else 1          # image x of the lateral side: subject's right eye is image-left
        u = np.arange(-19, 19.001, 0.05)
        v = np.arange(24, -10.001, -0.05)
        X = c[None, None] + (sg * u[None, :, None] / mm) * ex + (-v[:, None, None] / mm) * ey
        pat = np.stack([lidfold._bilinear(A[..., k], X[..., 0], X[..., 1]) for k in range(3)], -1)
        np.save(f"{G}/p_{tag}_{s}.npy", pat.astype(np.float32))
        Image.fromarray((pat * 255).astype(np.uint8)).save(f"{G}/p_{tag}_{s}.png")
        print(tag, s, "limbus r mm", lb[s]["r_px"] * mm, "det", lb[s]["detector_px"] * mm)
