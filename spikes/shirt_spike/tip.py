"""tip.py <tag>...: the collar points' tips: within 15 mm (pattern) of each point, crumple p95 (mm, rough.py's read) and
edge stretch max (%), and the tip's twist: angle between the leaf's normal near the point and near the leaf's middle."""
import sys, pickle
import numpy as np
for t in sys.argv[1:]:
    d = pickle.load(open(f"/mnt/data/hifipushie/shirt_spike/{t}.pkl", "rb")); X = np.asarray(d["A"]); M = d["mesh"]
    F = np.asarray(M["F"]); pid = np.asarray(M["piece"]); nm = list(M["names"]); uv = np.asarray(M["uv"]); P = M["points"]
    n = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]]); vn = np.zeros_like(X)
    for k in range(3): np.add.at(vn, F[:, k], n)
    vn /= np.linalg.norm(vn, axis=1)[:, None] + 1e-12
    E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1), axis=0); E = E[pid[E[:, 0]] == pid[E[:, 1]]]
    S = np.zeros_like(X); c = np.zeros(len(X))
    np.add.at(S, E[:, 0], X[E[:, 1]]); np.add.at(S, E[:, 1], X[E[:, 0]]); np.add.at(c, E[:, 0], 1); np.add.at(c, E[:, 1], 1)
    lap = np.abs(((S / np.maximum(c, 1)[:, None] - X) * vn).sum(1)) * 1000
    st = np.abs(np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1) / np.maximum(np.linalg.norm(uv[E[:, 0]] - uv[E[:, 1]], axis=1), 1e-9) - 1) * 100
    out = []
    for s_ in ("left", "right"):
        o = P[f"collar:{s_}TopEdge"]; ck = pid == nm.index("collar")
        near = ck & (np.linalg.norm(uv - uv[o], axis=1) < 0.015) & (c >= 3)
        en = near[E[:, 0]] & near[E[:, 1]]
        mid = ck & (np.abs(np.linalg.norm(uv - uv[o], axis=1) - 0.04) < 0.005)
        tw = np.degrees(np.arccos(np.clip(abs(vn[near].mean(0) @ vn[mid].mean(0)) / (np.linalg.norm(vn[near].mean(0)) * np.linalg.norm(vn[mid].mean(0))), -1, 1)))
        out.append(f"{s_}: crumple p95 {np.percentile(lap[near],95):.2f} mm, stretch max {st[en].max():.0f} %, twist {tw:.0f} deg")
    print(f"{t:5s} " + " | ".join(out))
