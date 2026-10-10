"""camscale.py <refs model> <model>: the model's landmarks through each shared camera vs the picture's detector points
(the 68's MediaPipe equivalents): spread ratio and centre offset (px)."""
import json
import sys

import numpy as np

from hifipushie import humanfit, humanfit_map as hm, likeness, store

refm, m = sys.argv[1], sys.argv[2]
refs = json.loads((store.HOME / refm / "human_refs.json").read_text())
sp = json.loads((store.HOME / m / "spec.json").read_text())
st = humanfit.state(sp.get("spec", sp)["base"])
for vi, (v, cam) in enumerate(zip(refs["views"], refs["cameras"])):
    uv = humanfit.project(cam, st["L"][:68])
    det = hm.detector_points(v)
    pts = v.get("points") or {}
    if det is not None:
        ref = det[likeness.MP68]
    else:
        ids = [humanfit.point_index(k) for k in pts]
        ref = np.array(list(pts.values()), float)
        uv = humanfit.project(cam, st["L"][ids])
    print(f"view {vi}: model spread {np.ptp(uv, axis=0).round(1)} vs picture {np.ptp(ref, axis=0).round(1)}; centre "
          f"{uv.mean(0).round(1)} vs {ref.mean(0).round(1)}; cam t {np.round(cam['t'], 3)} f {cam['f']:.0f}")
