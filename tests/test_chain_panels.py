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
        TH[:, 8] = 0.0
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
    pan = Panels(c, plan, out={"a": 1.0})
    assert pan.n == 2 and len(pan.hinges) == 1
    TH0 = pan.fit_start(np.c_[c.uv, np.zeros(c.n)] + [0, 0, 0.2])
    keep = np.array([[[5, 5, 5], [5, 5, 6]]], float)
    TH, rd = ca.assemble(pan, TH0, keep)
    h = rd["hinges"]["f#0"]
    assert abs(h["got"] - 90.0) < 2.0, h
    assert max(rd["seam_gaps_mm"]["hinge f#0"]) < 0.5


def test_outline_walked_whole_through_a_pinch():
    """(N2f, C444) An outline touching itself at one vertex (a sliver triangle on a corner, as at a collar's tip) is
    walked whole: every boundary edge once (a greedy walk cut it short and lost a collar's neck edge); a chains-only
    network gives the pattern's outline."""
    u, F = grid(5, 4, 0.2, 0.1)
    corner = 4 * 4 + 3  # (the (0.2, 0.1) corner)
    u = np.r_[u, [[0.25, 0.1], [0.25, 0.14]]]
    F = np.r_[F, [[corner, len(u) - 2, len(u) - 1]]]
    M, _ = pattern([("a", u, F)])
    net = Network(M)
    lp = net.loop("a")
    assert len(lp) == 14 + 3 and (lp == corner).sum() == 2
    E = {tuple(sorted(e)) for e in zip(lp, np.roll(lp, -1))}
    assert len(E) == 17
    c, keep = chain_network(net)
    assert set(keep[c.loop("a")]) == set(lp[np.isin(lp, keep)])


def test_ruled_hinge_turn_is_exact_by_construction():
    """(N2f) A hinge rules its turned panel: whatever the numbers (any rigid motion, any roll of both panels), the turned
    panel leaves the row at the plan's turn and meets the base at the row's middle; a fold lying on another piece is
    not ruled."""
    u, F = grid(21, 11, 0.2, 0.1)
    M, _ = pattern([("a", u, F)])
    row = [10 * 11 + j for j in range(11)]
    M["folds"] = [{"piece": "a", "name": "f", "rows": [row], "sign": 1.0}]
    c = _net(M)
    pan = Panels(c, {"folds": {"f": {"on": "a", "fold": "f", "turn_deg": 85.0, "lies_on": "a"}}}, out={"a": 1.0})
    assert list(pan.ruled) == [pan.hinges[0]["turned"]]
    rng = np.random.default_rng(3)
    h = pan.hinges[0]
    a, b = h["base"], h["turned"]
    for _ in range(5):
        TH = pan.resolve(np.c_[rng.normal(0, 1, (2, 6)), rng.uniform(0, 3, 2), rng.normal(0, 4, 2), np.zeros(2)])
        assert abs(pan.hinge_read(TH, h)[2] - 85.0) < 0.5
        assert np.linalg.norm(pan.place(TH[a], a, h["mid"][None]) - pan.place(TH[b], b, h["mid"][None])) < 1e-6
    free = Panels(c, {"folds": {"f": {"on": "a", "fold": "f", "turn_deg": 85.0, "lies_on": "b"}}}, out={"a": 1.0})
    assert not free.ruled


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


def test_seam_along_two_pieces_is_one_chain_through_the_junction():
    """An armhole-like seam: a's long edge (0.3 m) sewn sparsely to b (0.12 m) then c (0.18 m), b and c sewn at their
    meeting corner: every point along all three edges sewn, matched by arc fraction through the junction."""
    ua, Fa = grid(4, 13, 0.05, 0.3)
    ub, Fb = grid(3, 5, 0.05, 0.12)
    uc, Fc = grid(3, 7, 0.05, 0.18)
    M, off = pattern([("a", ua, Fa), ("b", ub, Fb), ("c", uc, Fc)])
    a0, b0, c0 = off
    # (a's x = 0 edge: j = 0..12 at height 0.025 j; b's x = 0 edge j = 0..4 at 0.03 j; c's x = 0 edge at 0.03 j)
    M["sew"] = np.array([(a0 + 0, b0 + 0), (a0 + 12, c0 + 6), (b0 + 4, c0 + 0)])
    J, _, _, nw = join_seams(M)
    sew = J["sew"]
    U, P = J["uv"], J["piece"]
    for p in range(3):
        ids = np.where((P == p) & (np.abs(U[:, 0]) < 1e-9))[0]
        assert np.isin(ids, sew.ravel()).all(), (p, ids[~np.isin(ids, sew.ravel())])
    # (a's point at 0.12 sewn to both junction corners)
    j = np.where((P == 0) & (np.abs(U[:, 0]) < 1e-9) & (np.abs(U[:, 1] - 0.12) < 1e-9))[0]
    assert len(j) == 1
    partners = {int(b) if a == j[0] else int(a) for a, b in sew if j[0] in (a, b)}
    assert {b0 + 4, c0 + 0} <= partners


