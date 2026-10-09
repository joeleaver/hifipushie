"""trace.py <photo> <trace json> <out png>: the hair traced on a reference photo, as an artist would before grooming.
- silhouette: the hair mask (dark, low-saturation-against-skin pixels, cleaned: the largest blobs touching the head)
- orientation field: the structure tensor of the photo's luminance inside the mask (the strands' 2D direction), drawn
  as short ticks with their coherence as strength
- hand strokes from the trace json (picked on a grid): "part" (a polyline), "flow" {name: polyline, root first},
  "wisps" {name: polyline}
Writes <out png> (the photo dimmed + the mask's outline + ticks + strokes), <trace>_mask.png and <trace>_field.json
(sampled [x, y, angle deg, coherence])."""
import json, sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

photo, tj, out = sys.argv[1], sys.argv[2], sys.argv[3]
im = Image.open(photo).convert("RGB")
a = np.asarray(im).astype(float) / 255
L = a @ [0.299, 0.587, 0.114]
tr = json.load(open(tj))
# hair: darker than the face's skin and the background, brownish (r >= b); the background is a light grey
bg = np.median(a[:40, :40].reshape(-1, 3), 0)
sat = a.max(-1) - a.min(-1)
hair = (L < 0.42) & (a[..., 0] >= a[..., 2] - 0.02)
hair |= (L < 0.55) & (sat > 0.12) & (np.abs(a - bg).sum(-1) > 0.25) & (a[..., 0] - a[..., 2] > 0.09) & (L < 0.5)
hair = ndi.binary_opening(hair, iterations=1)
hair = ndi.binary_closing(hair, iterations=4)
lab, n = ndi.label(hair)
sizes = ndi.sum(hair, lab, range(1, n + 1))
keep = np.isin(lab, 1 + np.flatnonzero(sizes > 0.02 * sizes.max()))
if "clip_y" in tr:  # nothing under this row is hair (shoulders / clothes)
    keep[int(tr["clip_y"]):] = keep[int(tr["clip_y"]):] & (np.arange(keep.shape[1])[None] > tr.get("clip_x", 0))
mask = ndi.binary_fill_holes(keep)
# the face's own dark features (brows, eyes, nostrils, lips) are not hair: the convex hull of the face points
if "face_hull" in tr:
    hull = Image.new("L", (mask.shape[1], mask.shape[0]), 0)
    ImageDraw.Draw(hull).polygon([tuple(map(float, q)) for q in tr["face_hull"]], fill=255)
    mask &= ~(np.asarray(hull) > 0)
mp = tj.replace(".json", "_mask.png")
Image.fromarray((mask * 255).astype(np.uint8)).save(mp)
# structure tensor (strand direction = the eigenvector of the smaller eigenvalue: along the strands)
g = ndi.gaussian_filter(L, 1.0)
gx, gy = ndi.sobel(g, 1), ndi.sobel(g, 0)
s = 4.0
Jxx, Jyy, Jxy = (ndi.gaussian_filter(v, s) for v in (gx * gx, gy * gy, gx * gy))
ang = 0.5 * np.arctan2(2 * Jxy, Jxx - Jyy) + np.pi / 2  # along the strands
lam = np.sqrt((Jxx - Jyy) ** 2 + 4 * Jxy ** 2)
coh = lam / np.maximum(Jxx + Jyy, 1e-9)
step = 22
field = []
for y in range(step // 2, mask.shape[0], step):
    for x in range(step // 2, mask.shape[1], step):
        if mask[y, x]:
            field.append([x, y, round(float(np.degrees(ang[y, x])) % 180, 1), round(float(coh[y, x]), 3)])
fp = tj.replace(".json", "_field.json")
json.dump({"mask": mp, "field": field}, open(fp, "w"))  # (kept out of the stroke file: that one is hand-written)
# overlay
base = Image.fromarray((np.clip(a * 0.55 + 0.25, 0, 1) * 255).astype(np.uint8))
ov = base.copy()
dr = ImageDraw.Draw(ov)
edge = mask ^ ndi.binary_erosion(mask, iterations=2)
ys, xs = np.nonzero(edge)
for x, y in zip(xs[::2], ys[::2]):
    dr.point((int(x), int(y)), fill=(255, 220, 0))
for x, y, t, c in field:
    r = 9 * min(1.0, 0.3 + c)
    dx, dy = r * np.cos(np.radians(t)), r * np.sin(np.radians(t))
    dr.line([(x - dx, y - dy), (x + dx, y + dy)], fill=(0, 200, 255), width=2)


def poly(pts, col, w=5, arrow=True):
    pts = [tuple(map(float, p)) for p in pts]
    dr.line(pts, fill=col, width=w)
    dr.ellipse([pts[0][0] - 7, pts[0][1] - 7, pts[0][0] + 7, pts[0][1] + 7], outline=col, width=3)  # the root
    if arrow and len(pts) > 1:
        (x0, y0), (x1, y1) = pts[-2], pts[-1]
        v = np.array([x1 - x0, y1 - y0])
        v = v / max(np.linalg.norm(v), 1e-6) * 22
        n = np.array([-v[1], v[0]]) * 0.5
        dr.polygon([(x1, y1), (x1 - v[0] + n[0], y1 - v[1] + n[1]), (x1 - v[0] - n[0], y1 - v[1] - n[1])], fill=col)


if tr.get("part"):
    poly(tr["part"], (255, 40, 40), 6, arrow=False)
for k, p in (tr.get("flow") or {}).items():
    poly(p, (255, 120, 0))
    dr.text((p[0][0] + 10, p[0][1] - 18), k, fill=(255, 255, 255))
for k, p in (tr.get("wisps") or {}).items():
    poly(p, (230, 60, 230), 3)
side = Image.new("RGB", (im.width * 2, im.height))
side.paste(im, (0, 0))
side.paste(ov, (im.width, 0))
dd = ImageDraw.Draw(side)
dd.rectangle([im.width, 0, im.width + 640, 64], fill=(0, 0, 0))
dd.text((im.width + 8, 6), "trace: yellow = hair silhouette, cyan = strand direction (structure tensor), red = part,", fill=(255, 255, 255))
dd.text((im.width + 8, 24), "orange = main flow strokes (root circle -> arrow), magenta = face-framing wisps", fill=(255, 255, 255))
side.save(out)
side.resize((side.width // 2, side.height // 2)).save(out.replace(".png", "_half.png"))
print("saved", out, "field", len(field), "mask px", int(mask.sum()))
