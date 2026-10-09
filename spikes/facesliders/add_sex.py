"""add_sex.py <sexaxis npz>: put the ANSUR-based sex axis (sexaxis.py) into src/hifipushie/face_atlas.npz as
delta_sex (+ its source measures and differences)."""
import sys

import numpy as np

from hifipushie import faceatlas

z = np.load(sys.argv[1], allow_pickle=True)
t = dict(np.load(faceatlas.TABLE, allow_pickle=True))
t["delta_sex"] = z["delta"]
t["sex_keys"] = z["keys"]
t["sex_diff_mm"] = z["diff"]
np.savez(faceatlas.TABLE, **t)
print("delta_sex |", round(float(np.linalg.norm(z["delta"])), 2), "sigmas")
