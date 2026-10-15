"""profover.py <model> [view=1] [tag=]: OUR hair outline over THE PICTURE through the fitted camera (no skull in between:
the skull fit and the head scale are what the stand-off numbers depend on). Draws the picture's solid hair (green edge)
and ours (red edge, from the tile's alpha / non-backdrop) and prints, along rays from the head centre every 15 deg over
the top half, the hair edge's distance from the head centre in mm, picture vs ours. $TOUT/s_<model><tag>_v<view>.png in,
$TOUT/profover_<model><tag>_v<view>.png out. The render's whole silhouette is drawn too (blue): it checks the head's
registration on the picture."""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

from hifipushie import hair_read, store

m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
OUT = os.environ["TOUT"]
vi = int(kw.get("view", 1))
tag = kw.get("tag", "")
spec = store.load(m)
fr = [f for f in hair_read.frames(m, spec, [vi]) if f["i"] == vi][0]
img = fr["image"]
W, H = img.size
hn = hair_read.hairness(img, fr["hair"], fr["bg"], fr["mm"])
theirs = np.asarray(hn["solid"], bool)
tile = Image.open(f"{OUT}/s_{m}{tag}_v{vi}.png")
rgba = hair_read.render_as_picture(tile.convert("RGBA") if tile.mode == "RGBA" else tile, (W, H))
a = np.asarray(rgba.convert("RGB"), float)
bgc = a[:6, :6].reshape(-1, 3).mean(0)
fg = np.abs(a - bgc).max(-1) > 12
# our hair: dark, low-saturation pixels of the foreground that are not skin (skin: R clearly > B)
R, G, B = a[..., 0], a[..., 1], a[..., 2]
skinish = (R - B > 25) & (R > 90)
ours = ndi.binary_opening(fg & ~skinish, iterations=1)
ours = ndi.binary_fill_holes(ndi.binary_closing(ours, iterations=2))
lab, n = ndi.label(ours)
if n:
    ours = lab == (1 + int(np.argmax(ndi.sum(ours, lab, range(1, n + 1)))))
cx, cy = fr["c"]
mm = fr["mm"]
rows = []
for ang in range(-150, 151, 15):  # 0 = straight up, + = image right (past 90: below the centre, the cheeks)
    t = np.radians(ang)
    dx, dy = np.sin(t), -np.cos(t)
    def edge(mask):
        last = None
        for r in np.arange(0, max(W, H), 0.5):
            x, y = int(round(cx + dx * r)), int(round(cy + dy * r))
            if not (0 <= x < W and 0 <= y < H):
                break
            if mask[y, x]:
                last = r
        return last
    e1, e2 = edge(theirs), edge(ours)
    rows.append((ang, None if e1 is None else round(e1 * mm, 1), None if e2 is None else round(e2 * mm, 1)))
print(f"{m} view {vi}: hair edge from the head centre, mm (angle 0 = up, + = image right): picture | ours | ours - picture")
for ang, e1, e2 in rows:
    d = None if (e1 is None or e2 is None) else round(e2 - e1, 1)
    print(f"  {ang:4d}  {e1} | {e2} | {d}")
vis = Image.blend(img.convert("RGB"), rgba.convert("RGB"), 0.35)
d = ImageDraw.Draw(vis)
# the whole render's silhouette (face and body too) in BLUE: whether OUR HEAD sits on the picture's (the red hair edge
# runs down the face where our hair hangs beside the cheek: read alone it looked like our face profile)
for mask, col in ((theirs, (0, 255, 0)), (ours, (255, 0, 0)), (fg, (0, 120, 255))):
    e = mask & ~ndi.binary_erosion(mask, iterations=2)
    ys, xs = np.nonzero(e)
    for x, y in zip(xs[::3], ys[::3]):
        d.point((int(x), int(y)), fill=col)
d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], outline=(255, 255, 0))
vis.save(f"{OUT}/profover_{m}{tag}_v{vi}.png")
print(f"{OUT}/profover_{m}{tag}_v{vi}.png")
