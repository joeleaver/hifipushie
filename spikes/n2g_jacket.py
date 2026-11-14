"""N2g proof (docs/proposals/step5_rewrite.md): N2f's START (rolled panels placed from their own tapes, folds exact by
construction: panel_start + chain_panels.fit_start) closed by the FLEXIBLE chain solve (chain_solve on the chains-only
network: links hard at their cut, bends free, folds at plan, tapes pulling, followers bound on their hosts, contact).
No rigid assembly. Seams close by CONTINUATION: the network unsewn (each side its own nodes), each sew pair pulled to
its pair's current midpoint at rising weight (SEAM_W), each stage a full solve warm-started from the last; then the
sewn network (one node per seam point) solved from there (a small merge jump instead of N2b's 10-30 cm one).

  HIFIPUSHIE_HOME=<scratch ws> capped uv run python spikes/n2g_jacket.py <out> <loaded.pkl> [measure]
The start as N2f's (panel_start.starts, Panels.fit_start), each girth piece's way round read from its seams. measure:
the start's numbers only. Writes X_start.npy, X_stage<k>.npy, X.npy (solved), cnet.pkl, report.json."""
import copy
import json
import os
import pickle
import subprocess
import sys
import time

import numpy as np

from hifipushie import chain_lay, chain_settle, panel_start, resources
from hifipushie import chain_solve as cs
from hifipushie import chain_solve_plies as cp
from hifipushie.chain_holds import read as holds_read
from hifipushie.chain_lay_net import chain_network
from hifipushie.chain_net import Network
from hifipushie.chain_panels import Panels
from hifipushie.chain_seams import join_seams

SEAM_W = (0.1, 1.0, 10.0)  # per REF (1 cm): the seam pulls' weights, stage by stage, before the sewn solve

out, src = sys.argv[1:3]
only_measure = "measure" in sys.argv[3:]
os.makedirs(out, exist_ok=True)
d = pickle.load(open(src, "rb"))
pat, body, plan = d["pat"], d["body"], d["wear"]
log = lambda m: print(m, flush=True)
up = lambda: subprocess.run(["uptime"], capture_output=True, text=True).stdout.strip()


def unsewn(c):
    """The same chains with every seam cut: each side its own nodes and its own links at its own cut."""
    u = copy.copy(c)
    u.root = np.arange(c.n)
    u.sew = np.zeros((0, 2), np.int64)
    u.link_i, u.link_j = c.chain_v[:, 0].copy(), c.chain_v[:, 1].copy()
    u.link_L = np.asarray(c.chain_L, float).copy()
    u.link_cut = np.c_[u.link_L, u.link_L]
    u.link_of_chain = np.arange(len(u.link_L))
    return u


def seam_read(c, X, X0=None):
    """{'a ~ b': [mean, max] mm} per seam: the gap between its two sides at X; with X0, how far each side moved from
    X0 to where it is (sewn: the shared node)."""
    out_ = {}
    for a, b in c.sew:
        k = " ~ ".join(sorted((c.names[c.piece[a]], c.names[c.piece[b]])))
        v = [np.linalg.norm(X[a] - X[b])] if X0 is None else [np.linalg.norm(X[a] - X0[a]), np.linalg.norm(X[b] - X0[b])]
        out_.setdefault(k, []).extend(float(x) * 1e3 for x in v)
    return {k: [round(float(np.nanmean(v)), 1), round(float(np.nanmax(v)), 1)]
            for k, v in sorted(out_.items(), key=lambda t: -np.nanmax(t[1]))}


def numbers(c, X, pulls, tag):
    m = chain_lay.measures(c, X, plan, body.contact)
    a, b = c.chain_v[:, 0], c.chain_v[:, 1]
    e = np.abs(np.linalg.norm(X[b] - X[a], axis=1) / np.maximum(c.chain_L, 1e-12) - 1) * 100
    r = {"links_pct": {"max": round(float(np.nanmax(e)), 2), "median": round(float(np.nanmedian(e)), 3),
                       "over_2pct": int((e > 2).sum()), "of": int(len(e))},
         "seam_gaps_mm": seam_read(c, X), "measures": m, "tapes_mm": chain_settle.pull_report(X, pulls)}
    log(f"{tag}: links {r['links_pct']}, inside {m.get('inside')}, worst seams "
        f"{dict(list(r['seam_gaps_mm'].items())[:6])}")
    return r


