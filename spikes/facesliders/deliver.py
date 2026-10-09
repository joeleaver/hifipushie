"""deliver.py <n>: the matched pairs (likeness_pair.sheet) of ll_garrett (before) and fs_garrett (after) as
human_renders/ll_s_<n>_before_pair.png / ll_s_<n>_after_pair.png, and the summary ll_s_<n>_summary.png: photo | before |
after at whole-face scale, then the eyes and the mouth at 2x (crops of the same three), with the measures."""
import sys

from PIL import Image, ImageDraw

import gm
from hifipushie import likeness_pair as lp
from hifipushie import store

n = sys.argv[1]
R = "/home/joe/dev/hifipushie/workspace/human_renders"
rows = {}
ms = {}
for tag, name in (("before", "ll_garrett"), ("after", "fs_garrett")):
    ph, md, m = gm.measure(name, store.load(name)["base"])
    lp.sheet(m, f"{R}/ll_s_{n}_{tag}_pair.png", title=f"{name} ({tag})")
    rows[tag], rows["photo"], ms[tag] = md, ph, m
W, H = ms["before"]["photo"].size
ims = [ms["before"]["photo"], ms["before"]["render"], ms["after"]["render"]]
labs = ["photo", "before (ll_garrett: one-off edits)", "after (fs_garrett: sliders)"]
CROPS = ((0.15, 0.33, 0.85, 0.5), (0.25, 0.6, 0.75, 0.8))
hs = [int(W * (y1 - y0) * H / ((x1 - x0) * W)) for x0, y0, x1, y1 in CROPS]
S = Image.new("RGB", (3 * W, H + sum(hs) + 250), (255, 255, 255))
d = ImageDraw.Draw(S)
for i, (im, lab) in enumerate(zip(ims, labs)):
    S.paste(im.convert("RGB"), (i * W, 0))
    d.text((i * W + 8, 8), lab, fill=(255, 0, 0))
    for j, (x0, y0, x1, y1) in enumerate(CROPS):
        c = im.convert("RGB").crop((int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H)))
        S.paste(c.resize((W, hs[j])), (i * W, H + sum(hs[:j])))
y = H + sum(hs) + 8
keys = ("open", "cover", "canthal_tilt", "brow_gap", "brow_tilt", "upper_lip", "lower_lip", "cupid_bow", "mouth_width",
        "alar_width", "width_jaw")
for k in keys:
    d.text((8, y), f"{k:14s} photo {rows['photo'][k]:7.2f}   before {rows['before'][k]:7.2f}   after {rows['after'][k]:7.2f}",
           fill=(0, 0, 0))
    y += 20
S.save(f"{R}/ll_s_{n}_summary.png")
print(f"{R}/ll_s_{n}_summary.png", S.size)
for k in keys:
    print(f"{k:14s} photo {rows['photo'][k]:7.2f}  before {rows['before'][k]:7.2f}  after {rows['after'][k]:7.2f}")
