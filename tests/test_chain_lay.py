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




def test_mirrored_lapels_both_turn_outward_by_the_plan():
    """N2i: ONE fold-direction rule (chain_lay.fold_way): the draft's turn (+ = onto the outside) x the piece's outside
    (chain_lay.outside: which side of F faces away from the body). A mirrored pair (the draft's flap signs +1 / -1, the
    mirrored flat rewound as drafted) both turn OUTWARD, away from the body, by the plan's angle (N2h: the flap sign
    multiplied in turned one lapel in, onto the body)."""
    from hifipushie import chain_lay
    from hifipushie import chain_solve as cs
    r = 0.3
    u, F = grid(21, 11, 0.2, 0.1)
    um = u * [-1, 1]
    M, off = pattern([("a.L", u, F), ("a.R", um, F[:, ::-1])])
    row = np.array([16 * 11 + j for j in range(11)])
    M["folds"] = [{"piece": "a.L", "name": "f", "rows": [row], "sign": 1.0, "turn": 1.0},
                  {"piece": "a.R", "name": "f", "rows": [row + off[1]], "sign": -1.0, "turn": 1.0}]
    net = Network(M)
    uv = net.uv
    X0 = np.c_[uv[:, 0] + np.where(net.piece == 0, 0.02, -0.02), np.full(net.n, -r - 0.02), uv[:, 1]]
    body = cylinder(r, -0.2, 0.3)
    out = chain_lay.outside(net, X0, body)
    assert out == {"a.L": 1.0, "a.R": 1.0}
    plan = {"folds": {"f.L": {"on": "a.L", "fold": "f", "turn_deg": 90.0},
                      "f.R": {"on": "a.R", "fold": "f", "turn_deg": 90.0}}}
    X, rep = cs.solve(net, X0, body=body, folds=chain_lay.fold_rows(net, plan, out))
    turns = chain_lay._fold_turns(net, X, plan, out)
    for nm, k in (("f.L", 0), ("f.R", 1)):
        assert abs(turns[nm]["median"] - 90.0) < 5.0, turns
        assert turns[nm]["way"] == turns[nm]["plan_way"] == "outward", turns
        mine = net.piece == k
        flap = np.where(mine & (np.abs(uv[:, 0]) > 0.17))[0]
        Fb = net.F[(mine & (np.abs(uv[:, 0]) < 0.14))[net.F].all(1)]
        nb = np.cross(X[Fb[:, 1]] - X[Fb[:, 0]], X[Fb[:, 2]] - X[Fb[:, 0]]).sum(0) * out[f"a.{nm[-1]}"]
        nb /= np.linalg.norm(nb)
        mid = X[row + (off[1] if k else 0)].mean(0)
        assert (X[flap] - mid).mean(0) @ nb > 0.01, nm  # (the flap stands off the base's OUTSIDE face)
