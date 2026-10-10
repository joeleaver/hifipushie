"""framechk.py <model> <view> <region>: does a featsheet crop line up? The photo crop with the photo's detector points
(blue) and the model's lm68 projected through its fitted camera (green), and the model's render of the same frame with
the same green points: if the green sits on the render's features but not on the photo's, the camera is off; if not on
the render's either, the render frame is off."""
import json
import sys

import numpy as np
from PIL import Image, ImageDraw

import featsheet as FS
from hifipushie import humanfit, store

m, vi, rg = sys.argv[1], int(sys.argv[2]), sys.argv[3]
refs = json.loads((store.HOME / m / "human_refs.json").read_text())
bx = [b for b in FS.boxes(refs, [rg]) if b[0] == vi]
ims = FS.render_model(m, bx)
_, _, box, img = bx[0]
cam = refs["cameras"][vi]
st = humanfit.state(store.load(m)["base"])
L = humanfit.project(cam, st["L"][:68])
T = 500
k = T / (box[2] - box[0])
out = Image.new("RGB", (2 * T, T), "white")
for j, im in enumerate([img.crop(tuple(int(round(b)) for b in box)), ims[f"v{vi}_{rg}"]]):
    im = im.convert("RGB").resize((T, T))
    d = ImageDraw.Draw(im)
    for p in L:
        q = (p - box[:2]) * k
        d.ellipse([q[0] - 3, q[1] - 3, q[0] + 3, q[1] + 3], fill=(0, 220, 0))
    out.paste(im, (j * T, 0))
p = f"/mnt/data/hifipushie/faces5/out/framechk_{m}_{vi}_{rg}.png"
out.save(p)
print("wrote", p, "box", [round(b) for b in box])
