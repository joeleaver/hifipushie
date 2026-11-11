"""F6: the flat gate's seam_ends (a seam's edges run the same way) and body_lengths (girths vs the body) rows."""
import numpy as np

from hifipushie import draft_body_lengths as dbl, draft_seam_ends as dse


def _rect(name, w, h, names):
    """A w x h rectangle (CCW from bottom-left), its corners named bl, br, tr, tl -> names[...]."""
    P = np.array([[0, 0], [w, 0], [w, h], [0, h]], float)
    return {"name": name, "P": P, "names": {names[k]: i for i, k in enumerate(("bl", "br", "tr", "tl"))},
            "marks": {}, "lines": {}, "wrap": {"to": "torso"}}


def _B(seam_b):
    band = _rect("band", 0.4, 0.04, {"bl": "sd", "br": "cf", "tr": "cfT", "tl": "sdT"})
    front = _rect("front", 0.4, 0.6, {"bl": "hemOut", "br": "hemIn", "tr": "cfWaist", "tl": "sideWaist"})
    return {"pieces": {"band": band, "front": front}, "seams": [["band:sd>cf", "front:" + seam_b]],
            "decl": {"pieces": {"band": {}, "front": {}}, "edges": {"band": {"bottom": "sd>cf"},
                                                                   "front": {"waist": seam_b}},
                     "seams": [{"a": "band:bottom", "b": "front:waist"}]}}


def test_a_reversed_seam_fails_naming_the_seam_and_the_swap():
    r = dse.rows(_B("cfWaist>sideWaist"))[0]
    assert r["status"] == "FAIL" and "front:cfWaist>sideWaist" in r["why"]
    assert '"cfWaist>sideWaist" -> "sideWaist>cfWaist"' in r["fix"]


def test_an_aligned_seam_passes():
    assert dse.rows(_B("sideWaist>cfWaist"))[0]["status"] == "PASS"


def test_up_and_down_decide_where_no_name_does():
    a = _rect("a", 0.2, 0.5, {"bl": "p1", "br": "p2", "tr": "p3", "tl": "p4"})
    b = _rect("b", 0.2, 0.5, {"bl": "q1", "br": "q2", "tr": "q3", "tl": "q4"})
    B = {"pieces": {"a": a, "b": b}, "seams": [["a:p3>p2", "b:q1>q4"]], "decl": {"pieces": {}}}
    assert dse.rows(B)[0]["status"] == "FAIL"  # a runs down its piece, b runs up
    B["seams"] = [["a:p3>p2", "b:q4>q1"]]
    assert dse.rows(B)[0]["status"] == "PASS"


def test_place_names():
    assert [dse.place_of(n) for n in ("cfWaist", "cb", "cbNeck.m", "nape", "sideWaist", "sd", "neckFront", "hps")] == \
        ["cf", "cb", "cb", "cb", "side", "side", None, None]


def test_a_girth_summed_round_shorter_than_the_body_fails():
    B = _B("sideWaist>cfWaist")  # band bottom 400 mm = front waist 400 mm, one seam naming the waist
    step1 = {"seams": [{"a": "band:bottom", "b": "front:waist", "length": {"body": ["waist"]}}]}
    step3 = {"measurements": [{"name": "waist", "mm": 420.0, "loop": [[0, 0, 0]]}]}
    r = dbl.rows(B, step1, step3, {})[0]
    assert r["status"] == "FAIL" and "waist" in r["why"] and "-20 mm" in r["why"]
    assert dbl.rows(B, step1, {"measurements": [{"name": "waist", "mm": 380.0, "loop": [[0, 0, 0]]}]}, {})[0]["status"] == "PASS"
    # the plan's ease counts: 380 + 40 ease = 420 > 400 drafted
    r = dbl.rows(B, step1, {"measurements": [{"name": "waist", "mm": 380.0, "loop": [[0, 0, 0]]}]},
                 {"waist": {"ease_mm": 40}})[0]
    assert r["status"] == "FAIL" and "ease 40" in r["why"]


