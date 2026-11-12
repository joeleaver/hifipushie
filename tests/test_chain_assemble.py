"""Step 5's ASSEMBLED start (N2c, chain_lay.lay): pieces sewn onto what is already sewn, seams one chain from the start,
loops closed by bends only, a loop bends can't close named (never stretched). Synthetic, fast."""
from types import SimpleNamespace

import numpy as np

from hifipushie import chain_lay
from hifipushie.chain_lay_net import chain_network
from hifipushie.chain_net import Network

from test_chain_lay import _band_and_panel
from test_chain_solve import cylinder, grid, pattern

NY = 11


def _tube(wb=0.2, stiff=False, hb=0.1):
    """Two 0.1 tall panels, a 0.2 wide and b wb wide, sewn side to side both ways (a tube). a's left side is named on a
    vertical tape beside a thin frame (cylinder r 0.02 at the origin); b's on a girth loop round the frame."""
    ua, Fa = grid(21, NY, 0.2, 0.1)
    nb = int(round(wb / 0.01)) + 1
    ub, Fb = grid(nb, NY, wb, hb)
    M, off = pattern([("a", ua, Fa), ("b", ub, Fb)])
    M["sew"] = np.array([(20 * NY + j, off[1] + j) for j in range(NY)] +
                        [(off[1] + (nb - 1) * NY + j, j) for j in range(NY)])
    th = np.linspace(0, 2 * np.pi, 64, endpoint=False)
    loop = np.c_[0.07 * np.cos(th), 0.07 * np.sin(th), np.full(64, 0.05)]
    side = np.c_[np.full(11, 0.07), np.zeros(11), np.linspace(0, 0.1, 11)]
    M["starts"] = {"tapes": {"girth": {"kind": "loop", "pts": loop}, "side": {"kind": "path", "pts": side}},
                   "pieces": {"a": ["side"], "b": ["girth"]}, "edges": {"a": {"left": {"tape": "side"}}}}
    n = len(M["uv"])
    net = Network(M, stiff=np.full(n, 1.0 if stiff else 0.0), bend=np.full(n, 5.0 if stiff else 1.0))
    holds = SimpleNamespace(plies={}, layers={}, inside={}, parts=[SimpleNamespace(pieces=["a"]),
                                                                   SimpleNamespace(pieces=["b"])])
    return net, holds, SimpleNamespace(contact=cylinder(0.02, -0.3, 0.3))


def test_two_panels_sewn_into_a_tube_close_by_bends_only():
    net, holds, body = _tube()
    c, keep = chain_network(net)
    S = chain_lay.lay(net, c, keep, body, {}, holds)
    st = S["start"]["after_bends"]
    print(S["order"], S["start"]["before_bends"]["links_max_pct"], st)
    assert S["order"] == ["a", "b"]
    assert st["seam_gap_mm"] == 0.0  # (one chain from the start: nothing was ever apart)
    assert st["links_max_pct"] < 0.5 and st["loops_open"] == 0
    assert S["start"]["closed"]


def test_a_loop_bends_cannot_close_is_named_not_stretched():
    net, holds, body = _tube(hb=0.07)  # (b's sides 30 mm shorter than the sides of a they are sewn to)
    c, keep = chain_network(net)
    S = chain_lay.lay(net, c, keep, body, {}, holds)
    st = S["start"]["after_bends"]
    print(st["sides_differ_mm"], S["start"]["named"])
    d = st["sides_differ_mm"]["a ~ b"]
    assert d["a"] < -10 and d["b"] > 10  # (each side off its cut by about half the 2 x 30 mm: named, never hidden)
    assert "a ~ b" in S["start"]["named"] and "back to step 4" in S["start"]["named"]


def test_a_collar_strip_with_a_roll_line_is_assembled_onto_its_neckline():
    net, holds, body = _band_and_panel(stiff=True, fold=True)
    c, keep = chain_network(net)
    plan = {"folds": {"fall": {"on": "band", "fold": "roll", "turn_deg": 160.0}}}
    S = chain_lay.lay(net, c, keep, body, plan, holds)
    st = S["start"]["after_bends"]
    print(st)
    assert st["links_max_pct"] < 0.5 and st["seam_gap_mm"] == 0.0
    assert st["folds"]["fall"]["off"] < 20.0  # (the roll is pressed while the garment is made)
    bottom = np.where((c.piece == 0) & (c.uv[:, 1] < 1e-9))[0]
    assert np.abs(S["X0"][bottom, 2] - 0.1).max() < 0.03  # (the neck edge near its tape: settle's pull puts it on)
