"""N2b proof (docs/proposals/step5_rewrite.md): the jacket's step-5 CHAINS only (chain_lay_net), laid isometrically
from the edge tapes and their seams (chain_lay), then ONE chain_solve on the chain network. Not wired into GarmentBuild.

  HIFIPUSHIE_HOME=<scratch ws> capped uv run python spikes/n2b_chains_jacket.py <out dir> <loaded.pkl> [start]
loaded.pkl: {pat, body, wear} (chain_garment.load_garment + chain_plan.planned_wear). "start": lay only, no solve."""
import json
import os
import pickle
import subprocess
import sys
import time

import numpy as np

from hifipushie import chain_lay, chain_solve, resources
from hifipushie.chain_lay_net import chain_network
from hifipushie.chain_net import Network

out, src = sys.argv[1], sys.argv[2]
only_start = len(sys.argv) > 3 and sys.argv[3] == "start"
os.makedirs(out, exist_ok=True)
d = pickle.load(open(src, "rb"))
pat, body, plan = d["pat"], d["body"], d["wear"]
log = lambda m: print(m, flush=True)
up = lambda: subprocess.run(["uptime"], capture_output=True, text=True).stdout.strip()
with resources.heavy("n2b chains jacket", gb=3, kind="chain_build", log=log):
    t0 = time.time()
    net = Network(pat.M, pat.stiff, pat.bend)
    cnet, keep = chain_network(net)
    t1 = time.time()
    S = chain_lay.lay(net, cnet, keep, body, plan)
    t2 = time.time()
    rep = {"points": int(cnet.n), "nodes": int(len(np.unique(cnet.root))), "lines_across": int(len(cnet.edges)),
           "faces": int(len(cnet.F)), "net_s": round(t1 - t0, 1), "lay_s": round(t2 - t1, 1), "start": S["start"],
           "reads": S["reads"], "folds": [(f["name"], f["turn_deg"], f["toward"]) for f in S["folds"]],
           "ties": len(S["ties"]), "pulls": [(p["name"], len(p["ids"])) for p in S["pulls"]]}
    print(json.dumps(rep, default=str)[:5000], flush=True)
    np.save(os.path.join(out, "X0.npy"), S["X0"])
    pickle.dump({"keep": keep, "cnet": cnet}, open(os.path.join(out, "cnet.pkl"), "wb"))
    if not only_start:
        rep["uptime"] = [up()]
        X, sr = chain_solve.solve(cnet, S["X0"], body=body, ties=S["ties"], folds=S["folds"], pulls=S["pulls"],
                                  plies=() if "noplies" in sys.argv[3:] else S["plies"], log=log)
        rep["uptime"].append(up())
        rep["solve"] = sr
        np.save(os.path.join(out, "X.npy"), X)
json.dump(rep, open(os.path.join(out, "report.json"), "w"), indent=1, default=str)
if "solve" in rep:
    print(json.dumps(rep["solve"], default=str)[:5000])
