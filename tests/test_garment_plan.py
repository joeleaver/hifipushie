"""garment_plan (T4): steps 0-2 of the garment record for any garment. Refusals by name, record writes, the looks drawn
over the reference, the tool through the server. Cheap: a generated picture, no renders."""
import asyncio
import copy

import pytest
from PIL import Image

from hifipushie import garment_plan as gp, garment_record as gr, server, store


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setenv("HIFIPUSHIE_APPROVED", str(tmp_path / "approved.json"))
    im = Image.new("RGB", (200, 300), (40, 40, 200))
    im.paste((200, 30, 30), (50, 50, 150, 250))
    im.save(tmp_path / "ref.png")
    return tmp_path


def _read(home):
    return {"kind": "a waistcoat", "views": [{"image": str(home / "ref.png"), "view": "front"}],
            "cloth": {"shell": {"fabric": "wool_suiting", "stiffness": "crisp", "colour": {"at": [[100, 150]], "view": 0},
                                "grain": "down CF"},
                      "trim": {"gsm": 300, "thickness_mm": 1.0, "stretch": "none", "stiffness": "stiff",
                               "colour": [210, 170, 60], "source": "braid convention", "grain": "along"}},
            "fit": {"chest": {"ease_mm": 60, "source": "fronts lie flat"}}}


def _parts():
    return {"pieces": {"front.L": {"what": "front", "cloth": "shell", "seen": "seen", "build": "full", "stiff": False,
                                   "layer": 1, "where": {"view": 0, "outline": [[100, 50], [150, 50], [150, 250], [100, 250]]}},
                       "front.R": {"what": "front", "cloth": "shell", "seen": "seen", "build": "full", "stiff": False,
                                   "layer": 1, "where": {"view": 0, "outline": [[50, 50], [100, 50], [100, 250], [50, 250]]}},
                       "back": {"what": "back", "cloth": "shell", "seen": "occluded", "from": "a waistcoat back is one piece",
                                "build": "simplified", "why": "never seen", "stiff": False, "layer": 1}},
            "details": {"buttons": {"what": "buttons", "on": ["front.R"], "count": 5, "seen": "seen", "build": "full",
                                    "where": {"view": 0, "at": [[100, 80], [100, 120]]}},
                        "edge": {"what": "binding", "on": ["front.L"], "cloth": "trim", "follows": ["front.L:cf"],
                                 "seen": "seen", "build": "full", "where": {"view": 0, "outlines": [[[100, 50], [100, 250]]]}}},
            "closures": {"front": {"what": "buttons", "pieces": ["front.L", "front.R"], "details": ["buttons"]}},
            "seams": [{"a": "front.L:side", "b": "back:side.L", "length": {"body": ["armpit_to_waist"]}},
                      {"a": "front.R:side", "b": "back:side.R", "length": {"body": ["armpit_to_waist"]}},
                      {"a": "front.L:shoulder", "b": "back:shoulder.L", "length": {"style": {"ratio": 0.5, "of": "x",
                                                                                              "source": "front view"}}}]}


def _style():
    return {"state": {"front": {"state": "closed", "source": "front view"}},
            "bends": [{"id": "lie", "on": "front.L", "target": {"is": "flat"}, "source": "front view"}],
            "pose": {"name": "arms down", "source": "front view"},
            "rows": [{"id": "width", "what": "trim_lines_apart", "note": "the two binding lines apart",
                      "target": {"value": 0.5, "unit": "ratio", "of": "shoulder_width"},
                      "source": "front view", "view": 0, "at": [[50, 150], [150, 150]]}]}


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
    del bad["fit"]["chest"]["source"]
    bad["views"][0]["view"] = "top"
    _refused(lambda: gp.check_read(bad), "cloth.shell.fabric 'unobtainium'", "fit.chest: no source", "views[0]: view 'top'")


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
    assert r["plan"]["measurements"] == ["armpit_to_waist"]
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
    # a changed reading makes the later steps stale
    rd = _read(home)
    rd["kind"] = "a waistcoat, longer"
    gp.write("m", "w", "read", rd, look=False)
    assert gr.states(gr.load("m", "w"))["1"]["stale"]


def test_the_tool_through_call_tool(home):
    out = asyncio.run(server.call_tool("garment_plan", {"name": "m", "garment": "w", "step": "read", "plan": _read(home)}))
    out = out if isinstance(out, list) else [out]
    assert "step 0 (read) written" in str(out[-1]) and "next:" in str(out[-1])
    bad = copy.deepcopy(_read(home))
    bad["fit"] = {}
    with pytest.raises(Exception, match="PlanRefused: step 0 \\(read\\) refused:\\s+fit:"):
        asyncio.run(server.call_tool("garment_plan", {"name": "m", "garment": "w", "step": "read", "plan": bad}))


def test_style_traces_refused_by_name_then_written_and_drawn(home):
    """T15 (C299): traced edges + body marks at step 2: refused by name, then written, listed and drawn."""
    gp.write("m", "w", "read", _read(home), look=False)
    gp.write("m", "w", "parts", _parts(), look=False)
    tr = {"id": "hem", "what": "hem", "view": 0, "points": [[50, 250], [100, 240], [150, 250], [160, 251]], "corners": [1],
          "source": "front view: the hem"}
    marks = [{"view": 0, "at": {"hps.L": [120, 50], "hps.R": [80, 50]}, "source": "front view"}]
    st = dict(_style(), traces=[dict(tr, what="hemline")], body_marks=marks)
    _refused(lambda: gp.write("m", "w", "style", st), "traces[0] hem.what", "hemline")
    st = dict(_style(), traces=[tr])
    _refused(lambda: gp.write("m", "w", "style", st), "body_marks: view 0 needs two landmarks")
    r = gp.write("m", "w", "style", dict(_style(), traces=[tr], body_marks=marks))
    assert r["look"] and "trace hem (hem) on view 0: 4 points" in gp.text("m", "w", r)
