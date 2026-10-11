"""tile.py <out.png> <cols> <file[:label]> ...: a quick look sheet of the left-eye crop (C) of fitted-camera shots
(out/<file>.png), labelled; env C="x0,y0,x1,y1" (shot px), Z (zoom, 1)."""
import os
import sys

from PIL import Image, ImageDraw

G = os.environ["G"] + "/out/"
C = tuple(int(x) for x in os.environ.get("C", "860,640,1480,1030").split(","))
Z = float(os.environ.get("Z", "1"))
out, cols = sys.argv[1], int(sys.argv[2])
items = [a.split(":", 1) if ":" in a else (a, a) for a in sys.argv[3:]]
w, h = int((C[2] - C[0]) * Z), int((C[3] - C[1]) * Z)
rows = (len(items) + cols - 1) // cols
S = Image.new("RGB", (cols * w, rows * (h + 26)), "white")
d = ImageDraw.Draw(S)
for i, (f, lab) in enumerate(items):
    x, y = (i % cols) * w, (i // cols) * (h + 26)
    p = G + f + ".png"
    if os.path.exists(p):
        S.paste(Image.open(p).convert("RGB").crop(C).resize((w, h), Image.LANCZOS), (x, y + 26))
    d.text((x + 6, y + 3), lab, fill=(0, 0, 0), font_size=18)
S.save(out if "/" in out else G + out)
print("saved", out, S.size)
