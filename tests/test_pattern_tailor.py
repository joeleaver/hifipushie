"""Tailoring operations (pattern_tailor: contour, join, round_corner, fisheye; the lapel's straight gorge): each keeps
the draft's invariant (every seam's sides equal or its ease declared), named edges still run, and the draft unfolds.
Run: uv run python tests/test_pattern_tailor.py"""
import numpy as np

from hifipushie import pattern, pattern_draft as pd

MM = {"neck": 370.5, "shoulderSlope": 29.0, "shoulderToShoulder": 463.9, "chest": 994.0, "waist": 776.3, "hips": 920.6,
      "seat": 972.2, "biceps": 340.2, "wrist": 148.6, "shoulderToElbow": 300.3, "shoulderToWrist": 570.0,
      "hpsToWaistBack": 545.0, "hpsToBust": 331.1, "highBust": 994.0, "waistToArmpit": 230.7, "waistToHips": 145.2,
      "waistToSeat": 245.2, "waistToFloor": 1109.3, "waistToKnee": 585.4, "head": 560.0, "waistToUpperLeg": 251.1,
      "inseam": 858.2}


def _ok(D):
    bad = [t for ok, t in pd.consistency(D) if not ok]
    assert not bad, bad


def _width(pc, y):
    from hifipushie.cloth import _piece_xs_at
    xs = _piece_xs_at(pc["P"], y)
    return max(xs) - min(xs)


def test_contour_shapes_a_centre_back_seam():
    D = pd.start("bodice", MM, {"fitted": True, "cb": "seam"})
    wy = D["meta"]["waist_y"]
    w0 = _width(D["pieces"]["back"], wy)
    hem0 = pd.edge_length(D, D["edges"]["hem_back"])
    pd.apply(D, [{"op": "contour", "edge": "centre_back", "at": [["top", 0], ["chest", 0.004], ["waist", 0.02], ["hem", 0.012]]}])
    b = D["pieces"]["back"]
    assert abs(_width(b, wy) - (w0 - 0.02)) < 1e-3  # 20 mm out of the half back at the waist
    assert abs(b["P"][b["names"]["cbNeck"], 0]) < 1e-9  # the top stays on the centre line
    assert abs(pd.edge_length(D, D["edges"]["hem_back"]) - (hem0 - 0.012)) < 1e-3
    _ok(D)
    pd.unfold(D)
    _ok(D)
    # the two backs are sewn along the shaped edge (equal: mirror images)
    assert any("back.L:cbNeck" in str(s) and "back.R:cbNeck" in str(s) for s in D["seams"])
    # a side seam shaped on both pieces alike stays matched
    S = pd.start("bodice", MM, {})
    pd.apply(S, [{"op": "contour", "edge": ["front:armhole>hem", "back:armhole>hem"], "at": [["waist", 0.015], ["hem", -0.01]]}])
    _ok(S)


def test_join_makes_a_side_panel_without_a_side_seam():
    D = pd.start("bodice", MM, {"cb": "seam"})
    ops = [{"op": "style_line", "piece": "front", "name": "sideF", "from": {"edge": "armhole>armholePitch", "t": 0.45},
            "to": {"edge": "hem>cfHem", "t": 0.30}, "names": ["front", "side_front"]},
           {"op": "style_line", "piece": "back", "name": "sideB", "from": {"edge": "armhole>armholePitch", "t": 0.45},
            "to": {"edge": "hem>cbHem", "t": 0.30}, "names": ["back", "side_back"]}]
    pd.apply(D, ops)
    area = lambda P: 0.5 * abs(np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1]))
    a0 = area(D["pieces"]["side_front"]["P"]) + area(D["pieces"]["side_back"]["P"])
    ah = pd.edge_length(D, D["edges"]["armhole_front"]) + pd.edge_length(D, D["edges"]["armhole_back"])
    hem = pd.edge_length(D, D["edges"]["hem_front"]) + pd.edge_length(D, D["edges"]["hem_back"])
    n_seams = len(D["seams"])
    pd.apply(D, [{"op": "join", "a": "side_front", "b": "side_back", "name": "side"}])
    assert "side" in D["pieces"] and "side_back" not in D["pieces"] and "side_front" not in D["pieces"]
    assert len(D["seams"]) == n_seams - 1  # the side seam is gone
    assert abs(area(D["pieces"]["side"]["P"]) - a0) < 0.02 * a0  # the same cloth (a straight side seam loses nothing)
    # the armhole and the hem still run, over the joined piece
    assert abs(pd.edge_length(D, D["edges"]["armhole_front"]) + pd.edge_length(D, D["edges"]["armhole_back"]) - ah) < 2e-3
    assert abs(pd.edge_length(D, D["edges"]["hem_front"]) + pd.edge_length(D, D["edges"]["hem_back"]) - hem) < 2e-3
    _ok(D)
    # both panel seams now end on the one side panel, and a sleeve still drafts into the armhole
    assert sum("side:" in str(s) for s in D["seams"]) == 2
    pd.apply(D, [{"op": "take_in", "line": "sideF", "amount": 0.02}, {"op": "take_in", "line": "sideB", "amount": 0.03},
                 {"op": "sleeve"}])
    _ok(D)
    pd.unfold(D)
    _ok(D)
    assert {"side.L", "side.R"} <= set(D["pieces"])
    # a shaped side seam: joining says what was lost
    F = pd.start("bodice", MM, {"fitted": True})
    pd.apply(F, [{"op": "join", "a": "front", "b": "back", "along": "armhole"}])
    assert F["meta"]["joined"]["front"]["lost"] > 0.01 and any("shaping is lost" in t for t in F["log"])


