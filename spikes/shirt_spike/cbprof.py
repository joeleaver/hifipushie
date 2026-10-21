"""cbprof.py <tag>...: the collar + band section at CB (|x| < 3 mm): y, z of each vertex in flat order from the band's
neck seam up, then the collar from its sewn edge out to its outer edge. The shape of the fold, in mm."""
import sys, pickle
import numpy as np
for t in sys.argv[1:]:
    d = pickle.load(open(f"/mnt/data/hifipushie/shirt_spike/{t}.pkl", "rb"))
    X = np.asarray(d["A"]); M = d["mesh"]; pid = np.asarray(M["piece"]); nm = list(M["names"]); uv = np.asarray(M["uv"])
    out = []
    for p, start in (("stand", "bottomMid"), ("collar", "bottomMid")):
        k = M["points"][f"{p}:{start}"]; v = np.where(pid == nm.index(p))[0]; v = v[np.abs(X[v, 0]) < 0.003]
        o = np.argsort(np.linalg.norm(uv[v] - uv[k], axis=1)); prev = None
        for i in v[o]:
            s = np.linalg.norm(uv[i] - uv[k]) * 1000
            if prev is None or s - prev > 1.5: out.append(f"{p[0]}{s:4.0f}:({X[i,1]*1000:.0f},{X[i,2]*1000:.0f})"); prev = s
    print(t, " ".join(out))
