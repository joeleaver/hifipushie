"""iso.py <model> <out.png> [tier=hero] [views=close_front,three_quarter] [size=560]: what makes a pattern in a card
tier: strands | the tier | cap only | cards only | no normal map | unlit base colour | solid by layer."""
import os, sys
from PIL import Image, ImageDraw
from hifipushie import hair, store
name, out = sys.argv[1], sys.argv[2]
kw = dict(a.split("=", 1) for a in sys.argv[3:])
tier = kw.get("tier", "hero")
tier = int(tier) if tier.isdigit() else tier
views = tuple(kw.get("views", "close_front,three_quarter").split(","))
size = int(kw.get("size", 560))
modes = kw.get("modes", "strands,cards,cap_only,cards_only,no_normal,unlit,layers").split(",")
rows = []
for m in modes:
    spec = store.load(name)
    spec["hair"]["style"] = "strands" if m == "strands" else "cards"
    sheet, sec, _ = hair.look(name, views=views, size=size, spec=spec, clay=False,
                              budget=None if m == "strands" else tier, debug=None if m in ("strands", "cards") else m)
    rows.append((f"{m}  {sec}s", sheet.crop((0, 22, size * len(views), 22 + size))))
    print(m, sec, flush=True)
# rows side by side in pairs to keep the sheet readable
W = size * len(views)
cols = int(kw.get("cols", 2))
nr = (len(rows) + cols - 1) // cols
img = Image.new("RGB", (W * cols, nr * (size + 18)), (30, 31, 35))
d = ImageDraw.Draw(img)
for i, (lab, im) in enumerate(rows):
    x, y = (i % cols) * W, (i // cols) * (size + 18)
    d.text((x + 6, y + 3), lab, fill=(240, 220, 160))
    img.paste(im, (x, y + 18))
img.save(out if os.path.isabs(out) else os.path.join(os.environ["HR"], out))
