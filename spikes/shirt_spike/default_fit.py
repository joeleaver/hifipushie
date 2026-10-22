"""default_fit.py <tag>: wf_simon's shirt from the REPO DEFAULTS only (no overrides): on_form + worn_style; reads."""
import sys, time, pickle
import numpy as np
from hifipushie import store, pattern_form as pf, cloth, garment_pull as gp, resources
t0 = time.time(); tag = sys.argv[1]
spec = store.load("wf_simon"); g = cloth.expanded(spec["cloth"]["shirt"])
with resources.heavy("default fit", gb=6.0):
    res = pf.on_form("wf_simon", "shirt", spec, g=g)
    X0 = np.asarray(res["A"], float); M = res["mesh"]; body = res["body"]
    X, infos = gp.worn_style(M, X0, (np.asarray(body.V, float), np.asarray(body.T, int)), g)
print(f"fit + style {time.time()-t0:.0f}s; ops {len(infos or [])}")
for r in gp.open_collar_rows(M, X): print(f"  {r['status']} {r['id']} | {r['target']} | {r['ours']}")
pickle.dump({"A": X, "mesh": M, "A_info": res.get("A_info"), "bodyV": np.asarray(body.V), "bodyF": np.asarray(body.T),
             "at": {k: np.asarray(v).tolist() for k, v in body.at.items() if np.asarray(v).size <= 6}}, open(f"/mnt/data/hifipushie/shirt_spike/{tag}.pkl", "wb"))
