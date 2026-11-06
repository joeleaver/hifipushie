"""garment_plan (T4): steps 0-2 of the garment record for any garment. Refusals by name, record writes, the looks drawn
over the reference, the tool through the server. Cheap: a generated picture, no renders."""
import asyncio
import copy

import pytest
from PIL import Image

from hifipushie import garment_fit as gf, garment_plan as gp, garment_record as gr, server, store

# a synthetic body (mm): the fit's ratios are applied to it (garment_fit.DictBody)
BODY = {"chest": {"girth_mm": 1000.0, "width_mm": 330.0, "z_mm": 1300.0},
        "waist": {"girth_mm": 800.0, "width_mm": 280.0, "z_mm": 1100.0},
        "knee": {"girth_mm": 360.0, "width_mm": 100.0, "z_mm": 500.0},
        "floor": {"girth_mm": 0.0, "width_mm": 0.0, "z_mm": 0.0}}


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setenv("HIFIPUSHIE_APPROVED", str(tmp_path / "approved.json"))
    im = Image.new("RGB", (200, 300), (40, 40, 200))
    im.paste((200, 30, 30), (50, 50, 150, 250))
    im.save(tmp_path / "ref.png")
    monkeypatch.setattr(gf, "body_for", lambda model: gf.DictBody(BODY))
    return tmp_path


def _read(home):
    return {"kind": "a waistcoat", "views": [{"image": str(home / "ref.png"), "view": "front"}],
            "cloth": {"shell": {"fabric": "wool_suiting", "stiffness": "crisp", "colour": {"at": [[100, 150]], "view": 0},
                                "grain": "down CF"},
                      "trim": {"gsm": 300, "thickness_mm": 1.0, "stretch": "none", "stiffness": "stiff",
                               "colour": [210, 170, 60], "source": "braid convention", "grain": "along"}},
            "fit": {"view": "front", "landmarks": {"chest": 100, "waist": 150},
                    "widths": [{"at": "chest", "garment": [[50, 100], [150, 100]], "body": [[60, 100], [140, 100]],
                                "body_from": "inferred: the chest inside, from the shoulders"}],
                    "heights": [{"name": "hem", "at": 250}]}}


def _parts():
    return {"pieces": {"front.L": {"what": "front", "cloth": "shell", "seen": "seen", "build": "full", "stiff": False,
                                   "layer": 1, "edges": {"shoulder": [0, 1], "side": [1, 2], "hem": [2, 3], "cf": [3, 0]}, "free": ["hem"], "where": {"view": 0, "outline": [[100, 50], [150, 50], [150, 250], [100, 250]]}},
                       "front.R": {"what": "front", "cloth": "shell", "seen": "seen", "build": "full", "stiff": False,
                                   "layer": 1, "edges": {"shoulder": [0, 1], "side": [1, 2], "hem": [2, 3], "cf": [3, 0]}, "free": ["hem", "cf", "shoulder"], "where": {"view": 0, "outline": [[50, 50], [100, 50], [100, 250], [50, 250]]}},
                       "back": {"what": "back", "cloth": "shell", "seen": "occluded", "from": "a waistcoat back is one piece",
                                "build": "simplified", "why": "never seen", "stiff": False, "layer": 1,
                                "edges": ["side.L", "side.R", "shoulder.L", "shoulder.R", "hem", "neck"],
                                "free": ["shoulder.R", "hem", "neck"]}},
            "details": {"buttons": {"what": "buttons", "on": ["front.R"], "count": 5, "seen": "seen", "build": "full",
                                    "where": {"view": 0, "at": [[100, 80], [100, 120]]}},
                        "edge": {"what": "binding", "on": ["front.L"], "cloth": "trim", "follows": ["front.L:cf"],
                                 "seen": "seen", "build": "full", "where": {"view": 0, "outlines": [[[100, 50], [100, 250]]]}}},
            "closures": {"front": {"what": "buttons", "pieces": ["front.L", "front.R"], "details": ["buttons"]}},
            "seams": [{"a": "front.L:side", "b": "back:side.L", "length": {"body": ["armpit_to_waist"]}},
                      {"a": "front.R:side", "b": "back:side.R", "length": {"body": ["armpit_to_waist"]}},
                      {"a": "front.L:shoulder", "b": "back:shoulder.L", "length": {"style": {"ratio": 0.5, "of": "biceps",
                                                                                              "source": "front view"}}}],
            "define": {"armpit_to_waist": "length"}}


def _style():
    return {"state": {"front": {"state": "closed", "source": "front view"}},
            "bends": [{"id": "lie", "on": "front.L", "target": {"is": "flat"}, "source": "front view"}],
            "pose": {"name": "arms down", "source": "front view"},
            "rows": [{"id": "width", "what": "trim_lines_apart", "note": "the two binding lines apart",
                      "target": {"value": 0.5, "unit": "ratio", "of": "shoulder_width"},
                      "source": "front view", "view": 0, "at": [[50, 150], [150, 150]]}],
            "traces": [{"id": "hem", "what": "hem", "view": 0, "points": [[50, 250], [80, 250], [120, 250], [150, 250]],
                        "corners": [1], "source": "front view: the hem"}]}


def _refused(fn, *names):
    with pytest.raises(gp.PlanRefused) as e:
        fn()
    for n in names:
        assert n in str(e.value), (n, str(e.value))
    return str(e.value)