def test_cone_is_isometric_and_a_cylinder_at_zero_taper():
    u, F = grid(41, 21, 0.3, 0.15)
    M, _ = pattern([("a", u, F)])
    c = _net(M)
    pan = Panels(c)
    rng = np.random.default_rng(2)
    for _ in range(5):
        TH = rng.normal(0, 1, (pan.n, NP))
        TH[:, 7] = rng.uniform(-10, 10)
        TH[:, 8] = rng.uniform(-0.8, 0.8)
        assert ca.links_pct(c, pan.positions(TH))["max"] < 0.1
    TH[:, 8] = 0.0
    A = pan.positions(TH)
    TH[:, 8] = 2e-4
    assert np.abs(pan.positions(TH) - A).max() < 2e-3  # (the cone runs into the cylinder as its taper goes to 0)


def _sector(sb=0.4, n_r=6, n_a=41):
    """A flat annular sector that closes into a cone of sin(half-angle) sb (a cap-like piece): its two straight
    edges sewn to each other point for point."""
    A = 2 * np.pi * sb
    rr, aa = np.meshgrid(np.linspace(0.15, 0.25, n_r), np.linspace(0, A, n_a), indexing="ij")
    uv = np.c_[(rr * np.cos(aa)).ravel(), (rr * np.sin(aa)).ravel()]
    _, F = grid(n_r, n_a, 1, 1)
    M, _ = pattern([("s", uv, F)])
    M["sew"] = np.array([(i * n_a, i * n_a + n_a - 1) for i in range(n_r)])
    return M, A


def test_cone_panel_closes_a_cap_like_seam_a_cylinder_cannot():
    M, A = _sector()
    c = _net(M)
    pan = Panels(c)
    # (start: the flat wrapped round a cylinder, as a cap starts round the arm)
    r, a = np.linalg.norm(c.uv, axis=1), np.arctan2(c.uv[:, 1], c.uv[:, 0])
    R0 = 0.2 * A / (2 * np.pi)
    X0 = np.c_[R0 * np.cos(a * 2 * np.pi / A), R0 * np.sin(a * 2 * np.pi / A), r]
    TH0 = pan.fit_start(X0)
    keep = np.array([[[0, 0, 5.0], [0, 0, 6.0]]], float)
    gap0 = max(ca.seam_gaps(pan, TH0)["s ~ s"])
    TH, rd = ca.assemble(pan, TH0, keep, iters=200)
    gap = max(rd["seam_gaps_mm"]["s ~ s"])
    assert gap < 3.0 and gap < 0.2 * gap0, (gap0, gap)
    assert abs(TH[0, 8]) > 0.2, TH[0]  # (the fit chose a cone: nothing named it)


def test_mirrored_fold_rows_turn_the_same_way_about_the_body():
    u, F = grid(21, 11, 0.2, 0.1)
    um = u * [-1, 1]
    M, off = pattern([("a.L", u, F), ("a.R", um, F[:, ::-1])])  # (the mirrored flat wound the same way, as drafted)
    row = [16 * 11 + j for j in range(11)]
    M["folds"] = [{"piece": "a.L", "name": "f", "rows": [np.array(row)], "sign": 1.0},
                  {"piece": "a.R", "name": "f", "rows": [np.array(row) + off[1]], "sign": -1.0}]
    c = _net(M)
    plan = {"folds": {"f.L": {"on": "a.L", "fold": "f", "turn_deg": 90.0},
                      "f.R": {"on": "a.R", "fold": "f", "turn_deg": 90.0}}}
    pan = Panels(c, plan, out={"a.L": 1.0, "a.R": 1.0})  # (both flats' +z away from the body: the outside)
    assert len(pan.hinges) == 2
    TH0 = pan.fit_start(np.c_[c.uv, np.zeros(c.n)] + [0, 0, 0.2])
    keep = np.array([[[5, 5, 5], [5, 5, 6]]], float)
    TH, rd = ca.assemble(pan, TH0, keep)
    zs = []
    for h in pan.hinges:
        assert abs(rd["hinges"][h["name"]]["got"] - 90.0) < 3.0, rd["hinges"]
        b, t = h["base"], h["turned"]
        m = pan.place(TH[b], b, h["mid"][None])[0]
        n = pan.normal(TH[b], b, h["mid"][None])[0]  # (both flats wound the same way: +z is the same side of the cloth)
        zs.append(float((pan.place(TH[t], t, pan.panels[t]["c"][None])[0] - m) @ n))
    assert min(zs) > 0.01, zs  # (both turned OUTWARD, onto the outside: N2i, the draft's sign picks the flap only)


