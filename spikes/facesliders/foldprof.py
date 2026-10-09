"""foldprof.py <model>: the left upper lid's profile (depth z against height over the margin, GNM frame, mm) in the
middle u band, and the concavity used by faceslide._fold_turn."""
import copy
import sys

import numpy as np

from hifipushie import faceslide, onemesh, store

b0 = copy.deepcopy(store.load(sys.argv[1])["base"])
V = np.asarray(onemesh.head_template(b0)["carry"]["V"], float)
T = faceslide.head_template(V)
faceslide._left_fields(T)
Hc, H0, u, up_ = faceslide._CACHE["last_crease"]
X = T["X"]
lm = T["lm"]
# h as _left_fields computes it
c_in, c_out = lm[42], lm[45]
w = float(np.linalg.norm(c_out - c_in))
ex = (c_out - c_in) / w
uk = lambda p: float((p - c_in) @ ex / w)  # noqa: E731
ym = faceslide._quad(np.array([0.0, uk(lm[43]), uk(lm[44]), 1.0]), np.array([c_in[1], lm[43][1], lm[44][1], c_out[1]]))
h = X[:, 1] - ym(np.clip(u, 0, 1))
for a, b_ in ((0.35, 0.5), (0.5, 0.65)):
    s = up_ & (u >= a) & (u < b_)
    print(f"u {a}-{b_}:")
    for hh in np.arange(0.5, 12.1, 0.5):
        q = s & (np.abs(h - hh / 1000) < 0.3 / 1000)
        if q.any():
            print(f"  h {hh:4.1f} mm: z {1000 * np.median(X[q, 2]):7.2f}  n.y {np.median(T['n'][q, 1]):5.2f}  ({int(q.sum())})")
