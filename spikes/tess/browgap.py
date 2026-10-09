"""browgap.py <sheet png> [row]: the brow-to-eye GAP as it READS, like with like on a facesheet row (reference = column
0, ours = column 1, 640 px each): the detector's upper-lid margin points (inner / middle / outer third of each eye), then
straight up to the first row where the picture turns brow-dark (luminance under 0.78 of the skin just above the lid)
= the brow's lower edge; its upper edge = where it turns light again; mm by the pupils' distance (54.8 mm, hers).
The detector's own brow points follow the brow's FORM (the ridge), not its hair: that is why "brow height" agreed
within 0.3 mm while the painted brows sat high."""
import sys

import numpy as np
from PIL import Image

import rs

sheet = Image.open(sys.argv[1]).convert("RGB")
row = int(sys.argv[2]) if len(sys.argv) > 2 else 0
IPD = 54.8
# MediaPipe: upper lid margin (inner, middle, outer) per eye; iris centres 468 / 473
LIDS = {"R": (157, 159, 161), "L": (384, 386, 388)}


def read(im):
    a = np.asarray(im).astype(float)
    d = rs.detect([a.astype(np.uint8)])[0]
    P = d["P"][:, :2]
    if P.max() <= 2.0:  # normalised
        P = P * [im.width, im.height]
    mmpx = IPD / np.linalg.norm(P[468] - P[473])
    L = a @ [0.299, 0.587, 0.114]
    out = {}
    for side, ids in LIDS.items():
        for name, i in zip(("inner", "mid", "outer"), ids):
            x, y = int(round(P[i, 0])), int(round(P[i, 1]))
            col = np.convolve(L[:, max(x - 2, 0):x + 3].mean(1), np.ones(3) / 3, mode="same")
            # the brow = the darkest band 5..30 mm over the lid; its edges where it is half-way back to the skin
            a0, a1 = max(int(y - 30 / mmpx), 0), int(y - 5 / mmpx)
            seg = col[a0:a1]
            ym = a0 + int(np.argmin(seg))
            skin = np.percentile(seg, 90)
            half = 0.5 * (col[ym] + skin)
            lo = next((yy for yy in range(ym, a1) if col[yy] > half), None)
            hi = next((yy for yy in range(ym, a0, -1) if col[yy] > half), None)
            out[f"{side}_{name}"] = (None if lo is None else (y - lo) * mmpx, None if (lo is None or hi is None) else (lo - hi) * mmpx, round(float(col[ym] / skin), 2))
    return out


y0 = 28 + 640 * row
ref = read(sheet.crop((0, y0, 640, y0 + 640)))
ours = read(sheet.crop((640, y0, 1280, y0 + 640)))
print("lid -> brow lower edge (gap) | brow thickness, mm: ref | ours (diff)")
for k in ref:
    g0, t0, c0 = ref[k]
    g1, t1, c1 = ours[k]
    f = lambda v: "  -  " if v is None else f"{v:5.1f}"  # noqa: E731
    dg = "" if g0 is None or g1 is None else f"({g1 - g0:+.1f})"
    dt = "" if t0 is None or t1 is None else f"({t1 - t0:+.1f})"
    print(f"  {k:9s} gap {f(g0)} | {f(g1)} {dg:8s}  thick {f(t0)} | {f(t1)} {dt:8s}  darkness {c0} | {c1}")
