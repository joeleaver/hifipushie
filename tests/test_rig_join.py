"""A limb's seam (rig_join): an arm hanging beside the body, its mesh joined to the body's only at the top (the
shoulder). The arm's weight blends across that seam and nowhere else: its inner face, a cell's gap from the side
but not joined to it, stays wholly the arm's; the side stays wholly the body's. Light: numpy + scipy only.
uv run python tests/test_rig_join.py"""
import sys

import numpy as np
from scipy.sparse import coo_matrix

from hifipushie import rig_join

STEP = 0.0025
JOIN_Z = 0.18  # the strip is joined to the plate only above this (the shoulder)
BAND = 0.05


def hanging_arm():
    """A flat grid: the body plate (x <= 0) and the arm strip (x > 0) beside it, with no faces across the gap
    between the two columns either side of x = 0 below JOIN_Z."""
    xs = np.arange(-0.1, 0.035 + 1e-9, STEP)
    zs = np.arange(0.0, 0.2 + 1e-9, STEP)
    X, Z = np.meshgrid(xs, zs, indexing="ij")
    V = np.c_[X.ravel(), np.zeros(X.size), Z.ravel()]
    idx = np.arange(X.size).reshape(X.shape)
    gap = int(np.argmin(np.abs(xs)))  # the cells between column gap (x = 0) and gap + 1 (x = STEP)
    F = []
    for i in range(len(xs) - 1):
        for j in range(len(zs) - 1):
            if i == gap and zs[j] < JOIN_Z:
                continue
            a, b, c, d = idx[i, j], idx[i + 1, j], idx[i + 1, j + 1], idx[i, j + 1]
            F += [(a, b, c), (a, c, d)]
    F = np.array(F)
    e = rig_join._edges(F)
    ln = np.linalg.norm(V[e[:, 0]] - V[e[:, 1]], axis=1)
    n = len(V)
    G = coo_matrix((np.r_[ln, ln], (np.r_[e[:, 0], e[:, 1]], np.r_[e[:, 1], e[:, 0]])), shape=(n, n)).tocsr()
    return V, e, G, V[:, 0] > STEP / 2


def test_share_blends_across_the_seam_only():
    V, e, G, limb = hanging_arm()
    g = rig_join.join_share(G, e, limb, BAND)
    x, z = V[:, 0], V[:, 2]
    inner = limb & (np.abs(x - STEP) < 1e-9) & (z < JOIN_Z - BAND)  # the arm's face beside the side, unjoined
    side = ~limb & (np.abs(x) < 1e-9) & (z < JOIN_Z - BAND)
    assert inner.sum() > 10 and np.all(g[inner] == 1.0), g[inner].min()
    assert side.sum() > 10 and np.all(g[side] == 0.0), g[side].max()
    seam = (np.abs(x) < 1e-9) & (z >= JOIN_Z + STEP) | (np.abs(x - STEP) < 1e-9) & (z >= JOIN_Z + STEP)
    assert np.all((g[seam] > 0.0) & (g[seam] < 1.0))  # the joined skin is shared
    # across the joined top: rising from the body into the arm, the body's side held (most of the band on the arm's)
    row = np.flatnonzero(np.abs(z - 0.195) < 1e-9)
    row = row[np.argsort(x[row])]
    assert np.all(np.diff(g[row]) >= -1e-12)
    assert np.all(g[row][x[row] < -(1 - rig_join.JOIN_SPLIT_L) * BAND - 1e-9] == 0.0)
    assert g[row][x[row] < 0].max() <= rig_join.JOIN_SPLIT + 1e-9


def test_no_seam_no_share():
    V, e, G, limb = hanging_arm()
    keep = (V[:, 2] < JOIN_Z - STEP)  # cut the top off: arm and body share no edge
    ee = e[keep[e[:, 0]] & keep[e[:, 1]]]
    assert rig_join.join_share(G, ee, limb, BAND) is None


def test_reblend_keeps_rows_and_each_sides_mix():
    rng = np.random.default_rng(1)
    D = rng.uniform(0, 1, (50, 4))  # bones: 0 spine, 1 shoulder (the limb's parent), 2 arm (root), 3 forearm
    D[:5, 2:] = 0  # body skin with no arm weight: the arm side borrows the root
    D[5:10, :2] = 0  # arm skin with no body weight: the body side borrows the parent
    D /= D.sum(1, keepdims=True)
    cols = np.array([False, False, True, True])
    g = rng.uniform(0, 1, 50)
    N = rig_join.reblend(D, g, cols, root=2, parent=1)
    assert np.allclose(N.sum(1), 1.0)
    assert np.allclose(N[:, cols].sum(1), g)
    assert np.allclose(N[:5, 3], 0) and np.allclose(N[:5, 2], g[:5])
    assert np.allclose(N[5:10, 0], 0) and np.allclose(N[5:10, 1], 1 - g[5:10])
    mix = D[10:, 2] / D[10:, 2:].sum(1)  # the arm's own split between arm and forearm is kept
    assert np.allclose(N[10:, 2] / N[10:, 2:].sum(1), mix)
    assert np.allclose(rig_join.reblend(D, (D[:, cols]).sum(1), cols, 2, 1), D)  # its own share: unchanged


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
    sys.exit(0)
