"""align0.py <tag> [turn=<deg about Z>] [yup=1]: the scan's FIRST similarity into GNM world from anatomical points:
the scan is drawn from the front through a known camera, the detector (MediaPipe, as the pipeline uses it) marks the
68 standard landmarks on that picture, each is carried back onto the scan's surface by the depth buffer, and the
inner 51 (brows, eyes, nose, lips) + the chin point are laid on GNM's (the sex's class mean) by least squares: rigid
when the scan has real scale (the free scale is printed), with scale otherwise. -> work/<tag>/S0.json and
out/align0_<tag>.png (the picture with the points: LOOK at it). The direct fit (fit3d.py) refines this pose."""
import json
import sys
import numpy as np
from PIL import Image, ImageDraw
import gt, rast
from hifipushie import likeness

tag = sys.argv[1]
kw = dict(a.split("=") for a in sys.argv[2:])
s = gt.load_scan(tag)
V, F = s["V"], s["F"]
R0 = np.eye(3)
if kw.get("yup") == "1":
    R0 = np.array([[1.0, 0, 0], [0, 0, -1], [0, 1, 0]])
a = np.radians(float(kw.get("turn", 0)))
R0 = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]]) @ R0
u = s["info"]["unit_m"] or float(kw.get("unit", 0.6))
Vw = u * V @ R0.T
top = Vw[:, 2].max()
ctr = np.r_[np.median(Vw[Vw[:, 2] > top - 0.2][:, :2], 0), top - 0.13]
cam = rast.look_cam(ctr, dist=1.6, lens=85, size=(1200, 1600), shift=(0, -0.0))
cam["f"] *= 2.2
vis = rast.visibility(Vw, F, cam)
if "C" in s and s["C"] is not None:
    im = rast.shade(vis, Vw, F, s["C"] * 255, ambient=0.75, lights=(((-0.3, -0.3, -0.9), 0.3),))
else:
    tex = np.asarray(Image.open(gt.ROOT / s["info"]["texture"]).convert("RGB"))
    im = rast.shade(vis, Vw, F, rast.texture_lookup(vis, s["FUV"], tex), ambient=0.6, lights=(((-0.3, -0.3, -0.9), 0.45),))
P = likeness.detect([im])[0]
if P is None:
    im.save(gt.OUT / f"align0_{tag}.png")
    raise SystemExit("no face detected: see the picture; try turn=")
P68 = np.asarray(P)[likeness.MP68][:, :2]
# back onto the surface: the pixel's depth -> camera frame -> world
from hifipushie import humanfit
Rc = humanfit._cam_rot(cam)
pts = []
for x, y in P68:
    xi, yi = int(round(x)), int(round(y))
    z = vis["z"][max(yi - 2, 0):yi + 3, max(xi - 2, 0):xi + 3]
    z = z[np.isfinite(z)]
    if not len(z):
        pts.append([np.nan] * 3)
        continue
    z = float(np.median(z))
    xc = np.array([(x - cam["size"][0] / 2) * z / cam["f"], (y - cam["size"][1] / 2) * z / cam["f"], z])
    pts.append((xc - np.asarray(cam["t"])) @ Rc + np.asarray(cam["centre"]))
pts = np.asarray(pts)
G = gt.gnm()
Lg = G["WL"] @ gt.verts(gt.class_mean(s["info"]["sex"]))
use = np.array([i for i in list(range(17, 68)) + [8] if np.isfinite(pts[i]).all()])
real = s["info"]["unit_m"] is not None
Sf = gt.umeyama(pts[use], Lg[use], scale=True)
S = Sf if not real else gt.umeyama(pts[use], Lg[use], scale=False)
res = np.linalg.norm(gt.apply(S, pts[use]) - Lg[use], axis=1) * 1000
# the whole similarity from the scan's OWN frame and units
S0 = gt.compose(S, (u, R0, np.zeros(3)))
gt.save_sim(gt.WORK / tag / "S0.json", S0, landmarks_scan=(pts / u @ R0).tolist(), free_scale=float(Sf[0]), residual_mm=float(res.mean()))
d = ImageDraw.Draw(im)
for i, (x, y) in enumerate(P68):
    d.ellipse([x - 3, y - 3, x + 3, y + 3], outline=(0, 255, 0) if i in use else (255, 160, 0), width=2)
x0, y0, x1, y1 = P68[:, 0].min() - 120, P68[:, 1].min() - 220, P68[:, 0].max() + 120, P68[:, 1].max() + 100
im.crop((int(x0), int(y0), int(x1), int(y1))).save(gt.OUT / f"align0_{tag}.png")
print(f"{tag}: {len(use)} points; landmark residual {res.mean():.1f} mm (max {res.max():.1f}); scale used {S[0]:.4f}; free scale {Sf[0]:.4f} (x unit {u}: scan units -> m {Sf[0] * u:.4f})")