def test_round_corner_keeps_the_edges_named():
    D = pd.start("bodice", MM, {})
    f = D["pieces"]["front"]
    c = f["P"][f["names"]["cfHem"]].copy()
    hem0 = pd.edge_length(D, D["edges"]["hem_front"])
    pd.apply(D, [{"op": "round_corner", "piece": "front", "corner": "cfHem", "along": [0.10, 0.07]}])
    f = D["pieces"]["front"]
    assert 0.015 < np.linalg.norm(f["P"][f["names"]["cfHem"]] - c) < 0.06  # the corner is cut away
    assert pd.edge_length(D, D["edges"]["hem_front"]) < hem0  # hem + curve to its middle: shorter than the square corner
    assert pd.edge_length(D, D["edges"]["cfHem_round"]) > 0.11
    _ok(D)
    pd.apply(D, [{"op": "facing", "piece": "front", "edges": ["centre_front"], "width": 0.06}])
    _ok(D)


def test_fisheye_darts_on_a_hip_length_block():
    D = pd.start("bodice", MM, {"fitted": True, "darts": True})  # to the hips: the waist darts are fish-eyes
    for nm in ("front", "back"):
        pc = D["pieces"][nm]
        assert "waistDart" in pc["fisheyes"]
        a, t, b = (pc["P"][pc["names"][k]] for k in pc["fisheyes"]["waistDart"])
        wy = D["meta"]["waist_y"]
        assert t[1] > wy + 0.1 and abs(a[1] - pc["P"][:, 1].min()) < 0.03  # tip above the waist, feet on the hem
        am, bm = pc["P"][pc["names"]["waistDartAm"]], pc["P"][pc["names"]["waistDartBm"]]
        assert abs(abs(am[0] - bm[0]) - D["meta"]["waist_dart"]) < 1e-4 and abs(am[1] - wy) < 1e-6
        assert abs(np.linalg.norm(a - b) - 0.003) < 1e-3  # a closed cut below the dart
    _ok(D)
    # the hem edge still runs (in two parts either side of the dart), and the draft unfolds and meshes
    assert len(D["edges"]["hem_front"]) == 2
    pd.unfold(D)
    _ok(D)
    N = pd.start("bodice", MM, {"fitted": True})
    assert "fisheyes" not in N["pieces"]["front"]


def test_straight_gorge():
    D = pd.start("bodice", MM, {"fitted": True})
    pd.apply(D, [{"op": "lapel", "break_y": 0.42, "stand": 0.025, "width": 0.085, "gorge": "straight", "gorge_drop": 0.09,
                  "notch": 0.035},
                 {"op": "collar", "type": "roll", "stop": 0.0, "height": 0.07}])
    f = D["pieces"]["front"]
    ix = pattern.arc_indices(f, "hps>cfNeck")
    L = f["P"][ix]
    d = (L[-1] - L[0]) / np.linalg.norm(L[-1] - L[0])
    off = np.abs((L - L[0]) @ np.array([-d[1], d[0]]))
    assert off.max() < 1e-6  # the front neck is one straight line
    lp = f["P"][f["names"]["lapelPoint"]]
    assert abs(np.linalg.norm(lp - L[-1]) - 0.035) < 1e-6 and abs((lp - L[0]) @ np.array([-d[1], d[0]])) < 1e-6
    assert abs((f["P"][f["names"]["hps"], 1] - lp[1]) - 0.09) < 1e-6
    _ok(D)


