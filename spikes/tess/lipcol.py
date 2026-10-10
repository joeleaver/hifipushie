"""lipcol.py <sheet png>: lip colour like with like on a facesheet front row (ref col 0, ours col 1): mean sRGB in
small patches on the upper lip (detector 0 / 37 / 267) and the lower lip (17 / 84 / 314), and on the cheek (50 / 280)
for the lip / skin ratio (light-independent-ish)."""
import sys

import numpy as np
from PIL import Image

import rs

sheet = Image.open(sys.argv[1]).convert("RGB")
PATCH = {"upper": (0, 37, 267), "lower": (17, 84, 314), "cheek": (50, 280)}


def read(im):
    a = np.asarray(im).astype(float)
    P = rs.detect([a.astype(np.uint8)])[0]["P"][:, :2]
    out = {}
    for k, ids in PATCH.items():
        v = []
        for i in ids:
            x, y = int(round(P[i, 0])), int(round(P[i, 1]))
            v.append(a[y - 2:y + 3, x - 2:x + 3].reshape(-1, 3).mean(0))
        out[k] = np.mean(v, 0)
    return out


r = read(sheet.crop((0, 28, 640, 668)))
o = read(sheet.crop((640, 28, 1280, 668)))
for k in PATCH:
    print(f"  {k:6s} ref {r[k].round(0)} ours {o[k].round(0)}")
for k in ("upper", "lower"):
    print(f"  {k}/cheek  ref {(r[k] / r['cheek']).round(2)}  ours {(o[k] / o['cheek']).round(2)}")
