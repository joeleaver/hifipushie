"""skintone.py <model> [views=v0,v1] [tag=]: the SKIN-TONE sanity row on a hair sheet (2026-10-18, Joe: "last one I saw he
was very dark-skinned"). Median Lab (linear median -> Lab, as spikes/projskin/skincheck.py) in the skin thread's boxes
(forehead, cheek_R, cheek_L from MediaPipe landmarks of the PHOTO; the render is at the photo camera, so the same box)
on the photo and on our tile $TOUT/s_<model><tag>_<view>.png. Row passes when |dL| <= 5 on every box (tone within ~5 L
of the photo / the skin thread's render, whose garrett_g14 values are printed beside). LIGHT."""
import json
import os
import sys

import numpy as np
from PIL import Image

from hifipushie import hair_read, likeness, store
from hifipushie import skin_project as sp

m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
OUT = os.environ["TOUT"]
TAG = kw.get("tag", "")
refs = json.loads((store.HOME / m / "human_refs.json").read_text())
W, H = refs["cameras"][0]["size"]
SKIN = "/mnt/data/hifipushie/projskin/out/private/gate/garrett_g14/skincheck.json"


def bbox(P, ids, dx=0.0, dy=0.0, w=None, h=None):
    q = P[list(ids)]
    c = (q.min(0) + q.max(0)) / 2 + [dx, dy]
    return [c[0] - w / 2, c[1] - h / 2, c[0] + w / 2, c[1] + h / 2]


def lab_box(im, box):
    a = np.asarray(im.crop(tuple(int(round(x)) for x in box)), float) / 255.0
    return sp.lab(np.median(sp._lin(a.reshape(-1, 3)), 0)[None])[0]


skin = {}
if os.path.exists(SKIN):
    for r in json.load(open(SKIN)):
        if r["item"].startswith("tone "):
            skin[r["item"].split()[1]] = r["ours"]
rows, ok = [], True
for v in kw.get("views", "v0,v1").split(","):
    R = Image.open(refs["views"][int(v[1:])]["image"]).convert("RGB")
    p = f"{OUT}/s_{m}{TAG}_{v}.png"
    if not os.path.exists(p):
        print("missing", p)
        continue
    O = hair_read.render_as_picture(p, (W, H)).convert("RGB")
    PR = np.asarray(likeness.detect([R])[0], float)[:, :2]
    u = float(np.linalg.norm(PR[33] - PR[263])) / 60.0
    B = {"forehead": bbox(PR, (9, 107, 336), w=24 * u, h=10 * u, dy=-8 * u),
         "cheek_R": bbox(PR, (116, 123, 147, 50), w=14 * u, h=14 * u),
         "cheek_L": bbox(PR, (345, 352, 376, 280), w=14 * u, h=14 * u)}
    for k, b in B.items():
        lr, lo = lab_box(R, b), lab_box(O, b)
        good = abs(lo[0] - lr[0]) <= 5.0
        if k.startswith("hair") or (lr[1] ** 2 + lr[2] ** 2) ** 0.5 < 5:  # info only / not skin in this view (backdrop)
            good = None
        else:
            ok &= good
        rows.append(f"| skin tone {v} {k} (Lab) | {np.round(lr, 1).tolist()} | {np.round(lo, 1).tolist()} | dL {lo[0] - lr[0]:+.1f} | "
                    f"{'info' if good is None else 'PASS' if good else 'FAIL'} | skin thread {skin.get(k, '-') if v == 'v0' else '-'} |")
print("| item | photo | ours | diff | pass (|dL| <= 5) | skin thread render (v0) |")
print("\n".join(rows))
print("SKIN TONE ROW", "PASS" if ok else "FAIL")