def test_pockets_are_laid_on_and_tacked():
    D = pd.start("bodice", MM, {"cf": "fold", "chest_ease": 0.18})
    pd.apply(D, [{"op": "pocket", "piece": "front", "type": "kangaroo", "width": 0.34, "height": 0.18}])
    p = D["pieces"]["pocket"]
    assert p["wrap"]["lies_on"] == "front" and p["wrap"]["face"] == "out" and p["role"] == "pocket"
    n = len(D["sym_stitches"])
    assert n >= 8
    pd.unfold(D)
    _ok(D)
    # cut on the fold like its front: one piece, its tacks on both sides (those on the fold once)
    assert "pocket" in D["pieces"] and n < len(D["stitches"]) <= 2 * n
    marks = D["pieces"]["front"]["marks"]
    for a, b in D["stitches"]:
        assert a.split(":")[0] == "pocket" and b.split(":", 1)[1] in marks, (a, b)
    # a patch pocket on a paired front: one per side, each lying on its own front
    D = pd.start("bodice", MM, {})
    pd.apply(D, [{"op": "pocket", "piece": "front", "type": "patch", "at": [0.13, -0.52], "width": 0.13, "height": 0.14}])
    pd.unfold(D)
    assert D["pieces"]["pocket.R"]["wrap"]["lies_on"] == "front.R"
    assert all(a.split(":")[0][-2:] == b.split(":")[0][-2:] for a, b in D["stitches"])
    try:
        pd.apply(pd.start("bodice", MM, {}), [{"op": "pocket", "piece": "front", "type": "patch", "at": [0.5, -0.6]}])
    except pd.DraftError as e:
        assert "doesn't lie inside" in str(e)
    else:
        raise AssertionError("a pocket off its piece must be refused")


def test_welt_flap_and_in_seam_pockets():
    D = pd.start("bodice", MM, {})
    pd.apply(D, [{"op": "pocket", "piece": "front", "type": "welt", "at": [0.13, -0.56], "width": 0.13, "name": "welt"},
                 {"op": "pocket", "piece": "front", "type": "flap", "at": [0.13, -0.60], "width": 0.14, "name": "flap"}])
    w, f = D["pieces"]["welt"], D["pieces"]["flap"]
    assert np.ptp(w["P"][:, 1]) <= 0.0121 and "welt" in D["interfaced"] and w["wrap"]["face"] == "out"
    n_w = sum(1 for a, b in D["sym_stitches"] if a.startswith("welt:"))
    n_f = sum(1 for a, b in D["sym_stitches"] if a.startswith("flap:"))
    assert n_w >= 8 and 3 <= n_f <= 6  # the welt sewn all round, the flap along its top only
    tops = [f["P"][f["names"][a.split(":")[1]], 1] for a, b in D["sym_stitches"] if a.startswith("flap:")]
    assert np.ptp(tops) < 1e-9 and abs(tops[0] - f["P"][:, 1].max()) < 1e-9
    _ok(D)
    # in the side seam of a yoked skirt: the seam (a chain) is left open, two bags sewn to its lips and each other
    S = pd.start("skirt", MM, {"length": 0.56, "darts": False})
    pd.apply(S, [{"op": "style_line", "piece": "front", "name": "yokeF", "from": {"edge": "cWaist>cHem", "dist": 0.10},
                  "to": {"edge": "sideWaist>sideSeat", "y": -0.085}, "names": ["front_yoke", "front"]},
                 {"op": "style_line", "piece": "back", "name": "yokeB", "from": {"edge": "cWaist>cHem", "dist": 0.10},
                  "to": {"edge": "sideWaist>sideSeat", "y": -0.085}, "names": ["back_yoke", "back"]}])
    n0 = len(S["seams"])
    pd.apply(S, [{"op": "pocket", "type": "in_seam", "piece": "front", "other": "back", "top": 0.02, "opening": 0.15,
                  "width": 0.12, "height": 0.22}])
    _ok(S)
    assert len(S["seams"]) == n0 + 5  # the side seam in two parts (+1), and four bag seams
    bf, bb = S["pieces"]["pocket_front"], S["pieces"]["pocket_back"]
    assert bf["wrap"]["lies_on"] == "front" and bb["wrap"]["lies_depth"] == 2 and np.allclose(bf["P"], bb["P"])
    assert abs(pd.edge_length(S, "pocket_front:open.a>open.b") - 0.15) < 2e-3
    # nothing sews the opening's two lips to each other any more
    assert not any({"front:pocket.top>pocket.low", "back:pocket.top>pocket.low"} <= {str(x) for x in s} for s in S["seams"])
    pd.unfold(S)
    _ok(S)
    assert {"pocket_front.L", "pocket_back.R"} <= set(S["pieces"])


