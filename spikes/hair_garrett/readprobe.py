"""readprobe.py <model> [authority=<i>]: hair_read.read + start on the model, the text printed, and per view an overlay
$TOUT/read_<model>_v<i>.png (crop round the head): skull silhouette green, solid hair edge red, halo band rays
yellow where they meet the backdrop, hairline samples blue, the part's column magenta, dense colour pixels dimmed out).
Also writes $TOUT/read_<model>.json (the read without pictures)."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

from hifipushie import hair, hair_read, humanfit, store

m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
OUT = os.environ["TOUT"]
au = int(kw["authority"]) if "authority" in kw else None
spec = store.load(m)
fs = hair_read.frames(m, spec)
r = hair_read.read(m, spec, authority=au, fs=fs)
print(r["text"])
s = hair_read.start(r, spec)
print(s["text"])
json.dump({"read": {k: v for k, v in r.items() if k != "text"}, "start": s["hair"]}, open(f"{OUT}/read_{m}.json", "w"),
          indent=1, default=float)
sc = hair.scalp(m, spec)
for f, v in zip(fs, r["views"]):
    hn = hair_read.hairness(f["image"], f["hair"], f["bg"], f["mm"])
    im = np.asarray(f["image"], float).copy()
    e = hn["solid"] ^ ndi.binary_erosion(hn["solid"], iterations=2)
    k = f["skull"] ^ ndi.binary_erosion(f["skull"], iterations=2)
    im[k] = [0, 220, 0]
    im[e] = [255, 0, 0]
    pil = Image.fromarray(im.clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(pil)
    # hairline samples: re-project their scalp points
    hl = np.array(v.get("hairline") or [], float).reshape(-1, 3)
    if len(hl):
        P = sc.point(hl[:, 0], hl[:, 1], 0.0)
        uv = humanfit.project(f["cam"], P)
        for u_, v_ in uv[::2]:
            d.ellipse([u_ - 2, v_ - 2, u_ + 2, v_ + 2], fill=(40, 90, 255))
    p = v.get("parting") or {}
    if p.get("x_px") is not None:
        d.line([p["x_px"], 0, p["x_px"], f["image"].size[1] * 0.45], fill=(255, 0, 255), width=2)
    x0, y0, x1, y1 = [int(x) for x in f["box"]]
    pil.crop((x0, y0, x1, y1)).resize((700, 700)).save(f"{OUT}/read_{m}_v{f['i']}.png")
print("saved", [f"{OUT}/read_{m}_v{f['i']}.png" for f in fs])
