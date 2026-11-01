"""chain_net / chain_garment: lengths exact, seams one node, no fit input, refusals name a line, mirror two-way (the collapse),
and the MCP layer offers no other way to start a garment."""
import asyncio
import re

import numpy as np
import pytest

from hifipushie import chain_garment as cg, chain_net as cn, server


def _strip(n=9, w=0.1, h=0.02, x0=0.0, piece=0):
    """A flat strip of n x 2 vertices."""
    xs = np.linspace(x0, x0 + w, n)
    uv = np.r_[np.c_[xs, np.zeros(n)], np.c_[xs, np.full(n, h)]]
    F = []
    for i in range(n - 1):
        F += [[i, i + 1, n + i], [i + 1, n + i + 1, n + i]]
    return uv, np.array(F), np.full(2 * n, piece)


def _mesh(pieces=2):
    uvs, Fs, ps, off = [], [], [], 0
    for p in range(pieces):
        uv, F, pc = _strip(piece=p, x0=0.2 * p)
        uvs.append(uv), Fs.append(F + off), ps.append(pc)
        off += len(uv)
    names = [f"p{k}" for k in range(pieces)]
    return {"uv": np.concatenate(uvs), "F": np.concatenate(Fs), "piece": np.concatenate(ps), "names": names,
            "sew": np.zeros((0, 2), np.int64), "folds": [], "closures": []}


def test_project_makes_chains_exact():
    """From a rough start every exact link reaches its cut length; an at-most line may stay shorter, never longer."""
    M = _mesh(1)
    net = cn.Network(M)
    rng = np.random.default_rng(1)
    X = np.c_[net.uv, np.zeros(net.n)] * [1.1, 1.0, 1.0] + rng.normal(0, 0.002, (net.n, 3))
    li, lj, lL, lE = net.lines(step=1)
    I, J = np.r_[net.link_i, li], np.r_[net.link_j, lj]
    L, E = np.r_[net.link_L, lL], np.r_[np.ones(len(net.link_L), bool), lE]
    Y, rd = cn.project(X, I, J, L, E, iters=60, step=0.01)
    assert rd["worst_exact_pct"] <= cn.EXACT_TOL * 100 * 1.01, rd
    assert net.chain_report(Y)["worst_pct"] < 0.02
    d = np.linalg.norm(Y[J] - Y[I], axis=1)
    assert (d[~E] <= L[~E] * (1 + cn.ATMOST_TOL) + 1e-9).all()


def test_seam_merge_is_one_node_and_keeps_closures_apart():
    """Sewn points are one node; closures are wear and never merge; a seam's two sides average, the difference is read."""
    M = _mesh(2)
    n = 9
    M["sew"] = np.array([[n + i, 18 + i] for i in range(n)])  # p0's top edge to p1's bottom edge
    M["uv"][18:27, 0] -= 0.2  # same x
    M["closures"] = [{"name": "c", "over": "p0", "under": "p1", "v": [[0, 18]], "closed": [True]}]
    net = cn.Network(M)
    assert net.root[n] == net.root[18]
    assert net.root[0] != net.root[18 + 9]
    assert net.root[0] != net.root[18 + 0] or (0, 18) in [tuple(p) for p in M["sew"]]
    # a link whose two ends are sewn together closes a cut: no length
    assert (net.link_i != net.link_j).all()
    assert net.seam_mismatch()["max_mm"] < 1e-6


def test_mirror_map_is_two_way():
    """The first all-pieces build mapped left -> right only: every right node mirrored onto itself and the net collapsed."""
    M = _mesh(2)
    M["names"] = ["a.L", "a.R"]
    net = cn.Network(M)
    mir = cn.mirror_map(net, [("a.L", "a.R", 1.0)])
    both = np.r_[net.verts("a.L"), net.verts("a.R")]
    assert (mir[both] >= 0).all()
    assert (net.piece[mir[net.verts("a.R")]] == net.pid("a.L")).all()


def test_no_fit_input():
    """Positions can't get in: Pattern keeps pattern keys only, and a Network given positions refuses."""
    M = _mesh(1)
    M2 = dict(M, A=np.zeros((len(M["uv"]), 3)))
    p = cg.pattern_from_mesh(M2)
    assert "A" not in p.M and "A" not in cg.PATTERN_KEYS
    with pytest.raises(ValueError, match="never a fit"):
        cn.Network(M2)


