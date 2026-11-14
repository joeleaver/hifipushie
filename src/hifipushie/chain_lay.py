"""CHAIN LAY: the reads and plan inputs step 5's chains share (N2d of docs/proposals/step5_rewrite.md). N2c's per-piece
placement (each piece sewn onto what was placed, then bent as rigidly as possible: links 300-2,900 % off their cut before
any bend) is gone: the garment is assembled from rolled panels (chain_panels, chain_assemble), no point ever free.

- node_links(cnet): every chain link over nodes at its cut, then the lines across (each at most its flat length).
- measures(cnet, X, plan, contact): links % off cut per piece, loops that don't close (named, mm), each side of a seam
  against its own cut, fold turns, points inside.
- outside / fold_way: which side of F is each piece's outside, and THE one rule for which way a fold turns (N2i).
- fold_rows / tie_pairs: chain_solve's folds (step 2's turn per planned fold over the draft's rows, the way fold_way
  says) and ties (closures, a LAYER apart). _draft_fold / _uv_wind: the draft's fold entry and a piece's flat winding.
Nothing here knows a garment, a piece's role or a wear state.
"""
from __future__ import annotations

import numpy as np

from .chain_core import GAP, LAYER, ChainRefused

CLOSE_TOL = 0.5  # % off its cut: past this, a link's loop is named (its gap in mm), never stretched


def _uv_wind(net, piece) -> float:
    v = net.verts(piece)
    F = net.F[np.isin(net.F, v).all(1)]
    a, b, c = net.uv[F[:, 0]], net.uv[F[:, 1]], net.uv[F[:, 2]]
    u, w = b - a, c - a
    return 1.0 if float((u[:, 0] * w[:, 1] - u[:, 1] * w[:, 0]).sum()) >= 0 else -1.0


def _draft_fold(net, f, bid):
    fd = next((d for d in net.M.get("folds") or [] if d.get("piece") == f["on"] and d.get("name") == f["fold"]), None)
    if fd is None:
        raise ChainRefused(f"fold {bid}: the draft has no fold {f['fold']} on {f['on']}: back to step 4")
    return fd


def node_links(cnet):
    """(i, j, L, exact) over nodes: every chain link at its cut (a seam's two sides: one link at their mean), then the
    lines across, each AT MOST its flat length (exact False)."""
    r = cnet.root
    a, b = np.sort(r[cnet.chain_v], axis=1).T
    k = a != b
    key, inv = np.unique(np.c_[a[k], b[k]], axis=0, return_inverse=True)
    L = np.bincount(inv.ravel(), cnet.chain_L[k]) / np.bincount(inv.ravel())
    e = np.sort(r[cnet.edges], axis=1)
    m = e[:, 0] != e[:, 1]
    return (np.r_[key[:, 0], e[m, 0]], np.r_[key[:, 1], e[m, 1]], np.r_[L, cnet.flat[m]],
            np.r_[np.ones(len(key), bool), np.zeros(int(m.sum()), bool)])


def _fold_turns(cnet, X, plan, out=None) -> dict:
    """Measured turn (deg) of each planned fold: per row the median angle between the faces either side of its links,
    SUMMED over the draft's rows (N2e: a fold split over two rows turns half at each; the per-row median read against
    the whole fold's turn read it at half). With out (outside() at the start): which WAY it turned ("outward": the
    plies closed on the piece's outside) against the way the draft asks (fold_way)."""
    from .chain_solve_terms import fold_quads, turn_of
    res = {}
    for bid, f in sorted((plan.get("folds") or {}).items()):
        fd = _draft_fold(cnet, f, bid)
        rows = []
        for row in fd.get("rows") or []:
            row = np.asarray(row, np.int64)
            got = []
            for a, b in zip(row[:-1], row[1:]):
                fs = cnet.F[(cnet.F == a).any(1) & (cnet.F == b).any(1)]
                if len(fs) != 2:
                    continue
                n = np.cross(X[fs[:, 1]] - X[fs[:, 0]], X[fs[:, 2]] - X[fs[:, 0]])
                n = n / np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]
                got.append(np.degrees(np.arccos(np.clip(n[0] @ n[1], -1, 1))))
            if got:
                rows.append(float(np.median(got)))
        if rows:
            tot = float(np.sum(rows))
            res[bid] = {"planned": float(f["turn_deg"]), "median": round(tot, 1), "rows": [round(r, 1) for r in rows],
                        "off": round(abs(tot - float(f["turn_deg"])), 1)}
            if out is not None and f["on"] in out:
                o = out[f["on"]]
                fr = [{"row": np.asarray(r, np.int64), "turn_deg": 0.0, "name": bid} for r in fd.get("rows") or []]
                Q = np.concatenate([q["quads"] for q in fold_quads(cnet, fr)])
                t = turn_of(X, *(Q[:, i].astype(np.int64) for i in range(4)), Q[:, 4])[0]
                say = lambda w: "outward" if w > 0 else "inward"
                res[bid]["way"] = say(float(np.median(t)) * o)
                res[bid]["plan_way"] = say(fold_way(fd, o) * o)
    return res


