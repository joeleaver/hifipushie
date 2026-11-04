"""body_tape (garment step 3): measuring a body by name. The by-name tapes equal tailor.measure's for the same
measurements on two real bodies, jacket measurements tailor doesn't take are sane, refusals name the fix, and the tool
writes step 3 of the garment record with its look.

Needs the workspace models wf_simon and dg_garrett (HIFIPUSHIE_HOME, as test_garment_pull); skipped without them."""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from hifipushie import body_tape as bt

HOME = Path(os.environ.get("HIFIPUSHIE_HOME") or "/home/joe/dev/hifipushie/workspace")
BODIES = ("wf_simon", "dg_garrett")
_CACHE: dict = {}


def _body(m):
    if not (HOME / m / "spec.json").exists():
        pytest.skip(f"no workspace model {m} under {HOME}")
    if m not in _CACHE:
        from hifipushie import cloth, store
        old = store.HOME
        store.HOME = HOME
        try:
            spec = store.load(m)
            _CACHE[m] = (spec, cloth.model_body(m, spec, {}))
        finally:
            store.HOME = old
    return _CACHE[m]


@pytest.fixture(scope="module", params=BODIES)
def tape(request):
    _, b = _body(request.param)
    return bt.Tape(b["V"], b["F"], b["J"])


def test_by_name_equals_tailor(tape):
    mm = tape.R["mm"]
    same = [  # (by-name item, tailor's measurement)
        ({"kind": "girth", "at": "chest"}, "chest"),
        ({"kind": "girth", "at": "waist"}, "waist"),
        ({"kind": "girth", "at": "hips"}, "hips"),
        ({"kind": "girth", "at": "seat"}, "seat"),
        ({"kind": "girth", "at": "high_hip"}, "highHip"),
        ({"kind": "girth", "square_to": "arm.L", "fullest": [0.25, 0.75]}, "biceps"),
        ({"kind": "arc", "from": "shoulder_point.L", "to": "shoulder_point.R", "over": "back", "taut": False},
         "shoulderToShoulder"),
        ({"kind": "length", "from": "hps.L", "down_to": "waist", "side": "back"}, "hpsToWaistBack"),
        ({"kind": "length", "from": "hps.L", "down_to": "armpit", "side": "back"}, "hpsToArmpitBack"),
        ({"kind": "length", "from": "shoulder_point.L", "via": ["elbow.L"], "to": "wrist.L", "over": "straight"},
         "shoulderToWrist"),
        ({"kind": "height", "from": "waist", "to": "floor"}, "waistToFloor"),
        ({"kind": "height", "from": "waist", "to": "seat"}, "waistToSeat"),
        ({"kind": "height", "from": "armpit", "to": "waist"}, "waistToArmpit"),
    ]
    for i, (it, fs) in enumerate(same):
        r = tape.take(dict(it, name=f"m{i}"))
        assert abs(r["mm"] - mm[fs]) <= 0.15, (fs, r["mm"], mm[fs], r["how"])
        assert r["how"] and f"m{i}" in tape.lines
    # FreeSewing names: tailor's value, in FreeSewing's definition (hips is the iliac crest: measure_defs' adapter)
    assert tape.take("chest")["mm"] == mm["chest"]
    assert tape.take("hips")["mm"] == pytest.approx(mm["highHip"], abs=0.1)
    assert tape.take({"name": "hips_own", "kind": "freesewing", "measure": "hips", "consumer": None})["mm"] == mm["hips"]