def test_lining_is_derived_from_its_shell():
    D = pd.start("bodice", MM, {"fitted": True, "cb": "seam"})
    pd.apply(D, [{"op": "contour", "edge": "centre_back", "at": [["top", 0], ["waist", 0.02], ["hem", 0.01]]},
                 {"op": "sleeve", "cap_ease": 0.04}, {"op": "lining"}])
    _ok(D)
    for n in ("front", "back", "sleeve"):
        L = D["pieces"][n + "_lining"]
        assert L["role"] == "lining" and L["wrap"]["lies_on"] == n and np.allclose(L["P"], D["pieces"][n]["P"])
    # the linings are sewn to each other as their shells are, and to the shell at the hems and the back neck
    assert ["front_lining:shoulder>hps", "back_lining:shoulder>hps"] in D["seams"]
    att = [s for s in D["seams"] if "lining" in str(s[0]) and "lining" not in str(s[1])]
    assert len(att) == 4, att
    pd.unfold(D)
    _ok(D)
    assert D["pieces"]["back_lining.R"]["wrap"]["lies_on"] == "back.R"
    assert any("back_lining.L:cbNeck" in str(s) and "back_lining.R:cbNeck" in str(s) for s in D["seams"])  # its own CB seam


def test_kimono_and_hood_are_placed():
    D = pd.start("knit", MM, {"chest_ease": 0.16})
    pd.apply(D, [{"op": "kimono", "angle": 30, "drop": 0.08}, {"op": "hood"}])
    _ok(D)
    pd.unfold(D)
    _ok(D)
    P = D["pieces"]
    # the sleeve past the underarm-to-shoulder line is its own part on the arm: the front half round the front of
    # the arm, the back half round the back, mirrored on the right arm; the overarm seam along the top (x = 0)
    assert P["front_sleeve.L"]["wrap"] == dict(P["front_sleeve.L"]["wrap"], to="arm.L", front=-1, cx=0.0)
    assert P["front_sleeve.R"]["wrap"]["to"] == "arm.R" and P["front_sleeve.R"]["wrap"]["front"] == 1
    assert P["back_sleeve.L"]["wrap"]["front"] == 1 and P["back_sleeve.R"]["wrap"]["front"] == -1
    fs = P["front_sleeve.L"]
    assert abs(fs["P"][fs["names"]["shoulder"]]).max() < 1e-9 and fs["P"][:, 1].max() < 1e-6  # down the arm from the shoulder
    assert fs["P"][:, 0].max() < 1e-6 and fs["P"][:, 0].min() < -0.1  # all on one side of the overarm line
    assert sum(1 for v in D["notes"].values() if v.get("virtual")) == 4
    assert P["hood.L"]["wrap"]["to"] == "head" and P["hood.L"]["wrap"]["apart"] > 0.02




