"""guidefield.py <model> [side=back] [len=0.01]: the loose guides' COMB at the roots seen from behind (or `side=top`):
each guide's root and where it is 1 cm along, drawn as short arrows on a plot of the head's back, coloured by the
downward share. Where arrows point away from each other the field diverges (a rosette / bald spot seen from behind).
Also prints the guides whose first step goes UP on the back (a back comb should fall). $TOUT/guidefield_<model>.png"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import hair, store

m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
OUT = os.environ["TOUT"]
L = float(kw.get("len", 0.01))
spec = store.load(m)
sc = hair.scalp(m, spec)
C = np.asarray(sc.C, float)
locks = spec["hair"]["locks"]
R, D = [], []
for lk in locks.values():
    P = np.asarray(lk["pts"], float)
    if len(P) < 2:
        continue
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    q = np.array([np.interp(min(L, s[-1]), s, P[:, c]) for c in range(3)])
    R.append(P[0])
    D.append(q - P[0])
R, D = np.asarray(R), np.asarray(D)
back = R[:, 1] > 0.02  # behind the head centre (the head faces -y)
up = back & (D[:, 2] > 0.002)
print(f"{m}: {len(R)} guides, {int(back.sum())} rooted behind the centre, {int(up.sum())} of them start UPWARD (> 2 mm in 1 cm)")
if up.any():
    print("  upward starters (x, z rel. centre, mm), median:", np.round(np.median(R[up][:, [0, 2]], 0) * 1000, 1),
          "spread:", np.round(np.std(R[up][:, [0, 2]], 0) * 1000, 1))
S, pad = 900, 0.11
img = Image.new("RGB", (S, S), (235, 235, 235))
d = ImageDraw.Draw(img)


def px(x, z):
    return (S / 2 + x / pad * S / 2, S / 2 - z / pad * S / 2)


for r, v in zip(R[back], D[back]):
    a = px(r[0], r[2])
    b = px(r[0] + 3 * v[0], r[2] + 3 * v[2])
    dn = float(np.clip(-v[2] / max(np.linalg.norm(v), 1e-9), -1, 1))
    col = (int(255 * (1 - dn) / 2), 60, int(255 * (1 + dn) / 2))  # blue = down, red = up
    d.line([a, b], fill=col, width=2)
    d.ellipse([a[0] - 1.5, a[1] - 1.5, a[0] + 1.5, a[1] + 1.5], fill=(0, 0, 0))
img.save(f"{OUT}/guidefield_{m}.png")
print(f"{OUT}/guidefield_{m}.png")
