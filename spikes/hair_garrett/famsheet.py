"""famsheet.py <model> [prev=<model>] [out=] [title=]: REFERENCE | model | prev for heads with two fitted views (front v0,
side v1) and no back pictures: the two views whole, then close-ups at the same crop in reference and renders: hairline
and parting (front), both temples (front), the side's lengths and ends (side view, below the ear). Tiles from
$TOUT/s_<model>_v<i>.png (hgshots.py)."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from hifipushie import hair, hair_read, humanfit, store

m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
OUT = os.environ["TOUT"]
prev = kw.get("prev")
spec = store.load(m)
sc = hair.scalp(m, spec)
refs = json.loads((store.HOME / m / "human_refs.json").read_text())
T = 500
font = ImageFont.load_default(size=22)


def size(i):
    return refs["cameras"][i]["size"]


def tile(model, i):
    p = f"{OUT}/s_{model}_v{i}.png"
    return hair_read.render_as_picture(p, size(i)) if os.path.exists(p) else None


def ref(i):
    return Image.open(refs["views"][i]["image"]).convert("RGB")


def head_box(i, pad=1.7, down=0.18):
    cam = refs["cameras"][i]
    A, E = np.meshgrid(np.arange(0, 360, 4.0), np.arange(-40, 90, 4.0))
    uv = humanfit.project(cam, sc.point(A.ravel(), E.ravel(), 0.0))
    x0, y0 = uv.min(0)
    x1, y1 = uv.max(0)
    s = pad * max(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 + down * s
    return (cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2)


def at(i, az, el, size_mm, h=0.01, dz=0.0):
    cam = refs["cameras"][i]
    P = sc.point(np.array([az]), np.array([el]), h) + np.array([0, 0, dz])
    uv = humanfit.project(cam, P)[0]
    eye, _ = hair_read.cam_eye(cam)
    s = size_mm / 1000.0 * cam["f"] / np.linalg.norm(sc.C - eye)
    return (uv[0] - s / 2, uv[1] - s / 2, uv[0] + s / 2, uv[1] + s / 2)


def crop(im, box):
    if im is None:
        im = Image.new("RGB", (10, 10), (60, 60, 60))
    return im.crop(tuple(int(round(v)) for v in box)).resize((T, T), Image.LANCZOS)


side_az = 90.0 if refs["cameras"][1].get("yaw", refs["views"][1].get("yaw", 90)) >= 0 else -90.0
rows = []
for i, nm in ((0, "front"), (1, "side")):
    b = head_box(i)
    rows.append((nm, [crop(ref(i), b), crop(tile(m, i), b)] + ([crop(tile(prev, i), b)] if prev else [])))
for nm, i, b in (("hairline and parting (front)", 0, at(0, 0.0, 45.0, 110.0)),
                 ("temple (picture left)", 0, at(0, -60.0, 20.0, 90.0)),
                 ("temple (picture right)", 0, at(0, 60.0, 20.0, 90.0)),
                 ("side: lengths and ends", 1, at(1, side_az * 1.5, -20.0, 160.0, dz=-0.07))):
    rows.append((nm, [crop(ref(i), b), crop(tile(m, i), b)] + ([crop(tile(prev, i), b)] if prev else [])))
heads = ["REFERENCE", m] + ([prev] if prev else [])
sheet = Image.new("RGB", (len(heads) * T, 40 + len(rows) * (T + 30)), (245, 245, 245))
d = ImageDraw.Draw(sheet)
d.text((8, 8), kw.get("title", f"{m}: REFERENCE | ours" + (f" | {prev}" if prev else "")) + "   (EEVEE strands)", fill=(0, 0, 0), font=font)
for j, h in enumerate(heads):
    d.text((j * T + 8, 40), h, fill=(120, 0, 0), font=font)
y = 40
for nm, ims in rows:
    y += 30
    for j, im in enumerate(ims):
        sheet.paste(im, (j * T, y))
    d.text((8, y - 26), nm, fill=(0, 0, 0), font=font)
    y += T
out = kw.get("out", f"{OUT}/sheet_{m}.jpg")
sheet.save(out, quality=88)
print(out)
