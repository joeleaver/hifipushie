"""bandz.py <tag>...: zigzag of the BAND across its height, round the neck: per angle (every 15 deg), the largest bend
(deg) between consecutive 2 mm segments of the band's section from its neck seam up to 4 mm under its top (the fold
excluded). A smooth band reads < ~15 deg; a crease across it reads 40+."""
import sys, pickle
import numpy as np
for t in sys.argv[1:]:
    d = pickle.load(open(f"/mnt/data/hifipushie/shirt_spike/{t}.pkl", "rb")); X = np.asarray(d["A"]); M = d["mesh"]
    pid = np.asarray(M["piece"]); nm = list(M["names"]); uv = np.asarray(M["uv"]); P = M["points"]
    v = np.where(pid == nm.index("stand"))[0]; ctr = X[v][:, :2].mean(0)
    ybot, ytop = uv[P["stand:bottomMid"], 1], uv[P["stand:topMid"], 1]
    out = []
    for a in range(-150, 151, 15):
        th = np.radians(a); ax = np.array([np.sin(th), np.cos(th)]); rel = X[v, :2] - ctr
        w = v[(np.abs(rel @ np.array([ax[1], -ax[0]])) < 0.003) & (rel @ ax > 0)]
        if len(w) < 6: continue
        h = (uv[w, 1] - ybot) / (ytop - ybot); w = w[(h > 0.02) & (h < 0.85)]; w = w[np.argsort(uv[w, 1])]
        if len(w) < 5: continue
        rz = np.c_[(X[w, :2] - ctr) @ ax, X[w, 2]]
        keep = [0]
        for i in range(1, len(rz)):
            if np.linalg.norm(rz[i] - rz[keep[-1]]) > 0.002: keep.append(i)
        rz = rz[keep]
        if len(rz) < 4: continue
        sg = np.diff(rz, axis=0); an = np.degrees(np.arctan2(sg[:, 1], sg[:, 0])); tr = np.abs((np.diff(an) + 180) % 360 - 180)
        out.append(f"{a:+d}:{tr.max():.0f}")
    print(f"{t:5s} band crease (max bend deg) by angle: " + " ".join(out))
