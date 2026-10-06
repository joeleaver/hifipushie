"""Style operations (pattern_styles): each keeps the draft's invariant: every seam's two sides equal or its ease
declared, named edges still there, and the draft unfolds. No body, no sim.
Run: uv run python tests/test_pattern_styles.py"""
import numpy as np

from hifipushie import cloth, pattern, pattern_draft as pd

MM = {"neck": 370.5, "shoulderSlope": 29.0, "shoulderToShoulder": 463.9, "chest": 994.0, "waist": 776.3, "hips": 920.6,
      "seat": 972.2, "biceps": 340.2, "wrist": 148.6, "shoulderToElbow": 300.3, "shoulderToWrist": 570.0,
      "hpsToWaistBack": 545.0, "hpsToBust": 331.1, "highBust": 994.0, "waistToArmpit": 230.7, "waistToHips": 145.2,
      "waistToSeat": 245.2, "waistToFloor": 1109.3, "waistToKnee": 585.4, "head": 560.0, "waistToUpperLeg": 251.1,
      "inseam": 858.2}
PRIN = [{"op": "style_line", "piece": "front", "name": "princessF", "from": {"edge": "hps>shoulder", "t": 0.5},
         "to": {"edge": "hem>cfHem", "t": 0.45}, "via": ["bust"], "names": ["front", "side_front"], "take_in": 0.03},
        {"op": "style_line", "piece": "back", "name": "princessB", "from": {"edge": "hps>shoulder", "t": 0.5},
         "to": {"edge": "hem>cbHem", "t": 0.45}, "via": [[0.09, -0.30]], "names": ["back", "side_back"], "take_in": 0.035}]


def _ok(D):
    bad = [t for ok, t in pd.consistency(D) if not ok]
    assert not bad, bad


def _draft(block, opts, ops):
    D = pd.start(block, MM, opts)
    pd.apply(D, ops)
    _ok(D)
    return D


def _area(P):
    return 0.5 * abs(np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1]))


def test_shawl_collar_on_the_roll_line():
    D = _draft("bodice", {"fitted": True}, PRIN + [{"op": "shawl", "break_y": 0.40},
                                                  {"op": "facing", "piece": "front", "edges": ["shawl_edge", "centre_front"], "width": 0.07},
                                                  {"op": "buttons", "piece": "front", "n": 1}, {"op": "sleeve", "cap_ease": 0.04},
                                                  {"op": "two_piece"}])
    f = D["pieces"]["front"]
    # the collar's neck seam is the back neck's length, and it carries on past the neck point
    assert abs(pd.edge_length(D, "front:collarCB>hps") - pd.edge_length(D, D["edges"]["neck_back"])) < 1e-4
    assert f["P"][f["names"]["collarCB"], 1] > f["P"][f["names"]["hps"], 1]
    assert any(fd["kind"] == "roll" and fd["piece"] == "front" for fd in D["folds"])
    assert D["pair_seams"], "the collar's centre back seam joins the two fronts"
    # the back collar has spring: its outer edge is longer than its neck seam (a straight strip can't turn down)
    assert f["P"][f["names"]["collarTop"]] is not None and D["hinges"]
    pd.unfold(D)
    _ok(D)
    # one cloth, two placements: the collar past the neck point is its own piece on the neck, joined by a seam
    # noted "virtual"; the facing is cut the same way and lies on the front
    c = D["pieces"]["front_collar.L"]
    assert c["wrap"]["to"] == "neck" and D["pieces"]["front.L"]["wrap"]["to"] == "torso"
    assert pattern.length(c["P"][pattern.arc_indices(c, "collarTop>neckHinge_front.b")]) > \
        1.25 * pattern.length(c["P"][pattern.arc_indices(c, "collarCB>hps")])
    virt = [k for k, v in D["notes"].items() if v.get("virtual")]
    assert len(virt) == 4 and any("front.L:neckHinge_front.a" in k and "front_collar.L" in k for k in virt)
    assert D["pieces"]["front_facing.L"]["wrap"]["lies_on"] == "front.L"
    assert D["pieces"]["front_facing_collar.R"]["wrap"]["lies_on"] == "front_collar.R"
    assert ["front_collar.L:collarCB>collarTop", "front_collar.R:collarCB>collarTop"] in D["seams"]
    # the roll line is cut with the piece: a roll on the front, one crease at the fall's isometric angle on the collar
    fc = next(fd for fd in D["folds"] if fd["piece"] == "front_collar.L")
    assert fc["kind"] == "press" and 20 < fc["angle"] < 90 and fc["flap"] == "collarTop"
    assert any(fd["piece"] == "front_facing.L" for fd in D["folds"])  # the facing turns with its front
    assert 0.006 < D["pieces"]["front.L"]["wrap"]["out"] <= 0.016  # the lap: as little as holds the layers apart
    assert D["pieces"]["front_facing.L"]["wrap"]["fused"] == "front.L"  # one cloth with its front in the sim
    assert len(D["stitches"]) == 1  # the one button, right front to left
    # the right front's roll line is the left's mirrored
    L = next(fd for fd in D["folds"] if fd["piece"] == "front.L")["line"]
    R = next(fd for fd in D["folds"] if fd["piece"] == "front.R")["line"]
    assert np.allclose(np.asarray(L) * [-1, 1], np.asarray(R))


