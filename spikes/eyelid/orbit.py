"""orbit.py <model> [view index=2]: the model's orbit drawn on a side reference picture through its fitted camera
(out/orbit_<model>_<view>.png, the eye region x4): the mid-sagittal profile (green: forehead - nasion - nose), the
near eye's corneal apex (yellow cross) and eyeball outline (yellow), the lid margins at the pupil column (cyan), the
brow landmarks (magenta), nasion (red). Prints the model's own mm: cornea apex behind nasion (profile depth of the
eye), brow landmark over the pupil, brow ridge forward of the cornea."""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

import lidmap as lm
from hifipushie import blockin as bi, blockin_eyes as be, humanfit, likeness, store

G = os.environ["G"] + "/out"
name = sys.argv[1]
vi = int(sys.argv[2]) if len(sys.argv) > 2 else 2
rj = bi._refs(name)
v, cam = rj["views"][vi], rj["cameras"][vi]
img = Image.open(v["image"]).convert("RGB")
st = humanfit.state(store.load(name)["base"])
ht = st["head"]
L = st["L"]
W = np.asarray(ht["verts"], float)
fwd = np.asarray(ht["forward"], float)
r = float(ht["eye_r"])
side = 1.0 if float(v.get("yaw", 90)) > 0 else -1.0
# which eye faces this camera: the one whose centre projects nearer the camera
R = humanfit._cam_rot(cam)
eye_c = np.asarray(cam["centre"], float) - R.T @ np.asarray(cam["t"], float)
eyes = [np.asarray(e, float) for e in ht["eyes"]]
c = min(eyes, key=lambda e: np.linalg.norm(e - eye_c))
apex = c + r * fwd
mm = likeness._mm_per_px(cam, L[27:48])
P = lambda X: humanfit.project(cam, np.atleast_2d(X))   # noqa: E731
pa = P(apex)[0]
K = 4
half = 30.0 / mm
box = (pa[0] - half, pa[1] - half, pa[0] + half, pa[1] + half)
im = img.crop(tuple(int(round(x)) for x in box)).resize((int(2 * half) * K, int(2 * half) * K), Image.LANCZOS)
d = ImageDraw.Draw(im)
q = lambda X: (P(X) - box[:2]) * K   # noqa: E731
# mid-sagittal profile of the skin
F = be._tris(ht["faces"])
x0 = float(0.5 * (eyes[0][0] + eyes[1][0]))
for Lc in be._chain(be._slice(W, F, x0)):
    pts = q(Lc)
    ok = (Lc[:, 2] > c[2] - 0.06) & (Lc[:, 2] < c[2] + 0.06) & ((Lc - c) @ fwd > -0.02)
    for a, b, o1, o2 in zip(pts[:-1], pts[1:], ok[:-1], ok[1:]):
        if o1 and o2:
            d.line([tuple(a), tuple(b)], fill=(0, 220, 0), width=2)
# the eyeball's outline in this view + the apex
th = np.linspace(0, 2 * np.pi, 90)
up = np.array([0, 0, 1.0])
circ = c + r * (np.cos(th)[:, None] * fwd + np.sin(th)[:, None] * up)
cp = q(circ)
d.line([tuple(p) for p in cp], fill=(255, 220, 0), width=1)
ap = q(apex)[0]
d.line([(ap[0] - 12, ap[1]), (ap[0] + 12, ap[1])], fill=(255, 220, 0), width=3)
d.line([(ap[0], ap[1] - 12), (ap[0], ap[1] + 12)], fill=(255, 220, 0), width=3)
# the lid's sagittal section through the pupil (cyan)
for Lc in be._chain(be._slice(W, F, float(c[0]))):
    ok = (np.linalg.norm(Lc - c, axis=1) < 0.03) & ((Lc - c) @ fwd > 0)
    pts = q(Lc)
    for a, b, o1, o2 in zip(pts[:-1], pts[1:], ok[:-1], ok[1:]):
        if o1 and o2:
            d.line([tuple(a), tuple(b)], fill=(0, 220, 255), width=2)
# the FAR eye: its corneal apex (white cross) and its lid section (white): with the near eye it tells yaw from depth
cf = max(eyes, key=lambda e: np.linalg.norm(e - eye_c))
af = q(cf + r * fwd)[0]
d.line([(af[0] - 12, af[1]), (af[0] + 12, af[1])], fill=(255, 255, 255), width=3)
d.line([(af[0], af[1] - 12), (af[0], af[1] + 12)], fill=(255, 255, 255), width=3)
for Lc in be._chain(be._slice(W, F, float(cf[0]))):
    ok = (np.linalg.norm(Lc - cf, axis=1) < 0.02) & ((Lc - cf) @ fwd > 0.004)
    pts = q(Lc)
    for a, b, o1, o2 in zip(pts[:-1], pts[1:], ok[:-1], ok[1:]):
        if o1 and o2:
            d.line([tuple(a), tuple(b)], fill=(255, 255, 255), width=2)
for i in (19, 24) if c[0] > 0 else (19, 24):
    p = q(L[i])[0]
    d.ellipse([p[0] - 6, p[1] - 6, p[0] + 6, p[1] + 6], outline=(255, 0, 255), width=3)
p = q(L[27])[0]
d.ellipse([p[0] - 6, p[1] - 6, p[0] + 6, p[1] + 6], outline=(255, 0, 0), width=3)
d.line([(20, 20), (20 + 10 / mm * K, 20)], fill=(0, 0, 0), width=4)
d.text((24, 26), "10 mm", fill=(0, 0, 0), font_size=22)
im.save(f"{G}/orbit_{name}_{vi}.png")
bl = L[24] if c[0] > 0 else L[19]
ms = np.array([Lc for Lc in be._chain(be._slice(W, F, float(c[0]))) for Lc in [Lc]][0]) if False else None
print(f"{name} view {vi}: mm/px {mm:.3f}; cornea apex behind nasion {float((L[27] - apex) @ fwd) * 1000:.1f} mm; brow landmark over the pupil {float(bl[2] - c[2]) * 1000:.1f} mm, "
      f"forward of the cornea apex {float((bl - apex) @ fwd) * 1000:.1f} mm; nasion over the pupil {float(L[27][2] - c[2]) * 1000:.1f} mm; saved orbit_{name}_{vi}.png")
