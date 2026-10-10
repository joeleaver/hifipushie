"""extfold.py <name> <scale>: where an extension (stored field / its fold-free scale x scale) turns quads over or folds
neighbours on the template (test_faceslide's criteria): nearest landmark, distance, quad size, move."""
import sys

import numpy as np

from hifipushie import faceext, faceslide, gnmloops

k, v = sys.argv[1], float(sys.argv[2])
T = faceslide.template()
tab = faceext.table()
D = np.asarray(tab[k], float) / float(tab[f"{k}__scale"]) * v
Q = gnmloops.plan()["quads"]
Q = Q[T["skin"][Q].all(1)]
X0 = T["X"]


def nrm(X):
    n = np.cross(X[Q[:, 2]] - X[Q[:, 0]], X[Q[:, 3]] - X[Q[:, 1]])
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-18)


n0, n1 = nrm(X0), nrm(X0 + D)
ef = {}
for qi, q in enumerate(Q):
    for j in range(4):
        ef.setdefault(tuple(sorted((int(q[j]), int(q[(j + 1) % 4])))), []).append(qi)
pairs = np.array([p for p in ef.values() if len(p) == 2])
ang = lambda a: np.degrees(np.arccos(np.clip(a, -1, 1)))  # noqa: E731
a0 = np.einsum("ij,ij->i", n0[pairs[:, 0]], n0[pairs[:, 1]])
a1 = np.einsum("ij,ij->i", n1[pairs[:, 0]], n1[pairs[:, 1]])
fold = pairs[(a1 < np.cos(np.radians(60))) & (ang(a1) - ang(a0) > 10)].ravel()
bad = np.unique(np.r_[np.flatnonzero(np.einsum("ij,ij->i", n0, n1) < 0), fold])
lm = T["lm"]
area = 0.5 * np.linalg.norm(np.cross(X0[Q[:, 2]] - X0[Q[:, 0]], X0[Q[:, 3]] - X0[Q[:, 1]]), axis=1)
for q in bad[:14]:
    c = X0[Q[q]].mean(0)
    j = int(np.argmin(np.linalg.norm(lm - c, axis=1)))
    print(f"quad {q}: near lm {j} ({np.linalg.norm(lm[j] - c) * 1000:.1f} mm), edge {np.sqrt(area[q]) * 1000:.2f} mm, "
          f"move {np.linalg.norm(D[Q[q]], axis=1).max() * 1000:.2f} mm, ext {bool(T['ext'][Q[q]].all())}")
print(len(bad), "quads")
