"""Closures (closures.py): a lap held by fastenings, from one design entry. No sim.
uv run python tests/test_closures.py"""
import numpy as np

from hifipushie import closures


def _pieces():
    sq = lambda x0: np.array([[x0, 0.0], [x0 + 0.2, 0.0], [x0 + 0.2, -0.6], [x0, -0.6]])
    mk = lambda x, pre: {f"{pre}{n}": np.array([x, -0.1 * n]) for n in (1, 2, 3)}
    over = {"P": sq(0.0), "names": {"top": 0, "tr": 1, "br": 2, "bottom": 3}, "marks": mk(0.015, "buttonhole")}
    under = {"P": sq(-0.2), "names": {"tl": 0, "top": 1, "bottom": 2, "bl": 3}, "marks": mk(-0.009, "button")}
    return {"front.L": over, "front.R": under}


ENTRY = {"name": "front", "kind": "buttons", "over": "front.L", "under": "front.R",
         "edge": {"over": "bottom>top", "under": "top>bottom"}, "band": {"over": 0.03, "under": 0.018}}


def test_one_entry_makes_stitches_and_band_rows():
    st, folds, seams, out = closures.expand([ENTRY], _pieces())
    assert st == [[f"front.L:buttonhole{n}", f"front.R:button{n}"] for n in (1, 2, 3)]
    assert [f["piece"] for f in folds] == ["front.L", "front.R"] and all(f["angle"] == 180 and f["in_wrap"] for f in folds)
    assert not seams and out[0]["pairs"][0] == ("buttonhole1", "button1") and out[0]["closed"] == [True] * 3


def test_states():
    st, _, _, out = closures.expand([dict(ENTRY, state="open")], _pieces())
    assert not st and out[0]["closed"] == [False] * 3  # open: nothing sewn, the buttons still exist
    st, _, _, out = closures.expand([dict(ENTRY, state={"open_above": "buttonhole2"})], _pieces())
    assert len(st) == 2 and out[0]["closed"] == [False, True, True]  # the top button undone
    st, _, _, out = closures.expand([dict(ENTRY, state={"open_top": 1})], _pieces())
    assert len(st) == 2 and out[0]["closed"] == [False, True, True]  # the highest fastening, by its mark


def test_a_shirt_without_a_tie_is_worn_open_at_the_neck():
    # garment_kb kinds.shirt.wear: no tie (the default) -> only the collar button undone (the user on su_77: "two
    # buttons open when there should only be one"), the fronts rolled softly back to the first, closed, button
    from hifipushie import cloth, garment_design
    g = {"pattern": {"from": "simon"}}
    assert {c["name"]: c["state"] for c in garment_design.wear(g)} == {"collar": "open", "front": "closed"}
    assert all(f["line"][-1].startswith(("buttonhole1", "button1")) for f in garment_design.wear(g, "folds"))
    assert {c["name"]: c["state"] for c in garment_design.wear(dict(g, tie=True))} == {"collar": "closed", "front": "closed"}
    assert garment_design.wear({"pattern": {"from": "carlton"}}) == []  # a coat: as its pattern says
    # open as worn: the stand's ends apart at the throat, the fronts rolled back above the first closed button
    assert {c["name"]: c.get("gap") for c in garment_design.wear(g)}["collar"] > 0.05
    fl = garment_design.wear(g, "folds")
    assert {f["piece"] for f in fl} == {"front.L", "front.R"} and all(90 < f["angle"] < 180 for f in fl)
    assert garment_design.wear(dict(g, tie=True), "folds") == []
    # the UNDER front's roll ends above the first closed fastening (under the over front there): rolled out to the
    # button both flaps met there and the under one turned out through the over one (29 crossings at su_garrett's start)
    from hifipushie import pattern
    under = next(f for f in fl if f["piece"] == "front.R")
    end = under["line"][-1]
    assert "+" in end and pattern.eval_vec(end.partition("+")[2])[1] >= 0.03, end
    assert "tie" in garment_design.SHEET_KEYS
    # an unbuttoned stand is laid by the girth it would close at (its fastening's points), not by its length
    M = {"names": ["stand"], "piece": np.zeros(3, int), "uv": np.array([[0.02, 0.0], [0.40, 0.0], [0.2, 0.01]]),
         "closures": [{"name": "collar", "over": "stand", "under": "stand", "closed": [False], "v": [[0, 1]]}]}
    assert np.isclose(cloth._open_closure(M, "stand")[0], 0.38) and cloth._open_closure(M, "stand")[1] == 0.02
    M["closures"][0]["closed"] = [True]
    assert cloth._open_closure(M, "stand") == (0.0, 0.0, 0.0)  # buttoned: the stitched path


