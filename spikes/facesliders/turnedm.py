"""turnedm.py <model> <slider> <value>: template quads turned over by a slider on a model's own head."""
import copy
import sys

import numpy as np

from hifipushie import humanfit, store

b0 = store.load(sys.argv[1])["base"]
b1 = copy.deepcopy(b0)
b1["head"].setdefault("sliders", {})[sys.argv[2]] = float(sys.argv[3])
P0 = np.asarray(humanfit.state(b0)["tpl"]["P"])
st = humanfit.state(b1)
P1 = np.asarray(st["tpl"]["P"])
Q = np.asarray(st["tpl"]["L"]).reshape(-1, 4)
n0 = np.cross(P0[Q[:, 2]] - P0[Q[:, 0]], P0[Q[:, 3]] - P0[Q[:, 1]])
n1 = np.cross(P1[Q[:, 2]] - P1[Q[:, 0]], P1[Q[:, 3]] - P1[Q[:, 1]])
print(sys.argv[1:], "turned", int(((n0 * n1).sum(1) < 0).sum()), "max move mm", round(1000 * float(np.linalg.norm(P1 - P0, axis=1).max()), 2))
