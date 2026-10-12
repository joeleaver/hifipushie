"""fitc.py <model> [frames=<pkl tag>] [groups=tone,zones,eyes,lips,stubble] [anchor=auto]: the COLOUR fit alone from cached
frames ($G/out/frames_<tag>.pkl; no Blender, no fold read): the read's region table, the fit's text, the fitted
parameters. Nothing is saved."""
import json, os, pickle, sys, time
import numpy as np
from hifipushie import skin_read as sr

name = sys.argv[1]
kw = dict(a.split("=") for a in sys.argv[2:])
G = os.environ["G"] + "/out"
frames = pickle.load(open(f"{G}/frames_{kw.get('frames', name)}.pkl", "rb"))
t = time.time()
c = sr.context(name, frames=frames, anchor=kw.get("anchor", "auto"), log=lambda s: None)
R = sr.regions(c)
r = {"anchor": {k: v for k, v in c.anchor.items() if k != "gain"}, "views": c.views, "regions": {k: sr._region(c, wz) for k, wz in R.items()},
     "freckles": {"read": False, "views": {}}, "brows": {"read": False}, "eyes": {}, "ctx": c}
print(c.anchor["note"])
for k, x in r["regions"].items():
    print(f"  {k:16s} {x['px']:7.0f}  " + (f"{str(x['ours']):20s} {str(x['picture']):20s} {x['d']}" if x["read"] else "NOT READ"))
groups = tuple(kw.get("groups", "tone,zones,eyes,lips,stubble").split(","))
f = sr.fit(r, groups=groups, log=print)
print(f["text"])
print("shade", json.dumps(f["shade"]))
print("face zones", json.dumps(f["face"]["zones"]))
print("residual after:", json.dumps({k: v["after"] for k, v in f["residual"].items()}))
print(f"{time.time() - t:.0f} s")
