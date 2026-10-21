"""faults.py <tag>: where the fit's geometry is off. Per piece: face strain p99 / max (and where), cloth inside the body,
the stand-off from the body (p50 / p95), sewn seams open (per piece pair)."""
import sys, pickle
import numpy as np
from scipy.spatial import cKDTree
from hifipushie import diag_render as dr, cloth
d = pickle.load(open(f"/mnt/data/hifipushie/shirt_spike/{sys.argv[1]}.pkl", "rb"))
X = np.asarray(d["A"], float); M = d["mesh"]; F = np.asarray(M["F"]); pid = np.asarray(M["piece"]); names = list(M["names"])
st = np.abs(dr.face_strain(X, F, M["uv"])); fp = pid[F[:, 0]]; fc = X[F].mean(1)
B = cloth.Body({"V": d["bodyV"], "F": d["bodyF"]}) if False else None
bt = cKDTree(d["bodyV"]); bd, bj = bt.query(X)
# signed: inside if (X - body point) . body normal < 0 (normals from the body faces)
BV, BF = d["bodyV"], d["bodyF"]
n = np.cross(BV[BF[:, 1]] - BV[BF[:, 0]], BV[BF[:, 2]] - BV[BF[:, 0]]); vn = np.zeros_like(BV)
for k in range(3): np.add.at(vn, BF[:, k], n)
vn /= np.linalg.norm(vn, axis=1)[:, None] + 1e-12
sd = ((X - BV[bj]) * vn[bj]).sum(1)
print(f"{'piece':10s} {'strain p99':>10s} {'max':>6s}  worst-at (mm)        inside  off p50 p95 (mm)")
for k, nm in enumerate(names):
    m = fp == k; v = pid == k
    if not m.any(): continue
    w = np.argmax(st[m]); c = fc[m][w]
    print(f"{nm:10s} {np.percentile(st[m],99)*100:9.1f}% {st[m].max()*100:5.0f}%  {np.round(c*1000).astype(int)}  {int((sd[v] < -0.001).sum()):5d}   {np.median(sd[v])*1000:5.1f} {np.percentile(sd[v],95)*1000:5.1f}")
sw = np.asarray(M["sew"]).reshape(-1, 2); gap = np.linalg.norm(X[sw[:, 0]] - X[sw[:, 1]], axis=1)
pairs = {}
for (a, b), g in zip(sw, gap):
    key = tuple(sorted((names[pid[a]], names[pid[b]]))); pairs.setdefault(key, []).append(g)
print("seams open (max mm):", {f"{a}|{b}": round(max(g) * 1000, 1) for (a, b), g in pairs.items() if max(g) > 0.002})
