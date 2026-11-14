"""CHAIN LAY: the reads and plan inputs step 5's chains share (N2d of docs/proposals/step5_rewrite.md). N2c's per-piece
placement (each piece sewn onto what was placed, then bent as rigidly as possible: links 300-2,900 % off their cut before
any bend) is gone: the garment is assembled from rolled panels (chain_panels, chain_assemble), no point ever free.

- node_links(cnet): every chain link over nodes at its cut, then the lines across (exact where interfaced, else at most).
- measures(cnet, X, plan, contact): links % off cut per piece, loops that don't close (named, mm), each side of a seam
  against its own cut, fold turns, points inside.
- fold_rows / tie_pairs: chain_solve's folds (step 2's turn per planned fold over the draft's rows, the way the draft's
  sign says in the flat's winding) and ties (closures, a LAYER apart). _draft_fold / _uv_wind: the draft's fold entry and
  a piece's flat winding.
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
    lines across at their flat length (exact where interfaced at both ends, else at most)."""
    r = cnet.root
    a, b = np.sort(r[cnet.chain_v], axis=1).T
    k = a != b
    key, inv = np.unique(np.c_[a[k], b[k]], axis=0, return_inverse=True)
    L = np.bincount(inv.ravel(), cnet.chain_L[k]) / np.bincount(inv.ravel())
    e = np.sort(r[cnet.edges], axis=1)
    m = e[:, 0] != e[:, 1]
    ex = (cnet.stiff[cnet.edges[:, 0]] > 0) & (cnet.stiff[cnet.edges[:, 1]] > 0)
    return (np.r_[key[:, 0], e[m, 0]], np.r_[key[:, 1], e[m, 1]], np.r_[L, cnet.flat[m]],
            np.r_[np.ones(len(key), bool), ex[m]])


def _fold_turns(cnet, X, plan) -> dict:
    """Measured turn (deg) of each planned fold: per row the median angle between the faces either side of its links,
    SUMMED over the draft's rows (N2e: a fold split over two rows turns half at each; the per-row median read against
    the whole fold's turn read it at half)."""
    out = {}
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
            out[bid] = {"planned": float(f["turn_deg"]), "median": round(tot, 1), "rows": [round(r, 1) for r in rows],
                        "off": round(abs(tot - float(f["turn_deg"])), 1)}
    return out


def measures(cnet, X, plan=None, contact=None) -> dict:
    """Links % off cut per piece (per point: each side of a seam at its own cut), the loops that don't close (links past
    CLOSE_TOL, by piece pair, gap mm), seam gaps (0 by construction: a check), fold turns, points inside."""
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
        out["folds"] = _fold_turns(cnet, X, plan)
    if contact is not None:
        sd, _ = contact.query(X)
        out["inside"] = int((sd < 0).sum())
        out["under_gap"] = int((sd < GAP - 1e-4).sum())
    return out


def _out_sign(net, piece, X, contact) -> float:
    """+1 when the piece's F normals point away from the body at the start (area weighted), else -1."""
    v = net.verts(piece)
    F = net.F[np.isin(net.F, v).all(1)]
    c = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    _, nb = getattr(contact, "contact", contact).query(X[F].mean(1))
    return 1.0 if float((c * nb).sum()) >= 0 else -1.0


def fold_rows(net, plan, sign) -> list:
    """chain_solve folds: step 2's turn per planned fold, split over the draft's rows. Which way: the draft's fold sign
    read in the flat's own winding (sign x uv winding: +1 = onto the side the flat's +z faces), then into F's normals
    on the body by the piece's out sign."""
    out = []
    for bid, f in sorted((plan.get("folds") or {}).items()):
        fd = _draft_fold(net, f, bid)
        rows = [np.asarray(r, np.int64) for r in fd.get("rows") or []]
        way = float(fd.get("sign", 1.0)) * _uv_wind(net, f["on"]) * sign.get(f["on"], 1.0)
        for k, r in enumerate(rows):
            out.append({"row": r, "turn_deg": float(f["turn_deg"]) / len(rows), "toward": way, "weight": 1.0,
                        "name": f"{bid}#{k}"})
    return out


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
