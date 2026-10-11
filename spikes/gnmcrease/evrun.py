"""evrun.py <model> <crease template> <out npz> [iters]: the NEW eye step's solve (blockin_eyes.solve, crease=<template>)
on the model's base with its front picture's evidence; no model written (scratch): saves c + the eye pairs."""
import sys
import numpy as np
from PIL import Image
from hifipushie import blockin as bi, blockin_eyes as be, store

name, crease, out = sys.argv[1], sys.argv[2], sys.argv[3]
iters = int(sys.argv[4]) if len(sys.argv) > 4 else 6
rj = bi._refs(name)
v = rj["views"][bi._front(rj)]
ev = be.photo_evidence(Image.open(v["image"]).convert("RGB"), v)
print("evidence", {k: x for k, x in ev.items() if k != "columns"}, flush=True)
s = be.solve(store.load(name)["base"], ev, iters=iters, crease=crease, log=lambda m: print(m, flush=True))
Ln, Rn, _ = be._names()
e = np.array([s["expression"].get(Ln[k], 0.0) for k in range(be.NE)])
np.savez(out, c=s["c"], e=e, dc=s["dc"], shape0=s["shape0"], shape=s["shape"], heights=np.array(s["heights"] or [np.nan] * 3), tps_cols=np.array(ev.get("tps_cols") or [np.nan] * 3))
print(be.text({"evidence": ev, **{k: s[k] for k in ("read0", "read", "dc", "e", "crease", "shape0", "shape", "heights")}}))
print("done", out)