def test_notched_lapel_and_collar_to_the_gorge():
    D = _draft("bodice", {"fitted": True}, [{"op": "lapel", "break_y": 0.42, "stand": 0.025, "width": 0.085},
                                            {"op": "collar", "type": "roll", "stop": 0.04, "height": 0.07},
                                            {"op": "facing", "piece": "front", "edges": ["lapel_edge", "gorge"], "width": 0.08}])
    c = D["pieces"]["collar"]
    sewn = pd.edge_length(D, "collar:cb>shoulderNotch>cf")
    # the collar stops 40 mm short of the neckline's end, and its outer edge is LONGER than its neck edge (it lies
    # away from the neck; drawn on the hole's side it came out shorter and crossed itself)
    assert abs(sewn - (pd.edge_length(D, D["edges"]["neck_back"]) + pd.edge_length(D, D["edges"]["neck_front"]) - 0.04)) < 2e-3
    assert pattern.length(c["P"][pattern.arc_indices(c, "frontTop>cbTop")]) > sewn * 1.2
    assert _area(c["P"]) > 0.9 * sewn * 0.07
    fc = D["pieces"]["front_facing"]
    assert _area(fc["P"]) < _area(D["pieces"]["front"]["P"]) * 0.6
    # the facing lies inside the front it was traced from
    assert cloth._inside(D["pieces"]["front"]["P"], fc["P"] * 0.999 + 0.001 * fc["P"].mean(0)).mean() > 0.9


def test_band_collar_leans_in():
    D = _draft("bodice", {}, [{"op": "collar", "type": "band", "height": 0.035}])
    c = D["pieces"]["collar"]
    top = pattern.length(c["P"][pattern.arc_indices(c, "frontTop>cbTop")])
    assert top < pd.edge_length(D, "collar:cb>shoulderNotch>cf")


def test_darts_joined_into_a_seam():
    D = _draft("bodice", {"fitted": True, "darts": True, "length": "waist", "bust_dart": 0.03},
               [{"op": "dart", "piece": "front", "dart": "bustDart", "to": {"edge": "hps>shoulder", "t": 0.5}, "apex": "bust"},
                {"op": "darts_to_seam", "piece": "front", "darts": ["bustDart", "waistDart"], "names": ["front", "side_front"]}])
    assert {"front", "side_front"} <= set(D["pieces"]) and not D["pieces"]["front"].get("darts")
    assert pd.edge_length(D, D["edges"]["shoulder_front"]) - pd.edge_length(D, D["edges"]["shoulder_back"]) < 1e-3


