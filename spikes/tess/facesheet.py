"""facesheet.py <model> <out png> [title]: the face sheet on S0urc3's approved head set. One row per reference view
(front, three-quarter, profile): reference | ours through its fitted camera | 50/50 overlay, the same square crop of
the picture; then a front close-up row (eyes to chin). Skin as stored, stage.FRONT_LIGHT at EXPO (default -0.1)."""
import json, os, sys

import numpy as np
from PIL import Image, ImageDraw

import stage
from hifipushie import store

name, out = sys.argv[1], sys.argv[2]
title = sys.argv[3] if len(sys.argv) > 3 else name
refs = json.loads((store.HOME / name / "human_refs.json").read_text())
LIGHT = {**stage.FRONT_LIGHT, "exposure": float(os.environ.get("EXPO", "-0.1"))}
PX = 640
boxes, frames, imgs = [], [], []
for i, (v, cam) in enumerate(zip(refs["views"], refs["cameras"])):
    U = np.array(list(v["points"].values()), float)
    lo, hi = U.min(0), U.max(0)
    yaw = abs(float(v.get("yaw", 0)))
    side = (2.3 if yaw < 60 else 3.4) * max(hi - lo)
    c = 0.5 * (lo + hi) + np.array([side * (0.0 if yaw < 30 else 0.08 if yaw < 60 else 0.2), -side * 0.04])
    box = [c[0] - side / 2, c[1] - side / 2, c[0] + side / 2, c[1] + side / 2]
    boxes.append(box)
    frames.append(stage.fitted_frame(cam, box, f"v{i}"))
    imgs.append(Image.open(v["image"]).convert("RGB"))
# the close-up: the front picture from the brows to the chin
U = np.array(list(refs["views"][0]["points"].values()), float)
lo, hi = U.min(0), U.max(0)
s = 0.95 * (hi - lo)[0]
c = np.array([0.5 * (lo[0] + hi[0]), lo[1] + 0.55 * (hi[1] - lo[1])])
zb = [c[0] - s / 2, c[1] - s / 2, c[0] + s / 2, c[1] + s / 2]
boxes.append(zb)
frames.append(stage.fitted_frame(refs["cameras"][0], zb, "zoom"))
imgs.append(imgs[0])
shots = stage.shoot(name, frames, LIGHT, size=PX, hair_on=os.environ.get("HAIR") == "1")


def lab(im, t):
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 7 * len(t) + 12, 18], fill=(20, 20, 20))
    d.text((6, 3), t, fill=(255, 255, 255))
    return im


names = ["front", "three-quarter (director's pick)", "true left profile", "front close-up"]
rows = []
for i, f in enumerate(frames):
    ref = imgs[i].crop(tuple(int(round(x)) for x in boxes[i])).resize((PX, PX), Image.LANCZOS)
    ours = shots[f["name"]].resize((PX, PX))
    row = Image.new("RGB", (PX * 3, PX), (230, 230, 230))
    row.paste(lab(ref.copy(), f"reference: {names[i]}"), (0, 0))
    row.paste(lab(ours, "ours, its fitted camera"), (PX, 0))
    row.paste(lab(Image.blend(ref, shots[f["name"]].resize((PX, PX)), 0.5), "50/50 overlay"), (2 * PX, 0))
    rows.append(row)
S = Image.new("RGB", (PX * 3, PX * len(rows) + 28), (240, 240, 240))
ImageDraw.Draw(S).text((8, 8), title, fill=(0, 0, 0))
for i, r in enumerate(rows):
    S.paste(r, (0, 28 + PX * i))
S.save(out)
S.resize((S.width // 2, S.height // 2), Image.LANCZOS).save(out.replace(".png", "_half.png"))
print("saved", out, S.size)
