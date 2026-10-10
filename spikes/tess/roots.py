"""roots.py <model> <out png>: the front of the scalp unrolled (az -100..100 across, el -40..90 up): the hairline (red),
every head lock's spine (grey, its root a dot; tie gather row 0 in orange), and the under-layer's density mask
(hp_density, shaded). Shows whether roots populate the band between the hairline and the part."""
import sys

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import hair, hair_strands as hs, store

name, out = sys.argv[1], sys.argv[2]
sp = store.load(name)
sc = hair.scalp(name, sp)
g = hair.groom_of(sp) if hasattr(hair, "groom_of") else hair._merge(hair.GROOM, sp["hair"]["groom"])
line = hair.hairline(sc, g)
W, H = 1000, 650
img = Image.new("RGB", (W, H), (245, 245, 245))
dr = ImageDraw.Draw(img)


def xy(az, el):
    a = ((np.asarray(az, float) + 180) % 360) - 180
    return (a + 100) / 200 * W, (90 - np.asarray(el, float)) / 130 * H


S = {**hs.hc.STRAND_DEFAULTS, **(sp["hair"].get("strands") or {})} if hasattr(hs.hc, "STRAND_DEFAULTS") else None
for az in range(-100, 101, 2):
    for el in range(-40, 90, 2):
        d = float(hair.inside(sc, line, az % 360, el))
        v = int(245 - 120 * np.clip((d + 0.0015) / 0.012, 0, 1))
        x, y = xy(az, el)
        dr.rectangle([x - 5, y - 5, x + 5, y + 5], fill=(v, v, 245))
A = np.arange(-100, 101)
x, y = xy(A, line[A % 360])
dr.line(list(zip(x, y)), fill=(220, 0, 0), width=3)
for k, lk in (sp["hair"].get("locks") or {}).items():
    if lk.get("space") == "xyz":
        continue
    P = np.asarray(lk["pts"], float)
    x, y = xy(P[:, 0], P[:, 1])
    col = (255, 140, 0) if k.startswith("tg0_") else (120, 120, 120)
    dr.line(list(zip(x, y)), fill=col, width=2)
    dr.ellipse([x[0] - 4, y[0] - 4, x[0] + 4, y[0] + 4], fill=col)
for el in range(-40, 91, 10):
    _, yy = xy(0, el)
    dr.text((2, yy), f"el {el}", fill=(0, 0, 0))
for az in range(-90, 91, 30):
    xx, _ = xy(az, 0)
    dr.text((xx, H - 14), f"az {az}", fill=(0, 0, 0))
img.save(out)
print("saved", out)
