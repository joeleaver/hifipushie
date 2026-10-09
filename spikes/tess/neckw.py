"""neckw.py <sheet png>: neck width like with like on a facesheet front row (ref = column 0, ours = column 1): the
figure's run against the background through the face's centre line, at 15 / 30 / 45 mm under the chin (detector point
152), mm by the pupils' distance (54.8 mm, hers). Also the jaw width at the gonial level (detector 172 / 397)."""
import sys

import numpy as np
from PIL import Image

import rs

sheet = Image.open(sys.argv[1]).convert("RGB")
IPD = 54.8


def read(im):
    a = np.asarray(im).astype(float)
    P = rs.detect([a.astype(np.uint8)])[0]["P"][:, :2]
    mmpx = IPD / np.linalg.norm(P[468] - P[473])
    bg = np.median(a[5:40, 5:40].reshape(-1, 3), 0)
    fg = np.abs(a - bg).sum(-1) > 30
    cx = int(round(0.5 * (P[468, 0] + P[473, 0])))
    out = {"jaw_172_397": float(np.linalg.norm(P[172] - P[397]) * mmpx)}
    for d in (15, 30, 45):
        y = int(round(P[152, 1] + d / mmpx))
        if y >= a.shape[0]:
            continue
        row = fg[y]
        l = cx
        while l > 0 and row[l - 1]:
            l -= 1
        r = cx
        while r < len(row) - 1 and row[r + 1]:
            r += 1
        out[f"neck_{d}mm"] = 2 * (cx - l) * mmpx  # (her right side only: the tail and wisps hang on her left)
    return out


ref = read(sheet.crop((0, 28, 640, 668)))
ours = read(sheet.crop((640, 28, 1280, 668)))
for k in ref:
    print(f"  {k:12s} ref {ref[k]:6.1f} | ours {ours.get(k, float('nan')):6.1f} ({ours.get(k, float('nan')) - ref[k]:+.1f}) mm")
