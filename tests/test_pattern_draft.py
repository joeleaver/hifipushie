"""Principle-based drafting: blocks by rule, and the invariants every pattern operation must keep (mating edges stay
matched or declare their ease; named edges survive). No body, no FreeSewing, no sim.
Run: uv run python tests/test_pattern_draft.py"""
import numpy as np

from hifipushie import cloth, cloth_check, pattern, pattern_blocks as pb, pattern_draft as pd

MM = {"neck": 370.5, "shoulderSlope": 29.0, "shoulderToShoulder": 463.9, "chest": 994.0, "waist": 776.3, "hips": 920.6,
      "seat": 972.2, "biceps": 340.2, "wrist": 148.6, "shoulderToElbow": 300.3, "shoulderToWrist": 570.0,
      "hpsToWaistBack": 545.0, "hpsToBust": 331.1, "highBust": 994.0, "waistToArmpit": 230.7, "waistToHips": 145.2,
      "waistToSeat": 245.2, "waistToFloor": 1109.3, "waistToKnee": 585.4}


def _ok(D):
    bad = [t for ok, t in pd.consistency(D) if not ok]
    assert not bad, bad


def _len(D, e):
    return pd.edge_length(D, e)


def test_bodice_rules():
    D = pd.start("bodice", MM, {"chest_ease": 0.15})
    f, b = D["pieces"]["front"], D["pieces"]["back"]
    assert abs(f["P"][f["names"]["armhole"], 0] - 0.994 * 1.15 / 4) < 1e-6  # chest quarter
    neck = _len(D, D["edges"]["neck_front"]) + _len(D, D["edges"]["neck_back"])
    assert abs(neck - 0.3705 * 1.05 / 2) < 5e-4  # the neckline is solved to half the neck girth + ease
    assert abs(_len(D, "front:hps>shoulder") - _len(D, "back:hps>shoulder")) < 1e-9
    _ok(D)
    F = pd.start("bodice", MM, {"fitted": True, "darts": True, "length": "waist", "bust_dart": 0.03})
    fr = F["pieces"]["front"]
    waist = sum(_len(F, e) for e in F["edges"]["hem_front"])  # the sewn waist (the dart left out)
    assert abs(waist - (0.7763 * 1.10 / 4 + F["meta"]["waist_left"])) < 2e-3, waist
    assert set(fr["darts"]) == {"bustDart", "waistDart"}
    _ok(F)


def test_sleeve_is_solved_into_the_armhole():
    for ease, be in ((0.0, 0.10), (0.015, 0.15), (0.045, 0.2)):
        D = pd.start("bodice", MM, {})
        pd.apply(D, [{"op": "sleeve", "cap_ease": ease, "biceps_ease": be}])
        af, ab = _len(D, D["edges"]["armhole_front"]), _len(D, D["edges"]["armhole_back"])
        cap = D["meta"]["sleeve"]["cap"]
        assert cap["ok"] and abs(cap["front"] - af * (1 + ease)) < 3e-4 and abs(cap["back"] - ab * (1 + ease)) < 3e-4
        assert abs(np.ptp(D["pieces"]["sleeve"]["P"][:, 0]) - 0.3402 * (1 + be)) < 1e-6
        _ok(D)
    # a wider sleeve gets a lower cap (the three can't be chosen independently)
    h = [pb.solve_cap(w, 0.28, 0.27, 0.015)["h"] for w in (0.36, 0.40, 0.44)]
    assert h[0] > h[1] > h[2]
    assert not pb.solve_cap(0.60, 0.28, 0.27, 0.0)["ok"]  # wider than the armhole is long: no cap


def test_style_line_keeps_everything_matched():
    D = pd.start("bodice", MM, {"fitted": True})
    before = {k: sum(_len(D, e) for e in v) for k, v in D["edges"].items()}
    pd.apply(D, [{"op": "style_line", "piece": "front", "name": "pf", "from": {"edge": "hps>shoulder", "t": 0.5},
                  "to": {"edge": "hem>cfHem", "t": 0.45}, "via": ["bust"], "names": ["front", "side_front"]}])
    assert set(D["pieces"]) == {"front", "side_front", "back"}
    for k, v in before.items():  # every named edge is still there, the same length, now over two pieces
        assert abs(sum(_len(D, e) for e in D["edges"][k]) - v) < 1e-9, k
    assert len(D["edges"]["shoulder_front"]) == 2 and len(D["edges"]["hem_front"]) == 2
    sa, sb = D["lines"]["pf"]
    assert abs(_len(D, sa) - _len(D, sb)) < 1e-12
    _ok(D)
    pd.apply(D, [{"op": "take_in", "line": "pf", "amount": 0.03}, {"op": "sleeve"}])
    assert abs(_len(D, sa) - _len(D, sb)) < 1.5e-3  # shaved alike
    _ok(D)  # the sleeve was drafted into the armhole as it is now (two pieces at the front)


