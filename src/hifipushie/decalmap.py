"""Surface-following decal coordinates: a discrete exponential map (Schmidt, Grimm & Wyvill 2006, "Interactive decal
compositing with discrete exponential maps") from a centre point on the exact field, so a sticker lies on any curved
surface like paper: distances from the centre and directions out of it are kept (geodesic polar coordinates), the
stretch that is left is the surface's own Gaussian curvature (a flat sticker can't cover a sphere without it).

The map is computed on a mesh of its own, not the scene's: the field of the decal's parts meshed in a box round the
centre (reach = the decal's half diagonal x REACH, `RES` voxels across), projected onto the exact surface, cut where
the box cut it (no caps). Dijkstra from the centre, ordered by the map's own distance; each vertex's coordinates are
the upwind average of its finished neighbours' coordinates plus the edge carried into their tangent frames (each
frame carried from its parent's by projection onto the vertex's tangent plane). Then a point anywhere is looked up
on its nearest triangle (barycentric), so the coordinates are a function of position: the scene's mesh, the
measured per-vertex inputs and the exported low poly all agree. Cached on disk by content (the parts' primitive
fingerprints and the placement).

Measured on a sphere against its exact log map (tests/test_images.py): error < 1% of the decal at 1.5 radii."""

from __future__ import annotations

import hashlib
import heapq
import json

import numpy as np

REACH = 1.3  # the map runs out to this x the decal's half diagonal (geodesic)
RES = 160  # voxels across the box at most
MIN_VOXEL = 0.0002
VERSION = 3


def _key(prims, fr) -> str:
    from . import sdf
    fps = sorted(sdf.fingerprint(p) for p in prims)
    pl = [np.round(np.asarray(fr[k], float), 7).tolist() for k in ("c", "right", "up", "dir")]
    return hashlib.sha1(json.dumps([fps, pl, round(fr["reach"], 7), round(fr["voxel"], 8), VERSION]).encode()
                        ).hexdigest()[:16]


def _local_mesh(prims, c, reach, voxel):
    """The field's surface in the box c +- reach, projected, with the faces touching the box's walls dropped."""
    from . import sdf
    lo, hi = c - reach, c + reach
    res = int(np.ceil(2 * reach / voxel))
    grid = sdf.evaluate(prims, resolution=res, box=(lo, hi), pad=4 * voxel)  # (pad: the model's own bounds)
    V, F = sdf.mesh(grid, smooth=2)
    glo = grid.origin
    ghi = grid.origin + (np.array(grid.field.shape) - 1) * grid.voxel
    near_wall = ((V < glo + 1.01 * grid.voxel) | (V > ghi - 1.01 * grid.voxel)).any(1)
    F = F[~near_wall[F].any(1)]
    used = np.unique(F)
    remap = np.full(len(V), -1)
    remap[used] = np.arange(len(used))
    V, F = V[used], remap[F]
    V, N = sdf.project(prims, V, F, grid.voxel)
    return V.astype(np.float64), N.astype(np.float64), F.astype(np.int64), grid.voxel


def _csr(n, F):
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    e = np.unique(np.sort(np.concatenate([e, e[:, ::-1]]), axis=1), axis=0)
    e = np.concatenate([e, e[:, ::-1]])
    order = np.argsort(e[:, 0], kind="stable")
    e = e[order]
    indptr = np.searchsorted(e[:, 0], np.arange(n + 1))
    return indptr.astype(np.int64), e[:, 1].astype(np.int64)


