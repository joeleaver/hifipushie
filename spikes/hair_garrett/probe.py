"""probe.py <model>: faceparse's hair probability on each fitted reference view, cropped round the head (the scalp
projected through the camera), saved as overlays $TOUT/probe_<model>_v<i>.png. A first look at what a reader can see."""
import json
import os
import sys
import time

import numpy as np
from PIL import Image

from hifipushie import faceparse, hair, humanfit, store

m = sys.argv[1]
OUT = os.environ["TOUT"]
spec = store.load(m)
t = time.time()
sc = hair.scalp(m, spec)
print(f"scalp {time.time() - t:.1f} s; lm {len(sc.lm)}")
refs = hair.human_refs(m)
A, E = np.meshgrid(np.arange(0, 360, 2.0), np.arange(-60, 90, 2.0))
P = sc.point(A.ravel(), E.ravel(), 0.0)
for i, cam in enumerate(refs["cameras"]):
    img = Image.open(refs["views"][i]["image"]).convert("RGB")
    uv = humanfit.project(cam, P)
    x0, y0 = uv.min(0)
    x1, y1 = uv.max(0)
    s = 1.3 * max(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    box = (cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2)
    for model in ("bisenet", "mediapipe"):
        t = time.time()
        g = faceparse.groups(faceparse.parse(img, box, model))
        hp = faceparse.to_picture(g["hair"], box, img.size)
        print(f"v{i} {model}: {time.time() - t:.1f} s, hair px > 0.5: {(hp > 0.5).sum()}")
        a = np.asarray(img, float)
        ov = a * 0.6 + 0.4 * np.stack([hp * 255, np.zeros_like(hp), np.zeros_like(hp)], -1)
        q = np.round(uv).astype(int)
        ok = (q[:, 0] >= 0) & (q[:, 0] < img.size[0]) & (q[:, 1] >= 0) & (q[:, 1] < img.size[1])
        ov[q[ok, 1], q[ok, 0]] = [0, 255, 0]
        Image.fromarray(ov.clip(0, 255).astype(np.uint8)).crop(tuple(int(v) for v in box)).save(f"{OUT}/probe_{m}_v{i}_{model}.png")
