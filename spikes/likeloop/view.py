"""view.py <out.jpg> <x0,y0,x1,y1 fractions of a tile> <w> <sheet.png>...: photo tile of the first sheet, then each
sheet's model tile, cropped to the same box, w px wide each, side by side (to compare rounds in one small image)."""
import sys

from PIL import Image

PX, TOP = 520, 34
out, fr, w = sys.argv[1], [float(v) for v in sys.argv[2].split(",")], int(sys.argv[3])
sheets = [Image.open(p) for p in sys.argv[4:]]
box = lambda col: (col * PX + fr[0] * PX, TOP + fr[1] * PX, col * PX + fr[2] * PX, TOP + fr[3] * PX)  # noqa: E731
tiles = [sheets[0].crop(box(0))] + [s.crop(box(1)) for s in sheets]
h = int(w * tiles[0].size[1] / tiles[0].size[0])
S = Image.new("RGB", (w * len(tiles), h))
for i, t in enumerate(tiles):
    S.paste(t.resize((w, h), Image.LANCZOS), (i * w, 0))
S.save(out, quality=85)
