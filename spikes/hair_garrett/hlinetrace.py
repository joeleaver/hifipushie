"""hlinetrace.py <model> [views=0,1,2] [out=]: the HAIRLINE traced in each fitted picture and in our render through the
same camera (the reader's hair / bare-skin boundary from the face parser), both drawn on the picture's close crop
(picture red, ours cyan), and per |az| bin the height difference ours - picture (mm, + = ours higher) of the line cast
onto the scalp. Renders from $TOUT/s_<model>_v<i>.png."""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import hair, hair_read, humanfit, store

m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
OUT = os.environ["TOUT"]
views = [int(v) for v in kw.get("views", "0,1,2").split(",")]
spec = store.load(m)
sc = hair.scalp(m, spec)
fp = {f["i"]: f for f in hair_read.frames(m, spec)}
fo = {f["i"]: f for f in hair_read.frames(m, spec, images={i: f"{OUT}/s_{m}_v{i}.png" for i in views})}
T = 520
tiles = []
for i in views:
    a, b = fp[i], fo[i]
    lines = {}
    for nm, f in (("picture", a), ("ours", b)):
        pts, _ = hair_read.hairline_pixels(f["hair"], f["skin"], step=2)
        if len(pts):
            P, hit, _ = hair_read.onto_scalp(sc, f["cam"], pts, step=0.001)
            az, el, _ = sc.coords(P)
            eye, _ = hair_read.cam_eye(f["cam"])
            nn = sc.normal(az, el)
            face = ((eye - P) / np.linalg.norm(eye - P, axis=1, keepdims=True) * nn).sum(1)
            fa = np.abs(((az + 180) % 360) - 180)
            ok = hit & (face > 0.35) & ((fa > 110) | (el > -12))
            lines[nm] = (pts[ok], fa[ok], P[ok, 2])
    # crop round the front hairline: the scalp's front-top point
    cam = a["cam"]
    c = humanfit.project(cam, sc.point(np.array([0.0 if abs(a["yaw"]) < 60 else (90.0 if a["yaw"] < 0 else -90.0) * 0.5]),
                                       np.array([35.0]), 0.0))[0]
    s = 0.13 * cam["f"] / np.linalg.norm(sc.C - hair_read.cam_eye(cam)[0])
    box = (c[0] - s / 2, c[1] - s / 2, c[0] + s / 2, c[1] + s / 2)
    im = a["image"].copy()
    d = ImageDraw.Draw(im)
    for nm, col in (("picture", (255, 40, 40)), ("ours", (0, 220, 255))):
        if nm in lines:
            for x, y in lines[nm][0][::1]:
                d.ellipse([x - 1.5, y - 1.5, x + 1.5, y + 1.5], fill=col)
    tiles.append(im.crop(tuple(int(v) for v in box)).resize((T, T), Image.LANCZOS))
    if "picture" in lines and "ours" in lines:
        print(f"view {i}: hairline height ours - picture (mm) by |az|:")
        for a0 in range(0, 100, 10):
            mp = (lines["picture"][1] >= a0) & (lines["picture"][1] < a0 + 10)
            mo = (lines["ours"][1] >= a0) & (lines["ours"][1] < a0 + 10)
            if mp.sum() > 3 and mo.sum() > 3:
                print(f"  {a0:3d}-{a0 + 10}: {1000 * (np.median(lines['ours'][2][mo]) - np.median(lines['picture'][2][mp])):+.1f}"
                      f"  (n {int(mo.sum())} | {int(mp.sum())})")
sheet = Image.new("RGB", (T * len(tiles), T), (255, 255, 255))
for k, t in enumerate(tiles):
    sheet.paste(t, (k * T, 0))
out = kw.get("out", f"{OUT}/hlinetrace_{m}.jpg")
sheet.save(out, quality=90)
print(out)
