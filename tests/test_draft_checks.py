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
