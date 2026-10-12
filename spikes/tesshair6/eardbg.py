"""eardbg.py <model> [open=19]: the residual hair.ear() thresholds (mm, opened along the azimuth), az 60..150."""
import sys

import numpy as np
from scipy import ndimage

from hifipushie import hair, store

m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
sc = hair.scalp(m, store.load(m))
R = sc.R
na = len(sc.A)
Rs = 0.5 * (R + R[(-np.arange(na)) % na])
op = int(kw.get("open", hair.EAR_OPEN))
pad = op + 4
D = Rs - ndimage.grey_opening(np.concatenate([Rs[-pad:], Rs, Rs[:pad]], 0), size=(op, 1))[pad:-pad]
ia = np.nonzero((sc.A >= 60) & (sc.A <= 150))[0]
ie = np.nonzero((sc.E >= -60) & (sc.E <= 40))[0][::-1]
print("C", sc.C, "lm", len(sc.lm), "ear", {k: v for k, v in (hair.ear(sc) or {}).items() if k != "cells"})
print("     el " + " ".join(f"{e:3.0f}" for e in sc.E[ie]))
for i in ia:
    print(f"az {sc.A[i]:4.0f} " + " ".join(f"{D[i, j] * 1000:3.0f}" for j in ie))
