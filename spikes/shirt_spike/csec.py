"""csec.py <tag>...: the collar's sections round the neck (angle from CB, 0 = CB, 90 = the wearer's left side, 180 = CF):
the band's neck seam z and top z, the fall's outer edge z (lowest collar vertex there), cover = band seam - outer edge
(> 0: the fall covers the neck seam, as a turned-down collar does), stand-off of the fall's edge from the neck axis."""
import sys, pickle
import numpy as np
for t in sys.argv[1:]:
    d = pickle.load(open(f"/mnt/data/hifipushie/shirt_spike/{t}.pkl", "rb"))
    X = np.asarray(d["A"], float); M = d["mesh"]; pid = np.asarray(M["piece"]); nm = list(M["names"])
    S = X[pid == nm.index("stand")]; C = X[pid == nm.index("collar")]
    ctr = np.r_[S[:, :2].mean(0)]
    ang = lambda P: np.degrees(np.arctan2(P[:, 0] - ctr[0], P[:, 1] - ctr[1]))  # 0 at +Y (CB), +90 toward +X
    aS, aC = ang(S), ang(C)
    print(f"== {t}  (centre {np.round(ctr*1000).astype(int)} mm)")
    print(" angle  band seam z  band top z  fall edge z  cover mm  fall edge r  band r")
    for a in (0, 45, 90, 135, 160, -45, -90, -135, -160):
        ms = np.abs(((aS - a + 180) % 360) - 180) < 6; mc = np.abs(((aC - a + 180) % 360) - 180) < 6
        if not ms.any() or not mc.any(): print(f" {a:5d}  (none)"); continue
        zs0, zs1 = S[ms, 2].min(), S[ms, 2].max(); zc = C[mc, 2].min()
        rc = np.linalg.norm(C[mc][np.argmin(C[mc, 2]), :2] - ctr); rs = np.linalg.norm(S[ms, :2] - ctr, axis=1).mean()
        print(f" {a:5d}  {zs0*1000:9.0f}  {zs1*1000:9.0f}  {zc*1000:10.0f}  {(zs0-zc)*1000:7.0f}  {rc*1000:10.0f}  {rs*1000:6.0f}")
