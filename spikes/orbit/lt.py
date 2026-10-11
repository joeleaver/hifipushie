"""lt.py <model> [donor]: blockin_lid.lid_step on a model's base with the eye ruler's fold line (no model written):
the numbers against spikes/eyelid/lidsolve.py's (er_s4 -> el_a6: |dc| 5.0, miss 0.23, platform 1.59 -> 1.06, tuck 17 ->
24-25, wall 29 -> 42)."""
import sys

import numpy as np

from hifipushie import blockin_eyes as be, blockin_lid as bl, store

name = sys.argv[1]
base = store.load(name)["base"]
rv = be.ruler_evidence(name)
print("ruler fold line over the margin at", be.RULER_COLS.tolist(), "->", np.round(rv["crease"], 2).tolist(), "dark", round(rv["crease_dark"], 3))
s = bl.lid_step(base, rv["crease"], be.RULER_COLS, (rv["inner"][0], rv["outer"][0]), donor_name=sys.argv[2] if len(sys.argv) > 2 else bl.DONOR)
print(bl.text(s))
print("ball rings before", {k: round(v, 2) for k, v in s["ball0"]["rings"].items()}, "landmarks", round(s["ball0"]["landmarks"], 2))
print("ball rings after ", {k: round(v, 2) for k, v in s["ball"]["rings"].items()}, "landmarks", round(s["ball"]["landmarks"], 2))
