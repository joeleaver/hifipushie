"""The caves checked in the terrain's report, before any export (the consumer's island: two of three caves failed the
tile export's walk an hour after the spec was saved). A small synthetic hillside with a karst cave: one passage gentle
enough to walk, one too steep, each told in the spec's terms. uv run python tests/test_caves_early.py"""
import json
import tempfile
import time
from pathlib import Path

import numpy as np

from hifipushie import terrain, terrain_caves, terrain_mesh as tm

SPEC = {"world": {"kind": "coast", "base": 10}, "extent": [[0, 0], [160, 160]], "cell": 2,
        "tilt": {"down": "south", "grade": 0.4},
        "sea": {"level": 0, "shore": "cliffs", "cliffs": {"height": [10, 14]}},
        "cover": [{"type": "meadow", "in": "everywhere"}],
        "caves": {"grotto": {"kind": "karst", "width": 4, "height": 4,
                             "entrances": {"mouth": {"at": [80, 70]}},
                             "chambers": {"low": {"at": [80, 120], "depth": 14, "size": [8, 5]},
                                          "high": {"at": [130, 140], "depth": 14, "size": [8, 5]}},
                             "passages": [["mouth", "low"], ["low", "high"]]}}}


def _terrain(spec):
    d = Path(tempfile.mkdtemp())
    (d / "spec.json").write_text(json.dumps(spec))
    return terrain.load(d / "spec.json")


def _place(T):
    """Chambers' z for this build: `low` a gentle climb from the mouth, `high` a steep one from `low`."""
    caves, _ = terrain_caves.light_field(T)
    mouth = caves[0].nodes["mouth"]
    spec = json.loads(json.dumps(T.source))
    spec["caves"]["grotto"]["chambers"]["low"] = {"at": [80, 120], "z": round(mouth["z"] + 2.0, 1), "size": [8, 5]}
    spec["caves"]["grotto"]["chambers"]["high"] = {"at": [130, 140], "z": round(mouth["z"] + 16.0, 1),
                                                   "size": [8, 5]}
    return spec


def test_report_walks_the_caves(T):
    t = time.time()
    rep = T.report()
    took = time.time() - t
    assert "caves (walked now" in rep, rep
    lines = rep.splitlines()
    low = next(l for l in lines if "grotto mouth -> low" in l)
    high = next(l for l in lines if "grotto low -> high" in l)
    assert "PASSES" in low, low
    warn = [l for l in lines if l.strip().startswith("cave grotto: low -> high")]
    assert warn and "too steep to walk" in warn[0], (high, warn)
    # the fix in the spec's terms: the chamber lower, with a z to give, or a longer passage
    assert "put high lower" in warn[0] and '"z":' in warn[0] and "make the passage longer" in warn[0], warn[0]
    assert not any(l.strip().startswith("cave grotto: mouth -> low") and "steep" in l for l in lines), lines
    return took


def test_survey_numbers(T):
    caves, _ = terrain_caves.light_field(T)
    sv = {(p["from"], p["to"]): p for p in terrain_caves.survey(T, caves)}
    hi = sv[("low", "high")]
    assert abs(hi["rise"] - 14.0) < 3.0, hi["rise"]  # (karst floors snap to the rock's beds)
    assert hi["grade"] > terrain_caves.GRADE_WALK
    assert sv[("mouth", "low")]["grade"] < terrain_caves.GRADE_WALK


def test_same_verdict_as_the_full_field(T):
    """The light field (no rock character) walks to the same verdicts as the export's field."""
    caves, light = terrain_caves.light_field(T)
    a = terrain_caves.check(caves, light, sea=tm._sea(T))
    full, _, _, caves2 = tm.build_field(T, dict(tm.DEFAULTS))
    b = terrain_caves.check(caves2, full, sea=tm._sea(T))
    assert [("PASSES" in x) for x in a] == [("PASSES" in x) for x in b], (a, b)


def test_flow_length_is_metres():
    class L:
        props = {"length": 640.0}
        xy = np.array([[0.0, 0.0], [1.0, 0.0]])
    assert terrain_caves._line_length(L) == 640.0


if __name__ == "__main__":
    T0 = _terrain(SPEC)
    T = _terrain(_place(T0))
    test_flow_length_is_metres()
    took = test_report_walks_the_caves(T)
    print(f"report with caves {took:.1f} s")
    test_survey_numbers(T)
    test_same_verdict_as_the_full_field(T)
    print("ok")
