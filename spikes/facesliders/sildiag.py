"""sildiag.py <model>: fit5.silhouette_env on the model's profile view: misses per row band (mm, + = model outside)
and an overlay (photo contour red, model silhouette vertices green) in $F/out/sildiag_<model>.png."""
import json
import sys

import numpy as np
from PIL import Image, ImageDraw

import fit5
import outl
from hifipushie import humanfit, store

m = sys.argv[1]
sp = store.load(m)
refs = json.loads((store.HOME / m / "human_refs.json").read_text())
vi = [i for i, v in enumerate(refs["views"]) if abs(float(v.get("yaw", 0))) > 70][0]
v, cam = refs["views"][vi], refs["cameras"][vi]
st = humanfit.state(fit5.spec_with(sp, humanfit.identity(sp["base"]))["base"])
o = outl.profile_auto(v, step=3)
env = fit5.silhouette_env(st, cam, o)
px = humanfit.project(cam, env["X"])
mm = cam["t"][2] / cam["f"] * 1000
r = ((px - env["p"]) * env["n"]).sum(1) * mm
for y0 in range(560, 960, 20):
    sel = (env["p"][:, 1] >= y0) & (env["p"][:, 1] < y0 + 20)
    if sel.any():
        print(f"rows {y0}-{y0 + 20}: miss mm {np.round(r[sel], 1).tolist()}")
img = Image.open(v["image"]).convert("RGB")
d = ImageDraw.Draw(img)
d.line([tuple(p) for p in o], fill=(255, 0, 0), width=1)
for p in px:
    d.ellipse([p[0] - 1.5, p[1] - 1.5, p[0] + 1.5, p[1] + 1.5], fill=(0, 200, 0))
img.crop((50, 450, 450, 1000)).save(f"/mnt/data/hifipushie/faces5/out/sildiag_{m}.png")