def test_jacket_measurements_tailor_lacks(tape):
    mm = tape.R["mm"]
    # back waist to the seat over the surface: at least the vertical drop, not much more (the seat's curve)
    r = tape.take({"name": "back_waist_to_seat", "kind": "length", "from": "cb_waist", "to": "cb_seat", "side": "back"})
    assert mm["waistToSeat"] <= r["mm"] <= 1.35 * mm["waistToSeat"], (r, mm["waistToSeat"])
    # armhole depth: shoulder point down to the armpit level (adult men: ~10-25 cm)
    r = tape.take({"name": "armhole_depth", "kind": "height", "from": "shoulder_point.L", "to": "armpit"})
    assert 100 <= r["mm"] <= 250, r
    # across back at the armpit, over the surface, taut: shorter than half the chest + a bit, longer than its width
    r = tape.take({"name": "across_back", "kind": "arc", "from": "side_armpit.L", "to": "side_armpit.R", "over": "back"})
    w = 2 * tape.point("side_armpit.L")[0] * 1000
    assert w < r["mm"] < 0.7 * mm["chest"], (r, w)
    # a limb girth at a named place and a level between two levels
    r = tape.take({"name": "elbow_g", "kind": "girth", "square_to": "forearm.L", "t": 0.1})
    assert 180 < r["mm"] < 400, r
    r = tape.take({"name": "mid", "kind": "girth", "at": {"between": ["waist", "chest"], "t": 0.5}})
    assert min(mm["waist"], mm["chest"]) - 60 < r["mm"] < max(mm["waist"], mm["chest"]) + 60, r
    lm = tape.landmarks()
    assert lm["cb_waist"]["surface"] and not lm["elbow.L"]["surface"] and "how" in lm["hps.L"]
    assert np.allclose(lm["hps.R"]["pos"], lm["hps.L"]["pos"] * [-1, 1, 1])


@pytest.mark.parametrize("item,says", [
    ({"kind": "girth", "at": "belly"}, ["unknown level 'belly'", "shoulder_point.L", "waist"]),
    ({"kind": "girth", "at": {"z": 2.5}}, ["outside the body (floor"]),
    ({"kind": "arc", "from": "elbow.L", "to": "wrist.L"}, ["not on the surface", "straight"]),
    ({"kind": "arc", "from": "nape", "to": "cb_waist"}, ["unknown landmark 'nape'", "cb_neck"]),
    ({"kind": "spiral"}, ["one of girth, arc, length, height, freesewing"]),
    ({"kind": "freesewing", "measure": "chestFull"}, ["not a FreeSewing measurement", "hpsToWaistBack"]),
    ({"kind": "girth", "square_to": "tail"}, ["square_to 'tail'", "arm.L"]),
    ({"kind": "length", "from": "cb_waist", "down_to": "chest"}, ["is not below"]),
])
def test_refusals_name_the_fix(item, says):
    _, b = _body("wf_simon")
    tp = _CACHE.setdefault("tape_wf_simon", bt.Tape(b["V"], b["F"], b["J"]))
    with pytest.raises(bt.TapeError) as e:
        tp.take(dict(item, name="x"))
    for s in says:
        assert s in str(e.value), (s, str(e.value)[:300])


def test_tool_writes_step3(tmp_path, monkeypatch):
    from hifipushie import cloth, garment_record as gr, server, store
    spec, b = _body("wf_simon")
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setenv("HIFIPUSHIE_APPROVED", str(tmp_path / "approved.json"))
    monkeypatch.setattr(store, "load", lambda name: spec)
    monkeypatch.setattr(cloth, "model_body", lambda *a, **k: b)
    items = ["chest", {"name": "back_waist_to_seat", "kind": "length", "from": "cb_waist", "to": "cb_seat", "side": "back"},
             {"name": "bad", "kind": "girth", "at": "belly"}]
    # step 2 not ready: measured and drawn, the record refuses by name
    look, txt = bt.run("wf_simon", items, garment="hussar")
    assert Path(look).exists() and "record: refused" in txt and "step 2" in txt and "REFUSED bad" in txt
    for sid in ("0", "1", "2"):  # (steps 0-2 stubbed as done; step 1 names what its seams need)
        gr.write("wf_simon", "hussar", sid, "done", output={"n": sid} if sid != "1" else {"measurements": ["chest", "loop"]})
    out = server.body_tape("wf_simon", items, garment="hussar")  # (C355: a name step 1 calls for is missing)
    assert "record: refused: step 3 not written: step 1 names loop" in out[1], out[1]
    items.append({"name": "loop", "kind": "sum", "of": ["chest", "back_waist_to_seat"]})
    out = server.body_tape("wf_simon", items, garment="hussar")
    assert isinstance(out, list) and "record: step 3 (measure) written" in out[1]
    st = gr.load("wf_simon", "hussar")["steps"]["3"]
    assert st["status"] == "done" and st["look"] == [str(gr.look_dir("wf_simon", "hussar") / "step3_measure.png")]
    names = [r["name"] for r in st["output"]["measurements"]]
    assert names == ["chest", "back_waist_to_seat", "loop"] and st["output"]["refused"]
    m = {r["name"]: r["mm"] for r in st["output"]["measurements"]}
    assert m["loop"] == round(m["chest"] + m["back_waist_to_seat"], 1)
    rows = st["output"]["measurements"]  # (F4: where each was taken: a girth's loop, a length's path)
    assert len(rows[0]["loop"]) > 8 and len(rows[1]["path"]) >= 2
    assert gr.states(gr.load("wf_simon", "hussar"))["3"]["ready"]
    # no measurements: the landmark list
    txt = server.body_tape("wf_simon")
    assert "shoulder_point.L" in txt and "levels:" in txt and "joints" in txt