def test_dart_pivot_changes_no_seam():
    D = pd.start("bodice", MM, {"fitted": True, "darts": True, "length": "waist", "bust_dart": 0.03})
    side = _len(D, ["front:armhole>bustDartA", "front:bustDartB>waist"])
    sh = _len(D, "front:hps>shoulder")
    pd.apply(D, [{"op": "dart", "piece": "front", "dart": "bustDart", "to": {"edge": "hps>shoulder", "t": 0.5}, "apex": "bust"}])
    fr = D["pieces"]["front"]
    assert np.sum(np.abs(fr["P"][:, 0]) < 1e-9) >= 2  # the centre front stayed on x = 0
    assert abs(sum(_len(D, e) for e in D["edges"]["shoulder_front"]) - sh) < 1e-9  # the shoulder skips the new dart
    s = next(s for s in D["seams"] if "back:armhole>waist" in s)
    assert abs(_len(D, s[0]) - side) < 1e-9  # the side seam is whole again and no longer
    a, t, b = fr["darts"]["bustDart"]
    assert abs(_len(D, f"front:{a}>{t}") - _len(D, f"front:{b}>{t}")) < 1e-9
    _ok(D)
    # and on to another edge again
    pd.apply(D, [{"op": "dart", "piece": "front", "dart": "bustDart", "to": {"edge": "cfNeck>hps", "t": 0.5}, "apex": "bust"}])
    _ok(D)


def test_dart_to_ease_declares_it():
    D = pd.start("bodice", MM, {"fitted": True, "darts": True, "length": "waist"})
    w0 = sum(_len(D, e) for e in D["edges"]["hem_back"])
    pd.apply(D, [{"op": "dart_to_ease", "piece": "back", "dart": "waistDart", "as": "gathers"}])
    w1 = sum(_len(D, e) for e in D["edges"]["hem_back"])
    assert abs((w1 - w0) - 0.035) < 1e-6 and "waistDart" not in D["pieces"]["back"]["darts"]
    _ok(D)


def test_flare_lengthen_extend_facing_collar():
    D = pd.start("bodice", MM, {})
    side = _len(D, "front:armhole>hem")
    hem = _len(D, D["edges"]["hem_front"])
    pd.apply(D, [{"op": "lengthen", "pieces": ["front", "back"], "amount": 0.2},
                 {"op": "flare", "piece": "front", "edge": "hem>cfHem", "hinge": "armhole", "amount": 0.05, "n": 2},
                 {"op": "flare", "piece": "back", "edge": "hem>cbHem", "hinge": "armhole", "amount": 0.05, "n": 2}])
    assert abs(_len(D, "front:armhole>hem") - (side + 0.2)) < 1e-6  # the hinge edge keeps its length
    assert 0.07 < _len(D, D["edges"]["hem_front"]) - hem < 0.12  # the hem grew by about the spread
    assert np.sum(np.abs(D["pieces"]["front"]["P"][:, 0]) < 1e-9) >= 2  # the centre stayed
    cf = _len(D, D["edges"]["centre_front"])
    pd.apply(D, [{"op": "extend", "piece": "front", "edge": "cfNeck>cfHem", "amount": 0.02, "name": "stand"},
                 {"op": "collar", "type": "band", "height": 0.035},
                 {"op": "facing", "piece": "front", "edges": "stand", "width": 0.06}, {"op": "sleeve"}])
    assert abs(_len(D, D["edges"]["stand"]) - cf) < 1e-9
    neck = _len(D, D["edges"]["neck_front"]) + _len(D, D["edges"]["neck_back"])
    assert abs(_len(D, "collar:cb>shoulderNotch>cf") - neck) < 1e-6  # the collar is drafted from the neckline
    _ok(D)
    pd.unfold(D)
    assert {"back", "front.L", "front.R", "collar", "front_facing.L", "front_facing.R", "sleeve.L", "sleeve.R"} == set(D["pieces"])
    _ok(D)


