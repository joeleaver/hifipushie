"""sheet.py <out png> <title> <label>=<model> <label>=<model> [...]: REFERENCE | best | the rest, rows per reference view,
LARGE labels. Per model three tiles from jsheet.py's cached shots ($G/out/j_ / d_<model>_<view>.png): 50 % blend with
the picture, the reference pictures projected as its skin, its own dressing. COLS=blend,proj,own picks the tiles.
unseen.py-style second use: sheet.py <out> <title> --unseen <label>=<model> ...: nsheet's cached angles, a row per model."""
import os, sys
from PIL import Image, ImageDraw, ImageFont
from hifipushie import blockin as bi

G = os.environ.get("G", "/mnt/data/hifipushie/garrettgood") + "/out"
N = int(os.environ.get("SIZE", "560"))
F = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
big, mid = ImageFont.truetype(F, 40), ImageFont.truetype(F, 26)
out, title, args = sys.argv[1], sys.argv[2], sys.argv[3:]
unseen = args and args[0] == "--unseen"
cols = [a.split("=", 1) for a in args[1 if unseen else 0:]]
KIND = {"blend": "50 % blend with the picture", "proj": "pictures projected as skin", "own": "own dressing"}
kinds = os.environ.get("COLS", "blend,proj,own").split(",")
TOP, HEAD = 70, 100


def tile(f):
    return Image.open(f).convert("RGB").resize((N, N), Image.LANCZOS)


if unseen:
    V = ("three_quarter", "three_quarter_other", "profile_right", "low_angle")
    W = Image.new("RGB", (N * len(V), TOP + (N + 50) * len(cols)), "white")
    d = ImageDraw.Draw(W)
    d.text((10, 10), title, fill=(0, 0, 0), font=big)
    for r, (lab, m) in enumerate(cols):
        y = TOP + r * (N + 50)
        d.text((10, y + 8), lab, fill=(160, 0, 0), font=mid)
        for k, v in enumerate(V):
            W.paste(tile(f"{G}/n_{m}_{v}.png"), (k * N, y + 50))
    W.save(out); print(out); sys.exit()

rj = bi._refs(cols[0][1])
nv = len(rj["views"])
W = Image.new("RGB", (N * (1 + len(kinds) * len(cols)), TOP + HEAD + N * nv), "white")
d = ImageDraw.Draw(W)
d.text((10, 10), title, fill=(0, 0, 0), font=big)
d.text((10, TOP + 8), "REFERENCE", fill=(0, 0, 0), font=big)
for c, (lab, m) in enumerate(cols):
    x0 = N * (1 + c * len(kinds))
    d.text((x0 + 10, TOP + 4), lab, fill=(160, 0, 0) if c == 0 else (0, 0, 140), font=big)
    for k, kd in enumerate(kinds):
        d.text((x0 + k * N + 10, TOP + 58), KIND[kd], fill=(0, 0, 0), font=mid)
    d.line([(x0, TOP), (x0, W.size[1])], fill=(0, 0, 0), width=4)
for vi, (v, box) in enumerate(zip(rj["views"], rj["blockin"]["boxes"])):
    y = TOP + HEAD + vi * N
    ph = Image.open(v["image"]).convert("RGB").crop(tuple(int(round(x)) for x in box)).resize((N, N), Image.LANCZOS)
    W.paste(ph, (0, y))
    for c, (lab, m) in enumerate(cols):
        x0 = N * (1 + c * len(kinds))
        fj, fd = f"{G}/j_{m}_{vi}.png", f"{G}/d_{m}_{vi}.png"
        if not os.path.exists(fj):
            continue
        j = tile(fj)
        for k, kd in enumerate(kinds):
            W.paste({"blend": Image.blend(ph, j, 0.5), "proj": j, "own": tile(fd) if kd == "own" else j}[kd], (x0 + k * N, y))
W.save(out); print(out)
