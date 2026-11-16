"""D1 (diagnostic, no new method): WHERE does N2j's stretch come from? N2j's network and chain_solve unchanged; each
experiment switches terms off or pieces out (arguments here, never module switches) and solves the SEWN network
straight from a start, then reads every sewn link against its cut (by piece and kind), the seams' meeting distance and
the wall time.

  HIFIPUSHIE_HOME=<scratch ws> capped uv run python spikes/d1_where.py <out> <loaded.pkl> <n2j run dir> <exp> [opts]
exp:
  E1  pattern alone: no body, no contact, no tapes, no fold targets (the pattern's fold rows stay chains), no plies.
  E2  E1 without the pieces named by drop=a,b,c (their links gone, their seams cut; the rest unchanged).
  E3  E1 + the undercollar tied to the collar's roll row (opts host=<piece with the row> to=<piece without>): each row
      point's flat position carried through the two pieces' sewn pairs (an affine map), tied (gap LAYER) to the
      nearest point of the other piece.
  E4  E1 + plies (followers bound on their hosts, as N2j: the unsewn followers only).
  E5  E4 + body contact.
  E6  E5 + fold targets + ties + tapes (N2j's full term set, solved sewn from the start: no continuation).
opts: folds (add the plan's fold targets to any exp), flat (start = each piece's FLAT pattern placed rigidly where the
  panel start put it: a second, unrolled start), only=a,b (keep only these pieces: the solver check), noise=<m>.
The network and the panel start are N2j's own (run dir: cnet.pkl, X_start.npy, made by spikes/n2j_jacket.py at this
commit). Writes <out>/<exp>.json and <exp>_X.npy."""
import copy
import json
import os
import pickle
import sys
import time

import numpy as np

from hifipushie import chain_lay, chain_settle, panel_start, resources
from hifipushie import chain_solve as cs
from hifipushie import chain_solve_plies as cp
from hifipushie.chain_core import LAYER
from hifipushie.chain_holds import read as holds_read
from hifipushie.chain_net import Network
from hifipushie.chain_seams import join_seams

KINDS = {0: "edge", 1: "fold row", 2: "line along", 3: "line across"}
out, src, run, exp = sys.argv[1:5]
opt = dict(a.split("=", 1) if "=" in a else (a, "1") for a in sys.argv[5:])
os.makedirs(out, exist_ok=True)
tag = exp + "".join(f"_{k}{'' if v == '1' else '-' + v.replace(',', '+')}" for k, v in sorted(opt.items()))
log = lambda m: print(m, flush=True)


