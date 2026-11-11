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


def test_neckline_standoff_known_answer():
    assert "hifipushie.cloth_check.neckline_standoff_mm" in validated.GATE_MEASURES
    assert validated.run(["hifipushie.cloth_check.neckline_standoff_mm"]) == {
        "hifipushie.cloth_check.neckline_standoff_mm": "ok"}


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


def test_form_refine_recipes():
    from hifipushie import pattern_form as pf
    assert pf.form_refine({"design": {"ops": [{"op": "neckline"}, {"op": "lapel"}]}}) is pf.FORM_REFINE_LAPEL
    assert pf.form_refine({"pattern": {"from": "simon"}}) is pf.FORM_REFINE_SHIRT
    own = [{"piece": "x", "h": 0.004}]
    assert pf.form_refine({"mesh_refine": own}) is own

