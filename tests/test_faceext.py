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
        assert np.linalg.norm(V @ y) < 0.1 * np.linalg.norm(y), (k, np.linalg.norm(V @ y) / np.linalg.norm(y))


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
        assert (np.linalg.norm(d, axis=1) > 2e-4).sum() < 0.1 * len(d), k
