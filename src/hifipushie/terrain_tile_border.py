"""A tile's border: its polylines, welding rows, simplifying and collapsing along the border so neighbours
meet. Part of the terrain mesh (terrain_mesh.py has the overview)."""
from __future__ import annotations

import math

import numpy as np

from .terrain_tile_mesh import _boundary_edges

def _polylines(edges):
    """The ordered vertex lists an undirected edge set makes: open chains (from a vertex that isn't degree 2) and
    closed loops (first vertex repeated at the end). Deterministic: walks start at the lowest row."""
    adj = {}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    done = set()

    def walk(s):
        line, cur = [s], s
        while True:
            nxt = sorted(x for x in adj[cur] if (min(cur, x), max(cur, x)) not in done)
            if not nxt:
                return line
            x = nxt[0]
            done.add((min(cur, x), max(cur, x)))
            line.append(x)
            cur = x
            if cur == s:
                return line

    out = []
    for s in sorted(v for v, n in adj.items() if len(n) != 2):
        while any((min(s, x), max(s, x)) not in done for x in adj[s]):
            out.append((walk(s), False))
    for s in sorted(adj):
        if any((min(s, x), max(s, x)) not in done for x in adj[s]):
            out.append((walk(s), True))
    return out


WELD = 1e-3  # x voxel: canonical border vertices joined by a chain edge and closer than this are one vertex


def _weld_rows(plane_edges, CP, corner, tol):
    """{row: the row it is welded to} for canonical border rows joined by a border chain edge and closer than tol.
    Two marching-cubes crossings whose Newton steps converge on one point (a corner of pebble's karst passage in a tile
    border plane: 7e-7 m apart) are one vertex in the GLB's float32 positions: the sliver face between them turns
    degenerate and its neighbours meet on a non-manifold edge with doubled directed edges. Dropping one in the chain
    simplification wasn't enough (a border collapse that failed at a coarser LOD put it back at every LOD), so the pair
    is merged before any LOD is made: in the chains here and in each tile's dense mesh (`_job_dense`). Corners win."""
    par = {}

    def find(x):
        while par.get(x, x) != x:
            x = par[x]
        return x

    for e in plane_edges.values():
        for a, b in e:
            if a != b and float(np.linalg.norm(CP[a] - CP[b])) < tol:
                ra, rb = find(a), find(b)
                if ra == rb:
                    continue
                if corner[ra] and corner[rb]:
                    continue
                keep_, gone = (ra, rb) if corner[ra] or (not corner[rb] and ra < rb) else (rb, ra)
                par[gone] = keep_
    return {x: find(x) for x in par}


def _simplify(P, line, closed, tol, always):
    """Douglas-Peucker on a chain of rows (in 3D, within its border plane): the rows kept, in order. Ends, and rows
    in `always` (tile corners), are kept; a loop keeps at least 3 (it must not close up)."""
    pts = [r for r in line if r in always] if closed else []
    keep = {line[0], line[-1], *[r for r in line if r in always]}

    def dp(a, b):
        stack = [(a, b)]
        while stack:
            a, b = stack.pop()
            if b <= a + 1:
                continue
            A, B = P[line[a]], P[line[b]]
            Q = P[line[a + 1:b]]
            d = B - A
            L2 = max(float(d @ d), 1e-18)
            t = np.clip((Q - A) @ d / L2, 0, 1)
            e = np.linalg.norm(Q - (A + t[:, None] * d), axis=1)
            k = int(np.argmax(e))
            if e[k] > tol:
                keep.add(line[a + 1 + k])
                stack += [(a, a + 1 + k), (a + 1 + k, b)]

    if closed:
        body = line[:-1]
        far = int(np.argmax(np.linalg.norm(P[body] - P[body[0]], axis=1)))
        keep.add(body[far])
        dp(0, far)
        dp(far, len(line) - 1)
        if len(keep) < 3:  # a thin loop: the vertex furthest from its chord too
            A, B = P[body[0]], P[body[far]]
            d = np.linalg.norm(np.cross(P[body] - A, B - A), axis=1)
            keep.add(body[int(np.argmax(d))])
    else:
        # the anchors split the chain; each piece simplified on its own
        anchors = [i for i, r in enumerate(line) if r in keep]
        for a, b in zip(anchors, anchors[1:]):
            dp(a, b)
    del pts
    return [r for r in line if r in keep]


