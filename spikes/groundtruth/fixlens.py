"""fixlens.py <truth model> <start name>: a block-in start on a truth set's pictures with each picture's TRUE lens
told in the PIPELINE'S convention: humanfit_map.lens_prior reads lens_mm as EXIF's FocalLengthIn35mmFilm, i.e. on the
frame's DIAGONAL (f_px = mm / 43.27 * diagonal), while the benchmark's "85 mm" and face_ruler.lens_mm (the CAMERA
lines) count on the picture's WIDTH (f_px = mm / 36 * width): on a 3:4 portrait the two differ by x1.387. gmk.py /
gphone.py first told the width number (the *L00 / gt_ph*_A00 starts: a lens 39 % too long = cameras 39 % too far)."""
import copy, json, sys
import numpy as np
from hifipushie import blockin as bi, store

T, S0 = sys.argv[1], sys.argv[2]
rj = json.loads((store.HOME / T / "human_refs.json").read_text())
sp = store.load(T)
views = []
for v, cam in zip(rj["views"], rj["cameras"]):
    v = copy.deepcopy(v)
    w, h = v["size"]
    v["lens_mm"] = round(float(cam["f"]) * 43.27 / float(np.hypot(w, h)), 1)
    views.append(v)
bd = sp["base"]["body"]
e = bi.start(S0, views, sex="male" if float(bd.get("sex", 1)) >= 0.5 else "female", age=float(bd.get("age", 35)), cameras="refit", replace=True)
print(S0, [v["lens_mm"] for v in views], e["start"]["cameras"])
