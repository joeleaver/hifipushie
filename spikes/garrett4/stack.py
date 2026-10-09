"""stack.py <out.jpg> x0,y0,x1,y1 <in> [<in> ...]: the same crop of several pictures stacked top to bottom."""
import sys

from PIL import Image

box = tuple(int(v) for v in sys.argv[2].split(","))
ims = [Image.open(f).convert("RGB").crop(box) for f in sys.argv[3:]]
S = Image.new("RGB", (ims[0].size[0], sum(i.size[1] for i in ims)))
y = 0
for i in ims:
    S.paste(i, (0, y))
    y += i.size[1]
S.save(sys.argv[1], quality=90)
