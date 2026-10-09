"""eyezoom.py <out.jpg> <label=shot:tag>...: each eye of the photo and of the renders, one box per eye (the photo's
detector points: corners, lid, brow), side by side at the same scale, with mm ticks up the left edge (every 2 mm
from the lid margin): to place the crease and the platform by eye."""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

import sheet1
from hifipushie import likeness

L = os.environ["L"]
refs = likeness._refs("ll_garrett")
ph = likeness.photo_sides(refs)[0]
P, mmpx = ph["side"].P, ph["mmpx"]
crop = sheet1.crop_of(refs["views"][0])
W = 420
srcs = [("photo", ph["img"], (0.0, 0.0), 1.0)]
for a in sys.argv[2:]:
    lab, tag = a.split("=", 1)
    im = Image.open(f"{L}/out/{tag.split(':', 1)[1]}_front_big.png").convert("RGB")
    srcs.append((lab, im, tuple(crop[:2]), im.size[0] / (crop[2] - crop[0])))
rows = []
for up, a, b, brow in ((159, 133, 33, 105), (386, 362, 263, 334)):
    xs = [P[a][0], P[b][0]]
    x0, x1 = min(xs) - 4 / mmpx, max(xs) + 4 / mmpx
    y0, y1 = P[brow][1] - 3 / mmpx, P[145 if up == 159 else 374][1] + 5 / mmpx
    h = int(W * (y1 - y0) / (x1 - x0))
    row = []
    for lab, im, o, s in srcs:
        t = im.transform((W, h), Image.EXTENT, ((x0 - o[0]) * s, (y0 - o[1]) * s, (x1 - o[0]) * s, (y1 - o[1]) * s), Image.BICUBIC)
        d = ImageDraw.Draw(t)
        k = W / (x1 - x0)
        for mm in range(0, 15, 2):
            yy = (P[up][1] - mm / mmpx - y0) * k
            d.line([(0, yy), (10 if mm % 4 else 18, yy)], fill=(255, 255, 0), width=1)
        d.text((4, 2), lab, fill=(255, 255, 0))
        row.append(t)
    rows.append(row)
H = sum(r[0].size[1] for r in rows)
S = Image.new("RGB", (W * len(srcs), H))
y = 0
for r in rows:
    for i, t in enumerate(r):
        S.paste(t, (i * W, y))
    y += r[0].size[1]
S.save(sys.argv[1], quality=88)
