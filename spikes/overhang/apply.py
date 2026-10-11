"""apply.py <src model> <dst oh_*> [mean=1] [crease=4.7] [overhang=<mm>] [brow=<mm>] [hold=1] [standoff=1.3]: a scratch
model = the source with gnm_fold.fold applied to its identity (mean=1: to GNM's mean, the source only lends its
dressing). Prints gnm_fold.fold_text. The source is never written."""
import copy
import json
import shutil
import sys

import numpy as np

from hifipushie import blockin as bi, gnm_fold as gf, store

src, dst = sys.argv[1:3]
kw = dict(a.split("=", 1) for a in sys.argv[3:])
assert dst.startswith("oh_"), "scratch models are oh_*"
sp = copy.deepcopy(store.load(src))
c0 = np.zeros(170) if kw.get("mean") == "1" else bi.identity(sp)
r = gf.fold(c0, crease=float(kw.get("crease", 4.7)), overhang=float(kw["overhang"]) if "overhang" in kw else None,
            brow=float(kw["brow"]) if "brow" in kw else None, hold=float(kw.get("hold", 1.0)), standoff=float(kw.get("standoff", 1.3)))
print(f"{dst} <- {src}" + (" (GNM mean)" if kw.get("mean") == "1" else "") + f" {kw}")
print(gf.fold_text(r))
bi.set_identity(sp, r["c"])
sp["base"]["head"].pop("expression", None)
sp.pop("hair", None)
d = store._dir(dst)
d.mkdir(parents=True, exist_ok=True)
(d / "spec.json").write_text(json.dumps(sp))
shutil.copy(store._dir(src) / "human_refs.json", d / "human_refs.json")
