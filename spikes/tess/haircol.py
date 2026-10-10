"""haircol.py <trace json> [our render png + our id mask npy]: her hair's colour inside the traced mask: luminance
percentiles 10 / 50 / 90 (shadow, mid, highlight) and the mean sRGB of each band, as hex. With our render + mask, the
same for ours."""
import json, sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi


def stats(img, m):
    a = np.asarray(img.convert("RGB"), float)
    m = ndi.binary_erosion(m, iterations=3)  # off the edge (background mixed in)
    L = a @ [0.299, 0.587, 0.114]
    v = L[m]
    out = {}
    for k, (lo, hi) in {"shadow": (0, 20), "mid": (40, 60), "highlight": (85, 98)}.items():
        a0, a1 = np.percentile(v, [lo, hi])
        sel = m & (L >= a0) & (L <= a1)
        c = a[sel].mean(0)
        out[k] = "#%02x%02x%02x" % tuple(int(x) for x in c)
        out[k + "_rgb"] = [round(float(x)) for x in c]
    return out


tr = json.load(open(sys.argv[1]))
m = np.asarray(Image.open(sys.argv[1].replace(".json", "_mask.png")).convert("L")) > 127
print("hers", json.dumps(stats(Image.open(tr["photo"]), m)))
if len(sys.argv) > 3:
    print("ours", json.dumps(stats(Image.open(sys.argv[2]), np.load(sys.argv[3]))))
