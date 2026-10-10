"""adopt.py <src head model> <dressed model> <dst> [slider_mode]: dst = the dressed model (skin, hair, paint, brows,
everything) with the src model's whole base.head (identity, sliders, shape, warp, pose...) and its human_refs.json
(cameras). slider_mode is set on the head when given (e.g. "coupled")."""
import copy, json, sys
from hifipushie import store

src, dressed, dst = sys.argv[1:4]
mode = sys.argv[4] if len(sys.argv) > 4 else None
a, d = store.load(src), copy.deepcopy(store.load(dressed))
d["base"]["head"] = copy.deepcopy(a["base"]["head"])
if mode:
    d["base"]["head"]["slider_mode"] = mode
store.save(dst, d, f"tess: {dressed} with {src}'s head" + (f" (slider_mode {mode})" if mode else ""))
(store.HOME / dst / "human_refs.json").write_text((store.HOME / dressed / "human_refs.json").read_text())
print("saved", dst)
