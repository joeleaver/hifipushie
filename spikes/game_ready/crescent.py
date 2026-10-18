"""crescent.py <id.png> ...: the fast path's front ID pass (mouthhits, 0.25 mm/px). Opening = anything not face-on skin
(rows above 0.65 of the image). At 9 stations between the opening's ends, + = below the line joining its end points (mm):
the opening's top, the teeth's top (white / lower teeth), the teeth bottom; the top's bow (middle - mean of 0.3 / 0.7;
- = middle higher: an arch); and the band of inner lip (interior pink / edge-on) between the opening's top and the teeth
at the middle (mm). Reference smile (photo, % io -> mm at io 63): teeth top bow ~ -0.4 mm, band 0; x43: bow +0.6, band 2.5."""
import sys, numpy as np
from PIL import Image
for f in sys.argv[1:]:
    a = np.asarray(Image.open(f).convert("RGB")).astype(int); h = int(a.shape[0] * 0.65); a = a[:h]
    skin = (a == [220, 190, 170]).all(-1)
    teeth = (a == [255, 255, 255]).all(-1) | (a == [200, 200, 120]).all(-1)
    op = ~skin
    cols = np.flatnonzero(op.sum(0) > 0); x0, x1 = cols.min(), cols.max()
    def first(m, x): r = np.flatnonzero(m[:, x]); return (r.min(), r.max()) if len(r) else (np.nan, np.nan)
    ya, yb = np.mean(first(op, x0)), np.mean(first(op, x1))
    us = np.linspace(0.1, 0.9, 9); xs = np.round(x0 + us * (x1 - x0)).astype(int); line = ya + us * (yb - ya)
    O = np.array([first(op, x)[0] for x in xs]) - line
    T = np.array([first(teeth, x)[0] for x in xs]) - line; B = np.array([first(teeth, x)[1] for x in xs]) - line
    q = lambda v: " ".join(f"{x * 0.25:+.1f}" for x in v)
    bow = lambda v: 0.25 * (v[4] - (v[2] + v[6]) / 2)
    print(f"{f.split('/')[-1]}: width {0.25 * (x1 - x0):.1f} mm | opening top [{q(O)}] bow {bow(O):+.2f} | teeth top [{q(T)}] bow {bow(T):+.2f}"
          f" | teeth bottom [{q(B)}] | teeth at mid {0.25 * (B[4] - T[4]):.1f} | band above teeth at mid {0.25 * (T[4] - O[4]):.1f} mm")
