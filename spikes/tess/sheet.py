"""sheet.py <model> <out png> [FACE=1] [title]: Tess stage sheet. Row 1: v5 | ours (clay, same framing) | blend,
then v4 | ours. Row 2: the face: v5 crop | ours through its fitted camera | v4 crop | ours through its camera.
The figure camera is v5's framing: a long lens (8 m), the crown at px 92 and the floor at 1402 of 1536."""
import json, math, os, sys

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import server, store

T = os.environ["T"]
REF = "/home/joe/dev/s0urc3/docs/img/tess_ref_full/"
name, out = sys.argv[1], sys.argv[2]
title = sys.argv[4] if len(sys.argv) > 4 else name
FACE = os.environ.get("FACE", "1") == "1"
STAT = float(os.environ.get("STAT", "1.65"))
H = 1536
CROWN, FLOOR = 92.0, 1402.0           # v5: vertex and floor (sole bottom minus ~2 cm of shoe) in px
DIST = 8.0
mpp = STAT / (FLOOR - CROWN)          # metres a pixel at the figure
zc = (FLOOR - H / 2) * mpp            # world z at the picture's centre
fov = math.degrees(2 * math.atan(H * mpp / 2 / DIST))


def fig_render(nm):
    cam = {"eye": [0.0, -DIST, zc], "target": [0.0, 0.0, zc], "fov": fov, "name": "v5"}
    r = server.look(nm, size=H, camera=cam, resolution=int(os.environ.get("RES", "300")))
    im = Image.open(__import__("io").BytesIO(next(x for x in r if not isinstance(x, str)).data)).convert("RGB")
    # the look panel may carry a margin/title: find the square panel by size
    if im.size != (H, H):
        im = im.resize((H, H))
    x0 = (H - 1056) // 2
    return im.crop((x0, 0, x0 + 1056, H))


def label(im, t):
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 8 * len(t) + 10, 18], fill=(20, 20, 20))
    d.text((5, 3), t, fill=(255, 255, 255))
    return im


v5 = Image.open(REF + "tess_headturn_v5_8ab06ebb.png").convert("RGB")
v4 = Image.open(REF + "tess_apose_v4_70110ef2.png").convert("RGB")
ours = fig_render(name)
blend = Image.blend(v5, ours, 0.5)
row1 = [label(v5.copy(), "reference v5"), label(ours, f"ours {title}"), label(blend, "blend"), label(v4.copy(), "reference v4")]
W1 = sum(i.width for i in row1)
sheet_rows = [row1]
if FACE:
    import stage
    refs = json.loads((store.HOME / name / "human_refs.json").read_text())
    crops = [("v5_face_x3.png", refs["cameras"][0]), ("v4_face_x3.png", refs["cameras"][1])]
    frames = [stage.fitted_frame(c, [0, 0, 900, 900], f"f{i}") for i, (_, c) in enumerate(crops)]
    shots = stage.shoot(name, frames, stage.FRONT_LIGHT, size=900, hair_on=False)
    row2 = []
    for i, (f, _) in enumerate(crops):
        row2 += [label(Image.open(T + "/ref/" + f).convert("RGB"), f"reference {f[:2]} (x3 crop)"),
                 label(shots[f"f{i}"], "ours, fitted camera")]
    sheet_rows.append(row2)
scale = 0.5
rows = []
for r in sheet_rows:
    w = sum(i.width for i in r)
    h = max(i.height for i in r)
    im = Image.new("RGB", (w, h), (235, 235, 235))
    x = 0
    for p in r:
        im.paste(p, (x, 0))
        x += p.width
    rows.append(im)
W = max(r.width for r in rows)
rows = [r.resize((W, int(r.height * W / r.width))) for r in rows]
S = Image.new("RGB", (W, sum(r.height for r in rows) + 30), (235, 235, 235))
ImageDraw.Draw(S).text((10, 8), f"Tess stage sheet: {title}", fill=(0, 0, 0))
y = 30
for r in rows:
    S.paste(r, (0, y))
    y += r.height
S = S.resize((int(S.width * scale), int(S.height * scale)), Image.LANCZOS)
S.save(out)
print("saved", out, S.size)
