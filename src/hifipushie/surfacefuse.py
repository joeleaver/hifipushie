"""One surface from several pictures' reads, the published way: Nehab, Rusinkiewicz, Davis, Ramamoorthi 2005,
"Efficiently combining positions and normals for precise 3D geometry". Positions are right in the large and
wrong in the small; normals are the other way round. So the big shape is KEPT from a mesh that is right in the
large, and everything finer than `scale` is taken from normals: here the reads (surfaceread.py) of ALL the views
at once. Each vertex listens to the views that see it, squarely before obliquely, so the side of a head is shaped
by the side picture, its face by the front picture, and the corner between them by both, in one smooth surface.
No view's depth is ever used: only which way it says the surface faces.

  refine(verts, faces, views, scale, iters)   the mesh's vertices moved along their normals
A view is {"normals" (h, w, 3): x right, y up, z to the viewer; "mask" (h, w): where the read counts; "U", "F": the
picture's right and the way to its viewer, on the creature's axes; "u0", "z0": the world place of the grid's corner
along U and its height; "px", "za": metres per pixel across and (px * za) down; "mirror": True for the other side's
picture of a middle part (the same read, left and right swapped)} (the grid twoskin_build._read makes).
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

VIS = 0.0015       # m: the cell of the visibility test
BEHIND = 0.004     # m: a vertex this far behind the first surface in its cell is hidden from that view
FACING = (0.15, 0.6)   # a view counts from this much facing (cosine), fully from that


def vertex_normals(V: np.ndarray, F: np.ndarray) -> np.ndarray:
    n = np.zeros(V.shape, np.float64)
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    for k in range(3):
        np.add.at(n, F[:, k], fn)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def edges(F: np.ndarray) -> np.ndarray:
    e = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    return np.unique(e, axis=0)


def _smooth(s):
    s = np.clip(s, 0.0, 1.0)
    return s * s * (3 - 2 * s)


def _seen(V: np.ndarray, N: np.ndarray, view: dict):
    """What a view says at each vertex: (its normal there on the creature's axes, how much it counts 0..1)."""
    flip = np.array([-1.0, 1.0, 1.0]) if view.get("mirror") else np.ones(3)
    P, Nn = V * flip, N * flip
    U, Fv = np.asarray(view["U"], float), np.asarray(view["F"], float)
    u, t = P @ U, P @ Fv
    facing = Nn @ Fv
    # hidden behind something nearer to this viewer?
    ci, ri = np.floor(u / VIS).astype(np.int64), np.floor(P[:, 2] / VIS).astype(np.int64)
    ci -= ci.min()
    ri -= ri.min()
    key = ri * (int(ci.max()) + 1) + ci
    front = np.full(int(key.max()) + 1, -np.inf)
    np.maximum.at(front, key, t)
    visible = t >= front[key] - BEHIND
    h, w = view["mask"].shape
    c = (u - view["u0"]) / view["px"] - 0.5
    r = (view["z0"] - P[:, 2]) / (view["px"] * view["za"]) - 0.5
    inside = (c >= 0) & (c <= w - 1) & (r >= 0) & (r <= h - 1)
    at = [np.clip(r, 0, h - 1), np.clip(c, 0, w - 1)]
    n = np.stack([ndimage.map_coordinates(view["normals"][..., k], at, order=1, mode="nearest") for k in range(3)], 1)
    m = ndimage.map_coordinates(view["mask"].astype(np.float32), at, order=1, mode="nearest")
    world = (n[:, :1] * U[None] + n[:, 1:2] * np.array([0.0, 0.0, 1.0])[None] + n[:, 2:3] * Fv[None]) * flip
    wgt = visible * inside * m * _smooth((facing - FACING[0]) / (FACING[1] - FACING[0])) * np.clip(facing, 0, 1)
    return world, wgt


def targets(V: np.ndarray, N: np.ndarray, views) -> tuple[np.ndarray, np.ndarray]:
    """Per vertex, the normal the pictures ask for (the views' reads, each by how squarely it sees the vertex) and
    how much any picture says about it (0..1): where none does, the mesh's own normal stands."""
    acc, tot = np.zeros(V.shape), np.zeros(len(V))
    for view in views:
        world, wgt = _seen(V, N, view)
        acc += world * wgt[:, None]
        tot += wgt
    say = np.clip(tot / 0.3, 0.0, 1.0)
    m = acc / np.maximum(tot, 1e-9)[:, None]
    m = m * say[:, None] + N * (1 - say)[:, None]
    return m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-12), say


def refine(V: np.ndarray, F: np.ndarray, views, scale: float = 0.01, iters: int = 3, hold: float = 3.0, log=None) -> np.ndarray:
    """The mesh's vertices moved along their normals so that the surface faces the way the pictures say, keeping
    the mesh's own shape for everything broader than about 6 x `scale` (a bump of wavelength 2 pi `scale` is shared
    evenly between the two). Linear least squares per round (the mesh's normals and what each view sees are taken
    afresh each round)."""
    import scipy.sparse as sp
    import scipy.sparse.linalg as spl
    V = np.asarray(V, np.float64).copy()
    E = edges(F)
    i, j = E[:, 0], E[:, 1]
    n = len(V)
    for it in range(iters):
        N = vertex_normals(V, F)
        M, say = targets(V, N, views)
        me = M[i] + M[j]
        me /= np.maximum(np.linalg.norm(me, axis=1, keepdims=True), 1e-12)
        e = V[j] - V[i]
        ln = np.maximum(np.linalg.norm(e, axis=1), 1e-9)
        # each edge should lie in the surface the pictures describe: m_e . (p_j + d_j n_j - p_i - d_i n_i) = 0
        aj, ai = (me * N[j]).sum(1) / ln, -(me * N[i]).sum(1) / ln
        rhs = -(me * e).sum(1) / ln
        k = len(E)
        A = sp.csr_matrix((np.r_[aj, ai], (np.r_[np.arange(k), np.arange(k)], np.r_[j, i])), shape=(k, n))
        H = (A.T @ A + sp.identity(n) * (hold / scale ** 2)).tocsr()
        b = A.T @ rhs
        pre = sp.diags(1.0 / H.diagonal())
        d, info = spl.cg(H, b, M=pre, rtol=1e-5, maxiter=400)
        d = np.clip(d, -scale, scale)
        V += d[:, None] * N
        if log:
            log(f"round {it + 1}: {int((say > 0.5).sum())} of {n} vertices seen; moved rms {1e3 * float(np.sqrt((d ** 2).mean())):.2f} mm, "
                f"most {1e3 * float(np.abs(d).max()):.1f} mm (cg {info})")
    return V


def eased(moved: np.ndarray, F: np.ndarray, rounds: int = 3) -> np.ndarray:
    """A per-vertex amount averaged with its neighbours' a few times: the grain two views leave where they disagree
    hair by hair goes, the shapes stay."""
    import scipy.sparse as sp
    E = edges(F)
    n = len(moved)
    A = sp.csr_matrix((np.ones(2 * len(E)), (np.r_[E[:, 0], E[:, 1]], np.r_[E[:, 1], E[:, 0]])), shape=(n, n))
    deg = np.maximum(np.asarray(A.sum(1)).ravel(), 1.0)
    m = np.asarray(moved, np.float64)
    for _ in range(rounds):
        m = 0.5 * m + 0.5 * (A @ m) / deg
    return m