def test_a_chosen_closure_must_be_in_the_pattern():
    pcs = _pieces()
    pcs["front.R"]["marks"] = {}
    try:
        closures.expand([ENTRY], pcs)
    except closures.ClosureError as e:
        assert "no fastenings" in str(e)
    else:
        raise AssertionError("a closure with no buttons was accepted")
    try:
        closures.validate([dict(ENTRY, snaps=3)])
    except closures.ClosureError:
        pass
    else:
        raise AssertionError("unknown key accepted")
    assert closures.expand([dict(ENTRY, over="gone")], _pieces())[3] == []  # a dropped piece's closure leaves with it


def test_measure_and_buttons():
    _, _, _, out = closures.expand([ENTRY], _pieces())
    marks = {f"front.L:buttonhole{n}": n - 1 for n in (1, 2, 3)}
    marks.update({f"front.R:button{n}": n + 2 for n in (1, 2)})  # button3's vertex lost in the mesh
    M = {"closures": closures.resolve(out, marks, {}), "F": np.array([[0, 1, 2], [3, 4, 5]])}
    V = np.array([[0, 0, 0.002], [0, 0.1, 0.002], [0.1, 0, 0.002], [0, 0, 0.0], [0, 0.1, 0.02], [0.1, 0, 0]], float)
    r = closures.measure(V, M)[0]
    assert r["fastenings"] == 2 and r["lost"] == 1 and not r["ok"]  # one lost, and one 18 mm apart
    assert r["gap_mm"] == [2.0, 18.0] and "LOST" in closures.text([r])
    b = closures.buttons_mesh(V, M, None)
    assert b["V"].shape[1] == 3 and b["F"].max() < len(b["V"]) and len(set(b["at"])) == 2
    rad = np.linalg.norm(b["V"][b["at"] == 0] - V[0], axis=1).max()
    assert 0.005 < rad < 0.0075  # an 11 mm button


def test_a_zip_is_measured_along_its_seam():
    # a closed zip has no button marks: its fastenings are its seam's sewn pairs ("0 of 0 closed" before)
    zip_ = {"name": "fly", "kind": "zip", "over": "front.L", "under": "front.R", "seam": ["front.L:a>b", "front.R:a>b"],
            "pairs": [], "closed": [], "state": "closed"}
    seams = [["x:a>b", "y:a>b"], ["front.L:a>b", "front.R:a>b"]]
    sew, sew_seam = np.array([[0, 1], [2, 3], [4, 5]]), np.array([0, 1, 1])
    M = {"closures": closures.resolve([zip_], {}, {}, seams, sew, sew_seam)}
    V = np.zeros((6, 3))
    V[3, 0] = 0.002
    r = closures.measure(V, M)[0]
    assert r["fastenings"] == 2 and r["closed"] == 2 and r["ok"] and r["gap_max_mm"] == 2.0
    V[5, 0] = 0.009
    assert not closures.measure(V, M)[0]["ok"]  # gaping


def _grid(x0, x1, n=21, m=61):
    xs, ys = np.meshgrid(np.linspace(x0, x1, n), np.linspace(0, -0.6, m))
    uv = np.c_[xs.ravel(), ys.ravel()]
    i = np.arange(n * m).reshape(m, n)
    q = np.c_[i[:-1, :-1].ravel(), i[:-1, 1:].ravel(), i[1:, 1:].ravel(), i[1:, :-1].ravel()]
    return uv, np.r_[q[:, [0, 1, 2]], q[:, [0, 2, 3]]]


