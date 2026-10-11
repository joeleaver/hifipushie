import glob, json
import numpy as np
rows = []
for f in sorted(glob.glob("/mnt/data/hifipushie/gnmcrease/out/s_*_[123].npz")):
    z = np.load(f, allow_pickle=True)
    G, K = json.loads(str(z["geo"])), json.loads(str(z["clay"]))
    for i in range(len(G)):
        rows.append((f.split("s_")[1][:-4], i, {**G[i], **{"k_" + k: v for k, v in K[i].items()}}))
print(len(rows))
dk = np.array([r[2]["k_dark"] for r in rows]); tp = np.array([r[2]["k_tps"] for r in rows])
lo = np.array([r[2]["local"] for r in rows]); hs = np.array([r[2]["hsoft"] for r in rows])
for a, b in ((0, 3.5), (3.5, 5), (5, 7), (7, 14)):
    m = (tp >= a) & (tp < b)
    print(f"clay line {a}-{b} mm: n {m.sum()}, dark>0.15 {np.sum(m & (dk > 0.15))}, dark>0.25 {np.sum(m & (dk > 0.25))}, max dark {dk[m].max():.2f}")
for a, b in ((0, 3.5), (3.5, 5), (5, 7), (7, 14)):
    m = (hs >= a) & (hs < b)
    print(f"geo crease {a}-{b} mm: n {m.sum()}, depth p90 {np.percentile(lo[m], 90):.2f} max {lo[m].max():.2f}")
# the crispest at Tess's height: clay line 4-6.5 mm, by dark
sel = [r for r in rows if 4.0 <= r[2]["k_tps"] < 6.5]
sel.sort(key=lambda r: -r[2]["k_dark"])
print("top at 4-6.5 mm:", " ".join(f"{k}:{i}({r['k_dark']:.2f}@{r['k_tps']:.1f}, geo {r['local']:.2f}@{r['hsoft']:.1f})" for k, i, r in sel[:14]))
sel = [r for r in rows if 4.0 <= r[2]["hsoft"] < 6.5]
sel.sort(key=lambda r: -r[2]["local"])
print("deepest geo at 4-6.5 mm:", " ".join(f"{k}:{i}({r['local']:.2f}, n {r['x_narrow']:.2f}, clay {r['k_dark']:.2f}@{r['k_tps']:.1f})" for k, i, r in sel[:14]))
