"""Step 5 as ROLLED PANELS (N2d: chain_seams, chain_panels, chain_assemble): synthetic, fast."""
import numpy as np

from hifipushie import chain_assemble as ca
from hifipushie.chain_lay_net import chain_network
from hifipushie.chain_net import Network
from hifipushie.chain_panels import NP, Panels
from hifipushie.chain_seams import join_seams

from test_chain_solve import grid, pattern

R = 0.06


def _net(M):
    net = Network(M)
    return chain_network(net)[0]


NX = 49


def _tube(short=0.0, ends_only=False):
    """Two half-tube rectangles (pi R wide, 0.2 tall) sewn along both long edges; b `short` m shorter (its seams)."""
    w = np.pi * R
    ua, Fa = grid(NX, 9, w, 0.2)
    ub, Fb = grid(NX, 9, w, 0.2 - short)
    M, off = pattern([("a", ua, Fa), ("b", ub, Fb)])
    js = [0, 8] if ends_only else range(9)
    e = (NX - 1) * 9
    sew = [(off[0] + j, off[1] + e + j) for j in js] + [(off[0] + e + j, off[1] + j) for j in js]
    M["sew"] = np.array(sew)
    return M


def _tube_start(c, noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    X = np.zeros((c.n, 3))
    for p in range(2):
        m = c.piece == p
        u, v = c.uv[m, 0], c.uv[m, 1]
        w = np.ptp(c.uv[c.piece == p, 0])
        th = np.pi * u / w + (np.pi if p else 0.0)
        X[m] = np.c_[R * np.cos(th), R * np.sin(th), v]
        X[m] += rng.normal(0, noise, 3)
    return X


def test_rolled_rectangle_is_isometric_for_any_numbers():
    u, F = grid(61, 31, 0.3, 0.15)
    M, _ = pattern([("a", u, F)])
    c = _net(M)
    pan = Panels(c)
    rng = np.random.default_rng(1)
    for _ in range(5):
        TH = rng.normal(0, 1, (pan.n, NP))
        TH[:, 7] = rng.uniform(-10, 10)
        X = pan.positions(TH)
        assert ca.links_pct(c, X)["max"] < 0.05  # (exact on the surface; a link is its chord: (k L)^2 / 24)


def test_two_panels_assemble_into_a_tube():
    c = _net(_tube())
    pan = Panels(c)
    TH0 = pan.fit_start(_tube_start(c, noise=0.01))
    keep = np.array([[[0, 0, -0.1], [0, 0, 0.3]]], float)
    TH, rd = ca.assemble(pan, TH0, keep)
    assert max(v[1] for v in rd["seam_gaps_mm"].values()) < 1.0, rd["seam_gaps_mm"]
    assert ca.links_pct(c, pan.positions(TH))["max"] < 0.05


def test_short_panel_leaves_its_gap_named_nothing_stretched():
    c = _net(_tube(short=0.03))
    pan = Panels(c)
    TH0 = pan.fit_start(_tube_start(c))
    keep = np.array([[[0, 0, -0.1], [0, 0, 0.3]]], float)
    TH, rd = ca.assemble(pan, TH0, keep)
    g = rd["seam_gaps_mm"]["a ~ b"]
    X = pan.positions(TH)
    d = np.linalg.norm(X[c.sew[:, 0]] - X[c.sew[:, 1]], axis=1) * 1e3
    z = c.uv[c.sew[:, 0], 1]
    ends = d[np.isclose(z, z.min())].mean() + d[np.isclose(z, z.max())].mean()
    assert 27 < ends < 33, (g, ends)  # (30 mm short: shared between the seam's two ends, reported, not stretched)
    assert ca.links_pct(c, X)["max"] < 0.05  # (exact on the surface; a link is its chord: (k L)^2 / 24)


def test_hinge_turns_to_its_planned_angle():
    u, F = grid(21, 11, 0.2, 0.1)
    M, _ = pattern([("a", u, F)])
    row = [10 * 11 + j for j in range(11)]  # (the middle column)
    M["folds"] = [{"piece": "a", "name": "f", "rows": [row], "sign": 1.0}]
    c = _net(M)
    plan = {"folds": {"f": {"on": "a", "fold": "f", "turn_deg": 90.0}}}
    pan = Panels(c, plan)
    assert pan.n == 2 and len(pan.hinges) == 1
    TH0 = pan.fit_start(np.c_[c.uv, np.zeros(c.n)] + [0, 0, 0.2])
    keep = np.array([[[5, 5, 5], [5, 5, 6]]], float)
    TH, rd = ca.assemble(pan, TH0, keep)
    h = rd["hinges"]["f#0"]
    assert abs(h["got"] - 90.0) < 2.0, h
    assert max(rd["seam_gaps_mm"]["hinge f#0"]) < 0.5


def test_sparse_seam_resampled_into_one_chain():
    ua, Fa = grid(13, 9, np.pi * R, 0.2)
    ub, Fb = grid(13, 5, np.pi * R, 0.2)  # (b coarser along its height: its seam points at other fractions)
    M2, off = pattern([("a", ua, Fa), ("b", ub, Fb)])
    M2["sew"] = np.array([(0, off[1] + 12 * 5), (8, off[1] + 12 * 5 + 4), (12 * 9, off[1]), (12 * 9 + 8, off[1] + 4)])
    J, _, _, nw = join_seams(M2)
    assert len(nw) > 0
    net = Network(J)
    # (every boundary point of both long edges is sewn: one chain end to end)
    for p, xs in ((0, (0.0, np.pi * R)), (1, (0.0, np.pi * R))):
        ids = np.where(J["piece"] == p)[0]
        for x in xs:
            e = ids[np.abs(J["uv"][ids, 0] - x) < 1e-9]
            assert np.isin(e, J["sew"].ravel()).all()
    # (matching arc fractions: sewn points at the same height)
    s = J["sew"]
    assert np.abs(J["uv"][s[:, 0], 1] - J["uv"][s[:, 1], 1]).max() < 1e-9
    assert net.chain_report(np.c_[J["uv"], np.zeros(len(J["uv"]))])["links"] > 0
