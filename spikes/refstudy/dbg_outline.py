"""Why does the outline term hurt? One subject, exact landmarks, the outline's residual with the TRUE head and camera."""
import sys

import numpy as np
from scipy.spatial import cKDTree

import fitlib
import rs
import subjects
import table

name = sys.argv[1] if len(sys.argv) > 1 else "S6_plain"
s = subjects.load(name)
for view in ("front", "tq"):
    cam, V = table.view_true(s, view)
    zb = np.load(subjects.OUT / f"{name}_{view}_zb.npy")
    o = rs.outline(zb, cam, V)
    sv = fitlib.silhouette(V, cam)
    P = rs.humanfit.project(cam, V[sv])
    d, j = cKDTree(P).query(o)
    mmpx = cam["t"][2] / cam["f"] * 1000
    print(view, "outline px", len(o), "silhouette verts", len(sv), "TRUE head: outline -> nearest silhouette vertex mm: median",
          round(float(np.median(d) * mmpx), 2), "p90", round(float(np.percentile(d, 90) * mmpx), 2), "max", round(float(d.max() * mmpx), 2))
    g = rs.gnm()
    reg = {k: set(v.tolist()) for k, v in g["regions"].items() if k not in ("face", "head", "profile")}
    cnt = {}
    for v in sv[j]:
        r = next((k for k, st in reg.items() if int(v) in st), "none")
        cnt[r] = cnt.get(r, 0) + 1
    print("   outline pixels by the region of their silhouette vertex:", cnt)
for tag, kw in (("lm only", {}), ("lm + outline", {"outline": True})):
    ev = table.evidence(s, ["front", "tq"], "oracle", noise=0.0, **kw)
    for r in (2, 3, 5, 8):
        f = fitlib.fit(ev, rounds=r)
        print(f"{tag:14s} rounds {r}: " + rs.row(rs.score(rs.head(f["c"]), s["V"])), "sigma", round(float(np.sqrt((f['c'] ** 2).mean())), 2))
