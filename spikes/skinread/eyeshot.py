"""eyeshot.py <model> <tag>: the model's eyes (front reference camera), lit by the picture's light and flat (albedo),
side by side at 4 px a picture pixel -> $G/out/eye_<tag>.png"""
import os, sys
import numpy as np
from PIL import Image
from hifipushie import skin_read as sr, blockin as bi, humanfit, resources, store

m, tag = sys.argv[1:3]
rj = bi._refs(m)
vi = bi._front(rj)
cam = rj["cameras"][vi]
L = humanfit.state(store.load(m)["base"])["L"]
P = humanfit.project(cam, L)
w = float(np.linalg.norm(P[45] - P[36]))
c = P[36:48].mean(0)
box = [c[0] - 0.75 * w, c[1] - 0.45 * w, c[0] + 0.75 * w, c[1] + 1.05 * w]   # square 1.5 w
with resources.heavy(f"skinread eyeshot {m}", gb=6):
    sn = sr.stage(m, log=lambda s: None)
    fr = [sr.fitted_frame(cam, box, "v")]
    a = sr.shoot(sn, fr, sr.lighting(m, vi), size=1200)["v"]
    b = sr.shoot(sn, fr, None, size=1200, flat=True)["v"]
W = np.concatenate([a[:560, :, :3], b[:560, :, :3]], 0)
out = f"{os.environ['G']}/out/eye_{tag}.png"
Image.fromarray(W).save(out); print(out)
