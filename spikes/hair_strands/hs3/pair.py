"""pair.py <model> <out.png> <label=glb> ... [views=close_front,three_quarter] [size=560] [dist=]: GLBs side by side
as an engine draws them: strands | each GLB under alpha test | dithered."""
import os, sys
from PIL import Image, ImageDraw
from hifipushie import hair, store
name, out = sys.argv[1], sys.argv[2]
glbs, kw = [], {}
for a in sys.argv[3:]:
    k, v = a.split("=", 1)
    (kw.__setitem__(k, v) if k in ("views", "size", "dist") else glbs.append((k, v)))
views = tuple(kw.get("views", "close_front,three_quarter").split(","))
size = int(kw.get("size", 560))
dist = float(kw["dist"]) if "dist" in kw else None
spec = store.load(name)
spec["hair"]["style"] = "strands"
rows = []
if dist is None:
    sheet, _, _ = hair.look(name, views=views, size=size, spec=spec, clay=False)
    rows.append(("strands (the groom, EEVEE)", sheet.crop((0, 22, size * len(views), 22 + size))))
for lab, glb in glbs:
    for alpha in ("test", "dither"):
        imgs, _, _ = hair.look_glb(name, glb, views=views, size=size, alpha=alpha, dist=dist)
        r = Image.new("RGB", (size * len(views), size))
        for i, im in enumerate(imgs):
            r.paste(im, (i * size, 0))
        rows.append((f"{lab}: alpha {alpha}", r))
W = size * len(views)
img = Image.new("RGB", (W, len(rows) * (size + 18)), (30, 31, 35))
d = ImageDraw.Draw(img)
for i, (lab, im) in enumerate(rows):
    d.text((6, i * (size + 18) + 3), lab, fill=(240, 220, 160))
    img.paste(im, (0, i * (size + 18) + 18))
img.save(out if os.path.isabs(out) else os.path.join(os.environ["HR"], out))
