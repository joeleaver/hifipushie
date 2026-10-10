"""storeprof.py <refs model> <traces model>: outl.profile_auto of the true profile stored as the traces model's
'profile' line on that picture (likeness' contour items read it), the auto contour marked by."""
import json
import sys

import outl
from hifipushie import likeness_shape as ls, store

refs = json.loads((store.HOME / sys.argv[1] / "human_refs.json").read_text())
v = next(v for v in refs["views"] if abs(float(v.get("yaw", 0))) > 70)
o = outl.profile_auto(v, step=4)
ls.set_points(sys.argv[2], v["image"], lines={"profile": o.tolist()},
              by="facesliders outl.profile_auto: skin against the plain background, brow to under the chin, 2026-10-09")
print("stored", len(o), "points")
