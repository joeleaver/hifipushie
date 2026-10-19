"""The pattern gate (cloth_check.pattern_gate; cloth_job.require_pattern_gate): no cloth sim of a drafted garment runs
without a PASS record for exactly its pattern + body. No sims, no renders: a fake rented remote stands in for the
GPU fleet, synthetic pieces for a draft. Run: /mnt/data/hifipushie/bin/slot uv run pytest tests/test_pattern_gate.py"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import numpy as np
import pytest

from hifipushie import cloth_check as cc, cloth_job, validated


def _panel(name, h):
    P = np.array([[0.0, 0.0], [0.0, h], [0.3, h], [0.3, 0.0]])
    return {"name": name, "P": P, "names": {"bl": 0, "tl": 1, "tr": 2, "br": 3}, "wrap": {"to": "torso"}, "marks": {}}


def _bp(h=0.5):
    return {"pieces": {"front": _panel("front", 0.5), "back": _panel("back", h)}, "seams": [("front:bl>tl", "back:bl>tl")]}


BODY = {"V": np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]), "F": [[0, 1, 2]]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("HIFIPUSHIE_PATTERN_GATE_DIR", str(tmp_path / "gate"))
    monkeypatch.delenv(cc.GATE_ENV_OVERRIDE, raising=False)
    monkeypatch.setenv("HP_SUBMIT_SIMS", "1")
    monkeypatch.setenv("HP_SKIP_PREFLIGHT", "1")
    # a fake rented solver: it leaves out.npz in the job folder (and counts its runs)
    remote = tmp_path / "rent.sh"
    remote.write_text("#!/bin/bash\necho run >> \"$1/ran\"\npython3 -c \"import numpy as np,sys; "
                      "np.savez(sys.argv[1]+'/out.npz', V=np.zeros((3,3)))\" \"$1\"\n")
    remote.chmod(remote.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("HIFIPUSHIE_ZOZO_REMOTE", str(remote))
    return tmp_path


def _job(tmp, Bp, name="m:jacket"):
    jd = cloth_job.write(tmp / "job" / "sim", {"name": name}, {"X": np.zeros((3, 3)), "F": np.array([[0, 1, 2]])})
    cloth_job.write_gate_keys(jd, {"pattern": cc.pattern_hash(Bp), "body": cc.body_hash(BODY), "name": name})
    return jd


def _record(Bp, rows, waive=None):
    keys = {"pattern": cc.pattern_hash(Bp), "body": cc.body_hash(BODY)}
    rec = cc.make_record("m", "jacket", "jacket", keys, rows, waive)
    cc.write_record(rec)
    return rec


def _submit(jd):
    return cloth_job.run_zozo(jd, lambda s: None, log=lambda *_: None)


def test_submit_refused_without_record(env):
    jd = _job(env, _bp())
    with pytest.raises(cloth_job.SimNotSubmitted, match="no pattern-gate record"):
        _submit(jd)
    assert not (jd / "ran").exists()


def test_submit_refused_without_gate_file(env):
    jd = cloth_job.write(env / "hand" / "sim", {"name": "x"}, {"X": np.zeros((3, 3))})
    with pytest.raises(cloth_job.SimNotSubmitted, match="pattern_gate.json"):
        _submit(jd)


def test_submit_allowed_with_pass_record(env):
    Bp = _bp()
    rec = _record(Bp, cc.gate_rows(Bp, []))
    assert rec["status"] == "PASS"
    jd = _job(env, Bp)
    d, _ = _submit(jd)
    assert (jd / "ran").exists() and d["V"].shape == (3, 3)


def test_submit_refused_when_pattern_changed(env):
    Bp = _bp()
    _record(Bp, cc.gate_rows(Bp, []))
    Bp2 = _bp()
    Bp2["pieces"]["front"]["P"] = Bp2["pieces"]["front"]["P"] + [[0.0, 0.0], [0.0, 0.0], [0.018, 0.0], [0.0, 0.0]]
    assert cc.pattern_hash(Bp2) != cc.pattern_hash(Bp)
    jd = _job(env, Bp2)
    with pytest.raises(cloth_job.SimNotSubmitted, match="no pattern-gate record"):
        _submit(jd)


def test_failing_record_names_its_rows(env):
    Bp = _bp(0.48)  # a plain seam 500 vs 480 mm: +4.2 % ease, outside +-1.5 %
    rows = cc.gate_rows(Bp, [{"id": "gorge_height", "stage": 3, "measure": "missing: no measure yet"}])
    rec = _record(Bp, rows)
    assert rec["status"] == "FAIL"
    jd = _job(env, Bp)
    with pytest.raises(cloth_job.SimNotSubmitted, match="FAIL seams; UNMEASURED gorge_height"):
        _submit(jd)


def test_override_logged(env, monkeypatch):
    Bp = _bp()
    jd = _job(env, Bp)
    monkeypatch.setenv(cc.GATE_ENV_OVERRIDE, "collar-redraft session in flight")
    _submit(jd)
    assert (jd / "ran").exists()
    log = [json.loads(x) for x in (jd / "pattern_gate_override.log").read_text().splitlines()]
    assert log[-1]["reason"] == "collar-redraft session in flight"
    assert (cc.gate_dir() / "overrides.jsonl").exists()
    rec = cc.read_record(cc.pattern_hash(Bp), cc.body_hash(BODY))
    assert rec["overrides"][-1]["reason"] == "collar-redraft session in flight" and not cc.passed(rec)


def test_unmeasured_items_reported_and_blocking():
    Bp = _bp()
    items = [{"id": "notch", "stage": 3, "measure": "missing: tailored collar sections"},
             {"id": "new_item", "stage": 3, "measure": "some_measure_nobody_wrote"},
             {"id": "fold_character", "stage": 5, "measure": "fold_level"},
             {"id": "chest_width", "stage": 2, "measure": "chest_width"}]
    rows = {r["id"]: r for r in cc.gate_rows(Bp, items, ctx=None)}
    assert rows["notch"]["status"] == "UNMEASURED" and rows["new_item"]["status"] == "UNMEASURED"
    assert rows["chest_width"]["status"] == "UNMEASURED"  # no placed rest / no reading: never a silent pass
    assert rows["fold_character"]["status"] == "SIM"
    assert cc.verdict(list(rows.values())) == "FAIL"
    w = {"notch": "x", "new_item": "x", "chest_width": "x"}
    assert cc.verdict(list(rows.values()), w) == "PASS_WAIVED"


def test_live_checklist_items_all_classified():
    from hifipushie import cloth_reference as cr
    for it in cr.checklist()["items"]:  # (new items, e.g. the collar ones, land here without a code change)
        assert cc.classify(it) in ("pattern", "flat", "worn", "later", "placed", "sim", "unmeasured")


def test_pattern_measure_rule():
    Bp = _bp()
    it = {"id": "neck_lie", "stage": 3, "pattern_measure": "neckline_standoff_mm", "target_mm": [0, 12], "tolerance": 3}
    ok = cc.gate_rows(Bp, [it], extra={"neckline_standoff_mm": {"median_mm": 10.0}})[-1]  # (after seams, truing)
    bad = cc.gate_rows(Bp, [it], extra={"neckline_standoff_mm": {"median_mm": 40.0}})[-1]
    assert ok["status"] == "PASS" and bad["status"] == "FAIL" and bad["miss"] == 28.0


def test_neckline_standoff_known_answer():
    assert "hifipushie.cloth_check.neckline_standoff_mm" in validated.GATE_MEASURES
    assert validated.run(["hifipushie.cloth_check.neckline_standoff_mm"]) == {
        "hifipushie.cloth_check.neckline_standoff_mm": "ok"}


def test_option_sources_warn_only():
    g = {"pattern": {"from": "draft", "ops": [{"op": "neckline", "widen": 0.018, "back": 0.035},
                                              {"op": "neckline", "widen": 0.01, "source": "Aldrich p.42"},
                                              {"op": "neckline"}]},
         "construct": {"collar_options": {"widen": 0.01}, "lapel_options": {"roll_top": 0.02, "source": "measured"}}}
    w = cc.option_sources(g)
    assert len(w) == 2, w
    assert "op 1 (neckline)" in w[0] and "widen=0.018" in w[0] and "back=0.035" in w[0]
    assert "collar_options" in w[1]


def test_source_key_is_inert():
    from hifipushie import cloth_made, pattern_draft as pd
    assert "source" not in cloth_made.options({"construct": {"source": "x", "collar_options": {"widen": 0.01, "source": "y"}}})["collar_options"]
    seen = {}
    pd.OPS["_probe"] = lambda D, **o: seen.update(o)
    try:
        pd.apply({}, [{"op": "_probe", "a": 1, "source": "book"}])
    finally:
        pd.OPS.pop("_probe")
    assert seen == {"a": 1}


def test_gate_places_on_the_dress_form():
    # (dress-garrett 2026-10-19) the gate measures the garment ASSEMBLED on the virtual dress form, not cloth.build's
    # place_only start (its neck point ~30 mm out of the body's HPS)
    import inspect
    src = inspect.getsource(cc.pattern_gate)
    assert "pattern_form.on_form" in src and "place_only" not in src
    sh = inspect.getsource(cc.pattern_sheet)
    assert 'res["A"]' in sh and "form_under" in sh


def test_form_refine_recipes():
    from hifipushie import pattern_form as pf
    assert pf.form_refine({"design": {"ops": [{"op": "neckline"}, {"op": "lapel"}]}}) is pf.FORM_REFINE_LAPEL
    assert pf.form_refine({"pattern": {"from": "simon"}}) is pf.FORM_REFINE_SHIRT
    own = [{"piece": "x", "h": 0.004}]
    assert pf.form_refine({"mesh_refine": own}) is own


def test_form_items_are_info_while_form_not_validated():
    """(dress-garrett 2026-10-19 muslin 1, codified C29) GATE ON WHAT'S PROVEN: while the dress form has not passed its
    own validation (cc.FORM_VALIDATED False), a row read on the form (a placed item, a worn collar item) is INFO with its
    form reading kept, neither blocking nor passing; the flat rows (seams, truing, flat readings) still block; a reading
    from the last validated drape blocks in place of the form's."""
    assert cc.FORM_VALIDATED is False  # (flip it only with the form's validation record, in the same commit)
    Bp = _bp()

    class Ctx:  # a placed rest stand-in (cloth_reference.measure fails on it: the row would be UNMEASURED)
        pass
    items = [{"id": "waist_suppression", "stage": 2, "measure": "waist_width", "target_mm": [380, 420]},
             {"id": "collar_hug_side", "stage": 4, "measure": "missing: worn sections", "gate": "worn"},
             {"id": "wear_age", "stage": 5, "measure": "missing: paint", "gate": "later"},
             {"id": "collar_stand", "stage": 3, "measure": "missing: x", "flat_measure": "collar_stand_cb_mm",
              "flat_target": [25, 30]}]
    off = {r["id"]: r for r in cc.gate_rows(Bp, items, ctx=Ctx(), form_ok=False,
                                             flat={"collar_stand_cb_mm": {"value": 29.0}})}
    assert off["waist_suppression"]["status"] == "INFO" and "form_status" in off["waist_suppression"]
    assert off["collar_hug_side"]["status"] == "INFO" and off["wear_age"]["status"] == "INFO"
    assert off["collar_stand"]["status"] == "PASS" and off["collar_stand"]["read_on"] == "flat draft"
    assert cc.verdict(list(off.values())) == "PASS"
    on = {r["id"]: r for r in cc.gate_rows(Bp, items, ctx=Ctx(), form_ok=True, flat={})}
    assert on["waist_suppression"]["status"] == "UNMEASURED" and on["collar_hug_side"]["status"] == "UNMEASURED"
    assert on["collar_stand"]["status"] == "UNMEASURED"  # a flat item with no flat reading blocks
    bad = cc.gate_rows(Bp, items[3:], form_ok=False, flat={"collar_stand_cb_mm": {"value": 11.0}})[-1]
    assert bad["status"] == "FAIL"
    dr = {"source": "validated drape x", "rows": {"waist_suppression": {"status": "FAIL", "ours": 368}}}
    r = {x["id"]: x for x in cc.gate_rows(Bp, items[:1], ctx=Ctx(), form_ok=False, drape=dr)}
    assert r["waist_suppression"]["status"] == "FAIL" and r["waist_suppression"]["read_on"] == "validated drape"