with resources.heavy("n2g chain solve jacket", gb=3, kind="chain_build", log=log):
    t0 = time.time()
    rep = {"uptime": [up()], "seam_w": SEAM_W}
    M2, st2, bd2, _ = join_seams(pat.M, pat.stiff, pat.bend)
    net = Network(M2, st2, bd2)
    cnet, keep = chain_network(net)
    other = {cnet.names[cnet.piece[x]] for a, b in cnet.sew if cnet.piece[a] != cnet.piece[b] for x in (a, b)}
    skip = [p for p in cnet.names if p not in other]
    h = holds_read(net)
    follow = {**h.plies, **h.layers, **h.inside}
    pan = Panels(cnet, plan, skip)
    Xs, epulls, srd = panel_start.starts(cnet, keep, body, skip, spin={p: 0.0 for p in cnet.names})
    for h_ in pan.hinges:  # (the start UNTURNED: the solve's fold terms turn each fold, in the solve's own sign; N2g:
        # a hinge's way read off the flat turned the collar fall up into a funnel, and neither way read within 50 deg)
        h_["turn_deg"] = 0.0
    t1 = time.time()
    TH0 = pan.fit_start(np.nan_to_num(Xs))
    rep["seconds_fit_start"] = round(time.time() - t1, 1)
    sgn0 = {p: chain_lay._out_sign(cnet, p, np.nan_to_num(Xs), body.contact) for p in cnet.names if p not in skip}
    X = pan.positions(TH0)
    ok = ~np.isnan(X[:, 0]) & ~np.isnan(Xs[:, 0])
    rep["start_pieces"] = srd
    rep["start_fit_rms_mm"] = round(float(np.sqrt(((X[ok] - Xs[ok]) ** 2).sum(1).mean())) * 1e3, 1)
    # followers (plies, floating layers, inside pieces) bound on their hosts: a term of every solve, and their start
    sign = {p: chain_lay._out_sign(cnet, p, np.nan_to_num(X), body.contact) for p in set(follow.values())}
    k_of = {p: (1 + sum(1 for q, hh in h.layers.items() if hh == follow[p])) if p in h.inside else 1 for p in follow}
    bound = {p: follow[p] for p in (follow if "bindall" in sys.argv else skip)}  # (run1 bound every follower: the
    # collar bound point for point on the undercollar fought its own fall fold, links to 3966 %)
    plies = cp.bind(cnet, bound, k_of, sign)
    for b in plies:  # (a ply sewn to nothing has no panel start: put it where its binding says)
        if np.isnan(X[b["ids"], 0]).any():
            P = (b["w"][:, :, None] * X[b["tri"]]).sum(1) + b["d"][:, None] * cp.normals(X, b["tri"], b.get("hostF"))
            X[b["ids"]] = np.where(np.isnan(X[b["ids"]]), P, X[b["ids"]])
    pulls = chain_settle.girth_pulls(cnet, X) + epulls
    folds = chain_lay.fold_rows(cnet, plan, sgn0)
    ties = chain_lay.tie_pairs(cnet, plan)
    np.save(os.path.join(out, "X_start.npy"), X)
    pickle.dump({"keep": keep, "cnet": cnet, "TH0": TH0}, open(os.path.join(out, "cnet.pkl"), "wb"))
    rep.update(points=int(cnet.n), nodes=int(len(np.unique(cnet.root))), panels=pan.n, skipped=skip,
               follow=follow, folds=len(folds), ties=len(ties), pulls=len(pulls))
    rep["start"] = numbers(cnet, X, pulls, "start")
    rep["seconds"] = {"setup": round(time.time() - t0, 1)}
    if not only_measure:
        u = unsewn(cnet)
        Xk = X.copy()
        rep["stages"] = []
        for k, w in enumerate(SEAM_W):
            t1 = time.time()
            A, B = cnet.sew[:, 0], cnet.sew[:, 1]
            mid = 0.5 * (Xk[A] + Xk[B])
            sp_ = [{"ids": np.r_[A, B], "to": np.r_[mid, mid], "weight": w, "name": "seams"}]
            Xk, rk = cs.solve(u, Xk, body, ties, folds, pulls + sp_, plies=plies, log=None)
            np.save(os.path.join(out, f"X_stage{k}.npy"), Xk)
            sr = numbers(cnet, Xk, pulls, f"stage {k} (seam w {w})")
            sr.update(seconds=round(time.time() - t1, 1), solve={kk: rk.get(kk) for kk in
                                                                ("links", "folds", "contact", "ties", "plies")})
            rep["stages"].append(sr)
        t1 = time.time()
        Xf, rf = cs.solve(cnet, Xk, body, ties, folds, pulls, plies=plies, log=None)
        np.save(os.path.join(out, "X.npy"), Xf)
        rep["solved"] = numbers(cnet, Xf, pulls, "solved")
        rep["solved"]["seam_moved_mm"] = seam_read(cnet, Xf, X)
        rep["solved"]["merge_moved_mm"] = seam_read(cnet, Xf, Xk)
        rep["solved"]["solve"] = {kk: rf.get(kk) for kk in ("links", "folds", "contact", "ties", "plies", "pulls",
                                                            "timing", "lm_passes", "projection_passes")}
        rep["seconds"]["stages"] = [s_["seconds"] for s_ in rep["stages"]]
        rep["seconds"]["sewn"] = round(time.time() - t1, 1)
    rep["seconds"]["total"] = round(time.time() - t0, 1)
    rep["uptime"].append(up())
json.dump(rep, open(os.path.join(out, "report.json"), "w"), indent=1, default=str)
log(f"done {rep['seconds']}")
