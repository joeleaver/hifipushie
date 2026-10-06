"""tiers.py <model> <out.png> [views=..] [size=..]: the strands (EEVEE) over each card tier, same views."""
import os, sys
from PIL import Image, ImageDraw
from hifipushie import hair, store
name, out = sys.argv[1], sys.argv[2]
kw = dict(a.split("=", 1) for a in sys.argv[3:])
views = tuple(kw.get("views", "wide_r,back_quarter,close_front,three_quarter").split(","))
size = int(kw.get("size", 480))
rows = kw.get("rows", "strands,hero,main,npc,far").split(",")
spec0 = store.load(name)
strips, labels = [], []
for r in rows:
    spec = store.load(name)
    spec["hair"]["style"] = "strands" if r == "strands" else "cards"
    j = hair.job(name, spec, budget=None if r == "strands" else r)
    info = "" if r == "strands" else f'{j["cards"]["triangles"] + j["cards"]["cap_triangles"]} triangles ({j["cards"]["cards"]} cards, cap {j["cards"]["cap_triangles"]}; {j["cards"]["budget"]})'
    sheet, sec, fr = hair.look(name, views=views, size=size, spec=spec, clay=False, budget=None if r == "strands" else r)
    strips.append(sheet.crop((0, 22, size * len(views), 22 + size)))
    st = [l for l in fr if "strands" in l]
    labels.append(f"{r}: {info or (st[0][:160] if st else '')}   {sec}s")
    print(labels[-1], "bare", hair.look.mass_share)
W = size * len(views)
img = Image.new("RGB", (W, (size + 20) * len(rows)), (30, 31, 35))
d = ImageDraw.Draw(img)
for i, (s_, lab) in enumerate(zip(strips, labels)):
    img.paste(s_, (0, i * (size + 20) + 20))
    d.text((6, i * (size + 20) + 4), lab, fill=(240, 220, 160))
img.save(os.path.join(os.environ["HR"], out))
