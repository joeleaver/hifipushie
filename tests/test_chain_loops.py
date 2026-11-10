"""F1 (after blind trial t8): the chain build without collar-band assumptions, on small synthetic patterns and a lathe
body: a waistband on the waist loop by its own edge names (no Simon point names), a belt (a strap sewn to nothing) and
one too short refused by name, a stand that must stay upright with its whole top edge found (taller ends than CB), a
held stiff edge link past its cut counted, a half garment and a sideless limb piece refused by name."""
import numpy as np
import pytest

from hifipushie import chain_garment as cg, chain_loops as cl, chain_net as cn, chain_roles as cr


def _lathe():
    """A round body: torso r 0.15 (waist 0.13 at z 1.10), shoulders to z 1.45, a neck r 0.06 to z 1.62; capped."""
    zs = np.r_[np.linspace(0.80, 1.44, 33), np.linspace(1.46, 1.62, 9)]
    r = np.where(zs < 1.445, 0.15 - 0.02 * np.exp(-((zs - 1.10) / 0.08) ** 2), 0.06)
    na = 48
    th = np.linspace(0, 2 * np.pi, na, endpoint=False)
    V = np.concatenate([np.c_[rr * np.sin(th), -rr * np.cos(th), np.full(na, z)] for z, rr in zip(zs, r)])
    F = []
    for i in range(len(zs) - 1):
        for j in range(na):
            a, b, c, d = i * na + j, i * na + (j + 1) % na, (i + 1) * na + j, (i + 1) * na + (j + 1) % na
            F += [[a, b, d], [a, d, c]]
    V = np.r_[V, [[0, 0, zs[0]], [0, 0, zs[-1]]]]
    lo, hi = len(V) - 2, len(V) - 1
    top = (len(zs) - 1) * na
    F += [[lo, (j + 1) % na, j] for j in range(na)] + [[hi, top + j, top + (j + 1) % na] for j in range(na)]
    at = {"hps.L": [0.06, 0.0, 1.45], "cf_neck": [0.0, -0.06, 1.44], "cb_neck": [0.0, 0.06, 1.46],
          "shoulder.L": [0.18, 0.0, 1.43], "armpit_z": 1.30, "chest_z": 1.28, "waist_z": 1.10, "hips_z": 0.95,
          "crotch_z": 0.82, "neck_side.L": [0.06, 0.0, 1.47]}
    return cg.Body(V, np.array(F), at)


def _grid(x0, x1, y0, y1, nx, ny, k0):
    xs, ys = np.linspace(x0, x1, nx), np.linspace(y0, y1, ny)
    uv = np.array([[x, y] for y in ys for x in xs])
    F = [[k0 + j * nx + i, k0 + j * nx + i + 1, k0 + (j + 1) * nx + i + 1] for j in range(ny - 1) for i in range(nx - 1)]
    F += [[k0 + j * nx + i, k0 + (j + 1) * nx + i + 1, k0 + (j + 1) * nx + i] for j in range(ny - 1) for i in range(nx - 1)]
    return uv, F


def _pattern(pieces: dict, stiff=(), roles=None, closures=(), sew_rows=()):
    """pieces {name: (x0, x1, y0, y1, nx, ny)}; sew_rows: (piece a, its row a, piece b, its row b) sewn column by
    column (row index from the bottom, -1 = top); closures: (piece, (col a, row), (col b, row))."""
    uvs, Fs, ps, off, dims = [], [], [], {}, {}
    k = 0
    for i, (nm, (x0, x1, y0, y1, nx, ny)) in enumerate(pieces.items()):
        uv, F = _grid(x0, x1, y0, y1, nx, ny, k)
        uvs.append(uv), Fs.append(F), ps.append(np.full(len(uv), i))
        off[nm], dims[nm] = k, (nx, ny)
        k += len(uv)
    vid = lambda nm, c, r: off[nm] + (r % dims[nm][1]) * dims[nm][0] + c
    sew = []
    for a, ra, b_, rb in sew_rows:
        na_, nb_ = dims[a][0], dims[b_][0]
        for c in range(min(na_, nb_)):
            sew.append([vid(a, c, ra), vid(b_, c, rb)])
    M = {"uv": np.concatenate(uvs), "F": np.array(sum(Fs, [])), "piece": np.concatenate(ps), "names": list(pieces),
         "sew": np.array(sew, np.int64).reshape(-1, 2), "folds": [], "closures": []}
    for nm, ca, cb in closures:
        M["closures"].append({"name": nm + "_cl", "kind": "buttons", "over": nm, "under": nm, "state": "closed",
                              "v": [[vid(nm, *ca), vid(nm, *cb)]], "closed": [True]})
    border = np.zeros(len(M["uv"]), bool)
    for nm, (nx, ny) in dims.items():
        for r in range(ny):
            for c in range(nx):
                if r in (0, ny - 1) or c in (0, nx - 1):
                    border[vid(nm, c, r)] = True
    M["border"] = border
    if roles:
        M["roles"] = roles
    st = np.zeros(len(M["uv"]))
    for nm in stiff:
        st[M["piece"] == list(pieces).index(nm)] = 1.0
    return cg.Pattern(M, st, np.ones(len(st))), vid


