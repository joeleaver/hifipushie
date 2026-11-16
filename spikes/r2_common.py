"""R2 (drape first) helpers: flattening (LSCM then ARAP, from R1's spike), strain, the piece check (a mark that does
not separate a piece is refused), strip meshes for the collar, the reference's jacket top line. Spike code."""
import numpy as np
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.linalg import factorized, spsolve

from r1_common import compact, face_components


class Refused(RuntimeError):
    """A mark that does not separate a piece: the cut is refused, never worked round (R1 mirrored the other side)."""


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


def boundary_edges(F):
    E = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    u, c = np.unique(E, axis=0, return_counts=True)
    return u[c == 1]


def areas(V, F):
    return 0.5 * np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1)


def one_piece(V, F, name, by, min_share=0.97):
    """The piece's faces must be ONE region: a second component over 3 % of the area means the marks `by` did not
    separate it (or cut it in two): refused with a message naming them. Returns the compacted piece."""
    F = F[areas(V, F) > 2e-9]
    if len(F) == 0:
        raise Refused(f"{name}: empty: the marks {by} leave no cloth for it")
    lab = face_components(F, len(V))
    ar = np.bincount(lab, weights=areas(V, F))
    big = ar.argmax()
    if ar[big] / ar.sum() < min_share:
        second = np.argsort(ar)[-2]
        at = V[F[lab == second]].mean((0, 1))
        raise Refused(f"{name}: the marks {by} do not separate it: {len(ar)} regions, the largest {ar[big] / ar.sum():.0%} "
                      f"of its area (shares {np.round(np.sort(ar)[::-1][:4] / ar.sum(), 3).tolist()}; the second at "
                      f"{np.round(at, 3).tolist()}); fix the mark, do not mirror or patch round it")
    return compact(V, F[lab == big])


def flatten(V, F):
    """LSCM then ARAP; (U grain up (NaN at vertices no face uses), singular values s1 >= s2, the faces kept: the
    degenerate ones of a strip mesh dropped)."""
    F = F[areas(V, F) > 1e-10]
    used = np.unique(F)
    remap = -np.ones(len(V), int)
    remap[used] = np.arange(len(used))
    Vc, Fc = V[used], remap[F]
    U, p = lscm(Vc, Fc)
    U, S = arap(Vc, Fc, U, p)
    Uf = np.full((len(V), 2), np.nan)
    Uf[used] = grain_up(U, Vc)
    return Uf, S, F


def strain(S):
    """max(stretch s1 - 1, compression 1 - s2) per face."""
    return np.maximum(S[:, 0] - 1, 1 - S[:, 1])


def grid_mesh(rows):
    """rows: (m) curves of n points each; quads between consecutive rows split into triangles. (V, F, index grid)"""
    R = np.stack(rows)
    m, n, _ = R.shape
    idx = np.arange(m * n).reshape(m, n)
    a, b, c, d = idx[:-1, :-1], idx[:-1, 1:], idx[1:, 1:], idx[1:, :-1]
    F = np.concatenate([np.stack([a, b, c], -1).reshape(-1, 3), np.stack([a, c, d], -1).reshape(-1, 3)])
    return R.reshape(-1, 3), F, idx


def ref_top(ref, us, dark=75, v0=300, v1=700):
    """The reference's jacket top line: the first dark pixel from v0 down at picture columns us (px)."""
    from PIL import Image
    im = np.asarray(Image.open(ref).convert("L"), float)
    out = []
    for u in us:
        k = np.where(im[v0:v1, int(round(u))] < dark)[0]
        out.append(v0 + k[0] if len(k) else np.nan)
    return np.array(out, float)
