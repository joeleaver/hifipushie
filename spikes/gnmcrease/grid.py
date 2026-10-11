"""grid.py <out> <tag=label>...: single-eye zoom crops [dressed | clay] per tag, 2 tags per row, the photo first. Labels get
the dressed read (readd.json)."""
import json
import sys
from PIL import Image, ImageDraw

G = "/mnt/data/hifipushie/gnmcrease/out/"
rd = json.load(open(G + "readd.json"))
box = (0.54, 0.33, 0.96, 0.6)
W, H = 520, 334


def cr(p):
    im = Image.open(p).convert("RGB").resize((1600, 1600))
    return im.crop(tuple(int(v * 1600) for v in box)).resize((W, H), Image.LANCZOS)


cells = []
ph = cr(G + "photo_tess.png")
r = rd.get("photo", {})
cells.append((ph, None, f"Tess photo: line {r.get('tps', 0):.1f} mm, dark {r.get('dark', 0):.2f}"))
for a in sys.argv[2:]:
    t, _, lab = a.partition("=")
    r = rd.get(t, {})
    cells.append((cr(G + f"d_{t}_dressed.png"), cr(G + f"d_{t}_clay.png"),
                  f"{lab or t}: dressed line {r.get('tps', float('nan')):.1f} mm dark {r.get('dark', float('nan')):.2f}"))
ncol = 2
rows = (len(cells) + ncol - 1) // ncol
S = Image.new("RGB", (ncol * 2 * W, rows * (H + 30)), (255, 255, 255))
d = ImageDraw.Draw(S)
for i, (a, b, lab) in enumerate(cells):
    x, y = (i % ncol) * 2 * W, (i // ncol) * (H + 30)
    S.paste(a, (x, y + 30))
    if b is not None:
        S.paste(b, (x + W, y + 30))
    d.text((x + 6, y + 4), lab, fill=(0, 0, 0), font_size=20)
S.save(sys.argv[1])
print("wrote", sys.argv[1])
