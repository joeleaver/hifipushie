"""Edge flips after the export's decimation, toward the surface the low poly stands for.

A quadric collapse places vertices well and leaves the diagonals where they fell: over a smooth saddle (the fold of
skin between brow and upper lid, the side of a nose) a long edge can run ACROSS the bend, so one of its two triangles
stands 60-70 degrees off the surface under it. Both lie within a millimetre of it, so the decimation's error says
nothing; shaded, the edge is a hard crease, and a baked normal map can't hide a 68 degree step (Garrett's left upper
lid: a 14 mm edge from the lid's fold up to the brow, a dark line in every blink). An artist turns such an edge.

`flip_to_fit`: every interior edge whose two triangles meet sharply (normals' dot < SHARP) is judged against the
reference surface (the dense mesh the low poly was collapsed from): each triangle's worst agreement with the
reference's normals at seven points of it, now and with the edge turned. It is turned when that improves by GAIN or
more for the worse triangle, both new triangles agree with the reference (FIT), the new pair is no sharper than the
old, and nothing strays further from the reference than it did (+ `tol`). A modelled crease (a lid's margin, a box's
corner) has both triangles agreeing with the surface already: left alone.

numpy only: blender_asset.py imports this (as it does focuswarp.py), giving a BVH lookup as `nearest`."""

from __future__ import annotations

import numpy as np

SHARP = 0.7   # edges whose triangles' normals have a dot under this are looked at (~45 degrees)
GAIN = 0.15   # the worse triangle's agreement with the reference must improve by this (a dot of normals)
FIT = 0.6     # and both new triangles must agree at least this well everywhere
ROUNDS = 4

_W = np.array([[1, 1, 1], [4, 1, 1], [1, 4, 1], [1, 1, 4], [2, 2, 1], [2, 1, 2], [1, 2, 2]], np.float64)
_W /= _W.sum(1, keepdims=True)


def _normals(A, B, C):
    n = np.cross(B - A, C - A)
    a = np.linalg.norm(n, axis=-1, keepdims=True)
    return n / np.maximum(a, 1e-30), a[..., 0] / 2


def _pairs(T: np.ndarray):
    """Interior manifold edges: (a, b, o0, o1, f0, f1) with f0 = (a, b, o0) and f1 = (b, a, o1) in their own
    winding (edges whose two faces run the same way along them, or with 3+ faces, are left out)."""
    he = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    opp = np.concatenate([T[:, 2], T[:, 0], T[:, 1]])
    fid = np.tile(np.arange(len(T)), 3)
    key = np.sort(he, 1)
    order = np.lexsort((key[:, 1], key[:, 0]))
    k = key[order]
    new = np.r_[True, (k[1:] != k[:-1]).any(1)]
    start = np.flatnonzero(new)
    count = np.diff(np.r_[start, len(k)])
    two = start[count == 2]
    i, j = order[two], order[two + 1]
    ok = (he[i, 0] == he[j, 1]) & (he[i, 1] == he[j, 0])  # opposite directions: consistently wound
    i, j = i[ok], j[ok]
    return he[i, 0], he[i, 1], opp[i], opp[j], fid[i], fid[j], {tuple(e) for e in k[start].tolist()}


