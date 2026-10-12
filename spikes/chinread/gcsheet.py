"""gcsheet.py <out png> <title> <label>=<model> [...]: REFERENCE | per model: 50 % BLEND (the picture with the model wearing
the pictures as its skin: jsheet.py's cached j_<model>_<view>.png) and its OWN-SHAPE CLAY under the picture's fitted light
(blockin.lit_render), a row per reference view (front / 3-4 / side), LARGE labels inside the image; then a CHIN CLOSE-UP
block: the same tiles cropped to the lower face and enlarged. At most 3 models (4 column groups)."""
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from hifipushie import blockin as bi, face_ruler as fr, humanfit, store

SHOTS = os.environ.get("SHOTS", "/mnt/data/hifipushie/chinread/out:/mnt/data/hifipushie/solvereads/out:/mnt/data/hifipushie/garrettgood/out:/mnt/data/hifipushie/reruns/out:/mnt/data/hifipushie/refread/out").split(":")
N = int(os.environ.get("SIZE", "560"))
F = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
big, mid = ImageFont.truetype(F, 44), ImageFont.truetype(F, 30)
out, title, args = sys.argv[1], sys.argv[2], sys.argv[3:]
cols = [a.split("=", 1) for a in args]
TOP, HEAD = 76, 112
VN = {0: "front", 1: "3/4", 2: "side"}


def find(name):
    return next((f"{d}/{name}" for d in SHOTS if os.path.exists(f"{d}/{name}")), None)


def cut(im, box, cr):
    im = im.crop(tuple(int(round(x)) for x in box))
    if cr is not None:
        k = im.size[0]
        im = im.crop(tuple(int(round(c * k)) for c in cr))
    return im.resize((N, N), Image.LANCZOS)


rj0 = bi._refs(cols[0][1])
nv = len(rj0["views"])
# tiles per model and view: (blend, clay), full and chin
data = {}
crops = {}
for lab, m in cols:
    rj = bi._refs(m)
    spec = store.load(m)
    head = fr.model_head(spec)
    L = np.asarray(head["L"], float)
    for vi, (v, cam, box) in enumerate(zip(rj["views"], rj["cameras"], rj["blockin"]["boxes"])):
        img = Image.open(v["image"]).convert("RGB")
        clay, lt, _ = bi.lit_render(head["mesh"], cam, img)
        if clay.size != img.size:
            clay = clay.resize(img.size, Image.LANCZOS)
        P = humanfit.project(cam, L[:68])
        mm = float(cam["t"][2]) / cam["f"] * 1000
        c = 0.5 * (P[33] + P[8]) + [0, 10 / mm]
        r = 58 / mm
        s = float(box[2] - box[0])
        q = [(c[0] - r - box[0]) / s, (c[1] - r - box[1]) / s, (c[0] + r - box[0]) / s, (c[1] + r - box[1]) / s]
        for a_ in (0, 1):
            d_ = max(0.0, -q[a_]) - max(0.0, q[a_ + 2] - 1.0)
            q[a_], q[a_ + 2] = q[a_] + d_, q[a_ + 2] + d_
        fj = find(f"j_{m}_{vi}.png")
        for blk, cr in ((0, None), (1, tuple(q))):
            ph = cut(img, box, cr)
            cl = cut(clay.convert("RGB"), box, cr)
            if fj:
                j = Image.open(fj).convert("RGB")
                if cr is not None:
                    j = j.crop(tuple(int(round(c_ * j.size[0])) for c_ in cr))
                bl = Image.blend(ph, j.resize((N, N), Image.LANCZOS), 0.5)
            else:
                bl = Image.blend(ph, cl, 0.5)
            data[(m, vi, blk)] = (ph, bl, cl)
        print(m, vi, "light", np.round(lt[1], 3), "projected shot" if fj else "NO projected shot: the blend is with the clay", flush=True)
ncol = 1 + 2 * len(cols)
blockh = HEAD + N * nv
W = Image.new("RGB", (N * ncol, TOP + blockh * 2), "white")
d = ImageDraw.Draw(W)
d.text((12, 12), title, fill=(0, 0, 0), font=big)
for blk in range(2):
    y0 = TOP + blk * blockh
    d.text((12, y0 + 8), "REFERENCE" if blk == 0 else "CHIN close-up", fill=(0, 0, 0), font=big)
    for c, (lab, m) in enumerate(cols):
        x0 = N * (1 + 2 * c)
        d.text((x0 + 12, y0 + 4), lab, fill=(170, 0, 0) if c == 0 else (0, 0, 150), font=big)
        d.text((x0 + 12, y0 + 64), "50 % blend", fill=(0, 0, 0), font=mid)
        d.text((x0 + N + 12, y0 + 64), "own shape: clay", fill=(0, 0, 0), font=mid)
    for vi in range(nv):
        y = y0 + HEAD + vi * N
        W.paste(data[(cols[0][1], vi, blk)][0], (0, y))
        for c, (lab, m) in enumerate(cols):
            if (m, vi, blk) not in data:
                continue
            _, bl, cl = data[(m, vi, blk)]
            W.paste(bl, (N * (1 + 2 * c), y))
            W.paste(cl, (N * (2 + 2 * c), y))
        d.rectangle([0, y, 120, y + 44], fill=(0, 0, 0))
        d.text((8, y + 4), VN.get(vi, str(vi)), fill=(255, 255, 0), font=mid)
    for c in range(len(cols)):
        x0 = N * (1 + 2 * c)
        d.line([(x0, y0), (x0, y0 + blockh)], fill=(0, 0, 0), width=5)
W.save(out)
print(out)
