"""atlas_report.py <atlas npz> <out prefix>: what the sampled heads say.
- per attribute: its spread over GNM's population (sd, 5-95%), the share of heads where it's defined (the crease
  needs a fold of its own), R2 of a LINEAR model in the 120 components (held-out 20%: how well one direction in the
  identity space carries it; 1.0 for anything linear in the vertices), and how many components carry 80% of it;
- the attribute x attribute correlation matrix (what moves together in GNM's faces), as a heat map <prefix>_corr.png;
- the strongest couplings, printed.
"""
import sys

import numpy as np
from PIL import Image, ImageDraw

z = np.load(sys.argv[1], allow_pickle=True)
C, A, names = z["c"], z["A"], [str(x) for x in z["names"]]
pre = sys.argv[2]
n, m = A.shape
tr = np.arange(n) < int(0.8 * n)
print(f"{n} heads, {m} attributes\n")
print(f"{'attribute':20s} {'defined':>7s} {'sd':>8s} {'p5':>8s} {'p95':>8s} {'R2 lin':>7s} {'comps80':>7s}")
R2, B = {}, {}
for j, nm in enumerate(names):
    a = A[:, j]
    ok = np.isfinite(a)
    Xc = np.c_[np.ones(n), C]
    sel = ok & tr
    if sel.sum() < 50:
        print(f"{nm:20s} {ok.mean():7.2f}  (too few)")
        continue
    beta = np.linalg.lstsq(Xc[sel], a[sel], rcond=None)[0]
    te = ok & ~tr
    pred = Xc[te] @ beta
    r2 = 1 - np.mean((a[te] - pred) ** 2) / np.var(a[te])
    b = beta[1:]
    share = np.cumsum(np.sort(b ** 2)[::-1]) / max(float((b ** 2).sum()), 1e-30)
    k80 = int(np.searchsorted(share, 0.8) + 1)
    R2[nm], B[nm] = r2, b
    print(f"{nm:20s} {ok.mean():7.2f} {np.nanstd(a):8.3f} {np.nanpercentile(a, 5):8.3f} {np.nanpercentile(a, 95):8.3f} "
          f"{r2:7.3f} {k80:7d}")
# correlations (pairwise complete)
M = np.full((m, m), np.nan)
for i in range(m):
    for j in range(m):
        ok = np.isfinite(A[:, i]) & np.isfinite(A[:, j])
        if ok.sum() > 50 and np.std(A[ok, i]) > 0 and np.std(A[ok, j]) > 0:
            M[i, j] = np.corrcoef(A[ok, i], A[ok, j])[0, 1]
np.save(pre + "_corr.npy", M)
pairs = [(abs(M[i, j]), names[i], names[j], M[i, j]) for i in range(m) for j in range(i + 1, m) if np.isfinite(M[i, j])]
pairs.sort(reverse=True)
print("\nstrongest couplings (|r|):")
for _, a_, b_, r in pairs[:40]:
    print(f"  {a_:18s} ~ {b_:18s} {r:+.2f}")
# heat map
cell = 22
pad = 150
S = Image.new("RGB", (pad + cell * m, pad + cell * m), (255, 255, 255))
d = ImageDraw.Draw(S)
for i in range(m):
    for j in range(m):
        r = M[i, j]
        col = (200, 200, 200) if not np.isfinite(r) else (
            (255, int(255 * (1 - r)), int(255 * (1 - r))) if r > 0 else (int(255 * (1 + r)), int(255 * (1 + r)), 255))
        d.rectangle((pad + j * cell, pad + i * cell, pad + (j + 1) * cell - 1, pad + (i + 1) * cell - 1), fill=col)
    d.text((4, pad + i * cell + 5), names[i][:22], fill=(0, 0, 0))
    lab = Image.new("RGB", (pad, cell), (255, 255, 255))
    ImageDraw.Draw(lab).text((4, 5), names[i][:22], fill=(0, 0, 0))
    S.paste(lab.rotate(90, expand=True), (pad + i * cell, 0))
S.save(pre + "_corr.png")
print("\n", pre + "_corr.png")
