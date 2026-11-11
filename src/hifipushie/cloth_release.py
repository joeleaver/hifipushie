"""The vertices a styling pin names on a garment mesh (`pin_vertices`), used by garment_pull.

What was here before (the release and arrange sims of a fitted garment, tools release_garment / arrange_garment) was
deleted with the older clothing routes on 2026-11-10 (C408).
"""
from __future__ import annotations

import numpy as np


def pin_vertices(M: dict, ref: str) -> np.ndarray:
    """The vertices a pin names: "piece:point" (M["points"]) -> that vertex; "piece:a..b" -> the piece's BORDER from
    point a to point b along its boundary edges, the shorter way round (a front edge from the break to the hem)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra
    P = M.get("points") or {}
    if ".." not in ref:
        if ref not in P:
            raise KeyError(f"no point {ref!r} (points like {', '.join(list(P)[:6])} ...)")
        return np.array([int(P[ref])], np.int64)
    pc, ab = ref.split(":", 1)
    a, b = (f"{pc}:{s}" for s in ab.split(".."))
    for q in (a, b):
        if q not in P:
            raise KeyError(f"no point {q!r}")
    F = np.asarray(M["F"])
    pid = np.asarray(M["piece"])
    k = M["names"].index(pc)
    Fk = F[(pid[F] == k).all(1)]
    E = np.sort(np.r_[Fk[:, [0, 1]], Fk[:, [1, 2]], Fk[:, [2, 0]]], axis=1)
    u, c = np.unique(E, axis=0, return_counts=True)
    B = u[c == 1]  # the piece's boundary edges
    uv = np.asarray(M["uv"], float)
    w = np.linalg.norm(uv[B[:, 0]] - uv[B[:, 1]], axis=1) + 1e-9
    n = len(uv)
    G = coo_matrix((np.r_[w, w], (np.r_[B[:, 0], B[:, 1]], np.r_[B[:, 1], B[:, 0]])), shape=(n, n)).tocsr()
    ia, ib = int(P[a]), int(P[b])
    dist, pred = dijkstra(G, indices=ia, return_predecessors=True)
    if not np.isfinite(dist[ib]):
        raise ValueError(f"{a} and {b} are not joined by {pc}'s border")
    path = [ib]
    while path[-1] != ia:
        path.append(int(pred[path[-1]]))
    return np.asarray(path[::-1], np.int64)

