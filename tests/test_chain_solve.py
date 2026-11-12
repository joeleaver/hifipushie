"""chain_solve (N1 of docs/proposals/step5_rewrite.md): one solve, nothing held, every link solved. Synthetic, fast."""
import ast
import pathlib

import numpy as np

from hifipushie import chain_solve as cs
from hifipushie.chain_core import GAP, LAYER
from hifipushie.chain_net import Contact, Network

SRC = pathlib.Path(cs.__file__).parent


def grid(nx, ny, w, h):
    """uv (nx*ny, 2) of a w x h rectangle and its faces (CCW in uv)."""
    u, v = np.meshgrid(np.linspace(0, w, nx), np.linspace(0, h, ny), indexing="ij")
    uv = np.c_[u.ravel(), v.ravel()]
    F = []
    for i in range(nx - 1):
        for j in range(ny - 1):
            a, b, c, d = i * ny + j, (i + 1) * ny + j, (i + 1) * ny + j + 1, i * ny + j + 1
            F += [(a, b, c), (a, c, d)]
    return uv, np.array(F)


def pattern(pieces, sew=(), folds=None):
    """pieces: [(name, uv, F)] -> the pattern mesh dict Network reads, and each piece's vertex offset."""
    uv, F, pc, off = [], [], [], []
    n = 0
    for k, (_, u, f) in enumerate(pieces):
        uv.append(u)
        F.append(f + n)
        pc.append(np.full(len(u), k))
        off.append(n)
        n += len(u)
    M = {"uv": np.concatenate(uv), "F": np.concatenate(F), "piece": np.concatenate(pc),
         "names": [p[0] for p in pieces], "sew": np.asarray(sew, np.int64).reshape(-1, 2)}
    if folds:
        M["folds"] = folds
    return M, off


def cylinder(r, z0, z1, seg=48, rings=12):
    th = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    zs = np.linspace(z0, z1, rings)
    V = [(r * np.cos(t), r * np.sin(t), z) for z in zs for t in th] + [(0, 0, z0), (0, 0, z1)]
    T = []
    for k in range(rings - 1):
        for s in range(seg):
            a, b = k * seg + s, k * seg + (s + 1) % seg
            T += [(a, b, b + seg), (a, b + seg, a + seg)]
    bot, top = len(V) - 2, len(V) - 1
    for s in range(seg):
        T.append((bot, (s + 1) % seg, s))
        T.append((top, (rings - 1) * seg + s, (rings - 1) * seg + (s + 1) % seg))
    return Contact(np.array(V, float), np.array(T))


def strip(nx=41, ny=6, L=0.4, w=0.05, stiff=None):
    uv, F = grid(nx, ny, L, w)
    M, _ = pattern([("strip", uv, F)])
    return Network(M, stiff=stiff), uv


def flat(uv, z=0.0):
    return np.c_[uv, np.full(len(uv), z)]


def test_stretched_strip_comes_back_to_its_lengths():
    net, uv = strip()
    X, rep = cs.solve(net, flat(uv * [1.3, 1.0]))
    print(rep["links"], rep["edges"], rep["seconds"])
    assert rep["links"]["worst_pct"] < 2.0 and rep["links"]["over_tol"] == 0
    assert rep["edges"]["worst_over_pct"] < 2.0 and rep["hard_ok"]


def test_compressed_strip_relaxes_without_crossing():
    net, uv = strip()
    X0 = flat(uv * [0.5, 1.0])
    X0[:, 2] = 0.002 * np.sin(uv[:, 0] * 40)  # (a little buckle to start from)
    X, rep = cs.solve(net, X0)
    print(rep["links"], rep["seconds"])
    assert rep["links"]["worst_pct"] < 2.0
    cols = X.reshape(41, 6, 3).mean(1)
    ax = cols[-1] - cols[0]
    assert np.all(np.diff(cols @ ax) > 0)  # the columns keep their order along the strip
    n = np.cross(X[net.F[:, 1]] - X[net.F[:, 0]], X[net.F[:, 2]] - X[net.F[:, 0]])
    assert np.all(n @ n.mean(0) > 0)  # no face turned over


