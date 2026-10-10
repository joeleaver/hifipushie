"""hairline.py <model> <trace json> <view index> <x0> <x1> <y_brow>: the front hairline from a traced hair mask: per
column x0..x1 (px), the lowest hair pixel above y_brow (scanning up from the brow), lifted onto the scalp through the
fitted camera: groom.hairline.front_points [[az, z], ...] (az >= 0: the left half, mirrored by the groom). Prints
the json patch."""
import json, sys

import numpy as np
from PIL import Image

from hifipushie import hair, humanfit, store

name, tj, vi = sys.argv[1], sys.argv[2], int(sys.argv[3])
x0, x1, yb = int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])
refs = json.loads((store.HOME / name / "human_refs.json").read_text())
cam = refs["cameras"][vi]
R = humanfit._cam_rot(cam)
eye = np.asarray(cam["centre"], float) - R.T @ np.asarray(cam["t"], float)
w, h = cam["size"]
sc = hair.scalp(name)
mask = np.asarray(Image.open(tj.replace(".json", "_mask.png")).convert("L")) > 127
pts = []
for x in range(x0, x1 + 1, 12):
    col = mask[:yb, x]
    ys = np.nonzero(col)[0]
    if not len(ys):
        continue
    y = int(ys.max())  # the hair's lowest pixel over the forehead in this column
    d = R.T @ np.array([(x - w / 2) / cam["f"], (y - h / 2) / cam["f"], 1.0])
    d /= np.linalg.norm(d)
    P = eye + np.linspace(0.2, 3.0, 2800)[:, None] * d
    az, el, hp = sc.coords(P)
    i = int(np.argmax(hp < 0.0005)) if (hp < 0.0005).any() else int(np.argmin(hp))
    a = float(az[i]) % 360
    a = a - 360 if a > 180 else a
    pts.append((abs(a), round(float(P[i, 2]), 4)))
# one z per azimuth bin (both sides folded onto the left), smoothed
pts.sort()
bins = {}
for a, z in pts:
    bins.setdefault(int(a // 5) * 5, []).append(z)
fp = [[k + 2.5, round(float(np.median(v)), 4)] for k, v in sorted(bins.items())]
print(json.dumps({"hairline": {"front_points": fp}}))