def relink(c, keep_piece):
    """The network with only keep_piece's chains: every other point unsewn and linked to nothing (it floats, touching
    nothing kept); a seam's two sides one link at their mean, exactly as chain_net._chain_links merges them."""
    u = copy.copy(c)
    kept = keep_piece[c.piece]
    root = np.arange(c.n)
    for r in np.unique(c.root[kept]):  # (a sewn group's new root: its least KEPT member)
        g = np.where(kept & (c.root == r))[0]
        root[g] = g.min()
    u.root = root
    m = keep_piece[c.chain_piece]
    u.chain_v, u.chain_L, u.chain_kind, u.chain_piece = c.chain_v[m], np.asarray(c.chain_L)[m], c.chain_kind[m], \
        c.chain_piece[m]
    a, b = root[u.chain_v[:, 0]], root[u.chain_v[:, 1]]
    i, j = np.minimum(a, b), np.maximum(a, b)
    uk, inv = np.unique(i.astype(np.int64) * c.n + j, return_inverse=True)
    s, k = np.zeros(len(uk)), np.zeros(len(uk))
    np.add.at(s, inv, u.chain_L)
    np.add.at(k, inv, 1)
    hi, lo = np.zeros(len(uk)), np.full(len(uk), np.inf)
    np.maximum.at(hi, inv, u.chain_L)
    np.minimum.at(lo, inv, u.chain_L)
    u.link_i, u.link_j = (uk // c.n).astype(np.int64), (uk % c.n).astype(np.int64)
    u.link_L, u.link_cut, u.link_of_chain = s / k, np.stack([lo, hi], 1), inv
    u.sew = c.sew[kept[c.sew].all(1)]
    return u


def read(c, X, keep_piece):
    """Sewn links against their cut (over 2 %: count, worst, by piece and kind), the cut spread a sewn link carries,
    the seams' meeting distance (each pair's two points: 0 when sewn as one node)."""
    cur = np.linalg.norm(X[c.link_j] - X[c.link_i], axis=1)
    s = (cur / np.maximum(c.link_L, 1e-12) - 1) * 100
    kind = np.zeros(len(s), int)
    piece = np.zeros(len(s), int)
    kind[c.link_of_chain], piece[c.link_of_chain] = c.chain_kind, c.chain_piece
    two = c.link_cut[:, 1] > c.link_cut[:, 0] + 1e-12  # (a seam link: its sides' own cuts)
    side = np.maximum(np.abs(cur / c.link_cut[:, 0] - 1), np.abs(cur / c.link_cut[:, 1] - 1)) * 100
    over = np.abs(s) > 2
    by_p, by_k = {}, {}
    for x in np.where(over)[0]:
        by_p[c.names[piece[x]]] = by_p.get(c.names[piece[x]], 0) + 1
        by_k[KINDS[kind[x]]] = by_k.get(KINDS[kind[x]], 0) + 1
    gap = np.linalg.norm(X[c.sew[:, 0]] - X[c.sew[:, 1]], axis=1) * 1e3 if len(c.sew) else np.zeros(1)
    return {"links": int(len(s)), "over_2pct": int(over.sum()), "stretched": int((s > 2).sum()),
            "short": int((s < -2).sum()), "worst_pct": round(float(np.abs(s).max()), 2),
            "median_pct": round(float(np.median(np.abs(s))), 3),
            "by_piece": dict(sorted(by_p.items(), key=lambda t: -t[1])),
            "by_kind": dict(sorted(by_k.items(), key=lambda t: -t[1])),
            "seam_links_off_own_side_2pct": int((side[two] > 2).sum()), "seam_links": int(two.sum()),
            "seam_gap_mm": {"mean": round(float(gap.mean()), 2), "max": round(float(gap.max()), 2)}}


def flat_start(c, X):
    """Each piece's flat pattern placed rigidly (Kabsch) onto where X has it: no roll, the same placement."""
    Y = X.copy()
    for p in range(len(c.names)):
        v = np.where((c.piece == p) & ~np.isnan(X[:, 0]))[0]
        if len(v) < 3:
            continue
        A = np.c_[c.uv[v], np.zeros(len(v))]
        a0, b0 = A.mean(0), X[v].mean(0)
        U, _, Vt = np.linalg.svd((A - a0).T @ (X[v] - b0))
        D = np.diag([1, 1, np.sign(np.linalg.det(U @ Vt))])
        R = U @ D @ Vt
        w = np.where(c.piece == p)[0]
        Y[w] = (np.c_[c.uv[w], np.zeros(len(w))] - a0) @ R + b0
    return Y


def roll_ties(c, host, to):
    """Ties carrying `host`'s fold-row points onto `to` through their sewn pairs (affine fit in the flat)."""
    ph, pt = c.names.index(host), c.names.index(to)
    pairs = [(a, b) if c.piece[a] == ph else (b, a) for a, b in c.sew
             if {c.piece[a], c.piece[b]} == {ph, pt}]
    pairs = np.asarray(pairs)
    A = np.c_[c.uv[pairs[:, 0]], np.ones(len(pairs))]
    M = np.linalg.lstsq(A, c.uv[pairs[:, 1]], rcond=None)[0]
    res = np.linalg.norm(A @ M - c.uv[pairs[:, 1]], axis=1)
    row = np.unique(c.chain_v[(c.chain_kind == 1) & (c.chain_piece == ph)])
    q = np.c_[c.uv[row], np.ones(len(row))] @ M
    tv = np.where(c.piece == pt)[0]
    d = np.linalg.norm(c.uv[tv][None] - q[:, None], axis=2)
    near = tv[d.argmin(1)]
    log(f"roll ties: {len(row)} row points, affine fit rms {res.mean() * 1e3:.1f} mm, nearest {d.min(1).max() * 1e3:.1f} mm")
    return [(int(a), int(b), LAYER) for a, b in zip(row, near)]


d = pickle.load(open(src, "rb"))
pat, body, plan = d["pat"], d["body"], d["wear"]
g = pickle.load(open(os.path.join(run, "cnet.pkl"), "rb"))
cnet = g["cnet"]
X0 = np.load(os.path.join(run, "X_start.npy"))
names = cnet.names
keep_piece = np.ones(len(names), bool)
if "drop" in opt:
    keep_piece[[names.index(p) for p in opt["drop"].split(",")]] = False
if "only" in opt:
    keep_piece[:] = False
    keep_piece[[names.index(p) for p in opt["only"].split(",")]] = True
c = relink(cnet, keep_piece) if not keep_piece.all() else cnet
X = np.nan_to_num(X0)
if "flat" in opt:
    X = flat_start(cnet, X)
if "noise" in opt:
    X = X + np.random.default_rng(0).normal(0, float(opt["noise"]), X.shape)
use_body = exp in ("E5", "E6")
ties, folds, pulls, plies = [], [], [], []
if exp in ("E4", "E5", "E6") or "folds" in opt:
    OUT = chain_lay.outside(cnet, X, body.contact, [p for p in names if p not in ("canvas.L", "canvas.R")])
if exp in ("E4", "E5", "E6"):
    M2, st2, bd2, _ = join_seams(pat.M, pat.stiff, pat.bend)
    h = holds_read(Network(M2, st2, bd2))
    follow = {**h.plies, **h.layers, **h.inside}
    other = {names[cnet.piece[x]] for a, b in cnet.sew if cnet.piece[a] != cnet.piece[b] for x in (a, b)}
    skip = [p for p in names if p not in other]
    sign = chain_lay.outside(cnet, X, body.contact, sorted(set(follow.values())))
    k_of = {p: (1 + sum(1 for q, hh in h.layers.items() if hh == follow[p])) if p in h.inside else 1 for p in follow}
    plies = cp.bind(cnet, {p: follow[p] for p in skip}, k_of, sign)
if exp == "E6" or "folds" in opt:
    folds = chain_lay.fold_rows(cnet, plan, OUT)
if exp == "E6":
    ties = chain_lay.tie_pairs(cnet, plan)
    M2, st2, bd2, _ = join_seams(pat.M, pat.stiff, pat.bend)
    _, epulls, _ = panel_start.starts(cnet, g["keep"], body, skip, spin={p: 0.0 for p in names})
    pulls = chain_settle.girth_pulls(cnet, X) + epulls
if exp == "E3":
    ties = roll_ties(cnet, opt.get("host", "collar"), opt.get("to", "undercollar"))
with resources.heavy(f"d1 {tag}", gb=4, kind="chain_build", log=log):
    t0 = time.time()
    Xf, rf = cs.solve(c, X, body if use_body else None, ties, folds, pulls, plies=plies, log=None)
    sec = round(time.time() - t0, 1)
r = {"exp": exp, "opts": opt, "seconds": sec, "start": read(c, X, keep_piece), "solved": read(c, Xf, keep_piece),
     "folds": rf.get("folds"), "ties": rf.get("ties"), "plies": rf.get("plies"), "contact": rf.get("contact"),
     "pulls": rf.get("pulls"),
     "final_converged": rf.get("final_converged"), "timing": rf.get("timing")}
np.save(os.path.join(out, f"{tag}_X.npy"), Xf)
json.dump(r, open(os.path.join(out, f"{tag}.json"), "w"), indent=1, default=str)
s = r["solved"]
log(f"{tag}: {sec} s; over 2 % {s['over_2pct']} of {s['links']} (stretched {s['stretched']}, short {s['short']}), worst "
    f"{s['worst_pct']} %, by piece {s['by_piece']}, by kind {s['by_kind']}, seam gap {s['seam_gap_mm']}, "
    f"converged {rf.get('final_converged')}, contact {rf.get('contact')}")
