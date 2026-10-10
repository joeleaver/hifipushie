"""mkt2.py <dst> <head model> <dressed model>: the CURRENT dressing (the dressed model's whole spec: skin, paint, hair,
base.cornea, eyes, lashes, lidfold...) with the head model's SHAPE: base.head's identity, sliders, pose, warp,
shape, dimorphism, eye size, lip seal (its features / seed / spread dropped: the identity is explicit). The head
model's refs (cameras)."""
import json
import shutil
import sys

from hifipushie import store

dst, head, src = sys.argv[1:4]
sp = json.loads((store.HOME / src / "spec.json").read_text())
sp = sp.get("spec", sp)
hb = json.loads((store.HOME / head / "spec.json").read_text())
hb = hb.get("spec", hb)["base"]["head"]
h = sp["base"]["head"]
for k in ("seed", "spread", "features"):
    h.pop(k, None)
for k in ("identity", "sliders", "pose", "warp", "shape", "dimorphism", "eyes", "lip_seal", "slider_mode"):
    if k in hb:
        h[k] = hb[k]
    else:
        h.pop(k, None)
h["sliders"] = {k: v for k, v in (h.get("sliders") or {}).items()
                if k not in ("eye_crease_height", "eye_crease_depth", "eye_platform", "eye_hood", "eye_hood_lateral", "age_lid_fold")}
d = store.HOME / dst
d.mkdir(exist_ok=True)
(d / "spec.json").write_text(json.dumps(sp, indent=1))
shutil.copy(store.HOME / head / "human_refs.json", d / "human_refs.json")
for f in (store.HOME / src).glob("hair_*.npz"):
    shutil.copy(f, d / f.name)
print("wrote", d)
