"""jexp.py <model>: crease reads vs the 20 symmetric eye-region expression pairs at the model's identity (gk.geo with e)."""
import sys
import numpy as np
import gk
from hifipushie import blockin as bi, blockin_eyes as be, store
c0 = bi.identity(store.load(sys.argv[1]))
RK = ["local", "x_narrow", "hsoft", "up", "lo", "drop", "x_hidden10"]
g0 = gk.geo(c0)[0]
print("e=0", {k: round(g0[k], 3) for k in RK})
J = np.zeros((len(RK), be.NE))
for k in range(be.NE):
    out = []
    for s in (1.0, -1.0):
        e = np.zeros(be.NE); e[k] = s
        g = gk.geo(c0, e)[0]
        out.append(np.array([g[q] for q in RK]))
    J[:, k] = (out[0] - out[1]) / 2
    print(f"pair {k:2d}: " + ", ".join(f"{q} {out[0][i] - g0[q]:+.2f}/{out[1][i] - g0[q]:+.2f}" for i, q in enumerate(RK)), flush=True)
g = J[0]
print("cheapest +1 mm depth by expression alone: |e|", 1 / np.linalg.norm(g), "side", dict(zip(RK, (J @ (g / (g @ g))).round(2))))