def test_half_and_sideless_pieces_are_refused_by_name():
    pat, _ = _pattern({"front": (-0.25, 0.02, -0.3, 0.0, 5, 3), "back": (-0.25, 0.25, -0.3, 0.0, 5, 3),
                       "sleeve": (-0.1, 0.1, -0.4, 0.0, 5, 3)}, sew_rows=[("sleeve", 0, "sleeve", -1)])
    net = cn.Network(pat.M, pat.stiff, pat.bend)
    with pytest.raises(cg.ChainRefused) as e:
        cg.read_roles(net)
    msg = str(e.value)
    assert "front: half a garment" in msg and "sleeve: a limb piece with no side" in msg and "back" not in msg.split("next")[0]
    assert "front.L and front.R" not in msg and 'pieces.NAME {"pair": true}' in msg  # (F3: the pair declaration)


def _trousers(band_x=0.40, band_len=None):
    """A centred skirt-like body piece and a waistband with its own edge names only (no Simon points), its closure
    marks at its two ends: closed length 2 x band_x."""
    W = 0.45 if band_len is None else band_len
    return _pattern({"body": (-0.45, 0.45, -0.70, -0.35, 19, 5), "waistband": (-W, W, -0.35, -0.31, 19, 3)},
                    stiff=["waistband"], closures=[("waistband", (0, 0), (18, 0))],
                    sew_rows=[("waistband", 0, "body", -1)])


def test_a_waistband_is_a_band_on_the_waist_loop_at_its_seam():
    body = _lathe()
    pat, vid = _trousers()
    b = cg.GarmentBuild(pat, body, {"state": "closed"}, log=lambda *_: None)
    assert b.roles.rings == ["waistband"] and b.roles.band is None
    b.stiff_rest()  # (no band: nothing on the neck, never self.sb; C396: the one stiff sequence, rings in it)
    rd = b.reads["rings"]["waistband"]
    assert rd["body_loop"] == "its seam's height" and abs(rd["z_mm"] - 1100) < 1  # (hps z + the body piece's top y)
    X = b.X[b.net.verts("waistband")]
    assert rd["min_gap_mm"] >= 2.0
    per = np.linalg.norm(np.diff(X[:19][:, :2], axis=0), axis=1).sum()  # bottom row: its closed length round the loop
    assert abs(per - 0.9) < 0.02
    assert X[19:, 2].mean() > X[:19, 2].mean() + 0.015  # its free edge above its seam


def test_a_belt_sewn_to_nothing_sits_where_the_torso_takes_its_length_and_a_short_one_is_refused():
    body = _lathe()
    pat, _ = _pattern({"strap": (-0.47, 0.47, 0.0, 0.035, 25, 3)}, stiff=["strap"], closures=[("strap", (1, 1), (23, 1))])
    b = cg.GarmentBuild(pat, body, {"state": "closed"}, log=lambda *_: None)
    assert b.roles.rings == ["strap"] and not b.roles.panels
    b.stiff_rest()  # (C396: stiff_stage + rings are the one stiff sequence)
    rd = b.reads["rings"]["strap"]
    assert "nearest the waist" in rd["body_loop"] and abs(rd["z_mm"] - 1100) < 40 and rd["min_gap_mm"] > 2.0
    short, _ = _pattern({"strap": (-0.3, 0.3, 0.0, 0.035, 25, 3)}, stiff=["strap"], closures=[("strap", (1, 1), (23, 1))])
    b2 = cg.GarmentBuild(short, body, {"state": "closed"}, log=lambda *_: None)
    with pytest.raises(cg.ChainRefused, match="shorter than the torso"):
        b2.rings()


def test_a_ring_with_no_closure_is_refused_by_name():
    body = _lathe()
    pat, _ = _pattern({"strap": (-0.47, 0.47, 0.0, 0.035, 25, 3)}, stiff=["strap"])
    b = cg.GarmentBuild(pat, body, {"state": "closed"}, log=lambda *_: None)
    with pytest.raises(cg.ChainRefused, match="no closure of its own"):
        b.rings()


def _stand_flat():
    """A stand 0.44 m long on its neck edge (y 0), its top TALLER at the ends (60 mm) than at CB (40 mm)."""
    pat, vid = _pattern({"body": (-0.22, 0.22, -0.3, 0.0, 23, 5), "collar": (-0.22, 0.22, 0.0, 0.04, 23, 5)},
                        stiff=["collar"], roles={"collar": "collar_stand"}, sew_rows=[("collar", 0, "body", -1)])
    uv = pat.M["uv"]
    k = pat.M["piece"] == 1
    x = uv[k, 0]
    uv[k, 1] = uv[k, 1] * (1 + 0.5 * (x / 0.22) ** 2)  # (ends 60 mm, CB 40 mm)
    return pat, vid


