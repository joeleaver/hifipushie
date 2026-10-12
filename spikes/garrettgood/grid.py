"""grid.py <image> <x0> <y0> <x1> <y1> <out> [step] [scale] [x,y ...]: a crop with a labelled pixel grid (full-image
coordinates), for clicking profile points by eye; extra x,y pairs are drawn as red crosses (checking the clicks)."""
import sys
from PIL import Image, ImageDraw, ImageFont

im = Image.open(sys.argv[1]).convert("RGB")
x0, y0, x1, y1 = map(int, sys.argv[2:6])
step = int(sys.argv[7]) if len(sys.argv) > 7 else 50
k = float(sys.argv[8]) if len(sys.argv) > 8 else 2.0
c = im.crop((x0, y0, x1, y1)).resize((int((x1 - x0) * k), int((y1 - y0) * k)), Image.LANCZOS)
d = ImageDraw.Draw(c)
f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
for x in range((x0 // step + 1) * step, x1, step):
    d.line([((x - x0) * k, 0), ((x - x0) * k, c.height)], fill=(0, 255, 255), width=1)
    d.text(((x - x0) * k + 2, 2), str(x), fill=(0, 0, 255), font=f)
for y in range((y0 // step + 1) * step, y1, step):
    d.line([(0, (y - y0) * k), (c.width, (y - y0) * k)], fill=(0, 255, 255), width=1)
    d.text((2, (y - y0) * k + 2), str(y), fill=(0, 0, 255), font=f)
for a in sys.argv[9:]:
    x, y = map(float, a.split(","))
    X, Y = (x - x0) * k, (y - y0) * k
    d.line([(X - 8, Y), (X + 8, Y)], fill=(255, 0, 0), width=2)
    d.line([(X, Y - 8), (X, Y + 8)], fill=(255, 0, 0), width=2)
c.save(sys.argv[6])
