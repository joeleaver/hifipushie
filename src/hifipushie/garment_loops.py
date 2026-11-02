"""Step 10, EXPORT: a piece re-gridded in clean LOOPS (T11b, C293), the game artist's retopology of a flat pattern.

garment_game.remesh_panel (the old route) put a hex grid inside each panel + its border samples, Delaunay, trimmed:
no loops round an armhole, cuff, collar edge or hem, so a joint bent through a jagged strip and a weight jump showed
as a kink (Joe, T11's shirt). Here, per piece, in the pattern's 2D (its UVs stay the pattern):
  * the border is garment_game.boundaries' samples, untouched (a seam resampled ONCE, shared by both sides: no crack);
  * RINGS: LOOP_RINGS loops of points offset inward from the border by h, 2h ... along the border's inward normal
    (mitred at corners), so every edge (seam, armhole, cuff, collar edge, hem) gets loops parallel to it; a ring
    point is dropped where the ring would come closer than 0.75 x its offset to another border (a narrow piece keeps
    fewer rings) or bunch closer than RING_MERGE x h to the last point kept (a concave corner: a triangle there);
  * inside the last ring, a square GRID along the grain (the pattern's axes) at h;
  * LINES kept as vertex rows: the pattern's folds (a collar's roll) at h / 2, and JOINT lines: where the garment
    goes round a joint the rig bends (an elbow, a knee: rig bones named in BEND_JOINTS, found from the body's joints,
    not per garment), the cut of the piece by the plane through the joint across the limb, at h: an extra loop
    across the tube;
  * Delaunay of all the points, trimmed to the piece (remesh_panel's rules), then triangle PAIRS merged into quads
    (best first, convex, every corner within QUAD_MAX_SKEW of 90 deg), never across a border / ring / line edge:
    quad-dominant, triangles only where the shape forces one. The game file stays triangles (each quad its two).
Returns remesh_panel's dict plus "quads" [q, 4] and "tris" [t, 3] (the face set before triangulation) and "rings".
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import Delaunay, cKDTree

from .garment_game import MPath, _area2, _bary_map, _interp_chain

LOOP_RINGS = 2  # loops parallel to every edge ("a few rings in"); more cost triangles a coarse budget can't pay
RING_MERGE = 0.6  # x h: ring points closer than this to the last kept merge (a concave corner)
QUAD_MAX_SKEW = 40.0  # deg: a merged quad's corners stay within this of 90
BEND_JOINTS = ("ForeArm", "Leg")  # Mixamo hinge joints (elbow, knee): the head of these bones
JOINT_REACH = 1.6  # a joint line's points: nearest rig segment is the joint's own two bones, within this x the median


def _inward(P: np.ndarray) -> np.ndarray:
    """Mitred inward normals of a CCW closed polyline (scaled so an offset d keeps d from both edges, capped 2x)."""
    t = np.roll(P, -1, 0) - P
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-15)
    n_next = np.stack([-t[:, 1], t[:, 0]], 1)
    n_prev = np.roll(n_next, 1, 0)
    m = n_prev + n_next
    m /= np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-15)
    c = np.maximum((m * n_next).sum(1), 0.5)
    return m / c[:, None]


def _smooth_ring(Q: np.ndarray, rounds: int = 2) -> np.ndarray:
    for _ in range(rounds):
        Q = 0.5 * Q + 0.25 * (np.roll(Q, 1, 0) + np.roll(Q, -1, 0))
    return Q


def rings(loop2: np.ndarray, h: float, dense: np.ndarray, poly: MPath, avoid: np.ndarray | None = None,
          n: int = LOOP_RINGS) -> list[np.ndarray]:
    """Up to n rings of points offset inward from the border (module docstring). avoid: line samples (folds, joints)
    no ring point comes within 0.45 h of."""
    out = []
    N = _inward(loop2)
    tree = cKDTree(dense)
    at = cKDTree(avoid) if avoid is not None and len(avoid) else None
    for i in range(1, n + 1):
        d = i * h
        Q = _smooth_ring(loop2 + d * N)
        ok = poly.contains_points(Q) & (tree.query(Q)[0] > 0.75 * d)
        if at is not None:
            ok &= at.query(Q)[0] > 0.45 * h
        if ok.mean() < 0.5 or ok.sum() < 4:
            break
        kept, last = [], None
        for j in np.flatnonzero(ok):
            if last is None or np.linalg.norm(Q[j] - last) >= RING_MERGE * h:
                kept.append(Q[j])
                last = Q[j]
        if len(kept) > 2 and np.linalg.norm(kept[0] - kept[-1]) < RING_MERGE * h:
            kept.pop()
        if len(kept) < 4:
            break
        out.append(np.array(kept))
    return out


def grid(inner: MPath, lo, hi, h: float) -> np.ndarray:
    """A square grid along the grain (the pattern's axes) at h, inside `inner`."""
    xs, ys = np.arange(lo[0] + h / 2, hi[0], h), np.arange(lo[1] + h / 2, hi[1], h)
    if not len(xs) or not len(ys):
        return np.zeros((0, 2))
    G = np.stack(np.meshgrid(xs, ys), -1).reshape(-1, 2)
    return G[inner.contains_points(G)]


def _sample(L: np.ndarray, step: float) -> np.ndarray:
    n = max(2, int(np.ceil(np.linalg.norm(np.diff(L, axis=0), axis=1).sum() / step)) + 1)
    return _interp_chain(L, np.linspace(0, len(L) - 1, n))


def pair_quads(P2: np.ndarray, tri: np.ndarray, protect: set) -> tuple[np.ndarray, np.ndarray]:
    """Greedy best-first merge of triangle pairs into quads (convex, corners within QUAD_MAX_SKEW of 90 deg), never
    removing a protected edge. Returns (quads [q, 4] in the triangles' winding, leftover tris)."""
    E = {}
    for f, t in enumerate(tri):
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            E.setdefault((min(a, b), max(a, b)), []).append(f)
    cand = []
    for (a, b), fs in E.items():
        if len(fs) != 2 or (a, b) in protect:
            continue
        f, g = fs
        tf, tg = list(tri[f]), list(tri[g])
        c = [x for x in tf if x not in (a, b)][0]
        d = [x for x in tg if x not in (a, b)][0]
        k = tf.index(c)
        q = [c, tf[(k + 1) % 3], d, tf[(k + 2) % 3]]  # c, next, opposite, prev: the merged loop in f's winding
        Q = P2[q]
        e1, e0 = np.roll(Q, -1, 0) - Q, Q - np.roll(Q, 1, 0)
        cr = e0[:, 0] * e1[:, 1] - e0[:, 1] * e1[:, 0]
        if not (np.all(cr > 0) or np.all(cr < 0)):
            continue
        cosang = (-e0 * e1).sum(1) / np.maximum(np.linalg.norm(e0, axis=1) * np.linalg.norm(e1, axis=1), 1e-15)
        skew = float(np.max(np.abs(np.degrees(np.arccos(np.clip(cosang, -1, 1))) - 90)))
        if skew <= QUAD_MAX_SKEW:
            cand.append((skew, f, g, q))
    used = np.zeros(len(tri), bool)
    quads = []
    for _, f, g, q in sorted(cand, key=lambda x: x[0]):
        if not used[f] and not used[g]:
            used[f] = used[g] = True
            quads.append(q)
    return np.array(quads, int).reshape(-1, 4), tri[~used]


def remesh_loops(drape: dict, name: str, bd: dict, h: float, lines=(), joint_lines=()) -> dict:
    """One piece in loops (module docstring); bd from garment_game.boundaries; lines: fold polylines (2D), joint_lines:
    joint polylines (2D). Same dict as garment_game.remesh_panel + quads / tris / rings."""
    i = drape["names"].index(name)
    pc, F = drape["piece"], drape["F"]
    Fi = F[(pc[F] == i).all(1)]
    loop2, loop3 = bd["loop2d"], bd["loop3d"]
    nb = len(loop2)
    poly = MPath(np.vstack([loop2, loop2[:1]]))
    dense = _interp_chain(np.vstack([loop2, loop2[:1]]), np.linspace(0, nb, nb * 10 + 1))
    S = [(_sample(np.asarray(L, float), 0.5 * h), "fold") for L in lines if len(L) > 1]
    S += [(_sample(np.asarray(L, float), h), "joint") for L in joint_lines if len(L) > 1]
    rows = []
    for X, _ in S:
        X = X[poly.contains_points(X)]
        if len(X):
            X = X[cKDTree(dense).query(X)[0] > 0.3 * h]
        if len(X) > 1:
            rows.append(X)
    Lp = np.vstack(rows) if rows else np.zeros((0, 2))
    R = rings(loop2, h, dense, poly, Lp if len(Lp) else None)
    if R:
        inner_loop = R[-1]
        inner = MPath(np.vstack([inner_loop, inner_loop[:1]]))
        idense = _interp_chain(np.vstack([inner_loop, inner_loop[:1]]), np.linspace(0, len(inner_loop), len(inner_loop) * 6 + 1))
        G = grid(inner, loop2.min(0), loop2.max(0), h)
        if len(G):
            G = G[cKDTree(idense).query(G)[0] > 0.6 * h]
    else:
        G = grid(poly, loop2.min(0), loop2.max(0), h)
        if len(G):
            G = G[cKDTree(dense).query(G)[0] > 0.6 * h]
    if len(G) and len(Lp):
        G = G[cKDTree(Lp).query(G)[0] > 0.45 * h]
    pts = [loop2] + R + rows + [G]
    P2 = np.vstack([p for p in pts if len(p)])
    # protected edges: the border, consecutive ring points, consecutive line samples
    protect, off = set(), 0
    for p, closed in [(loop2, True)] + [(r, True) for r in R] + [(r, False) for r in rows]:
        m = len(p)
        for j in range(m if closed else m - 1):
            a, b = off + j, off + (j + 1) % m
            protect.add((min(a, b), max(a, b)))
        off += m
    tri = Delaunay(P2).simplices
    ok = poly.contains_points(P2[tri].mean(1))
    for a, b in ((0, 1), (1, 2), (2, 0)):
        ia, ib = tri[:, a], tri[:, b]
        chord = (ia < nb) & (ib < nb) & ~(((ia - ib) % nb == 1) | ((ib - ia) % nb == 1))
        mid = 0.5 * (P2[ia] + P2[ib])
        ok &= ~chord | (poly.contains_points(mid) & (cKDTree(dense).query(mid)[0] > 0.05 * h))
    tri = tri[ok]
    su = drape["uv"]
    sgn_sim = np.sign(np.median([_area2(su[f]) for f in Fi[:200]]))
    if np.sign(np.median([_area2(P2[t]) for t in tri[:200]])) != sgn_sim:
        tri = tri[:, ::-1]
    quads, tris = pair_quads(P2, tri, protect)
    T = np.vstack([quads[:, [0, 1, 2]], quads[:, [0, 2, 3]], tris]) if len(quads) else tris
    Gin = P2[nb:]
    V3 = np.vstack([loop3, _bary_map(su, Gin, drape["V"], Fi) if len(Gin) else np.zeros((0, 3))])
    gid = np.concatenate([bd["gid"], -np.ones(len(Gin), int)])
    e = set(map(tuple, np.sort(np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]), 1).tolist()))
    missing = sum((min(j, (j + 1) % nb), max(j, (j + 1) % nb)) not in e for j in range(nb))
    free_e = [(j, (j + 1) % nb) for j in range(nb) if bd["free"][j]]
    return {"V": V3, "uv": P2, "T": T, "gid": gid, "free_edges": np.array(free_e, int).reshape(-1, 2),
            "missing_boundary_edges": int(missing), "name": name, "quads": quads, "tris": tris,
            "rings": [len(r) for r in R]}