def test_a_closed_lap_is_laid_closed():
    """The solver leaves a lap its contact gap proud (5 mm here) and the buttons a few mm apart in the surface: seat
    lays the over band 1.2 mm off the under layer between the fastenings and brings each fastening's sides together;
    away from the band and beyond the last button the cloth stays where the sim left it."""
    pcs = _pieces()
    _, _, _, out = closures.expand([ENTRY], pcs)
    uo, Fo = _grid(0.0, 0.2)
    uu, Fu = _grid(-0.2, 0.0)
    uv = np.r_[uo, uu]
    F = np.r_[Fo, Fu + len(uo)]
    piece = np.r_[np.zeros(len(uo), int), np.ones(len(uu), int)]
    # world: x across, z down the front, y = depth (out = -y). The under front shifted 3 cm under the over front
    V = np.c_[uv[:, 0], np.zeros(len(uv)), uv[:, 1]]
    V[piece == 1, 0] += 0.03
    V[piece == 0, 1] -= 0.005
    near = lambda k, p: int(np.where(piece == k)[0][np.argmin(np.linalg.norm(uv[piece == k] - p, axis=1))])
    marks = {f"front.L:buttonhole{n}": near(0, pcs["front.L"]["marks"][f"buttonhole{n}"]) for n in (1, 2, 3)}
    marks.update({f"front.R:button{n}": near(1, pcs["front.R"]["marks"][f"button{n}"]) for n in (1, 2, 3)})
    M = {"closures": closures.resolve(out, marks, {}), "F": F, "piece": piece, "uv": uv, "names": ["front.L", "front.R"]}
    before = closures.measure(V, M)[0]
    X, rows = closures.seat(V, M, pcs, None)
    after = closures.measure(X, M)[0]
    assert before["gap_max_mm"] > 6 and after["gap_max_mm"] < 2.5 and after["ok"], (before, after)
    band = (piece == 0) & (uv[:, 0] < 0.028) & (uv[:, 1] < -0.1) & (uv[:, 1] > -0.3)
    assert np.abs(np.abs(X[band, 1]) - closures.LAY).max() < 4e-4  # the band lies 1.2 mm off the under front
    far = (piece == 0) & (uv[:, 0] > 0.12)
    below = (piece == 0) & (uv[:, 1] < -0.4)
    assert np.abs(X[far] - V[far]).max() < 1e-4 and np.abs(X[below] - V[below]).max() < 1e-4
    assert rows[0]["laid"] > 50 and rows[0]["fastenings_left_mm"] == [0.0, 0.0, 0.0]
    # fastenings apart IN the surface too (4 mm across, and the lap 3 mm under the over front at the bottom button):
    # bringing them together moves both layers round each button, so the band is laid on the under layer again after
    # (laid only before, it came out through the under front round su_garrett's 4th and 5th buttons)
    V2 = V.copy()
    V2[piece == 1, 0] -= 0.004
    V2[(piece == 1) & (uv[:, 1] < -0.25), 1] -= 0.003
    X2, rows2 = closures.seat(V2, M, pcs, None)
    band2 = band & (np.abs(uv[:, 1] - pcs["front.L"]["marks"]["buttonhole2"][1]) > 0.03)
    assert closures.measure(X2, M)[0]["ok"], closures.measure(X2, M)[0]
    under = X2[piece == 1]
    # every band vertex on one side of the under front, LAY off it: none through it (without a body seat takes the
    # under front's own normal: which side is the triangles' winding's)
    side = []
    for v in np.where(band2)[0]:
        q = under[np.argmin(np.linalg.norm(under[:, [0, 2]] - X2[v, [0, 2]], axis=1))]
        side.append(X2[v, 1] - q[1])
    side = np.asarray(side)
    assert (np.sign(side) == np.sign(np.median(side))).all() and np.abs(side).min() > 0.0005, side


