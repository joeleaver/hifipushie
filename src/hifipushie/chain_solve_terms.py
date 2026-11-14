"""CHAIN SOLVE TERMS: what chain_solve.solve() is made of, read off the flat pattern (chain_net.Network) and the caller's
lists; and the residual report. Nothing here moves a point; chain_solve.py is the solver and its docstring is the spec.

- NODES: one per sewn group (Network.root); a vertex's position is its node's.
- LINKS: Network's links (every boundary edge and fold row at its cut; a seam's two sides one link).
- EDGES: every other mesh edge of the pattern: exact where interfaced at both ends (EXACT_INTERFACED), else at most
  its flat length. N2h: on the chains-only network the lines across are long Delaunay rulings, and exact ones made each
  interfaced piece a flat board that could not wrap the neck (the jacket's collar: links stuck 27-43 % off; at most,
  0.3 %), so the jacket driver sets EXACT_INTERFACED False; on a fine grid exact edges still bend along their lines.
- BEND STENCILS: per vertex, the affine weights of its flat neighbours that reproduce its flat position (sum w = 1,
  sum w uv_j = uv_i, least norm). X_i - sum w_j X_j is zero for ANY rigid (indeed affine) placement of a flat
  neighbourhood and grows with the bend: a linear, rotation-free bending row (so the solve's matrix is constant).
  Rows of fold-row vertices are left out (they are where the cloth is told to turn).
- FOLD QUADS: per row edge (a, b) the two faces' far corners (c, d); the turn is d's angle off c's flat continuation,
  about the edge, positive towards c's face normal (F's winding).
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp

from . import chain_net as cn

EXACT_INTERFACED = True  # (EDGES above; a knob: the chains-only proof sets it False)


def nodes_of(net: cn.Network):
    """(node per vertex, node count): sewn vertices share one node."""
    _, nid = np.unique(net.root, return_inverse=True)
    return nid.astype(np.int64), int(nid.max()) + 1 if len(nid) else 0


def links(net, nid):
    """(i, j, L, piece) of the network's links as node ids."""
    lp = np.zeros(len(net.link_L), np.int64)
    lp[net.link_of_chain] = net.chain_piece
    return nid[net.link_i], nid[net.link_j], np.asarray(net.link_L, float), lp


def edges(net, nid, li, lj):
    """(i, j, L, exact) for every mesh edge that is not a link (node ids, deduplicated)."""
    e = net.edges
    a, b = nid[e[:, 0]], nid[e[:, 1]]
    ok = a != b
    a, b, L = a[ok], b[ok], net.flat[ok]
    ex = (net.stiff[e[ok, 0]] > 0.5) & (net.stiff[e[ok, 1]] > 0.5) & EXACT_INTERFACED
    lo, hi = np.minimum(a, b), np.maximum(a, b)
    nn = int(max(nid.max() + 1, 1))
    key = lo * nn + hi
    lkey = np.minimum(li, lj) * nn + np.maximum(li, lj)
    keep = ~np.isin(key, lkey)
    key, L, ex = key[keep], L[keep], ex[keep]
    uk, first = np.unique(key, return_index=True)
    return uk // nn, uk % nn, L[first], ex[first]


def bend_rows(net, nid, nn, weight, skip=()):
    """Bending rows (sparse, rows x nodes) with per-row weight (already / h^2) and their vertex ids."""
    uv = net.uv
    e = net.edges
    A = sp.coo_matrix((np.ones(2 * len(e)), (np.r_[e[:, 0], e[:, 1]], np.r_[e[:, 1], e[:, 0]])),
                      shape=(net.n, net.n)).tocsr()
    skip = set(int(v) for v in skip)
    R, C, V, W, who = [], [], [], [], []
    r = 0
    for v in range(net.n):
        if v in skip or weight[v] <= 0:
            continue
        nb = A.indices[A.indptr[v]:A.indptr[v + 1]]
        if len(nb) < 3:
            continue
        d = uv[nb] - uv[v]
        M = np.vstack([np.ones(len(nb)), d.T])  # (3, k)
        G = M @ M.T
        if np.linalg.cond(G) > 1e8:
            continue
        w = M.T @ np.linalg.solve(G, np.array([1.0, 0.0, 0.0]))
        h = float(np.linalg.norm(d, axis=1).mean())
        R += [r] * (len(nb) + 1)
        C += [nid[v]] + nid[nb].tolist()
        V += [1.0] + (-w).tolist()
        W.append(weight[v] / h ** 2)
        who.append(v)
        r += 1
    S = sp.coo_matrix((V, (R, C)), shape=(r, nn)).tocsr()  # (duplicates sum: a neighbour sewn to its centre)
    return S, np.asarray(W, float), np.asarray(who, np.int64)


