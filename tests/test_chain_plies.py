"""Plies and layers as a TERM of chain_solve's one solve (N2, chain_solve_plies): synthetic, fast."""
import numpy as np

from hifipushie import chain_solve as cs
from hifipushie import chain_solve_plies as cp
from hifipushie.chain_core import GAP, LAYER
from hifipushie.chain_net import Network

from test_chain_solve import cylinder, grid, pattern


def _facing_on_panel():
    """A 0.30 x 0.20 panel; a 0.06 facing in its flat along its right edge, sewn there; a fold row at x = 0.20."""
    ny = 21
    up, Fp = grid(31, ny, 0.30, 0.20)
    uf, Ff = grid(7, ny, 0.06, 0.20)
    uf = uf + [0.24, 0.0]
    M, off = pattern([("panel", up, Fp), ("facing", uf, Ff)])
    sew = [(30 * ny + j, off[1] + 6 * ny + j) for j in range(ny)]
    row = [20 * ny + j for j in range(ny)]
    M["sew"] = np.array(sew)
    M["folds"] = [{"name": "turn", "piece": "panel", "rows": [row]}]
    return Network(M), off, row


def test_a_facing_folded_with_its_panel_stays_on_it_never_crosses():
    net, off, row = _facing_on_panel()
    X0 = np.c_[net.uv, np.zeros(net.n)]
    X0[off[1]:, 2] = -LAYER
    pl = cp.bind(net, {"facing": "panel"}, {"facing": 1}, {"panel": 1.0})
    X, rep = cs.solve(net, X0, folds=[{"row": row, "turn_deg": 170.0, "toward": 1, "name": "turn"}], plies=pl)
    p = rep["plies"]["facing on panel"]
    print(rep["plies"], rep["folds"], rep["links"])
    assert p["crossed"] == 0
    assert p["max_mm"] < 1.0
    assert rep["folds"]["turn"]["worst_off_deg"] < 5.0
    assert rep["links"]["worst_pct"] < 2.0
    # the facing went over with the turned part: on its inner face, a LAYER from it
    v = net.verts("facing")
    assert X[v, 2].max() > 0.0  # (the turned part lies over the panel now, z > 0)


def test_two_layer_collar_on_a_neck_keeps_its_ply_a_layer_off():
    r = 0.06
    neck = cylinder(r, -0.1, 0.2)
    ny = 7
    uu, F = grid(31, ny, 0.30, 0.06)
    M, off = pattern([("under", uu, F), ("top", uu.copy(), F)])
    n0 = len(uu)
    top = [i * ny + ny - 1 for i in range(31)]
    ends = [j for j in range(ny)] + [30 * ny + j for j in range(ny)]
    M["sew"] = np.array([(a, n0 + a) for a in sorted(set(top + ends))])
    net = Network(M, stiff=np.ones(2 * n0), bend=np.full(2 * n0, 5.0))
    R = r + GAP + 0.002
    th = net.uv[:, 0] / R
    X0 = np.c_[R * np.cos(th), R * np.sin(th), net.uv[:, 1]]  # (both plies seeded on top of each other)
    pl = cp.bind(net, {"top": "under"}, {"top": 1}, {"under": 1.0})
    X, rep = cs.solve(net, X0, body=neck, plies=pl)
    p = rep["plies"]["top on under"]
    print(rep["plies"], rep["links"], rep.get("contact"))
    assert p["crossed"] == 0
    # (sewn round three edges, the ply can't be a full LAYER in right at its seams: under a LAYER off there)
    assert p["max_mm"] < LAYER * 1e3 and p["mean_mm"] < 1.0
    assert rep["links"]["worst_pct"] < 2.0
    rr = np.linalg.norm(X[:, :2], axis=1)
    assert rr.min() >= r + GAP - 1e-3  # (nothing inside the neck)
    # unsewn top points sit a LAYER inside the under ply
    free = np.setdiff1d(np.arange(n0, 2 * n0), net.sew[:, 1])
    d = np.linalg.norm(X[free, :2], axis=1) - np.linalg.norm(X[free - n0, :2], axis=1)
    assert np.median(d) < -0.5 * LAYER


def test_bindings_skip_points_sewn_to_their_host():
    net, off, _ = _facing_on_panel()
    pl = cp.bind(net, {"facing": "panel"}, {"facing": 1}, {"panel": 1.0})
    from hifipushie.chain_solve_terms import nodes_of
    nid, nn = nodes_of(net)
    b = cp.blocks(pl, nid, nn)[0]
    assert not (b["tri"] == b["p"][:, None]).any()
    assert len(b["p"]) == len(net.verts("facing")) - 21