def test_drafted_buttons_are_a_closure_with_a_wear_state():
    # the draft op `buttons` writes a closures entry (it wrote bare stitches: no state, no buttons, nothing measured);
    # a jacket worn open has its buttons and no stitches
    from hifipushie import cloth, pattern_draft as pd
    mm = {"neck": 370.5, "shoulderSlope": 29.0, "shoulderToShoulder": 463.9, "chest": 994.0, "waist": 776.3,
          "hips": 920.6, "seat": 972.2, "biceps": 340.2, "wrist": 148.6, "shoulderToElbow": 300.3,
          "shoulderToWrist": 570.0, "hpsToWaistBack": 545.0, "hpsToBust": 331.1, "highBust": 994.0,
          "waistToArmpit": 230.7, "waistToHips": 145.2, "waistToSeat": 245.2, "waistToFloor": 1109.3,
          "waistToKnee": 585.4, "head": 560.0, "waistToUpperLeg": 251.1, "inseam": 858.2}
    for state, n_st in (("closed", 2), ("open", 0), ({"open_above": "button2"}, 1)):
        ops = [{"op": "style_line", "piece": "front", "name": "pf", "from": {"edge": "hps>shoulder", "t": 0.5},
                "to": {"edge": "hem>cfHem", "t": 0.45}, "via": ["bust"], "names": ["front", "side_front"]},
               {"op": "lapel", "break_y": 0.4}, {"op": "buttons", "piece": "front", "n": 2, "state": state, "size": 0.02}]
        blk = pd.build(mm, {"block": "bodice", "block_options": {"fitted": True}, "ops": ops})
        cl = blk["closures"]
        assert len(cl) == 1 and cl[0]["over"] == "front.L" and cl[0]["under"] == "front.R" and cl[0]["state"] == state
        assert not any("button" in a for a, b in blk["stitches"])
        st, _, _, out = closures.expand(cl, blk["pieces"])
        assert len(st) == n_st and len(out[0]["pairs"]) == 2 and out[0]["size"] == 0.02, (state, st)
        Bp = cloth.pieces({"pattern": {"from": "draft", "block": "bodice", "block_options": {"fitted": True}, "ops": ops}}, mm)
        assert Bp["closures"] and Bp["closures"][0]["state"] == state
        assert sum("button" in a for a, b in Bp["stitches"]) == n_st


def _placket(finish=None):
    """Two rectangular fronts lapped by a buttoned closure, meshed (cloth.pieces / cloth.mesh): the over front's edge
    on x = -0.1 with its holes 15 mm in, the under front's on x = 0.1 with its buttons 9 mm in."""
    from hifipushie import cloth
    ys = (0.2, 0.0, -0.2)
    c = dict(ENTRY, edge={"over": "nw>w>sw", "under": "se>e>ne"}, **({"finish": finish} if finish else {}))
    g = {"pieces": {"front.L": {"rect": [0.2, 0.6], "wrap": {"to": "flat", "at": [0, 0, 1.0]},
                                "marks": {f"buttonhole{n + 1}": [-0.085, y] for n, y in enumerate(ys)}},
                    "front.R": {"rect": [0.2, 0.6], "wrap": {"to": "flat", "at": [0, 0, 1.0]},
                                "marks": {f"button{n + 1}": [0.091, y] for n, y in enumerate(ys)}}},
         "seams": [], "closures": [c]}
    Bp = cloth.pieces(g, {})
    M = cloth.mesh(Bp, 0.01)
    return g, Bp, M


