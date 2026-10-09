"""wid.py <src> <dst> [strength 0..1]: widths toward the front picture by humanfit.fit_outline: the outline is the
detector's face oval below the eyes (cheek, jaw, chin) on the FRONT picture only (the turned views are not one
projection). strength < 1 moves the outline that share of the way from the model's own silhouette (a partial step)."""
import copy, json, sys

import numpy as np
from PIL import Image

from hifipushie import humanfit, likeness as lk, store

src, dst = sys.argv[1], sys.argv[2]
k = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
sp = store.load(src)
refs = json.loads((store.HOME / src / "human_refs.json").read_text())
v0 = refs["views"][0]
img = Image.open(v0["image"]).convert("RGB")
P = lk.detect_region(img, (0, 0, img.size[0], img.size[1]), info=True)["P"][:, :2]
eye_y = 0.5 * (P[33, 1] + P[263, 1])
ov = [P[i].tolist() for i in lk.OVAL if P[i, 1] > eye_y + 5]
views = [dict(v) for v in refs["views"]]
views[0] = {**v0, "outline": ov}
for v in views[1:]:
    v.pop("outline", None)
if k < 1.0:
    views[0]["outline_weight"] = k
nb, rep = humanfit.fit_outline(copy.deepcopy(sp["base"]), views, refs["cameras"])
for r in rep.get("rounds", []):
    print({a: (round(b, 2) if isinstance(b, float) else b) for a, b in r.items() if not isinstance(b, (list, dict))})
st0, st1 = humanfit.state(sp["base"]), humanfit.state(nb)
print(humanfit.verdict(humanfit.integrity(nb, st1, st0))[:300])
for m in ("face_width", "jaw_width", "chin_width", "face_height"):
    print(m, round(st0["measures"][m], 1), "->", round(st1["measures"][m], 1))
store.save(dst, {**copy.deepcopy(sp), "base": nb}, f"tess: {src} + fit_outline (front oval below the eyes) k={k}")
(store.HOME / dst / "human_refs.json").write_text((store.HOME / src / "human_refs.json").read_text())
print("saved", dst)
