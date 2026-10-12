"""jdbg.py <model> <view index>: the jaw contour's stages on the model's own clay (counts; a picture of the contour)."""
import sys
import numpy as np
from PIL import Image, ImageDraw
from hifipushie import blockin as bi, face_ruler as fr, store
m, vi = sys.argv[1], int(sys.argv[2])
spec, rj = store.load(m), bi._refs(m)
head = fr.model_head(spec)
cam = rj["cameras"][vi]
print("jaw set", int(fr._jaw_set(head).sum()), "of", len(head["V"]), "head F", len(head["F"]))
E, t, X, p, n2 = fr.jaw_contour(head, cam)
print("contour points", len(E))
im, ps = fr.clay(head, cam, passes=True)
zb, mask = ps["zb"], ps["part"] >= 0
H, W = zb.shape
mm1 = X[:, 2] / cam["f"] * 1000
qo = p + n2 * (2.5 / mm1)[:, None]
qi = p - n2 * (1.0 / mm1)[:, None]
r = lambda q: (np.clip(np.round(q[:, 1]).astype(int), 0, H - 1), np.clip(np.round(q[:, 0]).astype(int), 0, W - 1))
print("mm/px", np.median(mm1), "outward in mask", int(mask[r(qo)].sum()), "depth step > 4 mm", int((zb[r(qo)] - X[:, 2] > 0.004).sum()),
      "visible", int((np.abs(zb[r(qi)] - X[:, 2]) < 0.004).sum()))
print("zb - z at inner (mm) quantiles", np.percentile((zb[r(qi)] - X[:, 2])[np.isfinite(zb[r(qi)])] * 1000, [5, 25, 50, 75, 95]).round(1))
print("zb - z at outer (mm) quantiles", np.percentile((zb[r(qo)] - X[:, 2])[np.isfinite(zb[r(qo)])] * 1000, [5, 25, 50, 75, 95]).round(1))
d = ImageDraw.Draw(im)
for q, n in zip(p, n2):
    d.line([tuple(q), tuple(q + 8 * n)], fill=(255, 0, 0), width=1)
    d.point(tuple(q), fill=(0, 255, 0))
cx, cy = p.mean(0)
im.crop((int(cx - 350), int(cy - 350), int(cx + 350), int(cy + 350))).save(f"/mnt/data/hifipushie/solvereads/out/jdbg_{m}_{vi}.png")
