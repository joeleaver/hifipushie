"""N2 proof (docs/proposals/step5_rewrite.md): the jacket's step-5 start seeded from its tapes (chain_seed), then ONE
chain_solve with plies / layers as a term. Not wired into GarmentBuild (N3).

  HIFIPUSHIE_HOME=<scratch ws> capped uv run python spikes/n2_seed_jacket.py <out dir> [loaded.pkl]
loaded.pkl: {pat, body, wear} saved from chain_garment.load_garment + chain_plan.planned_wear (the flat mesh and the body
only are read; its positions are dropped by Pattern)."""
import json
import os
import pickle
import subprocess
import sys
import time

import numpy as np

from hifipushie import chain_seed, chain_solve, resources
from hifipushie.chain_net import Network

out = sys.argv[1]
src = sys.argv[2] if len(sys.argv) > 2 else os.path.join(out, "loaded.pkl")
os.makedirs(out, exist_ok=True)
d = pickle.load(open(src, "rb"))
if "wear" not in d:
    from hifipushie import chain_garment as cg, chain_plan, chain_structure as cs
    d["pat"], d["body"], _ = cg.load_garment("garrett", "jacket")
    d["wear"] = chain_plan.planned_wear(cs.load_plan("garrett", "jacket"), None, None)
pat, body, wear = d["pat"], d["body"], d["wear"]
net = Network(pat.M, pat.stiff, pat.bend)
log = lambda m: print(m, flush=True)
with resources.heavy("n2 seed + solve jacket", gb=6, kind="chain_build", log=log):
    t0 = time.time()
    S = chain_seed.seed(net, body, wear)
    t1 = time.time()
    print("seed s", round(t1 - t0, 1), json.dumps(S["reads"])[:3000])
    print("folds", [(f["name"], f["turn_deg"], f["toward"]) for f in S["folds"]])
    print("ties", len(S["ties"]), "pulls", [(p["name"], len(p["ids"])) for p in S["pulls"]])
    np.save(os.path.join(out, "X0.npy"), S["X0"])
    load0 = subprocess.run(["uptime"], capture_output=True, text=True).stdout.strip()
    X, rep = chain_solve.solve(net, S["X0"], body=body, ties=S["ties"], folds=S["folds"], pulls=S["pulls"],
                               plies=S["plies"], log=log)
    load1 = subprocess.run(["uptime"], capture_output=True, text=True).stdout.strip()
np.save(os.path.join(out, "X.npy"), X)
rep["uptime"] = [load0, load1]
rep["seed_seconds"] = round(t1 - t0, 1)
json.dump(rep, open(os.path.join(out, "report.json"), "w"), indent=1, default=str)
print(json.dumps({k: rep[k] for k in rep if k not in ("by_link",)}, default=str)[:6000])
