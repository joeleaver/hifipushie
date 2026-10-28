"""THE KIND'S CHECKLIST IS THE DESIGN INPUT (C243; trials.md lesson 3, "targets are inputs").

Blind trial agents wrote their pass conditions in their own logs, translated each into a block option or an op by
hand, ran, measured and nudged: a round per translation (tee t4: hip length 3 rounds in metres; shirt t7: lengthBonus
0.05 cut 17 cm, 7 rounds on the shirttail; hoodie t6: 4 rounds on the dropped shoulder). Now the brief's items are the
input (design.targets), one definition each (cloth_checklist.json design_targets), mapped to what makes them and
solved on the draft (design_targets), measured by the gate with the same definition (cloth_check.target_rows)."""

import copy
from types import SimpleNamespace

import numpy as np
import pytest

from hifipushie import cloth, cloth_check as cc, design_targets as dt, garment_design as gd, pattern_blocks as pb

from test_pattern_draft import MM as _MM

# the tapes the trials' bodies carry that the synthetic MM lacks, consistent with MM's own (the hip line waistToHips
# below the waist, the seat waistToSeat): the hps tapes down the back to each body level, the hps -> shoulder seam
MM = dict(_MM, hpsToHipLineBack=_MM["hpsToWaistBack"] + _MM["waistToHips"],
          hpsToSeatBack=_MM["hpsToWaistBack"] + _MM["waistToSeat"], hpsToCrotchBack=_MM["hpsToWaistBack"] + 270.0,
          hpsToShoulder=166.0, hpsToArmpitBack=240.0)
# the ease's one definition reads the body (cloth.sizing: the body's girth heights + its tapes): a body standing with
# its hps at 1.45 m, each level down the back's tapes
_H = 1.45
BODY = SimpleNamespace(m={"mm": MM}, at={"hps.L": np.array([0.08, 0.0, _H]),
                                         "chest_z": _H - MM["hpsToArmpitBack"] / 1000,
                                         "waist_z": _H - MM["hpsToWaistBack"] / 1000,
                                         "hips_z": _H - MM["hpsToHipLineBack"] / 1000 + 0.02,
                                         "seat_z": _H - MM["hpsToSeatBack"] / 1000})


def _draft(meas=MM):
    def f(g):
        try:
            return cloth.pieces(cloth._garment_for_sim(g), meas)
        except (RuntimeError, FileNotFoundError) as e:  # (no Node / FreeSewing pack and no cached draft)
            pytest.skip(f"FreeSewing unavailable: {e}")
    return f


def _solved(sheet):
    g = {"design": copy.deepcopy(sheet)}
    out = dt.solve(g, MM, _draft(), body=BODY)
    g["design"]["solved"] = out["solved"]
    return g, out


def test_every_item_has_one_definition_and_every_kind_lists_real_items():
    """One definition per item, used by the input, the draft, the gate and the review: units, what it is on the body,
    how the pattern is measured, what it sets, the review sentence; numeric items carry the gate's tolerance. Every
    kind's checklist names only real items with values in their units, and garment_reference's template covers them."""
    I = dt.items()
    for k, it in I.items():
        for f in ("type", "stage", "units", "definition", "pattern", "sets", "review"):
            assert it.get(f) not in (None, ""), (k, f)
        if it["type"] not in ("choice", "neckline"):
            assert it.get("tolerance", 0) > 0 or it["type"] == "hem", k
    kinds = dt.kinds_with_targets()
    assert {"tee", "hoodie", "shirt"} <= set(kinds)
    for kind in kinds:
        tg = gd.kb()["kinds"][kind]["targets"]
        for item, v in tg.items():
            assert item in I or item in dt.choice_items(kind), (kind, item)
            dt.normalise(item, v, kind)
        tpl = dt.template(kind)
        assert set(dt.kind_items(kind)) == set(tpl), kind
        assert tpl["chest_ease"]["range"], kind
    assert dt.template("jacket") == {}  # (no checklist yet: said, not guessed)


