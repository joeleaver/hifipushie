"""vermb.py: GNM's upper_lip / lower_lip groups vs the 68 landmarks (template, mm): where each group's outer edge (the
exterior skin's lip vertices next to non-lip skin) lies at the landmarks' x, against the landmark border."""
import numpy as np

from hifipushie import base

g = base._gnm_data()
X = np.asarray(g["template_vertex_positions"], float)
lm = np.array([sum(float(w) * X[int(v)] for v, w in zip(r[0::2], r[1::2])) for r in g["lm68"]])
ext = np.asarray(g["groups"]["skin_exterior"]) > 0.5
Q = np.asarray(g["quads"])
for grp, ids in (("upper_lip", (48, 49, 50, 51, 52, 53, 54)), ("lower_lip", (54, 55, 56, 57, 58, 59, 48))):
    m = (np.asarray(g["groups"][grp]) > 0.5) & ext
    e = np.r_[Q[:, [0, 1]], Q[:, [1, 2]], Q[:, [2, 3]], Q[:, [3, 0]]]
    edge = np.unique(np.r_[e[m[e[:, 0]] & ~m[e[:, 1]] & ext[e[:, 1]], 0]])
    print(grp, "group verts", int(m.sum()), "edge verts", len(edge))
    for i in ids:
        near = edge[np.abs(X[edge, 0] - lm[i][0]) < 0.0015]
        if len(near):
            j = near[np.argmin(np.abs(X[near, 1] - lm[i][1]))]
            print(f"  lm{i}: landmark y {1000*lm[i][1]:.1f}  group edge y {1000*X[j,1]:.1f}  (z {1000*lm[i][2]:.1f} / {1000*X[j,2]:.1f})")