def test_two_piece_sleeve():
    D = pd.start("bodice", MM, {"chest_ease": 0.14})
    pd.apply(D, [{"op": "sleeve", "cap_ease": 0.045, "biceps_ease": 0.18}])
    cap = _len(D, D["edges"]["cap"])
    hem = _len(D, D["edges"]["sleeve_hem"])
    pd.apply(D, [{"op": "two_piece"}])
    assert abs(_len(D, D["edges"]["cap"]) - cap) < 2e-3  # the cap is the same length, over three edges
    assert abs(_len(D, D["edges"]["sleeve_hem"]) - hem) < 3e-3
    _ok(D)
    t, u = D["pieces"]["top"], D["pieces"]["under"]
    # the under sleeve is turned right side up: its forearm edge on the side that meets the top's under the arm
    assert t["P"][t["names"]["tsF"], 0] > 0 > u["P"][u["names"]["usF"], 0]
    # bent at the elbow: forearm seams equal, the top's hindarm longer (elbow ease, declared), the wrist forward
    assert abs(_len(D, "top:tsF>tsHemF") - _len(D, "under:usF>usHemF")) < 1e-3
    assert 0.003 < _len(D, "top:tsB>tsHemB") - _len(D, "under:usB>usHemB") < 0.02
    assert t["P"][t["names"]["tsHemF"], 1] > t["P"][t["names"]["tsHemB"], 1] + 0.01  # the hem square to the forearm
    from hifipushie import pattern
    bd = t["wrap"]["bend"]
    assert np.abs(pattern.bend(pattern.unbend(t["P"], **bd), **bd) - t["P"]).max() < 1e-6
    S = pd.start("bodice", MM, {"chest_ease": 0.14})
    pd.apply(S, [{"op": "sleeve", "cap_ease": 0.045, "biceps_ease": 0.18}, {"op": "two_piece", "elbow": 0}])
    s = S["pieces"]["top"]
    for k in ("tsHemF", "tsHemB", "tsF", "tsB"):  # unbent, it is the straight sleeve
        assert np.linalg.norm(pattern.unbend(t["P"][t["names"][k]], **bd)[0] - s["P"][s["names"][k]]) < 1e-6


def test_trouser_and_knit_blocks():
    T = pd.start("trouser", MM, {})
    f, b = T["pieces"]["front"], T["pieces"]["back"]
    assert abs(_len(T, "front:fork>inKnee>inHem") - _len(T, "back:fork>inKnee>inHem") - 0.005) < 3e-4
    seat = (f["P"][f["names"]["sideSeat"], 0] + b["P"][b["names"]["sideSeat"], 0]) * 2
    assert abs(seat - 0.9722 * 1.05) < 1e-6
    assert abs(b["P"][b["names"]["fork"], 0]) > 1.4 * abs(f["P"][f["names"]["fork"], 0])  # the back fork is the longer
    _ok(T)
    K = pd.start("knit", MM, {})
    pd.apply(K, [{"op": "sleeve"}])
    assert K["meta"]["sleeve"]["cap_ease"] == 0.0
    _ok(K)


def test_goes_through_cloth_pieces_and_meshes():
    g = {"pattern": {"from": "draft", "block": "bodice", "block_options": {"fitted": True}, "ops": [
        {"op": "style_line", "piece": "front", "name": "pf", "from": {"edge": "hps>shoulder", "t": 0.5},
         "to": {"edge": "hem>cfHem", "t": 0.45}, "via": ["bust"], "names": ["front", "side_front"], "take_in": 0.03},
        {"op": "sleeve"}, {"op": "collar", "type": "band"}]}}
    Bp = cloth.pieces(g, MM)
    assert {"front.L", "front.R", "side_front.L", "side_front.R", "back", "sleeve.L", "sleeve.R", "collar"} == set(Bp["pieces"])
    rows = cloth_check.seams(Bp, "shirt")
    assert all(abs(r["ease"]) < 0.02 for r in rows), [(r["a"], r["ease"]) for r in rows if abs(r["ease"]) >= 0.02]
    assert Bp["seam_notes"]
    M = cloth.mesh(Bp, 0.02)
    assert len(M["sew"]) > 200