def test_unknown_items_and_bad_units_are_refused_with_the_kinds_list():
    """The C241 contract for targets: an unknown item names every item the kind takes with its units; a value in the
    wrong units says what the item takes; a kind with no checklist says which kinds have one."""
    from hifipushie.cloth import ClothError
    with pytest.raises(ClothError) as e:
        gd.validate({"kind": "tee", "targets": {"length": "hips"}})
    assert "body_length" in str(e.value) and "sleeve_length" in str(e.value) and "chest_ease" in str(e.value)
    with pytest.raises(ClothError) as e:
        gd.validate({"kind": "tee", "targets": {"body_length": "knees"}})
    assert "waist, hips, seat, crotch" in str(e.value)
    with pytest.raises(ClothError) as e:
        gd.validate({"kind": "tee", "targets": {"chest_ease": "10%"}})
    assert "fraction" in str(e.value)
    with pytest.raises(ClothError) as e:
        gd.validate({"kind": "jacket", "targets": {"body_length": "seat"}})
    assert "no target checklist" in str(e.value) and "tee" in str(e.value)
    gd.validate({"kind": "hoodie", "targets": {"fit": "relaxed", "shoulder": "dropped", "pockets": "kangaroo"}})


def test_each_target_maps_to_what_makes_it():
    """The plan, before any body: lengths as body levels on the block (the band's height taken off by the solve), a
    short sleeve level on the sleeve op, the fit's chest ease, the crew neckline; a dropped shoulder is op
    drop_shoulder + the shoulder detail; a shirt drafts from Simon with the shirttail as its baseball hem and its
    numbers as FreeSewing options; an item a draft can't make is refused with the reason; an option the sheet gives
    itself overrides its target and is said."""
    e = dt.effective({"kind": "tee", "targets": {"body_length": "hips", "sleeve_length": "short"}})
    assert e["block_options"]["length"] == {"to": "hips", "below": 0.0}
    assert e["block_options"]["neckline"] == "crew" and e["block_options"]["chest_ease"] == 0.1  # regular: 4..16 %
    assert e["ops"][0]["op"] == "sleeve" and e["ops"][0]["length"] == "short"
    assert e["fit"] == "regular" and "targets" not in e and dt.effective(e) is e  # (idempotent)
    e = dt.effective({"kind": "hoodie", "targets": {"fit": "relaxed", "shoulder": "dropped"}})
    assert e["ops"][0] == {"op": "drop_shoulder", "drop": 0.05} and e["details"]["shoulder"] == "dropped"
    assert e["details"]["cuff"]["generate"]["height"] == pytest.approx(0.13)  # 65 mm finished, folded
    comp = gd.compile_sheet({"kind": "hoodie", "targets": {"shoulder": 0.07}})["pattern"]
    assert [o for o in comp["ops"] if o["op"] == "drop_shoulder"] == [{"op": "drop_shoulder", "drop": 0.07}]
    e = dt.effective({"kind": "shirt", "targets": {"hem_shape": "shirttail"}})
    assert e["from"] == "simon" and e["details"]["hem"] == "shirttail"
    assert {"lengthBonus", "sleeveLengthBonus", "chestEase", "waistEase", "hipsEase", "cuffLength"} <= set(e["pattern"]["options"])
    assert gd.compile_sheet({"kind": "shirt", "targets": {"fit": "regular"}})["pattern"]["options"]["hemStyle"] == "baseball"
    with pytest.raises(dt.TargetError, match="set-in shoulder"):
        dt.plan({"kind": "shirt", "targets": {"shoulder": "dropped"}})
    with pytest.raises(dt.TargetError, match="straight from the chest"):
        dt.plan({"kind": "tee", "targets": {"waist_ease": 0.1}})
    p = dt.plan({"kind": "tee", "targets": {"body_length": "seat"}, "block_options": {"length": {"to": "hips", "below": 0.02}}})
    assert any("overrides" in o and "body_length" in o for o in p["overrides"])