def test_read_fills_fabric_samples_colour_and_writes_step0(home):
    r = gp.write("m", "w", "read", _read(home))
    c = r["plan"]["cloth"]["shell"]
    assert c["gsm"] and c["thickness_mm"] and "garment_kb" in c["source"]
    assert c["colour"] == [200, 30, 30]  # (sampled off the picture, garment_from_reference's colour reading)
    rec = gr.load("m", "w")
    assert rec["steps"]["0"]["status"] == "done" and rec["steps"]["0"]["reference"].endswith("ref.png")
    assert rec["steps"]["0"]["look"] and all(map(lambda p: Image.open(p).size[0] > 900, rec["steps"]["0"]["look"]))


def test_read_refusals_by_name(home):
    bad = _read(home)
    bad["cloth"]["shell"]["fabric"] = "unobtainium"
    bad["fit"]["widths"][0]["at"] = "elbw"
    bad["views"][0]["view"] = "top"
    msg = _refused(lambda: gp.check_read(bad), "cloth.shell.fabric 'unobtainium'", "fit.widths[0].at 'elbw'",
                   "views[0]: view 'top'")
    assert "wool_suiting" in msg and "medium" in msg  # (every step-0 refusal lists the fabrics and stiffness values)


def test_parts_before_read_is_refused(home):
    _refused(lambda: gp.write("m", "w", "parts", _parts()), "step 0 (read) has no reading")


def test_parts_refusals_by_name(home):
    gp.write("m", "w", "read", _read(home), look=False)
    p = _parts()
    p["seams"][0]["a"] = "yoke:front"                       # a seam on a piece the inventory lacks
    p["pieces"]["collar"] = {"what": "collar", "cloth": "shell", "seen": "inferred", "from": "x", "build": "full",
                             "stiff": True, "layer": 1}     # a built piece with no seam
    p["pieces"]["back"]["seen"] = "occluded"
    del p["pieces"]["back"]["from"]                         # occluded without its convention
    p["details"]["buttons"]["on"] = ["placket"]
    p["pieces"]["front.R"]["cloth"] = "silk"
    p["details"]["edge"]["follows"] = ["hem:edge"]
    _refused(lambda: gp.write("m", "w", "parts", p), "'yoke:front'", "pieces with no seam: collar",
             "pieces.back: occluded: from", "details.buttons.on", "pieces.front.R.cloth 'silk'", "details.edge.follows")
    assert gr.load("m", "w")["steps"]["1"]["status"] == "todo"  # (nothing written)


def test_parts_write_lists_measurements_and_draws_marks(home):
    gp.write("m", "w", "read", _read(home), look=False)
    r = gp.write("m", "w", "parts", _parts())
    assert r["plan"]["measurements"] == ["armpit_to_waist", "biceps"]
    im = Image.open(r["look"][0]).convert("RGB")
    s = 900 / 200
    # the seen front.L's outline is drawn (solid) over the picture: a pixel on its right edge is no longer the picture's
    assert im.getpixel((int(150 * s), int(150 * s))) != (150, 23, 23)
    assert gr.load("m", "w")["steps"]["1"]["look"] == r["look"]


def test_style_refusals_by_name(home):
    gp.write("m", "w", "read", _read(home), look=False)
    gp.write("m", "w", "parts", _parts(), look=False)
    s = _style()
    s["state"]["zip"] = {"state": "open", "source": "x"}     # a closure the inventory doesn't have
    del s["rows"][0]["source"]                               # a target with no source
    s["rows"][0]["target"].pop("of")                         # a ratio with no base
    s["bends"][0]["on"] = "sleeve"
    _refused(lambda: gp.write("m", "w", "style", s), "state.zip: no closure", "rows[0] width: no source",
             "is OF", "bends[0] lie.on 'sleeve'")
    s = _style()
    s["state"] = {}
    _refused(lambda: gp.write("m", "w", "style", s), "state.front: the ONE worn state")


def test_style_written_and_the_record_points_at_the_tool(home):
    assert 'call_tool("garment_plan"' in gr.answer("m", "w") and '"step": "read"' in gr.answer("m", "w")
    gp.write("m", "w", "read", _read(home), look=False)
    gp.write("m", "w", "parts", _parts(), look=False)
    r = gp.write("m", "w", "style", _style())
    assert r["look"] and gr.states(gr.load("m", "w"))["2"]["ready"]
    # a changed reading the later steps still validate against carries them forward (F2); one they don't makes them stale
    rd = _read(home)
    rd["kind"] = "a long waistcoat"
    gp.write("m", "w", "read", rd, look=False)
    s = gr.states(gr.load("m", "w"))
    assert s["1"]["ready"] and s["2"]["ready"]
    rd["cloth"].pop("trim")  # step 1's binding is cut from it
    gp.write("m", "w", "read", rd, look=False)
    s = gr.states(gr.load("m", "w"))
    assert s["1"]["stale"] and s["2"]["stale"] and "trim" in s["1"]["why"]


def test_the_tool_through_call_tool(home):
    out = asyncio.run(server.call_tool("garment_plan", {"name": "m", "garment": "w", "step": "read", "plan": _read(home)}))
    out = out if isinstance(out, list) else [out]
    assert "step 0 (read) written" in str(out[-1]) and "next:" in str(out[-1])
    bad = copy.deepcopy(_read(home))
    bad["fit"] = {}
    with pytest.raises(Exception, match="PlanRefused: step 0 \\(read\\) refused:\\s+fit:"):
        asyncio.run(server.call_tool("garment_plan", {"name": "m", "garment": "w", "step": "read", "plan": bad}))


