"""cmp_locks.py <model> <tag>: a hash of the model's hair job (style as saved) and a 2-view look saved as raw arrays."""
import hashlib, json, sys, os
import numpy as np
import hifipushie
from hifipushie import hair, store
name, tag = sys.argv[1], sys.argv[2]
spec = store.load(name)
j = hair.job(name, spec)
h = hashlib.sha1()
h.update(json.dumps(j["locks"], sort_keys=True, default=float).encode())
z = np.load(j["cap"])
for k in sorted(z.files):
    h.update(k.encode()); h.update(np.ascontiguousarray(z[k]).tobytes())
h.update(json.dumps(j["look"], sort_keys=True).encode())
print(tag, "code", os.path.dirname(hifipushie.__file__), "style", spec["hair"].get("style", "locks"), "locks", len(j["locks"]), "job sha", h.hexdigest()[:16], "keys", sorted(j))
sheet, sec, fr = hair.look(name, views=("front", "three_quarter", "back"), size=320, spec=spec)
np.save(f"scratchpad/hs/cmp_{tag}.npy", np.asarray(sheet))
sheet.save(f"scratchpad/hs/cmp_{tag}.png")
