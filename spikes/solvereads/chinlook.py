"""chinlook.py <out png> <model> [<model> ...]: the CHIN close up, per reference view of the first model's pictures:
photo | then per model: photo with the model's outline (green) and its landmarks' chin / jaw line (yellow dots: lm 3..13)
drawn through that model's own fitted camera | the model's clay through it | 50 % blend photo / clay. Rows = views."""
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from hifipushie import blockin as bi, face_ruler as fr, store

out, models = sys.argv[1], sys.argv[2:]
N = 420
F = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
rows = []
for m in models:
    spec, rj = store.load(m), bi._refs(m)
    head = fr.model_head(spec)
    L = np.asarray(head["L"], float)
    tiles = []
    for vi, (v, cam) in enumerate(zip(rj["views"], rj["cameras"])):
        img = Image.open(v["image"]).convert("RGB")
        cl, ps = fr.clay(head, cam, passes=True)
        _, P = fr._cam_points(cam, L[:68])
        mm = float(cam["t"][2]) / cam["f"] * 1000
        c = 0.5 * (P[33] + P[8]) + [0, 12 / mm]
        r = 62 / mm
        box = tuple(int(round(x)) for x in (c[0] - r, c[1] - r, c[0] + r, c[1] + r))
        ov = img.copy()
        d = ImageDraw.Draw(ov)
        cm = fr._curve(ps["part"] >= 0)
        if cm is not None:
            d.line([tuple(p) for p in cm], fill=(0, 230, 0), width=3)
        for i in range(3, 14):
            d.ellipse([P[i, 0] - 4, P[i, 1] - 4, P[i, 0] + 4, P[i, 1] + 4], fill=(255, 235, 0))
        cl = cl.convert("RGB").resize(img.size) if cl.size != img.size else cl.convert("RGB")
        t = [x.crop(box).resize((N, N), Image.LANCZOS) for x in (img, ov, cl, Image.blend(img, cl, 0.5))]
        tiles.append(t)
    rows.append((m, tiles))
nv = len(rows[0][1])
W = Image.new("RGB", (N * (1 + 3 * len(rows)), 50 + N * nv), "white")
d = ImageDraw.Draw(W)
d.text((8, 10), "REFERENCE", fill=(0, 0, 0), font=F)
for k, (m, tiles) in enumerate(rows):
    d.text((N * (1 + 3 * k) + 8, 10), f"{m}: outline on photo | clay | blend", fill=(160, 0, 0) if k == 0 else (0, 0, 140), font=F)
    for vi, t in enumerate(tiles[:nv]):
        if k == 0:
            W.paste(t[0], (0, 50 + vi * N))
        for j in range(3):
            W.paste(t[1 + j], (N * (1 + 3 * k + j), 50 + vi * N))
W.save(out)
print(out)