def _dem_py(V, N, indptr, nbr, seeds, seed_uv, seed_e1, rmax):
    n = len(V)
    U = np.full((n, 2), np.nan)
    E1 = np.zeros((n, 3))
    dist = np.full(n, np.inf)
    done = np.zeros(n, np.bool_)
    for i in range(len(seeds)):
        s = seeds[i]
        U[s, 0], U[s, 1] = seed_uv[i, 0], seed_uv[i, 1]
        E1[s, 0], E1[s, 1], E1[s, 2] = seed_e1[i, 0], seed_e1[i, 1], seed_e1[i, 2]
        dist[s] = np.sqrt(seed_uv[i, 0] ** 2 + seed_uv[i, 1] ** 2)
    heap = [(dist[seeds[0]], seeds[0])]
    for i in range(1, len(seeds)):
        heapq.heappush(heap, (dist[seeds[i]], seeds[i]))
    while heap:
        d, p = heapq.heappop(heap)
        if done[p] or d != dist[p]:
            continue
        done[p] = True
        if d > rmax:
            continue
        for jj in range(indptr[p], indptr[p + 1]):
            q = nbr[jj]
            if done[q]:
                continue
            su = sv = sw = 0.0
            ax = ay = az = 0.0
            best, br = 1e300, -1
            for kk in range(indptr[q], indptr[q + 1]):
                r = nbr[kk]
                if not done[r]:
                    continue
                dx, dy, dz = V[q, 0] - V[r, 0], V[q, 1] - V[r, 1], V[q, 2] - V[r, 2]
                L2 = dx * dx + dy * dy + dz * dz
                nr = N[r]
                dn = dx * nr[0] + dy * nr[1] + dz * nr[2]
                tx, ty, tz = dx - dn * nr[0], dy - dn * nr[1], dz - dn * nr[2]
                tl = np.sqrt(tx * tx + ty * ty + tz * tz)
                if tl > 1e-30:
                    s_ = np.sqrt(L2) / tl
                    tx, ty, tz = tx * s_, ty * s_, tz * s_
                e1 = E1[r]
                e2x = nr[1] * e1[2] - nr[2] * e1[1]
                e2y = nr[2] * e1[0] - nr[0] * e1[2]
                e2z = nr[0] * e1[1] - nr[1] * e1[0]
                a = U[r, 0] + tx * e1[0] + ty * e1[1] + tz * e1[2]
                b = U[r, 1] + tx * e2x + ty * e2y + tz * e2z
                w = 1.0 / (L2 + 1e-30)
                su += w * a
                sv += w * b
                sw += w
                # the neighbour's frame carried onto q's tangent plane, averaged like the coordinates
                nq = N[q]
                de = e1[0] * nq[0] + e1[1] * nq[1] + e1[2] * nq[2]
                ax += w * (e1[0] - de * nq[0])
                ay += w * (e1[1] - de * nq[1])
                az += w * (e1[2] - de * nq[2])
                if L2 < best:
                    best, br = L2, r
            if br < 0:
                continue
            uq, vq = su / sw, sv / sw
            nd = np.sqrt(uq * uq + vq * vq)
            U[q, 0], U[q, 1] = uq, vq
            fx, fy, fz = ax, ay, az
            fl = np.sqrt(fx * fx + fy * fy + fz * fz)
            if fl > 1e-30:
                E1[q, 0], E1[q, 1], E1[q, 2] = fx / fl, fy / fl, fz / fl
            dist[q] = nd
            heapq.heappush(heap, (nd, q))
    for i in range(n):
        if not done[i]:
            U[i, 0], U[i, 1] = np.nan, np.nan
    return U


try:
    from numba import njit
    _dem = njit(cache=True)(_dem_py)
except ImportError:  # pragma: no cover
    _dem = _dem_py


def build(prims, fr) -> dict:
    """The map for a surface decal frame: {"V", "N", "F", "U" (n, 2) metres along right/up, NaN = not reached,
    "voxel"}. Cached on disk."""
    from . import store
    key = _key(prims, fr)
    path = store.HOME / "_images" / f"m_{key}.npz"
    if path.exists():
        with np.load(path) as z:
            return {k: z[k] for k in z.files} | {"key": key}
    c = np.asarray(fr["c"], float)
    right, up, n0 = (np.asarray(fr[k], float) for k in ("right", "up", "dir"))
    V, N, F, vox = _local_mesh(prims, c, fr["reach"] * 1.02, fr["voxel"])
    if not len(F):
        raise ValueError("the decal's surface map found no surface round its centre")
    indptr, nbr = _csr(len(V), F)
    # seeds: the vertices within 1.5 voxels of the centre, on the centre's tangent plane
    d = np.linalg.norm(V - c, axis=1)
    seeds = np.flatnonzero((d <= 1.5 * vox) & (N @ n0 > 0.5))  # (not the back of a thin board)
    if not len(seeds):
        seeds = np.array([int(np.argmin(d))])
    rel = V[seeds] - c
    rel = rel - (rel @ n0)[:, None] * n0
    seed_uv = np.stack([rel @ right, rel @ up], 1)
    e1 = right[None] - (N[seeds] @ right)[:, None] * N[seeds]
    e1 /= np.maximum(np.linalg.norm(e1, axis=1, keepdims=True), 1e-12)
    U = _dem(V, N, indptr, nbr, seeds.astype(np.int64), seed_uv, e1, float(fr["reach"]))
    out = {"V": V.astype(np.float32), "N": N.astype(np.float32), "F": F.astype(np.int32), "U": U.astype(np.float32),
           "voxel": np.float64(vox)}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.npz")
    np.savez(tmp, **out)
    tmp.replace(path)
    return out | {"key": key}


_TREES: dict = {}


