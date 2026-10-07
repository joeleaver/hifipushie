"""cards.gd's pictures measured: per GLB (drawn where the plant fills its share of the view) the plant's covered area in
m2 (pixels not background x the pixel's size squared: does alpha-tested foliage thin out or vanish with distance?) and
the share of its pixels that flip between two frames half a pixel apart (shimmer; an opaque mesh's edge alone gives
roughly its outline's share), + a contact sheet.

  python spikes/godot_veg/measure_cards.py <prefix> <sheet.png> <height m> <mode> <stem>:<share> ...   (the first is the reference)
"""
import math
import sys

import numpy as np
from PIL import Image

prefix, sheet, H, mode = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
items = [a.rsplit(":", 1) for a in sys.argv[5:]]


def fg(im):
    a = np.asarray(im.convert("RGB"), float) / 255
    return ~((a[..., 0] > 0.75) & (a[..., 1] < 0.35) & (a[..., 2] > 0.75)), a


ref = None
cells = []
for stem, share in items:
    share = float(share)
    ims = [Image.open(f"{prefix}_{stem}_{mode}_{f}.png") for f in (0, 1)]
    (m0, a0), (m1, a1) = fg(ims[0]), fg(ims[1])
    px = ims[0].height
    d = H / (share * 2 * math.tan(math.radians(20)))
    pixel = 2 * d * math.tan(math.radians(20)) / px
    area = float(m0.sum()) * pixel * pixel
    flips = float((m0 ^ m1).sum()) / max(float(m0.sum()), 1)
    edge = float((m0 ^ np.roll(m0, 1, 1)).sum() + (m0 ^ np.roll(m0, 1, 0)).sum()) / max(float(m0.sum()), 1)
    mx, mn = a0.max(-1), a0.min(-1)
    fol = m0 & ((mx - mn) / np.maximum(mx, 1e-6) > 0.22)
    lum = float(a0[fol].mean()) if fol.any() else 0.0
    ref = ref or area
    print(f"{stem} [{mode}] at {d:.0f} m (fills {share:.2f} of the view, {pixel * 100:.1f} cm a pixel): covered {area:.1f} m2 = {area / ref:.2f} of the first; "
          f"pixels flipping for a half-pixel move {flips:.3f} of its area (its outline is {edge:.3f}: ratio {flips / max(edge, 1e-6):.2f}); foliage luma {lum:.3f}")
    # the plant cropped and blown up to the same size, to see it
    ys, xs = np.nonzero(m0)
    if len(xs):
        c = ims[0].crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
        s = 300 / max(c.size)
        cells.append(c.resize((max(int(c.width * s), 1), max(int(c.height * s), 1)), Image.NEAREST))
S = Image.new("RGB", (310 * len(cells), 310), (255, 0, 255))
for i, c in enumerate(cells):
    S.paste(c, (310 * i, 0))
S.save(sheet)
print(sheet)
