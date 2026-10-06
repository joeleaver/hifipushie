"""dist.py <model> <export dir> <out.png> [alpha=test]: each tier's GLB at the distance it is meant for (camera
fov 30 deg, 400 px frame): hero 0.62 m (bust), main 1.5 m, npc 3 m, far 8 m; views three_quarter, side, back."""
import json, os, sys
from pathlib import Path
from PIL import Image, ImageDraw
from hifipushie import hair
name, d, out = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
kw = dict(a.split("=", 1) for a in sys.argv[4:])
rep = json.loads((d / f"{name}_hair.json").read_text())
views = ("three_quarter", "side", "back")
size = 400
rows = []
for tier, dist in (("hero", 0.62), ("main", 1.5), ("npc", 3.0), ("far", 8.0)):
    if tier not in rep["tiers"]:
        continue
    imgs, _, _ = hair.look_glb(name, rep["tiers"][tier]["glb"], views=views, size=size, alpha=kw.get("alpha", "test"), dist=dist)
    rows.append((f"{tier} at {dist} m ({rep['tiers'][tier]['triangles']} triangles), alpha {kw.get('alpha', 'test')}", imgs))
img = Image.new("RGB", (size * len(views), len(rows) * (size + 18)), (30, 31, 35))
dr = ImageDraw.Draw(img)
for i, (lab, ims) in enumerate(rows):
    dr.text((6, i * (size + 18) + 3), lab, fill=(240, 220, 160))
    for j, im in enumerate(ims):
        img.paste(im, (j * size, i * (size + 18) + 18))
img.save(out if os.path.isabs(out) else os.path.join(os.environ["HR"], out))
