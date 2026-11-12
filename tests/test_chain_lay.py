"""Step 5's chains-only network and isometric start (N2b: chain_lay_net, chain_lay): synthetic, fast."""
from types import SimpleNamespace

import numpy as np

from hifipushie import chain_lay, chain_solve as cs
from hifipushie.chain_lay_net import chain_network
from hifipushie.chain_net import Network

from test_chain_solve import cylinder, grid, pattern

R = 0.06


def _band_and_panel(stiff=False, fold=False):
    """A 0.30 x 0.06 band (centre piece) whose bottom edge is named on a loop tape round a neck (cylinder r 0.06), and
    a 0.30 x 0.08 panel sewn under it along that edge. fold: a row along the band's middle."""
    ub, Fb = grid(31, 7, 0.30, 0.06)
    ub = ub - [0.15, 0.0]
    up, Fp = grid(31, 5, 0.30, 0.08)
    up = up - [0.15, 0.08]
    M, off = pattern([("band", ub, Fb), ("panel", up, Fp)])
    M["sew"] = np.array([(i * 7, off[1] + i * 5 + 4) for i in range(31)])
    th = np.linspace(0, 2 * np.pi, 64, endpoint=False) + np.pi / 2
    neck = np.c_[R * np.cos(th), R * np.sin(th), np.full(64, 0.1)]
    low = np.array([[0.0, -R, 0.05], [0.0, -R, -0.05]])
    M["starts"] = {"tapes": {"neck": {"kind": "loop", "pts": neck}, "low": {"kind": "path", "pts": low}},
                   "pieces": {"band": ["neck"], "panel": ["low"]}, "edges": {"band": {"bottom": {"tape": "neck"}}}}
    row = [i * 7 + 3 for i in range(31)]
    if fold:
        M["folds"] = [{"piece": "band", "name": "roll", "rows": [row], "sign": 1.0}]
    n = len(M["uv"])
    st = np.r_[np.full(len(ub), 1.0 if stiff else 0.0), np.zeros(len(up))]
    net = Network(M, stiff=st, bend=np.r_[np.full(len(ub), 5.0 if stiff else 1.0), np.ones(len(up))][:n])
    holds = SimpleNamespace(plies={}, layers={}, inside={}, parts=[SimpleNamespace(pieces=["band"]),
                                                                   SimpleNamespace(pieces=["panel"])])
    body = SimpleNamespace(contact=cylinder(R, -0.3, 0.3))
    return net, holds, body


def test_the_network_is_chains_only_and_keeps_the_cut():
    net, _, _ = _band_and_panel(fold=True)
    c, keep = chain_network(net)
    assert c.n < net.n / 2  # (no interior points)
    assert np.allclose(c.link_L, net.link_L)
    assert len(c.edges) > len(c.link_L)  # (lines across between the chains)


def test_a_strip_laid_on_a_curved_tape_is_exact():
    net, holds, body = _band_and_panel()
    c, keep = chain_network(net)
    S = chain_lay.lay(net, c, keep, body, {}, holds)
    a, b = c.chain_v.T
    m = c.chain_piece == c.names.index("band")
    e = np.abs(np.linalg.norm(S["X0"][b] - S["X0"][a], axis=1) / c.chain_L - 1)[m] * 100
    bottom = np.where((c.piece == 0) & (c.uv[:, 1] < 1e-9))[0]
    sd, _ = body.contact.query(S["X0"][bottom])
    print(S["start"], e.max())
    assert np.sort(e)[-2] < 0.5  # (every link at its cut but the one where the outline's two walks meet)
    assert np.abs(S["X0"][bottom, 2] - 0.1).max() < 0.005  # (the edge lies on its tape)
    assert sd.min() > 0.0


def test_two_panels_sewn_along_a_tape_edge_start_closed():
    net, holds, body = _band_and_panel()
    c, keep = chain_network(net)
    S = chain_lay.lay(net, c, keep, body, {}, holds)
    gap = S["start"]["seam_gap_mm"]["band ~ panel"]
    print(S["start"])
    assert gap < 1.0  # (the panel is laid from its seam with the laid band: closed by construction)
    assert S["X0"][c.piece == 1, 2].mean() < 0.1  # (away from the band, towards its own tape)


def test_a_stiff_collar_on_a_neckline_turns_its_fold_row():
    net, holds, body = _band_and_panel(stiff=True, fold=True)
    c, keep = chain_network(net)
    plan = {"folds": {"fall": {"on": "band", "fold": "roll", "turn_deg": 160.0}}}
    S = chain_lay.lay(net, c, keep, body, plan, holds)
    X, rep = cs.solve(c, S["X0"], body=body, folds=S["folds"], pulls=S["pulls"], plies=S["plies"])
    print(rep["links"], rep["folds"], rep.get("contact"))
    assert rep["links"]["worst_pct"] < 2.0
    assert max(f["median_off_deg"] for f in rep["folds"].values()) < 20.0
    assert rep["contact"]["inside"] == 0