def quad_share(pieces: list[dict]) -> float:
    """Share of the faces (before triangulation) that are quads."""
    q = sum(len(p.get("quads", ())) for p in pieces)
    t = sum(len(p.get("tris", ())) for p in pieces)
    return q / max(q + t, 1)


# ---------------------------------------------------------------- joint lines

def _seg_d(P, a, b):
    ab = b - a
    t = np.clip(((P - a) @ ab) / max(ab @ ab, 1e-12), 0, 1)
    return np.linalg.norm(P - (a + t[:, None] * ab), axis=1)


def joint_lines(drape: dict, rb: list[dict]) -> dict:
    """{piece: [2D polyline]}: where a piece goes round a joint the rig bends (BEND_JOINTS), the cut of the piece by
    the plane through the joint across the limb (normal: the bisector of the two bones), kept to the points whose
    nearest rig segment is one of the joint's two bones (a sleeve, not the body panel beside it)."""
    from .garment_bend import _dir
    V, uv, F, pc = drape["V"], drape["uv"], drape["F"], drape["piece"]
    heads = np.array([b["head"] for b in rb], float)
    segs = [(i, b["parent"]) for i, b in enumerate(rb) if b["parent"] >= 0]
    A = heads[[p for _, p in segs]]
    B = heads[[c for c, _ in segs]]
    out = {}
    for j, b in enumerate(rb):
        short = b["name"].split(":")[-1]
        if not any(short.endswith(k) and not short.endswith("Up" + k) for k in BEND_JOINTS) or b["parent"] < 0:
            continue
        o = heads[j]
        n = _dir(rb, j) + _dir(rb, b["parent"])
        n /= max(np.linalg.norm(n), 1e-12)
        s = (V - o) @ n
        E = np.unique(np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), 1), axis=0)
        E = E[(np.sign(s[E[:, 0]]) != np.sign(s[E[:, 1]])) & (pc[E[:, 0]] == pc[E[:, 1]])]
        if not len(E):
            continue
        t = s[E[:, 0]] / (s[E[:, 0]] - s[E[:, 1]])
        X = V[E[:, 0]] + t[:, None] * (V[E[:, 1]] - V[E[:, 0]])
        U = uv[E[:, 0]] + t[:, None] * (uv[E[:, 1]] - uv[E[:, 0]])
        D = np.stack([_seg_d(X, A[k], B[k]) for k in range(len(segs))], 1)
        own = {k for k, (c, p) in enumerate(segs) if c == j or p == j}
        near = np.argmin(D, 1)
        keep = np.isin(near, list(own))
        if keep.sum() < 3:
            continue
        r = D[np.arange(len(D)), near]
        keep &= r < JOINT_REACH * np.median(r[keep])
        for p in np.unique(pc[E[keep, 0]]):
            u = U[keep & (pc[E[:, 0]] == p)]
            if len(u) < 3:
                continue
            c = u - u.mean(0)
            ax = np.linalg.svd(c, full_matrices=False)[2][0]
            out.setdefault(drape["names"][p], []).append(u[np.argsort(c @ ax)])
    return out
