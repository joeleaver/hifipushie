"""popstat.py [n=2000] [label=<identity source> ...]: the lid's structure numbers (lidstruct.mean_structure, raw mesh)
over n identities from GNM's prior (170 comps ~ N(0, 1)): percentiles, the tuck against the fold's height (is there a
crisp turn on a TALL platform anywhere?), any overhang (hang), and where the named heads sit (percentile of each)."""
import os
import sys

import numpy as np

import lidstruct as ls

args = sys.argv[1:]
n = int(args[0]) if args and args[0].isdigit() else 2000
named = [a.split("=", 1) for a in args if "=" in a]
rng = np.random.default_rng(7)
K = ("crease_h", "platform_s", "roll", "tuck", "wall", "drape", "hang")
C = rng.standard_normal((n, 170))
S, ok = [], []
for c in C:
    try:
        S.append([ls.mean_structure(c)[k] for k in K])
        ok.append(True)
    except (IndexError, KeyError, ValueError):
        ok.append(False)
S, C = np.array(S), C[np.array(ok)]
print("read", len(S), "of", n)
n = len(S)
np.savez(os.environ["G"] + "/out/popstat.npz", C=C, S=S, K=K)
print(f"{n} identities ~ N(0, I):")
print("  " + "".join(f"{k:>11s}" for k in ("",) + K))
for p in (1, 10, 50, 90, 99, 100):
    print(f"  p{p:<9d}" + "".join(f"{np.percentile(S[:, j], p):11.2f}" for j in range(len(K))))
h, tk = S[:, 0], S[:, 3]
print("  tuck by the fold's height over the margin (raw mm):")
for a, b in ((0, 2), (2, 3), (3, 4), (4, 5), (5, 7), (7, 99)):
    m = (h >= a) & (h < b)
    if m.sum():
        print(f"    {a}-{b} mm: n {m.sum():4d}, tuck median {np.median(tk[m]):5.1f}, p90 {np.percentile(tk[m], 90):5.1f}, max {tk[m].max():5.1f}; platform stand-off median {np.median(S[m, 1]):.2f}")
print(f"  platform lying on the ball (stand-off < 1.2 mm): {(S[:, 1] < 1.2).mean() * 100:.1f} %; with a turn >= 30 deg: {((S[:, 1] < 1.2) & (tk >= 30)).mean() * 100:.1f} %; "
      f"and the fold >= 4.5 mm up: {((S[:, 1] < 1.2) & (tk >= 30) & (h >= 4.5)).mean() * 100:.2f} %")
print(f"  any overhang (hang > 0.1 mm): {(S[:, 6] > 0.1).mean() * 100:.2f} % (max {S[:, 6].max():.2f} mm)")
print(f"  corr(tuck, fold height) {np.corrcoef(tk, h)[0, 1]:+.2f}; corr(tuck, platform stand-off) {np.corrcoef(tk, S[:, 1])[0, 1]:+.2f}")
for lab, src in named:
    q = ls.mean_structure(ls.ident(src))
    print(f"  {lab:10s} " + " ".join(f"{k} {q[k]:.2f} (p{(S[:, j] < q[k]).mean() * 100:.0f})" for j, k in enumerate(K)))
