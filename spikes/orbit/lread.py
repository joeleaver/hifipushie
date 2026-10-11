"""lread.py <model>...: the near eye's limbus on each model's own side reference pictures through its own cameras:
picture - model, mm in the picture (x: + = toward the picture's right; the "forward" component: + = her limbus is
further FORWARD than the model's)."""
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from hifipushie import blockin as bi, face_ruler as fr, humanfit, store

for name in sys.argv[1:]:
    rj = bi._refs(name)
    head = fr.model_head(store.load(name))
    lbs = fr.limbus_model(head, 11.0)
    for v, cam in zip(rj["views"], rj["cameras"]):
        k = fr.kind_of(v.get("yaw", 0))
        if k == "front":
            continue
        img = Image.open(v["image"]).convert("RGB")
        eye_c = np.asarray(cam["centre"], float) - humanfit._cam_rot(cam).T @ np.asarray(cam["t"], float)
        j = int(np.argmin([np.linalg.norm(q["X"] - eye_c) for q in lbs]))
        rd = fr.limbus_read(fr._lum(img), cam, lbs[j], valid=ndi.binary_erosion(fr.foreground(img), iterations=3))
        d = rd["d"] * rd["mmpx"]
        print(f"{name:8s} {k:8s} near eye: picture - model {d[0]:+.2f} / {d[1]:+.2f} mm; her limbus forward of the model's by {float(rd['d'] @ rd['fwd']) * rd['mmpx']:+.2f} mm in the picture "
              f"(score {rd['score']:.2f}, sharp {rd['sharp']:.3f})", flush=True)