def test_a_box_placket_in_the_maps():
    """The user on the shirt (2026-10-08): "We're really not getting the shirt placket right": no band, rivets for
    buttons, no buttonholes. The over front's band is drawn as a box placket: proud, a crisp fold at its inner edge,
    a topstitch row 3 mm in from each edge, vertical buttonholes (a slit between satin beads, size + 3 mm long, along
    the band) on its centre line; the free edge's turned hem is not drawn inside the band."""
    from hifipushie import cloth
    g, Bp, M = _placket()
    c = next(c for c in M["closures"] if c["name"] == "front")
    assert set(c["edge_xy"]) == {"over", "under"} and c["finish"] == {"over": "box", "under": "french"}
    T = 2048
    uv, side = cloth.atlas_uv(M)
    dm = cloth.detail_maps(M, uv, side, dict(g, detail={"texture": T}))
    H, thr, cav = dm["height"], dm["thread"], dm["cavity"]
    mpt = side / T
    k = M["names"].index("front.L")
    vs = np.where(M["piece"] == k)[0]
    off = uv[vs[0]] * side - M["uv"][vs[0]]
    pix = lambda x, y: (int(round((x + off[0]) / side * T)), int(round((1 - (y + off[1]) / side) * T)))
    row = lambda y, xs: np.array([H[pix(x, y)[1], pix(x, y)[0]] for x in xs])
    # across the band at y = 0.1 (between buttons): proud inside, a crisp fall at the inner edge (x = -0.07)
    xs = np.arange(-0.099, -0.05, mpt)
    h = row(0.1, xs)
    inside_, outside_ = h[(xs > -0.094) & (xs < -0.076)], h[xs > -0.065]
    assert np.median(inside_) > np.median(outside_) + 0.0004, (np.median(inside_), np.median(outside_))
    fall = np.diff(h[(xs > -0.075) & (xs < -0.066)])
    assert -fall.min() / mpt > 0.25  # steeper than 1 in 4 within a texel or two: a fold, not a slope
    # two rows of stitching, 3 mm in from each edge of the band
    t_ = np.array([thr[pix(x, 0.1)[1], pix(x, 0.1)[0]] for x in xs])
    for at in (-0.097, -0.073):
        near = np.abs(xs - at) < 0.0008
        assert t_[near].max() > 0.5, at
    assert t_[(xs > -0.092) & (xs < -0.078)].max() < 0.1  # (not the old turned hem's row 6 mm in)
    # the buttonhole at (-0.085, 0): a dark slit along y, about 14 mm long
    hx, hy = pix(-0.085, 0.0)
    col = cav[hy - int(0.012 / mpt): hy + int(0.012 / mpt), hx]
    slit_len = (col < 0.75).sum() * mpt
    assert 0.009 < slit_len < 0.0135, slit_len
    across = cav[hy, hx - int(0.006 / mpt): hx + int(0.006 / mpt)]
    assert (across < 0.75).sum() * mpt < 0.0012  # a slit, not a slot
    # a French front (the under side) has no rows
    k2 = M["names"].index("front.R")
    vs2 = np.where(M["piece"] == k2)[0]
    off2 = uv[vs2[0]] * side - M["uv"][vs2[0]]
    pix2 = lambda x, y: (int(round((x + off2[0]) / side * T)), int(round((1 - (y + off2[1]) / side) * T)))
    t2 = np.array([thr[pix2(x, 0.1)[1], pix2(x, 0.1)[0]] for x in np.arange(0.075, 0.099, mpt)])
    assert t2.max() < 0.1


def test_flat_sew_through_buttons():
    """Buttons are flat 4-hole discs (a dome on a rim read as a rivet): `size` across, ~2 mm thick, sitting on the
    cloth at the closed buttonhole, their holes squared with the band (along it)."""
    g, Bp, M = _placket()
    V = np.c_[M["uv"][:, 0], np.zeros(len(M["uv"])), M["uv"][:, 1]]  # flat, facing -y
    k = M["names"].index("front.R")
    V[M["piece"] == k, 1] += 0.001  # the under front behind
    b = closures.buttons_mesh(V, M, None)
    assert len(set(b["at"])) == 3 and set(b["mark"]) != set(b["at"])
    c = next(c for c in M["closures"] if c["name"] == "front")
    for va, _vb in c["v"]:
        P = b["V"][b["at"] == va]
        d = P - V[va]
        h = np.abs(d[:, 1])
        assert h.max() < 0.0025 and np.ptp(d[:, 1]) < 0.0025  # flat, ~2 mm
        r = np.hypot(d[:, 0], d[:, 2]).max()
        assert abs(r - 0.0055) < 3e-4
    # the thread's bars (the vertices standing highest) run along the band: z
    P = b["V"][b["at"] == c["v"][0][0]]
    top = P[np.abs(P[:, 1] - V[c["v"][0][0], 1]) > np.abs(P[:, 1] - V[c["v"][0][0], 1]).max() - 2e-4]
    assert np.ptp(top[:, 2]) > np.ptp(top[:, 0])
    assert abs(closures.hole_axis(c, M, *c["v"][0]) @ np.array([0, 1.0])) > 0.99  # along the edge


