"""sheet.py: fr_01 (how the ruler reads: a target's pictures with the model's outline and the reads) and fr_02 (three
driven pairs: TARGET | the Claude driver with the picture ruler | the ruler's 8 largest gaps applied blindly | START)."""
import json
import os

import numpy as np
from PIL import Image, ImageDraw

import arms
import drv
import gnmc
from hifipushie import face_ruler as fr

G, R = os.environ["G"], os.environ["R"]


def pair(case):
    h = json.loads((drv.HIDDEN / f"{case}.json").read_text())
    st = json.loads((drv.CASES / case / "state.json").read_text())
    return np.array(h["A"]), np.array(h["B"]), np.array(st["c"]), h


# ---- fr_01
cA, cB, _, h = pair("s6_03")
A = fr.gnm_head(cA)
views = arms.pictures(cB)
res = fr.read(A, views, rounds=1)
tiles = []
for v in views:
    im = v["img"].copy()
    d = ImageDraw.Draw(im)
    _, ps = fr.clay(A, v["cam"], passes=True)
    d.line([tuple(p) for p in fr._curve(ps["part"] >= 0)], fill=(0, 200, 0), width=2)
    for ob in res["obs"]:
        if ob["view"] != v["kind"]:
            continue
        if ob["type"] == "outline":
            d.line([tuple(ob["p"]), tuple(ob["q"])], fill=(255, 220, 0), width=1)
        else:
            for q, col in ((ob["q"], (255, 0, 255)), (ob["p"], (0, 255, 255))):
                d.ellipse([q[0] - 5, q[1] - 5, q[0] + 5, q[1] + 5], outline=col, width=2)
    tiles.append(im.resize((440, 440), Image.LANCZOS))
S = gnmc.grid([tiles], cols_labels=["front", "3/4", "profile"],
              title="fr_01 the face ruler reading s6_03 (nose): TARGET's pictures; green = the model's outline through the same camera, "
                    "yellow = outline reads, magenta / cyan = pupil, lip, brow reads (picture / model)", lw=0)
S.save(f"{R}/fr_01_ruler_reads.png")
rows = sorted(fr.read(A, views)["gaps"], key=lambda r: -abs(r["sd"]))[:6]
print("fr_01 top rows:", [(r["measure"], round(r["gap"], 1)) for r in rows])

# ---- fr_02
PX = 230


def cell(c, cB):
    ims = drv.view_imgs(c, cB, "head", px=PX, views=["front", "profile"])
    W = Image.new("RGB", (2 * PX, PX), "white")
    W.paste(ims[0], (0, 0))
    W.paste(ims[1], (PX, 0))
    return W


ar = json.load(open(f"{G}/out/arms_s6.json"))
rs = json.load(open(f"{G}/out/rescore_s6.json"))
rws, labs = [], []
for case in ("s6_03", "s6_07", "s6_05"):
    cA, cB, c, h = pair(case)
    c8 = arms.apply(cA, ar[case]["pic"], 8)
    rws.append([cell(cB, cB), cell(c, cB), cell(c8, cB), cell(cA, cB)])
    dr, b8 = rs[case]["driver"], ar[case]["pic:top8"]
    labs.append(f"{case}\n{'+'.join(x['region'] for x in h['changes'])}\ndriver {dr['region']:.2f}/{dr['id']:.2f}\n{'PASS' if dr['pass'] else 'fail'}\n"
                f"blind {b8['region']:.2f}/{b8['id']:.2f}\n{'PASS' if b8['pass'] else 'fail'}")
S = gnmc.grid(rws, cols_labels=["TARGET (front | profile)", "Claude driver + picture ruler", "ruler's 8 largest gaps, blind", "START"],
              rows_labels=labs, title="fr_02 set s6: region closed / ID closed", lw=130)
S.save(f"{R}/fr_02_s6_drive.png")
print("saved")
