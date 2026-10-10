"""profdiag.py <model> [out png]: the profile view: the photo's auto contour (outl.profile_auto, red), the model's
envelope vertices through the stored camera (green), its clicked points (blue) and the model's projected lm68 (yellow)."""
import json
import sys

import numpy as np
from PIL import Image, ImageDraw

from hifipushie import headfit

headfit.N = 170
import joint2 as J2  # noqa: E402
import outl  # noqa: E402
from hifipushie import humanfit, store  # noqa: E402

m = sys.argv[1]
sp = store.load(m)
refs = json.loads((store.HOME / m / "human_refs.json").read_text())
vi = [i for i, v in enumerate(refs["views"]) if abs(float(v.get("yaw", 0))) > 70][0]
v, cam = refs["views"][vi], refs["cameras"][vi]
st = humanfit.state(sp["base"])
o = outl.profile_auto(v, step=3)
env = J2.envelope(st, cam, o)
img = Image.open(v["image"]).convert("RGB")
d = ImageDraw.Draw(img)
d.line([tuple(p) for p in o], fill=(255, 0, 0), width=2)
px = humanfit.project(cam, env["X"])
for p in px:
    d.ellipse([p[0] - 2, p[1] - 2, p[0] + 2, p[1] + 2], fill=(0, 200, 0))
for k, p in (v.get("points") or {}).items():
    d.ellipse([p[0] - 4, p[1] - 4, p[0] + 4, p[1] + 4], outline=(0, 0, 255), width=2)
L = humanfit.project(cam, st["L"][:68])
for p in L:
    d.ellipse([p[0] - 2, p[1] - 2, p[0] + 2, p[1] + 2], fill=(230, 200, 0))
print("points", v.get("points"), "cam yaw", cam.get("yaw"), "n contour", len(o), "n env", len(px))
img.save(sys.argv[2] if len(sys.argv) > 2 else "/tmp/prof.png")
