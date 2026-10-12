"""foldover.py <model> [view=0]: the folds' landmark paths (yellow) and, per station, the picture's valley (red where it
passes the threshold, grey where not) and ours (blue), drawn over the picture's crop at 3x. -> $G/out/fo_<model>_<view>.png"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw
from hifipushie import skin_read as sr, skin_folds as sf, skin as skinmod, humanfit, store

m = sys.argv[1]
vi = int(sys.argv[2]) if len(sys.argv) > 2 else 0
K = 3
f = sr.capture(m, views=[vi], log=lambda s: None)[0]
st = sr.stage_spec(store.load(m))
J = skinmod._joints(st)
nominal = sf.paths(st, "body", J, None)
im = Image.fromarray((np.clip(sr._srgb(f["P"]), 0, 1) * 255).astype(np.uint8)).resize((sr.N * K, sr.N * K), Image.LANCZOS)
d = ImageDraw.Draw(im)
box = f["box"]; k = sr.N / (box[2] - box[0])
for (name, sd), q in nominal.items():
    fd = sf.FOLDS[name]
    p0 = (humanfit.project(f["cam"], q["P"]) - np.asarray(box[:2])) * k
    v = (humanfit.project(f["cam"], q["P"] + 0.001 * q["across"]) - np.asarray(box[:2])) * k - p0
    d.line([tuple(p * K) for p in p0], fill=(255, 230, 0), width=1)
    r = sr._fold_view(f, q, fd)
    if r is None:
        continue
    for i in range(0, len(p0), 2):
        if not r["valid"][i]:
            continue
        for key, col in (("ours", (60, 120, 255)), ("picture", (255, 40, 40))):
            if r[key][i] >= sr.FOLD_T:
                x, y = (p0[i] + r[key + "_u"][i] * v[i]) * K
                d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=col)
    d.text(tuple(p0[len(p0) // 2] * K + 6), name + sd, fill=(255, 255, 0))
out = f"{os.environ['G']}/out/fo_{m}_{vi}.png"
im.save(out); print(out)