def test_tailored_collar():
    """One piece, stand + fall on a roll line, its outer edge sprung past the neck edge, ending at the gorge."""
    D = pd.start("bodice", MM, {"fitted": True})
    pd.apply(D, [{"op": "lapel", "break_y": 0.42, "stand": 0.025, "width": 0.085, "gorge": "straight", "gorge_drop": 0.09},
                 {"op": "collar", "type": "tailored", "stop": 0.0, "stand_height": 0.03, "fall": 0.045}])
    c = D["pieces"]["collar"]
    for nm in ("cbNeck", "cbRoll", "cbOuter", "endNeck", "endRoll", "endOuter"):
        assert nm in c["names"], nm
    neck = pd.edge_length(D, D["edges"]["collar_neck"])
    outer = pd.edge_length(D, D["edges"]["collar_outer"])
    assert outer > neck + 0.02, (outer, neck)  # (Jaeger's is 16 mm SHORTER: its fall can't lie on the shoulders)
    assert abs(np.linalg.norm(c["P"][c["names"]["cbRoll"]] - c["P"][c["names"]["cbNeck"]]) - 0.03) < 1e-6
    assert any(f["piece"] == "collar" and f["kind"] == "press" and f.get("in_wrap") for f in D["folds"])
    _ok(D)


LEG = dict(MM, knee=361.5, calf=381.8, heel=337.1, ankle=225.4, upperLeg=559.3)


def test_leg_cut_comes_from_the_leg():
    from hifipushie import pattern_blocks as pb
    knee, hem, rule = pb.leg_cut(LEG, "slim")
    assert abs(2 * knee - 0.3615 * 1.20) < 1e-6 and 2 * knee > 0.3818 * 1.08  # knee girth + 20%, clear of the calf
    assert 2 * hem >= 0.3371 + 0.02 - 1e-9 and hem <= knee  # the hem passes the heel, never wider than the knee
    assert "heel" in rule
    wide = pb.leg_cut(LEG, "wide")
    assert wide[0] > knee and abs(wide[1] - wide[0]) < 1e-9
    T = pd.start("trouser", LEG, {"leg": "slim"})
    fr, bk = T["pieces"]["front"], T["pieces"]["back"]
    kw = lambda pc: np.linalg.norm(pc["P"][pc["names"]["sideKnee"]] - pc["P"][pc["names"]["inKnee"]])
    assert abs(kw(fr) + kw(bk) - 2 * knee) < 1e-6
    # the crease is the grain line: through the middle of knee and hem on both pieces
    for pc in (fr, bk):
        cx = pc["lines"]["crease"][0][0]
        for a, b in (("sideKnee", "inKnee"), ("sideHem", "inHem")):
            assert abs(0.5 * (pc["P"][pc["names"][a]][0] + pc["P"][pc["names"][b]][0]) - cx) < 1e-9
    try:
        pb.leg_cut(LEG, "bootcut")
        assert False
    except ValueError:
        pass


def test_shaped_dart_keeps_its_legs_equal():
    T = pd.start("trouser", LEG, {"dart_taper": 0.6})
    _ok(T)
    bk = T["pieces"]["back"]
    ia, it, ib = (bk["names"][k] for k in ("dartA", "dartTip", "dartB"))
    assert it - ia == 2 and ib - it == 2  # a shaping point on each leg
    P = bk["P"]
    full = np.degrees(np.arctan2(abs(P[ib, 0] - P[ia, 0]), abs(P[ia, 1] - P[it, 1])))
    tip = np.degrees(np.arctan2(abs(P[it + 1, 0] - P[it - 1, 0]), abs(P[it + 1, 1] - P[it, 1])))
    assert tip < 0.5 * full, (tip, full)  # the tip dies away: under half the straight dart's angle


