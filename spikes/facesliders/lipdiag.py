"""lipdiag.py <model>: does a change of identity / lower-face expression reach the BUILT one-mesh head's lip-over-sulcus
step as on GNM's raw mesh? (lipfit's shadow barely moved along directions that moved the raw proxy 2.4 mm per unit.)
For a few single components: the raw proxy change (mid, side) vs the built head's (world, forward = -Y, x head scale)."""
import copy
import sys

import numpy as np

from hifipushie import headfit

headfit.N = 170
import lipfit as LF  # noqa: E402
from hifipushie import humanfit, onemesh, store  # noqa: E402

spec = store.load(sys.argv[1])
z0 = np.r_[humanfit.identity(spec["base"]), LF.h_of(spec)]


def built_proxy(z):
    sp = LF.spec_with(spec, z[:LF.NC], z[LF.NC:])
    st = humanfit.state(sp["base"])
    P = np.asarray(st["tpl"]["P"], float)
    gid = np.asarray(onemesh.asset()["gnm_id"], int)[np.asarray(st["tpl"]["fid"])]
    of = np.full(len(LF.TPL), -1)
    of[gid[gid >= 0]] = np.flatnonzero(gid >= 0)
    out = []
    for top, deep in LF.SETS:
        a, b = of[top], of[deep]
        a, b = a[a >= 0], b[b >= 0]
        out.append(-(P[a, 1].mean() - P[b, 1].mean()))
    return np.array([out[0], 0.5 * (out[1] + out[2])]), float(st["head"]["carry"]["s"])


p0, s = built_proxy(z0)
r0, _ = LF.proxy_jac(z0)
print("start: built", (p0 * 1e3).round(3), "raw x scale", (r0 * s * 1e3).round(3), "scale", s)
for nm, j in (("head_000", 0), ("head_010", 10), ("head_040", 40), ("head_100", 100), ("head_150", 150),
              ("lower_face_000", LF.NC), ("lower_face_003", LF.NC + 3), ("lower_face_010", LF.NC + 10)):
    dz = np.zeros(len(z0))
    dz[j] = 1.0
    p1, _ = built_proxy(z0 + dz)
    _, Jp = LF.proxy_jac(z0)
    print(f"{nm:16s} built d {((p1 - p0) * 1e3).round(3)} mm | raw d x scale {(Jp[:, j] * s * 1e3).round(3)} mm", flush=True)
