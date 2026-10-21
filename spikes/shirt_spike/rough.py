"""rough.py <tag>...: crumple read per piece (collar, stand): each vertex's distance from its one-ring centroid along the
local normal (mm), p50 / p95 / p99; the fold rows (a real crease) reported apart. Smooth cloth reads ~0.0x mm at 2 mm."""
import sys, pickle
import numpy as np
for t in sys.argv[1:]:
    d = pickle.load(open(f"/mnt/data/hifipushie/shirt_spike/{t}.pkl", "rb")); X = np.asarray(d["A"]); M = d["mesh"]
    F = np.asarray(M["F"]); pid = np.asarray(M["piece"]); nm = list(M["names"])
    fold = np.zeros(len(X), bool)
    for fd in M.get("folds") or []:
        for r in fd["rows"]: fold[np.asarray(r, int)] = True
    n = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]]); vn = np.zeros_like(X)
    for k in range(3): np.add.at(vn, F[:, k], n)
    vn /= np.linalg.norm(vn, axis=1)[:, None] + 1e-12
    E = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]; E = np.unique(np.sort(E, 1), axis=0)
    E = E[pid[E[:, 0]] == pid[E[:, 1]]]
    S = np.zeros_like(X); c = np.zeros(len(X))
    np.add.at(S, E[:, 0], X[E[:, 1]]); np.add.at(S, E[:, 1], X[E[:, 0]]); np.add.at(c, E[:, 0], 1); np.add.at(c, E[:, 1], 1)
    lap = np.abs(((S / np.maximum(c, 1)[:, None] - X) * vn).sum(1)) * 1000
    out = []
    for p in ("collar", "stand"):
        m = (pid == nm.index(p)) & ~fold & (c >= 5)
        out.append(f"{p} p50 {np.median(lap[m]):.3f} p95 {np.percentile(lap[m],95):.3f} p99 {np.percentile(lap[m],99):.3f}")
    print(f"{t:6s} " + " | ".join(out))
