"""N2c proof (docs/proposals/step5_rewrite.md): the jacket ASSEMBLED as chains (chain_lay: seams one chain, links at their
cut, loops closed by bends) round its thin skeleton, then SETTLED on the body by bends only as it grows (chain_settle).
Not wired into GarmentBuild.

  HIFIPUSHIE_HOME=<scratch ws> capped uv run python spikes/n2c_jacket.py <out dir> <loaded.pkl> [assemble]
loaded.pkl: {pat, body, wear}. Writes X_asm.npy (assembled), X.npy (settled), cnet.pkl, report.json."""
import json
import os
import pickle
import subprocess
import sys
import time

import numpy as np

from hifipushie import chain_lay, chain_settle, resources
from hifipushie.chain_lay_net import chain_network
from hifipushie.chain_net import Network

out, src = sys.argv[1], sys.argv[2]
only = len(sys.argv) > 3 and sys.argv[3] == "assemble"
os.makedirs(out, exist_ok=True)
d = pickle.load(open(src, "rb"))
pat, body, plan = d["pat"], d["body"], d["wear"]
log = lambda m: print(m, flush=True)
up = lambda: subprocess.run(["uptime"], capture_output=True, text=True).stdout.strip()
with resources.heavy("n2c assemble jacket", gb=3, kind="chain_build", log=log):
    t0 = time.time()
    rep = {"uptime": [up()]}
    net = Network(pat.M, pat.stiff, pat.bend)
    cnet, keep = chain_network(net)
    thin = chain_settle.grown(body, chain_settle.ASSEMBLE_S)
    t1 = time.time()
    S = chain_lay.lay(net, cnet, keep, body, plan, frame=thin.contact)
    t2 = time.time()
    rep.update(points=int(cnet.n), nodes=int(len(np.unique(cnet.root))), assemble_s=round(t2 - t1, 1),
               order=S["order"], start=S["start"], reads=S["reads"],
               folds=[(f["name"], f["turn_deg"], f["toward"]) for f in S["folds"]], ties=len(S["ties"]))
    rep["start"]["on_body"] = chain_lay.measures(cnet, S["X0"], plan, body.contact)
    print(json.dumps({k: rep[k] for k in ("order", "start", "assemble_s")}, default=str)[:6000], flush=True)
    np.save(os.path.join(out, "X_asm.npy"), S["X0"])
    np.save(os.path.join(out, "thin_V.npy"), thin.V)
    pickle.dump({"keep": keep, "cnet": cnet}, open(os.path.join(out, "cnet.pkl"), "wb"))
    json.dump(rep, open(os.path.join(out, "report.json"), "w"), indent=1, default=str)
    if not only:
        X, reps = chain_settle.settle(cnet, S, body, plan, log=log)
        rep["settle"] = reps
        rep["uptime"].append(up())
        rep["settle_s"] = round(time.time() - t2, 1)
        np.save(os.path.join(out, "X.npy"), X)
        for r in reps:
            print(json.dumps({"grown": r["grown"], "measures": r["measures"], "pulls_mm": r["pulls_mm"],
                              "seconds": r["seconds"]}, default=str)[:4000], flush=True)
json.dump(rep, open(os.path.join(out, "report.json"), "w"), indent=1, default=str)