def row_rows(net, nid, nn, weight, rows):
    """A fold row bends only ACROSS itself: along it, each inner point stays on the chord of its two row neighbours
    (weights by flat arc length), so the line itself doesn't kink. Rows (sparse) and per-row weights (/ h^2)."""
    R, C, V, W = [], [], [], []
    r = 0
    for row in rows:
        row = np.asarray(row, np.int64)
        for k in range(1, len(row) - 1):
            p, v, q = row[k - 1], row[k], row[k + 1]
            a, b = np.linalg.norm(net.uv[v] - net.uv[p]), np.linalg.norm(net.uv[q] - net.uv[v])
            if a + b < 1e-12:
                continue
            R += [r, r, r]
            C += [nid[v], nid[p], nid[q]]
            V += [1.0, -b / (a + b), -a / (a + b)]
            W.append(max(weight[v], weight[p], weight[q]) / ((a + b) / 2) ** 2)
            r += 1
    return sp.coo_matrix((V, (R, C)), shape=(r, nn)).tocsr(), np.asarray(W, float)


def _face_of(F, a, b):
    m = (F == a).any(1) & (F == b).any(1)
    return np.where(m)[0]


def fold_quads(net, folds):
    """Per fold: quads (a, b, c, d, sign of c's face) along its row and its target turn (radians, signed)."""
    out = []
    for k, f in enumerate(folds):
        row = np.asarray(f["row"], np.int64)
        target = np.radians(float(f["turn_deg"])) * (1.0 if float(f.get("toward", 1.0)) >= 0 else -1.0)
        Q = []
        for a, b in zip(row[:-1], row[1:]):
            fs = _face_of(net.F, a, b)
            if len(fs) != 2:
                continue  # (a row edge on the outline has one face: nothing turns across it)
            cd, sg = [], 0.0
            for fi in fs:
                t = net.F[fi].tolist()
                cd.append(next(x for x in t if x not in (a, b)))
            fa = net.F[fs[0]].tolist()
            ia, ib = fa.index(a), fa.index(b)
            sg = 1.0 if (ib - ia) % 3 == 1 else -1.0  # (a, b, c) is F's own order: c's face normal is (b-a)x(c-a)
            Q.append((a, b, cd[0], cd[1], sg))
        if not Q:
            raise ValueError(f"fold {f.get('name', k)}: its row has no edge with a face on each side")
        out.append({"name": f.get("name", f"fold{k}"), "quads": np.asarray(Q, float), "target": target,
                    "weight": float(f.get("weight", 1.0)), "piece": net.names[net.piece[row[0]]]})
    return out


def turn_of(X, a, b, c, d, sg):
    """Signed turn (radians) at each quad, and the frame (e, x, y) it is read in."""
    e = cn.unit(X[b] - X[a])
    uc = X[c] - X[a]
    uc = uc - (uc * e).sum(1, keepdims=True) * e
    ud = X[d] - X[a]
    ud = ud - (ud * e).sum(1, keepdims=True) * e
    x = -cn.unit(uc)
    y = cn.unit(np.cross(X[b] - X[a], X[c] - X[a])) * sg[:, None]
    y = cn.unit(y - (y * e).sum(1, keepdims=True) * e)
    psi = np.arctan2((ud * y).sum(1), (ud * x).sum(1))
    return psi, e, x, y


# ---- the report
def _named(net, v):
    return net.names[int(net.piece[int(v)])]


