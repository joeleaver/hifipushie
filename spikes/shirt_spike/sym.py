"""sym.py <tag>...: mirror symmetry of a fit. Every vertex mirrored across x = 0 and matched to the nearest vertex of the
fit itself; a symmetric garment reads ~0 mm. Per piece p50 / p95 / max mm, and which way the worst side is off."""
import sys, pickle
import numpy as np
from scipy.spatial import cKDTree
for tag in sys.argv[1:]:
    d = pickle.load(open(f"/mnt/data/hifipushie/shirt_spike/{tag}.pkl", "rb"))
    X = np.asarray(d["A"], float); M = d["mesh"]; pid = np.asarray(M["piece"]); names = list(M["names"])
    Xm = X * [-1, 1, 1]; dist, j = cKDTree(X).query(Xm)
    print(f"== {tag}: whole p50 {np.median(dist)*1000:.1f} p95 {np.percentile(dist,95)*1000:.1f} max {dist.max()*1000:.1f} mm")
    for k, nm in enumerate(names):
        m = pid == k
        if not m.any(): continue
        dd = dist[m]; w = np.argmax(dd); v = np.where(m)[0][w]
        off = (X[j[v]] - Xm[v]) * 1000
        print(f"  {nm:14s} p50 {np.median(dd)*1000:5.1f} p95 {np.percentile(dd,95)*1000:5.1f} max {dd.max()*1000:5.1f}  worst at {np.round(X[v]*1000).astype(int)} off {np.round(off).astype(int)}")
