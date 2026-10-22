"""profile.py <tag>...: the collar's outer edge seen from the side (Joe's "one continuous swoop instead of three different
angles"): the fall's outer-edge vertices (collar boundary, not the sewn edge, between the two points), each side's half
from CB to its point projected on the side plane (y, z); the turn of the edge's direction over 15 mm windows; the
largest turns (deg) and where (angle round the neck from CB). One smooth swoop: small, evenly spread turns."""
import sys, pickle
import numpy as np
for t in sys.argv[1:]:
    d = pickle.load(open(f"/mnt/data/hifipushie/shirt_spike/{t}.pkl", "rb")); X = np.asarray(d["A"]); M = d["mesh"]
    pid = np.asarray(M["piece"]); nm = list(M["names"]); uv = np.asarray(M["uv"]); P = M["points"]; F = np.asarray(M["F"])
    k = nm.index("collar"); v = np.where(pid == k)[0]
    E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1), axis=0)
    E = E[(pid[E[:, 0]] == k) & (pid[E[:, 1]] == k)]
    from collections import Counter
    cnt = Counter(map(tuple, np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1).tolist()))
    bE = np.array([e for e in map(tuple, E.tolist()) if cnt[e] == 1])
    bv = np.unique(bE)
    sw = set(np.asarray(M["sew"]).ravel().tolist()); outer = np.array([i for i in bv if i not in sw])
    ctr = X[pid == nm.index("stand")][:, :2].mean(0)
    out = []
    for side, sg in (("left", -1), ("right", 1)):
        pt = P[f"collar:{side}TopEdge"]
        o = outer[np.sign(uv[outer, 0] - uv[P["collar:topMid"], 0]) == np.sign(uv[pt, 0] - uv[P["collar:topMid"], 0])]
        o = o[np.argsort(np.abs(uv[o, 0] - uv[P["collar:topMid"], 0]))]
        yz = X[o][:, [1, 2]]; s_ = np.r_[0, np.cumsum(np.linalg.norm(np.diff(X[o], axis=0), axis=1))]
        ang_r = np.degrees(np.arctan2(X[o, 0] - ctr[0], X[o, 1] - ctr[1]))
        turns = []
        for i in range(len(o)):
            a = np.searchsorted(s_, s_[i] - 0.0075); b = np.searchsorted(s_, s_[i] + 0.0075) - 1
            if a >= i or b <= i: continue
            d1 = yz[i] - yz[a]; d2 = yz[b] - yz[i]
            t_ = np.degrees(np.arccos(np.clip(d1 @ d2 / (np.linalg.norm(d1) * np.linalg.norm(d2) + 1e-12), -1, 1)))
            turns.append((t_, ang_r[i]))
        turns = np.array(turns); turns = turns[np.abs(turns[:, 1]) < np.abs(ang_r[-1]) - 12]  # (not the point's own corner)
        top = turns[np.argsort(-turns[:, 0])][:3]
        out.append(f"{side}: max turn {top[0,0]:.0f} deg at {top[0,1]:+.0f}, then {top[1,0]:.0f} at {top[1,1]:+.0f}, {top[2,0]:.0f} at {top[2,1]:+.0f}; p50 {np.median(turns[:,0]):.0f}")
    print(f"{t:5s} side-view edge kinks: " + " | ".join(out))
