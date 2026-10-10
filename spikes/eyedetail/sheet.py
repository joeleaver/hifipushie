"""sheet.py <out.jpg> <title> <row>...: rows of labelled panels; a row is 'label=path[#ref|#ours],label=path...'.
Panels are squares of 480 px. The judging sheet for reports."""
import sys

from PIL import Image, ImageDraw

out, title = sys.argv[1], sys.argv[2]
P = 480
rows = []
for r in sys.argv[3:]:
    ims = []
    for a in r.split(","):
        lab, p = a.split("=", 1)
        half = None
        if "#" in p:
            p, half = p.split("#")
        im = Image.open(p).convert("RGB")
        if half:
            w = im.width // 2
            im = im.crop((0, 0, w, im.height) if half == "ref" else (w, 0, im.width, im.height))
        im = im.resize((P, P), Image.LANCZOS)
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 7 * len(lab) + 10, 16], fill=(20, 20, 20))
        d.text((5, 2), lab, fill=(255, 255, 255))
        ims.append(im)
    rows.append(ims)
W = max(len(r) for r in rows) * P
S = Image.new("RGB", (W, 26 + P * len(rows)), (238, 238, 238))
ImageDraw.Draw(S).text((8, 7), title, fill=(0, 0, 0))
for i, r in enumerate(rows):
    for j, im in enumerate(r):
        S.paste(im, (j * P, 26 + i * P))
S.save(out, quality=88)
print(out, S.size)
