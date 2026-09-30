"""Sharp features for marching-cubes meshes of the terrain field (Kobbelt et al.'s Extended Marching Cubes, on the
exact field), and how far a mesh's creases stray from the field's.

Marching cubes puts vertices only on lattice edges, so a crease running across its cells comes out as a sawtooth
(each cell cuts the corner). Here every cell whose surface patch sees normals that disagree (a crease or a corner
inside the cell) gets one extra vertex at the point its tangent planes meet (a QEF on the exact field's normals at
the patch's vertices, as dual contouring places vertices), the patch is replaced by a fan round it, and then every
edge between two fans is flipped to join the two feature vertices: the mesh's edges now run along the crease.
Tile borders are untouched: a patch's own boundary (on the cell faces) stays, so the canonical border chains are
kept bit for bit."""

from __future__ import annotations

import math

import numpy as np

SHARP_COS = math.cos(math.radians(20.0))  # a patch whose normals spread wider than this has a feature


def _unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def _face_normals(P, F):
    return _unit(np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]]))


def feature_points(P, F, idx, N, field, to_world, v, movable, bounds=None, sharp_cos=SHARP_COS):
    """Extended marching cubes on one tile's mesh. P: vertices on the surface (world), F: faces, idx: the vertices'
    lattice coordinates as marching cubes made them (a face's cell is floor of its centroid), N: exact unit normals
    at P, to_world: lattice coordinates -> world, v: voxel, movable: vertices that may change (not tile borders).
    Returns (P, F, N, n_feature): the feature vertices appended to P."""
    cell = np.floor(idx[F].mean(1) + 1e-9).astype(np.int64)
    # the cells whose patch normals spread: a normal cone wider than acos(sharp_cos)
    key = (cell[:, 0] * 1_000_003 + cell[:, 1]) * 1_000_033 + cell[:, 2]
    order = np.argsort(key, kind="stable")
    ks = key[order]
    starts = np.r_[0, np.flatnonzero(ks[1:] != ks[:-1]) + 1]
    ends = np.r_[starts[1:], len(ks)]
    # quick test per cell: the smallest dot of a corner normal with the cell's mean normal
    grp = np.empty(len(F), np.int64)
    grp[order] = np.repeat(np.arange(len(starts)), ends - starts)
    m = np.zeros((len(starts), 3))
    for c in range(3):
        np.add.at(m, grp, N[F[:, c]])
    m = _unit(m)
    worst = np.ones(len(starts))
    for c in range(3):
        np.minimum.at(worst, grp, (N[F[:, c]] * m[grp]).sum(1))
    cand = np.flatnonzero(worst < math.sqrt((1 + sharp_cos) / 2))  # (half the cone's angle)
    newP, newN, fans, drop = [], [], [], []
    nP = len(P)
    for g in cand:
        fs = order[starts[g]:ends[g]]
        tri = F[fs]  # (a patch touching a tile border keeps its boundary edges: the border chain is unchanged)
        # components of the patch (faces sharing a vertex)
        comps = _components(tri)
        for comp in comps:
            t = tri[comp]
            vs = np.unique(t)
            n = N[vs]
            if (n @ n.T).min() >= sharp_cos:
                continue
            p = P[vs]
            c = p.mean(0)
            A = np.einsum("ki,kj->ij", n, n)
            b = np.einsum("ki,kj,kj->i", n, n, p - c)
            U, s, Vt = np.linalg.svd(A)
            inv = np.where(s > 0.1 * s[0], 1.0 / np.maximum(s, 1e-12), 0.0)
            x = c + Vt.T @ (inv * (U.T @ b))
            lo, hi = to_world(cell[fs[comp[0]]]), to_world(cell[fs[comp[0]]] + 1)
            pad = 0.2 * v
            if np.any(x < lo - pad) or np.any(x > hi + pad):
                continue
            if bounds is not None and (np.any(x[:2] <= bounds[0] + 1e-3 * v) or np.any(x[:2] >= bounds[1] - 1e-3 * v)):
                continue
            # the patch's boundary loop (directed edges whose reverse isn't in the patch)
            e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
            es = set(map(tuple, e.tolist()))
            bd = [(a, b_) for a, b_ in es if (b_, a) not in es]
            nxt = dict(bd)
            if len(nxt) != len(bd) or len(bd) < 3:
                continue
            loop, cur = [bd[0][0]], nxt[bd[0][0]]
            while cur != loop[0] and len(loop) <= len(bd):
                loop.append(cur)
                cur = nxt.get(cur, -1)
            if cur != loop[0] or len(loop) != len(bd):
                continue
            fid = nP + len(newP)
            fan = np.array([(a, b_, fid) for a, b_ in zip(loop, loop[1:] + loop[:1])], np.int64)
            newP.append(x)
            newN.append(_unit(n.sum(0)))
            fans.append(fan)
            drop.append(fs[comp])
    if not newP:
        return P, F, N, 0
    newP = np.array(newP)
    # on the surface (the tangent planes can meet off it where the field curves), and no fan turned over
    f_at = field.value(newP)
    ok_pt = np.abs(f_at) < 0.15 * v
    P2 = np.vstack([P, newP])
    keep_face = np.ones(len(F), bool)
    add = []
    nfeat = 0
    for k, (fan, d) in enumerate(zip(fans, drop)):
        if not ok_pt[k]:
            continue
        fn = _face_normals(P2, fan)
        ref = _unit(N[fan[:, 0]] + N[fan[:, 1]])
        if ((fn * ref).sum(1) < 0.2).any():
            continue
        keep_face[d] = False
        add.append(fan)
        nfeat += 1
    if not add:
        return P, F, N, 0
    F2 = np.vstack([F[keep_face], np.vstack(add)])
    N2 = np.vstack([N, np.array(newN)])
    # vertices of rejected fans are unused: drop them
    used = np.zeros(len(P2), bool)
    used[F2.ravel()] = True
    used[:nP] = True
    remap = np.cumsum(used) - 1
    P2, N2, F2 = P2[used], N2[used], remap[F2]
    F2 = flip_to_features(P2, F2, N2, nP)
    return P2, F2, N2, nfeat


