"""jsheet.py <out.jpg> <refs model> <label=model:dressed_tag> ...: rows front / desk painting, each: the concept's crop,
then per column the dressed render ($F/out/<tag>_<view>_big.png, shot2.py) and the clay through the model's own fitted
camera (likeness.render), same crop. A text block under it (the report lines given in $NOTE file)."""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

import sheet1
from hifipushie import likeness, store

F = os.environ.get("F", "/mnt/data/hifipushie/facesliders")
T = 400


def tile(im, text):
    im = im.convert("RGB").resize((T, T), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 8 + 7 * len(text), 16], fill=(0, 0, 0))
    d.text((4, 2), text, fill=(255, 255, 255))
    return im


out, refm = sys.argv[1], sys.argv[2]
refs = json.loads((store.HOME / refm / "human_refs.json").read_text())
rows = []
for vi, vn in ((0, "front"), (1, "desk")):
    v = refs["views"][vi]
    crop = [int(round(x)) for x in sheet1.crop_of(v)]
    ph = Image.open(v["image"]).convert("RGB").crop(tuple(crop))
    row = [tile(ph, f"concept {vn}")]
    for a in sys.argv[3:]:
        lb, rest = a.split("=", 1)
        m, tag = rest.split(":")
        p = f"{F}/out/{tag}_{vn}_big.png"
        if os.path.exists(p):
            row.append(tile(Image.open(p), f"{lb} dressed"))
        cam = json.loads((store.HOME / m / "human_refs.json").read_text())["cameras"][vi]
        mesh = likeness.model_mesh(store.load(m)["base"])
        im = likeness.render(mesh, cam, crop, px=T)[0]
        row.append(tile(im, f"{lb} clay"))
    rows.append(row)
W = max(len(r) for r in rows) * T
note = open(os.environ["NOTE"]).read().splitlines() if os.environ.get("NOTE") else []
H = len(rows) * T + 14 * len(note) + (10 if note else 0)
S = Image.new("RGB", (W, H), (24, 24, 24))
for i, r in enumerate(rows):
    for j, im in enumerate(r):
        S.paste(im, (j * T, i * T))
d = ImageDraw.Draw(S)
for k, line in enumerate(note):
    d.text((8, len(rows) * T + 6 + 14 * k), line, fill=(230, 230, 230))
S.save(out, quality=88)
print("wrote", out, S.size)
