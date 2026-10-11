"""stale.py <case>: are renders of different heads in one process really different? (driver report: CURRENT stale)"""
import json
import sys

import numpy as np

import drv

case = sys.argv[1]
h = json.loads((drv.HIDDEN / f"{case}.json").read_text())
st = json.loads((drv.CASES / case / "state.json").read_text())
cA, cB, c = np.array(h["A"]), np.array(h["B"]), np.array(st["c"])
for feat in ("head", "nose"):
    a1 = np.asarray(drv.view_imgs(cA, cB, feat, px=240)[0]).astype(float)
    c1 = np.asarray(drv.view_imgs(c, cB, feat, px=240)[0]).astype(float)
    c2, _ = drv.view_imgs(c, cB, feat, px=240, fg=True)
    c2 = np.asarray(c2[0]).astype(float)
    a2 = np.asarray(drv.view_imgs(cA, cB, feat, px=240)[0]).astype(float)
    print(feat, "A vs cur", np.abs(a1 - c1).mean(), "cur vs cur(passes)", np.abs(c1 - c2).mean(), "A vs A", np.abs(a1 - a2).mean(),
          "|c - A|", np.linalg.norm(c - cA))
