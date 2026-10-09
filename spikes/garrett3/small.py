"""small.py <sheet.png> <out stem> [rows=4]: the sheet cut into a top half (matched views) and a bottom half (six
views), downscaled for a look."""
import sys

from PIL import Image

c = Image.open(sys.argv[1]).convert("RGB")
W, H = c.size
h2 = H // 2
for tag, box in (("top", (0, 0, W, h2)), ("bot", (0, h2, W, H))):
    t = c.crop(box)
    k = 1728 / t.size[0]
    t.resize((1728, int(t.size[1] * k)), Image.LANCZOS).save(f"{sys.argv[2]}_{tag}.jpg", quality=88)
