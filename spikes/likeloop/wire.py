"""wire.py <out.png> [model]: the one mesh's quads over the right eye region (brow to cheek), drawn front-facing
through the photo's camera on the clay render: are there edge loops parallel to the upper lid margin between the
margin and the brow? Also prints the vertex rows crossed going straight up from the mid upper lid to the brow."""
import sys

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import humanfit, likeness, likeness_eyes as le, store

name = sys.argv[2] if len(sys.argv) > 2 else "ll_garrett"
base = store.load(name)["base"]
refs = likeness._refs(name)
ph = likeness.photo_sides(refs)[0]
cam = ph["cam"]
mesh = likeness.model_mesh(base)
st = mesh["state"]
P = np.asarray(st["tpl"]["P"], float)
Q = np.asarray(st["tpl"]["L"]).reshape(-1, 4)
L = np.asarray(st["L"])
box = le.eye_box(ph["side"].P)
x0, y0, x1, y1 = box
box = (x0, y0, 0.5 * (x0 + x1) + 0.05 * (x1 - x0), y1)          # the picture's left half: the right eye
im, k = likeness.render(mesh, cam, box, px=1400, brows=False)
im = im.convert("RGB")
d = ImageDraw.Draw(im)
uv = (humanfit.project(cam, P) - [box[0], box[1]]) * k
Rc = humanfit._cam_rot(cam)
Xc = (P - np.asarray(cam["centre"])) @ Rc.T + np.asarray(cam["t"])
fn = np.cross(Xc[Q[:, 2]] - Xc[Q[:, 0]], Xc[Q[:, 3]] - Xc[Q[:, 1]])
front = (fn * Xc[Q].mean(1)).sum(1) < 0
W_, H_ = im.size
for q in Q[front]:
    pts = [tuple(uv[i]) for i in q]
    if all(-50 < p[0] < W_ + 50 and -50 < p[1] < H_ + 50 for p in pts):
        d.line(pts + [pts[0]], fill=(30, 60, 200), width=1)
for i in (36, 37, 38, 39, 19):
    p = uv[np.argmin(np.linalg.norm(P - L[i], axis=1))]
    d.ellipse([p[0] - 5, p[1] - 5, p[0] + 5, p[1] + 5], outline=(220, 30, 30), width=2)
im.save(sys.argv[1])
U, B = 0.5 * (L[37] + L[38]), L[19]
sel = (np.abs(P[:, 0] - U[0]) < 0.002) & (P[:, 2] > U[2]) & (P[:, 2] < B[2]) & (P[:, 1] < U[1] + 0.006)
print("vertices in a 4 mm column from the mid upper lid to the brow:", int(sel.sum()), "over", round(1000 * float(B[2] - U[2]), 1), "mm;",
      "their heights mm:", sorted(np.round((P[sel][:, 2] - U[2]) * 1000, 1).tolist()))
