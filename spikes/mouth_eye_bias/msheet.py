"""msheet.py <ref> <before tag> <after tag> <out.png>: reference | before | after, mouth row and eyes row (crops from
mcrop.py at the same framing)."""
import sys

from PIL import Image, ImageDraw

import meb

ref, b, a, out = sys.argv[1:5]
rows = []
for region in ("mouth", "eyes"):
    ims = [Image.open(f"{meb.OUT}/crop_{ref}_{region}_{t}.png").convert("RGB") for t in ("photo", b, a)]
    h = 300 if region == "mouth" else 220
    ims = [i.resize((int(i.size[0] * h / i.size[1]), h)) for i in ims]
    rows.append(ims)
W = max(sum(i.size[0] for i in r) + 16 for r in rows)
H = sum(r[0].size[1] for r in rows) + 8 + 24
sh = Image.new("RGB", (W, H), (25, 25, 25))
d = ImageDraw.Draw(sh)
x = 0
for lab, im in zip(("reference", "before", "after"), rows[0]):
    d.text((x + 6, 6), lab, fill=(255, 255, 255))
    x += im.size[0] + 8
y = 24
for r in rows:
    x = 0
    for im in r:
        sh.paste(im, (x, y))
        x += im.size[0] + 8
    y += r[0].size[1] + 8
sh.save(out)
print(out)
