"""mlchk.py <refs model>: the mentolabial depth (joint2.mentolabial) of the photo's auto profile contour, mm."""
import json
import sys

import numpy as np

import joint2
import outl
from hifipushie import store

refs = json.loads((store.HOME / sys.argv[1] / "human_refs.json").read_text())
vi = next(i for i, v in enumerate(refs["views"]) if abs(float(v.get("yaw", 0))) > 70)
cam = refs["cameras"][vi]
P = outl.profile_auto(refs["views"][vi])
print("rows", len(P), "depth px", round(joint2.mentolabial(P), 2), "mm ~", round(joint2.mentolabial(P) * cam["t"][2] / cam["f"] * 1000, 2))
n = len(P)
for f in joint2.ML_ROWS:
    print(f, P[int(f * n)])
