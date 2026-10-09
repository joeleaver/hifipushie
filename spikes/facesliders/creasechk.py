"""creasechk.py <out.png> <model> [model ...]: eye_crease_depth 0 / 0.8 / 1.5 on each model's head through its photo's
camera and fitted light (clay, likeness_pair.matched), the eyes cropped at 2x; prints where the crease sits on that
head (its own fold turn, mm over the margin, per u band) against the template's 6.2 mm."""
import copy
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import base as basemod
from hifipushie import faceslide, likeness_eyes as le
from hifipushie import likeness_pair as lp
from hifipushie import onemesh, store

rows = []
for name in sys.argv[2:]:
    b0 = copy.deepcopy(store.load(name)["base"])
    ht = onemesh.head_template(b0)
    V = np.asarray(ht["carry"]["V"], float)  # (its GNM-frame head, close to what the sliders see)
    T = faceslide.head_template(V)
    X = T["X"]
    lm = T["lm"]
    c_in, c_out = lm[42], lm[45]
    faceslide._left_fields(T)
    Hc, H0, u, up_ = faceslide._CACHE["last_crease"]
    bands = [(a, a + 0.15) for a in (0.15, 0.3, 0.45, 0.6, 0.75)]
    print(name, "crease over the margin, mm (own | template) per u band:",
          [(round(1000 * float(np.median(np.atleast_1d(Hc)[(u >= a) & (u < b) & up_])), 1) if np.ndim(Hc) else round(1000 * float(np.median(H0[(u >= a) & (u < b) & up_])), 1),
            round(1000 * float(np.median(H0[(u >= a) & (u < b) & up_])), 1)) for a, b in bands])
    tiles = []
    for v in (0.0, 0.8, 1.5):
        b = copy.deepcopy(b0)
        b["head"].setdefault("sliders", {})["eye_crease_depth"] = v
        m = lp.matched(name, b, face_id=False)
        img = (m["clay"] if os.environ.get("CLAY") else (m.get("render") or m["clay"])).convert("RGB")  # (CLAY=1: the key light from the upper left, rakes the lid)
        P = np.asarray(m["md"]["side"].P, float)
        k = img.size[0] / (m["box"][2] - m["box"][0])
        x0, y0, x1, y1 = le.eye_box(P)
        q = lambda p: ((np.asarray(p) - np.array(m["box"][:2])) * k)  # noqa: E731
        t = img.crop(tuple(int(round(z)) for z in (*q((x0, y0 + 0.3 * (y1 - y0))), *q((x1, y1 - 0.15 * (y1 - y0))))))
        t = t.resize((600, int(600 * t.size[1] / t.size[0])))
        ImageDraw.Draw(t).text((6, 4), f"{name} crease_depth {v}", fill=(255, 0, 0))
        tiles.append(t)
    rows.append(tiles)
W, H = 600, max(t.size[1] for r in rows for t in r)
S = Image.new("RGB", (3 * W, H * len(rows)), (255, 255, 255))
for i, r in enumerate(rows):
    for j, t in enumerate(r):
        S.paste(t, (j * W, i * H))
S.save(sys.argv[1])
print(sys.argv[1], S.size)
