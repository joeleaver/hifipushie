"""Flattening a cut piece with least distortion (R1 / R2 spikes, C489-C490): LSCM for a start, then ARAP (as rigid as
possible: every triangle's shape kept, the stretch spread); the flat turned so the body's up (z) runs up the piece (the
grain). strain per face = max(stretch s1 - 1, compression 1 - s2): where a dart (compression) or ease (stretch) is
needed, the draper's reading. Metres."""
import numpy as np
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.linalg import factorized, spsolve

from .mark_split import areas


def lscm(V, F):
    n = len(V)
    e1 = V[F[:, 1]] - V[F[:, 0]]
    e2 = V[F[:, 2]] - V[F[:, 0]]
    x1 = np.linalg.norm(e1, axis=1)
    ex = e1 / x1[:, None]
    nn = np.cross(e1, e2)
    ar2 = np.linalg.norm(nn, axis=1)
    ey = np.cross(nn / ar2[:, None], ex)
    p = np.zeros((len(F), 3, 2))
    p[:, 1, 0] = x1
    p[:, 2, 0] = np.einsum("ij,ij->i", e2, ex)
    p[:, 2, 1] = np.einsum("ij,ij->i", e2, ey)
    s = 1 / np.sqrt(ar2)
    rows, cols, vals = [], [], []
    for j in range(3):
        a, b = (j + 1) % 3, (j + 2) % 3
        Wr = (p[:, b, 0] - p[:, a, 0]) * s
        Wi = (p[:, b, 1] - p[:, a, 1]) * s
        r = np.arange(len(F))
        rows += [2 * r, 2 * r, 2 * r + 1, 2 * r + 1]
        cols += [F[:, j], n + F[:, j], F[:, j], n + F[:, j]]
        vals += [Wr, -Wi, Wi, Wr]
    M = csr_matrix(coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(2 * len(F), 2 * n)))
    i1 = int(np.argmax(np.linalg.norm(V - V[0], axis=1)))
    i0 = int(np.argmax(np.linalg.norm(V - V[i1], axis=1)))
    d = np.linalg.norm(V[i1] - V[i0])
    fixed = np.array([i0, i1, n + i0, n + i1])
    fv = np.array([0.0, d, 0.0, 0.0])
    free = np.setdiff1d(np.arange(2 * n), fixed)
    Mf, Mp = M[:, free], M[:, fixed]
    x = spsolve((Mf.T @ Mf).tocsc(), -(Mf.T @ (Mp @ fv)))
    U = np.zeros(2 * n)
    U[free] = x
    U[fixed] = fv
    return np.c_[U[:n], U[n:]], p


def arap(V, F, U, p, iters=60):
    n = len(V)
    rows, cols, vals = [], [], []
    W = np.zeros((len(F), 3))
    for k in range(3):
        i, j = (k + 1) % 3, (k + 2) % 3
        a = p[:, i] - p[:, k]
        b = p[:, j] - p[:, k]
        cot = np.einsum("ij,ij->i", a, b) / np.maximum(np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]), 1e-12)
        W[:, k] = 0.5 * cot
        I, J = F[:, i], F[:, j]
        rows += [I, J, I, J]
        cols += [I, J, J, I]
        vals += [W[:, k], W[:, k], -W[:, k], -W[:, k]]
    Lm = coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n)).tolil()
    Lm[0, 0] += 1e3
    solve = factorized(Lm.tocsc())
    X = p
    for _ in range(iters):
        Ju = np.stack([U[F[:, 1]] - U[F[:, 0]], U[F[:, 2]] - U[F[:, 0]]], 2)
        Jx = np.stack([X[:, 1] - X[:, 0], X[:, 2] - X[:, 0]], 2)
        Us, S, Vt_ = np.linalg.svd(Ju @ np.linalg.inv(Jx))
        R = Us @ Vt_
        neg = np.linalg.det(R) < 0
        Us[neg, :, 1] *= -1
        R = Us @ Vt_
        b = np.zeros((n, 2))
        for k in range(3):
            i, j = (k + 1) % 3, (k + 2) % 3
            e = np.einsum("fab,fb->fa", R, X[:, i] - X[:, j]) * W[:, k, None]
            np.add.at(b, F[:, i], e)
            np.add.at(b, F[:, j], -e)
        b[0] += 1e3 * U[0]
        U = np.c_[solve(b[:, 0]), solve(b[:, 1])]
    Ju = np.stack([U[F[:, 1]] - U[F[:, 0]], U[F[:, 2]] - U[F[:, 0]]], 2)
    Jx = np.stack([X[:, 1] - X[:, 0], X[:, 2] - X[:, 0]], 2)
    S = np.linalg.svd(Ju @ np.linalg.inv(Jx), compute_uv=False)
    return U, S


