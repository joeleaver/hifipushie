"""small.py <in> <out.jpg> <width> [x0,y0,x1,y1 fractions]: a crop, downscaled (to look at once, cheaply)."""
import sys

from PIL import Image

im = Image.open(sys.argv[1]).convert("RGB")
if len(sys.argv) > 4:
    f = [float(v) for v in sys.argv[4].split(",")]
    im = im.crop((int(f[0] * im.size[0]), int(f[1] * im.size[1]), int(f[2] * im.size[0]), int(f[3] * im.size[1])))
w = int(sys.argv[3])
im.resize((w, int(w * im.size[1] / im.size[0])), Image.LANCZOS).save(sys.argv[2], quality=85)
