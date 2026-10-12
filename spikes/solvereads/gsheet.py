"""gsheet.py <out png> <title> <label>=<model> [...]: REFERENCE | best | the rest, a row per reference view, LARGE labels
(spikes/garrettgood/sheet.py's layout: per model 50 % blend with the picture, the pictures projected as its skin, its
own dressing; from jsheet.py's cached shots j_/d_<model>_<view>.png found in the $SHOTS dirs), then a CHIN CLOSE-UP
block: the same columns cropped to the lower face (nose base to under the chin) and enlarged, a row per view.
COLS=blend,proj,own picks the tiles; CHIN=0 leaves the close-up out."""
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from hifipushie import blockin as bi, humanfit, store

SHOTS = os.environ.get("SHOTS", "/mnt/data/hifipushie/solvereads/out:/mnt/data/hifipushie/garrettgood/out:/mnt/data/hifipushie/reruns/out:/mnt/data/hifipushie/refread/out").split(":")
N = int(os.environ.get("SIZE", "560"))
F = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
big, mid = ImageFont.truetype(F, 40), ImageFont.truetype(F, 26)
out, title, args = sys.argv[1], sys.argv[2], sys.argv[3:]
cols = [a.split("=", 1) for a in args]
KIND = {"blend": "50 % blend with the picture", "proj": "pictures projected as skin", "own": "own dressing"}
kinds = os.environ.get("COLS", "blend,proj,own").split(",")
chin = os.environ.get("CHIN", "1") == "1"
TOP, HEAD = 70, 100
VN = {0: "front", 1: "3/4", 2: "side"}


def find(name):
    return next((f"{d}/{name}" for d in SHOTS if os.path.exists(f"{d}/{name}")), None)


def tile(f, crop=None):
    im = Image.open(f).convert("RGB")
    if crop is not None:
        k = im.size[0]
        im = im.crop(tuple(int(round(c * k)) for c in crop))
    return im.resize((N, N), Image.LANCZOS)


rj = bi._refs(cols[0][1])
nv = len(rj["views"])
ncol = 1 + len(kinds) * len(cols)
blockh = HEAD + N * nv
W = Image.new("RGB", (N * ncol, TOP + blockh * (2 if chin else 1)), "white")
d = ImageDraw.Draw(W)
d.text((10, 10), title, fill=(0, 0, 0), font=big)
# the chin's crop per view, as a share of the tile: from the first model's landmarks through its cameras
L = np.asarray(humanfit.state(store.load(cols[0][1])["base"])["L"], float)
crops = []
for cam, box in zip(rj["cameras"], rj["blockin"]["boxes"]):
    P = humanfit.project(cam, L[:68])
    mm = float(cam["t"][2]) / cam["f"] * 1000
    c = 0.5 * (P[33] + P[8]) + [0, 10 / mm]
    r = 58 / mm
    s = float(box[2] - box[0])
    crops.append(((c[0] - r - box[0]) / s, (c[1] - r - box[1]) / s, (c[0] + r - box[0]) / s, (c[1] + r - box[1]) / s))
for blk in range(2 if chin else 1):
    y0 = TOP + blk * blockh
    d.text((10, y0 + 8), "REFERENCE" if blk == 0 else "CHIN close-up", fill=(0, 0, 0), font=big)
    for c, (lab, m) in enumerate(cols):
        x0 = N * (1 + c * len(kinds))
        d.text((x0 + 10, y0 + 4), lab, fill=(160, 0, 0) if c == 0 else (0, 0, 140), font=big)
        for k, kd in enumerate(kinds):
            d.text((x0 + k * N + 10, y0 + 58), KIND[kd], fill=(0, 0, 0), font=mid)
    for vi, (v, box) in enumerate(zip(rj["views"], rj["blockin"]["boxes"])):
        y = y0 + HEAD + vi * N
        cr = crops[vi] if blk else None
        ib = tuple(int(round(x)) for x in box)
        ph = Image.open(v["image"]).convert("RGB").crop(ib)
        if cr is not None:
            ph = ph.crop(tuple(int(round(c_ * ph.size[0])) for c_ in cr))
        ph = ph.resize((N, N), Image.LANCZOS)
        W.paste(ph, (0, y))
        d.text((8, y + 6), VN.get(vi, str(vi)), fill=(255, 255, 0), font=mid)
        for c, (lab, m) in enumerate(cols):
            x0 = N * (1 + c * len(kinds))
            fj, fd = find(f"j_{m}_{vi}.png"), find(f"d_{m}_{vi}.png")
            if fj is None:
                continue
            j = tile(fj, cr)
            bm = (bi._refs(m).get("blockin") or {}).get("boxes")       # the blend: the photo cropped by THIS model's own box
            phm = ph
            if bm and [round(x) for x in bm[vi]] != [round(x) for x in box]:
                phm = Image.open(v["image"]).convert("RGB").crop(tuple(int(round(x)) for x in bm[vi]))
                if cr is not None:
                    phm = phm.crop(tuple(int(round(c_ * phm.size[0])) for c_ in cr))
                phm = phm.resize((N, N), Image.LANCZOS)
            for k, kd in enumerate(kinds):
                W.paste({"blend": Image.blend(phm, j, 0.5), "proj": j, "own": tile(fd, cr) if (kd == "own" and fd) else j}[kd], (x0 + k * N, y))
for blk in range(2 if chin else 1):
    for c in range(len(cols)):
        x0 = N * (1 + c * len(kinds))
        d.line([(x0, TOP + blk * blockh), (x0, TOP + (blk + 1) * blockh)], fill=(0, 0, 0), width=4)
W.save(out)
print(out)
