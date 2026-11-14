"""D2 step 2: N2j's panel start moved OUT of the body by the panels' own numbers (chain_panels.Panels.outside), the
plies bound on their hosts as N2j does. Writes <out>/X_start.npy + cnet.pkl (d1_where.py reads them as a run dir) and
start.json: points inside / under the gap (before, after), links against their cut, seams' start distance.

  HIFIPUSHIE_HOME=<scratch ws> capped uv run python spikes/d2_start.py <out> <loaded.pkl> <n2j run dir>"""
import json
import os
import pickle
import sys
import time

import numpy as np

from hifipushie import chain_assemble as ca
from hifipushie import chain_lay, panel_start, resources
from hifipushie import chain_solve_plies as cp
from hifipushie.chain_core import GAP
from hifipushie.chain_holds import read as holds_read
from hifipushie.chain_net import Network
from hifipushie.chain_panels import Panels
from hifipushie.chain_seams import join_seams

out, src, run = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
d = pickle.load(open(src, "rb"))
pat, body, plan = d["pat"], d["body"], d["wear"]
g = pickle.load(open(os.path.join(run, "cnet.pkl"), "rb"))
cnet, keep, TH0 = g["cnet"], g["keep"], g["TH0"]
log = lambda m: print(m, flush=True)
T_START = time.time()


def contact_read(X, ids=None):
    ok = ~np.isnan(X[:, 0]) if ids is None else ids
    s = body.contact.query(X[ok])[0]
    by = {}
    for p in np.unique(cnet.piece[ok][s < GAP]):
        by[cnet.names[p]] = int(((cnet.piece[ok] == p) & (s < GAP)).sum())
    return {"inside": int((s < 0).sum()), "under_gap": int((s < GAP - 1e-5).sum()), "deepest_mm": round(float(-s.min()) * 1e3, 1),
            "under_gap_by_piece": by}


def seams(X):
    gp = np.linalg.norm(X[cnet.sew[:, 0]] - X[cnet.sew[:, 1]], axis=1) * 1e3
    return {"mean_mm": round(float(np.nanmean(gp)), 1), "max_mm": round(float(np.nanmax(gp)), 1)}


with resources.heavy("d2 start", gb=3, kind="chain_build", log=log):
    t0 = time.time()
    M2, st2, bd2, _ = join_seams(pat.M, pat.stiff, pat.bend)
    net = Network(M2, st2, bd2)
    other = {cnet.names[cnet.piece[x]] for a, b in cnet.sew if cnet.piece[a] != cnet.piece[b] for x in (a, b)}
    skip = [p for p in cnet.names if p not in other]
    h = holds_read(net)
    follow = {**h.plies, **h.layers, **h.inside}
    Xs, epulls, srd = panel_start.starts(cnet, keep, body, skip, spin={p: 0.0 for p in cnet.names})
    OUT = chain_lay.outside(cnet, np.nan_to_num(Xs), body.contact, [p for p in cnet.names if p not in skip])
    pan = Panels(cnet, plan, skip, OUT)
    for h_ in pan.hinges:  # (unturned, as N2j's start)
        h_["turn_deg"] = 0.0
    X_old = pan.positions(TH0)
    rep = {"before": {"contact": contact_read(X_old), "seams": seams(X_old), "links": ca.links_pct(cnet, X_old)}}
    log(f"before: {rep['before']}")
    t1 = time.time()
    TH, left = pan.outside(TH0, body.contact, log=log)
    rep["seconds_outside"] = round(time.time() - t1, 1)
    X = pan.positions(TH)
    rep["left_under_gap"] = left
    sign = chain_lay.outside(cnet, np.nan_to_num(X), body.contact, sorted(set(follow.values())))
    k_of = {p: (1 + sum(1 for q, hh in h.layers.items() if hh == follow[p])) if p in h.inside else 1 for p in follow}
    plies = cp.bind(cnet, {p: follow[p] for p in skip}, k_of, sign)
    for b in plies:
        if np.isnan(X[b["ids"], 0]).any():
            P = (b["w"][:, :, None] * X[b["tri"]]).sum(1) + b["d"][:, None] * cp.normals(X, b["tri"], b.get("hostF"))
            X[b["ids"]] = np.where(np.isnan(X[b["ids"]]), P, X[b["ids"]])
    shell = ~np.isin(cnet.piece, [cnet.pid(p) for p in skip])
    rep["after"] = {"contact_panels": contact_read(X, shell), "contact_all": contact_read(X), "seams": seams(X),
                    "links": ca.links_pct(cnet, X)}
    mv = np.linalg.norm(X[shell] - X_old[shell], axis=1) * 1e3
    rep["after"]["moved_mm"] = {"mean": round(float(mv.mean()), 1), "max": round(float(mv.max()), 1)}
    log(f"after: {rep['after']}")
    np.save(os.path.join(out, "X_start.npy"), X)
    pickle.dump({"keep": keep, "cnet": cnet, "TH0": TH}, open(os.path.join(out, "cnet.pkl"), "wb"))
    rep["seconds"] = round(time.time() - t0, 1)
json.dump(rep, open(os.path.join(out, "start.json"), "w"), indent=1, default=str)