def test_crease_fly_and_front_waistband():
    D = pd.start("trouser", LEG, {"leg": "slim", "length": "shoe"})
    pd.apply(D, [{"op": "fly"}, {"op": "crease"}, {"op": "waistband", "opening": "front", "overlap": 0.04}])
    _ok(D)
    fr = D["pieces"]["front"]
    assert "flyEnd" in fr["names"] and D["edges"]["centre_front"] == ["front:flyEnd>cSeat>fork"]
    assert abs(pd.edge_length(D, "front:cWaist>flyEnd") - min(0.18, 0.92 * pd.edge_length(D, "front:cWaist>cSeat"))) < 1e-6
    assert len(fr["lines"]["fly_stitch"]) > 5
    cr = [f for f in D["folds"] if f["name"].startswith("crease")]
    assert {f["piece"] for f in cr} == {"front", "back"} and all(f["angle"] > 180 and f["in_wrap"] for f in cr)
    pd.unfold(D)
    # the fly: a zip closure, left over right, its seam only the opening; the centre seam runs on below it
    c = next(c for c in D["closures"] if c["name"] == "fly")
    assert (c["kind"], c["over"], c["under"]) == ("zip", "front.L", "front.R")
    assert c["seam"] == ["front.L:cWaist>flyEnd", "front.R:cWaist>flyEnd"]
    assert ["front.L:flyEnd>cSeat>fork", "front.R:flyEnd>cSeat>fork"] in D["seams"]
    assert "fly_stitch" in D["pieces"]["front.L"]["lines"] and "fly_stitch" not in D["pieces"]["front.R"]["lines"]
    assert sum(1 for f in D["folds"] if f["name"].startswith("crease")) == 4
    # the waistband opens at the centre front: from the left front round the back to the right front, the left end
    # over, the extension with the button at the right end
    gen = D["generate"][0]
    assert gen["along"][0] == "front.L:cWaist>sideWaist" and gen["along"][-1] == "front.R:sideWaist>cWaist"
    assert gen["extension"] == "end" and gen["wrap"]["side"] == "back" and gen["wrap"]["over"] == "low"
    from hifipushie import garment_blocks
    pcs, seams, st, inter = garment_blocks.generate(D["pieces"], gen)
    wb = pcs["waistband"]
    assert seams[0][0] == "waistband:sw>s>lapEnd" and st == [["waistband:button1", "waistband:buttonhole1"]]
    assert wb["marks"]["button1"][0] > wb["marks"]["buttonhole1"][0]  # the button on the extension at the high end
    chain = abs(wb["marks"]["button1"][0] - wb["marks"]["buttonhole1"][0])
    assert abs(chain - garment_blocks._chain_length(D["pieces"], gen["along"])) < 1e-6
    # a RIB band (cloth10, for knits): cut shorter than its edge and folded in half, closed in a ring: its seam's
    # stretch and its fold are declared for the checks (not a plain +-1.5% seam, a real fold line)
    import json
    rib = {"band": "rib", "along": gen["along"], "ratio": 0.85, "height": 0.05, "ring": True, "fold": True}
    ex = {}
    pr, sr, _, _ = garment_blocks.generate(D["pieces"], rib, ex)
    note = ex["seam_notes"][json.dumps(sr[0])]
    assert note["ease"][0] < -0.15 < note["ease"][1] and "stretched" in note["why"]
    assert ex["folds"] == [{"piece": "rib", "line": "fold", "angle": 360.0, "kind": "press", "name": "rib fold"}]
    assert "fold" in pr["rib"]["lines"] and ["rib:sw>nw", "rib:se>ne"] in sr
    ex1 = {}
    garment_blocks.generate(D["pieces"], gen, ex1)
    assert not ex1.get("seam_notes") and not ex1.get("folds")  # (a waistband at ratio 1: nothing declared)
    # worn open: the zip's seam isn't sewn
    from hifipushie import closures
    D2 = pd.start("trouser", LEG, {})
    pd.apply(D2, [{"op": "fly", "state": "open"}])
    pd.unfold(D2)
    assert closures.expand(D2["closures"], D2["pieces"])[2] == []
    assert closures.expand(D["closures"], D["pieces"])[2] == [c["seam"]]


def test_suit_trousers_kind_drafts_itself():
    from hifipushie import garment_design as gd
    sheet = {"kind": "suit_trousers"}
    gd.validate(sheet)
    out = gd.compile_sheet(sheet)
    pat = out["pattern"]
    assert pat["block"] == "trouser" and pat["block_options"]["leg"] == "slim" and pat["block_options"]["length"] == "break"
    assert [o["op"] for o in pat["ops"]] == ["waistband", "fly", "crease"], pat["ops"]
    assert {t["kind"] for t in out["trims"]} == {"belt", "belt_loops"}
    # the sheet's own op of a name wins over the detail's; a fit changes the leg
    out2 = gd.compile_sheet({"kind": "suit_trousers", "fit": "classic", "ops": [{"op": "crease", "angle": 195}]})
    assert [o for o in out2["pattern"]["ops"] if o["op"] == "crease"] == [{"op": "crease", "angle": 195}]
    assert out2["pattern"]["block_options"]["leg"] == "straight"
    D = pd.build(LEG, pat)
    assert any(c["name"] == "fly" for c in D["closures"])


