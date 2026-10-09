"""tri.py <model> <view a> <u> <v> <view b> <u> <v>: a point seen in two reference pictures (e.g. the ponytail's tie)
triangulated through the model's fitted cameras: the closest point between the two rays. Prints xyz, the rays'
miss (mm) and the point as [az, el, h] on the model's scalp."""
import json, sys

import numpy as np

from hifipushie import hair, humanfit, store

name = sys.argv[1]
va, ua, wa, vb, ub, wb = int(sys.argv[2]), *map(float, sys.argv[3:5]), int(sys.argv[5]), *map(float, sys.argv[6:8])
refs = json.loads((store.HOME / name / "human_refs.json").read_text())


def ray(vi, u, v):
    cam = refs["cameras"][vi]
    R = humanfit._cam_rot(cam)
    eye = np.asarray(cam["centre"], float) - R.T @ np.asarray(cam["t"], float)
    w, h = cam["size"]
    d = R.T @ np.array([(u - w / 2) / cam["f"], (v - h / 2) / cam["f"], 1.0])
    return eye, d / np.linalg.norm(d)


(o1, d1), (o2, d2) = ray(va, ua, wa), ray(vb, ub, wb)
# closest points o1 + s d1, o2 + t d2
A = np.array([[d1 @ d1, -d1 @ d2], [d1 @ d2, -d2 @ d2]])
b = np.array([(o2 - o1) @ d1, (o2 - o1) @ d2])
s, t = np.linalg.solve(A, b)
p1, p2 = o1 + s * d1, o2 + t * d2
P = 0.5 * (p1 + p2)
sc = hair.scalp(name)
az, el, hp = sc.coords(P[None])
print(f"xyz {np.round(P, 4)}  rays miss {np.linalg.norm(p1 - p2) * 1000:.1f} mm  az {float(az[0]) % 360:.1f} el {float(el[0]):.1f} "
      f"h {float(hp[0]) * 1000:.0f} mm off the scalp; head centre {np.round(sc.C, 4)}")
