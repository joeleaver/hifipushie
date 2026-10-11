"""dsheet.py <out png> <title>=<model> [<title>=<model> ...]: DRESSED sheet, reference | best result | the rest.
Rows: each reference view through its fitted camera (the block-in's square boxes), then the eyes (front, zoomed).
Shots cached in $G/out/d_<model>_<view>.png. Env SIZE (640), HAIR (0)."""
import os, sys
import numpy as np
from PIL import Image, ImageDraw
sys.path[:0] = ["/home/joe/dev/hifipushie/spikes/garrett3"]
import stage
from hifipushie import blockin as bi, resources

G = os.environ.get("G", "/mnt/data/hifipushie/reruns") + "/out"
os.makedirs(G, exist_ok=True)
N = int(os.environ.get("SIZE", "640"))
HAIR = os.environ.get("HAIR", "0") == "1"
out, cols = sys.argv[1], [a.split("=", 1) for a in sys.argv[2:]]
tiles = {}
for title, m in cols:
    rj = bi._refs(m)
    boxes = rj["blockin"]["boxes"]
    for vi, (v, cam, box) in enumerate(zip(rj["views"], rj["cameras"], boxes)):
        ib = [int(round(x)) for x in box]
        if ("photo", vi) not in tiles:
            tiles[("photo", vi)] = Image.open(v["image"]).convert("RGB").crop(tuple(ib)).resize((N, N), Image.LANCZOS)
        f = f"{G}/d_{m}_{vi}{'h' if HAIR else ''}.png"
        if not os.path.exists(f):
            with resources.heavy(f"rerun shot {m} {vi}", gb=6):
                im = stage.shoot(m, [stage.fitted_frame(cam, [float(x) for x in ib], f"v{vi}")], stage.photo_light(m, vi), size=N * 2, hair_on=HAIR)[f"v{vi}"]
            bg = Image.new("RGB", im.size, (200, 200, 200))
            bg.paste(im, mask=im.split()[-1] if im.mode == "RGBA" else None)
            bg.save(f)
        tiles[(m, vi)] = Image.open(f).convert("RGB")
nv = len([k for k in tiles if k[0] == "photo"])
names = ["photo"] + [m for _, m in cols]
titles = ["reference"] + [t for t, _ in cols]
# the eyes row: the front tile's eye band, zoomed
P = None
rj0 = bi._refs(cols[0][1]); v0 = bi._front(rj0)
img = Image.open(rj0["views"][v0]["image"]).convert("RGB")
Pd = np.asarray(bi.detect_view(img, rj0["views"][v0]), float)[:, :2]
b = rj0["blockin"]["boxes"][v0]; s = N / (b[2] - b[0])
c = (0.5 * (Pd[468] + Pd[473]) - [b[0], b[1]]) * s
hw = 0.36 * N; eb = (c[0] - hw, c[1] - hw * 0.5, c[0] + hw, c[1] + hw * 0.5)
HEAD = 40
W, H = N * len(names), HEAD + N * nv + N // 2 + 8
sh = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(sh)
for j, (nm, t) in enumerate(zip(names, titles)):
    d.text((j * N + 6, 6), t, fill=(0, 0, 0))
    for vi in range(nv):
        sh.paste(tiles[(nm, vi)].resize((N, N), Image.LANCZOS), (j * N, HEAD + vi * N))
    big = tiles[(nm, v0)]; k = big.size[0] / N
    sh.paste(big.crop(tuple(int(x * k) for x in eb)).resize((N, N // 2), Image.LANCZOS), (j * N, HEAD + nv * N + 8))
sh.save(out); print(out)
