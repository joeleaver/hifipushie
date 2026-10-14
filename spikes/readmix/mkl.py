"""mkl.py <k> <sex> <age>: rm_<k>_L00 = block_in_start on groundtruth's set A pictures with each picture's TRUE lens told
in lens_prior's convention (35 mm equivalent on the frame's DIAGONAL: f / diag * 43.27). groundtruth's own "L" sets tell
f / width * 36: on these portrait crops that is a lens 39 % too long (found here: its told-lens chains start +28..+40 %
far and stay there)."""
import copy, json, sys
import numpy as np
from hifipushie import blockin as bi, store

k, sex, age = sys.argv[1], sys.argv[2], float(sys.argv[3])
rj = json.loads((store.HOME / f"gt_{k}_AT" / "human_refs.json").read_text())
vv = [copy.deepcopy(v) for v in rj["views"]]
for v, cam in zip(vv, rj["cameras"]):
    w, h = cam["size"]
    v["lens_mm"] = round(float(cam["f"]) / float(np.hypot(w, h)) * 43.27, 1)
e = bi.start(f"rm_{k}_L00", vv, sex=sex, age=age, cameras="refit", replace=True)
print(k, [v["lens_mm"] for v in vv], e["start"]["cameras"])
