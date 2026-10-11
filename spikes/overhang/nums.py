"""nums.py <tag>=<model>[:<source model | mean>] ...: the raw-mesh numbers of a scratch model for the sheets
(gnm_fold.read on its identity; against its source: |dc|, the brow ring's drop, gnm_mm's largest moves, the skin's
move outside the upper lids). Writes / updates out/nums.json."""
import json
import os
import sys

import numpy as np

from hifipushie import blockin as bi, gnm_controls as gc, gnm_fold as gf, gnm_mm, store

G = os.environ["G"] + "/out"
res = json.load(open(G + "/nums.json")) if os.path.exists(G + "/nums.json") else {}
g = gc.gnm()
t = gf.topo()
for a in sys.argv[1:]:
    tag, rest = a.split("=", 1)
    model, _, src = rest.partition(":")
    c = bi.identity(store.load(model))
    q = gf.read(gf.vertices(c))
    row = {"model": model, "c": float(np.linalg.norm(c)), "hang": q["hang_mean"], "hang_max": q["hang_max"], "turn": q["turn_mean"],
           "h": q["h_mean"], "brow_h": q["brow_h"]}
    if src:
        c0 = np.zeros(170) if src == "mean" else bi.identity(store.load(src))
        V0, V1 = gf.vertices(c0), gf.vertices(c)
        q0 = gf.read(V0)
        rr = np.minimum(np.abs(t["ring"]), np.abs(t["ring"][t["mir"]]))
        held = g["groups"]["skin_exterior"] & ~((rr >= 1) & (rr <= 9) & (g["T"][:, 1] > g["J"][2][1]))
        mv = np.linalg.norm(V1 - V0, axis=1)[held]
        row.update({"src": src, "dc": float(np.linalg.norm(c - c0)), "brow_drop": q0["brow_h"] - q["brow_h"],
                    "held_rms": float(np.sqrt((mv ** 2).mean())), "held_max": float(mv.max()),
                    "measures": [(r["measure"], round(r["gap"], 2)) for r in gnm_mm.gaps(V0 / 1000, V1 / 1000)[:4]]})
    res[tag] = row
    print(tag, {k: (round(v, 2) if isinstance(v, float) else v) for k, v in row.items()})
json.dump(res, open(G + "/nums.json", "w"))
