"""mp206.py: the 57 mm disagreement at MediaPipe points 206 / 426 between our calibrated table (mp478_gnm.npz) and XR
Blocks' FaceCorrespondence: is one of the tables mirrored there? A truth render answers it: render heads of known
shape from the front, run the detector, unproject its points 206 and 426 onto the head (depth buffer) and see on
which side of the head each lands (world x: + = the subject's left), next to what each table says."""
import base64
import os
import re

import numpy as np

import rs
from hifipushie import humanfit_map

D2 = os.environ.get("D2", "/mnt/data/hifipushie/refstudy2")
js = open(f"{D2}/xr/FaceCorrespondence.js").read()
b = base64.b64decode(re.search(r"PACKED =\s*'([^']+)'", js).group(1))
n = int(re.search(r"const COUNT = (\d+)", js).group(1))
lm = np.frombuffer(b, np.uint16, n, n * 12)
vx = np.frombuffer(b, np.uint16, n, n * 12 + 2 * n)
g = rs.gnm()
V0 = g["V0"]
t = humanfit_map.table()
PTS = (206, 426, 205, 425, 50, 280, 61, 291)      # 206 / 426 + cheek, cheekbone, mouth-corner pairs as controls
rng = np.random.default_rng(5)
imgs, meta = [], []
for i in range(6):
    V = rs.head(rng.normal(0, 0.7, rs.K_TRUE))
    cam = rs.make_cam(V, yaw=0.0, pitch=0.0, lens=70.0, size=(640, 640))
    img, zb = rs.render(V, cam, albedo=rs.skinned_albedo(i))
    imgs.append(img)
    meta.append((V, cam, zb))
det = rs.detect(imgs)
side = {p: [] for p in PTS}
pos = {p: [] for p in PTS}
for d, (V, cam, zb) in zip(det, meta):
    if d is None:
        continue
    X = rs.unproject(cam, d["P"][list(PTS), :2], zb)
    for p, x in zip(PTS, X):
        if np.all(np.isfinite(x)):
            side[p].append(float(x[0]))
            pos[p].append(x)
print("point: where the detector puts it on truth heads (world x mm, + = the subject's LEFT) | our table (front) | XR Blocks")
for p in PTS:
    ours = (V0[t["vid"][0][p]] * t["w"][0][p][..., None]).sum(0)
    j = np.flatnonzero(lm == p)
    theirs = V0[int(vx[j[0]])] if len(j) else None
    tr = np.mean(pos[p], 0) if pos[p] else None
    print(f"  mp{p:3d}: truth x {np.mean(side[p]) * 1000:+6.1f} (n {len(side[p])})  | ours x {ours[0] * 1000:+6.1f} sd {t['sd'][0][p]:.2f} mm, "
          f"{(np.linalg.norm(ours - tr) * 1000 if tr is not None else float('nan')):5.1f} mm from truth | "
          + (f"theirs x {theirs[0] * 1000:+6.1f}, {np.linalg.norm(theirs - tr) * 1000:5.1f} mm from truth" if theirs is not None else "not in their table"))
