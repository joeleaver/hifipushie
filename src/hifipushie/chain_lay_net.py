"""CHAIN LAY NET (N2b of docs/proposals/step5_rewrite.md): step 5's network is the CHAINS ONLY (Joe 2026-11-12: "I thought
all this step was supposed to do was lay out the chains"). Step 6 fills the surfaces between them (chain_net.fill).

chain_network(net) -> (cnet, keep): a chain_net.Network over the pattern's CHAIN points only (keep: their ids in net):
- CHAINS: every boundary edge and fold row of net, at its cut, exactly as net has them (links, seams as one shared
  chain, a seam's two sides one link at their mean; nothing is re-derived from the new faces).
- LINES ACROSS (N2j): real CHAINS (chain_lines: two families on one lattice, along and across the grain, every
  chain_lines.SPACING, never across a fold row), links EXACT at their flat length (chain_kind 2 along the grain, 3
  across): a piece may curve (a line bends, its chord shortens) but not squash (its arc is fixed). Their lattice points
  are the only points off the pattern's chains (keep: -1 there); interfacing / bending read from the nearest pattern
  vertex of the piece. N2b-N2i's at-most rulings let every conflict narrow the pieces (the wobble, chain_lines' doc).
- FACES: per piece, the Delaunay triangulation of its points in the flat, kept inside its outline and never across a
  fold row (each fold row link gets a face on each side, so the fold's turn is measurable). Faces carry the bending
  stencils and the plies' host triangles; a face edge is held AT MOST its flat length (cloth doesn't stretch). Faces wind as the piece's flat.
- NO SURFACE MESH: a jacket is a few thousand points (24k surface points before).
Nothing here knows a garment, a piece's role or a wear state.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import Delaunay

from . import chain_lines as cl
from . import chain_net as cn


def _inside(poly, q):
    """Even-odd test of flat points q (n, 2) in the closed polygon poly (m, 2)."""
    x, y = q[:, 0][:, None], q[:, 1][:, None]
    a, b = poly, np.roll(poly, -1, axis=0)
    c = (a[:, 1] > y) != (b[:, 1] > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        xc = a[:, 0] + (y - a[:, 1]) * (b[:, 0] - a[:, 0]) / (b[:, 1] - a[:, 1])
    return (c & (x < xc)).sum(1) % 2 == 1


def _side(uv, row, q):
    """Which side (+1 / -1) of the ordered flat polyline `row` each point q lies (0 on it)."""
    P = uv[row]
    a, b = P[:-1], P[1:]
    ab = b - a
    t = np.clip(((q[:, None] - a[None]) * ab[None]).sum(2) / np.maximum((ab * ab).sum(1), 1e-18)[None], 0, 1)
    d = np.linalg.norm(q[:, None] - (a[None] + t[..., None] * ab[None]), axis=2)
    k = np.argmin(d, axis=1)
    cr = ab[k, 0] * (q[:, 1] - a[k, 1]) - ab[k, 1] * (q[:, 0] - a[k, 0])
    return np.where(d[np.arange(len(q)), k] < 1e-7, 0.0, np.sign(cr))


def _wind(uv, F) -> float:
    a, b, c = uv[F[:, 0]], uv[F[:, 1]], uv[F[:, 2]]
    u, w = b - a, c - a
    return 1.0 if float((u[:, 0] * w[:, 1] - u[:, 1] * w[:, 0]).sum()) >= 0 else -1.0


def _piece_faces(net, p, pts, rows, uv):
    """Faces (ids into uv) over the points pts of piece p (module doc); rows in the same ids."""
    tri = pts[Delaunay(uv[pts]).simplices]
    poly = net.uv[net.loop(net.names[p])]
    keep = _inside(poly, uv[tri].mean(1))
    for row in rows:
        sd = _side(uv, row, uv[tri].reshape(-1, 2)).reshape(-1, 3)
        keep &= ~((sd > 0).any(1) & (sd < 0).any(1))
    tri = tri[keep]
    add = []
    for row in rows:  # (each row link a face on each side)
        rs = set(row.tolist())
        others = np.array([v for v in pts if v not in rs])
        if not len(others):
            continue
        so = _side(uv, row, uv[others])
        for a, b in zip(row[:-1], row[1:]):
            has = tri[(tri == a).any(1) & (tri == b).any(1)]
            got = {float(_side(uv, row, uv[[next(x for x in t if x not in (a, b))]])[0]) for t in has}
            mid = 0.5 * (uv[a] + uv[b])
            for s in (1.0, -1.0):
                if s in got or not (so == s).any():
                    continue
                c = others[so == s][np.argmin(np.linalg.norm(uv[others[so == s]] - mid, axis=1))]
                add.append((a, b, c))
    if add:
        tri = np.r_[tri, np.array(add, np.int64)]
    Fp = net.F[net.piece[net.F[:, 0]] == p]
    w0 = _wind(net.uv, Fp)
    a, b, c = uv[tri[:, 0]], uv[tri[:, 1]], uv[tri[:, 2]]
    cr = (b - a)[:, 0] * (c - a)[:, 1] - (b - a)[:, 1] * (c - a)[:, 0]
    flip = np.sign(cr) != w0
    tri[flip] = tri[flip][:, [0, 2, 1]]
    return tri


def chain_network(net: cn.Network):
    """(cnet, keep): the chains-only Network (module doc) and the ids in net of its points (-1: a line's lattice point)."""
    rows_of: dict = {}
    for f, row in net.fold_rows():
        rows_of.setdefault(int(net.piece[row[0]]), []).append(row)
    keep = np.unique(np.r_[net.chain_v.ravel(), net.closed_links.ravel(),
                           np.concatenate([r for rs in rows_of.values() for r in rs]) if rows_of else []]).astype(np.int64)
    keep = np.unique(np.r_[keep, net.root[keep]])
    idx = -np.ones(net.n, np.int64)
    idx[keep] = np.arange(len(keep))
    U, PC, SRC, lines = _lattice(net, keep, idx, rows_of)
    nk, nl = len(keep), len(U)
    uv_all, piece_all = np.r_[net.uv[keep], U], np.r_[net.piece[keep], PC]
    F = []
    for p in range(len(net.names)):
        pts = np.where(piece_all == p)[0]
        if len(pts) >= 3:
            F.append(_piece_faces(net, p, pts, [idx[r] for r in rows_of.get(p, [])], uv_all))
    F = np.concatenate(F)
    c = cn.Network.__new__(cn.Network)
    M = {k: v for k, v in net.M.items() if k not in ("uv", "F", "piece", "sew", "folds", "closures")}
    sew = net.sew[(idx[net.sew] >= 0).all(1)]
    M.update(uv=uv_all, F=F, piece=piece_all, sew=idx[sew])
    M["folds"] = [dict(f, rows=[idx[np.asarray(r, np.int64)] for r in f.get("rows") or []]) for f in net.M.get("folds") or []]
    cls = []
    for cd in net.M.get("closures") or []:  # (a tie's points on the nearest chain point of their piece)
        vv = []
        for pair in cd.get("v") or []:
            q = []
            for v in pair:
                own = np.where(net.piece[keep] == net.piece[v])[0]
                q.append(int(own[np.argmin(np.linalg.norm(net.uv[keep[own]] - net.uv[v], axis=1))]) if idx[v] < 0
                         else int(idx[v]))
            vv.append(q)
        cls.append(dict(cd, v=vv))
    M["closures"] = cls
    c.M, c.uv, c.F, c.piece, c.names = M, M["uv"], F, M["piece"], list(net.names)
    c.n, c.sew = len(uv_all), M["sew"]
    c.stiff, c.bend = np.r_[net.stiff[keep], net.stiff[SRC]], np.r_[net.bend[keep], net.bend[SRC]]
    c.root = np.r_[idx[net.root[keep]], nk + np.arange(nl)]
    c.edges = cn.edges_of(F)
    c.flat = np.linalg.norm(c.uv[c.edges[:, 0]] - c.uv[c.edges[:, 1]], axis=1)
    c.closed_links = idx[net.closed_links]
    # the chains: the pattern's (boundary 0, fold rows 1), then the lines across (2 along the grain, 3 across), each
    # line link once and never where the pattern already has a link between the same two nodes
    lv = np.array([(a, b) for ch, _ in lines for a, b in zip(ch[:-1], ch[1:])], np.int64).reshape(-1, 2)
    lk = np.array([k for ch, k in lines for _ in ch[1:]], int)
    key = np.sort(c.root[lv], axis=1)
    have = {tuple(e) for e in np.sort(c.root[idx[net.chain_v]], axis=1).tolist()}
    ok = (key[:, 0] != key[:, 1]) & np.array([tuple(e) not in have for e in key.tolist()], bool)
    _, first = np.unique(key[ok], axis=0, return_index=True)
    sel = np.where(ok)[0][np.sort(first)]
    lv, lk = lv[sel], lk[sel]
    lL = np.linalg.norm(c.uv[lv[:, 0]] - c.uv[lv[:, 1]], axis=1)
    c.chain_v = np.r_[idx[net.chain_v], lv]
    c.chain_L = np.r_[net.chain_L, lL]
    c.chain_kind = np.r_[net.chain_kind, lk]
    c.chain_piece = np.r_[net.chain_piece, c.piece[lv[:, 0]]]
    c.link_i, c.link_j = np.r_[idx[net.link_i], c.root[lv[:, 0]]], np.r_[idx[net.link_j], c.root[lv[:, 1]]]
    c.link_L = np.r_[net.link_L, lL]
    c.link_cut = np.r_[net.link_cut, np.c_[lL, lL]]
    c.link_of_chain = np.r_[net.link_of_chain, len(net.link_L) + np.arange(len(lv))]
    # (each piece's outline is the PATTERN's, its kept points in order: the chain faces between rows are not a clean
    # disk, and a loop walked on them breaks at the rows' ends (a collar's read 199 of its 373 edges, C444))
    c.outlines = {}
    for nm in net.names:
        lp = idx[net.loop(nm)]
        c.outlines[nm] = lp[lp >= 0]
    return c, np.r_[keep, -np.ones(nl, np.int64)]


def _lattice(net, keep, idx, rows_of):
    """Every piece's lines across (chain_lines.lines): lattice uv (k, 2), piece, nearest pattern vertex of the piece,
    and [(chain as ids in the new network: kept points first, lattice points after, kind)]."""
    grain = net.M.get("grain") or {}
    U, PC, SRC, out = [], [], [], []
    base = len(keep)
    for p, nm in enumerate(net.names):
        pts = keep[net.piece[keep] == p]
        if len(pts) < 3:
            continue
        u, chains, fam = cl.lines(net.uv, pts, net.uv[net.loop(nm)], rows_of.get(p, []), float(grain.get(nm, 90.0)))
        own = np.where(net.piece == p)[0]
        if len(u):
            U.append(u)
            PC.append(np.full(len(u), p))
            SRC.append(own[np.argmin(np.linalg.norm(net.uv[own][None] - u[:, None], axis=2), axis=1)])
        for ch, f in zip(chains, fam):
            out.append(([int(idx[r]) if r >= 0 else base + (-1 - r) for r in ch], 2 + f))
        base += len(u)
    if not U:
        return np.zeros((0, 2)), np.zeros(0, net.piece.dtype), np.zeros(0, np.int64), out
    return np.concatenate(U), np.concatenate(PC).astype(net.piece.dtype), np.concatenate(SRC), out
