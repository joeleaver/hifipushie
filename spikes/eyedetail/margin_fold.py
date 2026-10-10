"""margin_fold.py: where lid_margin_upper/lower fold neighbouring quads (test_faceslide's criterion)."""
import sys

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, "tests")
import test_faceslide as tf  # noqa: E402
from hifipushie import faceslide  # noqa: E402

T = faceslide.template()
X = T["X"]
Q = tf._skin_quads()
n0 = tf._normals(X, Q)
ef = {}
for qi, q in enumerate(Q):
    for k in range(4):
        e = tuple(sorted((q[k], q[(k + 1) % 4])))
        ef.setdefault(e, []).append(qi)
pairs = np.array([v for v in ef.values() if len(v) == 2])
a0 = np.einsum("ij,ij->i", n0[pairs[:, 0]], n0[pairs[:, 1]])
rimL = T["rim"][X[T["rim"], 0] > 0]
tree = cKDTree(X[rimL])
lm = T["lm"]
for name in ("lid_margin_upper", "lid_margin_lower"):
    for v in (0.5, 1.0, 1.5):
        X1 = X + faceslide.delta({name: v})
        n1 = tf._normals(X1, Q)
        a1 = np.einsum("ij,ij->i", n1[pairs[:, 0]], n1[pairs[:, 1]])
        ang = lambda a: np.degrees(np.arccos(np.clip(a, -1, 1)))  # noqa: E731
        fold = (a1 < np.cos(np.radians(60))) & (ang(a1) - ang(a0) > 10)
        print(name, v, int(fold.sum()))
        for p in pairs[fold][:6]:
            c = X[Q[p[0]]].mean(0)
            d = tree.query(c)[0]
            u = (c - lm[42]) @ (lm[45] - lm[42]) / np.linalg.norm(lm[45] - lm[42]) ** 2
            print(f"   at d {d * 1000:.2f} mm, u {u:.2f}, angle {ang(a0[fold][0]):.0f} -> {ang(a1[fold][0]):.0f}")
