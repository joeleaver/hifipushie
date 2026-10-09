"""silw.py <model> [tile]: SILHOUETTE widths, photo against our render through the front camera (sheet1's tile):
at levels set by the same detector on both pictures (eye line, nose base, lip seam, and fractions of seam -> chin),
the width of what is not backdrop on that row (the run through the face's middle), in pixels of the photo and as a
share of the detector's iris distance (scale-free). The detector's own oval points are not the outline (refstudy:
3-12 mm of definition bias on the jaw): this reads the outline itself. Rows where the photo's run includes ears /
hair / collar are marked by eye in the table's label only."""
import os
import sys

import numpy as np
from PIL import Image

import rs
import skinm

D3 = os.environ.get("D3")


def mask(a):
    a = a.astype(float)
    bg = np.median(np.concatenate([a[:12, :12].reshape(-1, 3), a[:12, -12:].reshape(-1, 3)]), 0)
    return np.linalg.norm(a - bg, axis=2) > 28


def rows(img):
    a = np.asarray(img.convert("RGB"))
    P = np.asarray(rs.detect([a])[0]["P"], float)[:, :2]
    m = mask(a)
    io = np.linalg.norm(P[468] - P[473])
    eye_y, nose_y, seam_y, chin_y = P[[468, 473], 1].mean(), P[2, 1], P[13, 1], P[152, 1]
    cx = P[[2, 13, 152], 0].mean()
    lv = {"eye": eye_y, "mid_eye_nose": 0.5 * (eye_y + nose_y), "nose_base": nose_y, "seam": seam_y,
          "seam+25%": seam_y + 0.25 * (chin_y - seam_y), "seam+50%": seam_y + 0.5 * (chin_y - seam_y),
          "seam+75%": seam_y + 0.75 * (chin_y - seam_y)}
    out = {}
    for n, y in lv.items():
        r = m[int(round(y))]
        x = int(round(cx))
        l = x
        while l > 0 and r[l - 1]:
            l -= 1
        h = x
        while h < len(r) - 1 and r[h + 1]:
            h += 1
        out[n] = (h - l) / io
    out["height nasion-chin"] = np.linalg.norm(P[168] - P[152]) / io
    return out, io


if __name__ == "__main__":
    name = sys.argv[1]
    tile = sys.argv[2] if len(sys.argv) > 2 else f"{D3}/out/{name}_m_front.png"
    ph, mm = skinm.photo_and_scale(name)
    big = ph.resize((ph.size[0] * 2, ph.size[1] * 2), Image.LANCZOS)
    ours = Image.open(tile).convert("RGB").resize(big.size, Image.LANCZOS)
    a, ioa = rows(big)
    b, iob = rows(ours)
    print(f"silhouette width / iris distance (x 73.3 = mm at the photo's iris distance); iris px photo {ioa:.1f} ours {iob:.1f}")
    for k in a:
        print(f"  {k:20s} photo {a[k]:.3f} ({a[k] * 73.3:6.1f} mm)  ours {b[k]:.3f} ({b[k] * 73.3:6.1f} mm)  diff {(b[k] - a[k]) * 73.3:+.1f} mm")