def test_style_traces_refused_by_name_then_written_and_drawn(home):
    """T15 (C299, C351): traced edges at step 2, required; the fit view placed by step 0's own landmarks."""
    gp.write("m", "w", "read", _read(home), look=False)
    gp.write("m", "w", "parts", _parts(), look=False)
    tr = _style()["traces"][0]
    _refused(lambda: gp.write("m", "w", "style", dict(_style(), traces=[dict(tr, what="hemline")])),
             "traces[0] hem.what", "hemline", "the form:", "trace kinds (what): hem:", "row kinds (what):")
    _refused(lambda: gp.write("m", "w", "style", dict(_style(), traces=[])), "traces: required")
    marks = [{"view": 0, "at": {"hps.L": [120, 50], "hps.R": [80, 50]}, "source": "front view"}]
    _refused(lambda: gp.write("m", "w", "style", dict(_style(), body_marks=marks)),
             "body_marks: view 0 is placed by step 0's fit landmarks")
    r = gp.write("m", "w", "style", _style())
    m = r["plan"]["body_marks"]
    assert len(m) == 1 and m[0]["from_step0"] and m[0]["at"] == {"chest_z": [100.0, 100.0], "waist_z": [100.0, 150.0]}
    assert r["look"] and "trace hem (hem) on view 0: 4 points" in gp.text("m", "w", r)
    r = gp.write("m", "w", "style", r["plan"])  # (the written plan, sent back as is: its step-0 marks aren't "given")
    assert len(r["plan"]["body_marks"]) == 1


def test_traces_sit_on_the_pictures_edges(home):  # (t s2-3: a stepped notch traced as diagonals; C353)
    gp.write("m", "w", "read", _read(home), look=False)
    gp.write("m", "w", "parts", _parts(), look=False)
    st = _style()
    st["traces"][0]["points"] = [[50, 250], [100, 200], [140, 200], [150, 250]]  # (a dip into the plain cloth)
    _refused(lambda: gp.write("m", "w", "style", st, look=False), "traces[0] hem: points 0-", "with no edge in the picture")
    st["traces"][0]["why"] = "test: an edge the picture can't show"
    assert gp.write("m", "w", "style", st, look=False)


def test_length_names_the_step0_height_and_not_judged_needs_no_target(home):  # (t s2-3; C353)
    gp.write("m", "w", "read", _read(home), look=False)
    gp.write("m", "w", "parts", _parts(), look=False)
    st = _style()
    st["rows"].append({"id": "len", "what": "garment_length", "target": {"value": 45, "unit": "px"}, "source": "f"})
    _refused(lambda: gp.write("m", "w", "style", st, look=False), "garment_length was measured at step 0",
             "{height: one of hem}")
    st["rows"][-1]["target"] = {"height": "hem"}
    st["rows"].append({"id": "back", "what": "not_judged", "source": "front view only"})
    r = gp.write("m", "w", "style", st, look=False)
    assert r["plan"]["rows"][1]["target"]["z_mm"] > 0
    assert "step 0's hem (" in gp.text("m", "w", r)


def test_body_marks_from_step0_sides_and_inferred():
    from hifipushie import structure_marks as sm
    read = {"views": [{"view": "front"}], "fit_read": {"view": 0, "landmarks": {
        "chest": 100, "waist": {"at": 150, "from": "covered"}, "wrist": [[20, 300], [180, 300]]}}}
    m = sm.from_read(read, centre=100)
    assert m["at"] == {"chest_z": [100.0, 100.0], "wrist.R": [20.0, 300.0], "wrist.L": [180.0, 300.0]}  # (front: L right)
    read["views"][0]["view"] = "back"
    assert sm.from_read(read, centre=100)["at"]["wrist.L"] == [20.0, 300.0]
    read["fit_read"]["landmarks"] = {"chest": 100, "waist": {"at": 150, "from": "covered"}}  # (one seen: inferred added)
    assert set(sm.from_read(read, centre=100)["at"]) == {"chest_z", "waist_z"}


def test_record_lists_what_the_next_step_uses_by_name(home):  # (t s2-1: the JSON was cut at 300 characters)
    from hifipushie import garment_record as gr
    gp.write("m", "w", "read", _read(home), look=False)
    p = _parts()
    for k in range(30):
        p["define"][f"long_measurement_name_{k}"] = "length"
    gp.write("m", "w", "parts", p, look=False)
    a = gr.answer("m", "w")
    assert "closures: front" in a and "pieces: front.L, front.R, back" in a and "long_measurement_name_29" in a
    assert "step 0 (read):" in a and "landmarks on view 0 (picture px: v, or [u, v]): chest 100, waist 150" in a  # (C352)
    gp.write("m", "w", "style", _style(), look=False)
    import json as _j
    import os as _os
    rec = gr.load("m", "w")
    ap = {f"garment/m.w.{k}": {"model": f"{gr.path('m', 'w')}#{rec['steps'][k]['digest']}", "by": "joe"} for k in "012"}
    with open(_os.environ["HIFIPUSHIE_APPROVED"], "w") as f:
        _j.dump({"approved": ap, "log": []}, f)
    nxt = gr.answer("m", "w").splitlines()[-1]  # (C354: step 3 is body_tape's, with the names to measure)
    assert nxt.startswith('next: call_tool("body_tape"') and '"measurements": ["armpit_to_waist", "biceps"' in nxt, nxt


# ---------------------------------------------------------------- fix run F2 (t8 findings 4, 6, 7)
def test_parts_refuses_measurement_names_the_tape_cannot_take(home):
    gp.write("m", "g", "read", _read(home), look=False)
    p = _parts()
    p["seams"][0]["length"]["body"] = ["acrossBack", "chest"]
    with pytest.raises(gp.PlanRefused, match=r"'acrossBack' is not a measurement body_tape takes .*define"):
        gp.write("m", "g", "parts", p, look=False)
    p["define"]["acrossBack"] = "arc"  # defined by kind: taken
    r = gp.write("m", "g", "parts", p, look=False)
    assert {"acrossBack", "chest", "armpit_to_waist"} <= set(r["plan"]["measurements"])
    p["define"]["acrossBack"] = "freesewing"
    with pytest.raises(gp.PlanRefused, match=r"define: \{measurement name: kind\}"):
        gp.write("m", "g", "parts", p, look=False)


