"""lineup.py <out.jpg> <label=front png> ...: the concept's face crop and each past dressed front (shot.py's _front_big,
the same crop) side by side, the face only, labelled: where did it go ugly."""
import sys

from PIL import Image, ImageDraw

import sheet1
from hifipushie import likeness

refs = likeness._refs("ll_garrett")
ph = likeness.photo_sides(refs)[0]
crop = sheet1.crop_of(refs["views"][0])
W = 300
cols = [("concept", ph["img"].crop(tuple(int(round(c)) for c in crop)))]
for a in sys.argv[2:]:
    lb, p = a.split("=", 1)
    cols.append((lb, Image.open(p).convert("RGB")))
tiles = []
for lb, im in cols:
    im = im.resize((W, int(W * im.size[1] / im.size[0])))
    t = im.crop((0, int(0.02 * im.size[1]), W, int(0.9 * im.size[1])))
    ImageDraw.Draw(t).rectangle((0, 0, W, 16), fill=(0, 0, 0))
    ImageDraw.Draw(t).text((4, 2), lb, fill=(255, 255, 255))
    tiles.append(t)
per = 6
rows = [tiles[i:i + per] for i in range(0, len(tiles), per)]
H = tiles[0].size[1]
S = Image.new("RGB", (W * per, H * len(rows)), (255, 255, 255))
for r, row in enumerate(rows):
    for j, t in enumerate(row):
        S.paste(t, (j * W, r * H))
S.save(sys.argv[1], quality=90)
print(sys.argv[1], S.size)