def test_a_two_piece_sleeves_cap_is_judged_once():  # (t s4-1: each of three cap edges against its own panel; C361)
    import numpy as np
    from hifipushie import draft_shape as ds

    def pc(name, P, to):
        return {"name": name, "P": np.asarray(P, float), "names": {k: i for i, k in enumerate("abcd")}, "wrap": {"to": to}}
    sq = lambda h: [[0, 0], [0.1, 0], [0.1, h], [0, h]]  # (a: top-left, b: top-right, c, d: bottom)
    B = {"pieces": {"top": pc("top", sq(0.12), "arm.L"), "under": pc("under", sq(0.12), "arm.L"),
                    "front": pc("front", sq(0.2), "torso"), "back": pc("back", sq(0.2), "torso"),
                    "side": pc("side", sq(0.2), "torso")},
         "seams": [["top:a>d", "front:b>c"], ["top:b>c", "back:a>d"], ["under:a>b", "side:a>b"], ["top:d>c", "under:d>c"]]}
    r = ds.cap_rows(B, {}, {})
    assert r["value"].count(" = ") == 1, r["value"]  # (one row for the sleeve, not one per cap edge)
    assert "top+under" in r["value"] and "0.60" in r["value"], r["value"]  # (120 mm cap over a 200 mm armhole depth)


def test_an_undercollar_with_no_role_is_judged_a_fall_not_a_stand():  # (t s4-3: C361's name fix missed the gate; C363)
    from hifipushie import draft_shape as ds
    assert ds._role("undercollar", {"pieces": {"undercollar": {}}}, {}) == "collar_fall"
    assert ds._role("undercollar", {"pieces": {"undercollar": {"role": "collar_stand"}}}, {}) == "collar_stand"
    assert ds._role("widget.L", {}, {}) == "" and ds._role("front.L", {}, {}) == "front"


def test_a_lapels_roll_fold_is_not_a_collar_fall():  # (t s4-5; C366)
    import numpy as np
    from hifipushie import draft_shape as ds
    sq = {"P": np.asarray([[0, 0], [0.1, 0], [0.1, 0.2], [0, 0.2]], float), "names": {"a": 0, "b": 1, "c": 2, "d": 3}}
    B = {"pieces": {"front.L": dict(sq, name="front.L"), "undercollar": dict(sq, name="undercollar")},
         "folds": [{"piece": "front.L", "kind": "roll"}, {"piece": "undercollar", "kind": "roll"}], "seams": []}
    f = ds.fall_pieces(B, {}, {})
    assert "front.L" not in f and "undercollar" in f


def test_a_point_both_sides_name_decides_where_cf_and_side_dont():
    """C403: the jacket's undercollar "notch>..>shoulderL" against the front's "neck>..>notch" passed (no cf / cb / side):
    a point both sides name is one place, so notch at one's start and the other's end is reversed."""
    a = _rect("a", 0.2, 0.05, {"bl": "notch", "br": "shoulderL", "tr": "t1", "tl": "t2"})
    b = _rect("b", 0.2, 0.05, {"bl": "neck", "br": "notch", "tr": "u1", "tl": "u2"})
    B = {"pieces": {"a": a, "b": b}, "seams": [["a:notch>shoulderL", "b:neck>notch"]], "decl": {"pieces": {}}}
    r = dse.rows(B)[0]
    assert r["status"] == "FAIL" and "point notch at a:notch>shoulderL's start is b:neck>notch's end" in r["why"]
    assert '"neck>notch" -> "notch>neck"' in r["fix"]
    B["seams"] = [["a:notch>shoulderL", "b:notch>neck"]]
    assert dse.rows(B)[0]["status"] == "PASS"


