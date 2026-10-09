"""camdbg2.py <model>: the model's landmarks projected through its stored desk camera, drawn on the reference crop
and on sheet1's desk tile ($D3/out/<model>_desk.png) -> $D3/out/camdbg_<model>.png; prints the frame."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

import sheet1
import stage
from hifipushie import humanfit, store

D3 = os.environ.get("D3")
name = sys.argv[1]
r = json.loads((store.HOME / name / "human_refs.json").read_text())
v, cam = r["views"][1], r["cameras"][1]
st = humanfit.state(store.load(name)["base"])
P = humanfit.project(cam, st["L"][:68])
crop = sheet1.crop_of(v)
k = 768 / (crop[2] - crop[0])
Q = (P - [crop[0], crop[1]]) * k
ref = Image.open(v["image"]).convert("RGB").crop(tuple(int(round(x)) for x in crop)).resize((768, 768))
ours = Image.open(f"{D3}/out/{name}_desk.png").convert("RGB")
for im in (ref, ours):
    d = ImageDraw.Draw(im)
    for x, y in Q:
        d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(0, 255, 0))
S = Image.new("RGB", (1536, 768))
S.paste(ref, (0, 0))
S.paste(ours, (768, 0))
S.save(f"{D3}/out/camdbg_{name}.png")
fr = stage.fitted_frame(cam, crop, "desk")
print({k_: (np.round(v_, 4).tolist() if isinstance(v_, (list, float)) else v_) for k_, v_ in fr.items()}, "crop", np.round(crop, 1).tolist())
