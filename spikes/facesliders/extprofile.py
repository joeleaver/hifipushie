"""extprofile.py <group:target+:target-> ...: what a carried MakeHuman target does to the lower (and upper) lip, by
|x| across the mouth (faces3): the mean move up / forward (mm at +1) of the visible vermilion and the skin under it."""
import sys

import numpy as np

from hifipushie import faceext, faceslide

T = faceslide.template()
X, n, lm = T["X"], T["n"], T["lm"]
R = faceslide._lip_rings()
inner = np.zeros(len(X), bool)
for r in R["rings"][:R["contact"] + 1]:
    inner[r] = True
up = np.zeros(len(X), bool)
up[:len(R["upper"])] = R["upper"]
vis = (n[:, 2] > 0.3) & ~inner & T["ext"]
hw = 0.5 * float(lm[54][0] - lm[48][0])
yb = float(lm[57][1])  # the lower border's middle
ys = float(lm[66][1])
for arg in sys.argv[1:]:
    nm, plus, minus = arg.split(":")
    faceext.EXT[nm] = ("mouth", plus, minus or None, "")
    d = faceext.field(nm)[0]
    print(f"== {nm}: max {np.linalg.norm(d, axis=1).max()*1e3:.2f} mm")
    for lab, sel in (("lower red", vis & ~up & (X[:, 1] > yb - 0.0005) & (X[:, 1] < ys)),
                     ("under lip", vis & (X[:, 1] < yb - 0.0005) & (X[:, 1] > yb - 0.006)),
                     ("upper red", vis & up & (X[:, 1] > ys) & (X[:, 1] < float(lm[51][1]) + 0.0005))):
        row = []
        for a, b in ((0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 1.0)):
            s = sel & (np.abs(X[:, 0]) >= a * hw) & (np.abs(X[:, 0]) < b * hw)
            m = d[s].mean(0) * 1e3 if s.any() else np.zeros(3)
            row.append(f"{m[1]:+.2f}u {m[2]:+.2f}f")
        print(f"   {lab:10s} |x|/hw 0-.2 .. .8-1: " + " | ".join(row))
