"""mmsheet.py: mm: moves at -4 / 0 / +4 mm on a random GNM head (front / 3/4 / profile): do they read natural?"""
import os
import sys
from pathlib import Path

import numpy as np

import drv
import gnmc
from hifipushie import blockin as bi

R = Path(os.environ.get("R"))
rng = np.random.default_rng(5)
c0 = rng.normal(size=170) * 0.8
names = sys.argv[2:]
rows, labels = [], []
for n in names:
    d = bi.direction("mm:" + n)
    ims = []
    for a in (-4, 0, 4):
        ims += drv.view_imgs(c0 + a * d, c0, "head", px=200, views=["front", "profile"])
    rows.append(ims)
    labels.append(f"mm:{n}\n-4 | 0 | +4 mm\n|dc| {4 * np.linalg.norm(d):.1f}")
S = gnmc.grid(rows, cols_labels=["-4 front", "-4 profile", "0 front", "0 profile", "+4 front", "+4 profile"],
              rows_labels=labels, title="mm: moves (a measure moved, every other measure held in mm)", lw=130)
S.save(R / f"{sys.argv[1]}.png")
print(R / f"{sys.argv[1]}.png")
