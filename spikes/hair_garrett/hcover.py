"""hcover.py <model> [views=t60,y180,y125,v1] [stage=<head>] [ss=2]: the hair's COVERAGE (Joe: "bald spots"): render
the groom with the scalp inside the hairline painted MAGENTA (look scalp #ff00ff at full tint), then count the magenta
pixels that show through, per view, as a share of the hair's own area (hair = not backdrop, not skin outside the
hairline, not magenta). Target ~0 outside a part line. Tiles $TOUT/s_<model>_mag_<view>.png + $TOUT/coverage_<model>.png
(the magenta pixels marked). Runs hgshots.py (HEAVY) then counts."""
import os
import subprocess
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

m = sys.argv[1]
kw = dict(a.split("=", 1) for a in sys.argv[2:])
OUT = os.environ["TOUT"]
views = kw.get("views", "t60,y180,y125,v1").split(",")
HG = os.environ.get("HG", "/mnt/data/hifipushie/hair_garrett")
if kw.get("render", "1") == "1":
    r = subprocess.run([f"{HG}/run.sh", "hgshots.py", m, "views=" + ",".join(views), "stage=" + kw.get("stage", m),
                        "size=" + kw.get("size", "1024"), "ss=" + kw.get("ss", "2"), "tag=_mag",
                        'look={"scalp": "#ff00ff", "scalp_tint": 1.0}'], capture_output=True, text=True)
    if r.returncode:
        print(r.stdout[-800:], r.stderr[-800:])
        sys.exit(1)
tiles, rows = [], []
for v in views:
    im = np.asarray(Image.open(f"{OUT}/s_{m}_mag_{v}.png").convert("RGB"), float)
    R, G, B = im[..., 0], im[..., 1], im[..., 2]
    # magenta by HUE, not brightness: seen through dark hair it is a dim purple (a dark head read 0.0 % with R, B > 150
    # while the top showed it); skin (B < G) and grey hair (R ~ G ~ B) are not
    mag = (R - G > 35) & (B - G > 35) & (np.abs(R - B) < 0.5 * np.maximum(R, B))
    bg = (np.abs(im - im[:8, :8].reshape(-1, 3).mean(0)).max(-1) < 10)
    hair = ~bg & ~mag
    # the hair region: the hair and what it encloses (holes in it count, not skin around the face below the hairline)
    region = ndi.binary_fill_holes(ndi.binary_closing(hair | mag, iterations=3))
    share = float(mag.sum()) / max(float(region.sum()), 1.0)
    rows.append((v, round(100 * share, 2), int(mag.sum())))
    vis = im.copy()
    vis[mag] = [0, 255, 0]
    tiles.append(Image.fromarray(vis.astype(np.uint8)).resize((400, 400)))
print("COVERAGE (magenta scalp showing, % of the hair region): " + ", ".join(f"{v} {s} % ({n} px)" for v, s, n in rows))
sheet = Image.new("RGB", (400 * len(tiles), 400))
for k, t in enumerate(tiles):
    sheet.paste(t, (k * 400, 0))
sheet.save(f"{OUT}/coverage_{m}.png")
print(f"{OUT}/coverage_{m}.png")