def test_coordinates_are_pixels_and_0_1_values_are_refused(home):
    gp.write("m", "g", "read", _read(home), look=False)
    p = _parts()
    p["pieces"]["front.L"]["where"]["outline"] = [[0.5, 0.2], [0.75, 0.2], [0.75, 0.8]]
    with pytest.raises(gp.PlanRefused, match=r"pieces.front.L.where.outline: .*PIXELS of view 0's image \(200 x 300 px"):
        gp.write("m", "g", "parts", p, look=False)
    r = gp.write("m", "g", "parts", _parts(), look=False)
    assert "PIXELS of the named view" in gp.text("m", "g", r)


def test_a_parts_change_carries_a_still_valid_style_and_tape_forward(home):
    from hifipushie import garment_record as gr
    gp.write("m", "g", "read", _read(home), look=False)
    gp.write("m", "g", "parts", _parts(), look=False)
    gp.write("m", "g", "style", _style(), look=False)
    gr.write("m", "g", "3", "done", output={"measurements": [{"name": "armpit_to_waist", "mm": 200.0}, {"name": "biceps", "mm": 300.0}]})
    d2, d3 = (gr.load("m", "g")["steps"][k]["digest"] for k in ("2", "3"))
    p = _parts()
    p["pieces"]["back"]["why"] = "never seen, reworded"  # a parts change that leaves style + tape valid
    r = gp.write("m", "g", "parts", p, look=False)
    assert any("step 2 (style) carried forward" in x for x in r["carried"]), r["carried"]
    s = gr.states(gr.load("m", "g"))
    assert s["2"]["ready"] and s["3"]["ready"] and not s["2"]["stale"] and not s["3"]["stale"]
    assert [gr.load("m", "g")["steps"][k]["digest"] for k in ("2", "3")] == [d2, d3]  # (digests, approvals kept)
    p["seams"][1]["length"]["body"] = ["armpit_to_waist", "chest"]  # step 3 hasn't taken chest: stale, said why
    gp.write("m", "g", "parts", p, look=False)
    s = gr.states(gr.load("m", "g"))
    assert s["2"]["ready"] and s["3"]["stale"] and "hasn't taken: chest" in s["3"]["why"]
    assert "hasn't taken: chest" in gr.answer("m", "g")
    p["closures"] = {}  # step 2's state names a closure step 1 no longer has: style stale, with the refusal
    p["details"]["buttons"]["what"] = "buttons"
    gp.write("m", "g", "parts", p, look=False)
    s = gr.states(gr.load("m", "g"))
    assert s["2"]["stale"] and "step 2 (style) refused" in s["2"]["why"]


def test_fit_ratios_applied_to_the_body_and_heights_between_landmarks(home):
    r = gp.write("m", "w", "read", _read(home))
    f, h = r["plan"]["fit"]["chest"], r["plan"]["heights"]["hem"]
    assert f["ratio"] == 1.25 and f["ease_mm"] == 250.0 and f["garment_width_mm"] == 412.5 and f["body"] == "inferred"
    assert h["z_mm"] == 700.0 and h["extrapolated"] and set(h["between"]) == {"chest", "waist"}  # (250 px: 3 x the chest -> waist 50 px: 1300 - 3 x 200)
    assert r["plan"]["fit_read"]["view"] == 0 and any(p.endswith("step0_fit.png") for p in r["look"])
    txt = gp.text("m", "w", r)
    assert "fit chest: ratio 1.25" in txt and "height hem: 700 mm" in txt and "wool_suiting" in txt


def test_fit_refusals_by_name(home):
    for change, why in (
            (lambda b: b["fit"]["widths"][0].update(garment=[[90, 100], [110, 100]]), "narrower than the body at the chest"),
            (lambda b: b["fit"]["widths"][0].pop("body_from"), "fit.widths[0].body_from"),
            (lambda b: b["fit"]["widths"][0].pop("body"), "fit.widths[0].body"),
            (lambda b: b["fit"]["landmarks"].update(knees=3), "fit.landmarks.knees: unknown landmark"),
            (lambda b: b.update(fit={"chest": {"ease_mm": 60, "source": "guess"}}), "no longer guessed"),
            (lambda b: b.update(kind="suit trousers, zip fly, belt loops"), "step 1 (parts)"),
            (lambda b: b["fit"].update(view="back"), "view 'back': no such view")):
        bad = _read(home)
        change(bad)
        _refused(lambda: gp.write("m", "w", "read", bad, look=False), why)
    ok = _read(home)
    ok["fit"]["widths"][0].update(garment=[[90, 100], [110, 100]], why="knit, worn tight")
    assert gp.write("m", "w", "read", ok, look=False)["plan"]["fit"]["chest"]["ratio"] == 0.25


def test_views_by_name_in_every_step(home):
    rd = _read(home)
    rd["cloth"]["shell"]["colour"]["view"] = "front"
    assert gp.write("m", "w", "read", rd, look=False)["plan"]["cloth"]["shell"]["colour_from"]["view"] == 0
    p = _parts()
    for x in list(p["pieces"].values()) + list((p.get("details") or {}).values()):
        if isinstance(x.get("where"), dict):
            x["where"]["view"] = "front"
    assert all((x.get("where") or {}).get("view", 0) == 0 for x in gp.write("m", "w", "parts", p, look=False)["plan"]["pieces"].values())


