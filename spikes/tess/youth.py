"""youth.py <sheet png> [more sheet pngs ...]: youth / nose / eye cues like with like on facesheet front rows (ref = column 0,
ours = column 1): the same detector (MediaPipe 478) on both, mm by the pupils' distance (54.8 mm, hers). Several
sheets: one column of ours per sheet (before / after)."""
import sys

import numpy as np
from PIL import Image

import rs

IPD = 54.8


def d(P, a, b):
    return float(np.linalg.norm(P[a] - P[b]))


def read(im):
    a = np.asarray(im).astype(float)
    P = rs.detect([a.astype(np.uint8)])[0]["P"][:, :2]
    k = IPD / d(P, 468, 473)
    m = {}
    m["eye aperture R (canthi)"] = d(P, 33, 133) * k
    m["eye aperture L"] = d(P, 362, 263) * k
    m["iris diameter R"] = d(P, 469, 471) * k
    m["iris / aperture R"] = d(P, 469, 471) / d(P, 33, 133)
    m["eye opening R (159-145)"] = d(P, 159, 145) * k
    m["cheek width at zygoma (234-454)"] = d(P, 234, 454) * k
    m["cheek width under it (93-323)"] = d(P, 93, 323) * k
    m["width at mouth level (132-361)"] = d(P, 132, 361) * k
    m["jaw (172-397)"] = d(P, 172, 397) * k
    m["nasion-chin (168-152)"] = d(P, 168, 152) * k
    m["lower face (2-152) / nasion-chin"] = d(P, 2, 152) / d(P, 168, 152)
    m["nose length nasion-subnasale (168-2)"] = d(P, 168, 2) * k
    m["alar width (129-358)"] = d(P, 129, 358) * k
    m["tip width (220-440)"] = d(P, 220, 440) * k
    m["bridge width mid-dorsum (196-419)"] = d(P, 196, 419) * k
    m["nose tip height over subnasale (1->2, mm)"] = (P[2, 1] - P[1, 1]) * k
    m["mouth width (61-291)"] = d(P, 61, 291) * k
    mid = 0.5 * (P[13, 1] + P[14, 1])
    m["mouth corners above lip mid (mm, + up)"] = (mid - 0.5 * (P[61, 1] + P[291, 1])) * k
    m["brow inner heads apart (55-285)"] = d(P, 55, 285) * k
    m["brow inner head over inner canthus R (55 vs 133)"] = (P[133, 1] - P[55, 1]) * k
    return m


sheets = sys.argv[1:]
first = Image.open(sheets[0]).convert("RGB")
ref = read(first.crop((0, 28, 640, 668)))
cols = [read(Image.open(s).convert("RGB").crop((640, 28, 1280, 668))) for s in sheets]
names = [s.split("/")[-1].replace(".png", "") for s in sheets]
print(f"{'measure (mm unless a ratio)':52s} {'hers':>7s} " + " ".join(f"{n:>14s}" for n in names))
for key in ref:
    print(f"{key:52s} {ref[key]:7.2f} " + " ".join(f"{c[key]:7.2f} ({c[key] - ref[key]:+5.2f})" for c in cols))
