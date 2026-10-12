"""bgdbg.py <model>: the backdrop pixels' colour per view (why the backdrop anchor did or did not take)."""
import os, pickle, sys
import numpy as np
from scipy import ndimage
from hifipushie import skin_read as sr

m = sys.argv[1]
frames = pickle.load(open(f"{os.environ['G']}/out/frames_{m}.pkl", "rb"))
for f in frames:
    fig = f["parse"]["figure"]
    for thr, it in ((0.08, 4), (0.3, 4), (0.5, 2)):
        bg = ndimage.binary_erosion((fig < thr) & (f["alpha"] < 0.02), iterations=it)
        if bg.sum() == 0:
            print(f["view"], thr, "no px"); continue
        L = sr.lab(f["P"][bg])
        med = np.median(L, 0)
        print(f["view"], "thr", thr, "px", bg.sum(), "Lab median", med.round(1), "L p80 dev", np.percentile(np.abs(L[:, 0] - med[0]), 80).round(1),
              "rgb", np.median(f["P"][bg], 0).round(3))
    sk = sr.trust(f) > 0.5
    print("   skin picture Lab", np.median(sr.lab(f["P"][sk]), 0).round(1), "render", np.median(sr.lab(f["R"][sk]), 0).round(1))
