"""truth | mean head | today's fit | best fit so far: front + profile, lit, and each fit's error on the truth as a
heat map (blue 0 .. red 6 mm+, after alignment on the face).  run.sh pic.py out.png subject ..."""
import sys

import numpy as np
from PIL import Image, ImageDraw

import fitlib
import rs
import subjects
import table as tb


def heat(d):
    t = np.clip(d / 6.0, 0, 1)[:, None]
    return (1 - t) * np.array([70, 110, 230.0]) + t * np.array([235, 50, 40.0])


def aligned(V, Vt):
    f = rs.gnm()["regions"]["face"]
    s, R, t = rs.similarity(V[f], Vt[f])
    return s * V @ R.T + t


def tiles(V, Vt, label, sc=None):
    out = []
    for yaw in (0.0, 88.0):
        cam = rs.make_cam(Vt, yaw=yaw, lens=85, size=(330, 380), fill=0.72)
        out.append(rs.render(V, cam)[0])
    if Vt is not V:
        A = aligned(V, Vt)
        d = np.linalg.norm(A - Vt, axis=1) * 1000
        for yaw in (0.0, 88.0):
            cam = rs.make_cam(Vt, yaw=yaw, lens=85, size=(330, 380), fill=0.72)
            out.append(rs.render(Vt, cam, albedo=heat(d), flat=True)[0])
    else:
        out += [np.full((380, 330, 3), 238, np.uint8)] * 2
    im = Image.fromarray(np.concatenate(out, 1))
    dr = ImageDraw.Draw(im)
    dr.text((6, 4), label + (f"   face {sc['face']:.1f}  profile {sc['profile']:.1f}  jaw {sc['jaw']:.1f}  chin {sc['chin']:.1f}  nose {sc['nose']:.1f} mm" if sc else ""), fill=(0, 0, 0))
    return np.asarray(im)


def main():
    out, names = sys.argv[1], sys.argv[2:]
    rows = []
    for n in names:
        s = subjects.load([x for x in subjects.names() if x.startswith(n)][0])
        Vt = s["V"]
        col = [tiles(Vt, Vt, f"{s['name']}: TRUTH (lit front, profile | error maps: blue 0 .. red 6 mm)")]
        mean = rs.head()
        col.append(tiles(mean, Vt, "mean head, no fit", rs.score(mean, Vt)))
        f1 = tb.METHODS["B1 mp68 no jaw, today's weights (fit_views)"](s)
        V1 = rs.head(f1["c"])
        col.append(tiles(V1, Vt, "today: detector's 68 as GNM's landmarks, today's weights", rs.score(V1, Vt)))
        f2 = tb.METHODS["B3b mp478 calibrated, sigma x2"](s)
        V2 = rs.head(f2["c"])
        col.append(tiles(V2, Vt, "MAP: detector's 478 at calibrated places + noise, identity prior", rs.score(V2, Vt)))
        f3 = tb.METHODS["A2 oracle lm +-1.5mm, MAP"](s)
        V3 = rs.head(f3["c"])
        col.append(tiles(V3, Vt, "ceiling: exact landmark definitions +-1.5 mm, MAP", rs.score(V3, Vt)))
        rows.append(np.concatenate(col, 0))
    Image.fromarray(np.concatenate(rows, 1)).save(out)
    print(out)


if __name__ == "__main__":
    main()