def _components(tri):
    """Groups of a few faces that share vertices (union-find over at most ~5 faces)."""
    n = len(tri)
    if n == 1:
        return [np.array([0])]
    par = list(range(n))

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    for a in range(n):
        for b in range(a + 1, n):
            if set(tri[a].tolist()) & set(tri[b].tolist()):
                par[find(a)] = find(b)
    out = {}
    for a in range(n):
        out.setdefault(find(a), []).append(a)
    return [np.array(v) for v in out.values()]


def flip_to_features(P, F, N, first_feature, min_dot=0.2):
    """Flip every edge between two ordinary vertices whose two faces' third corners are both feature vertices
    (index >= first_feature), so the edge joins the feature vertices and the crease runs along mesh edges. A flip is
    skipped if the new edge exists already or a new face turns away from the surface normals."""
    F = F.copy()
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    third = np.concatenate([F[:, 2], F[:, 0], F[:, 1]])
    fid = np.tile(np.arange(len(F)), 3)
    isf = np.zeros(len(P), bool)
    isf[first_feature:] = True
    # directed edge (a, b) in face f1 with apex c1; its twin (b, a) in f2 with apex c2
    sel = ~isf[e[:, 0]] & ~isf[e[:, 1]] & isf[third] & (e[:, 0] < e[:, 1])
    n = len(P)
    fwd = {int(k): i for i, k in enumerate(e[:, 0] * n + e[:, 1])}
    edges = set(map(int, np.minimum(e[:, 0], e[:, 1]) * n + np.maximum(e[:, 0], e[:, 1])))
    done = np.zeros(len(F), bool)
    for i in np.flatnonzero(sel):
        a, b = int(e[i, 0]), int(e[i, 1])
        j = fwd.get(b * n + a)
        if j is None or not isf[third[j]]:
            continue
        f1, f2 = int(fid[i]), int(fid[j])
        if done[f1] or done[f2]:
            continue
        c1, c2 = int(third[i]), int(third[j])
        if c1 == c2 or min(c1, c2) * n + max(c1, c2) in edges:
            continue
        # faces (a, b, c1) and (b, a, c2) -> (a, c2, c1) and (c2, b, c1)
        t1, t2 = np.array([a, c2, c1]), np.array([c2, b, c1])
        fn = _face_normals(P, np.array([t1, t2]))
        ref = _unit(np.array([N[t1].sum(0), N[t2].sum(0)]))
        if ((fn * ref).sum(1) < min_dot).any():
            continue
        F[f1], F[f2] = t1, t2
        done[f1] = done[f2] = True
        edges.add(min(c1, c2) * n + max(c1, c2))
    return F


def crease_error(P, F, field, h, sharp_deg=25.0, rock=None):
    """How well a mesh follows the field's creases. (1) mesh creases: edges whose faces turn by more than
    `sharp_deg`, sampled at 1/4, 1/2, 3/4: distance off the surface (|F|, m); a crease that zigzags across the true
    one cuts corners, so its edges leave the surface. (2) face normals against the field's normal at each face's
    centre (area weighted, degrees): sawtooth faces are tilted. `rock`: optional mask per face (only these)."""
    _, uid, inv = np.unique(np.round(P, 6), axis=0, return_index=True, return_inverse=True)  # (weld split vertices)
    P, F = P[uid], inv.ravel()[F]
    fn = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    area = np.linalg.norm(fn, axis=1) / 2
    fn = _unit(fn)
    sel = np.ones(len(F), bool) if rock is None else rock
    c = P[F].mean(1)
    _, g = field.value_gradient(c[sel], h)
    ang = np.degrees(np.arccos(np.clip((fn[sel] * _unit(g)).sum(1), -1, 1)))
    w = area[sel]
    o = np.argsort(ang)
    cw = np.cumsum(w[o]) / max(w.sum(), 1e-12)
    pct = lambda q: float(ang[o][min(np.searchsorted(cw, q), len(o) - 1)])
    # sharp edges
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    f = np.tile(np.arange(len(F)), 3)
    key = np.minimum(e[:, 0], e[:, 1]) * (len(P) + 1) + np.maximum(e[:, 0], e[:, 1])
    o2 = np.argsort(key, kind="stable")
    same = key[o2][1:] == key[o2][:-1]
    fa, fb = f[o2][:-1][same], f[o2][1:][same]
    ea = e[o2][:-1][same]
    dih = np.degrees(np.arccos(np.clip((fn[fa] * fn[fb]).sum(1), -1, 1)))
    sh = (dih > sharp_deg) & sel[fa] & sel[fb]
    E = ea[sh]
    if len(E):
        t = np.array([0.25, 0.5, 0.75])
        S = (P[E[:, 0]][:, None] * (1 - t)[None, :, None] + P[E[:, 1]][:, None] * t[None, :, None]).reshape(-1, 3)
        d = np.abs(field.value(S))
        cr = [round(float(np.percentile(d, q)), 4) for q in (50, 95)]
        L = np.linalg.norm(P[E[:, 1]] - P[E[:, 0]], axis=1).sum()
    else:
        cr, L = [0.0, 0.0], 0.0
    return {"normal_err_deg_p50_p95": [round(pct(0.5), 2), round(pct(0.95), 2)],
            "crease_edges_m": round(float(L), 1), "crease_off_surface_m_p50_p95": cr}
