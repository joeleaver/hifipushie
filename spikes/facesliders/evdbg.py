"""evdbg.py <model>: what evidence each view gives (rows, detector indices, oval rows)."""
import json
import sys

import numpy as np

import joint as J0
from hifipushie import humanfit, humanfit_map as hm, likeness, store

m = sys.argv[1]
refs = json.loads((store.HOME / m / "human_refs.json").read_text())
st = humanfit.state(store.load(m)["base"])
views = hm._resolve(st, [dict(v) for v in refs["views"]])
for v, e in zip(views, J0.evidence(st, views)):
    mi = np.asarray(e.get("mp_idx", []))
    print(v.get("yaw"), e["src"], "rows", len(e["X"]), "mp_idx", len(mi), "oval", int(np.isin(mi, likeness.OVAL).sum()),
          "sig median", round(float(np.median(e["sig"])), 2))
