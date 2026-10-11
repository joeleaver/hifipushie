"""mk.py <src model> <dst oh_*> <npz with c [, e] | mean>: a scratch model = the source's spec (dressing, body, refs)
with GNM's identity (and the eyes' expression, if the npz has one) replaced. Never touches the source."""
import copy
import json
import shutil
import sys

import numpy as np

from hifipushie import blockin as bi, gnm_controls as gc, store

src, dst, f = sys.argv[1:4]
assert dst.startswith("oh_"), "scratch models are oh_*"
sp = copy.deepcopy(store.load(src))
if f == "mean":
    c, e = np.zeros(170), None
elif f == "same":
    c, e = bi.identity(sp), None
else:
    z = np.load(f)
    c, e = z["c"][:170], (z["e"] if "e" in z.files and np.any(z["e"]) else None)
bi.set_identity(sp, c)
h = sp["base"]["head"]
h.pop("expression", None)
if e is not None:
    names = gc.gnm()["ex_names"]
    h["expression"] = {names[i]: round(float(v), 5) for i, v in enumerate(e) if abs(v) > 1e-6}
sp.pop("hair", None)
d = store._dir(dst)
d.mkdir(parents=True, exist_ok=True)
(d / "spec.json").write_text(json.dumps(sp))
shutil.copy(store._dir(src) / "human_refs.json", d / "human_refs.json")
print("wrote", dst, f"|c| {np.linalg.norm(c):.2f}", f"|e| {np.linalg.norm(e):.2f}" if e is not None else "")
