"""peek.py <sample dir> <out.png> [n=12] [dots=1] [scale=2]: a contact sheet of a dressing's samples on a grey
backdrop, the labels drawn (visible: green, hidden: red; eyeball points: cyan)."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

d, out = Path(sys.argv[1]), sys.argv[2]
kw = dict(a.split("=") for a in sys.argv[3:])
n, dots, sc = int(kw.get("n", 12)), kw.get("dots", "1") == "1", int(kw.get("scale", 2))
first = int(kw.get("first", 0))
lab = np.load(d / "labels.npz")
files = sorted(d.glob("[0-9]*.png"))[first:first + n]
size = int(lab["size"]) * sc
cols = min(len(files), 6)
rows = (len(files) + cols - 1) // cols
sheet = Image.new("RGB", (cols * size, rows * size), (120, 120, 120))
ns = lab["xy"].shape[1] - 18
for k, f in enumerate(files):
    i = int(f.stem)
    im = Image.open(f).convert("RGBA")
    bg = Image.new("RGBA", im.size, (128, 128, 128, 255))
    im = Image.alpha_composite(bg, im).convert("RGB").resize((size, size), Image.LANCZOS)
    if dots:
        dr = ImageDraw.Draw(im)
        for j, (p, v) in enumerate(zip(lab["xy"][i] * sc, lab["vis"][i])):
            col = (0, 255, 255) if j >= ns and v else ((60, 255, 60) if v else (255, 60, 60))
            dr.ellipse((p[0] - 1.2, p[1] - 1.2, p[0] + 1.2, p[1] + 1.2), fill=col)
    sheet.paste(im, ((k % cols) * size, (k // cols) * size))
sheet.save(out)
print(out, sheet.size)
