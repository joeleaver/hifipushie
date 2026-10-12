"""napedots.py <model>: where does the scalp layer put hair below the nape hairline? Prints the scalp mesh's density by
elevation at the back, and the under guides' seeds / ends there (the dots on the neck, th_T04 .. T06)."""
import sys
import numpy as np
from hifipushie import hair, hair_strands as hs, hair_cards as hc, store

m = sys.argv[1]
spec = store.load(m)
sc = hair.scalp(m, spec)
g = hair.groom_params(spec)
S = hc.strands_of(spec)
line = hair.hairline(sc, g)
print("EL0", sc.EL[0], "line at back (az 150..210):", np.round(line[150:211:10], 1), "line min", line.min())
sm = hs.scalp_mesh(sc, g, line, S)
V, d = sm["verts"], sm["hp_density"]
az, el, h = sc.coords(V)
back = (np.abs(((az + 180) % 360) - 180) > 150)
for lo in range(int(np.floor(el[back].min())), int(line[180]) + 8, 3):
    k = back & (el >= lo) & (el < lo + 3)
    if k.any():
        print(f"el {lo:4d}..{lo + 3:4d}: verts {k.sum():3d} density mean {d[k].mean():.2f} max {d[k].max():.2f}  h {h[k].mean() * 1000:.1f} mm  r {np.linalg.norm(V[k] - sc.C, axis=1).mean():.3f}")
locks = hair.resolve(spec, sc)
ug = hs.under_guides(sc, g, line, locks, S, int(g.get("seed", 0)))
P = ug["pts"].reshape(len(ug["counts"]), -1, 3)
a0, e0, _ = sc.coords(P[:, 0])
a1, e1, h1 = sc.coords(P[:, -1])
bk = np.abs(((a0 + 180) % 360) - 180) > 150
print("under guides", len(P), "at the back", bk.sum(), "root el min", e0[bk].min().round(1), "tip el min", e1[bk].min().round(1),
      "tips below the line - 3 deg:", int((e1[bk] < np.interp(a1[bk] % 360, np.arange(360.0), line) - 3).sum()))
ln = np.linalg.norm(np.diff(P, axis=1), axis=2).sum(1)
print("guide length mm p10/50/90", np.percentile(ln[bk] * 1000, [10, 50, 90]).round(1))
