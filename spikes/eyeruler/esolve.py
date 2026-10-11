"""esolve.py <src> <dst er_*> [ne=20] [crease=s376|fold|none] [iters=6]: the eye step's solve on the RULER's evidence
(blockin_eyes.solve with ev["ruler"]), written as a scratch model. Env: NOEXPR=1 starts from the source with its
eye expression cleared; BALL=<m> sets base.head.eye_radius (default: the key removed = GNM's own ball x 0.96);
SIGSHAPE=<mm> the section sigma; NOCREASE=1 drops the crease heights from the ruler (the old photo line)."""
import copy
import os
import sys

import numpy as np
from PIL import Image

import mk
from hifipushie import blockin as bi, blockin_eyes as be, store

src, dst = sys.argv[1], sys.argv[2]
ne = int(sys.argv[3]) if len(sys.argv) > 3 else be.NE
crease = sys.argv[4] if len(sys.argv) > 4 else "s376"
crease = None if crease == "none" else crease
iters = int(sys.argv[5]) if len(sys.argv) > 5 else 6
if os.environ.get("SIGSHAPE"):
    be.SIG_SHAPE = float(os.environ["SIGSHAPE"])
rj = bi._refs(src)
v = rj["views"][bi._front(rj)]
ev = be.photo_evidence(Image.open(v["image"]).convert("RGB"), v)
rv = be.ruler_evidence(src)
ev["ruler"] = {k: rv[k] for k in ("up", "lo", "inner", "outer", "crease_cols")}
if os.environ.get("NOCREASE"):
    ev["ruler"]["crease_cols"] = None
print("ruler:", {k: np.round(np.asarray(x, float), 2).tolist() if x is not None else None for k, x in ev["ruler"].items()}, "iris", round(rv["iris"], 2), flush=True)
sp = copy.deepcopy(store.load(src))
sp.pop("hair", None)
hd = sp["base"]["head"]
if os.environ.get("BALL"):
    hd["eye_radius"] = float(os.environ["BALL"])
else:
    hd.pop("eye_radius", None)
if os.environ.get("NOEXPR"):
    hd.pop("expression", None)
s = be.solve(sp["base"], ev, iters=iters, crease=crease, ne=ne, log=lambda m: print(m, flush=True))
bi.set_identity(sp, s["c"])
hd = sp["base"]["head"]
hd["expression"] = s["expression"]
if not hd["expression"]:
    hd.pop("expression")
sp.setdefault("skin", {}).setdefault("eyes", {})["iris_size"] = round(rv["iris"] / 1000, 5)
mk.write(dst, sp, src)
mg = s["read"].get("margins")
if mg is not None:
    print("target up", np.round(ev["ruler"]["up"], 2), "lo", np.round(np.asarray(ev["ruler"]["lo"]) - be.LO_BIAS, 2), "inner", np.round(ev["ruler"]["inner"], 2), "ring_out", round(ev["ruler"]["outer"][0] + be.OUT_RING, 2))
    print("model  up", np.round(mg["up"], 2), "lo", np.round(mg["lo"], 2), "inner", np.round(mg["inner"], 2), "ring_out", np.round(mg["ring_out"], 2))
print(f"|dc| {s['dc']:.2f} |e| {s['e']:.2f} shape {s['shape0']:.2f} -> {s['shape']:.2f} socket {s['socket0']} -> {s['socket']}")
print("done", dst)
