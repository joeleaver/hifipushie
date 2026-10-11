"""jac.py <model> [h]: at the model's identity (expression cleared, as gk.geo): finite-difference Jacobians of the lid
reads (local, x_narrow, hsoft, up, lo, show, drop) and the socket macros (orbital_rim, lower_orbit, eye_depth, + brow_ridge,
brow_height), the exact Jacobian of the 68 landmarks (perc). Then: the cheapest identity move (|dc|) for +1 mm of crease
depth, (a) free, (b) socket held, (c) socket + landmarks held (the eye step's holds), (d) + lid aperture held.
Writes out/jac_<model>.npz."""
import sys
import numpy as np
import gk
import lidgnm, perc
from hifipushie import blockin as bi, store

m = sys.argv[1]
h = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
c0 = bi.identity(store.load(m))
RK = ["local", "x_narrow", "hsoft", "up", "lo", "show", "drop", "x_hidden10", "lsoft"]
MK = ["orbital_rim", "lower_orbit", "eye_depth", "brow_ridge", "brow_height", "eye_height", "cheek_fullness"]


def reads(c):
    g, _, ht = gk.geo(c)
    mm = gk.macro(c)
    return np.array([g[k] for k in RK]), np.array([mm[k] for k in MK])


import os
if os.environ.get("LOAD"):
    z = np.load(f"/mnt/data/hifipushie/gnmcrease/out/jac_{m}.npz"); JR, JM, JL, JB = z["JR"], z["JM"], z["JL"], z["JB"]
r0, m0 = reads(c0)
print("at", m, dict(zip(RK, r0.round(3))), dict(zip(MK, m0.round(2))), flush=True)
if not os.environ.get("LOAD"):
  JR, JM = np.zeros((len(RK), 170)), np.zeros((len(MK), 170))
  for j in range(170):
    e = np.zeros(170); e[j] = h
    rp, mp = reads(c0 + e)
    rm, mm_ = reads(c0 - e)
    JR[:, j] = (rp - rm) / (2 * h)
    JM[:, j] = (mp - mm_) / (2 * h)
# landmarks (68 x 3, mm), linear
HOLD = [i for i in range(68) if not (36 <= i < 48 or 17 <= i < 27)]
BROWS = list(range(17, 27))
B = np.stack([perc.WLM @ perc.world(perc.IB[lidgnm.HC[j]] + perc.TPL) - perc.WLM @ perc.world(perc.TPL) for j in range(170)], -1) * 1000
JL = B[HOLD].reshape(-1, 170) / 0.3       # sigma 0.3 mm (eye step)
JB = B[BROWS].reshape(-1, 170) / 1.0
np.savez(f"/mnt/data/hifipushie/gnmcrease/out/jac_{m}.npz", JR=JR, JM=JM, JL=JL, JB=JB, c0=c0, r0=r0, m0=m0, RK=RK, MK=MK)


def cheapest(g, A):
    """MAP-style: min |x|^2 + |A x|^2 s.t. g.x = 1 (A rows already divided by their sigmas). Returns x; prints the
    total cost sqrt(|x|^2 + |Ax|^2) too via the caller."""
    M = np.eye(170) + (A.T @ A if A is not None else 0)
    y = np.linalg.solve(M, g)
    return y / (g @ y)


gl = JR[RK.index("local")]
gn = JR[RK.index("x_narrow")]
sock = JM[:3] / 0.15
for nm, A in (("free", None), ("socket held (0.15 sd)", sock), ("socket + landmarks (0.3 mm)", np.r_[sock, JL]),
              ("socket + landmarks + brows (1 mm)", np.r_[sock, JL, JB]),
              ("landmarks + brows only (socket free)", np.r_[JL, JB]),
              ("+ lid aperture (0.05 iris r)", np.r_[sock, JL, JB, JR[[3, 4]] / 0.05])):
    for tn, g in (("depth", gl), ("narrow", gn)):
        x = cheapest(g, A)
        pen = np.linalg.norm(A @ x) if A is not None else 0.0
        print(f"{nm:38s} +1 mm {tn:6s}: |dc| {np.linalg.norm(x):6.2f} hold-penalty {pen:6.2f} | " +
              ", ".join(f"{k} {v:+.2f}" for k, v in zip(RK, JR @ x) if k in ("local", "x_narrow", "hsoft", "up", "show")) + " | " + ", ".join(f"{k} {v:+.2f}" for k, v in zip(MK, JM @ x)),
              flush=True)
