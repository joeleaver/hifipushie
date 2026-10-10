"""borderquad.py: the template quads round the mouth's creased pairs (faces3): edge lengths, rings, lips."""
import numpy as np

from hifipushie import faceext, faceslide

faceext._turned(np.zeros_like(faceslide.template()["X"]))
X0, Q, pairs = faceext._C["fold"]
R = faceslide._lip_rings()
ring = np.full(len(X0), -1)
for i, r in enumerate(R["rings"]):
    ring[r] = i
up = np.asarray(R["upper"], bool)
T = faceslide.template()
mc = 0.5 * (T["lm"][62] + T["lm"][66])
n = np.cross(X0[Q[:, 2]] - X0[Q[:, 0]], X0[Q[:, 3]] - X0[Q[:, 1]])
n /= np.linalg.norm(n, axis=1, keepdims=True)
a0 = np.degrees(np.arccos(np.clip(np.einsum("ij,ij->i", n[pairs[:, 0]], n[pairs[:, 1]]), -1, 1)))
for i in np.flatnonzero(a0 > 65):
    p = X0[sorted(set(Q[pairs[i, 0]]) & set(Q[pairs[i, 1]]))].mean(0) - mc
    if np.linalg.norm(p) > 0.03 or p[0] < 0:
        continue
    print(f"pair a0 {a0[i]:.1f} at x {p[0]*1e3:+.1f} y {p[1]*1e3:+.1f} z {p[2]*1e3:+.1f}")
    for q in pairs[i]:
        v = Q[q]
        el = [np.linalg.norm(X0[v[k]] - X0[v[(k + 1) % 4]]) * 1e3 for k in range(4)]
        print(f"   quad {q}: verts {list(v)} rings {list(ring[v])} upper {list(up[v].astype(int))} edges mm {np.round(el, 2)}")

import sys  # noqa: E402
if len(sys.argv) > 1:
    d, _, _ = faceext.field(sys.argv[1])
    sc = faceext.fold_free(d, margin=1.0)
    for v in (4617, 4620, 4623, 4655, 4656, 4657, 4680, 4681, 4684):
        print(v, ring[v], np.round(X0[v] * 1e3 - mc * 1e3, 1), "d(mm) at -fold-free", np.round(-sc * d[v] * 1e3, 3))
