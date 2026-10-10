"""extfold.py <name> <value>: where an extension turns quads over on the template (nearest landmark, mm, move)."""
import sys

import numpy as np

from hifipushie import faceslide, gnmloops

k, v = sys.argv[1], float(sys.argv[2])
T = faceslide.template()
Q = gnmloops.plan()["quads"]
Q = Q[T["skin"][Q].all(1)]
X0 = T["X"]
D = faceslide.delta({k: v})


def nrm(X):
    n = np.cross(X[Q[:, 2]] - X[Q[:, 0]], X[Q[:, 3]] - X[Q[:, 1]])
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-18)


area = 0.5 * np.linalg.norm(np.cross(X0[Q[:, 2]] - X0[Q[:, 0]], X0[Q[:, 3]] - X0[Q[:, 1]]), axis=1)
bad = np.flatnonzero((np.einsum("ij,ij->i", nrm(X0), nrm(X0 + D)) < 0) & (area > 1.5e-7))
lm = T["lm"]
for q in bad:
    c = X0[Q[q]].mean(0)
    j = int(np.argmin(np.linalg.norm(lm - c, axis=1)))
    print(f"quad {q}: near lm {j} ({np.linalg.norm(lm[j] - c) * 1000:.1f} mm), edge {np.sqrt(area[q]) * 1000:.2f} mm, "
          f"move {np.linalg.norm(D[Q[q]], axis=1).max() * 1000:.2f} mm, ext {bool(T['ext'][Q[q]].all())}")
