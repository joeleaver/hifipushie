"""row.py <out.png> <label>=<file> ...: tiles side by side, each with a LARGE label; h=<px> (default 640);
crop=x0,y0,x1,y1 (shares of each tile, applied to all)."""
import sys

from PIL import Image, ImageDraw, ImageFont

out = sys.argv[1]
opts = dict(a.split("=", 1) for a in sys.argv[2:] if a.split("=", 1)[0] in ("h", "crop"))
items = [a.split("=", 1) for a in sys.argv[2:] if a.split("=", 1)[0] not in ("h", "crop")]
h = int(opts.get("h", 640))
crop = [float(x) for x in opts["crop"].split(",")] if opts.get("crop") else None
try:
    F = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", max(18, h // 22))
except OSError:
    F = ImageFont.load_default()
ims = []
for lab, f in items:
    try:
        im = Image.open(f).convert("RGB")
    except OSError:
        im = Image.new("RGB", (h, h), "#888")
    if crop:
        w_, h_ = im.size
        im = im.crop((int(crop[0] * w_), int(crop[1] * h_), int(crop[2] * w_), int(crop[3] * h_)))
    im = im.resize((int(im.width * h / im.height), h))
    ImageDraw.Draw(im).text((10, 8), lab, fill="black", font=F, stroke_width=3, stroke_fill="white")
    ims.append(im)
S = Image.new("RGB", (sum(i.width for i in ims), h), "white")
x = 0
for i in ims:
    S.paste(i, (x, 0))
    x += i.width
S.save(out, quality=88)
print("row", out)