def test_collar_draft_read_flat():
    """cloth_check.collar_draft on a drafted tailored collar (stand 30 / fall 45): stand at CB as drafted, tapering
    without a rise to ~0 where the roll line meets the neck edge."""
    from test_collar import _notched
    cd = cc.collar_draft(_notched())
    assert cd and abs(cd["stand_cb_mm"] - 30.0) < 1.0 and cd["stand_end_mm"] < 1.0 and cd["tapers"], cd


def test_gate_form_switch_reads_the_validation_record(tmp_path, monkeypatch):
    """(virtual fit validation 2, 2026-10-19) The gate's form switch is cloth_check.form_validated(): FORM_VALIDATED (a
    manual override) OR pattern_form.form_validated() (its VALIDATED flag AND a record whose rows all pass). A failing
    record or a missing one reads False even with the flag set; a passing record + the flag reads True."""
    import json
    from hifipushie import pattern_form as pf
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(json.dumps({"validated": True, "rows": []}))
    bad.write_text(json.dumps({"validated": False, "rows": []}))
    assert cc.FORM_VALIDATED is False
    monkeypatch.setattr(pf, "VALIDATED", True)
    monkeypatch.setattr(pf.form_validated, "__defaults__", (str(bad),))
    assert cc.form_validated() is False
    monkeypatch.setattr(pf.form_validated, "__defaults__", (str(tmp_path / "missing.json"),))
    assert cc.form_validated() is False
    monkeypatch.setattr(pf.form_validated, "__defaults__", (str(good),))
    assert cc.form_validated() is True
    monkeypatch.setattr(pf, "VALIDATED", False)
    assert cc.form_validated() is False