def test_stiff_strip_on_a_curve_keeps_its_flat_width():
    nx, ny, L, w, R = 41, 6, 0.4, 0.05, 0.1
    uv, F = grid(nx, ny, L, w)
    net = Network(pattern([("collar", uv, F)])[0], stiff=np.ones(len(uv)))
    X0 = np.c_[uv[:, 0] - L / 2, np.full(len(uv), -R), uv[:, 1]]
    edge = np.where(uv[:, 1] == 0)[0]
    th = (uv[edge, 0] - L / 2) / R
    to = np.c_[R * np.sin(th), -R * np.cos(th), np.zeros(len(edge))]
    X, rep = cs.solve(net, X0, pulls=[{"ids": edge, "to": to, "name": "neck edge"}],
                      stiffness=np.full(len(uv), 8.0))
    print(rep["links"], rep["pulls"], rep["seconds"])
    assert rep["links"]["worst_pct"] < 2.0
    assert rep["pulls"]["neck edge"]["max_mm"] < 5.0 and rep["pulls"]["neck edge"]["mean_mm"] < 2.0
    G = X.reshape(nx, ny, 3)
    dev = []
    for col in G:  # each line across the width stays straight and full width
        a, b = col[0], col[-1]
        t = np.clip(((col - a) @ (b - a)) / ((b - a) @ (b - a)), 0, 1)
        dev.append(np.linalg.norm(col - (a + t[:, None] * (b - a)), axis=1).max())
        assert abs(np.linalg.norm(b - a) - w) < 0.02 * w
    print("width line worst off straight mm", max(dev) * 1e3)
    assert max(dev) < 1.5e-3 and np.median(dev) < 1e-4  # (the free corners curl ~1 mm; the rest is straight)


def test_tube_closes_round_a_cylinder_without_entering():
    r, H = 0.05, 0.12
    W = 1.25 * np.pi * r
    nx, ny = 21, 9
    uv, F = grid(nx, ny, W, H)
    col0, col1 = np.arange(ny), (nx - 1) * ny + np.arange(ny)
    n = len(uv)
    M, _ = pattern([("front", uv, F), ("back", uv.copy(), F)], sew=np.r_[np.c_[col0, col0 + n], np.c_[col1, col1 + n]])
    net = Network(M)
    X0 = np.r_[np.c_[uv[:, 0] - W / 2, np.full(n, -r - 0.01), uv[:, 1]],
               np.c_[uv[:, 0] - W / 2, np.full(n, r + 0.01), uv[:, 1]]]
    body = cylinder(r, -0.05, H + 0.05)
    X, rep = cs.solve(net, X0, body=body)
    print(rep["links"], rep["contact"], rep["seconds"])
    assert rep["links"]["worst_pct"] < 2.0
    assert rep["contact"]["inside"] == 0 and rep["contact"]["deepest_mm"] < 0.05
    ang = np.sort(np.arctan2(X[:, 1], X[:, 0]))
    assert np.max(np.diff(np.r_[ang, ang[0] + 2 * np.pi])) < np.radians(30)  # all the way round


def test_fold_turns_to_its_angle_lengths_exact():
    nx, ny = 21, 11
    uv, F = grid(nx, ny, 0.2, 0.1)
    row = 10 * ny + np.arange(ny)  # the column at u = 0.1
    M, _ = pattern([("rect", uv, F)], folds=[{"name": "f", "piece": "rect", "rows": [row]}])
    net = Network(M)
    X, rep = cs.solve(net, flat(uv), folds=[{"row": row, "turn_deg": 170.0, "toward": 1, "name": "f"}])
    print(rep["folds"], rep["links"], rep["seconds"])
    assert rep["folds"]["f"]["worst_off_deg"] < 3.0
    assert rep["links"]["worst_pct"] < 0.1
    # the halves themselves, read off their own planes
    G = X.reshape(nx, ny, 3)
    na = np.cross(G[0, -1] - G[0, 0], G[9, 0] - G[0, 0])
    nb = np.cross(G[20, -1] - G[20, 0], G[11, 0] - G[20, 0])
    ang = np.degrees(np.arccos(abs(na @ nb) / np.linalg.norm(na) / np.linalg.norm(nb)))
    print("halves' planes apart deg", ang)
    assert abs(ang - 10.0) < 4.0  # (turned 170: the planes are 10 degrees apart)


