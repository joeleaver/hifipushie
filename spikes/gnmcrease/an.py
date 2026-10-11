"""an.py [files...]: the sample table: distributions, top lists, correlations with the macros."""
import json
import sys
import glob

import numpy as np

files = sys.argv[1:] or sorted(glob.glob("/mnt/data/hifipushie/gnmcrease/out/s_*.npz"))
rows = []
for f in files:
    z = np.load(f, allow_pickle=True)
    G, K, M, L = (json.loads(str(z[k])) for k in ("geo", "clay", "macro", "lab"))
    kind = f.split("/s_")[1].split("_")[0]
    for i in range(len(G)):
        r = {"kind": kind, "file": f, "i": i, **G[i], **{"k_" + k: v for k, v in K[i].items()}, **{"m_" + k: v for k, v in M[i].items()},
             "c": z["C"][i], "lab": L[i]}
        rows.append(r)
print(len(rows), "samples")
keys = ["drop", "local", "x_narrow", "x_hidden", "x_hidden10", "x_krad", "x_lip", "hsoft", "show", "up", "lo", "k_dark", "k_tps",
        "k_width", "k_dark_max"]
for kind in sorted(set(r["kind"] for r in rows)):
    R = [r for r in rows if r["kind"] == kind]
    print(f"\n== {kind} ({len(R)})")
    for k in keys:
        v = np.array([r.get(k, np.nan) for r in R], float)
        print(f"  {k:12s} p10 {np.nanpercentile(v, 10):6.2f} p50 {np.nanpercentile(v, 50):6.2f} p90 {np.nanpercentile(v, 90):6.2f} "
              f"p99 {np.nanpercentile(v, 99):6.2f} max {np.nanmax(v):6.2f}")
    v = np.array([r["x_hidden"] for r in R])
    print("  frac hidden>0.2:", np.mean(v > 0.2), " dark>0.2:", np.mean(np.array([r.get("k_dark", 0) for r in R]) > 0.2))