def test_raglan_kimono_hood_pleat():
    D = _draft("knit", {}, [{"op": "sleeve"}, {"op": "raglan"},
                            {"op": "collar", "type": "band", "height": 0.02, "name": "neckband", "role": "neckband"}])
    sl = D["pieces"]["sleeve"]
    assert {"hpsF", "hpsB"} <= set(sl["names"])  # the shoulder went to the sleeve
    pd.unfold(D)
    _ok(D)
    K = _draft("knit", {}, [{"op": "kimono"}])
    assert set(K["pieces"]) == {"front", "back"}
    H = _draft("knit", {"chest_ease": 0.15}, [{"op": "sleeve"}, {"op": "hood"}])
    assert H["pieces"]["hood"]["wrap"]["to"] == "head"
    P = pd.start("bodice", MM, {})
    w0 = np.ptp(P["pieces"]["back"]["P"][:, 0])
    pd.apply(P, [{"op": "pleat", "piece": "back", "from": {"edge": "cbNeck>hps", "t": 0.5}, "to": {"edge": "hem>cbHem", "t": 0.7}, "depth": 0.02}])
    _ok(P)
    assert abs(np.ptp(P["pieces"]["back"]["P"][:, 0]) - w0 - 0.04) < 2e-3  # spread by twice the depth
    assert sum(fd["piece"] == "back" for fd in P["folds"]) == 2


def test_asymmetric_ops_after_unfold_keep_the_shoulders():
    D = _draft("bodice", {"fitted": True}, [
        {"op": "neckline", "widen": 0.02, "back": 0.005}, {"op": "sleeve"}, {"op": "unfold"},
        {"op": "extend", "piece": "front.L", "edge": "cfNeck>cfHem", "amount": 0.16, "name": "wrap"},
        {"op": "cut_away", "piece": "front.L", "keep": "armhole", "from": "hps", "to": {"edge": "wrap.a>wrap.b", "t": 0.55}, "name": "vneck"},
        {"op": "cut_away", "piece": "front.R", "keep": "armhole", "from": "hps", "to": {"edge": "cfNeck>cfHem", "t": 0.5}, "name": "vneckR"}])
    sh = [s for s in D["seams"] if "shoulder" in str(s) and "sleeve" not in str(s)]
    assert len(sh) == 2, D["seams"]  # a cut from the neck point keeps both shoulder seams
    assert abs(np.ptp(D["pieces"]["front.L"]["P"][:, 0]) - np.ptp(D["pieces"]["front.R"]["P"][:, 0]) - 0.16) < 2e-3
    # widened on both: the shoulders are 20 mm shorter and still equal
    B = pd.start("bodice", MM, {"fitted": True})
    assert abs(pd.edge_length(B, "front:hps>shoulder") - pd.edge_length(D, "front.L:hps>shoulder") - 0.02) < 1e-3


def test_take_in_shapes_the_side_panel_more_and_two_piece_bends():
    D = _draft("bodice", {"fitted": True}, PRIN + [{"op": "sleeve", "cap_ease": 0.04}, {"op": "two_piece"}])
    sa, sb = D["lines"]["princessB"]

    def bow(spec):  # how far the edge leaves its chord
        n, arc = spec.split(":", 1)
        L = D["pieces"][n]["P"][pattern.arc_indices(D["pieces"][n], arc)]
        t = (L[-1] - L[0]) / np.linalg.norm(L[-1] - L[0])
        return np.abs((L - L[0]) @ [-t[1], t[0]]).max()

    side, centre = (sa, sb) if sa.startswith("side_back") else (sb, sa)
    assert bow(side) > bow(centre)
    top, under = D["pieces"]["top"], D["pieces"]["under"]
    assert D["meta"]["sleeve"]["two_piece"]
    # the under sleeve's hem is one straight line
    ix = pattern.arc_indices(under, "usHemF>usHemMid>usHemB")
    assert len(ix) == 3


def test_trouser_side_seams_are_trued_and_legs_wrap():
    T = pd.start("trouser", MM, {})
    _ok(T)
    assert abs(pd.edge_length(T, "front:sideWaist>sideSeat>sideHem") - pd.edge_length(T, "back:sideWaist>sideSeat>sideHem")) < 2e-4
    pd.unfold(T)
    assert {p["wrap"]["to"] for p in T["pieces"].values()} == {"leg.L", "leg.R"}
    assert "leg.L" in cloth.WRAPS


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