def test_front_balance_auto_from_the_body_tapes():
    # dress-garrett 2026-10-15: with the hps on the shoulder crest a man's front tape (hps -> seat) is longer than the
    # back's; a front cut as long as the back swung an open jacket apart at the hem. "auto" drafts the difference.
    from hifipushie import pattern_blocks as pb
    assert abs(pb.front_balance({"hpsToSeatFront": 713.0, "hpsToSeatBack": 673.0}) - 0.040) < 1e-9
    assert pb.front_balance({"hpsToSeatFront": 678.0, "hpsToSeatBack": 711.0}) == 0.0  # old hps: the old cut
    assert pb.front_balance({}) == 0.0
    assert pb.front_balance({"hpsToSeatFront": 713.0, "hpsToSeatBack": 673.0}, 0.0) == 0.0  # explicit wins


def test_large_abdomen_reads_the_excess_over_the_population_norm():
    """The belly is the waist's depth over the chest's past ANSUR II's median man (-17 mm), measured on the body, not
    from the hps (dress-garrett 2026-10-15 n): flat bodies don't fire it, a deeper waist gets only the excess, and the
    hps tapes play no part (they moved with the landmark: dg_mh +76 / -50)."""
    from hifipushie import cloth
    la = cloth.ALTERATIONS["large_abdomen"]
    for c, w in ((233, 201), (231, 200), (234, 190)):  # dg_garrett, gp_A01, MakeHuman's default male
        assert la({"chestDepth": c, "waistDepth": w}) == 0.0
    assert abs(la({"chestDepth": 263, "waistDepth": 249}) - 0.003) < 1e-9  # dg_mh: 3 mm past the norm
    assert abs(la({"chestDepth": 250, "waistDepth": 263}) - 0.030) < 1e-9  # waist 13 deeper than chest: 30 past it
    assert la({"hpsToSeatFront": 790, "hpsToSeatBack": 690}) == 0.0  # the old tape proxy is not read
    assert la({}) == 0.0


def test_hem_height_does_not_move_with_the_hps():
    """A garment's length comes from a fixed body level (nape to waist + waist to hips), never from the hps tape: the
    side-neck hps cut the back tape 32 mm on gp_h6c and the jacket rode up, its fronts swinging round the sides
    (dress-garrett j12, 2026-10-15). Moving the hps tapes must leave the back's hem where it was."""
    def hem(m):
        D = pd.start("bodice", m, {"length": "hips", "length_bonus": 0.12})
        b = D["pieces"]["back"]
        return float(b["P"][:, 1].min())
    m0 = dict(MM, napeToWaistBack=489.0, hpsToArmpitBack=258.0)
    m1 = dict(m0, hpsToWaistBack=m0["hpsToWaistBack"] - 32.0, hpsToArmpitBack=222.6)  # the hps moved
    assert abs(hem(m0) - hem(m1)) < 1e-9
    bn = 0.05 * m0["neck"] / 1000
    assert abs(-hem(m0) - (bn + 0.489 + 0.1452 + 0.12)) < 1e-6  # nape tape + back neck depth + waist-hips + bonus


def test_jacket_cap_height_from_the_armhole_depth():
    """A jacket's cap stands 3/4 of the armhole depth (shoulder point to underarm; Pattern Principles 2005: 2/3-3/4,
    tailored the high end): cap ease first (inside the coat band 3-6%), then a narrower sleeve; a shirt keeps the solve."""
    for kind, want in (("jacket", 0.75), (None, None)):
        D = pd.start("bodice", MM, {"armhole_depth": 0.0})
        D["meta"]["kind"] = kind
        pd.apply(D, [{"op": "sleeve", "cap_ease": 0.03}])
        S = D["meta"]["sleeve"]
        r = S["cap"]["h"] / S["depth"]
        if want:
            assert abs(r - want) < 0.015 or S["biceps_ease"] <= pb.CAP_BICEPS_EASE_MIN + 1e-9, r
            assert 0.03 <= S["cap_ease"] <= 0.06 + 1e-9 and S["biceps_ease"] >= pb.CAP_BICEPS_EASE_MIN - 1e-9
            af, ab = _len(D, D["edges"]["armhole_front"]), _len(D, D["edges"]["armhole_back"])
            assert abs(S["cap"]["front"] - af * (1 + S["cap_ease"])) < 3e-4  # still sewn into its armhole
        else:
            assert S["cap_ease"] == 0.03 and abs(S["biceps_ease"] - 0.15) < 1e-9
        _ok(D)
    # never lower than the plain solve: a cap already high enough is left alone
    o = dict(pb.SLEEVE_DEFAULTS, cap_height=0.3)
    W, e, c = pb.cap_for_height(MM, 0.24, 0.23, o, 0.25)
    assert e == o["cap_ease"] and abs(W - 0.3402 * 1.15) < 1e-9


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
