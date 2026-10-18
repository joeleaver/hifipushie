"""nape.py <model> <out dir> [size=512] [hair=0] [views=back,back_low]: the back of the neck (no photo camera sees it: seams
and fills there show only to a hair / garment agent's back views), lit from behind like FRONT_LIGHT from the front.
Tiles <out>/nape_<view>.png. HEAVY (a stage build)."""
import os, sys
import numpy as np
import stage
from hifipushie import render, skin_look, store

m, out = sys.argv[1:3]
kw = dict(a.split("=", 1) for a in sys.argv[3:])
os.makedirs(out, exist_ok=True)
J = skin_look._J(store.load(m))
nt = np.asarray(J["lm_nose_tip"], float)
c = np.array([0.0, nt[1] + 0.085, nt[2] - 0.08])   # the head's axis at the nape's height
D = {"back": [0.0, 1.0, 0.05], "back_low": [0.0, 1.0, -0.35], "back_side": [0.5, 1.0, 0.05]}
frames = []
for i, n in enumerate(kw.get("views", "back,back_low").split(",")):
    d = np.asarray(D[n], float); d /= np.linalg.norm(d)
    frames.append({**render.camera_frame({"eye": (c + d * 0.9).tolist(), "target": c.tolist(), "fov": 16.0, "name": f"nape_{n}"}, i)})
L = stage.FRONT_LIGHT
light = {**L, "lights": [{**l, "dir": [l["dir"][0], -l["dir"][1], l["dir"][2]]} for l in L["lights"]]}   # mirrored to the back
for k, im in stage.shoot(m, frames, light, size=int(kw.get("size", 512)), hair_on=kw.get("hair", "0") == "1").items():
    im.save(f"{out}/{k}.png")
print("nape ->", out)
