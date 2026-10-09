"""crease.py [label=shot:tag ...]: the upper lid's luminance profile, like with like: from the upper lid margin (159 /
386) straight up the face (-ey) to the brow, at three places along the lid (inner third, middle, outer third), on the
photo and on each dressed render ($L/out/<tag>_front_big.png, mapped into photo pixels): luminance every 0.5 mm, and
the crease (the darkest point 2-12 mm above the margin) and the platform (the brightest point under it): height mm,
depth (platform L / crease L). Prints one block per picture."""
import os
import sys

import numpy as np
from PIL import Image

import sheet1
from hifipushie import likeness
from hifipushie.likeness_eyes import frame

L = os.environ["L"]


def lum(img):
    a = np.asarray(img.convert("RGB"), float) / 255.0
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def profiles(Y, P, scale, origin, mmpx):
    """Y: luminance of an image whose pixel = origin + p / scale (photo px); P: detector points in photo px."""
    from scipy.ndimage import map_coordinates
    ex, ey = frame(P)
    out = {}
    for side, (up, inner, outer) in (("R", (159, 133, 33)), ("L", (386, 362, 263))):
        for name, t in (("inner", 0.28), ("mid", 0.5), ("outer", 0.75)):
            # the point on the lid margin: between the corners, raised onto the margin's height at the middle
            base = P[inner] + t * (P[outer] - P[inner])
            base = base + ((P[up] - base) @ ey) * ey * (1 - abs(t - 0.5) * 1.2)
            hs = np.arange(0, 14.01, 0.5)
            pts = base[None, :] - (hs / mmpx)[:, None] * ey[None, :]
            ij = (pts - origin) * scale
            v = map_coordinates(Y, [ij[:, 1], ij[:, 0]], order=1)
            win = (hs >= 2) & (hs <= 12)
            ic = np.where(win)[0][np.argmin(v[win])]
            ip = np.argmax(v[:ic + 1]) if ic > 0 else 0
            out[f"{side}_{name}"] = {"crease_mm": float(hs[ic]), "platform_mm": float(hs[ip]),
                                     "depth": round(float(v[ip] / max(v[ic], 1e-6)), 3),
                                     "profile": [round(float(x), 2) for x in v]}
    return out


refs = likeness._refs("ll_garrett")
ph = likeness.photo_sides(refs)[0]
P = ph["side"].P
rows = {"photo": profiles(lum(ph["img"]), P, 1.0, np.zeros(2), ph["mmpx"])}
crop = sheet1.crop_of(refs["views"][0])
for arg in sys.argv[1:]:
    lab, tag = arg.split("=", 1)
    im = Image.open(f"{L}/out/{tag.split(':', 1)[1]}_front_big.png")
    s = im.size[0] / (crop[2] - crop[0])
    Pm = likeness.detect([im])[0] / s + np.array(crop[:2])
    rows[lab] = profiles(lum(im), Pm, s, np.array(crop[:2]), ph["mmpx"])
for lab, r in rows.items():
    print(lab)
    for k, v in r.items():
        print(f"  {k:9s} crease {v['crease_mm']:4.1f} mm  platform {v['platform_mm']:4.1f}  depth {v['depth']:.2f}  "
              + " ".join(f"{x:.2f}" for x in v["profile"][:25]))
