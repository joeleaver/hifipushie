"""Lines across as real chains (N2j, chain_lines): a piece may curve but not squash. Synthetic, fast."""
import numpy as np

from hifipushie import chain_solve as cs
from hifipushie.chain_lay_net import chain_network
from hifipushie.chain_lines import walk, wave
from hifipushie.chain_net import Network

from test_chain_solve import cylinder, grid, pattern


def _strip(L, w, nx, ny, stiff=0.0, bend=1.0):
    uv, F = grid(nx, ny, L, w)
    net = Network(pattern([("strip", uv, F)])[0], stiff=np.full(len(uv), stiff), bend=np.full(len(uv), bend))
    c, _ = chain_network(net)
    return c


def _arc(X, P):
    return float(np.linalg.norm(np.diff(X[P], axis=0), axis=1).sum())


def _edge(c, v):
    """The strip's long edge at flat v, ordered along u."""
    lp = c.outlines["strip"]
    e = lp[np.isclose(c.uv[lp, 1], v)]
    return e[np.argsort(c.uv[e, 0])]


def _across(c):
    """The lines across the strip's width (they run along flat v)."""
    out = []
    for k in (2, 3):
        for P in walk(c, k):
            d = c.uv[P[-1]] - c.uv[P[0]]
            if abs(d[1]) > 3 * abs(d[0]):
                out.append(P)
    return out


def test_soft_strip_wraps_a_cylinder_keeping_its_width_and_smooth_edges():
    """Wrapped round a cylinder, the width curves (each line across bends: its chord shortens) but is never squashed
    (its arc stays at flat, within 1 %), and the long edges stay smooth (no waves)."""
    r, L, w = 0.05, 0.20, 0.12
    c = _strip(L, w, 41, 25)
    X0 = np.c_[c.uv[:, 1] - w / 2, np.full(c.n, -r - 0.01), c.uv[:, 0]]
    pulls = []
    for v, sg in ((0.0, -1.0), (w, 1.0)):
        e = _edge(c, v)
        th = -np.pi / 2 + sg * (w / 2) / r
        pulls.append({"ids": e, "to": np.c_[np.full(len(e), r * np.cos(th)), np.full(len(e), r * np.sin(th)),
                                            c.uv[e, 0]], "weight": 10.0, "name": f"edge{v}"})
    X, rep = cs.solve(c, X0, body=cylinder(r, -0.05, L + 0.05), pulls=pulls)
    assert rep["links"]["worst_pct"] < 1.0 and rep["contact"]["inside"] == 0
    A = _across(c)
    assert len(A) >= 4
    arcs = [_arc(X, P) / _arc(np.c_[c.uv, np.zeros(c.n)], P) for P in A]
    chords = [np.linalg.norm(X[P[-1]] - X[P[0]]) / _arc(np.c_[c.uv, np.zeros(c.n)], P) for P in A]
    print("arc / flat", np.round(arcs, 4), "chord / flat", np.round(chords, 3))
    assert max(abs(a - 1) for a in arcs) < 0.01  # (not squashed)
    assert np.median(chords) < 0.85  # (curved round the cylinder)
    for v in (0.0, w):
        e = _edge(c, v)
        wv = wave(X[e[(c.uv[e, 0] > 0.05) & (c.uv[e, 0] < L - 0.05)]], window=0.03)  # (free corners curl)
        print("edge wave", wv)
        assert wv < 2e-3


def test_strip_with_too_little_room_bulges_out_of_plane():
    """Its long edges pulled onto two lines 80 % of its width apart: the strip bulges (a smooth hump) instead of
    narrowing in its plane; every line across keeps its arc."""
    L, w = 0.20, 0.10
    c = _strip(L, w, 41, 21)
    X0 = np.c_[c.uv[:, 1] - w / 2, c.uv[:, 0], 0.002 * np.sin(np.pi * c.uv[:, 1] / w)]
    pulls = []
    for v, x in ((0.0, -0.4 * w), (w, 0.4 * w)):
        e = _edge(c, v)
        pulls.append({"ids": e, "to": np.c_[np.full(len(e), x), c.uv[e, 0], np.zeros(len(e))], "weight": 10.0,
                      "name": f"edge{v}"})
    X, rep = cs.solve(c, X0, pulls=pulls)
    assert rep["links"]["worst_pct"] < 1.0
    assert rep["pulls"]["edge0.0"]["max_mm"] < 2.0
    A = _across(c)
    flat = np.c_[c.uv, np.zeros(c.n)]
    arcs = [_arc(X, P) / _arc(flat, P) for P in A]
    print("arc / flat", np.round(arcs, 4))
    assert max(abs(a - 1) for a in arcs) < 0.01
    for P in A:  # (one hump: height rises then falls along the line, peak well up)
        z = X[P, 2] * np.sign(X[P, 2].sum())
        pk = int(np.argmax(z))
        assert z[pk] > 0.015, z
        assert np.all(np.diff(z[:pk + 1]) > -1e-4) and np.all(np.diff(z[pk:]) < 1e-4), z


def test_stiff_strip_keeps_its_shape():
    """An interfaced strip pulled by one edge onto a curve in its plane keeps its flat shape: its lines across stay
    straight and full width (exact chains, stiff bending), the pulled edge on the curve."""
    nx, ny, L, w, R = 41, 11, 0.4, 0.06, 0.15
    c = _strip(L, w, nx, ny, stiff=1.0, bend=8.0)
    X0 = np.c_[c.uv[:, 0] - L / 2, np.full(c.n, -R), c.uv[:, 1]]
    e = _edge(c, 0.0)
    th = (c.uv[e, 0] - L / 2) / R
    to = np.c_[R * np.sin(th), -R * np.cos(th), np.zeros(len(e))]
    X, rep = cs.solve(c, X0, pulls=[{"ids": e, "to": to, "name": "edge"}])
    assert rep["links"]["worst_pct"] < 1.0
    assert rep["pulls"]["edge"]["mean_mm"] < 3.0
    flat = np.c_[c.uv, np.zeros(c.n)]
    for P in _across(c):
        ch = np.linalg.norm(X[P[-1]] - X[P[0]]) / _arc(flat, P)
        assert ch > 0.99, ch  # (straight across: the stiff piece doesn't curl or crumple)
