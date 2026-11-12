"""CHAIN LAY NET (N2b of docs/proposals/step5_rewrite.md): step 5's network is the CHAINS ONLY (Joe 2026-11-12: "I thought
all this step was supposed to do was lay out the chains"). Step 6 fills the surfaces between them (chain_net.fill).

chain_network(net) -> (cnet, keep): a chain_net.Network over the pattern's CHAIN points only (keep: their ids in net):
- CHAINS: every boundary edge and fold row of net, at its cut, exactly as net has them (links, seams as one shared
  chain, a seam's two sides one link at their mean; nothing is re-derived from the new faces).
- LINES ACROSS: per piece, the Delaunay triangulation of its chain points in the flat, kept inside its outline and never
  across a fold row (each fold row link gets a face on each side, so the fold's turn is measurable). Its edges are the
  rulings between the piece's chains: chain_solve's "edges", exact where interfaced at both ends, else at most their
  flat length; its faces carry the bending stencils and the plies' host triangles. Faces wind as the piece's own flat.
- NO INTERIOR POINTS: a jacket is ~3k chain points (24k surface points before).
Nothing here knows a garment, a piece's role or a wear state.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import Delaunay

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


def _piece_faces(net, p, pts, rows):
    """Faces (orig ids) over the chain points pts of piece p (module doc)."""
    uv = net.uv
    tri = pts[Delaunay(uv[pts]).simplices]
    poly = uv[net.loop(net.names[p])]
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
    w0 = _wind(uv, Fp)
    a, b, c = uv[tri[:, 0]], uv[tri[:, 1]], uv[tri[:, 2]]
    cr = (b - a)[:, 0] * (c - a)[:, 1] - (b - a)[:, 1] * (c - a)[:, 0]
    flip = np.sign(cr) != w0
    tri[flip] = tri[flip][:, [0, 2, 1]]
    return tri


def chain_network(net: cn.Network):
    """(cnet, keep): the chains-only Network (module doc) and the ids in net of its points."""
    rows_of: dict = {}
    for f, row in net.fold_rows():
        rows_of.setdefault(int(net.piece[row[0]]), []).append(row)
    keep = np.unique(np.r_[net.chain_v.ravel(), net.closed_links.ravel(),
                           np.concatenate([r for rs in rows_of.values() for r in rs]) if rows_of else []]).astype(np.int64)
    keep = np.unique(np.r_[keep, net.root[keep]])
    idx = -np.ones(net.n, np.int64)
    idx[keep] = np.arange(len(keep))
    F = []
    for p in range(len(net.names)):
        pts = keep[net.piece[keep] == p]
        if len(pts) >= 3:
            F.append(_piece_faces(net, p, pts, rows_of.get(p, [])))
    F = idx[np.concatenate(F)]
    c = cn.Network.__new__(cn.Network)
    M = {k: v for k, v in net.M.items() if k not in ("uv", "F", "piece", "sew", "folds", "closures")}
    sew = net.sew[(idx[net.sew] >= 0).all(1)]
    M.update(uv=net.uv[keep], F=F, piece=net.piece[keep], sew=idx[sew])
    M["folds"] = [dict(f, rows=[idx[np.asarray(r, np.int64)] for r in f.get("rows") or []]) for f in net.M.get("folds") or []]
    cl = []
    for cd in net.M.get("closures") or []:  # (a tie's points on the nearest chain point of their piece)
        vv = []
        for pair in cd.get("v") or []:
            q = []
            for v in pair:
                own = np.where(net.piece[keep] == net.piece[v])[0]
                q.append(int(own[np.argmin(np.linalg.norm(net.uv[keep[own]] - net.uv[v], axis=1))]) if idx[v] < 0
                         else int(idx[v]))
            vv.append(q)
        cl.append(dict(cd, v=vv))
    M["closures"] = cl
    c.M, c.uv, c.F, c.piece, c.names = M, M["uv"], F, M["piece"], list(net.names)
    c.n, c.sew = len(keep), M["sew"]
    c.stiff, c.bend = net.stiff[keep], net.bend[keep]
    c.root = idx[net.root[keep]]
    c.edges = cn.edges_of(F)
    c.flat = np.linalg.norm(c.uv[c.edges[:, 0]] - c.uv[c.edges[:, 1]], axis=1)
    c.closed_links, c.chain_v = idx[net.closed_links], idx[net.chain_v]
    c.chain_L, c.chain_kind, c.chain_piece = net.chain_L, net.chain_kind, net.chain_piece
    c.link_i, c.link_j = idx[net.link_i], idx[net.link_j]
    c.link_L, c.link_cut, c.link_of_chain = net.link_L, net.link_cut, net.link_of_chain
    return c, keep
