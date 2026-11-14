"""Smooth chains (N2h of docs/proposals/step5_rewrite.md): slack is taken as a smooth arch or ripple, never a zigzag,
with every link at its cut. Synthetic, nothing held: a rigid frame is a stiff (interfaced) piece."""
import numpy as np

from hifipushie import chain_solve as cs
from hifipushie import chain_solve_terms as terms
from hifipushie.chain_net import Network
from test_chain_solve import grid, pattern


def _turns(X, ids):
    """Signed turns (degrees) along the polyline X[ids], signed by the binormal's side of the polyline's mean one."""
    P = X[ids]
    d1, d2 = P[1:-1] - P[:-2], P[2:] - P[1:-1]
    cr = np.cross(d1, d2)
    ang = np.degrees(np.arctan2(np.linalg.norm(cr, axis=1), (d1 * d2).sum(1)))
    ref = cr.sum(0)
    return ang * np.sign(cr @ ref)


def _links_pct(net, X):
    a, b = net.chain_v[:, 0], net.chain_v[:, 1]
    return np.abs(np.linalg.norm(X[b] - X[a], axis=1) / net.chain_L - 1) * 100


def _zig(n, amp=0.001):
    return amp * (-1.0) ** np.arange(n)


def test_a_long_chain_between_two_points_of_a_rigid_frame_is_one_smooth_arch():
    fuv, fF = grid(26, 3, 0.25, 0.02)  # (the frame: 250 mm, interfaced: rigid)
    suv, sF = grid(31, 2, 0.30, 0.01)  # (the chain: 300 mm, 20 % longer than the room between its ends)
    M, off = pattern([("frame", fuv, fF), ("strip", suv, sF)],
                     sew=[(1, 78), (2, 79), (76, 78 + 60), (77, 78 + 61)])
    stiff = np.r_[np.ones(len(fuv)), np.zeros(len(suv))]
    net = Network(M, stiff, np.r_[np.full(len(fuv), 20.0), np.ones(len(suv))])
    X0 = np.zeros((net.n, 3))
    X0[:78, :2] = fuv
    X0[78:, 0] = suv[:, 0] * 0.25 / 0.30
    X0[78:, 1] = suv[:, 1] + 0.01
    X0[78:, 2] = np.repeat(_zig(31), 2)  # (seeded as a zigzag: the worst start)
    X, rep = cs.solve(net, X0)
    for j in (0, 1):
        t = _turns(X, 78 + 2 * np.arange(31) + j)
        assert (np.sign(t[np.abs(t) > 0.5]) > 0).all() or (np.sign(t[np.abs(t) > 0.5]) < 0).all(), t.round(1)
        assert np.abs(t).max() < 15.0, t.round(1)
    assert _links_pct(net, X).max() < 0.1
    assert rep["chains"]["zigzags"] == 0
    assert all(rep["final_converged"])


def test_ease_is_a_smooth_ripple_never_a_zigzag():
    auv, aF = grid(31, 2, 0.30, 0.01)  # (300 mm eased onto 280 mm)
    buv, bF = grid(29, 2, 0.28, 0.01)
    na = len(auv)
    ib = [0, 5, 10, 15, 20, 25, 28]
    sew = [(2 * int(round(i * 30 / 28)), na + 2 * i + 1) for i in ib]
    M, _ = pattern([("a", auv, aF), ("b", buv, bF)], sew=sew)
    net = Network(M, np.zeros(len(auv) + len(buv)), np.ones(len(auv) + len(buv)))
    X0 = np.zeros((net.n, 3))
    X0[:na, 0] = auv[:, 0] * 0.28 / 0.30
    X0[:na, 1] = -auv[:, 1]
    X0[:na, 2] = np.repeat(_zig(31), 2)
    X0[na:, 0] = buv[:, 0]
    X0[na:, 1] = buv[:, 1] - 0.01
    X, rep = cs.solve(net, X0)
    assert _links_pct(net, X).max() < 2.0
    assert rep["chains"]["zigzags"] == 0, rep["chains"]
    t = _turns(X, 2 * np.arange(31))
    flips = int((np.diff(np.sign(t[np.abs(t) > 1.0])) != 0).sum())
    assert flips <= 2 * len(ib), t.round(1)  # (at most an inflection either side of each bump)
    assert all(rep["final_converged"])


def test_smoothness_counts_a_zigzag_and_not_an_arch():
    uv, F = grid(21, 2, 0.2, 0.01)
    M, _ = pattern([("s", uv, F)])
    net = Network(M)
    X = np.c_[uv, np.zeros(len(uv))]
    arch = X.copy()
    arch[:, 2] = 0.03 * np.sin(np.pi * uv[:, 0] / 0.2)
    zig = X.copy()
    zig[:, 2] = np.repeat(_zig(21, 0.002), 2)
    assert terms.smoothness(net, arch)["zigzags"] == 0
    assert terms.smoothness(net, zig)["zigzags"] >= 30