def measures(cnet, X, plan=None, contact=None, out=None) -> dict:
    """Links % off cut per piece (per point: each side of a seam at its own cut), the loops that don't close (links past
    CLOSE_TOL, by piece pair, gap mm), seam gaps (0 by construction: a check), fold turns (and ways, with out), points
    inside."""
    outs = out
    a, b = cnet.chain_v[:, 0], cnet.chain_v[:, 1]
    ln = np.linalg.norm(X[b] - X[a], axis=1)
    e = np.abs(ln / np.maximum(cnet.chain_L, 1e-12) - 1) * 100
    by: dict = {}
    for k in np.argsort(-e):
        by.setdefault(cnet.names[cnet.chain_piece[k]], round(float(e[k]), 3))
    i, j, L, ex = node_links(cnet)
    Xr = X  # (X is per point; a node's points coincide, so X at a root is the node's)
    l2 = np.linalg.norm(Xr[j] - Xr[i], axis=1)
    bad = ex & (np.abs(l2 / L - 1) * 100 > CLOSE_TOL)
    loops: dict = {}
    for u, v, ll, LL in zip(i[bad], j[bad], l2[bad], L[bad]):
        pp = sorted({cnet.names[q] for q in cnet.piece[(cnet.root == u) | (cnet.root == v)]})
        key = " ~ ".join(pp)
        loops[key] = max(loops.get(key, 0.0), round(float(ll - LL) * 1e3, 1))
    sides: dict = {}  # (a seam's two sides cut to different lengths: each side's own links, summed, mm over its cut)
    r = cnet.root
    shared = np.bincount(r, minlength=cnet.n) > 1
    for p in range(len(cnet.names)):
        m = (cnet.chain_piece == p) & shared[r[a]] & shared[r[b]]
        for k in np.where(m)[0]:
            pp = sorted({cnet.names[q] for q in cnet.piece[(r == r[a[k]]) | (r == r[b[k]])]} - {cnet.names[p]})
            if len(pp) != 1:
                continue
            key = " ~ ".join(sorted((cnet.names[p], pp[0])))
            d = sides.setdefault(key, {})
            d[cnet.names[p]] = d.get(cnet.names[p], 0.0) + float(ln[k] - cnet.chain_L[k]) * 1e3
    sides = {k: {q: round(x, 1) for q, x in v.items()} for k, v in sides.items()
             if max(abs(x) for x in v.values()) > 1.0}
    sew = cnet.sew
    gap = float(np.linalg.norm(X[sew[:, 0]] - X[sew[:, 1]], axis=1).max()) * 1e3 if len(sew) else 0.0
    out = {"links_max_pct": round(float(e.max()), 3), "links_over_2pct": int((e > 2).sum()), "links": len(e),
           "links_by_piece_max_pct": by, "loops_open_mm": dict(sorted(loops.items(), key=lambda t: -abs(t[1]))[:12]),
           "loops_open": len(loops), "seam_gap_mm": round(gap, 3),
           "sides_differ_mm": sides}
    if plan:
        out["folds"] = _fold_turns(cnet, X, plan, outs)
    if contact is not None:
        sd, _ = contact.query(X)
        out["inside"] = int((sd < 0).sum())
        out["under_gap"] = int((sd < GAP - 1e-4).sum())
    return out


def outside(net, X, contact, pieces=None) -> dict:
    """{piece: +1 when its F normals point away from the body at X (area weighted), else -1}: which side of F is the
    piece's OUTSIDE (the draft's own word: "the face placed away from the body"; one flat cuts a pair, so a flat may
    show either face). Read at the START, before any fold turns (a fold turned 180 makes half a piece face back)."""
    out = {}
    for piece in pieces if pieces is not None else net.names:
        v = net.verts(piece)
        F = net.F[np.isin(net.F, v).all(1)]
        c = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
        _, nb = getattr(contact, "contact", contact).query(X[F].mean(1))
        out[piece] = 1.0 if float((c * nb).sum()) >= 0 else -1.0
    return out


def fold_way(fd: dict, out: float) -> float:
    """THE fold-direction rule (N2i, one function for the solve's folds, the panels' hinges and the reports): +1 when
    the plies close on the side F's normals face, -1 the other side. The draft's turn says over onto the OUTSIDE
    (+, angle below 180: a lapel, a fall, a cuff turned back) or under onto the inside (-, a hem, a facing); `out`
    (outside()) says which side of F is the outside. The draft's "sign" (the flap's side of its line) never enters:
    it picks the side that turns, not the way (N2h: x sign turned one of a mirrored pair of lapels in, onto the body)."""
    return (1.0 if float(fd.get("turn", 1.0)) >= 0 else -1.0) * (1.0 if out >= 0 else -1.0)


def fold_rows(net, plan, out) -> list:
    """chain_solve folds: step 2's turn per planned fold, split over the draft's rows, the way fold_way says (out:
    outside() at the start)."""
    res = []
    for bid, f in sorted((plan.get("folds") or {}).items()):
        fd = _draft_fold(net, f, bid)
        rows = [np.asarray(r, np.int64) for r in fd.get("rows") or []]
        if f["on"] not in out:
            raise ChainRefused(f"fold {bid}: no outside read for {f['on']}: place it first (chain_lay.outside)")
        way = fold_way(fd, out[f["on"]])
        for k, r in enumerate(rows):
            res.append({"row": r, "turn_deg": float(f["turn_deg"]) / len(rows), "toward": way, "weight": 1.0,
                        "name": f"{bid}#{k}"})
    return res


def tie_pairs(net, plan) -> list:
    """(a, b, LAYER) for every tied pair of every closure (closure_ties, through chain_plan.apply_tie)."""
    from .chain_plan import apply_tie
    out = []
    ties = plan.get("ties") or {}
    for c in net.M.get("closures") or []:
        t = ties.get(c.get("name"))
        cl = apply_tie(c, t, net.uv) if t is not None else c
        for (a, b), on in zip(cl.get("v") or [], cl.get("closed") or []):
            if on:
                out.append((int(a), int(b), LAYER))
    return out