def _needs(lines, keep, CP, lods):
    """Per LOD, per canonical row on a kept chain: how far it is from the same plane's chains at the other LODs
    (what a skirt there has to cover)."""
    segs = {}
    for pl, L in lines.items():
        for k in range(lods):
            s = []
            for ln, closed in L:
                kept = [r for r in ln if r in keep[k]]
                s += list(zip(kept, kept[1:]))
            segs[pl, k] = np.array([[CP[x], CP[y]] for x, y in s]).reshape(-1, 2, 3)
    need = [np.zeros(len(CP)) for _ in range(lods)]
    for (pl, k), sg in segs.items():
        rows = np.unique(np.array(list(_plane_rows(lines[pl], keep[k])), np.int64))
        if not len(rows):
            continue
        for j2 in range(lods):
            if j2 != k and len(segs[pl, j2]):
                need[k][rows] = np.maximum(need[k][rows], _chain_dist(CP[rows], segs[pl, j2]))
    return need


def _plane_rows(L, keep):
    for ln, _ in L:
        for r in ln:
            if r in keep:
                yield r


def _cross3(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    return (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)


def _collapse_border(P, F, drop, min_dot=0.2):
    """Collapse each border vertex in `drop` into a neighbour along the border (half-edge collapse onto the
    neighbour's position). Returns the faces left and the vertices that couldn't go without turning a face over or
    joining the mesh badly (the link condition)."""
    F = F.copy()
    Pl = P.tolist()
    alive = np.ones(len(F), bool)
    bn = {}
    for a, b in _boundary_edges(F):
        bn.setdefault(int(a), set()).add(int(b))
        bn.setdefault(int(b), set()).add(int(a))
    # faces are only looked up round border vertices (a collapse moves a border vertex onto a border vertex)
    isb = np.zeros(int(F.max()) + 1, bool)
    isb[list(bn)] = True
    vf = {}
    for f in np.flatnonzero(isb[F].any(1)):
        for v in F[f]:
            if isb[v]:
                vf.setdefault(int(v), set()).add(int(f))
    dropping = set(int(u) for u in drop)

    def nbrs(v):
        return {int(x) for f in vf.get(v, ()) for x in F[f]} - {v}

    def attempt(u, w):
        fu = vf.get(u, set())
        shared = [f for f in fu if w in F[f]]
        if len(shared) != 1 or len(fu) < 2:  # (u's only face gone would leave w and the third vertex stranded)
            return False
        third = [int(x) for x in F[shared[0]] if x != u and x != w]
        if len(vf.get(w, ())) < 2 or (third[0] in vf and len(vf[third[0]]) < 2):
            return False
        if nbrs(u) & nbrs(w) != set(third):
            return False
        for f in fu:
            if f == shared[0]:
                continue
            tri = F[f]
            n0 = _cross3(Pl[tri[0]], Pl[tri[1]], Pl[tri[2]])
            t2 = [w if x == u else x for x in tri]
            n1 = _cross3(Pl[t2[0]], Pl[t2[1]], Pl[t2[2]])
            l0 = math.sqrt(n0[0] ** 2 + n0[1] ** 2 + n0[2] ** 2)
            l1 = math.sqrt(n1[0] ** 2 + n1[1] ** 2 + n1[2] ** 2)
            if l1 < 1e-9 or n0[0] * n1[0] + n0[1] * n1[1] + n0[2] * n1[2] <= min_dot * l0 * l1:
                return False
        f0 = shared[0]
        alive[f0] = False
        for x in F[f0]:
            vf.get(int(x), set()).discard(f0)
        for f in list(vf[u]):
            F[f][F[f] == u] = w
            vf.setdefault(w, set()).add(f)
        vf[u] = set()
        for x in bn.pop(u, set()):
            bn[x].discard(u)
            if x != w:
                bn[x].add(w)
                bn[w].add(x)
        return True

    pending = sorted(dropping)
    for _ in range(4):
        left = []
        for u in pending:
            # into a neighbour that stays if there is one (fewer moves), else one that goes later
            cands = sorted(bn.get(u, ()), key=lambda x: (x in dropping, x))
            if not any(attempt(u, w) for w in cands):
                left.append(u)
            else:
                dropping.discard(u)
        if len(left) == len(pending):
            break
        pending = left
    return F[alive], set(pending)


def _chain_dist(A, segs_b):
    """Distance from points A (n, 3) to the nearest of the segments (m, 2, 3)."""
    if not len(segs_b):
        return np.full(len(A), np.inf)
    P0, D = segs_b[:, 0], segs_b[:, 1] - segs_b[:, 0]
    L2 = np.maximum((D * D).sum(1), 1e-18)
    out = np.empty(len(A))
    for s0 in range(0, len(A), 256):
        Q = A[s0:s0 + 256, None, :] - P0[None]
        t = np.clip((Q * D[None]).sum(2) / L2[None], 0, 1)
        out[s0:s0 + 256] = np.linalg.norm(Q - t[..., None] * D[None], axis=2).min(1)
    return out