def grain_up(U, Vp):
    """Rotate the flat so the 3D upward direction (z) runs up the flat's y (the grain: vertical on the body)."""
    g = np.linalg.lstsq(np.c_[U, np.ones(len(U))], Vp[:, 2], rcond=None)[0][:2]
    a = np.arctan2(g[0], g[1])
    c, s = np.cos(a), np.sin(a)
    U2 = U @ np.array([[c, -s], [s, c]]).T
    return U2 - U2.min(0)


def rest_shape(V, F, p, t, e):
    """The faces' local shapes p stretched by (1 + e) along the 3D direction t (each face's own): cloth whose rest
    length there is longer than the toile's (an eased cap, cut_ease.py)."""
    ex = V[F[:, 1]] - V[F[:, 0]]
    ex /= np.linalg.norm(ex, axis=1, keepdims=True)
    nn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    ey = np.cross(nn / np.linalg.norm(nn, axis=1, keepdims=True), ex)
    t2 = np.c_[np.einsum("ij,ij->i", t, ex), np.einsum("ij,ij->i", t, ey)]
    t2 /= np.linalg.norm(t2, axis=1, keepdims=True) + 1e-12
    return p + e[:, None, None] * np.einsum("fkd,fd->fk", p, t2)[:, :, None] * t2[:, None, :]


def rest_edges(p, t2, ev, F):
    """The faces' local shapes p with each EDGE's component along t2 (per face, local) stretched by (1 + e) at its
    middle (ev per vertex): a stretch varying across a face (a shaped collar's rows, cut_shape.py) laid exactly on
    the edges along it; each triangle rebuilt from its three lengths."""
    def ln(a, b):
        v = p[:, b] - p[:, a]
        along = np.einsum("fd,fd->f", v, t2)
        return np.linalg.norm(v + ((ev[F[:, a]] + ev[F[:, b]]) / 2 * along)[:, None] * t2, axis=1)
    l01, l02, l12 = ln(0, 1), ln(0, 2), ln(1, 2)
    x = (l01 ** 2 + l02 ** 2 - l12 ** 2) / (2 * l01)
    q = np.zeros_like(p)
    q[:, 1, 0] = l01
    q[:, 2, 0], q[:, 2, 1] = x, np.sqrt(np.maximum(l02 ** 2 - x ** 2, 1e-16))
    return q


def flatten(V, F, rest=None):
    """LSCM then ARAP; (U grain up (NaN at vertices no face uses), singular values s1 >= s2, the faces kept: the
    degenerate ones of a strip mesh dropped). rest(V, F) -> (t, e) per face: ARAP against a rest shape stretched by
    (1 + e) along t (rest_shape), the singular values then against it; e per VERTEX (len V): along each edge
    (rest_edges)."""
    F = F[areas(V, F) > 1e-10]
    used = np.unique(F)
    remap = -np.ones(len(V), int)
    remap[used] = np.arange(len(used))
    Vc, Fc = V[used], remap[F]
    U, p = lscm(Vc, Fc)
    if rest is not None:
        t, e = rest(Vc, Fc)
        if len(e) == len(Vc) != len(Fc):
            ex = Vc[Fc[:, 1]] - Vc[Fc[:, 0]]
            ex /= np.linalg.norm(ex, axis=1, keepdims=True)
            nn = np.cross(Vc[Fc[:, 1]] - Vc[Fc[:, 0]], Vc[Fc[:, 2]] - Vc[Fc[:, 0]])
            ey = np.cross(nn / np.linalg.norm(nn, axis=1, keepdims=True), ex)
            t2 = np.c_[np.einsum("ij,ij->i", t, ex), np.einsum("ij,ij->i", t, ey)]
            p = rest_edges(p, t2 / (np.linalg.norm(t2, axis=1, keepdims=True) + 1e-12), e, Fc)
        else:
            p = rest_shape(Vc, Fc, p, t, e)
    U, S = arap(Vc, Fc, U, p)
    Uf = np.full((len(V), 2), np.nan)
    Uf[used] = grain_up(U, Vc)
    return Uf, S, F


def strain(S):
    """max(stretch s1 - 1, compression 1 - s2) per face."""
    return np.maximum(S[:, 0] - 1, 1 - S[:, 1])


