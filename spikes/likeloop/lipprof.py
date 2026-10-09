"""lipprof.py [label=shot:tag ...]: the mouth's vertical profiles like with like: from the subnasale (2) down the face
(+ey) 26 mm, at the midline and 8 mm to either side, luminance and redness (Lab a) every 0.5 mm, on the photo and on
each dressed render (mapped into photo pixels). Rows are placed from the PHOTO's points (same camera)."""
import os
import sys

import numpy as np
from PIL import Image

import sheet1
from hifipushie import likeness
from hifipushie.likeness_eyes import frame

L = os.environ["L"]


def lab(img):
    from skimage.color import rgb2lab
    return rgb2lab(np.asarray(img.convert("RGB"), float) / 255.0)


def prof(LAB, P, scale, origin, mmpx):
    from scipy.ndimage import map_coordinates
    ex, ey = frame(P)
    hs = np.arange(0, 26.01, 0.5)
    out = {}
    for name, dx in (("mid", 0.0), ("side", 8.0)):
        rows = []
        for sgn in ((1,) if dx == 0 else (-1, 1)):
            pts = P[2][None, :] + (sgn * dx / mmpx) * ex[None, :] + (hs / mmpx)[:, None] * ey[None, :]
            ij = (pts - origin) * scale
            rows.append([map_coordinates(LAB[..., c], [ij[:, 1], ij[:, 0]], order=1) for c in (0, 1)])
        out[name] = np.mean(rows, 0)
    return hs, out


refs = likeness._refs("ll_garrett")
ph = likeness.photo_sides(refs)[0]
P = ph["side"].P
seam = float((0.5 * (P[13] + P[14]) - P[2]) @ frame(P)[1]) * ph["mmpx"]
res = {"photo": prof(lab(ph["img"]), P, 1.0, np.zeros(2), ph["mmpx"])}
crop = sheet1.crop_of(refs["views"][0])
for arg in sys.argv[1:]:
    lb, tag = arg.split("=", 1)
    im = Image.open(f"{L}/out/{tag.split(':', 1)[1]}_front_big.png")
    s = im.size[0] / (crop[2] - crop[0])
    res[lb] = prof(lab(im), P, s, np.array(crop[:2]), ph["mmpx"])
print(f"photo's lip seam {seam:.1f} mm under the subnasale; columns every 1 mm from the subnasale")
for name in ("mid", "side"):
    for lb, (hs, o) in res.items():
        print(f"{name:4s} {lb:6s} L " + " ".join(f"{v:3.0f}" for v in o[name][0][::2]))
        print(f"{name:4s} {lb:6s} a " + " ".join(f"{v:3.0f}" for v in o[name][1][::2]))
