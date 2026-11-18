"""FLATTENING BY THE THREADS (R3g, C512; Joe 2026-11-17: "on a real jacket it's all one piece"). Woven cloth is a grid
of threads: it barely stretches ALONG a thread (warp, weft) but SHEARS freely, the grid skewing into diamonds with no
thread longer, until the threads jam. A flat piece laid on a curved surface is a Chebyshev net: the threads keep their
lengths and the angle between them changes. An isotropic flatten (LSCM + ARAP, flatten.arap) counts that shear as
strain: it can't tell a bias undercollar that takes the neck's curve by shear from one that has to be stretched.

THE GRAIN: each piece's warp runs at `grain` degrees in the flat (the block's convention: 90 = along the flat's y);
the flat's y is the piece's UP: the body's up (z, the straight grain of body pieces and sleeves) unless the caller
gives an `up` field (the collar: its CB column, neck -> outer edge; the undercollar is cut on the bias, 45 deg to it).

THE METHOD: ARAP's local / global iteration with a thread-preserving local step (as ARAP, a projective-dynamics fit;
the simplest correct change: the global step, the cotan Laplacian, is ARAP's own). Per face, D = the map flat -> toile
(the inverse of the flatten's Jacobian J); its warp and weft columns D e_w, D e_f are the threads as they lie on the
toile. The target keeps both threads' lengths (unit) and their angle where the shear is within the weave's limit
(free), clamping it at the limit beyond (a shear past the jam counts). The flat is then solved to that target (J ->
inverse of the target). The flat's orientation is the grain's: it is set from `up` before the fit and never turned
after (the energy is not rotation-free: the threads have a direction in the flat).

THE LIMIT: shear is free to SHEAR_LOCK_DEG (pattern_form, 35 deg: a woven's jamming angle, shirting / suiting
~30-40 deg, the picture-frame test's locking angle); read at call time.

MEASURES (threads()): per face warp, weft = the toile's thread length per flat length - 1 (+: the cloth stretched on
the toile; -: eased / shrunk), shear = the threads' angle off 90 deg (deg). thread_strain(): max(|warp|, |weft|), plus a
shear past the limit as the stretch it puts on the bias (half the angle past, radians). Metres."""
from __future__ import annotations

import numpy as np


SHEAR_WEAK = 0.02  # a weak pull of the shear toward square inside the limit, per round: free shear is a gauge (many
#                   nets fit), and with none the iteration wandered (the collar sheared near the jam all over, unevenly)


def lock_deg() -> float:
    from . import pattern_form
    return float(pattern_form.SHEAR_LOCK_DEG)


def axes(grain_deg: float):
    g = np.radians(grain_deg)
    return np.array([np.cos(g), np.sin(g)]), np.array([-np.sin(g), np.cos(g)])


def frames(V, F):
    """Each face's local orthonormal frame (ex, ey), as lscm's p coordinates."""
    e1 = V[F[:, 1]] - V[F[:, 0]]
    ex = e1 / np.linalg.norm(e1, axis=1, keepdims=True)
    nn = np.cross(e1, V[F[:, 2]] - V[F[:, 0]])
    ey = np.cross(nn / np.linalg.norm(nn, axis=1, keepdims=True), ex)
    return ex, ey


def jac(U, F, p):
    """J per face: local (p) coordinates -> flat."""
    Ju = np.stack([U[F[:, 1]] - U[F[:, 0]], U[F[:, 2]] - U[F[:, 0]]], 2)
    Jx = np.stack([p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]], 2)
    return Ju @ np.linalg.inv(Jx)


def orient(U, V, F, p, up=None):
    """U turned so the 3D `up` (per vertex; None: z) runs up the flat's y (area x |up| weighted)."""
    ex, ey = frames(V, F)
    u = np.tile([0.0, 0, 1], (len(F), 1)) if up is None else np.asarray(up, float)[F].mean(1)
    ul = np.c_[(u * ex).sum(1), (u * ey).sum(1)]
    d = np.einsum("fab,fb->fa", jac(U, F, p), ul)
    w = np.linalg.norm(ul, axis=1) * np.abs(p[:, 1, 0] * p[:, 2, 1] - p[:, 1, 1] * p[:, 2, 0]) / 2
    d = (d / (np.linalg.norm(d, axis=1, keepdims=True) + 1e-12) * w[:, None]).sum(0)
    a = np.arctan2(d[0], d[1])
    c, s = np.cos(a), np.sin(a)
    return U @ np.array([[c, -s], [s, c]]).T


