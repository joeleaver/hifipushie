"""edgeplot.py <out.png> <tag>...: the collar's outer edge (point -> CB -> point) as seen from the side (y, z) and from
the front (x, z), with the turning per 40 mm along it (deg), so a broad 'three angles' reads as three peaks."""
import sys, pickle
import numpy as np
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from collections import Counter, defaultdict, deque
out = sys.argv[1]; tags = sys.argv[2:]
fig, ax = plt.subplots(1, 3, figsize=(15, 5))
for t in tags:
    d = pickle.load(open(f"/mnt/data/hifipushie/shirt_spike/{t}.pkl", "rb")); X = np.asarray(d["A"]); M = d["mesh"]
    F = np.asarray(M["F"]); pid = np.asarray(M["piece"]); nm = list(M["names"]); P = M["points"]
    k = nm.index("collar"); cnt = Counter(map(tuple, np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1).tolist()))
    adj = defaultdict(list)
    for (a, b), c in cnt.items():
        if c == 1 and pid[a] == k and pid[b] == k: adj[a].append(b); adj[b].append(a)
    sw = set(np.asarray(M["sew"]).ravel().tolist())
    def path(a, b):
        prev = {a: None}; q = deque([a])
        while q:
            x = q.popleft()
            if x == b: break
            for y in adj[x]:
                if y not in prev and (y not in sw or y == b): prev[y] = x; q.append(y)
        o = [b]
        while prev[o[-1]] is not None: o.append(prev[o[-1]])
        return o[::-1]
    ch = np.array(path(P["collar:leftTopEdge"], P["collar:topMid"]) + path(P["collar:topMid"], P["collar:rightTopEdge"])[1:])
    p = X[ch] * 1000; s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    half = ch[: len(path(P["collar:leftTopEdge"], P["collar:topMid"]))]
    side = p[: len(half)][:, [1, 2]]  # wearer's right half (left on screen from the side view)
    ax[0].plot(side[:, 0], side[:, 1], label=t); ax[1].plot(p[:, 0], p[:, 2], label=t)
    tr = []
    for i in range(len(p)):
        a = np.searchsorted(s, s[i] - 20); b = np.searchsorted(s, s[i] + 20) - 1
        if a >= i or b <= i: tr.append(np.nan); continue
        d1, d2 = p[i] - p[a], p[b] - p[i]
        tr.append(np.degrees(np.arccos(np.clip(d1 @ d2 / np.linalg.norm(d1) / np.linalg.norm(d2), -1, 1))))
    ax[2].plot(s - s[len(half) - 1], tr, label=t)
ax[0].set_title("edge from the side (y, z mm), one half"); ax[0].set_aspect("equal"); ax[0].invert_xaxis()
ax[1].set_title("edge from the front (x, z mm)"); ax[1].set_aspect("equal")
ax[2].set_title("turn over 40 mm (deg) vs arc from CB (mm)"); 
for a in ax: a.legend(); a.grid(alpha=.3)
plt.tight_layout(); plt.savefig(out, dpi=80); print(out)
