"""N2 proof renders: the solved start (X.npy) 4 sides on the body, and the neck close, each beside the reference.
  capped uv run python spikes/n2_render.py <run dir> <loaded.pkl> <reference.png> [X.npy name]"""
import pickle
import sys

import numpy as np
from PIL import Image

from hifipushie.chain_render import render_views

run, src, ref = sys.argv[1:4]
xn = sys.argv[4] if len(sys.argv) > 4 else "X.npy"
d = pickle.load(open(src, "rb"))
pat, body = d["pat"], d["body"]
X = np.load(f"{run}/{xn}")
tag = xn.split(".")[0]
R = Image.open(ref).convert("RGB")
for focus in (None, "neck"):
    out = f"{run}/{tag}_{focus or 'all'}"
    res = render_views(X, pat.M, body.V, body.T, out, focus=focus, size=900)
    ims = [Image.open(p).convert("RGB") for _, p in res]
    h = ims[0].height
    r = R.resize((int(R.width * h / R.height), h))
    sheet = Image.new("RGB", (r.width + sum(i.width for i in ims), h), "white")
    sheet.paste(r, (0, 0))
    x = r.width
    for i in ims:
        sheet.paste(i, (x, 0))
        x += i.width
    sheet.save(f"{out}_sheet.png")
    print(f"{out}_sheet.png", [p for _, p in res])
