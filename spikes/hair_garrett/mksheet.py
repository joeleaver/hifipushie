"""mksheet.py <model> [prev=<model>] [refdir=<dir>] [out=<png>] [title=..]: REFERENCE | <model> | <prev> rows: front,
three-quarter, profile (fitted cameras: same pixels), back three-quarter and back (the front camera turned; the
pictures are not fitted: same framing only), then close-ups at the same crop in reference and render: hairline (front),
temple (three-quarter), crown and nape (back). Tiles from $TOUT/s_<model>_<view>.png (hgshots.py)."""
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
RD = kw.get("refdir", "/home/joe/dev/s0urc3/docs/img/garrett_ref_full")
BACKS = {"y125": kw.get("ref_y125", f"{RD}/garrett_head_three_quarter_rear.png"), "y180": kw.get("ref_y180", f"{RD}/garrett_head_back.png")}
spec = store.load(m)
sc = hair.scalp(m, spec)
refs = json.loads((store.HOME / m / "human_refs.json").read_text())
W, H = refs["cameras"][0]["size"]
T = 520  # tile px
font = ImageFont.load_default(size=22)


def tile(model, view):
    p = f"{OUT}/s_{model}_{view}.png"
    if not os.path.exists(p):
        return None
    return hair_read.render_as_picture(p, (W, H))


def ref(view):
    if view[0] == "v":
        return Image.open(refs["views"][int(view[1:])]["image"]).convert("RGB")
    p = BACKS.get(view)
    return Image.open(p).convert("RGB").resize((W, H)) if p and os.path.exists(p) else None


def head_box(view, pad=1.25):
    """The head's square in picture pixels: the scalp projected (fitted views), else the middle top of the frame."""
    if view[0] == "v":
        cam = refs["cameras"][int(view[1:])]
        A, E = np.meshgrid(np.arange(0, 360, 4.0), np.arange(-40, 90, 4.0))
        uv = humanfit.project(cam, sc.point(A.ravel(), E.ravel(), 0.0))
        x0, y0 = uv.min(0)
        x1, y1 = uv.max(0)
    else:
        cam = refs["cameras"][0]
        A, E = np.meshgrid(np.arange(0, 360, 4.0), np.arange(-40, 90, 4.0))
        uv = humanfit.project(cam, sc.point(A.ravel(), E.ravel(), 0.0))
        x0, y0 = uv.min(0)
        x1, y1 = uv.max(0)
    s = pad * max(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 - 0.05 * s
    return (cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2)


def at(view, az, el, h=0.01, size_mm=75.0):
    cam = refs["cameras"][int(view[1:])]
    uv = humanfit.project(cam, sc.point(np.array([az]), np.array([el]), h))[0]
    from hifipushie import hair_read as hr
    eye, _ = hr.cam_eye(cam)
    d = np.linalg.norm(sc.C - eye)
    s = size_mm / 1000.0 * cam["f"] / d
    return (uv[0] - s / 2, uv[1] - s / 2, uv[0] + s / 2, uv[1] + s / 2)


def crop(im, box):
    if im is None:
        im = Image.new("RGB", (W, H), (60, 60, 60))
    return im.crop(tuple(int(round(v)) for v in box)).resize((T, T), Image.LANCZOS)


rows = []
for v, nm in (("v0", "front"), ("v1", "three-quarter"), ("v2", "profile"), ("y125", "back three-quarter"), ("y180", "back")):
    b = head_box(v)
    rows.append((nm + ("" if v[0] == "v" else " (picture not fitted)"), [crop(ref(v), b), crop(tile(m, v), b)]
                 + ([crop(tile(prev, v), b)] if prev else [])))
# close-ups (same crop on reference and renders)
hl = [e for a, z, e, n in [] ]
cl = [("hairline (front)", "v0", at("v0", 0.0, 38.0, size_mm=95.0)),
      ("temple (his left)", "v1", at("v1", 62.0, 28.0, size_mm=75.0)),
      ("temple (his right)", "v0", at("v0", -55.0, 30.0, size_mm=75.0))]
if kw.get("direction", "1") == "1":  # tight top-front crops where strand LINES show (the blind review contradicted itself
    # on comb direction from whole-head pairs, Garrett G6-G9): the three-quarter and the profile, front of the top
    cl += [("direction (three-quarter, top-front)", "v1", at("v1", float(kw.get("dir_az1", 30.0)), 60.0, size_mm=85.0)),
           ("direction (profile, top-front)", "v2", at("v2", float(kw.get("dir_az2", 45.0)), 58.0, size_mm=85.0))]
for nm, v, b in cl:
    rows.append((nm, [crop(ref(v), b), crop(tile(m, v), b)] + ([crop(tile(prev, v), b)] if prev else [])))
for nm, v, fy in (("crown (back)", "y180", (0.0, 0.5)), ("nape (back)", "y180", (0.45, 0.95))):
    b0 = head_box(v)
    s = b0[2] - b0[0]
    b = (b0[0] + 0.2 * s, b0[1] + fy[0] * s, b0[0] + 0.8 * s, b0[1] + fy[0] * s + 0.6 * s)
    rows.append((nm, [crop(ref(v), b), crop(tile(m, v), b)] + ([crop(tile(prev, v), b)] if prev else [])))
if kw.get("pairs"):  # the gates' LOOK step (docs/notes/gates.md): each region's reference and result crop as files
    pd = kw["pairs"]
    os.makedirs(pd, exist_ok=True)
    for nm, ims in rows:
        slug = "".join(ch if ch.isalnum() else "_" for ch in nm.split(" (picture")[0]).strip("_")
        ims[0].save(f"{pd}/{slug}_ref.png")
        ims[1].save(f"{pd}/{slug}_res.png")
        print("PAIR", nm.split(" (picture")[0], f"{pd}/{slug}_ref.png", f"{pd}/{slug}_res.png")
ncol = max(len(r[1]) for r in rows)
heads = ["REFERENCE", m] + ([prev] if prev else [])
sheet = Image.new("RGB", (ncol * T, 40 + len(rows) * (T + 30)), (245, 245, 245))
d = ImageDraw.Draw(sheet)
d.text((8, 8), kw.get("title", f"{m}: REFERENCE | ours" + (f" | {prev}" if prev else "")) + "   (EEVEE strands)", fill=(0, 0, 0), font=font)
for j, h in enumerate(heads):
    d.text((j * T + 8, 40), h, fill=(120, 0, 0), font=font)
y = 40
for nm, ims in rows:
    d.text((8, y + 4 + 0), "", fill=(0, 0, 0))
    y += 30
    for j, im in enumerate(ims):
        sheet.paste(im, (j * T, y))
    d.text((8, y - 26), nm, fill=(0, 0, 0), font=font)
    y += T
out = kw.get("out", f"{OUT}/sheet_{m}.jpg")
sheet.save(out, quality=88)
print(out)
