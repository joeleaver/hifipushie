"""eyeshot.py <model> <tag> [json patch]: the face stage (garrett3 stage.py) of <model>, optionally with a deep-merged
JSON patch on its spec (saved as model _ed_<tag>), rendered through the front reference's fitted camera: the
front close-up (brows to chin, as facesheet.py) and a left-eye crop (4x), each beside the reference's same crop.
Writes $E/out/<tag>_face.png, <tag>_eye.png (reference | ours), and <tag>_eye_ours.png.
ENV: EXPO (-0.1), PX (640), CLAY=1 (flat grey material)."""
import copy
import json
import os
import shutil
import sys

import numpy as np
from PIL import Image

import stage
from hifipushie import store

name, tag = sys.argv[1], sys.argv[2]
patch = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
OUT = os.environ.get("E", "/mnt/data/hifipushie/eyedetail") + "/out"
PX = int(os.environ.get("PX", "640"))


def merge(a, b):
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(a.get(k), dict):
            merge(a[k], v)
        elif v is None:
            a.pop(k, None)
        else:
            a[k] = v
    return a


src = name
refs = json.loads((store.HOME / name / "human_refs.json").read_text())
if patch is not None:
    spec = merge(copy.deepcopy(store.load(name)), patch)
    name = f"_ed_{tag}"
    store._dir(name).mkdir(parents=True, exist_ok=True)
    (store._dir(name) / "spec.json").write_text(json.dumps(spec, indent=1))
    shutil.copy(store.HOME / src / "human_refs.json", store._dir(name) / "human_refs.json")
    pj = store.HOME / src / "pose.json"
    if pj.exists():
        shutil.copy(pj, store._dir(name) / "pose.json")
LIGHT = {**stage.FRONT_LIGHT, "exposure": float(os.environ.get("EXPO", "-0.1"))}
v, cam = refs["views"][0], refs["cameras"][0]
U = np.array(list(v["points"].values()), float)
lo, hi = U.min(0), U.max(0)
s = 0.95 * (hi - lo)[0]
c = np.array([0.5 * (lo[0] + hi[0]), lo[1] + 0.55 * (hi[1] - lo[1])])
zb = [c[0] - s / 2, c[1] - s / 2, c[0] + s / 2, c[1] + s / 2]
# the subject's left eye = picture right: from the outer corners (68-point 36 / 45)
P = v["points"]
a, b = np.asarray(P["lm45"], float), np.asarray(P["lm36"], float)
ec = a + 0.17 * (b - a)
keys = ["lm45", "lm36"]
es = 0.3 * s
eb = [ec[0] - es / 2, ec[1] - es / 2, ec[0] + es / 2, ec[1] + es / 2]
frames = [stage.fitted_frame(cam, zb, "zoom"), stage.fitted_frame(cam, eb, "eye")]
shots = stage.shoot(name, frames, LIGHT, size=PX, hair_on=False, flat=os.environ.get("CLAY") == "1")
img = Image.open(v["image"]).convert("RGB")
for fn, box in (("zoom", zb), ("eye", eb)):
    ref = img.crop(tuple(int(round(x)) for x in box)).resize((PX, PX), Image.LANCZOS)
    S = Image.new("RGB", (2 * PX, PX))
    S.paste(ref, (0, 0))
    S.paste(shots[fn].resize((PX, PX)), (PX, 0))
    S.save(f"{OUT}/{tag}_{'face' if fn == 'zoom' else 'eye'}.png")
    shots[fn].save(f"{OUT}/{tag}_{'face' if fn == 'zoom' else 'eye'}_ours.png")
print("eye box", [round(x) for x in eb], "keys", keys[:6])
print("saved", f"{OUT}/{tag}_face.png", f"{OUT}/{tag}_eye.png")