def test_refusal_names_the_line():
    """A length past the limit is refused with the piece, the line and the next step."""
    M = _mesh(1)
    n = len(M["uv"])
    b = object.__new__(cg.GarmentBuild)
    b.net = cn.Network(M)
    b.roles = cg.Roles(None, None, [], [], ["p0"], None, None, None)
    b.reads = {}
    b.X = np.c_[M["uv"] * [1.5, 1.0], np.zeros(n)]
    with pytest.raises(cg.ChainRefused) as e:
        b.gate_lengths()
    t = str(e.value)
    assert "p0 edge" in t and "next:" in t and "alter_pattern" in t


def test_contact_side_and_floor():
    """A point under a floor comes up to its gap in project; the signed distance reads the side."""
    V = np.array([[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0.0]])
    T = np.array([[0, 1, 2], [0, 2, 3]])
    ct = cn.Contact(V, T)
    sd, n = ct.query(np.array([[0.1, 0.1, 0.05], [0.1, 0.1, -0.02]]))
    assert sd[0] == pytest.approx(0.05) and sd[1] == pytest.approx(-0.02)
    X = np.array([[0.0, 0.0, -0.01], [0.1, 0.0, -0.01]])
    Y, rd = cn.project(X, [0], [1], [0.1], [True], contacts=[(ct, np.array([0, 1]), 0.005)], iters=20)
    assert ct.query(Y)[0].min() >= 0.005 - 1e-4
    assert abs(np.linalg.norm(Y[1] - Y[0]) - 0.1) < 1e-4


def test_threads_read_warp_and_weft_not_the_bias():
    """A pure shear of the flat cloth stretches the bias, not the threads' first-order reading (and a stretch reads)."""
    uv = np.array([[0, 0], [0.1, 0], [0, 0.1.__float__()]], float)
    th = cn.Threads(uv, np.array([[0, 1, 2]]), 0.02)
    X = np.c_[uv, np.zeros(3)]
    assert abs(th.report(X)["max_pct"]) < 1e-6
    X2 = X.copy()
    X2[:, 0] *= 1.1
    assert th.report(X2)["max_pct"] == pytest.approx(10.0, abs=0.01)


GATED = ("fit_garment", "style_garment", "release_garment", "arrange_garment", "dress", "look_cloth", "check_garment",
         "check_garment_reference", "game_garment")


@pytest.mark.skipif(server.LEGACY_CLOTH, reason="legacy cloth on")
def test_only_path_for_clothes():
    """A blind agent asking how to make clothes lands on the chain path and nothing else."""
    for q in ("make a shirt", "fit a garment", "dress the character", "drape a jacket on the body", "clothes", "simulate cloth"):
        t = server.find_tool(q, limit=8)
        assert "Clothes: design_garment" in t and "chain_garment" in t, (q, t)
        names = re.findall(r"^\d+\. (\w+) ", t, re.M)
        assert not set(names) & set(GATED), (q, names)
    full = server.find_tool("")
    for g in GATED:
        assert not re.search(r"\b" + g + r"\b", full)
    assert "chain_garment" in full
    ins = server.mcp.instructions
    assert "chain_garment" in ins and not any(g in ins for g in GATED)
    for g in GATED:
        with pytest.raises(ValueError, match="chain_garment"):
            asyncio.run(server.call_tool(g, {}))
        assert "chain_garment" in server.guide(g)
    for topic in ("cloth", "cloth_tools", "cloth_construction", "spec", "tools", ""):
        t = server.guide(topic)
        assert not any(re.search(r"\b" + g + r"\b", t) for g in GATED), topic
    assert "chain_garment" in server.guide("cloth")


def test_chain_tool_strict_arguments():
    with pytest.raises(ValueError, match="closed"):
        server.chain_garment("x", "y", wear="half")
    with pytest.raises(ValueError, match="only with"):
        server.chain_garment("x", "y", wear="closed", opening=1.5)
    with pytest.raises(ValueError, match="1.0"):
        server.chain_garment("x", "y", wear="open", opening=9)
