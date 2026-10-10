"""squintchk.py <model>: does a squint move the detector's canthal tilt? The model neutral and with a squint pose
(base.head.pose lid_upper / lid_lower), each through likeness.compare: canthal tilt, eye opening, photo vs model."""
import copy
import sys

from hifipushie import likeness, store

name = sys.argv[1]
b0 = store.load(name)["base"]
for lab, pose in (("neutral", {}), ("squint 1.5/0.8 mm", {"lid_upper": 0.0015, "lid_lower": 0.0008}),
                  ("squint 2.5/1.2 mm", {"lid_upper": 0.0025, "lid_lower": 0.0012})):
    b = copy.deepcopy(b0)
    b["head"]["pose"] = {**(b["head"].get("pose") or {}), **pose}
    rows = {(r["id"], r["vi"]): r for r in likeness.compare(name, b)["rows"] if r["id"] in ("canthal_tilt", "eye_opening")}
    print(lab, {f"{k[0]}@{k[1]}": (round(r["photo"], 2) if isinstance(r.get("photo"), float) else None,
                                  round(r["model"], 2) if isinstance(r.get("model"), float) else None) for k, r in sorted(rows.items())})
