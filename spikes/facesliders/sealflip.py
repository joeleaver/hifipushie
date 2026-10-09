"""sealflip.py: the template adult's lip quads that turn over under lip_seal 1 (GNM frame): where, rings, sides."""
import copy

import numpy as np

from hifipushie import base, faceslide, gnmloops, humans, onemesh

g = base._gnm_data()
b = humans.spec(age=40, sex=1.0, seed=None, skin=False, source="human")["base"]
b["head"].pop("mouth_gap", None)
V = {}
for s in (0.0, 1.0):
    bt = copy.deepcopy(b)
    bt["head"]["lip_seal"] = s
    V[s] = np.asarray(onemesh.head_template(bt)["carry"]["V"], float)
Q = gnmloops._raw()["quads"]
lips = (np.asarray(g["groups"]["upper_lip"]) > 0.5) | (np.asarray(g["groups"]["lower_lip"]) > 0.5)
Q = Q[lips[Q].any(1) & np.asarray(g["skin"], bool)[Q].all(1)]


def nrm(X):
    n = np.cross(X[Q[:, 2]] - X[Q[:, 0]], X[Q[:, 3]] - X[Q[:, 1]])
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-18)


bad = np.flatnonzero(np.einsum("ij,ij->i", nrm(V[0.0]), nrm(V[1.0])) < 0)
R = faceslide._lip_rings()
ring_of = {int(v): k for k, r in enumerate(R["rings"]) for v in r}
lm = np.array([sum(float(w) * V[0.0][int(v)] for v, w in zip(r[0::2], r[1::2])) for r in g["lm68"]])
c = 0.5 * (lm[62] + lm[66])
for q in bad:
    print("quad", Q[q].tolist(), "at", (1000 * (V[0.0][Q[q]].mean(0) - c)).round(1).tolist(), "rings",
          [ring_of.get(int(v), "-") for v in Q[q]], "upper", [bool(R["upper"][v]) for v in Q[q]],
          "moves", (1000 * (V[1.0][Q[q]] - V[0.0][Q[q]])).round(2).tolist())