def test_fit_form_errors_refused_with_the_form_not_crashed(home):  # (t s0-2: widths as a dict raised AttributeError)
    for change, why in ((lambda b: b["fit"].update(widths={"chest": {}}), "fit.widths: a list"),
                        (lambda b: b["fit"].update(heights={"hem": 250}), "fit.heights: a list"),
                        (lambda b: b["fit"]["widths"].append("chest"), "fit.widths[1]:")):
        bad = _read(home)
        change(bad)
        assert "the form: fit {view" in _refused(lambda: gp.write("m", "w", "read", bad, look=False), why)


def test_seen_edges_are_measured_on_the_picture(home):  # (the picture's block is 50..150 wide: marks 3 px wide of it)
    b = _read(home)
    b["fit"]["widths"][0].update(garment=[[47, 100], [153, 100]])
    f = gp.write("m", "w", "read", b, look=False)["plan"]["fit"]["chest"]
    assert max(f["measured"]["garment"]["moved_px"]) >= 2
    assert abs(f["ratio"] - 100 / 74) < 0.02 and 62 <= f["measured"]["body"]["measured"][0][0] <= 63  # (inset kept: C341)
    b["fit"]["widths"][0].update(garment=[[90, 100], [110, 100]], why="knit, worn tight")  # (no edge near: kept)
    f = gp.write("m", "w", "read", b, look=False)["plan"]["fit"]["chest"]
    assert f["ratio"] == 0.25 and f["measured"]["garment"]["notes"]


def test_landmarks_inferred_sensitivity_and_floor_never_used(home):
    b = _read(home)
    b["fit"]["landmarks"] = {"chest": 100, "waist": {"at": [[60, 150], [140, 150]], "from": "covered: by proportion"},
                             "floor": 290}
    r = gp.write("m", "w", "read", b, look=True)
    h = r["plan"]["heights"]["hem"]
    assert set(h["between"]) == {"chest", "waist"} and h["z_mm"] == 700.0  # (the floor marked, not used)
    assert h["landmarks"]["waist"] == "covered: by proportion" and h["mm_per_10px"]["waist"] > 0
    assert "INFERRED: covered" in gp.text("m", "w", r) and "floor" in h["source"]
    b["fit"]["landmarks"]["waist"] = {"at": 150}
    _refused(lambda: gp.write("m", "w", "read", b, look=False), "fit.landmarks.waist")


def test_a_width_sits_at_its_landmark_or_at_a_garment_edge(home):  # (t s0-3: an "ankle" width 45 px above the ankle)
    b = _read(home)
    b["fit"]["widths"][0].update(garment=[[50, 120], [150, 120]], body=[[60, 120], [140, 120]])
    assert "the chest is marked at row 100" in _refused(lambda: gp.write("m", "w", "read", b, look=False), "fit.widths[0]")
    b = _read(home)
    b["fit"]["widths"].append({"at": "hem", "garment": [[50, 250], [150, 250]], "body": [[70, 250], [130, 250]],
                               "body_from": "inferred: inside"})
    f = gp.write("m", "w", "read", b, look=False)["plan"]["fit"]["hem"]
    assert f["section"]["z_mm"] == 700.0 and "section at the hem (the torso at 700 mm" in f["source"]


def test_a_landmark_far_from_where_its_neighbours_put_it_is_refused_unless_why(home):
    b = _read(home)  # (chest 100 -> 1300 mm, waist 150 -> 1100 mm: 4 mm / px; the knee (500 mm) belongs near row 300)
    b["fit"]["landmarks"]["knee"] = 250
    e = _refused(lambda: gp.write("m", "w", "read", b, look=False), "fit.landmarks.knee: marked", "middle of the kneecap")
    assert "never used for heights" in e and "fit.landmarks.chest" not in e
    b["fit"]["landmarks"]["knee"] = {"at": 250, "from": "seen", "why": "a bent knee in the picture"}
    assert gp.write("m", "w", "read", b, look=False)["plan"]["heights"]["hem"]
    b["fit"]["landmarks"]["knee"] = 296
    assert gp.write("m", "w", "read", b, look=False)


def test_heights_on_a_part_and_landmarks_the_model_cannot_take(home):  # (t s0-4)
    BODY["crotch"] = {"girth_mm": 0.0, "width_mm": 0.0, "z_mm": 800.0}
    try:
        b = _read(home)  # (a torso edge mapped under the crotch: refused, it is on a leg)
        b["fit"]["heights"] = [{"name": "hem", "at": 290}]
        _refused(lambda: gp.write("m", "w", "read", b, look=False), "below the model's crotch", "on: 'leg'")
        b["fit"]["heights"] = [{"name": "cuff", "at": 200, "on": "arm"}]  # (no arm landmarks marked)
        _refused(lambda: gp.write("m", "w", "read", b, look=False), "needs 2 of the arm's landmarks")
        b["fit"]["heights"] = [{"name": "hem", "at": 250, "on": "knees"}]
        _refused(lambda: gp.write("m", "w", "read", b, look=False), "on 'knees'")
    finally:
        BODY.pop("crotch")

    class Broken(gf.DictBody):  # (a landmark the tape can't take: named, not raised)
        def at(self, lm, view="front"):
            if lm == "waist":
                raise ValueError("no section there")
            return super().at(lm, view)
    import hifipushie.garment_fit as gfm
    old = gfm.body_for
    gfm.body_for = lambda model: Broken(BODY)
    try:
        b = _read(home)
        _refused(lambda: gp.write("m", "w", "read", b, look=False), "fit.landmarks.waist: the model can't be measured")
    finally:
        gfm.body_for = old