def flip_to_fit(V: np.ndarray, T: np.ndarray, nearest, tol: float = 5e-4, sharp: float = SHARP, gain: float = GAIN,
                fit: float = FIT, rounds: int = ROUNDS) -> tuple[np.ndarray, int]:
    """Triangles T (n, 3) of vertices V with badly lying edges turned; (new T, the number of flips).
    nearest(points (m, 3)) -> (the reference surface's unit normals at the nearest points (m, 3), distances (m,))."""
    V = np.asarray(V, np.float64)
    T = np.array(T, np.int64)
    flips = 0
    for _ in range(rounds):
        if not len(T):
            break
        a, b, o0, o1, f0, f1, edges = _pairs(T)
        n0, ar0 = _normals(V[a], V[b], V[o0])
        n1, ar1 = _normals(V[b], V[a], V[o1])
        dot = (n0 * n1).sum(1)
        cand = np.flatnonzero((dot < sharp) & (ar0 > 1e-14) & (ar1 > 1e-14))
        if not len(cand):
            break
        a, b, o0, o1, f0, f1, dot = a[cand], b[cand], o0[cand], o1[cand], f0[cand], f1[cand], dot[cand]
        # the four triangles per edge: as they are (a, b, o0), (b, a, o1); turned (a, o1, o0), (o1, b, o0)
        tris = np.stack([np.stack([a, b, o0], 1), np.stack([b, a, o1], 1),
                         np.stack([a, o1, o0], 1), np.stack([o1, b, o0], 1)], 1)  # (m, 4, 3)
        C = V[tris]  # (m, 4, 3, 3)
        X = np.einsum("sw,mtwd->mtsd", _W, C)  # (m, 4, 7, 3)
        rn, rd = nearest(X.reshape(-1, 3))
        rn, rd = np.asarray(rn, np.float64).reshape(len(cand), 4, 7, 3), np.asarray(rd, np.float64).reshape(len(cand), 4, 7)
        tn, tar = _normals(C[:, :, 0], C[:, :, 1], C[:, :, 2])  # (m, 4, 3)
        agree = (rn * tn[:, :, None, :]).sum(-1).min(-1)  # (m, 4): each triangle's worst agreement
        off = rd.max(-1)
        now, turned = agree[:, :2].min(1), agree[:, 2:].min(1)
        ndot = (tn[:, 2] * tn[:, 3]).sum(1)
        exists = np.array([(min(p, q), max(p, q)) in edges for p, q in zip(o0.tolist(), o1.tolist())], bool)
        good = ((turned >= now + gain) & (turned >= fit) & (ndot >= dot) & (tar[:, 2] > 1e-14) & (tar[:, 3] > 1e-14)
                & (off[:, 2:].max(1) <= off[:, :2].max(1) + tol) & ~exists & (o0 != o1))
        if not good.any():
            break
        used = np.zeros(len(T), bool)
        done = 0
        for i in np.flatnonzero(good)[np.argsort(-(turned - now)[good], kind="stable")]:
            if used[f0[i]] or used[f1[i]]:
                continue
            used[f0[i]] = used[f1[i]] = True
            T[f0[i]] = tris[i, 2]
            T[f1[i]] = tris[i, 3]
            done += 1
        flips += done
        if not done:
            break
    return T, flips


def sharp_misfits(V: np.ndarray, T: np.ndarray, nearest, sharp: float = SHARP, fit: float = FIT) -> np.ndarray:
    """Midpoints of the sharp interior edges one of whose triangles disagrees with the reference surface (worst
    agreement under `fit`): what `flip_to_fit` is there to remove; for tests and reports."""
    V = np.asarray(V, np.float64)
    T = np.asarray(T, np.int64)
    a, b, o0, o1, _, _, _ = _pairs(T)
    n0, _ = _normals(V[a], V[b], V[o0])
    n1, _ = _normals(V[b], V[a], V[o1])
    c = np.flatnonzero((n0 * n1).sum(1) < sharp)
    if not len(c):
        return np.zeros((0, 3))
    tris = np.stack([np.stack([a[c], b[c], o0[c]], 1), np.stack([b[c], a[c], o1[c]], 1)], 1)
    C = V[tris]
    X = np.einsum("sw,mtwd->mtsd", _W, C)
    rn, _ = nearest(X.reshape(-1, 3))
    tn, _ = _normals(C[:, :, 0], C[:, :, 1], C[:, :, 2])
    agree = (np.asarray(rn, np.float64).reshape(len(c), 2, 7, 3) * tn[:, :, None, :]).sum(-1).min(-1).min(-1)
    return ((V[a[c]] + V[b[c]]) / 2)[agree < fit]


def mesh_nearest(RV: np.ndarray, RT: np.ndarray):
    """A `nearest` for a triangle mesh by scipy (outside Blender): nearest face centre's normal and distance."""
    from scipy.spatial import cKDTree
    RV = np.asarray(RV, np.float64)
    n, _ = _normals(RV[RT[:, 0]], RV[RT[:, 1]], RV[RT[:, 2]])
    tree = cKDTree(RV[RT].mean(1))

    def nearest(X):
        d, j = tree.query(X)
        return n[j], d
    return nearest
