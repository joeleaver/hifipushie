"""layers.py <tag>...: the collar's fall through what it is turned over: for each collar vertex (off its fold rows), the
nearest point of the band + fronts + yoke surface (faces, by nearest vertex + its normal sign, outward = away from the
body). A vertex on the INSIDE (signed distance < -0.5 mm) of that layer, within 15 mm of it, is through it. Counts per
region (back / side / front by angle round the neck)."""
import sys, pickle
import numpy as np
from scipy.spatial import cKDTree
for t in sys.argv[1:]:
    d = pickle.load(open(f"/mnt/data/hifipushie/shirt_spike/{t}.pkl", "rb")); X = np.asarray(d["A"]); M = d["mesh"]
    F = np.asarray(M["F"]); pid = np.asarray(M["piece"]); nm = list(M["names"])
    fold = np.zeros(len(X), bool)
    for fd in M.get("folds") or []:
        for r in fd["rows"]: fold[np.asarray(r, int)] = True
    under = np.isin(pid, [nm.index(p) for p in ("stand", "front.L", "front.R", "yoke")])
    fn = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]]); vn = np.zeros_like(X)
    for k in range(3): np.add.at(vn, F[:, k], fn)
    vn /= np.linalg.norm(vn, axis=1)[:, None] + 1e-12
    # orient the under layer's normals outward (away from the body: from the body's nearest point)
    BV = d["bodyV"]; bt = cKDTree(BV); _, bj = bt.query(X); outv = X - BV[bj]
    vn[under & ((vn * outv).sum(1) < 0)] *= -1
    ui = np.where(under)[0]; ut = cKDTree(X[ui])
    col = np.where((pid == nm.index("collar")) & ~fold)[0]
    dd, j = ut.query(X[col]); u = ui[j]
    sd = ((X[col] - X[u]) * vn[u]).sum(1)
    thr = (sd < -0.0005) & (dd < 0.015)
    ctr = X[pid == nm.index("stand")][:, :2].mean(0); ang = np.degrees(np.arctan2(X[col, 0] - ctr[0], X[col, 1] - ctr[1]))
    reg = {"back (<45)": np.abs(ang) < 45, "side (45-110)": (np.abs(ang) >= 45) & (np.abs(ang) < 110), "front (>110)": np.abs(ang) >= 110}
    out = [f"{k} {int((thr & m).sum())}/{int(m.sum())}" for k, m in reg.items()]
    print(f"{t:6s} collar through the band / fronts / yoke: {int(thr.sum())} of {len(col)} ({100*thr.mean():.0f} %): " + ", ".join(out) +
          f"; deepest {(-sd[thr]).max()*1000 if thr.any() else 0:.1f} mm")
# the CONVERSE: band / fronts / yoke vertices poking OUT through the collar: an under vertex covered by the collar (its
# nearest collar point within 10 mm) lying OUTSIDE the collar along the collar's outward normal (> 0.5 mm)
for t in sys.argv[1:]:
    d = pickle.load(open(f"/mnt/data/hifipushie/shirt_spike/{t}.pkl", "rb")); X = np.asarray(d["A"]); M = d["mesh"]
    F = np.asarray(M["F"]); pid = np.asarray(M["piece"]); nm = list(M["names"])
    fn = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]]); vn = np.zeros_like(X)
    for k in range(3): np.add.at(vn, F[:, k], fn)
    vn /= np.linalg.norm(vn, axis=1)[:, None] + 1e-12
    BV = d["bodyV"]; bt = cKDTree(BV); _, bj = bt.query(X); outv = X - BV[bj]
    vn[(vn * outv).sum(1) < 0] *= -1
    ci = np.where(pid == nm.index("collar"))[0]; ct = cKDTree(X[ci])
    und = np.where(np.isin(pid, [nm.index(p) for p in ("stand", "front.L", "front.R", "yoke")]))[0]
    dd, j = ct.query(X[und]); c = ci[j]
    sd = ((X[und] - X[c]) * vn[c]).sum(1); pk = (dd < 0.010) & (sd > 0.0005)
    by = {p: int((pk & (pid[und] == nm.index(p))).sum()) for p in ("stand", "front.L", "front.R", "yoke")}
    print(f"{t:6s} band / fronts / yoke vertices POKING OUT through the collar: {int(pk.sum())} {by}; highest {(sd[pk].max()*1000 if pk.any() else 0):.1f} mm")
