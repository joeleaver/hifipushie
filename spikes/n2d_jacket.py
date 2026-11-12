"""N2d proof (docs/proposals/step5_rewrite.md): the jacket as RIGID ROLLED PANELS (chain_panels: 8 numbers a panel, no
point free), seams one chain end to end (chain_seams), assembled round the skeleton, dressed on the body, then one
closing projection (chain_assemble). Not wired into GarmentBuild.

  HIFIPUSHIE_HOME=<scratch ws> capped uv run python spikes/n2d_jacket.py <out dir> <loaded.pkl> <start X0.npy>
loaded.pkl: {pat, body, wear}; start: a start per pattern vertex (the tapes' start, N2 run1 X0.npy). Writes X_asm.npy,
X_dress.npy, X.npy (closed), cnet.pkl, report.json."""
import json
import os
import pickle
import subprocess
import sys
import time

import numpy as np

from hifipushie import chain_assemble as ca, chain_lay, chain_settle, resources
from hifipushie import chain_solve_plies as cp
from hifipushie.chain_holds import read as holds_read
from hifipushie.chain_lay_net import chain_network
from hifipushie.chain_net import Network
from hifipushie.chain_panels import Panels
from hifipushie.chain_seams import carry_rows, join_seams, runs

out, src, start = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
d = pickle.load(open(src, "rb"))
pat, body, plan = d["pat"], d["body"], d["wear"]
log = lambda m: print(m, flush=True)
up = lambda: subprocess.run(["uptime"], capture_output=True, text=True).stdout.strip()


def followers_on(cnet, X, follow, skip, contact):
    """Followers sewn to nothing bound on their hosts (chain_solve_plies.bind), a layer in."""
    sign = {p: chain_lay._out_sign(cnet, p, np.nan_to_num(X), contact) for p in set(follow.values())}
    for p in skip:
        b = cp.bind(cnet, {p: follow[p]}, {p: 1}, sign)[0]
        P = (b["w"][:, :, None] * X[b["tri"]]).sum(1) + b["d"][:, None] * cp.normals(X, b["tri"], b["hostF"])
        X[b["ids"]] = P
    return X


with resources.heavy("n2d panels jacket", gb=3, kind="chain_build", log=log):
    t0 = time.time()
    rep = {"uptime": [up()]}
    rn = runs(pat.M)
    M2, st2, bd2, nw = join_seams(pat.M, pat.stiff, pat.bend)
    X0 = carry_rows(np.load(start), nw)
    net = Network(M2, st2, bd2)
    cnet, keep = chain_network(net)
    rep["seams_joined"] = {"runs": len(rn), "points_added": int(len(nw)), "sew_pairs": [int(len(pat.M["sew"])),
                                                                                         int(len(M2["sew"]))]}
    other = {cnet.names[cnet.piece[a]] for a, b in cnet.sew if cnet.piece[a] != cnet.piece[b]}
    other |= {cnet.names[cnet.piece[b]] for a, b in cnet.sew if cnet.piece[a] != cnet.piece[b]}
    skip = [p for p in cnet.names if p not in other]
    h = holds_read(net)
    follow = {**h.plies, **h.layers, **h.inside}
    pan = Panels(cnet, plan, skip)
    TH0 = pan.fit_start(X0[keep])
    Xs = pan.positions(TH0)
    ok = ~np.isnan(Xs[:, 0])
    rep.update(points=int(cnet.n), panels=pan.n, unknowns=pan.n * 8, skipped=skip, follow={p: follow.get(p) for p in skip},
               start_fit_rms_mm=round(float(np.sqrt(((Xs[ok] - X0[keep][ok]) ** 2).sum(1).mean())) * 1e3, 1),
               start=ca.reads(pan, TH0))
    log(json.dumps({k: rep[k] for k in ("seams_joined", "panels", "unknowns", "skipped", "start_fit_rms_mm")}))
    ties = chain_lay.tie_pairs(cnet, plan)
    segs = chain_settle.skeleton(body)
    t1 = time.time()
    TH, rd = ca.assemble(pan, TH0, segs, ties, log=log)
    rep["assemble"] = rd
    Xa, _ = ca.nodes_of(pan, TH)
    Xa = followers_on(cnet, pan.positions(TH), follow, skip, body.contact)
    rep["assemble"]["links"] = ca.links_pct(cnet, Xa)
    np.save(os.path.join(out, "X_asm.npy"), Xa)
    pickle.dump({"keep": keep, "cnet": cnet, "TH0": TH0, "TH": TH}, open(os.path.join(out, "cnet.pkl"), "wb"))
    log(json.dumps({"assemble": {k: rd[k] for k in ("cost", "seconds", "seam_gaps_mm", "hinges")}}, default=str)[:3000])
    t2 = time.time()
    pulls = chain_settle.girth_pulls(cnet, np.nan_to_num(Xa, nan=1e3))
    TH2, rd2 = ca.dress(pan, TH, body.contact, pulls, ties, log=log, sub=2)
    rep["dress"] = rd2
    Xd = followers_on(cnet, pan.positions(TH2), follow, skip, body.contact)
    rep["dress"]["links"] = ca.links_pct(cnet, Xd)
    rep["dress"]["tapes_mm"] = chain_settle.pull_report(Xd, pulls)
    np.save(os.path.join(out, "X_dress.npy"), Xd)
    log(json.dumps({"dress": {k: rd2[k] for k in ("cost", "seconds", "seam_gaps_mm", "hinges", "inside")}},
                   default=str)[:3000])
    t3 = time.time()
    Xn, _ = ca.nodes_of(pan, TH2)
    Xn = followers_on(cnet, np.where(np.isnan(Xd), Xn, Xn), follow, skip, body.contact)
    Xc, rd3 = ca.close(cnet, Xn, body.contact, log=None)
    rep["close"] = rd3
    rep["close"]["tapes_mm"] = chain_settle.pull_report(Xc, pulls)
    rep["close"]["measures"] = chain_lay.measures(cnet, Xc, plan, body.contact)
    np.save(os.path.join(out, "X.npy"), Xc)
    rep["seconds"] = {"setup": round(t1 - t0, 1), "assemble": round(t2 - t1, 1), "dress": round(t3 - t2, 1),
                      "close": round(time.time() - t3, 1)}
    rep["uptime"].append(up())
    log(json.dumps({"close": {k: rd3[k] for k in ("moved_mm", "links_pct")}, "seconds": rep["seconds"]}))
json.dump(rep, open(os.path.join(out, "report.json"), "w"), indent=1, default=str)
