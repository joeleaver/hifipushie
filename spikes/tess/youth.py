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
    m["upper lid over iris top R (mm, + covers)"] = (P[159, 1] - P[470, 1]) * k
    m["lower lid under iris bottom R (mm, + white shows)"] = (P[145, 1] - P[472, 1]) * k
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
    m["lower lip height at mid (14-17)"] = d(P, 14, 17) * k
    m["lower lip height at 1/4 (87-84)"] = d(P, 87, 84) * k
    m["upper lip height at mid (0-13)"] = d(P, 0, 13) * k
    # the lower lip's visible width: the red run along the row 40% down the lower vermilion (redness = r - (g+b)/2
    # over the cheek's own)
    y = int(round(P[14, 1] + 0.4 * (P[17, 1] - P[14, 1])))
    red = a[y, :, 0] - 0.5 * (a[y, :, 1] + a[y, :, 2])
    ck = np.median(a[int(P[50, 1]) - 3:int(P[50, 1]) + 3, int(P[50, 0]) - 3:int(P[50, 0]) + 3].reshape(-1, 3), 0)
    thr = (ck[0] - 0.5 * (ck[1] + ck[2])) + 0.45 * (red[int(P[17, 0])] - (ck[0] - 0.5 * (ck[1] + ck[2])))
    cx = int(round(P[17, 0]))
    l = cx
    while l > 0 and red[l - 1] > thr:
        l -= 1
    r = cx
    while r < len(red) - 1 and red[r + 1] > thr:
        r += 1
    m["lower lip visible width / mouth width"] = (r - l) / d(P, 61, 291)
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
