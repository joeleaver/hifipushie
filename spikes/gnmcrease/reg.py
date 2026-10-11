"""reg.py [files]: how linear are the crease reads in identity? ridge fits (CV R^2) per read; the min-norm direction's
cost per unit (1/|w|); and the reads' correlations with the eye-region macros."""
import glob
import json
import sys

import numpy as np

files = sys.argv[1:] or sorted(glob.glob("/mnt/data/hifipushie/gnmcrease/out/s_*.npz"))
C, R, M = [], [], []
for f in files:
    z = np.load(f, allow_pickle=True)
    G, K, Mm = (json.loads(str(z[k])) for k in ("geo", "clay", "macro"))
    for i in range(len(G)):
        C.append(z["C"][i]); R.append({**G[i], **{"k_" + k: v for k, v in K[i].items()}}); M.append(Mm[i])
C = np.array(C)
print(len(C), "samples, |c| median", np.median(np.linalg.norm(C, axis=1)).round(1))
keys = ["local", "x_narrow", "hsoft", "x_hidden10", "drop", "up", "show", "k_dark", "k_tps"]
rng = np.random.default_rng(0)
idx = rng.permutation(len(C))
te, tr = idx[: len(C) // 5], idx[len(C) // 5:]
W = {}
for k in keys:
    y = np.array([r.get(k, np.nan) for r in R], float)
    if k == "x_krad":
        y = np.log(y)
    ok = np.isfinite(y)
    best = None
    for lam in (1, 10, 100, 1000):
        a, b = tr[ok[tr]], te[ok[te]]
        X = np.c_[C[a], np.ones(len(a))]
        w = np.linalg.solve(X.T @ X + lam * np.diag(np.r_[np.ones(170), 0]), X.T @ y[a])
        p = np.c_[C[b], np.ones(len(b))] @ w
        r2 = 1 - np.mean((p - y[b]) ** 2) / np.var(y[b])
        if best is None or r2 > best[0]:
            best = (r2, lam, w)
    r2, lam, w = best
    W[k] = w
    top = np.argsort(-np.abs(w[:170]))[:8]
    print(f"{k:10s} sd {np.nanstd(y):.3f} CV R2 {r2:.2f} (lam {lam}) |w| {np.linalg.norm(w[:170]):.3f} -> |dc| per +1 unit "
          f"{1 / max(np.linalg.norm(w[:170]), 1e-9):.1f} | top comps " + " ".join(f"{j}:{w[j]:+.3f}" for j in top))
np.savez("/mnt/data/hifipushie/gnmcrease/out/reg_w.npz", **{k: v for k, v in W.items()})
# correlations with macros
mk = list(M[0].keys())
Mz = np.array([[m[k] for k in mk] for m in M])
for k in ("local", "x_narrow", "k_dark", "x_hidden10", "hsoft"):
    y = np.array([r.get(k, np.nan) for r in R], float)
    ok = np.isfinite(y)
    cc = [np.corrcoef(y[ok], Mz[ok, j])[0, 1] for j in range(len(mk))]
    o = np.argsort(-np.abs(cc))[:8]
    print(f"{k:10s} macros: " + ", ".join(f"{mk[j]} {cc[j]:+.2f}" for j in o))
