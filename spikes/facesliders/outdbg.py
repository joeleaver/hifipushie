"""outdbg.py <model> <traces model> <out.jpg> [view]: each traced outline line (red) and the model's matched silhouette
vertices through the model's fitted camera (blue, a yellow line to their outline point); green dots = the mesh."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

import outl
from hifipushie import humanfit, store

name, trm, out = sys.argv[1:4]
only = int(sys.argv[4]) if len(sys.argv) > 4 else None
sp = store.load(name)
refs = json.loads((store.HOME / name / "human_refs.json").read_text())
st = humanfit.state(sp["base"])
tiles = []
for i, (v, cam) in enumerate(zip(refs["views"], refs["cameras"])):
    if only is not None and i != only:
        continue
    lines = outl.traced(trm, v["image"], ("cheek.R", "cheek.L", "jaw.R", "jaw.L", "chin", "profile"))
    if not lines:
        continue
    im = Image.open(v["image"]).convert("RGB")
    d = ImageDraw.Draw(im)
    allv = humanfit.project(cam, np.asarray(st["tpl"]["P"], float)[::5])
    for a in allv:
        d.point(tuple(a), fill=(0, 255, 0))
    for ln, o in zip([k for k in ("cheek.R", "cheek.L", "jaw.R", "jaw.L", "chin", "profile")
                      if outl.traced(trm, v["image"], (k,))], lines):
        d.line([tuple(p) for p in o], fill=(255, 40, 40), width=2)
        sl = humanfit._silhouette(st, cam, np.asarray(o, float)) if os.environ.get("SIL") else __import__("joint2").envelope(st, cam, np.asarray(o, float), __import__("joint2").SHADE_LINES.get(ln))
        if sl is None:
            continue
        uv = humanfit.project(cam, sl["X"])
        for a, b in zip(uv, sl["p"]):
            d.line([tuple(a), tuple(b)], fill=(255, 255, 0), width=1)
            d.ellipse([a[0] - 2, a[1] - 2, a[0] + 2, a[1] + 2], fill=(0, 120, 255))
    P = np.concatenate(lines)
    lo, hi = P.min(0), P.max(0)
    c, r = 0.5 * (lo + hi), 0.65 * max(hi - lo)
    tiles.append(im.crop((int(c[0] - r), int(c[1] - r), int(c[0] + r), int(c[1] + r))).resize((600, 600)))
S = Image.new("RGB", (600 * len(tiles), 600))
for i, t in enumerate(tiles):
    S.paste(t, (600 * i, 0))
S.save(out, quality=85)
print("wrote", out)
