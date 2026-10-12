"""eyepos.py <model> ...: where the eyeballs sit (world mm): centres apart, and against the lid corners' midpoints
(the eye landmarks 36-39 / 42-45): is the ball centred in its opening, across and up?"""
import sys

import numpy as np

from hifipushie import onemesh, store

for name in sys.argv[1:]:
    b = store.load(name)["base"]
    ht = onemesh.head_rest(b)
    e = np.array(ht["eyes"]) * 1000
    lm = np.asarray(ht["lm68"]) * 1000
    cl, cr = 0.5 * (lm[42] + lm[45]), 0.5 * (lm[36] + lm[39])
    io = abs(lm[42][0] + lm[45][0] - lm[36][0] - lm[39][0]) / 2
    print(f"{name}: ball r {ht['eye_r'] * 1000:.2f}; centres apart {abs(e[0][0] - e[1][0]):.2f} mm; the openings' middles apart {io:.2f}; "
          f"left ball vs its opening's middle: across {e[0][0] - cl[0]:+.2f}, up {e[0][2] - cl[2]:+.2f}, back {e[0][1] - cl[1]:+.2f} mm; "
          f"eye corner to corner {np.linalg.norm(lm[42] - lm[45]):.2f} mm")
