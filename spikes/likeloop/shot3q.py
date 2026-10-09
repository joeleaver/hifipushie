"""shot3q.py <model> <tag> <out.jpg> [eyes|mouth|head]: the dressed head through the desk painting's fitted camera
(view 1), beside the painting's same crop: the region from the painting's points, 2x."""
import os
import sys

import numpy as np
from PIL import Image

import shot
import sheet1
import stage

L = os.environ["L"]
name, tag, out = sys.argv[1:4]
reg = sys.argv[4] if len(sys.argv) > 4 else "head"
vs, cams = sheet1.cameras(name)
crop = sheet1.crop_of(vs[1])
fr = stage.fitted_frame(cams[1], crop, "three_quarter")
f = f"{L}/out/{tag}_3q_big.png"
if not os.path.exists(f):
    im = stage.shoot(name, [fr], shot.light(), size=shot.BIG, hair_on=True)["three_quarter"]
    im.save(f)
im = Image.open(f).convert("RGB")
pic = Image.open(vs[1]["image"]).convert("RGB")
pts = vs[1]["points"]
U = np.array(list(pts.values()), float)
lo, hi = U.min(0), U.max(0)
if reg == "head":
    box = (crop[0], crop[1], crop[2], crop[3])
else:
    rng = range(17, 48) if reg == "eyes" else range(31, 68)
    keys = [k for k in pts if k.startswith("lm") and k[2:].isdigit() and int(k[2:]) in rng and (reg == "eyes" or int(k[2:]) >= 48 or int(k[2:]) <= 35)]
    Q = np.array([pts[k] for k in keys], float)
    c, s = Q.mean(0), 0.75 * float(np.ptp(Q, 0).max()) + 0.08 * float((hi - lo).max())
    box = (c[0] - s, c[1] - 0.6 * s, c[0] + s, c[1] + 0.6 * s)
sc = im.size[0] / (crop[2] - crop[0])
W = 640
h = int(W * (box[3] - box[1]) / (box[2] - box[0]))
a = pic.transform((W, h), Image.EXTENT, box, Image.BICUBIC)
b = im.transform((W, h), Image.EXTENT, tuple((np.array(box) - [crop[0], crop[1], crop[0], crop[1]]) * sc), Image.BICUBIC)
S = Image.new("RGB", (2 * W, h))
S.paste(a, (0, 0))
S.paste(b, (W, 0))
S.save(out, quality=88)
print("wrote", out)
