"""phcrop.py <model> <out>: the model's front photo cropped like dress.py's frame (84 mm wide at the 11.7 mm iris, centred
12 mm... above the eyes' centre as dress.py: +3 mm up), square, 1600 px."""
import json, sys
import numpy as np
from PIL import Image
from hifipushie import likeness, store
rj = json.loads((store.HOME / sys.argv[1] / "human_refs.json").read_text())
im = Image.open(rj["views"][0]["image"]).convert("RGB")
P = np.asarray(likeness.detect([im])[0], float)
ir = []
for c0 in (468, 473):
    pts = P[c0 + 1:c0 + 5, :2]
    ir.append(0.5 * (np.linalg.norm(pts[0] - pts[2]) + np.linalg.norm(pts[1] - pts[3])))
mmpx = 11.7 / np.mean(ir)
cen = 0.5 * (P[468, :2] + P[473, :2]) - [0, 3.0 / mmpx]
half = 42.0 / mmpx
box = (cen[0] - half, cen[1] - half, cen[0] + half, cen[1] + half)
im.crop(tuple(int(round(v)) for v in box)).resize((1600, 1600), Image.LANCZOS).save(sys.argv[2])
print("mm/px", mmpx, box)
