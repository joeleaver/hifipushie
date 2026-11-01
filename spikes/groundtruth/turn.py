"""turn.py <tag> [n=8] [yup=1]: a turntable of a prepared scan in its OWN frame (to see what it is and which way it
faces) -> out/turn_<tag>.png. yup=1: the scan is Y up (x, y, z) -> (x, -z, y) first."""
import sys
import numpy as np
from PIL import Image, ImageDraw
import gt, rast

tag = sys.argv[1]
kw = dict(a.split("=") for a in sys.argv[2:])
n = int(kw.get("n", 8))
s = gt.load_scan(tag)
V, F = s["V"], s["F"]
if kw.get("yup") == "1":
    V = np.stack([V[:, 0], -V[:, 2], V[:, 1]], 1)
u = float(kw.get("unit", 1.0))
V = V * u
top = V[:, 2].max()
ctr = np.r_[np.median(V[V[:, 2] > top - 0.2][:, :2], 0), top - 0.13]
C = (s["C"] * 255) if "C" in s and s["C"] is not None and kw.get("clay") != "1" else np.full((len(V), 3), 205.0)
ims = []
for i in range(n):
    az = 360.0 * i / n
    cam = rast.look_cam(ctr, yaw=az, dist=1.6, lens=85, size=(600, 800))
    vis = rast.visibility(V, F, cam)
    im = rast.shade(vis, V, F, C, ambient=0.35 if "C" in s else 0.22)
    ImageDraw.Draw(im).text((8, 8), f"{tag} az {az:.0f}", fill=(0, 0, 0))
    ims.append(im)
sheet = Image.new("RGB", (600 * n, 800))
for i, im in enumerate(ims):
    sheet.paste(im, (600 * i, 0))
sheet.save(gt.OUT / f"turn_{tag}.png")
print(gt.OUT / f"turn_{tag}.png", ctr)
