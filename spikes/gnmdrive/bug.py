"""bug.py <case>: BEFORE vs a zero trial (driver report: the BEFORE row isn't the current head)."""
import json
import sys

import numpy as np

import drv
import drive

case = sys.argv[1]
d, st, cB = drive._load(case)
c = st["c"]
c1 = drive.apply(c, {"ear_out!": 0.0})
print("max |c1 - c|", np.abs(np.asarray(c1) - np.asarray(c)).max(), type(c))
h = json.loads((drv.HIDDEN / f"{case}.json").read_text())
print("|c - A|", np.linalg.norm(np.asarray(c) - np.asarray(h["A"])))
for order in ("list first", "array first"):
    if order == "list first":
        a = np.asarray(drv.view_imgs(c, cB, "brows", px=240)[0]).astype(float)
        b = np.asarray(drv.view_imgs(c1, cB, "brows", px=240)[0]).astype(float)
    else:
        b = np.asarray(drv.view_imgs(c1, cB, "brows", px=240)[0]).astype(float)
        a = np.asarray(drv.view_imgs(c, cB, "brows", px=240)[0]).astype(float)
    print(order, "mean |list - array|", np.abs(a - b).mean())
A = np.asarray(drv.view_imgs(h["A"], cB, "brows", px=240)[0]).astype(float)
print("list render vs A", np.abs(a - A).mean(), "array render vs A", np.abs(b - A).mean())
V1, V2 = drv.verts(c), drv.verts(c1)
print("verts diff", np.abs(V1 - V2).max())
