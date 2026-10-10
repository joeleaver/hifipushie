"""outdbg.py <model> <traces model> <out.jpg>: each view's outline (red) and the model's matched silhouette vertices
through the model's fitted camera (blue, with a line to their outline point)."""
import json
import sys

import numpy as np
from PIL import Image, ImageDraw

import outl
from hifipushie import humanfit, store

name, trm, out = sys.argv[1:4]
sp = store.load(name)
refs = json.loads((store.HOME / name / "human_refs.json").read_text())
st = humanfit.state(sp["base"])
tiles = []
for v, cam in zip(refs["views"], refs["cameras"]):
    o = outl.front_outline(v) if abs(float(v.get("yaw", 0))) < 20 else np.concatenate(outl.traced(trm, v["image"]))
    sl = humanfit._silhouette(st, cam, o)
    im = Image.open(v["image"]).convert("RGB")
    d = ImageDraw.Draw(im)
    d.line([tuple(p) for p in o], fill=(255, 40, 40), width=2)
    uv = humanfit.project(cam, sl["X"])
    for a, b in zip(uv, sl["p"]):
        d.line([tuple(a), tuple(b)], fill=(255, 255, 0), width=1)
        d.ellipse([a[0] - 2, a[1] - 2, a[0] + 2, a[1] + 2], fill=(0, 120, 255))
    allv = humanfit.project(cam, np.asarray(st["tpl"]["P"], float)[::7])
    for a in allv:
        d.point(tuple(a), fill=(0, 255, 0))
    lo, hi = o.min(0), o.max(0)
    c, r = 0.5 * (lo + hi), 0.7 * max(hi - lo)
    tiles.append(im.crop((int(c[0] - r), int(c[1] - r), int(c[0] + r), int(c[1] + r))).resize((600, 600)))
S = Image.new("RGB", (600 * len(tiles), 600))
for i, t in enumerate(tiles):
    S.paste(t, (600 * i, 0))
S.save(out, quality=85)
print("wrote", out)
