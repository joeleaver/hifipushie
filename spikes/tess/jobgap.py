"""jobgap.py <job dir> [mm]: exact start clearance of a queued job's cloth from its collider (bodyV0 / bodyT: body + the
garments under it), per piece the closest vertex (cloth_workflow.start_in_standoff)."""
import json, sys, types
import numpy as np
from hifipushie import cloth_workflow

jd = sys.argv[1]
a = np.load(jd + "/in.npz")
J = json.load(open(jd + "/job.json"))
B = types.SimpleNamespace(V=a["bodyV0"] if "bodyV0" in a.files else a["bodyV"], T=a["bodyT"])
M = {"names": J["pieces"], "piece": a["piece"], "uv": a["uv"]}
lim = float(sys.argv[2]) / 1000 if len(sys.argv) > 2 else cloth_workflow.START_STANDOFF
print(cloth_workflow.start_in_standoff(a["X"], M, B, lim), "| offset", (J.get("zozo") or {}).get("body_offset"))
