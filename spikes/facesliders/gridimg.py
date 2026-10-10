"""gridimg.py <image> <x0> <y0> <x1> <y1> <step> <out.jpg> [lines.json]: a crop of a reference picture with a labelled
pixel grid (full-picture coordinates) for tracing by eye, upscaled to ~1000 px; optional {name: [[u, v], ...]} drawn
on it (to check a trace)."""
import json
import sys

from PIL import Image, ImageDraw

img, x0, y0, x1, y1, step, out = sys.argv[1], *map(int, sys.argv[2:7]), sys.argv[7]
lines = json.load(open(sys.argv[8])) if len(sys.argv) > 8 else {}
im = Image.open(img).convert("RGB").crop((x0, y0, x1, y1))
k = 1000 / max(x1 - x0, y1 - y0)
im = im.resize((int((x1 - x0) * k), int((y1 - y0) * k)), Image.LANCZOS)
d = ImageDraw.Draw(im)
for x in range(x0 - x0 % step + step, x1, step):
    X = (x - x0) * k
    d.line([(X, 0), (X, im.size[1])], fill=(0, 255, 255) if x % (5 * step) == 0 else (0, 140, 140), width=1)
    d.text((X + 2, 2), str(x), fill=(255, 255, 0))
for y in range(y0 - y0 % step + step, y1, step):
    Y = (y - y0) * k
    d.line([(0, Y), (im.size[0], Y)], fill=(0, 255, 255) if y % (5 * step) == 0 else (0, 140, 140), width=1)
    d.text((2, Y + 2), str(y), fill=(255, 255, 0))
for nm, pts in lines.items():
    P = [((u - x0) * k, (v - y0) * k) for u, v in pts]
    d.line(P, fill=(255, 40, 40), width=2)
    for p in P:
        d.ellipse([p[0] - 3, p[1] - 3, p[0] + 3, p[1] + 3], outline=(255, 40, 40))
im.save(out, quality=88)
print("wrote", out, im.size)
