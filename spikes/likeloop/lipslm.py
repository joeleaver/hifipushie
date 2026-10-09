"""lipslm.py [model]: the lip landmarks' heights (z, mm above the mouth corners' mean) and depths: is the upper lip's
outline (corners, peaks 50/52, top 51, inner 61-63) a proper ring seen from the front?"""
import sys

import numpy as np

from hifipushie import humanfit, store

name = sys.argv[1] if len(sys.argv) > 1 else "ll_garrett"
st = humanfit.state(store.load(name)["base"])
L = np.asarray(st["L"])
z0 = 0.5 * (L[48][2] + L[54][2])
for i in (48, 49, 50, 51, 52, 53, 54, 60, 61, 62, 63, 64, 65, 66, 67, 57):
    print(i, "x %.1f" % (L[i][0] * 1000), "z %+.2f mm" % ((L[i][2] - z0) * 1000), "y %.1f" % (L[i][1] * 1000))