def test_a_box_band_is_a_crisp_step_in_the_mesh():
    """The coordinator on su_77: at outfit distance the placket "doesn't read at all". A box band in the MESH: a row
    split in 1.5 mm outside its inner fold (vertices appended: old ids keep their meaning), the band pressed flat
    across (a solver's lap sank 3-4 mm between its edges) and standing proud, so the step is 1.5 mm wide."""
    g, Bp, M = _placket()
    pcs = Bp["pieces"]
    nV, nF = len(M["uv"]), len(M["F"])
    k = M["names"].index("front.L")
    uv = M["uv"].copy()
    V = np.c_[uv[:, 0], np.zeros(nV), uv[:, 1]]
    V[M["piece"] != k, 1] += 0.004  # the under front behind (+y = in)
    band = (M["piece"] == k) & (uv[:, 0] > -0.095) & (uv[:, 0] < -0.075)
    V[band, 1] += 0.003  # the sim's lap sunk 3 mm between the band's edges
    old = V.copy()
    sp = closures.split_band_edges(M, pcs)
    assert sp is not None and len(M["uv"]) == nV + len(sp["t"]) and len(M["F"]) > nF
    V = closures.extend(V, sp)
    assert np.allclose(V[:nV], old) and M["F"].max() == len(V) - 1
    new = M["uv"][nV:]
    assert np.allclose(new[:, 0], -0.1 + 0.03 + closures.EDGE_ROW, atol=2e-4)  # the row 1.5 mm outside the fold
    # no face folded: every triangle keeps its winding in the pattern
    P = M["uv"][M["F"]]
    e1, e2 = P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]
    area = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    assert (np.sign(area) == np.sign(np.median(area))).all()
    X = closures.relief(V, M, pcs, None)
    sel = np.where((M["piece"] == k) & (np.abs(M["uv"][:, 1] - 0.1) < 0.02))[0]
    out_ = -X[sel, 1]  # (out = -y)
    xs = M["uv"][sel, 0]
    inb, row, past = (xs > -0.095) & (xs < -0.072), np.abs(xs + 0.07) < 3e-4, np.abs(xs + 0.0685) < 3e-4
    assert np.ptp(out_[inb]) < 0.0012  # flat across (was a 3 mm groove)
    assert out_[row].mean() - out_[past].mean() > 0.0008  # a step of ~1 mm over 1.5 mm


def test_a_cuffs_holes_run_along_the_cuff():
    # a piece closed on itself: no edge, the hole's axis from the button toward the buttonhole
    M = {"uv": np.array([[0.0, 0.0], [0.2, 0.0]]), "piece": np.array([0, 0])}
    c = {"name": "cuff", "over": "cuff", "under": "cuff", "hole": "auto"}
    assert abs(closures.hole_axis(c, M, 1, 0) @ np.array([1.0, 0])) > 0.99
    assert abs(closures.hole_axis(dict(c, hole="across"), M, 1, 0) @ np.array([0, 1.0])) > 0.99
    try:
        closures.validate([dict(ENTRY, finish="lumpy")])
    except closures.ClosureError:
        pass
    else:
        raise AssertionError("unknown finish accepted")


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v()
            print("ok", k)
