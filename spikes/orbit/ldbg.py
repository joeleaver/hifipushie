"""ldbg.py <model A> <picture's model B> <kind> [photo]: the limbus read drawn on the picture's eye crop x6 (green = the
model's limbus circle, yellow = the read, red = the truth when B is a model) -> out/ldbg_<A>_<B>_<kind>.png.
"photo": B's own reference picture of that kind (REFS = B) instead of a dressed shot."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import blockin as bi, face_ruler as fr, humanfit, store

G = os.environ["G"] + "/out"
D = os.environ.get("D", "/mnt/data/hifipushie/faceruler/out")
a, b, kind = sys.argv[1:4]
photo = len(sys.argv) > 4
rj = bi._refs(b if photo else os.environ.get("REFS", "gd_T12"))
kinds = [fr.kind_of(v.get("yaw", 0)) for v in rj["views"]]
vi = kinds.index(kind)
cam = rj["cameras"][vi]
if photo:
    img, org = Image.open(rj["views"][vi]["image"]).convert("RGB"), (0.0, 0.0)
else:
    img, org = Image.open(f"{D}/d_{b}_{kind}.png").convert("RGB"), json.load(open(f"{D}/d_box.json"))["box"][:2]
ha = fr.model_head(store.load(a))
la = fr.limbus_model(ha, float(os.environ["IRIS"]) if os.environ.get("IRIS") else None)
lb = None if photo else fr.limbus_model(fr.model_head(store.load(b)))
lum = fr._lum(img)
from scipy import ndimage as ndi  # noqa: E402
valid = ndi.binary_erosion(fr.foreground(img), iterations=3)
eye_c = np.asarray(cam["centre"], float) - humanfit._cam_rot(cam).T @ np.asarray(cam["t"], float)
dist = [np.linalg.norm(q["X"] - eye_c) for q in la]
K = 6
tiles = []
for j in (0, 1):
    rd = fr.limbus_read(lum, cam, la[j], org, 1.0, far=dist[j] > min(dist) + 1e-6, valid=valid)
    if rd is None:
        continue
    half = 14.0 / rd["mmpx"]
    c = rd["p"]
    box = [int(c[0] - half), int(c[1] - half), int(c[0] + half), int(c[1] + half)]
    im = img.crop(box).resize((int(2 * half) * K, int(2 * half) * K), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    th = np.linspace(0, 2 * np.pi, 73)

    def ring(lb_, sh, col):
        P = lb_["X"] + lb_["r"] * (np.cos(th)[:, None] * lb_["lat"] + np.sin(th)[:, None] * lb_["up"])
        q = (fr._cam_points(cam, P)[1] - org + sh - box[:2]) * K
        d.line([tuple(x) for x in q], fill=col, width=2)
    ring(la[j], 0, (0, 230, 0))
    ring(la[j], rd["d"], (255, 235, 0))
    if lb:
        ring(lb[j], 0, (255, 0, 0))
    d.text((6, 6), f"{'rl'[j]} open {rd['open']:.2f} read {rd['d'][0] * rd['mmpx']:+.2f} {rd['d'][1] * rd['mmpx']:+.2f} mm score {rd['score']:.3f} sharp {rd['sharp']:.3f}", fill=(255, 255, 255), font_size=20)
    tiles.append(im)
W = Image.new("RGB", (sum(t.size[0] for t in tiles), max(t.size[1] for t in tiles)))
x = 0
for t in tiles:
    W.paste(t, (x, 0))
    x += t.size[0]
W.save(f"{G}/ldbg_{a}_{b}_{kind}.png")
print("saved", f"{G}/ldbg_{a}_{b}_{kind}.png")