def report(net, X, rep: dict, cts, tol_pct: float) -> dict:
    """Residuals at X (per vertex positions): links (% off the cut), edges, ties (mm), folds (deg), pulls (mm),
    contact; each worst named by piece. rep: the solve's terms (chain_solve._terms)."""
    out: dict = {}
    li, lj, L, lp = rep["links"]
    Xn = rep["Xn"]
    l = np.linalg.norm(Xn[lj] - Xn[li], axis=1)
    pct = np.abs(l / np.maximum(L, 1e-12) - 1) * 100
    by: dict = {}
    for k in range(len(pct)):
        nm = net.names[int(lp[k])]
        by[nm] = max(by.get(nm, 0.0), float(pct[k]))
    k = int(np.argmax(pct)) if len(pct) else 0
    out["links"] = {"n": len(pct), "worst_pct": round(float(pct.max()), 4) if len(pct) else 0.0,
                    "worst_piece": net.names[int(lp[k])] if len(pct) else None,
                    "over_tol": int((pct > tol_pct).sum()), "by_piece": {a: round(b, 4) for a, b in by.items()}}
    ei, ej, eL, ex = rep["edges"]
    le = np.linalg.norm(Xn[ej] - Xn[ei], axis=1) / np.maximum(eL, 1e-12) - 1
    over = np.where(ex, np.abs(le), np.maximum(le, 0)) * 100
    out["edges"] = {"n": len(le), "worst_over_pct": round(float(over.max()), 4) if len(le) else 0.0,
                    "over_tol": int((over > tol_pct).sum())}
    ties = rep["ties"]
    if ties:
        r = [abs(float(np.linalg.norm(X[b] - X[a])) - g) * 1e3 for a, b, g in ties]
        k = int(np.argmax(r))
        a, b, _ = ties[k]
        out["ties"] = {"n": len(r), "worst_mm": round(r[k], 4), "worst": f"{_named(net, a)}~{_named(net, b)}"}
    out["folds"] = {}
    for f in rep["folds"]:
        q = f["quads"]
        a, b, c, d = (q[:, t].astype(np.int64) for t in range(4))
        psi = turn_of(X, a, b, c, d, q[:, 4])[0]
        off = np.degrees(np.abs(np.angle(np.exp(1j * (psi - f["target"])))))
        out["folds"][f["name"]] = {"piece": f["piece"], "target_deg": round(float(np.degrees(f["target"])), 2),
                                   "turn_deg": round(float(np.degrees(np.median(psi))), 2),
                                   "median_off_deg": round(float(np.median(off)), 3),
                                   "worst_off_deg": round(float(off.max()), 3)}
    out["pulls"] = {}
    for p in rep["pulls"]:
        dd = np.linalg.norm(X[p["ids"]] - p["to"], axis=1) * 1e3
        out["pulls"][p["name"]] = {"piece": _named(net, p["ids"][0]), "max_mm": round(float(dd.max()), 3),
                                   "mean_mm": round(float(dd.mean()), 3)}
    if cts is not None:
        ct, gap = cts
        sd, _ = ct.query(X)
        k = int(np.argmin(sd))
        out["contact"] = {"inside": int((sd < 0).sum()), "under_gap": int((sd < gap - 1e-5).sum()),
                          "deepest_mm": round(float(max(gap - sd.min(), 0.0)) * 1e3, 3),
                          "worst_piece": _named(net, k) if sd[k] < gap - 1e-5 else None}
    t = out.get("ties", {}).get("worst_mm", 0.0)
    out["hard_ok"] = bool(out["links"]["over_tol"] == 0 and out["edges"]["over_tol"] == 0 and t <= 1.0
                          and out.get("contact", {}).get("inside", 0) == 0)
    return out


# ---- chains as curves (N2h): consecutive link pairs, for the chain bending rows and the smoothness report
def chain_triples(net):
    """(p, v, q, a, b, flat_turn): every point v with exactly two chain links of one kind (boundary / fold row) in its
    piece, p and q its neighbours along that chain, a = |uv_v - uv_p|, b = |uv_q - uv_v| and the chain's turn at v in
    the flat (radians). A corner (two chains meeting) is a triple too: flat_turn says how sharp it is cut."""
    cv = np.asarray(net.chain_v, np.int64)
    kind = np.asarray(net.chain_kind)
    inc: dict = {}
    for k, (i, j) in enumerate(cv):
        inc.setdefault((int(i), int(kind[k])), []).append(int(j))
        inc.setdefault((int(j), int(kind[k])), []).append(int(i))
    T = sorted((v, nb[0], nb[1]) for (v, _), nb in inc.items() if len(nb) == 2)
    if not T:
        z = np.zeros(0, np.int64)
        return z, z, z, np.zeros(0), np.zeros(0), np.zeros(0)
    v, p, q = (np.array(c, np.int64) for c in zip(*T))
    uv = net.uv
    d1, d2 = uv[v] - uv[p], uv[q] - uv[v]
    ft = np.arctan2(np.abs(d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]), (d1 * d2).sum(1))
    return p, v, q, np.linalg.norm(d1, axis=1), np.linalg.norm(d2, axis=1), ft