def test_close_landmarks_do_not_predict_each_other():  # (t s0-4: armpit + chest 15 px apart)
    from hifipushie import garment_fit_marks as gm
    z = {"armpit": 1300.0, "chest": 1280.0, "waist": 1100.0, "hips": 950.0}
    marks = {"armpit": 100, "chest": 102, "waist": 160, "hips": 200}  # (the chest 2 px under the armpit: 5 mm off)
    d = gm.drift(marks, z, 60.0)
    assert abs(d["waist"][1]) < 30 and abs(d["hips"][1]) < 30, d


def test_one_picture_one_scale(home):  # (t s0-4: across 1.17 mm/px, up and down 0.88: the hem 6 cm high)
    b = _read(home)  # (across: chest 330 mm / 80 px, waist 280 mm / 70 px; up: chest 1300 -> knee 500 mm)
    b["fit"]["widths"].append({"at": "waist", "garment": [[60, 150], [140, 150]], "body": [[65, 150], [135, 150]],
                               "body_from": "inferred: inside"})
    b["fit"]["landmarks"]["knee"] = 300
    sc = gp.write("m", "w", "read", b, look=False)["plan"]["fit_read"]["scale"]
    assert abs(sc["apart"]) < 0.18, sc
    b["fit"]["landmarks"] = {"chest": 100, "waist": {"at": 150, "from": "seen", "why": "test"},
                             "knee": {"at": 230, "from": "seen", "why": "test"}}  # (up and down: 800 mm / 130 px)
    e = _refused(lambda: gp.write("m", "w", "read", b, look=False), "One picture has one scale", "knee 29")
    assert "fit.landmarks" not in e
    b["fit"]["scale_why"] = "a stylised figure: long legs"
    assert gp.write("m", "w", "read", b, look=False)


def test_an_inferred_landmark_hangs_off_a_seen_one_at_the_pictures_scale(home):  # (t s0-6: a waist 36 mm low)
    b = _read(home)  # (across: chest 330 mm / 80 px, waist 280 mm / 70 px: ~4.06 mm/px; the waist 200 mm under the chest)
    b["fit"]["widths"].append({"at": "waist", "garment": [[60, 150], [140, 150]], "body": [[65, 150], [135, 150]],
                               "body_from": "inferred: inside"})
    b["fit"]["landmarks"]["waist"] = {"at": 150, "from": "covered: by proportion"}
    assert gp.write("m", "w", "read", b, look=False)
    b["fit"]["landmarks"]["waist"] = {"at": 170, "from": "covered: by proportion"}
    for w in b["fit"]["widths"]:
        if w["at"] == "waist":
            w.update(garment=[[60, 170], [140, 170]], body=[[65, 170], [135, 170]])
    _refused(lambda: gp.write("m", "w", "read", b, look=False), "fit.landmarks.waist (inferred)", "from the seen chest")
    b["fit"]["landmarks"]["waist"]["why"] = "test"
    assert gp.write("m", "w", "read", b, look=False)


def test_edges_are_named_spans_that_tile_the_outline(home):  # (t s1-1: free-text edges, seams of any length)
    gp.write("m", "w", "read", _read(home), look=False)
    b = _parts()
    b["pieces"]["front.L"]["edges"] = {"shoulder": [0, 1], "side": [1, 2], "cf": [3, 0]}  # (segment 2 -> 3 in none)
    _refused(lambda: gp.write("m", "w", "parts", b, look=False), "pieces.front.L.edges: the edges must tile", "in none: segments 2")
    b = _parts()
    b["seams"][0]["a"] = "front.L:hindarm"
    _refused(lambda: gp.write("m", "w", "parts", b, look=False), "front.L has no edge 'hindarm'")
    b = _parts()
    b["details"]["buttons"]["on"] = "front.R"
    e = _refused(lambda: gp.write("m", "w", "parts", b, look=False), "details.buttons.on: a LIST", "the form:")
    assert "f, r, o" not in e and "edges: {edge: [i0, i1]}" in e
    b = _parts()
    b["pieces"]["back"].pop("edges")
    _refused(lambda: gp.write("m", "w", "parts", b, look=False), "pieces.back.edges: name its edges ([names]")


def test_a_seam_length_far_from_its_edge_as_drawn_is_refused():
    from hifipushie import garment_parts_lengths as pe
    edges = {"front": {"shoulder": (0, [[0, 0], [100, 0]], False)}, "back": {"shoulder": None}}
    seam = [{"a": "front:shoulder", "b": "back:shoulder", "length": {"body": ["shoulderToShoulder"]}}]
    bad = []
    pe.lengths(seam, edges, 0, 1.2, {"shoulderToShoulder": 450.0}, {}, None, bad)  # (120 mm drawn, 450 on the body: 3.8x)
    assert bad and "3.8x" in bad[0]
    bad = []
    pe.lengths(seam, edges, 0, 1.2, {"shoulderToShoulder": 150.0}, {}, None, bad)
    assert not bad
    edges["front"]["shoulder"] = (0, [[0, 0], [100, 0]], True)  # (hidden in this view: not checked)
    bad = []
    pe.lengths(seam, edges, 0, 1.2, {"shoulderToShoulder": 450.0}, {}, None, bad)
    assert not bad
    edges["front"]["shoulder"] = (0, [[0, 0], [100, 0]], False)
    seam[0]["why"] = "test"
    bad = []
    pe.lengths(seam, edges, 0, 1.2, {"shoulderToShoulder": 450.0}, {}, None, bad)
    assert not bad


