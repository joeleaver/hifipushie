import copy, sys
import numpy as np
from hifipushie import faceslide, onemesh, store
b0 = copy.deepcopy(store.load(sys.argv[1])["base"])
V = np.asarray(onemesh.head_template(b0)["carry"]["V"], float)
T = faceslide.head_template(V)
orig = faceslide._fold_turn
def spy(X, u, h, sel, H0, NY=None):
    mm = 0.001
    for u0 in np.linspace(0.05, 0.9, 6):
        s = sel & (u >= u0) & (u < u0 + 0.095) & (h > 1.0 * mm) & (h < 11 * mm)
        o = np.argsort(h[s])
        print(f"u {u0:.2f}: n {int(s.sum())}", [(round(1000 * a, 1), round(b, 2)) for a, b in zip(h[s][o], NY[s][o])][:14])
    return orig(X, u, h, sel, H0, NY)
faceslide._fold_turn = spy
faceslide._left_fields(T)
