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
s = 0.95 * (hi - lo)[0] * float(os.environ.get("ZOOM_SCALE", "1"))
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
crops = [("zoom", zb, v), ("eye", eb, v)]
if len(refs["views"]) > 1 and {"lm36", "lm45"} <= set(refs["views"][1]["points"]):  # the three-quarter view's eye
    v1 = refs["views"][1]
    a1, b1 = np.asarray(v1["points"]["lm45"], float), np.asarray(v1["points"]["lm36"], float)
    e1 = a1 + 0.2 * (b1 - a1)
    s1 = 0.75 * float(np.linalg.norm(b1 - a1))
    qb = [e1[0] - s1 / 2, e1[1] - s1 / 2, e1[0] + s1 / 2, e1[1] + s1 / 2]
    frames.append(stage.fitted_frame(refs["cameras"][1], qb, "q"))
    crops.append(("q", qb, v1))
shots = stage.shoot(name, frames, LIGHT, size=PX, hair_on=False, flat=os.environ.get("CLAY") == "1",
                    layer=os.environ.get("LAYER") or None)
for fn, box, vv in crops:
    img = Image.open(vv["image"]).convert("RGB")
    ref = img.crop(tuple(int(round(x)) for x in box)).resize((PX, PX), Image.LANCZOS)
    S = Image.new("RGB", (2 * PX, PX))
    S.paste(ref, (0, 0))
    S.paste(shots[fn].resize((PX, PX)), (PX, 0))
    lab = {"zoom": "face", "eye": "eye", "q": "eyeq"}[fn]
    S.save(f"{OUT}/{tag}_{lab}.png")
    shots[fn].save(f"{OUT}/{tag}_{lab}_ours.png")
print("eye box", [round(x) for x in eb], "keys", keys[:6])
print("saved", f"{OUT}/{tag}_face.png", f"{OUT}/{tag}_eye.png")