def test_the_stand_top_edge_is_its_whole_top_not_its_tallest_ear():
    pat, vid = _stand_flat()
    net = cn.Network(pat.M, pat.stiff, pat.bend)
    sb = np.array([vid("collar", c, 0) for c in range(23)])
    st = cr._top_edge(net, "collar", sb)
    assert len(st) >= 21 and np.ptp(net.uv[st, 0]) > 0.38  # (was: the vertices near the farthest ear only)
    assert all(np.diff(net.uv[st, 0]) > 0)


def test_a_stand_stays_upright_by_its_own_height_and_keeps_its_top():
    body = _lathe()
    pat, _ = _stand_flat()
    b = cg.GarmentBuild(pat, body, {"state": "closed"}, log=lambda *_: None)
    assert b.roles.stand and b.roles.band == "collar"
    cr.stand_ring(b)
    s = b.reads["stand"]
    assert s["rise_deg_min"] >= 60 - 3 and s["rise_deg_cb"] >= 60  # (UPRIGHT_LEAN 30: was a 12 mm floor)
    assert s["top_worst_link_pct"] < 5 and b.reads["band"]["min_gap_mm"] > 0, (s, b.reads["band"])
    assert abs(s["top_mm"][0] - s["top_mm"][1]) < 5


def test_a_held_stiff_edge_past_its_cut_is_counted():
    body = _lathe()
    pat, _ = _trousers()
    b = cg.GarmentBuild(pat, body, {"state": "closed"}, log=lambda *_: None)
    b.stiff_rest()  # (C396: stiff_stage + rings are the one stiff sequence)
    net = b.net
    bv = net.verts("body")  # (the soft cloth hung straight down from the band, every free link at its cut)
    top = bv[net.uv[bv, 1] > net.uv[bv, 1].max() - 1e-6]
    for q in bv:
        t = top[np.argmin(np.abs(net.uv[top, 0] - net.uv[q, 0]))]
        b.X[q] = b.X[net.root[t]] + [0.0, 0.0, net.uv[q, 1] - net.uv[t, 1]]
    b._sync()
    rep = b.chain_read(b.X)
    assert rep["held_worst_pct"] < 5 and rep["free_worst_pct"] < 2  # (as built: round the loop at its cut)
    v = net.verts("waistband")
    v = v[net.uv[v, 1] > net.uv[v, 1].max() - 1e-6]  # (its free top edge: sewn to nothing, so no free link moves)
    X = b.X.copy()
    X[v] = X[v] * [1.6, 1.6, 1.0]  # (the top edge stretched: both ends of every link still held)
    rep = b.chain_read(X)
    assert rep["held_worst_pct"] > 50 and "waistband" in rep["held_worst_line"] and "stiff piece's own" in rep["held_worst_line"]
    b.X = X
    with pytest.raises(cg.ChainRefused, match="held length can't hold"):
        b.gate_lengths()


def test_a_stands_end_edges_are_in_its_solve_and_hold_their_cut():
    """(F3) The hussar r2 stand was refused 39.8 % over its cut at a top corner: its END edges were filled after the
    solve. Now each end edge is a chain neck end -> top end at its cut, solved with the ring and kept by fill_band."""
    body = _lathe()
    pat, _ = _stand_flat()
    b = cg.GarmentBuild(pat, body, {"state": "closed"}, log=lambda *_: None)
    cr.stand_ring(b)
    s = b.reads["stand"]
    assert len(s["end_edges_mm"]) == 2 and len(b.se) >= 4  # (5 rows: 3 inner points up each end)
    for got, cut in s["end_edges_mm"]:
        assert abs(got - cut) < 0.05 * cut, s
    assert s["end_worst_link_pct"] < 5, s
    keep = b.X[b.net.root[b.se]].copy()
    b.fill_band()
    assert np.allclose(b.X[b.net.root[b.se]], keep)


def test_a_bands_lap_past_its_marks_keeps_every_length():
    """F8 C325: the part of a band past its closure's marks lies a LAYER out at its own cut lengths (the trousers'
    waistband read 13 % over the step and ~3 % along the lap when the loop's points were pushed out radially)."""
    body = _lathe()
    pat, _ = _pattern({"strap": (-0.55, 0.55, 0.0, 0.035, 29, 3)}, stiff=["strap"], closures=[("strap", (2, 1), (26, 1))])
    b = cg.GarmentBuild(pat, body, {"state": "closed"}, log=lambda *_: None)
    b.stiff_rest()  # (C396: stiff_stage + rings are the one stiff sequence)
    net = b.net
    v = net.verts("strap")
    k = np.isin(net.edges[:, 0], v) & np.isin(net.edges[:, 1], v)
    E, L0 = net.edges[k], net.flat[k]
    st = (np.linalg.norm(b.X[E[:, 0]] - b.X[E[:, 1]], axis=1) / L0 - 1) * 100
    assert st.max() < 0.5, st.max()
    assert np.percentile(st, 5) > -2.0, np.percentile(st, 5)