def test_takes_is_every_name_tailor_measures():
    """body_tape.TAKES (garment_plan step 1's vocabulary, F2) is exactly tailor.measure's FreeSewing-named keys."""
    import re
    from pathlib import Path
    from hifipushie import body_tape as bt, tailor
    src = Path(tailor.__file__).read_text()
    assert set(bt.TAKES) == set(re.findall(r'mm\["([A-Za-z]+)"\]', src))
    assert "closest: hpsToShoulder" in bt.name_errors(["hpsToShoulders"])[0] and not bt.name_errors(["neck", "x"], {"x": "arc"})


def test_every_measurement_keeps_where_it_was_taken(tape):
    """F4: legs too: a leg girth's loop lies on the measured (+X) side; a vertical length's path spans its value."""
    from hifipushie import tape_geom as tg
    for nm in ("upperLeg", "knee", "inseam", "waistToFloor", "waist"):
        r = tape.take(nm)
        g = tg.geometry(tape, dict(r, measure=nm))
        if nm in ("upperLeg", "knee", "waist"):
            L = np.asarray(g["loop"])
            assert abs(np.linalg.norm(np.diff(L, axis=0), axis=1).sum() * 1000 - r["mm"]) < 0.03 * r["mm"]
            assert (L[:, 0].min() > 0.01) == (nm != "waist")
        else:
            P = np.asarray(g["path"])
            assert abs(np.ptp(P[:, 2]) * 1000 - r["mm"]) < 0.03 * r["mm"] + 10  # (the sole is not sliced)


def test_surface_tapes_stay_on_the_body_either_way(tape):  # (t s3-2: a chord through the shoulder, a tape over the head)
    from hifipushie import tape_checks as tc
    a = {"name": "x", "kind": "arc", "from": "shoulder_point.L", "to": "side_armpit.L", "over": "front"}
    b = dict(a, **{"from": "side_armpit.L", "to": "shoulder_point.L"})
    ra, rb = tape.take(a), tape.take(b)
    assert abs(ra["mm"] - rb["mm"]) < 1.0, (ra["mm"], rb["mm"])  # (the same tape in either direction)
    p, q = (tape.point(n, need_surface=True) for n in ("shoulder_point.L", "side_armpit.L"))
    chord = float(np.linalg.norm(q - p)) * 1000
    assert ra["mm"] > chord + 10 and tc.inside(tape, np.array([p, q]))  # (not the chord, which cuts the body)
    top = tape.take({"name": "s", "kind": "arc", "from": "hps.L", "to": "shoulder_point.L", "over": "top"})
    h, s = (tape.point(n, need_surface=True) for n in ("hps.L", "shoulder_point.L"))
    assert top["mm"] < tc.LONG_X * float(np.linalg.norm(s - h)) * 1000  # (along the shoulder, not over the head)


def test_an_adapted_name_draws_the_tape_it_came_from(tape):  # (t s3-2: hips = the iliac crest, drawn at the hip joint)
    from hifipushie import tailor
    r = tape.take("hips")
    L = tape.lines["hips"]
    assert abs(tailor.length(np.r_[L, L[:1]]) * 1000 - r["mm"]) < 0.03 * r["mm"]


def test_a_tape_down_the_back_keeps_its_line(tape):  # (t s3-2: it hopped across the spine's groove, adding length)
    r = tape.take({"name": "bl", "kind": "length", "from": "cb_neck", "down_to": "crotch", "side": "back"})
    P = tape.lines["bl"]
    assert float(np.ptp(P[:, 0])) < 1e-6 and r["mm"] > 0