def _fall_B(f, fold=True, band=False):
    """Backs (concave neck, CB to the side neck) and fronts (neck dropping to CF), a collar sewn round all four necks:
    with fold, a fall with its roll fold 25 mm up (stand 25, fall 45: lands 20 mm down); with band, a 30 mm band and a
    fall 38 mm deep on its top (lands 8 mm down). f scales the outer edge round its middle."""
    from hifipushie import pattern
    xs = np.linspace(0, 0.08, 9)
    t = np.linspace(0, np.pi / 2, 12)
    pcs = {}
    for sd in ("L", "R"):
        pcs[f"back.{sd}"] = {"name": f"back.{sd}", "P": np.array([(x, -0.02 * (1 - (x / 0.08) ** 2)) for x in xs] + [
            (0.2, -0.05), (0.2, -0.5), (0, -0.5)]), "names": {"cb": 0, "hps": 8}, "marks": {}, "lines": {}}
        pcs[f"front.{sd}"] = {"name": f"front.{sd}", "P": np.array([(0.08 * (1 - np.cos(u)), -0.07 * np.sin(u))
            for u in t] + [(0.08, -0.5), (0.25, -0.5), (0.2, 0.0)]), "names": {"hps": 0, "cf": 11}, "marks": {}, "lines": {}}
    W = 2 * (pattern.length(pcs["back.L"]["P"][:9]) + pattern.length(pcs["front.L"]["P"][:12]))
    xb = [0, W / 4, W / 2, 3 * W / 4, W]

    def strip(nm, h, ff):
        top = [(W / 2 + ff * W / 2, h), (W / 2, h), (W / 2 - ff * W / 2, h)]
        return {"name": nm, "P": np.array([(x, 0) for x in xb] + top), "names": {"bl": 0, "q1": 1, "bm": 2, "q3": 3,
                "br": 4, "tr": 5, "tm": 6, "tl": 7}, "marks": {}, "lines": {}}
    neck = {"neck1": "bl>q1", "neck2": "q1>bm", "neck3": "bm>q3", "neck4": "q3>br"}
    seams = [[["collar:bl>q1", "collar:q1>bm", "collar:bm>q3", "collar:q3>br"],
              ["front.R:cf>hps", "back.R:hps>cb", "back.L:cb>hps", "front.L:hps>cf"]]]
    arcs = {"back.L": {"neck": "cb>hps"}, "back.R": {"neck": "hps>cb"}, "front.L": {"neck": "hps>cf"},
            "front.R": {"neck": "cf>hps"}}
    folds, stiff = [], ["collar"]
    if band:
        pcs["collar"] = strip("collar", 0.03, 1.0)
        pcs["fall"] = strip("fall", 0.038, f)
        seams.append(["fall:bl>bm>br", "collar:tl>tm>tr"])
        arcs["collar"] = dict(neck, top="tl>tm>tr")
        arcs["fall"] = {"stand": "bl>bm>br", "outer": "tl>tm>tr"}
        stiff.append("fall")
    else:
        pcs["collar"] = strip("collar", 0.07, f)
        arcs["collar"] = dict(neck, outer="tl>tm>tr")
        if fold:
            folds.append({"name": "roll", "piece": "collar", "kind": "roll", "line": {"edge": "bl>bm>br", "offset": 0.025}})
    B = {"pieces": pcs, "seams": seams, "edge_arcs": arcs, "folds": folds}
    decl = {"pieces": {"collar": {"role": "collar_band" if band else "collar_fall"}}, "stiff": stiff}
    return B, decl


def test_a_falls_outer_edge_is_judged_where_it_lands():  # (s4-20: 558 mm against the 68 mm gorge read 8.230 PASS; C408)
    from hifipushie import draft_fall as df
    B, decl = _fall_B(1.0)
    r = df.row(B, decl, {"pieces": {}})
    T = r["detail"][0]["target"]
    assert abs(r["detail"][0]["d"] - 0.02) < 1e-3 and r["detail"][0]["line"] > r["detail"][0]["neck"], r
    W = r["detail"][0]["N"]
    ok = df.row(*_fall_B(T / W), {"pieces": {}})
    assert ok["status"] == "PASS" and abs(ok["detail"][0]["ratio"] - 1) < 0.01, ok
    long = df.row(*_fall_B(1.12 * T / W), {"pieces": {}})
    assert long["status"] == "FAIL" and "straighten the collar" in long["why"], long
    short = df.row(*_fall_B(0.88 * T / W), {"pieces": {}})
    assert short["status"] == "FAIL" and "spread the collar" in short["why"], short
    nofold = df.row(*_fall_B(1.0, fold=False), {"pieces": {}})
    assert nofold["status"] == "INFO" and "declare the collar's roll fold" in nofold["value"], nofold


def test_a_shirt_collar_on_its_band_lands_on_the_band_seam_fall():  # (simon's 1.024 spread passes; the floor stays: C408)
    from hifipushie import draft_fall as df, draft_shape as ds
    B, decl = _fall_B(1.024, band=True)
    r = df.row(B, decl, {"pieces": {}})
    D = r["detail"][0]
    assert r["status"] == "PASS" and abs(D["d"] - 0.008) < 1e-3, r
    assert "collar's height and fall's depth" in r["value"], r
    fl = {x["id"]: x for x in ds.rows(B, decl, {"pieces": {}})}
    assert fl["shape_fall"]["status"] == "PASS" and "fall_landing" in " ".join(fl), fl
    assert df.row(*_fall_B(1.0, band=True), {"pieces": {}})["status"] == "PASS"  # (inside 4 %: the floor rejects it)
    assert {x["id"]: x for x in ds.rows(*_fall_B(1.0, band=True), {"pieces": {}})}["shape_fall"]["status"] == "FAIL"