def test_ratio_lengths_are_checked_on_the_model():  # (t s1-9: no ratio was checked; C350)
    from hifipushie import garment_parts_lengths as pl
    from hifipushie.garment_fit_body import DictBody
    edges = {"front": {"side": (0, [[0, 0], [0, 400]], False), "cf": (0, [[0, 0], [0, 100]], False)},
             "back": {"side": None}}
    heights = {"hem": {"z_mm": 900.0, "on": "torso"}}
    body = DictBody({"armpit": {"z_mm": 1380.0}})
    seam = [{"a": "front:side", "b": "back:side", "length": {"style": {"ratio": 1.0, "of": ["armpit", "hem"]}}}]
    bad = []  # (480 mm drawn; armpit to hem on the model 480: 1.0x)
    done = pl.lengths(seam, edges, 0, 1.2, {}, heights, body, bad)
    assert not bad and done == [(0, 480.0, 480.0)]
    seam[0]["length"]["style"]["ratio"] = 0.15  # (72 mm: 0.15x)
    bad = []
    pl.lengths(seam, edges, 0, 1.2, {}, heights, body, bad)
    assert bad and "0.15 x armpit to hem is 72 mm" in bad[0]
    seam[0]["length"] = {"style": {"ratio": 4.0, "of": "neck"}}  # (of a tape measurement)
    bad = []
    pl.lengths(seam, edges, 0, 1.2, {"neck": 400.0}, heights, body, bad)
    assert bad and "4.0 x neck is 1600 mm" in bad[0] and "3.3x" in bad[0]
    seam[0]["length"] = {"style": {"ratio": 4.0, "of": "front:cf"}}  # (of another drawn edge: 480 = 480)
    bad = []
    assert pl.lengths(seam, edges, 0, 1.2, {}, heights, body, bad) and not bad
    seam[0]["length"] = {"style": {"value_mm": 40, "fixed": "a zip"}}  # (fixed mm, as given: 40 vs 480)
    bad = []
    pl.lengths(seam, edges, 0, 1.2, {}, heights, body, bad)
    assert bad and "fixed is 40 mm" in bad[0]


def test_mirrored_seams_swap_their_caught_edges():  # (t s1-9: the .R copy caught canvas.L)
    from hifipushie import garment_parts_mirror as gpm
    p = {"centre": 100, "pieces": {}, "details": {},
         "seams": [{"a": "front.L:gorge", "b": "collar:gorge.L", "caught": ["canvas.L:gorge"]}]}
    gpm.mirror(p, [])
    r = [s for s in p["seams"] if s.get("mirrored_from")]
    assert r and r[0]["caught"] == ["canvas.R:gorge"] and r[0]["b"] == "collar:gorge.R"


def test_hidden_edges_and_trims_placed_by_their_edges(home):  # (t s1-2: an invented point; bindings traced twice)
    gp.write("m", "w", "read", _read(home), look=False)
    b = _parts()
    b["details"]["edge"].pop("where")
    p = gp.write("m", "w", "parts", b, look=False)["plan"]
    assert p["details"]["edge"]["where"]["outlines"] == [[[100, 250], [100, 50]]]
    b = _parts()
    b["pieces"]["front.L"]["hidden"] = ["side"]
    b["details"]["edge"]["follows"] = ["front.L:side"]
    b["details"]["edge"].pop("where")  # (a hidden edge can't place a trim: it needs its own where)
    _refused(lambda: gp.write("m", "w", "parts", b, look=False), "details.edge: seen: where")
    b["pieces"]["front.L"]["hidden"] = ["armhole"]
    _refused(lambda: gp.write("m", "w", "parts", b, look=False), "pieces.front.L.hidden: a list of its own edges")


def test_mixed_trims_and_self_crossing_outlines_are_refused_with_why(home):  # (t s1-2 / s1-3)
    gp.write("m", "w", "read", _read(home), look=False)
    b = _parts()
    b["details"]["edge"]["follows"] = ["front.L:cf", "back:hem"]
    b["details"]["edge"].pop("where")
    _refused(lambda: gp.write("m", "w", "parts", b, look=False), "follows back:hem, with no drawn place", "two details")
    b = _parts()
    b["pieces"]["front.L"]["where"]["outline"] = [[100, 50], [150, 250], [150, 50], [100, 250]]  # (a bow tie)
    _refused(lambda: gp.write("m", "w", "parts", b, look=False), "pieces.front.L.where.outline crosses itself")
    b["pieces"]["front.L"]["hidden"] = ["shoulder"]  # (a crossing on a hidden run is allowed)
    assert gp.write("m", "w", "parts", b, look=False)
    b = _parts()
    b["seams"][2]["length"]["style"]["of"] = "nonsense"
    _refused(lambda: gp.write("m", "w", "parts", b, look=False), "length.style.of 'nonsense': a ratio's base")


def test_left_side_mirrors_to_the_right(home):  # (t s1-4: .R names refused, a CB seam written as back.L:cb = back.L:cb)
    gp.write("m", "w", "read", _read(home), look=False)
    b = _parts()
    b.pop("define", None)
    b["pieces"].pop("front.R")
    b["details"]["buttons"]["on"] = ["front.L"]
    b["details"]["edge"]["on"] = ["front.L"]
    b["closures"]["front"]["pieces"] = ["front.L", "front.R"]
    b["seams"] = [{"a": "front.L:side", "b": "back:side.L", "length": {"body": ["chest"]}},
                  {"a": "front.L:shoulder", "b": "back:shoulder.L", "length": {"body": ["chest"]}},
                  {"a": "front.L:cf", "b": "front.R:cf", "length": {"body": ["chest"]}}]
    _refused(lambda: gp.write("m", "w", "parts", b, look=False), "centre: the garment's centre line u on view 0")
    b["centre"] = 100
    p = gp.write("m", "w", "parts", b, look=False)["plan"]
    assert p["mirrored"] == ["front.R"] and p["pieces"]["front.R"]["where"]["outline"][0] == [100, 50]
    assert p["pieces"]["front.R"]["where"]["outline"][1] == [50, 50]  # (u 150 -> 2 x 100 - 150)
    ends = {(s["a"], s["b"]) for s in p["seams"]}
    assert ("front.R:side", "back:side.R") in ends and ("front.R:shoulder", "back:shoulder.R") in ends
    assert len(p["seams"]) == 5  # (the CF seam already crosses the centre: not doubled)


