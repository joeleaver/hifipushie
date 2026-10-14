"""closeups.py <model> <col>[,<col>..] [out=] [refdir=]: close-ups (hairline from the front, both temples, crown, nape)
REFERENCE | each column, where a column is <model><tag> (tiles $TOUT/s_<model><tag>_<view>.png: v0, v1, y180) at the
same crops as mksheet.py. Columns name tags: "" (the plain tiles), "_ramp", "_ss2" ..."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from hifipushie import hair, hair_read, humanfit, store

m = sys.argv[1]
cols = sys.argv[2].split(",")
kw = dict(a.split("=", 1) for a in sys.argv[3:])
OUT = os.environ["TOUT"]
RD = kw.get("refdir", "/home/joe/dev/s0urc3/docs/img/garrett_ref_full")
spec = store.load(m)
sc = hair.scalp(m, spec)
refs = json.loads((store.HOME / m / "human_refs.json").read_text())
W, H = refs["cameras"][0]["size"]
T = 440
font = ImageFont.load_default(size=20)
labels = kw.get("labels", "").split(",") if kw.get("labels") else cols


def at(view, az, el, size_mm):
    cam = refs["cameras"][int(view[1:])]
    uv = humanfit.project(cam, sc.point(np.array([az]), np.array([el]), 0.01))[0]
    eye, _ = hair_read.cam_eye(cam)
    s = size_mm / 1000.0 * cam["f"] / np.linalg.norm(sc.C - eye)
    return (uv[0] - s / 2, uv[1] - s / 2, uv[0] + s / 2, uv[1] + s / 2)


def back_box(fy):
    cam = refs["cameras"][0]
    A, E = np.meshgrid(np.arange(0, 360, 4.0), np.arange(-40, 90, 4.0))
    uv = humanfit.project(cam, sc.point(A.ravel(), E.ravel(), 0.0))
    x0, y0 = uv.min(0)
    x1, y1 = uv.max(0)
    s = 1.25 * max(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 - 0.05 * s
    b0 = (cx - s / 2, cy - s / 2)
    return (b0[0] + 0.2 * s, b0[1] + fy * s, b0[0] + 0.8 * s, b0[1] + fy * s + 0.6 * s)


rows = [("hairline (front)", "v0", at("v0", 0.0, 38.0, 95.0)), ("temple (his right)", "v0", at("v0", -55.0, 30.0, 75.0)),
        ("nape (back)", "y180", back_box(0.45))]
refimg = {"v0": Image.open(refs["views"][0]["image"]).convert("RGB"),
          "y180": Image.open(f"{RD}/garrett_head_back.png").convert("RGB").resize((W, H))}
sheet = Image.new("RGB", ((1 + len(cols)) * T, 34 + len(rows) * (T + 28)), (245, 245, 245))
d = ImageDraw.Draw(sheet)
for j, h in enumerate(["REFERENCE"] + labels):
    d.text((j * T + 6, 6), h, fill=(120, 0, 0), font=font)
y = 34
for nm, v, b in rows:
    d.text((6, y + 2), nm, fill=(0, 0, 0), font=font)
    y += 28
    def tile(c):
        p = f"{OUT}/s_{c.split(':')[0]}{c.split(':')[1]}_{v}.png" if ":" in c else f"{OUT}/s_{m}{c}_{v}.png"
        return hair_read.render_as_picture(p, (W, H)) if os.path.exists(p) else Image.new("RGB", (W, H), (90, 90, 90))
    ims = [refimg[v]] + [tile(c) for c in cols]
    for j, im in enumerate(ims):
        sheet.paste(im.crop(tuple(int(round(t)) for t in b)).resize((T, T), Image.LANCZOS), (j * T, y))
    y += T
out = kw.get("out", f"{OUT}/closeups_{m}.jpg")
sheet.save(out, quality=90)
print(out)