def lookup(m: dict, pos: np.ndarray):
    """(U (n, 2) metres, distance to the map's surface (n,), the map's normal there (n, 3)) at points: each on its
    nearest triangle of the map's mesh (among those round the nearest vertex), barycentric. U is NaN off the map."""
    from scipy.spatial import cKDTree
    V, F, U, N = (m[k].astype(np.float64) if k != "F" else m[k] for k in ("V", "F", "U", "N"))
    key = m.get("key")
    if key is None or key not in _TREES:
        tree = cKDTree(V)
        # each vertex's faces, padded (-1)
        vs = F.ravel().astype(np.int64)
        fs = np.repeat(np.arange(len(F)), 3)
        o = np.argsort(vs, kind="stable")
        vs, fs = vs[o], fs[o]
        start = np.searchsorted(vs, np.arange(len(V)))
        rank = np.arange(len(vs)) - start[vs]
        cap = int(min(rank.max() + 1, 16))
        vf = np.full((len(V), cap), -1, np.int64)
        keep = rank < cap
        vf[vs[keep], rank[keep]] = fs[keep]
        if len(_TREES) > 8:
            _TREES.pop(next(iter(_TREES)))
        _TREES[key] = (tree, vf)
    tree, vf = _TREES[key]
    pos = np.asarray(pos, float)
    n = len(pos)
    outU = np.full((n, 2), np.nan)
    outD = np.full(n, np.inf)
    outN = np.zeros((n, 3))
    if not n:
        return outU, outD, outN
    _, near = tree.query(pos)
    cand = vf[near]  # (n, cap)
    best = np.full(n, np.inf)
    for j in range(cand.shape[1]):
        f = cand[:, j]
        ok = f >= 0
        if not ok.any():
            continue
        i = np.flatnonzero(ok)
        tri = F[f[i]]
        a, b, c = V[tri[:, 0]], V[tri[:, 1]], V[tri[:, 2]]
        w = _closest_bary(pos[i], a, b, c)
        q = w[:, :1] * a + w[:, 1:2] * b + w[:, 2:] * c
        dd = np.linalg.norm(pos[i] - q, axis=1)
        better = dd < best[i]
        k = i[better]
        best[k] = dd[better]
        wb = w[better]
        tb = tri[better]
        outU[k] = (wb[:, :1] * U[tb[:, 0]] + wb[:, 1:2] * U[tb[:, 1]] + wb[:, 2:] * U[tb[:, 2]])
        nn = wb[:, :1] * N[tb[:, 0]] + wb[:, 1:2] * N[tb[:, 1]] + wb[:, 2:] * N[tb[:, 2]]
        outN[k] = nn / np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-12)
    outD = best
    return outU, outD, outN


def _closest_bary(p, a, b, c):
    """Barycentric weights of the closest point on triangles abc to points p (Ericson, Real-Time Collision
    Detection 5.1.5), vectorised."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = p - b
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = p - c
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va = d3 * d6 - d5 * d4
    vb = d5 * d2 - d1 * d6
    vc = d1 * d4 - d3 * d2
    den = np.where(np.abs(va + vb + vc) > 1e-30, va + vb + vc, 1e-30)
    v, w = vb / den, vc / den
    out = np.stack([1 - v - w, v, w], 1)
    # regions outside the face, in the order of the reference
    def put(mask, wts):
        out[mask] = wts[mask]
    one = np.ones_like(d1)
    zero = np.zeros_like(d1)
    m_a = (d1 <= 0) & (d2 <= 0)
    m_b = (d3 >= 0) & (d4 <= d3)
    m_c = (d6 >= 0) & (d5 <= d6)
    t_ab = d1 / np.where(np.abs(d1 - d3) > 1e-30, d1 - d3, 1e-30)
    m_ab = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
    t_ac = d2 / np.where(np.abs(d2 - d6) > 1e-30, d2 - d6, 1e-30)
    m_ac = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
    t_bc = (d4 - d3) / np.where(np.abs((d4 - d3) + (d5 - d6)) > 1e-30, (d4 - d3) + (d5 - d6), 1e-30)
    m_bc = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
    # apply from the lowest priority up, so the reference's first matching case wins
    put(m_bc, np.stack([zero, 1 - t_bc, t_bc], 1))
    put(m_ac, np.stack([1 - t_ac, zero, t_ac], 1))
    put(m_ab, np.stack([1 - t_ab, t_ab, zero], 1))
    put(m_c, np.stack([zero, zero, one], 1))
    put(m_b, np.stack([zero, one, zero], 1))
    put(m_a, np.stack([one, zero, zero], 1))
    return out
