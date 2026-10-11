"""top.py <key> [n] [files...]: top samples by a key."""
import sys, glob, json
import numpy as np
key = sys.argv[1]; n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
files = sys.argv[3:] or sorted(glob.glob("/mnt/data/hifipushie/gnmcrease/out/s_*.npz"))
rows = []
for f in files:
    z = np.load(f, allow_pickle=True)
    G, K = json.loads(str(z["geo"])), json.loads(str(z["clay"]))
    for i in range(len(G)):
        rows.append((f.split("/")[-1], i, {**G[i], **{"k_" + k: v for k, v in K[i].items()}}))
rows.sort(key=lambda r: -np.nan_to_num(r[2].get(key, -9), nan=-9))
for f, i, r in rows[:n]:
    print(f"{f}:{i:4d} dark {r.get('k_dark', np.nan):.2f}@{r.get('k_tps', np.nan):4.1f} w {r.get('k_width', np.nan):.1f} | depth {r['local']:.2f} "
          f"narrow {r['x_narrow']:.2f} hid {r['x_hidden']:.2f} hid10 {r['x_hidden10']:.2f} drop {r['drop']:.2f} krad {r['x_krad']:.2f} "
          f"lip {r['x_lip']:.2f} @{r['hsoft']:.1f} show {r['show']:.1f} up {r['up']:.2f}")
