"""D4: ONE chain_solve from the seams-on-lines start (spikes/d4_lines.py): links exact, contact on, folds turned to plan,
the laid seam points as STRONG SOFT pulls (never held), plies bound as N2j / D2 do, no tapes (the lines are where the body
was measured), no ties (the jacket is worn open).

  HIFIPUSHIE_HOME=<ws> capped uv run python spikes/d4_solve.py <start dir> <loaded.pkl> [pull weight]
Writes <start dir>/solved.json and X_solved.npy."""
import json
import os
import pickle
import sys
import time

import numpy as np

from hifipushie import chain_lay, resources
from hifipushie import chain_solve as cs
from hifipushie import chain_solve_plies as cp
from hifipushie.chain_holds import read as holds_read
from hifipushie.chain_net import Network
from hifipushie.chain_seams import join_seams

KINDS = {0: "edge", 1: "fold row", 2: "line along", 3: "line across"}
run, src = sys.argv[1:3]
W = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
log = lambda m: print(m, flush=True)
d = pickle.load(open(src, "rb"))
pat, body, plan = d["pat"], d["body"], d["wear"]
c = pickle.load(open(os.path.join(run, "cnet.pkl"), "rb"))["cnet"]
X = np.load(os.path.join(run, "X_start.npy"))
L = np.load(os.path.join(run, "laid.npz"))
names = c.names


def read(X):
    cur = np.linalg.norm(X[c.link_j] - X[c.link_i], axis=1)
    s = (cur / np.maximum(c.link_L, 1e-12) - 1) * 100
    kind, piece = np.zeros(len(s), int), np.zeros(len(s), int)
    kind[c.link_of_chain], piece[c.link_of_chain] = c.chain_kind, c.chain_piece
    over = np.abs(s) > 2
    by_p, by_k = {}, {}
    for x in np.where(over)[0]:
        by_p[names[piece[x]]] = by_p.get(names[piece[x]], 0) + 1
        by_k[KINDS[kind[x]]] = by_k.get(KINDS[kind[x]], 0) + 1
    gap = np.linalg.norm(X[c.sew[:, 0]] - X[c.sew[:, 1]], axis=1) * 1e3
    sd, _ = body.contact.query(X)
    return {"links": int(len(s)), "over_2pct": int(over.sum()), "stretched": int((s > 2).sum()),
            "short": int((s < -2).sum()), "worst_pct": round(float(np.abs(s).max()), 2),
            "by_piece": dict(sorted(by_p.items(), key=lambda t: -t[1])),
            "by_kind": dict(sorted(by_k.items(), key=lambda t: -t[1])),
            "seam_gap_mm": {"mean": round(float(gap.mean()), 2), "max": round(float(gap.max()), 2)},
            "inside": int((sd < 0).sum()), "deepest_mm": round(float(-sd.min()) * 1e3, 1)}


M2, st2, bd2, _ = join_seams(pat.M, pat.stiff, pat.bend)
h = holds_read(Network(M2, st2, bd2))
follow = {**h.plies, **h.layers, **h.inside}
other = {names[c.piece[x]] for a, b in c.sew if c.piece[a] != c.piece[b] for x in (a, b)}
skip = [p for p in names if p not in other]
OUT = chain_lay.outside(c, np.nan_to_num(X), body.contact, [p for p in names if p not in skip])
sign = chain_lay.outside(c, np.nan_to_num(X), body.contact, sorted(set(follow.values())))
k_of = {p: (1 + sum(1 for q, hh in h.layers.items() if hh == follow[p])) if p in h.inside else 1 for p in follow}
plies = cp.bind(c, {p: follow[p] for p in skip}, k_of, sign)
for b in plies:  # (a ply bound afterwards has no start: put it on its host, as D2 does)
    if np.isnan(X[b["ids"], 0]).any():
        P = (b["w"][:, :, None] * X[b["tri"]]).sum(1) + b["d"][:, None] * cp.normals(X, b["tri"], b.get("hostF"))
        X[b["ids"]] = np.where(np.isnan(X[b["ids"]]), P, X[b["ids"]])
folds = chain_lay.fold_rows(c, plan, OUT)
pos = dict(zip(L["roots"].tolist(), L["pos"]))
ids = np.array([v for v in range(c.n) if int(c.root[v]) in pos])
pulls = [{"ids": ids, "to": np.array([pos[int(c.root[v])] for v in ids]), "weight": W, "name": "seam lines"}]
rep = {"pull_weight": W, "start": read(X), "load_before": os.getloadavg()}
log(f"start: {rep['start']}")
with resources.heavy("d4 solve", gb=4, kind="chain_build", log=log):
    t0 = time.time()
    Xf, rf = cs.solve(c, X, body, [], folds, pulls, plies=plies, log=None)
    rep["seconds"] = round(time.time() - t0, 1)
rep["load_after"] = os.getloadavg()
rep["solved"] = read(Xf)
rep["folds"], rep["pulls"], rep["final_converged"] = rf.get("folds"), rf.get("pulls"), rf.get("final_converged")
np.save(os.path.join(run, "X_solved.npy"), Xf)
json.dump(rep, open(os.path.join(run, "solved.json"), "w"), indent=1, default=str)
log(f"solved {rep['seconds']} s: {rep['solved']}")
log(f"folds {json.dumps(rf.get('folds'), default=str)[:1500]}")
log(f"pulls {json.dumps(rf.get('pulls'), default=str)[:400]}")