def test_trims_ride_a_band():
    from hifipushie import cloth_trims
    cloth_trims.validate([{"kind": "belt"}, {"kind": "belt_loops", "count": 7}])
    try:
        cloth_trims.validate([{"kind": "buckle"}])
        assert False
    except cloth_trims.TrimError:
        pass
    # a band round a cylinder as a finished result: the belt lies outside it, loops stand over the belt
    n, h, R = 80, 0.04, 0.13
    xs = np.linspace(-0.41, 0.41, n)
    uv = np.array([[x, y] for x in xs for y in (0.0, h / 2, h)])
    th = uv[:, 0] / R
    V = np.c_[R * np.sin(th), -R * np.cos(th), 1.0 + uv[:, 1]]
    F = []
    for i in range(n - 1):
        for j in range(2):
            a = 3 * i + j
            F += [[a, a + 3, a + 4], [a, a + 4, a + 1]]
    pc = {"P": np.array([[-0.41, 0], [0.41, 0], [0.41, h], [-0.41, h]]), "role": "waistband", "marks": {}, "wrap": {}}
    res = {"V": V, "mesh": {"names": ["waistband"], "piece": np.zeros(len(V), int), "F": np.array(F), "uv": uv},
           "pieces": {"pieces": {"waistband": pc}}}
    trims = [{"kind": "belt", "buckle": False}, {"kind": "belt_loops", "count": 5}]
    assert all(ok for ok, _ in cloth_trims.check(trims, res["pieces"]["pieces"]))
    out = {m["kind"]: m for m in cloth_trims.meshes(res, {"trims": trims, "color": "#333333"})}
    rb = np.hypot(out["belt"]["V"][:, 0], out["belt"]["V"][:, 1])
    assert rb.min() > R + 0.0005 and rb.max() < R + 0.012, (rb.min(), rb.max())
    rl = np.hypot(out["belt_loops"]["V"][:, 0], out["belt_loops"]["V"][:, 1])
    assert rl.max() > rb.max() - 0.004 and out["belt_loops"]["color"] == "#333333"
    assert out["belt"]["F"].max() < len(out["belt"]["V"])


def test_trousers_cut_to_a_break():
    # length "break": the sides and front to "shoe", the back BREAK_BACK longer (a sloped hem); the break itself is
    # the front's length over the shoe, which the start gathers (cloth._hem_on_shoe)
    from hifipushie import pattern_blocks as pb
    B = pb.trouser(dict(LEG), {"length": "break", "leg": "slim"})
    fr, bk = B["pieces"]["front"], B["pieces"]["back"]
    y = lambda pc, nm: -float(pc["P"][pc["names"][nm], 1])  # length down from the waist
    L = LEG["waistToFloor"] / 1000 - pb.TROUSER_LENGTHS["shoe"]
    assert abs(y(fr, "sideHem") - L) < 1e-6 and abs(y(bk, "inHem") - L) < 1e-6
    assert "creaseHem" not in fr["names"] and abs(y(bk, "creaseHem") - (L + pb.BREAK_BACK)) < 1e-6


def test_jeans_are_construction():
    """{kind: jeans}: the trouser block without back darts, a back YOKE taking their intake, front scoop pockets and
    back patch pockets (two style lines by name, both kept), no crease; drafted, the yoke and pocket pieces exist and
    the patch pockets lie on the back legs (not girth)."""
    from hifipushie import garment_design as gd
    out = gd.compile_sheet({"kind": "jeans", "fit": "straight"})
    pat = out["pattern"]
    ops = [(o["op"], o.get("name")) for o in pat["ops"]]
    assert ("style_line", "yoke") in ops and ("style_line", "scoop") in ops and ("pocket", "back_pocket") in ops
    assert ("crease", None) not in ops and pat["block_options"]["back_dart"] == 0.0
    assert pat["block_options"]["leg"] == "straight"
    from hifipushie import cloth
    Bp = cloth.pieces({"pattern": pat}, MM)
    names = set(Bp["pieces"])
    assert {"yoke.L", "yoke.R", "pocket_side.L", "back_pocket.L"} <= names, names
    assert Bp["pieces"]["back_pocket.L"]["wrap"].get("lies_on")


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
