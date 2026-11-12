"""Step 5's chains-only network (N2b: chain_lay_net): synthetic, fast."""
from types import SimpleNamespace

import numpy as np


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


