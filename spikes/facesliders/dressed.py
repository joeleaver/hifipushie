"""dressed.py <out.jpg> <label=front_big.png> ...: photo | each dressed render (shot.py's _front_big, the photo's crop),
whole face, then the eyes and the mouth at 2x (the same crops of all)."""
import sys

from PIL import Image, ImageDraw

import sheet1
from hifipushie import likeness

refs = likeness._refs("ll_garrett")
ph = likeness.photo_sides(refs)[0]
crop = sheet1.crop_of(refs["views"][0])
W = 520
cols = [("photo", ph["img"].crop(tuple(int(round(c)) for c in crop)))]
for a in sys.argv[2:]:
    lb, p = a.split("=", 1)
    cols.append((lb, Image.open(p).convert("RGB")))
ims = [(lb, im.resize((W, int(W * im.size[1] / im.size[0])))) for lb, im in cols]
H = ims[0][1].size[1]
CR = ((0.22, 0.36, 0.78, 0.5), (0.3, 0.6, 0.7, 0.76))
hs = [int(W * (y1 - y0) * H / ((x1 - x0) * W)) for x0, y0, x1, y1 in CR]
S = Image.new("RGB", (W * len(ims), H + sum(hs)), (255, 255, 255))
d = ImageDraw.Draw(S)
for i, (lb, im) in enumerate(ims):
    S.paste(im, (i * W, 0))
    for j, (x0, y0, x1, y1) in enumerate(CR):
        S.paste(im.crop((int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H))).resize((W, hs[j])), (i * W, H + sum(hs[:j])))
    d.text((i * W + 6, 6), lb, fill=(255, 0, 0))
S.save(sys.argv[1], quality=90)
print(sys.argv[1], S.size)
