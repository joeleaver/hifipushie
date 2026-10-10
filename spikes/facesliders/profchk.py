"""profchk.py <refs model> <out.jpg>: the auto profile contour (outl.profile_auto) on the profile picture."""
import json
import sys

from PIL import Image, ImageDraw

import outl
from hifipushie import store

refs = json.loads((store.HOME / sys.argv[1] / "human_refs.json").read_text())
v = next(v for v in refs["views"] if abs(float(v.get("yaw", 0))) > 70)
o = outl.profile_auto(v)
im = Image.open(v["image"]).convert("RGB")
d = ImageDraw.Draw(im)
for p in o:
    d.ellipse([p[0] - 3, p[1] - 3, p[0] + 3, p[1] + 3], outline=(255, 0, 0))
lo, hi = o.min(0), o.max(0)
im = im.crop((int(lo[0] - 150), int(lo[1] - 60), int(lo[0] + 350), int(hi[1] + 60)))
im.thumbnail((700, 900))
im.save(sys.argv[2])
print("wrote", sys.argv[2], len(o), "rows", o[0], o[-1])
