"""build_atlas.py [n]: faceatlas.build (writes src/hifipushie/face_atlas.npz) and prints the attributes' R2 / sd."""
import sys
import numpy as np
from hifipushie import faceatlas
t = faceatlas.build(int(sys.argv[1]) if len(sys.argv) > 1 else 2000)
for nm, sd, r2 in zip(t["names"], t["sd"], t["r2"]):
    print(f"{str(nm):20s} sd {sd:8.3f}  R2 {r2:6.3f}")
