"""crop.py <in> <out.jpg> x0 y0 x1 y1: a crop saved as jpg."""
import sys

from PIL import Image

a = sys.argv
Image.open(a[1]).convert("RGB").crop(tuple(int(v) for v in a[3:7])).save(a[2], quality=90)
