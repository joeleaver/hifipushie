"""folds.py <slider> <value>: the neighbouring skin quads that fold under a slider (template frame): where (mm from the
left eye's inner corner), the angle between them before -> after, exterior or not."""
import sys

import numpy as np

from hifipushie import faceslide, gnmloops

nm, v = sys.argv[1], float(sys.argv[2])
T = faceslide.template()
X = T["X"]
Q = gnmloops.plan()["quads"]
Q = Q[T["skin"][Q].all(1)]


def nrm(Y):
    n = np.cross(Y[Q[:, 2]] - Y[Q[:, 0]], Y[Q[:, 3]] - Y[Q[:, 1]])
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-18)


ef = {}
for qi, q in enumerate(Q):
    for k in range(4):
        ef.setdefault(tuple(sorted((int(q[k]), int(q[(k + 1) % 4])))), []).append(qi)
pairs = np.array([p for p in ef.values() if len(p) == 2])
n0, n1 = nrm(X), nrm(X + faceslide.delta({nm: v}))
a0 = np.einsum("ij,ij->i", n0[pairs[:, 0]], n0[pairs[:, 1]])
a1 = np.einsum("ij,ij->i", n1[pairs[:, 0]], n1[pairs[:, 1]])
bad = np.flatnonzero((a1 < np.cos(np.radians(60))) & (a1 < a0 - 0.05))
c_in = T["lm"][42]
for i in bad:
    c = X[Q[pairs[i]].ravel()].mean(0)
    print(f"{1000 * (c - c_in).round(4)} angle {np.degrees(np.arccos(np.clip(a0[i], -1, 1))):.0f} -> "
          f"{np.degrees(np.arccos(np.clip(a1[i], -1, 1))):.0f} deg, exterior {T['ext'][Q[pairs[i]]].all(1).tolist()}")
