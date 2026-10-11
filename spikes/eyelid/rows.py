"""rows.py [model ...]: GNM's RAW mesh (no pipeline) at the pupil column of the left eye, row by row from the socket
lining over the lid margin up to the brow: height v over the eye centre, forward w, distance to GNM's own eyeball
(r 14.5), the row spacing. For GNM's mean and each model's identity (+ its expression if it has one)."""
import sys

import numpy as np

import lidmap as lm
from hifipushie import blockin as bi, gnm_controls as gc, store

g = gc.gnm()
t = lm.topo()
print("rings: vertices per ring", {k: len(v) for k, v in t["loops"].items()})


def expr(spec):
    e = np.zeros(len(g["ex_names"]))
    for k, x in (spec["base"]["head"].get("expression") or {}).items():
        e[g["ex_names"].index(k)] = float(x)
    return e


def show(label, c, e=None):
    V = gc.vertices(c, e) * 1000
    ctr, r = lm.eye_frame_raw(c)
    print(f"\n{label}: GNM's own ball r {r:.2f} mm, centre {np.round(ctr, 1)}")
    for u in (-5.0, 0.0, 5.0):
        col = lm.column(V, ctr, u)
        print(f"  u = {u:+.0f}:  ring   v(up)  w(fwd)  to ball   step")
        prev = None
        for k, v, w in col:
            d = np.sqrt(u * u + v * v + w * w) - r
            st = "" if prev is None else f"{np.hypot(v - prev[0], w - prev[1]):6.2f}"
            print(f"          {k:4d} {v:7.2f} {w:7.2f} {d:7.2f}  {st}")
            prev = (v, w)


show("GNM mean", None)
for name in sys.argv[1:]:
    sp = store.load(name)
    c = bi.identity(sp)
    show(name + " identity", c)
    if sp["base"]["head"].get("expression"):
        show(name + " identity + expression", c, expr(sp))
