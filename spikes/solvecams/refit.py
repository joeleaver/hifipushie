"""refit.py <head tag>: block_in_start's camera fit (blockin.fit_cameras = humanfit_map's camera-only fit) on each of
the benchmark's nine pictures, against the true camera: on the CLASS MEAN (what block_in_start has) and on the TRUE
head (the fit's own error, no shape misfit), with the STATED yaw off by 0 / -5 / -10 / -15 / +10 deg and the lens
prior as shipped (70 mm +- 40 %; 8-click views +- 5 %). -> out/refit_<tag>.json"""
import copy, json, sys
import numpy as np
from hifipushie import blockin as bi, store
import common as C

tag = sys.argv[1]
T = f"sc_{tag}_T"
rt = C.refs(T)
Lt = C.landmarks(T)
bases = {"mean": store.load(f"sc_{tag}_A00")["base"], "true": store.load(T)["base"]}
rec = []
for v, tc in zip(rt["views"], rt["cameras"]):
    for hn, base in bases.items():
        for dy in (0, -5, -10, -15, 10):
            v1 = copy.deepcopy(v)
            v1["yaw"] = float(np.sign(v["yaw"] or 1) * (abs(v["yaw"]) + dy)) if (dy == 0 or abs(v["yaw"]) >= 20) else None
            if v1["yaw"] is None:
                continue
            cam = bi.fit_cameras(base, [v1])[0]
            e = C.cam_err(cam, tc, Lt)
            rec.append({"view": v["name"], "head": hn, "stated_err": dy, **e})
            print(f"{v['name']:4s} on {hn:4s} stated {dy:+3d}: turn {e['view_yaw']:5.1f} " + C.cam_text(e), flush=True)
json.dump(rec, open(f"{C.S}/out/refit_{tag}.json", "w"))
