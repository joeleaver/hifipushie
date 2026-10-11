"""readd.py [tags]: lidfold.read_lid on the dressed eye crops (and photo_tess.png): middle columns of both eyes, tps (mm at
the iris' scale) / dark / width. -> out/readd.json"""
import glob
import json
import os
import sys

import numpy as np
from PIL import Image

from hifipushie import lidfold, likeness

G = "/mnt/data/hifipushie/gnmcrease/out/"
tags = sys.argv[1:] or sorted(p.split("d_")[1][:-9] for p in glob.glob(G + "d_*_face.png"))
res = {}
try:
    res = json.load(open(G + "readd.json"))
except Exception:
    pass
for t in ["photo"] + tags:
    p = ("/home/joe/dev/s0urc3/docs/img/tess_ref_full/tess_head_front.png" if t == "photo" else G + f"d_{t}_face.png")
    im = Image.open(p).convert("RGB")
    if t != "photo" and os.environ.get("PHOTORES", "1") == "1":
        im = im.resize((int(im.width * 0.146 / 0.277), int(im.height * 0.146 / 0.277)), Image.LANCZOS)   # the photo's mm / px
    P = likeness.detect([im])[0]
    if P is None:
        print(t, "no face"); continue
    cols = lidfold.read_lid(im, np.asarray(P, float), fractions=(0.4, 0.5, 0.6))
    mids = [c for e in cols for c in e]
    f = lambda k: float(np.nanmedian([c.get(k, np.nan) for c in mids]))  # noqa: E731
    res[t] = {"tps": f("tps"), "dark": f("dark"), "width": f("width")}
    print(f"{t:8s} line {res[t]['tps']:.2f} mm dark {res[t]['dark']:.2f} width {res[t]['width']:.2f}", flush=True)
json.dump(res, open(G + "readd.json", "w"))
