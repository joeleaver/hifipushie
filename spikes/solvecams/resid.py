"""resid.py <out tag> <model> ..: every read's residual AT a model with its cameras (dense landmarks evaluated too,
whether or not the chain used them): per type and view n, rms mm, rms in sigmas -> out/resid_<tag>.json"""
import json, sys
import numpy as np
from hifipushie import face_ruler as fr
import common as C

fr.DENSE = True
out = {}
for name in sys.argv[2:]:
    rj = C.refs(name)
    b0 = rj.get("blockin") or {}
    head, views, notes = fr.reference_views(name, lids=True, lips=True, parse="auto", kinds=b0.get("kinds"), readers=b0.get("readers"))
    for v in views:
        v["extra_obs"] = v["extra"](head, v)
    obs = fr.observe(head, views)
    r = {}
    for ob in obs:
        r.setdefault(f"{ob['type']} {ob['view']}", []).append((ob["o"], ob["sig"]))
    out[name] = {k: {"n": len(v), "mm": float(np.sqrt(np.mean([a * a for a, _ in v]))), "sig": float(np.sqrt(np.mean([(a / s) ** 2 for a, s in v]))),
                     "bias": float(np.mean([a for a, _ in v]))} for k, v in r.items()}
    print(name, " ".join(f"{k}: {x['mm']:.2f}" for k, x in sorted(out[name].items())), flush=True)
json.dump(out, open(f"{C.S}/out/resid_{sys.argv[1]}.json", "w"))
