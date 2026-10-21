"""flips.py <tag>...: folded-over cloth near the collar points: faces whose normal points against the mean normal of
their edge neighbours (dihedral > 120 deg), within 25 mm (pattern) of each point; where they are (distance from the
point on the pattern, on the point's front / outer edge or inside)."""
import sys, pickle
import numpy as np
from collections import defaultdict
for t in sys.argv[1:]:
    d = pickle.load(open(f"/mnt/data/hifipushie/shirt_spike/{t}.pkl", "rb")); X = np.asarray(d["A"]); M = d["mesh"]
    F = np.asarray(M["F"]); pid = np.asarray(M["piece"]); nm = list(M["names"]); uv = np.asarray(M["uv"]); P = M["points"]
    fold = np.zeros(len(X), bool)
    for fd in M.get("folds") or []:
        for r in fd["rows"]: fold[np.asarray(r, int)] = True
    fn = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]]); fn /= np.linalg.norm(fn, axis=1)[:, None] + 1e-15
    em = defaultdict(list)
    for fi, f in enumerate(F):
        for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])): em[(min(a, b), max(a, b))].append(fi)
    worst = np.zeros(len(F))
    for (a, b), fs in em.items():
        if len(fs) == 2 and not (fold[a] and fold[b]):
            c = float(fn[fs[0]] @ fn[fs[1]]); ang = np.degrees(np.arccos(np.clip(c, -1, 1)))
            worst[fs[0]] = max(worst[fs[0]], ang); worst[fs[1]] = max(worst[fs[1]], ang)
    for s_ in ("left", "right"):
        o = P[f"collar:{s_}TopEdge"]; dist = np.linalg.norm(uv[F].mean(1) - uv[o], axis=1)
        m = (pid[F[:, 0]] == nm.index("collar")) & (dist < 0.025)
        bad = m & (worst > 120)
        print(f"{t:5s} {s_}: faces near the point {m.sum()}, folded over (>120 deg) {bad.sum()}, worst {worst[m].max():.0f} deg"
              + (f", at {np.round(np.sort(dist[bad])[:6]*1000).astype(int).tolist()} mm from the point" if bad.any() else ""))
