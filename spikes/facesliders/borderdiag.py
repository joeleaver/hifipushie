"""borderdiag.py [names]: where each mouth extension first folds (faces3): the folded quad pairs at the first failing
scale, their template angle, lip ring (rings out from the open mouth loop) and position (mm from the mouth centre)."""
import sys

import numpy as np

from hifipushie import faceext, faceslide

import os  # noqa: E402
for k in ("CREASE_R", "HOLD_CREASES"):
    if os.environ.get(k):
        setattr(faceext, k, type(getattr(faceext, k))(os.environ[k]))
names = sys.argv[1].split(",") if len(sys.argv) > 1 else [k for k, v in faceext.EXT.items() if v[0] == "mouth"]
faceext._turned(np.zeros_like(faceslide.template()["X"]))
X0, Q, pairs = faceext._C["fold"]
R = faceslide._lip_rings()
ring = np.full(len(X0), -1)
for i, r in enumerate(R["rings"]):
    ring[r] = i
T = faceslide.template()
mc = 0.5 * (T["lm"][62] + T["lm"][66])


def nrm(X):
    n = np.cross(X[Q[:, 2]] - X[Q[:, 0]], X[Q[:, 3]] - X[Q[:, 1]])
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-18)


ang = lambda a: np.degrees(np.arccos(np.clip(a, -1, 1)))  # noqa: E731
n0 = nrm(X0)
a0 = ang(np.einsum("ij,ij->i", n0[pairs[:, 0]], n0[pairs[:, 1]]))
for k in names:
    d, share, cn = faceext.field(k)
    sc = faceext.fold_free(d, margin=1.0)
    m = np.linalg.norm(d, axis=1)
    print(f"== {k}: max {m.max()*1e3:.2f} mm at +1, fold-free {sc:.3f} ({sc*m.max()*1e3:.2f} mm)")
    for sgn in (1, -1):
        D = sgn * min(1.0, sc * 1.05 + 0.01) * d
        n1 = nrm(X0 + D)
        a1 = ang(np.einsum("ij,ij->i", n1[pairs[:, 0]], n1[pairs[:, 1]]))
        f = np.flatnonzero((a1 > 60) & (a1 - a0 > 10))
        turned = np.flatnonzero(np.einsum("ij,ij->i", n0, n1) < 0)
        print(f"  sign {sgn:+d} at {abs(D).max()*1e3:.2f}: {len(f)} folded pairs, {len(turned)} turned quads")
        for i in f[:12]:
            qa, qb = Q[pairs[i, 0]], Q[pairs[i, 1]]
            sh = sorted(set(qa) & set(qb))
            p = X0[sh].mean(0) - mc
            print(f"    a0 {a0[i]:5.1f} -> {a1[i]:5.1f}  rings {sorted(set(ring[sh]))}  at x {p[0]*1e3:+6.1f} y {p[1]*1e3:+6.1f} z {p[2]*1e3:+6.1f}"
                  f"  |d| {np.linalg.norm(D[sh],axis=1).mean()*1e3:.2f}  shear {np.linalg.norm(D[qa].mean(0)-D[qb].mean(0))*1e3:.2f}")
        for i in turned[:5]:
            p = X0[Q[i]].mean(0) - mc
            print(f"    turned quad rings {sorted(set(ring[Q[i]]))} at x {p[0]*1e3:+6.1f} y {p[1]*1e3:+6.1f}")
near = np.linalg.norm(X0[Q[pairs[:, 0]]].mean(1) - mc, axis=1) < 0.03
print("template pairs near the mouth > 45 deg:", int((near & (a0 > 45)).sum()), "> 60:", int((near & (a0 > 60)).sum()))
for i in np.flatnonzero(near & (a0 > 50))[:40]:
    sh = sorted(set(Q[pairs[i, 0]]) & set(Q[pairs[i, 1]]))
    p = X0[sh].mean(0) - mc
    print(f"   crease {a0[i]:5.1f} rings {sorted(set(ring[sh]))} x {p[0]*1e3:+6.1f} y {p[1]*1e3:+6.1f}")