def test_one_seam_per_edge_stacked_edges_are_caught():  # (t s1-5: a sleeve cap sewn to both armholes; t s1-8: C349)
    from hifipushie import garment_parts_edges as pe
    bad = []
    pe.once([{"a": "sleeve:cap", "b": "front:armhole"}, {"a": "sleeve:cap", "b": "back:armhole"}], bad, {})
    assert bad and "sleeve:cap is sewn in 2 seams" in bad[0] and "cap_front + cap_back" in bad[0]
    bad = []  # (stacked in one seam line, whatever the layer numbers say)
    pe.once([{"a": "collar:top", "b": "facing:top", "caught": ["canvas:top"]}], bad, {})
    assert not bad
    bad = []  # (two seams on one edge are refused even on different layers: say caught)
    pe.once([{"a": "collar:top", "b": "facing:top"}, {"a": "collar:top", "b": "canvas:top"}], bad,
            {"collar": {"layer": 2}, "facing": {"layer": 0}, "canvas": {"layer": 1}})
    assert bad and "caught: ['piece:edge']" in bad[0]
    bad = []  # (a caught edge sewn again elsewhere)
    pe.once([{"a": "a:x", "b": "b:x", "caught": ["c:x"]}, {"a": "c:x", "b": "d:x"}], bad, {})
    assert bad and bad[0].startswith("c:x is sewn in 2 seams")


def test_caught_edges_count_and_are_checked(home):
    gp.write("m", "w", "read", _read(home), look=False)
    b = _parts()
    b["pieces"]["front.L"]["free"] = []
    b["seams"][0]["caught"] = ["front.L:hem"]
    assert gp.write("m", "w", "parts", b, look=False)  # (a caught edge is accounted for)
    b["seams"][0]["caught"] = ["front.L:nope"]
    _refused(lambda: gp.write("m", "w", "parts", b, look=False), "front.L has no edge 'nope'")
    b["seams"][0]["caught"] = "front.L:hem"
    _refused(lambda: gp.write("m", "w", "parts", b, look=False), "caught: a list of 'piece:edge'")


def test_seam_lengths_never_mm_off_the_picture(home):  # (t s1-8: 38 of 42 seams in picture mm; C335, C349)
    gp.write("m", "w", "read", _read(home), look=False)
    b = _parts()
    b["seams"][0]["length"] = {"style": {"value_mm": 380, "source": "read off view 0, 350 px"}}
    _refused(lambda: gp.write("m", "w", "parts", b, look=False), "millimetres read off the picture don't transfer")
    b["seams"][0]["length"]["style"]["fixed"] = "a 20 cm zip, the same on every wearer"
    assert gp.write("m", "w", "parts", b, look=False)
    b["seams"][0]["length"] = {"style": {"ratio": 1.0, "of": ["armpit", "hem"], "source": "underarm to hem, view 0"}}
    assert gp.write("m", "w", "parts", b, look=False)
    b["seams"][0]["length"]["style"]["of"] = ["armpit", "knee_cap"]
    _refused(lambda: gp.write("m", "w", "parts", b, look=False), "knee_cap not a step-0 height or landmark")


def test_every_edge_of_a_built_piece_is_accounted_for(home):  # (t s1-6: edges sewn to nothing passed)
    gp.write("m", "w", "read", _read(home), look=False)
    b = _parts()
    b["pieces"]["front.L"]["free"] = []
    _refused(lambda: gp.write("m", "w", "parts", b, look=False), "pieces.front.L: edges not accounted for: hem")
    b["closures"]["front"]["edges"] = ["front.L:hem"]  # (a closure's edge counts)
    assert gp.write("m", "w", "parts", b, look=False)
    b["pieces"]["front.L"]["free"] = ["armhole"]
    _refused(lambda: gp.write("m", "w", "parts", b, look=False), "pieces.front.L.free: a list of its own edges")


def test_a_garment_as_wide_at_the_waist_as_the_chest_where_the_body_narrows_is_asked_open_or_flared():  # (C388)
    from hifipushie import garment_fit as gf
    ws = [dict(at="chest", px=[384.4, 335.8]), dict(at="waist", px=[394.4, 280.8]), dict(at="hips", px=[456.4, 341.2])]
    bad = gf._hangs_open(ws, [{"at": "waist"}])
    assert len(bad) == 1 and "hangs OPEN" in bad[0] and "waist" in bad[0], bad
    assert not gf._hangs_open(ws, [{"at": "waist", "why": "a sack coat cut straight from the chest"}])
    fitted = [dict(at="chest", px=[371.9, 335.8]), dict(at="waist", px=[309.6, 280.8])]
    assert not gf._hangs_open(fitted, [])
    opened = [dict(at="chest", px=[384.4, 335.8], v=400), dict(at="waist", ratio=1.2, gnote="worn open: fronts apart", v=600),
              dict(at="hips", px=[456.4, 341.2], v=700)]
    bad = gf._hangs_open(opened, [])
    assert len(bad) == 1 and "hips" in bad[0] and "hangs open too" in bad[0], bad