def chain_bend_rows(net, nid, nn, weight, max_flat_deg: float, skip=()):
    """Second differences ALONG chains: at each chain point v (neighbours p, q along its chain, flat arcs a, b) the row
    X_v - (b X_p + a X_q) / (a + b) with weight / ((a + b) / 2)^2: a point off its neighbours' chord by delta costs
    weight (2 delta / h)^2 ~ weight x turn^2, the chain's discrete curvature (rest: straight). Only where the flat
    chain turns less than max_flat_deg (a cut corner keeps its angle; a gently curved cut is a small rest it drifts
    towards, held by its links and lines across). skip: points with no row (a fold row's points: the fold turns the
    chains crossing it there, its turn is the fold term's). Returns rows (sparse, rows x nodes), weights."""
    p, v, q, a, b, ft = chain_triples(net)
    m = (np.degrees(ft) < max_flat_deg) & (a + b > 1e-12) & (nid[p] != nid[v]) & (nid[q] != nid[v])
    m &= ~np.isin(v, np.asarray(list(skip), np.int64))
    p, v, q, a, b = p[m], v[m], q[m], a[m], b[m]
    r = np.arange(len(v))
    S = sp.coo_matrix((np.r_[np.ones(len(v)), -b / (a + b), -a / (a + b)],
                       (np.r_[r, r, r], np.r_[nid[v], nid[p], nid[q]])), shape=(len(v), nn)).tocsr()
    w = np.maximum.reduce([weight[v], weight[p], weight[q]]) / ((a + b) / 2) ** 2
    return S, w


def smoothness(net, X, min_deg: float = 2.0) -> dict:
    """The chains as curves at X (per vertex): per chain point the 3D turn MINUS its flat turn (degrees: what was bent
    in), median / p99 / max; and ZIGZAGS: chain points turning the opposite way round to BOTH their neighbours along the
    chain (binormals (v - p) x (q - v) pointing apart), all three turning more than min_deg. A smooth bump's inflection
    flips once and is no zigzag; a zigzag flips at every point. Per piece and in all."""
    p, v, q, _, _, ft = chain_triples(net)
    X = np.asarray(X, float)
    d1, d2 = X[v] - X[p], X[q] - X[v]
    t3 = np.arctan2(np.linalg.norm(np.cross(d1, d2), axis=1), (d1 * d2).sum(1))
    bend = np.degrees(np.abs(t3 - ft))
    B = cn.unit(np.cross(d1, d2))
    at: dict = {}
    for k, x in enumerate(v):
        at.setdefault(int(x), []).append(k)
    big = np.degrees(t3) > min_deg

    def flip(k, nb):
        for kq in at.get(int(nb), []):
            if p[kq] == v[k] or q[kq] == v[k]:
                s_ = 1.0 if p[kq] == v[k] else -1.0  # (walking the chain the other way reverses its binormal)
                if nb == p[k]:
                    s_ = -s_
                return big[kq] and s_ * (B[k] * B[kq]).sum() < 0
        return False
    flips: dict = {}
    for k in np.where(big)[0]:
        if flip(k, q[k]) and flip(k, p[k]):
            nm = net.names[int(net.piece[int(v[k])])]
            flips[nm] = flips.get(nm, 0) + 1
    ok = np.isfinite(bend)
    if not ok.any():
        return {"turn_deg": {}, "zigzags": 0, "zigzags_by_piece": {}}
    return {"turn_deg": {"median": round(float(np.median(bend[ok])), 2),
                         "p99": round(float(np.percentile(bend[ok], 99)), 2), "max": round(float(bend[ok].max()), 2),
                         "n": int(ok.sum())},
            "zigzags": int(sum(flips.values())), "zigzags_by_piece": dict(sorted(flips.items(), key=lambda t: -t[1]))}