def _wrap(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


def target(J, ew, ef, lim, weak=0.0):
    """The thread-preserving target per face (local -> flat): both threads unit, their angle kept within the limit."""
    D = np.linalg.inv(J)
    dw, df = D @ ew, D @ ef
    aw, af = np.arctan2(dw[:, 1], dw[:, 0]), np.arctan2(df[:, 1], df[:, 0])
    phi = _wrap(af - aw)
    phic = np.pi / 2 + np.clip((phi - np.pi / 2) * (1 - weak), -lim, lim)
    mid = aw + phi / 2
    a1, a2 = mid - phic / 2, mid + phic / 2
    C = np.stack([np.c_[np.cos(a1), np.cos(a2)], np.c_[np.sin(a1), np.sin(a2)]], 1)
    B = np.c_[ew, ef]
    return np.linalg.inv(C @ B.T)


def thread_arap(V, F, U, p, grain_deg, iters=120, lim_deg=None):
    """ARAP (flatten.arap's weights and global step) with the thread-preserving local step (module doc)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.linalg import factorized
    n = len(U)
    ew, ef = axes(grain_deg)
    lim = np.radians(lock_deg() if lim_deg is None else lim_deg)
    rows, cols, vals = [], [], []
    W = np.zeros((len(F), 3))
    for k in range(3):
        i, j = (k + 1) % 3, (k + 2) % 3
        a, b = p[:, i] - p[:, k], p[:, j] - p[:, k]
        W[:, k] = 0.5 * np.einsum("ij,ij->i", a, b) / np.maximum(np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]), 1e-12)
        I, J_ = F[:, i], F[:, j]
        rows += [I, J_, I, J_]
        cols += [I, J_, J_, I]
        vals += [W[:, k], W[:, k], -W[:, k], -W[:, k]]
    Lm = coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n)).tolil()
    Lm[0, 0] += 1e3
    solve = factorized(Lm.tocsc())
    for _ in range(iters):
        T = target(jac(U, F, p), ew, ef, lim, SHEAR_WEAK)
        b = np.zeros((n, 2))
        for k in range(3):
            i, j = (k + 1) % 3, (k + 2) % 3
            e = np.einsum("fab,fb->fa", T, p[:, i] - p[:, j]) * W[:, k, None]
            np.add.at(b, F[:, i], e)
            np.add.at(b, F[:, j], -e)
        b[0] += 1e3 * U[0]
        U = np.c_[solve(b[:, 0]), solve(b[:, 1])]
    return U


def threads(V, F, U, grain_deg, p=None):
    """(warp, weft, shear deg) per face (module doc); p: the faces' rest shapes (a shaped rest), else the toile's."""
    if p is None:
        ex, ey = frames(V, F)
        e1, e2 = V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]
        p = np.zeros((len(F), 3, 2))
        p[:, 1, 0] = np.linalg.norm(e1, axis=1)
        p[:, 2] = np.c_[(e2 * ex).sum(1), (e2 * ey).sum(1)]
    D = np.linalg.inv(jac(U, F, p))
    ew, ef = axes(grain_deg)
    dw, df = D @ ew, D @ ef
    lw, lf = np.linalg.norm(dw, axis=1), np.linalg.norm(df, axis=1)
    cs = (dw * df).sum(1) / (lw * lf)
    return lw - 1, lf - 1, np.degrees(np.arcsin(np.clip(cs, -1, 1)))


def thread_strain(warp, weft, shear, lim_deg=None):
    """max(|warp|, |weft|, the bias stretch of a shear past the limit) per face (module doc)."""
    lim = lock_deg() if lim_deg is None else lim_deg
    return np.maximum(np.maximum(np.abs(warp), np.abs(weft)), np.radians(np.maximum(np.abs(shear) - lim, 0)) / 2)


def report(warp, weft, shear, ar, lim_deg=None) -> dict:
    """A piece's thread numbers (area weighted where a mean)."""
    lim = lock_deg() if lim_deg is None else lim_deg
    t = thread_strain(warp, weft, shear, lim)
    m = lambda x: round(float((x * ar).sum() / ar.sum() * 100), 2)
    sh = np.abs(shear)
    return {"thread_mean_pct": m(t), "warp_mean_pct": m(np.abs(warp)), "weft_mean_pct": m(np.abs(weft)),
            "warp_range_pct": [round(float(warp.min()) * 100, 1), round(float(warp.max()) * 100, 1)],
            "weft_range_pct": [round(float(weft.min()) * 100, 1), round(float(weft.max()) * 100, 1)],
            "thread_over_2pct_area": round(float(ar[t > 0.02].sum() / ar.sum() * 100), 1),
            "shear_mean_deg": round(float((sh * ar).sum() / ar.sum()), 1),
            "shear_p95_deg": round(float(np.percentile(sh, 95)), 1), "shear_max_deg": round(float(sh.max()), 1),
            "shear_limit_deg": lim, "shear_over_area_pct": round(float(ar[sh > lim].sum() / ar.sum() * 100), 1)}


def numbers(V, F, U, S, grain_deg, ar, p=None) -> tuple:
    """(the strain map: thread strain per face, the piece's numbers): strain_mean_pct / area_over_2pct read by the
    threads (the shear within the limit free), iso_strain_mean_pct the isotropic reading of the same flat (ARAP's:
    max(s1 - 1, 1 - s2)), `threads` the warp / weft / shear split. A piece flattened isotropically (grain None) is read
    on the straight grain."""
    g = 90.0 if grain_deg is None else grain_deg
    w, f, sh = threads(V, F, U, g, p)
    t = thread_strain(w, f, sh)
    iso = np.maximum(S[:, 0] - 1, 1 - S[:, 1])
    return t, {"strain_mean_pct": round(float((t * ar).sum() / ar.sum() * 100), 2),
               "area_over_2pct": round(float(ar[t > 0.02].sum() / ar.sum() * 100), 1),
               "iso_strain_mean_pct": round(float((iso * ar).sum() / ar.sum() * 100), 2), "grain_deg": g,
               "threads": report(w, f, sh, ar)}
