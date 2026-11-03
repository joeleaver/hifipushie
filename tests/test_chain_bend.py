"""F8: the sew's solver (chain_bend): rigid first (zero stretch), bend with lengths held, stall stops."""
import numpy as np

from hifipushie import chain_bend as cb


def _sheet(nx, ny, h, origin=(0, 0, 0)):
    """A flat grid sheet in the XZ plane: points, links (i, j, L) with diagonals, all 'at most' (mesh edges)."""
    xs, zs = np.meshgrid(np.arange(nx) * h, np.arange(ny) * h, indexing="ij")
    P = np.c_[xs.ravel(), np.zeros(xs.size), zs.ravel()] + np.asarray(origin, float)
    idx = np.arange(nx * ny).reshape(nx, ny)
    E = [(idx[a, c], idx[a + 1, c]) for a in range(nx - 1) for c in range(ny)]
    E += [(idx[a, c], idx[a, c + 1]) for a in range(nx) for c in range(ny - 1)]
    E += [(idx[a, c], idx[a + 1, c + 1]) for a in range(nx - 1) for c in range(ny - 1)]
    E = np.asarray(E)
    return P, E, idx


def _links(P, E):
    return E[:, 0], E[:, 1], np.linalg.norm(P[E[:, 1]] - P[E[:, 0]], axis=1)


def _stretch(X, i, j, L):
    return float(((np.linalg.norm(X[j] - X[i], axis=1) / L - 1) * 100).max())


def test_colours_batches_share_no_point():
    P, E, _ = _sheet(6, 5, 0.01)
    C = cb.colours(E[:, 0], E[:, 1], len(P))
    assert sum(len(c) for c in C) == len(E)
    for c in C:
        assert len(np.unique(E[c].ravel())) == 2 * len(c)
    assert len(C) <= 8


def test_rigid_closes_an_open_seam_with_zero_stretch():
    A, EA, ia = _sheet(5, 5, 0.02)
    B, EB, ib = _sheet(5, 5, 0.02, origin=(0.3, 0.1, 0.05))  # (apart, offset)
    R = cb._rot(np.array([0.0, 0.0, 0.6]))  # (and turned)
    B = (B - B.mean(0)) @ R.T + B.mean(0)
    X = np.r_[A, B]
    E = np.r_[EA, EB + len(A)]
    i, j, L = _links(X, E)
    S = np.zeros((5, 2), np.int64)
    S[:, 1] = ib[0, :] + len(A)
    S[:, 0] = ia[-1, :]
    held = np.zeros(len(X), bool)
    held[:len(A)] = True  # (A as built: B comes to it)
    g0 = np.linalg.norm(X[S[:, 0]] - X[S[:, 1]], axis=1).max()
    Y, rd = cb.rigid(X, [np.arange(len(A)), np.arange(len(A), len(X))], S, None, held)
    g1 = np.linalg.norm(Y[S[:, 0]] - Y[S[:, 1]], axis=1).max()
    assert g0 > 0.2 and g1 < 1e-4, (g0, g1, rd)
    assert abs(_stretch(Y, i, j, L)) < 1e-8 and np.allclose(Y[:len(A)], X[:len(A)])


def test_bend_closes_a_tube_with_lengths_held():
    """A flat sheet whose two side edges are sewn: no rigid motion closes it, bending alone does."""
    P, E, idx = _sheet(16, 4, 0.02)
    i, j, L = _links(P, E)
    S = np.c_[idx[0, :], idx[-1, :]]
    X, rd = cb.bend(P + np.random.default_rng(1).normal(0, 1e-4, P.shape) * [0, 1, 0], i, j, L,
                    np.zeros(len(L), bool), S, passes=2000)
    assert rd["why"] == "closed", rd
    assert rd["worst_pct"] <= cb.HOLD_PCT + 1e-9, rd
    assert _stretch(X, i, j, L) <= cb.HOLD_PCT


def test_bend_stops_at_a_stall():
    """Two held sheets a metre apart: their seam can't close; the bend stops on the stall, not at the pass cap."""
    A, EA, ia = _sheet(4, 4, 0.02)
    B, EB, ib = _sheet(4, 4, 0.02, origin=(1.0, 0, 0))
    X = np.r_[A, B]
    E = np.r_[EA, EB + len(A)]
    i, j, L = _links(X, E)
    held = np.zeros(len(X), bool)
    held[ia[0, :]] = True
    held[ib[-1, :] + len(A)] = True
    S = np.c_[ia[-1, :], ib[0, :] + len(A)]
    Y, rd = cb.bend(X, i, j, L, np.zeros(len(L), bool), S, held, passes=5000)
    assert rd["why"] == "stalled" and rd["passes"] < 1000, rd
    assert rd["max_gap_mm"] > 900
    assert _stretch(Y, i, j, L) <= cb.HOLD_PCT
