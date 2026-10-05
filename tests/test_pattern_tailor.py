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


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