def test_tie_brings_two_pieces_to_their_gap():
    uv, F = grid(4, 4, 0.03, 0.03)
    M, off = pattern([("a", uv, F), ("b", uv.copy(), F)])
    net = Network(M)
    X0 = np.r_[flat(uv), flat(uv) + [0.08, 0, 0.01]]
    a, b = off[0] + 15, off[1] + 0
    X, rep = cs.solve(net, X0, ties=[(a, b, LAYER)])
    print(rep["ties"], rep["links"], rep["seconds"])
    assert rep["ties"]["worst_mm"] < 0.1
    assert abs(np.linalg.norm(X[b] - X[a]) - LAYER) < 1e-4
    assert rep["links"]["worst_pct"] < 2.0


def test_contradicting_pulls_never_stretch_a_link():
    net, uv = strip(nx=21, ny=4, L=0.2, w=0.03)
    left, right = np.where(uv[:, 0] == 0)[0], np.where(np.isclose(uv[:, 0], 0.2))[0]
    pulls = [{"ids": left, "to": flat(uv[left]) + [-0.1, 0, 0], "name": "left"},
             {"ids": right, "to": flat(uv[right]) + [0.1, 0, 0], "name": "right"}]  # 0.4 apart: 2x the strip
    X, rep = cs.solve(net, flat(uv), pulls=pulls)
    print(rep["links"], rep["pulls"], rep["seconds"])
    assert rep["links"]["worst_pct"] < 0.1 and rep["edges"]["worst_over_pct"] < 0.1
    assert rep["pulls"]["left"]["max_mm"] > 80 and rep["pulls"]["right"]["max_mm"] > 80  # reported, not hidden


def _idents(path):
    tree = ast.parse(path.read_text())
    doc = {id(n.body[0].value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef))
           and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            out.append(n.id)
        elif isinstance(n, ast.arg):
            out.append(n.arg)
        elif isinstance(n, ast.Attribute):
            out.append(n.attr)
        elif isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            out.append(n.name)
        elif isinstance(n, ast.keyword) and n.arg:
            out.append(n.arg)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in doc:
            out += n.value.replace("-", " ").split()
    return [w.lower() for x in out for w in x.replace(" ", "_").split("_") if w]


FILES = [SRC / "chain_solve.py", SRC / "chain_solve_terms.py"]


def test_the_solver_has_no_held_set():
    for f in FILES:
        words = set(_idents(f))
        bad = words & {"held", "hold", "holds", "fixed", "fix", "pinned", "pin", "pins", "frozen", "freeze", "locked",
                       "anchor", "anchored"}
        assert not bad, f"{f.name} has a held / pinned set: {bad}"
    assert "held" not in cs.solve.__code__.co_varnames


def test_the_solver_reads_no_roles_or_wear_state():
    for f in FILES:
        words = set(_idents(f))
        bad = words & {"band", "fall", "stand", "collar", "placket", "ring", "rings", "sleeve", "panel", "tube", "open",
                       "closed", "worn", "wear"}
        assert not bad, f"{f.name} reads a role or wear state: {bad}"


WALL_24K = 150.0  # s: N1c (CHOLMOD) measured 69-109 s at load 45-68 on 24 cores (N1b, splu: 601 s at load 135); target ~60


def test_garment_sized_network_solves_in_time():
    """tests/chain_solve_bench.py at scale 1 (~24k points: torso + two sleeves round three cylinders): hard residuals
    and wall time. (Slow tier: tests/slow_tests.txt.)"""
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    import chain_solve_bench as bench
    net, X, rep, wall = bench.run(1.0)
    print(rep["links"]["worst_pct"], rep["contact"], rep["timing"], wall)
    assert net.n > 20000 and rep["hard_ok"]
    assert rep["links"]["worst_pct"] < 0.1 and rep["contact"]["inside"] == 0
    assert wall < WALL_24K
