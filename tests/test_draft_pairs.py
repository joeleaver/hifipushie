"""F3: cut pairs at step 4 (draft_pairs): a half / sideless piece refused at the draft with the pair declaration; a pair
expands to NAME.L + NAME.R with its seams per side; a folded centre piece's other half sewn to the other copy."""
import pytest

from hifipushie import draft_own as do, draft_pairs as dp


def _part(pts, order):
    """A FreeSewing part (mm, y down) whose seam runs through the named points in order."""
    ops = [{"type": "move", "to": pts[order[0]]}] + [{"type": "line", "to": pts[k]} for k in order[1:]] + \
        [{"type": "line", "to": pts[order[0]]}]
    return {"points": dict(pts), "paths": {"seam": {"ops": ops}}}


PARTS = {
    # a front half: CF at x = 0, side at x = 250 (lies wholly on one side: half a garment)
    "t.front": _part({"cfn": [0, 0], "sn": [250, 0], "sh": [250, 600], "cfh": [0, 600]}, ["cfn", "cfh", "sh", "sn"]),
    # a back half drafted for the fold at x = 0
    "t.back": _part({"cbn": [0, 0], "sn": [250, 0], "sh": [250, 600], "cbh": [0, 600]}, ["cbn", "cbh", "sh", "sn"]),
    # a sleeve: a centred flat sewn to itself
    "t.sleeve": _part({"a": [-150, 0], "b": [150, 0], "c": [120, 500], "d": [-120, 500]}, ["a", "d", "c", "b"]),
}
STEP1 = {"pieces": {"front": {"build": "full"}, "back": {"build": "full"}, "sleeve": {"build": "full"}}, "seams": []}


def _decl(**front):
    return {"pieces": {"front": dict({"part": "t.front", "place": {"to": "torso", "side": "front"}}, **front),
                       "back": {"part": "t.back", "fold": "x0", "place": {"to": "torso", "side": "back"}},
                       "sleeve": {"part": "t.sleeve", "place": {"to": "arm"}}},
            "edges": {"front": {"side": "sn>sh", "neck": "cfn>sn"}, "back": {"side": "sn>sh", "neck": "cbn>sn"},
                      "sleeve": {"ua": "a>d", "ub": "b>c"}},
            "seams": [{"a": "front:side", "b": "back:side"}, {"a": "front:neck", "b": "back:neck"},
                      {"a": "sleeve:ua", "b": "sleeve:ub"}]}


def test_a_half_piece_and_a_sideless_limb_are_refused_with_the_pair_declaration():
    bad = dp.faults(_decl(mirror=True), PARTS, STEP1)
    assert any("'front': half a garment" in b and 'pieces.front {"pair": true}' in b for b in bad), bad
    assert any("'sleeve': a limb piece with no side" in b and 'pieces.sleeve {"pair": true}' in b for b in bad), bad
    assert not any("'back'" in b for b in bad)  # (cut on the fold: whole)


def test_validate_refuses_at_step_4_and_passes_once_paired():
    d = _decl(mirror=True)
    bad = do.validate(d, STEP1, PARTS)
    assert any('"pair": true' in b for b in bad)
    d["pieces"]["front"] = {"part": "t.front", "pair": True, "place": {"to": "torso", "side": "front"}}
    d["pieces"]["sleeve"]["pair"] = True
    assert do.validate(d, STEP1, PARTS) == []


def test_a_pair_expands_per_side_and_a_folded_half_goes_to_the_other_copy():
    d = _decl(pair=True)
    d["pieces"]["sleeve"]["pair"] = True
    D = dp.expand(d, PARTS)
    assert {"front.L", "front.R", "sleeve.L", "sleeve.R", "back"} == set(D["pieces"])
    assert D["pieces"]["front.L"].get("mirror", False) != D["pieces"]["front.R"].get("mirror", False)
    assert D["pieces"]["sleeve.L"]["place"]["to"] == "arm.L" and D["pieces"]["sleeve.R"]["place"]["to"] == "arm.R"
    pairs = {(s["a"], s["b"]) for s in D["seams"]}
    assert ("front.L:side", "back:side") in pairs and ("front.R:side", "back:side.m") in pairs
    assert ("sleeve.L:ua", "sleeve.L:ub") in pairs and ("sleeve.R:ua", "sleeve.R:ub") in pairs
    assert D["edges"]["back"]["side.m"] == {"mirror_of": "side"}
    from hifipushie import pattern
    pc = pattern.from_freesewing(PARTS["t.back"], "back", fold="x0")
    m = dp.mirror_arc(pc, "sn>sh")
    assert m == "sn.m>sh.m"
    P = pc["P"]
    assert abs(P[pc["names"]["sn.m"]][0] + P[pc["names"]["sn"]][0]) < 1e-9


def test_a_seam_between_the_two_copies_and_a_whole_pair_refused():
    d = _decl(pair=True)
    d["seams"].append({"a": "front:neck", "b": "front:neck"})
    D = dp.expand(d, PARTS)
    assert {"a": "front.L:neck", "b": "front.R:neck"} in D["seams"]
    d["pieces"]["back"] = {"part": "t.sleeve", "pair": True, "place": {"to": "torso", "side": "back"}}
    d["seams"] = []
    assert any("'back': \"pair\": true but its flat is whole" in b for b in dp.faults(d, PARTS, STEP1))


def test_a_folded_piece_closed_on_its_own_end_closes_end_to_mirrored_end():
    d = _decl(pair=True)
    d["closures"] = [{"name": "fly", "over": "back", "under": "back", "edge": {"over": "side", "under": "side"}}]
    D = dp.expand(d, PARTS)
    assert D["closures"][0]["edge"] == {"over": "side", "under": "side.m"}