def test_fold_over_two_rows_reads_its_whole_turn_on_the_faces():
    """A fold drafted as two rows turns half at each: the faces read the SUM against the plan (N2e: read at half)."""
    from hifipushie.chain_lay import _fold_turns
    u, F = grid(21, 11, 0.2, 0.1)
    M, _ = pattern([("a", u, F)])
    rows = [np.array([c * 11 + j for j in range(11)]) for c in (14, 15)]
    M["folds"] = [{"piece": "a", "name": "f", "rows": rows, "sign": 1.0}]
    c = _net(M)
    plan = {"folds": {"f": {"on": "a", "fold": "f", "turn_deg": 90.0}}}
    pan = Panels(c, plan, out={"a": 1.0})
    TH0 = pan.fit_start(np.c_[c.uv, np.zeros(c.n)])
    TH, rd = ca.assemble(pan, TH0, np.array([[[5, 5, 5], [5, 5, 6]]], float))
    got = _fold_turns(c, pan.positions(TH), plan)["f"]
    assert abs(got["median"] - 90.0) < 8.0, (got, rd["hinges"])


def test_girth_piece_rolls_the_way_its_seams_say():
    """N2g: one flat cuts a pair, so a flat may show either face. Piece b's flat is drawn mirrored (its faces rewound,
    the same winding as a's): rolled the same way, the seams land on the wrong edges; _ways rolls one of them back."""
    from hifipushie import panel_start as ps
    M = _tube()
    b = M["piece"] == 1
    M["uv"] = M["uv"].copy()
    M["uv"][b, 0] = M["uv"][b, 0].max() + M["uv"][b, 0].min() - M["uv"][b, 0]
    fb = b[M["F"]].all(1)
    M["F"] = M["F"].copy()
    M["F"][fb] = M["F"][fb][:, ::-1]
    c = _net(M)
    loops = [np.c_[R * np.cos(t), R * np.sin(t), np.full_like(t, z)]
             for t in [np.linspace(0, 2 * np.pi, 33)[:-1]] for z in (0.0, 0.1, 0.2)]
    Xs = np.full((c.n, 3), np.nan)
    girth, rd = {}, {}
    for p, nm in enumerate(c.names):
        ids = np.where(c.piece == p)[0]
        Xs[ids], rd[nm] = ps._girth(c, nm, ids, loops, [], np.pi * p)
        girth[p] = (nm, ids, loops, [], np.pi * p)
    mine = c.piece == 1
    before = ps._seam_cost(c, Xs, mine)
    ps._ways(c, Xs, girth, rd)
    after = ps._seam_cost(c, Xs, mine)
    assert sorted(rd[n].get("way", 1.0) for n in "ab") == [-1.0, 1.0]  # (one of them turned: the seams are relative)
    assert after < 0.15 * before  # (2.3 -> 0.25 m summed over its sew pairs)


def test_start_inside_a_body_moved_out_by_panel_numbers_then_contact_keeps_links_exact():
    """D2: a tube started INSIDE a cylinder body (rolled at 0.75 of the body's radius) is moved out by its panels' own
    numbers (Panels.outside): every point at least the gap off, every link at its cut (a panel is isometric); then the
    sewn solve with contact on keeps every link within 2 % and no point inside."""
    from hifipushie import chain_solve as cs
    from hifipushie.chain_core import GAP
    from test_chain_solve import cylinder
    c = _net(_tube())
    body = cylinder(0.05, -0.15, 0.35, seg=96)
    X0 = _tube_start(c) * [0.75 * 0.05 / R, 0.75 * 0.05 / R, 1.0]
    pan = Panels(c)
    TH0 = pan.fit_start(X0)
    assert (body.query(pan.positions(TH0))[0] < 0).sum() > 0.5 * c.n  # (the start is inside)
    TH, left = pan.outside(TH0, body)
    X = pan.positions(TH)
    d = body.query(X)[0]
    assert not left and d.min() >= GAP - 1e-5, (left, d.min())
    assert ca.links_pct(c, X)["max"] < 0.05
    Xf, rep = cs.solve(c, X, body=body)
    assert rep["contact"]["inside"] == 0, rep["contact"]
    assert rep["links"]["worst_pct"] < 2.0, rep["links"]


def test_fused_finds_a_piece_closed_on_itself_through_others():
    """D4 (C488): a node joining two far points of one piece only through another piece is reported; a dart's own
    pair (sewn to each other) is not."""
    from hifipushie.chain_seams import fused
    uv = np.array([[0, 0], [0.2, 0], [1, 0], [0.5, 0.5], [0.52, 0.5]], float)
    M = {"uv": uv, "piece": np.array([0, 0, 1, 0, 0]), "names": ["front", "sleeve"],
         "sew": np.array([[0, 2], [1, 2], [3, 4]])}
    assert fused(M) == [("front", 0, 1, 200.0)]
    M["sew"] = np.array([[0, 2], [3, 4]])
    assert fused(M) == []
