"""flowcmp.py <model> [out.png] [view=0]: the groom's front locks (the tie's first gather row and any drape row) projected
through the model's fitted camera onto her photo, beside her traced flow (tess's trace_<view>.json: curtain strokes,
part, face hull) and the hairline (hair.hairline). Root = a dot. The trace method for the front: our lock spines
against her strand flow over the forehead band.
Env T = tess's trace dir (/mnt/data/hifipushie/tess)."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import hair, humanfit, store

name = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else f"{os.environ.get('F', '/mnt/data/hifipushie/faces2')}/out/flow_{name}.png"
vi = int(sys.argv[3]) if len(sys.argv) > 3 else 0
T = os.environ.get("T", "/mnt/data/hifipushie/tess")
TR = {0: "trace_front", 1: "trace_tq", 2: "trace_profile"}[vi]
tr = json.load(open(f"{T}/{TR}.json"))
sp = store.load(name)
refs = json.loads((store.HOME / name / "human_refs.json").read_text())
cam = refs["cameras"][vi]
sc = hair.scalp(name, sp)
g = hair.groom_params(sp)
line = hair.hairline(sc, g)
im = Image.open(tr["photo"]).convert("RGB")
d = ImageDraw.Draw(im)
for k, pts in (tr.get("flow") or {}).items():
    d.line([tuple(p) for p in pts], fill=(255, 220, 0), width=5)
if tr.get("part"):
    d.line([tuple(p) for p in tr["part"]], fill=(255, 220, 0), width=5)
d.line([tuple(p) for p in tr["face_hull"]] + [tuple(tr["face_hull"][0])], fill=(0, 255, 255), width=2)
a = np.arange(0.0, 360.0, 1.0)
L = sc.point(a, line, 0.0)
U = humanfit.project(cam, L)
fwd = np.abs(((a + 180) % 360) - 180) < 100
d.line([tuple(p) for p in U[fwd]], fill=(255, 255, 255), width=2)
for n, lk in (sp["hair"].get("locks") or {}).items():
    if lk.get("space") == "xyz" or not (n.startswith("tg0_") or n.startswith("td")):
        continue
    P = hair.lock_world(sc, lk, lk["pts"])
    if np.abs(((P[0] - sc.C)[0])) > 0.09:
        continue
    Q = humanfit.project(cam, P)
    if vi == 0:  # (the front view: only the part of the lock on the front of the head; the rest runs behind it)
        azs = np.array([abs(((float(p[0]) + 180) % 360) - 180) for p in lk["pts"]])
        Q = Q[: max(2, int(np.argmax(azs > 80)) if (azs > 80).any() else len(Q))]
    col = (255, 60, 60) if n.startswith("tg0_") else (60, 120, 255)
    d.line([tuple(p) for p in Q], fill=col, width=3)
    d.ellipse([Q[0][0] - 5, Q[0][1] - 5, Q[0][0] + 5, Q[0][1] + 5], fill=col)
box = (150, 100, 900, 700) if vi == 0 else (100, 100, 900, 800)
im.crop(box).resize((560, int(560 * (box[3] - box[1]) / (box[2] - box[0])))).save(out)
print("wrote", out)
