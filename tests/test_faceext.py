"""faceext: the MakeHuman model extensions (face_ext.npz): local, the probable identity part left to the identity, no
fold at +-1."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hifipushie import assets, base, faceext, faceslide, gnmloops  # noqa: E402


def _ok():
    try:
        assets.path("gnm", base.GNM)
        return bool(faceext.table())
    except Exception:
        return False


def test_probable_identity_part_removed():
    """(Up to the mirror symmetrising after the projection: GNM's template is symmetric to ~0.1 mm.) Each extension
    has no component along the identity's cheap directions over its region (what a few sigmas of
    identity make: that part is the identity's, the extension is the rest)."""
    if not _ok():
        return
    for k in faceext.EXT:
        if k not in faceext.table():
            continue
        d = np.asarray(faceext.table()[k], float)[:gnmloops.N_RAW]
        m = np.linalg.norm(d, axis=1)
        V, S, rows = faceext.cheap_basis(m > faceext.REGION * m.max())
        y = d[rows].ravel()
        # (the nose's: 0.2. The windowed projection (faces4: faceext.WINDOW, smooth edges instead of a step where a
        # hard region mask ended) and the lid-rim hold leave up to 0.17 of the field along the cheap directions (the
        # curve, nostrils_width). The joint prior of the coherent model (gnm_atlas.md, faces4 design) carries that correlation instead)
        tol = 0.1 if faceext.EXT[k][0] == "mouth" else 0.2
        assert np.linalg.norm(V @ y) < tol * np.linalg.norm(y), (k, np.linalg.norm(V @ y) / np.linalg.norm(y))


def test_extensions_fold_nothing():
    """Each extension at -1 / +1 on GNM's template: no skin quad turns over."""
    if not _ok():
        return
    T = faceslide.template()
    Q = gnmloops.plan()["quads"]
    Q = Q[T["skin"][Q].all(1)]
    X0 = T["X"]

    def nrm(X):
        n = np.cross(X[Q[:, 2]] - X[Q[:, 0]], X[Q[:, 3]] - X[Q[:, 1]])
        return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-18)
    n0 = nrm(X0)
    area = 0.5 * np.linalg.norm(np.cross(X0[Q[:, 2]] - X0[Q[:, 0]], X0[Q[:, 3]] - X0[Q[:, 1]]), axis=1)
    big = area > 1.5e-7
    for k in faceext.EXT:
        if k not in faceext.table():
            continue
        for v in (-1.0, 1.0):
            X1 = X0 + faceslide.delta({k: v})
            turned = int(((np.einsum("ij,ij->i", n0, nrm(X1)) < 0) & big).sum())
            assert turned == 0, (k, v, turned)


def test_extensions_are_local_and_symmetric():
    if not _ok():
        return
    mi = faceslide.template()["mirror"]
    for k in faceext.EXT:
        if k not in faceext.table():
            continue
        d = np.asarray(faceext.table()[k], float)
        assert np.abs(d - d[mi] * [-1.0, 1.0, 1.0]).max() < 1e-6, k
        # (12% of the template: the windowed projection (faces4) eases each field out over 12 mm; MakeHuman's hump
        # moves the whole upper nose and radix: 10.1%)
        assert (np.linalg.norm(d, axis=1) > 2e-4).sum() < 0.12 * len(d), k


def test_mouth_extensions_reach_a_millimetre():
    """faces3: with the lips' inner rolls held and the creases moved rigidly (faceext.hold_creases) the carried mouth
    targets stay fold-free to ~1 mm and more (before: 0.38-0.62 mm, folded in the inner roll near the corners)."""
    if not _ok():
        return
    for k, v in faceext.EXT.items():
        if v[0] == "mouth" and k in faceext.table():
            assert np.linalg.norm(faceext.table()[k], axis=1).max() > 0.9e-3, k


def test_crease_hold_keeps_rigid_motions():
    """A rigid motion (a shift and a small turn) keeps every crease already: hold_creases leaves it as it is."""
    if not _ok():
        return
    X = faceslide.template()["X"]
    w = np.array([0.01, -0.02, 0.015])
    d = np.array([3e-4, -1e-4, 2e-4]) + np.cross(w, X - X.mean(0))
    assert np.abs(faceext.hold_creases(d) - d).max() < 1e-9


def test_extensions_bend_the_visible_skin_smoothly():
    """faces4: the curvature change each extension makes on the visible exterior skin at +1 (|n . L d| / edge^2, the
    mesh Laplacian over GNM's quads) stays smooth: its 99th percentile under 30 /m. The nose fields projected under a
    HARD region mask put a step where the mask ended (the dorsum line at curve +1, a notch at the nasion at greek -1:
    p99 21-70 /m, max up to 220); the windowed projection (faceext.WINDOW) took them to 3-26."""
    if not _ok():
        return
    import scipy.sparse as sp
    T = faceslide.template()
    X, n = T["X"], T["n"]
    Q = gnmloops.plan()["quads"]
    e = np.r_[Q[:, [0, 1]], Q[:, [1, 2]], Q[:, [2, 3]], Q[:, [3, 0]]]
    A = sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), (len(X), len(X))).tocsr()
    A = ((A + A.T) > 0).astype(float)
    deg = np.maximum(np.asarray(A.sum(1)).ravel(), 1)
    L = sp.diags(1 / deg) @ A - sp.eye(len(X))
    r, c = A.nonzero()
    l2 = np.zeros(len(X))
    np.add.at(l2, r, ((X[r] - X[c]) ** 2).sum(1))
    l2 /= deg
    R = faceslide._lip_rings()
    inner = np.zeros(len(X), bool)
    for rr in R["rings"][:R["contact"] + 1]:
        inner[rr] = True
    vis = (n[:, 2] > 0.2) & ~inner & T["ext"]
    for k in faceext.EXT:
        if k not in faceext.table():
            continue
        d = np.asarray(faceext.table()[k], float)
        kap = np.abs(np.einsum("ij,ij->i", L @ d, n))[vis] / np.maximum(l2[vis], 1e-12)
        assert np.percentile(kap, 99) < 30.0, (k, np.percentile(kap, 99))
