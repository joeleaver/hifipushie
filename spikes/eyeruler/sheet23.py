"""sheet23.py <bare tag> <dressed tag>: er_02 (the upper lid: photo | #376 | #540 / gb_fx | result bare | result dressed
/ the lid sections' numbers) and er_03 (the reader on the photo and on two validation heads with the mesh truth in
blue, + the error table)."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import blockin_brows as bb, eye_ruler as er

G = os.environ["G"] + "/out/"
OUT = os.environ["R"] + "/"
bare, dressed = sys.argv[1], sys.argv[2]
R = json.load(open(G + "rule.json"))
mm = bb._inputs("gd_T12")["mm"]
K = 3
# ---- er_02 -----------------------------------------------------------------------------------------------------------
C = (860, 640, 1480, 1030)
Z = 2
W, H = (C[2] - C[0]) * Z, (C[3] - C[1]) * Z
HEAD, TAB = 70, 520
tiles = [("photo", "Tess photo"), ("s376", "GNM sample #376 (Joe: 'reads right')"), ("s540", "GNM sample #540 ('reads right')"),
         ("fx", "BEFORE: gb_fx"), (bare, "RESULT, the old dressing + caruncle"), (dressed, "RESULT, dressed: fold line (paint), finer lashes")]
S = Image.new("RGB", (3 * W, 2 * (H + HEAD) + TAB), "white")
d = ImageDraw.Draw(S)
for i, (tag, lab) in enumerate(tiles):
    x, y = (i % 3) * W, (i // 3) * (H + HEAD)
    im = Image.open(f"{G}s_{tag}.png").convert("RGB").crop(C).resize((W, H), Image.LANCZOS)
    S.paste(im, (x, y + HEAD))
    m = er.mean(R[tag]["read"])
    t = R[tag].get("model")
    d.text((x + 10, y + 4), lab, fill=(0, 0, 0), font_size=28)
    if t:
        mt = er.mean(t)
        pl = np.nanmean([q["platform"] for q in t], 0)
        d.text((x + 10, y + 38), f"mesh: fold {float(np.nanmedian(mt['crease'][1:6])):.1f} mm over the margin (platform shown {float(np.nanmedian(pl[1:6])):.1f}), upper lid hides {mt['cover_up']:.1f} mm of iris; "
                                 f"fold line darkness read on this image {m['crease_dark']:.2f}", fill=(0, 0, 0), font_size=19)
    else:
        d.text((x + 10, y + 38), f"read: fold line {m['crease'][3]:.1f} mm over the margin, upper lid hides {m['cover_up']:.1f} mm of iris; "
                                 f"fold line darkness {m['crease_dark']:.2f}", fill=(0, 0, 0), font_size=19)
    bx0, by0 = x + 16, y + HEAD + H - 22
    d.line([(bx0, by0), (bx0 + 10 / mm * K * Z, by0)], fill=(255, 255, 255), width=6)
    d.line([(bx0, by0), (bx0 + 10 / mm * K * Z, by0)], fill=(0, 0, 0), width=2)
    d.text((bx0 + 10 / mm * K * Z + 6, by0 - 12), "10 mm", fill=(0, 0, 0), font_size=18)
y = 2 * (H + HEAD) + 10
txt = open(G + "sheet2_notes.txt").read().splitlines() if os.path.exists(G + "sheet2_notes.txt") else []
for k, t in enumerate(txt):
    d.text((14 + (k // 18) * 1860, y + (k % 18) * 27), t, fill=(0, 0, 0), font_size=20)
S.save(OUT + "er_02_upper_lid_vs_376_540.png")
print(OUT + "er_02_upper_lid_vs_376_540.png", S.size)
# ---- er_03 -----------------------------------------------------------------------------------------------------------
ov = [("photo", "Tess photo: the reader's read (green margins, red canthi, yellow limbus circle, cyan fold line, magenta brow edge)"),
      ("s540", "validation head gk_s540, dressed, same camera: the read + the mesh's truth in blue (ring, margins at 7 columns)"),
      ("T12", "validation head gd_T12")]
ims = [Image.open(f"{G}o_{t}.png") for t, _ in ov]
w, h = ims[0].size
TW = 1250
S = Image.new("RGB", (w + TW, 3 * (h + 34)), "white")
d = ImageDraw.Draw(S)
for i, ((t, lab), im) in enumerate(zip(ov, ims)):
    d.text((8, i * (h + 34) + 4), lab, fill=(0, 0, 0), font_size=20)
    S.paste(im, (0, i * (h + 34) + 32))
txt = open(G + "sheet3_notes.txt").read().splitlines() if os.path.exists(G + "sheet3_notes.txt") else []
for k, t in enumerate(txt):
    d.text((w + 16, 8 + k * 25), t, fill=(0, 0, 0), font_size=19)
S.save(OUT + "er_03_eye_ruler_validation.png")
print(OUT + "er_03_eye_ruler_validation.png", S.size)