def test_the_draft_solves_the_targets_and_the_gate_reads_the_same_items():
    """Round 1 passes the measurable items by construction: a tee, a relaxed dropped-shoulder hoodie with rib bands
    and a long-sleeve dress shirt with a shirttail, each from kind + targets only, solved on the average-male tape;
    the gate's rows (cloth_check.target_rows: the same definitions) all PASS on the solved draft. A length asked as a
    level is the FINISHED hem (the hoodie's rib band below the block's hem), a sleeve the finished sleeve (cuff + the
    drop included)."""
    sheets = [{"kind": "tee", "targets": {"fit": "regular", "body_length": "hips", "sleeve_length": "short",
                                          "neckline": "crew"}},
              {"kind": "hoodie", "targets": {"fit": "relaxed", "body_length": "hips", "shoulder": "dropped",
                                             "collar": "hood", "pockets": "kangaroo", "cuff": "rib", "hem": "rib_band"}},
              {"kind": "shirt", "targets": {"fit": "regular", "sleeve_length": "long", "collar": "shirt_collar",
                                            "hem_shape": "shirttail"}}]
    for sheet in sheets:
        g, out = _solved(sheet)
        assert not out["unreached"], (sheet["kind"], out["unreached"])
        assert out["drafts"] <= dt.MAX_DRAFTS + 1
        rows = cc.target_rows(out["Bp"], g, sheet["kind"], BODY)
        judged = [r for r in rows if r["status"] != "INFO"]
        assert judged and all(r["status"] == "PASS" for r in judged), (sheet["kind"], [r for r in judged if r["status"] != "PASS"])
        ids = {r["id"] for r in rows}
        assert {"target:body_length", "target:sleeve_length", "target:chest_ease", "target:shoulder"} <= ids
        gd.validate(g["design"])  # (the solved sheet saves)
    # the hoodie: band at the hip line, the block's hem one band height above it; the drop and the cuff in the sleeve
    g, out = _solved(sheets[1])
    M = dt.measure(out["Bp"], body=BODY)
    assert M["body_length"] == pytest.approx(MM["hpsToHipLineBack"] / 1000, abs=0.005)
    assert M["shoulder"] == pytest.approx(0.05, abs=0.003) and M["hem_band_height"] == pytest.approx(0.065, abs=0.001)
    assert out["solved"]["block_options.length.below"] == pytest.approx(-0.065, abs=0.002)


def test_a_target_the_sheet_overrides_is_measured_anyway():
    """An explicit option wins over its target (said in the reply) and the gate still measures the target: a FAIL row
    naming the override and the fix, never a silent pass."""
    sheet = {"kind": "tee", "targets": {"body_length": "seat"}, "block_options": {"length": {"to": "hips"}}}
    g, out = _solved(sheet)
    r = {x["id"]: x for x in cc.target_rows(out["Bp"], g, "tee", BODY)}["target:body_length"]
    assert r["status"] == "FAIL" and "overrides" in r.get("why", "") and r.get("fix")
    lines = dt.reply_lines(cc.target_rows(out["Bp"], g, "tee", BODY), out["plan"], out)
    assert any(ln.strip().startswith("OVERRIDE") for ln in lines)


def test_a_short_sleeve_has_no_elbow_below_its_hem():
    """The short sleeve's outline ran underarm -> the elbow (below the hem) -> back up to the hem: a spike on every
    short-sleeve tee (the sleeve read 275 mm long for 170). Above the elbow there are no elbow points."""
    B = pb.bodice(MM, {}, knit=True)
    S = pb.sleeve(MM, B, {"length": "short"})
    pc = S["pieces"]["sleeve"]
    P = pc["P"]
    assert "elbowF" not in pc["names"] and P[:, 1].min() == pytest.approx(P[pc["names"]["wristF"], 1])
    S = pb.sleeve(MM, B, {"length": "long"})
    assert "elbowF" in S["pieces"]["sleeve"]["names"]
