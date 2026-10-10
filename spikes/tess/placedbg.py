"""placedbg.py <model> <garment> [piece ...]: the place check's start (as the build places it), and per named piece
its worst start stretch, where (pattern uv), its seam gaps to each partner, and its push off the body."""
import os, sys
import numpy as np
from hifipushie import cloth, cloth_workflow
from hifipushie.cloth_zozo import _start_stretch

name, g, pieces = sys.argv[1], sys.argv[2], sys.argv[3:]
c = cloth_workflow.Ctx(name, g) if hasattr(cloth_workflow, "Ctx") else None
Bp = c.Bp
M = cloth.mesh(Bp, float(os.environ.get("RES") or c.gx.get("coarse", 0.02)))
smooth = cloth.placement_of(c.gx) == "smooth"
body_p = c.body.straight_arms()[0] if smooth else c.body
X = cloth.place(Bp, M, body_p, smooth=smooth)
F = M["F"]
s = _start_stretch(np.c_[M["uv"], np.zeros(len(M["uv"]))], X, F)
P = M["piece"][F[:, 0]]
sw = np.asarray(M["sew"])
for nm in pieces or M["names"]:
    k = M["names"].index(nm)
    sel = np.where(P == k)[0]
    o = sel[np.argsort(-s[sel])[:4]]
    print(f"{nm}: max {s[sel].max():.2f} p95 {np.percentile(s[sel], 95):.2f}; worst at uv "
          + ", ".join(str(np.round(M["uv"][F[i]].mean(0), 3).tolist()) + f" {s[i]:.2f}" for i in o))
    for other in M["names"]:
        ko = M["names"].index(other)
        m = ((M["piece"][sw[:, 0]] == k) & (M["piece"][sw[:, 1]] == ko)) | ((M["piece"][sw[:, 1]] == k) & (M["piece"][sw[:, 0]] == ko))
        if m.any():
            d = np.linalg.norm(X[sw[m, 0]] - X[sw[m, 1]], axis=1)
            print(f"   seam to {other}: gap median {np.median(d) * 1000:.0f} max {d.max() * 1000:.0f} mm")
import os
if os.environ.get("PROBE"):  # PROBE=piece:x  -> the column of that piece at pattern x: uv and X per vertex
    pn, px = os.environ["PROBE"].split(":")
    k = M["names"].index(pn)
    vs = np.where((M["piece"] == k) & (np.abs(M["uv"][:, 0] - float(px)) < 0.006))[0]
    for v in vs[np.argsort(M["uv"][vs, 1])]:
        print(f"   uv {np.round(M['uv'][v], 4).tolist()} X {np.round(X[v], 4).tolist()}  unpushed {np.round(Bp['start_unpushed'][v], 4).tolist()}")
if os.environ.get("BODYGAP"):  # per piece: the closest cloth vertex to the body (sampled collider) and its uv
    from scipy.spatial import cKDTree
    Bv, Bt = body_p.V, body_p.T
    Sb = np.r_[Bv, Bv[Bt].mean(1), 0.5 * (Bv[Bt[:, 0]] + Bv[Bt[:, 1]]), 0.5 * (Bv[Bt[:, 1]] + Bv[Bt[:, 2]]),
               0.5 * (Bv[Bt[:, 2]] + Bv[Bt[:, 0]])]
    dd, _ = cKDTree(Sb).query(X)
    for k, nm in enumerate(M["names"]):
        sel = np.where(M["piece"] == k)[0]
        i = sel[np.argmin(dd[sel])]
        print(f"   body gap {nm}: min {dd[i] * 1000:.2f} mm at uv {np.round(M['uv'][i], 3).tolist()}")
print("sleeve_hits per round:", Bp.get("sleeve_hits"))