def test_a_fold_line_point_the_part_hasnt_is_refused_by_declaration_with_nearest_names():  # (s4-20; C408)
    import pytest
    from hifipushie import pattern
    pc = {"name": "collar", "P": np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float), "names": {"rollL": 0, "rollR": 1},
          "marks": {"rollCb": np.array([0.5, 0.3])}, "lines": {"rollLine": np.array([[0, 0.2], [0.5, 0.3], [1, 0.2]])}}
    with pytest.raises(KeyError) as e:
        pattern.fold_line({"collar": pc}, {"name": "collar_roll", "piece": "collar", "line": ["rollR", "rollCbTop", "rollL"]})
    m = str(e.value)
    assert m.startswith("folds 'collar_roll' on collar") and "snippets" in m and "rollCb" in m.split("nearest:")[1], m
    assert "rollLine" in m and not m.startswith("'"), m
    with pytest.raises(KeyError) as e:
        pattern.arc_indices(pc, "rollL>rolR")
    assert "nearest: rollR" in str(e.value) and "outline" in str(e.value), str(e.value)


def test_a_fold_line_may_be_a_curved_path_of_the_part():  # (s4-20: a roll line given as 3 points made a V; C408)
    from hifipushie import draft_shape as ds, pattern
    pc = {"name": "collar", "P": np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float), "names": {"a": 0, "b": 1}, "marks": {},
          "lines": {"rollLine": np.array([[0.01, 0.2]] + [[x, 0.3 - 0.1 * (2 * x - 1) ** 2] for x in np.linspace(0.1, 0.9, 9)]
                                         + [[0.99, 0.2]])}}
    L = pattern.fold_line({"collar": pc}, {"name": "roll", "piece": "collar", "line": "rollLine"})
    assert len(L) > 20 and abs(L[:, 0].min()) < 1e-6 and abs(L[:, 0].max() - 1) < 1e-6 and L[:, 1].max() > 0.29
    assert ds._line({"pieces": {"collar": pc}, "edge_arcs": {}}, "collar", "rollLine") is not None


def test_a_dart_the_inventory_builds_is_drafted_not_marked():
    """C410: trial s4-21 declared step 1's front fish dart as a mark only; the forepart had no shaping and all rows passed."""
    from hifipushie import draft_darts_inv as ddi
    step1 = {"details": {"front_dart.L": {"what": "front fish dart: waist suppression", "on": ["front.L"], "build": "full"},
                         "pocket.L": {"what": "flap pocket", "on": ["front.L"]},
                         "tuck": {"what": "a pleat", "kind": "dart", "on": ["back"], "build": "omit"}}}
    r = ddi.row(step1, {"darts": []})
    assert r["status"] == "FAIL" and "front_dart.L on front.L" in r["why"] and "1 inventory darts" in r["value"]
    assert ddi.row(step1, {"darts": [{"piece": "front", "legs": ["a", "b"]}]})["status"] == "PASS"
    assert ddi.row({"details": {"pocket.L": {"what": "flap pocket"}}}, {}) is None


def test_a_notch_outside_its_piece_fails_one_inside_is_listed():
    """C412: s4-22's facing and canvas carried the front's notches, up to 275 mm off them; every row passed."""
    from hifipushie import draft_notches as dn
    pc = _rect("facing", 0.1, 0.5, {"bl": "a", "br": "b", "tr": "c", "tl": "d"})
    pc["marks"] = {"top-notch": [0.05, 0.5], "pocket-notch": [0.05, 0.25]}
    B = {"pieces": {"facing": pc}}
    r = dn.row(B)
    assert r["status"] == "INFO" and "facing:pocket-notch" in r["why"]
    pc["marks"]["waist-notch"] = [0.25, 0.3]
    r = dn.row(B)
    assert r["status"] == "FAIL" and "facing:waist-notch 150 mm" in r["why"] and r["back_to"] == "4"
