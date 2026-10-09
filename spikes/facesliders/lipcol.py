"""lipcol.py [label=<render png> ...]: the lips' colour like with like, each picture sampled on ITS OWN vermilion (the
detector run on that picture: MediaPipe 0 -> 13 is the upper vermilion's middle, 14 -> 17 the lower's), 3 columns
(the middle and +-6 mm), the inner 70% of each span: Lab mean of the upper / lower vermilion and of the skin 3-6 mm
above the upper border, their heights (mm), and the lips' contrast (a lip - a skin). The photo is ll_garrett's."""
import sys

import numpy as np
from PIL import Image

from hifipushie import likeness
from hifipushie.likeness_eyes import frame


def lab(img):
    from skimage.color import rgb2lab
    return rgb2lab(np.asarray(img.convert("RGB"), float) / 255.0)


def read(img, mmpx, P=None):
    from scipy.ndimage import map_coordinates
    if P is None:
        d = likeness.detect([img.convert("RGB")])[0]
        if d is None:
            raise SystemExit("no face found in the render")
        P = np.asarray(d["P"] if isinstance(d, dict) else d, float)[:, :2]
    P = np.asarray(P, float)[:, :2]
    ex, ey = frame(P)
    LAB = lab(img)
    out = {}

    def samp(a, b, lo=0.15, hi=0.85):
        vals = []
        for dx in (-6.0, 0.0, 6.0):
            t = np.linspace(lo, hi, 15)
            pts = (a + t[:, None] * (b - a)) + (dx / mmpx) * ex
            vals.append([map_coordinates(LAB[..., c], [pts[:, 1], pts[:, 0]], order=1) for c in range(3)])
        return np.mean(vals, axis=(0, 2))
    out["upper"] = samp(P[0], P[13])
    out["lower"] = samp(P[14], P[17])
    out["skin"] = samp(P[0] - 6 / mmpx * ey, P[0] - 3 / mmpx * ey, 0, 1)
    out["h_up"] = float((P[13] - P[0]) @ ey) * mmpx
    out["h_lo"] = float((P[17] - P[14]) @ ey) * mmpx
    return out


refs = likeness._refs("ll_garrett")
ph = likeness.photo_sides(refs)[0]
rows = {"photo": read(ph["img"], ph["mmpx"], ph["side"].P)}
for arg in sys.argv[1:]:
    lb, path = arg.split("=", 1)
    im = Image.open(path)
    # (a render of the photo's crop: its pixel size against the photo's)
    import sheet1
    crop = sheet1.crop_of(refs["views"][0])
    s = im.size[0] / (crop[2] - crop[0])
    rows[lb] = read(im, ph["mmpx"] / s)
for lb, r in rows.items():
    print(f"{lb:8s} upper L/a/b {r['upper'].round(0).tolist()}  lower {r['lower'].round(0).tolist()}  skin "
          f"{r['skin'].round(0).tolist()}  | heights up {r['h_up']:.1f} lo {r['h_lo']:.1f} mm | contrast a: upper "
          f"{r['upper'][1] - r['skin'][1]:+.1f} lower {r['lower'][1] - r['skin'][1]:+.1f}")
