"""F3 (trial s4-27): step 4's rows caught, panels, turned_width; the seams row's run hint; design paths; vents as marks."""
import numpy as np
import pytest

from hifipushie import draft_caught, draft_panels, draft_runs, draft_turned, draft_vents, pattern_parts


def _piece(name, pts):
    P = np.array([p for _, p in pts], float)
    return {"name": name, "P": P, "names": {n: i for i, (n, _) in enumerate(pts)}}


# a forepart 300 x 500 mm: front edge on x = 0 (hem h0 .. f1 .. notch n), neck n .. k, shoulder k .. s, side s .. h1
HOST = [("h0", (0, 0)), ("f1", (0, .25)), ("n", (0, .5)), ("k", (.1, .5)), ("s", (.3, .5)), ("h1", (.3, 0))]


def _canvas(front_x):
    """A canvas on the forepart's top half, in its own frame (moved and turned); its front edge at x = front_x."""
    pts = [("b", (front_x, .25)), ("n2", (front_x, .5)), ("k", (.1, .5)), ("s", (.3, .5)), ("i", (.3, .25))]
    R = np.array([[0, -1], [1, 0]])
    return _piece("canvas.L", [(n, tuple(np.array(p) @ R.T + [2, 3])) for n, p in pts])


def _B(front_x):
    return {"pieces": {"front.L": _piece("front.L", HOST), "canvas.L": _canvas(front_x)},
            "edge_arcs": {"front.L": {"front": "h0>f1>n", "neck": "n>k", "shoulder": "k>s"},
                          "canvas.L": {"front": "b>n2", "neck": "n2>k", "shoulder": "k>s"}}}


STEP1 = {"seams": [{"a": "facing.L:front", "b": "front.L:front", "caught": ["canvas.L:front"]},
                   {"a": "collar:neck", "b": "front.L:neck", "caught": ["canvas.L:neck"]},
                   {"a": "front.L:shoulder", "b": "back.L:shoulder", "caught": ["canvas.L:shoulder"]}]}


def test_caught_canvas_short_of_the_front_edge_fails():
    r = draft_caught.row(_B(0.065), STEP1)
    assert r["status"] == "FAIL" and "canvas.L:front lies up to 65 mm off front.L:front" in r["why"]


def test_caught_canvas_to_the_front_edge_passes():
    assert draft_caught.row(_B(0.0), STEP1)["status"] == "PASS"


def test_caught_fits_without_shared_names():
    B = _B(0.0)
    c = B["pieces"]["canvas.L"]
    c["names"] = {f"c{i}": i for i in range(len(c["P"]))}
    B["edge_arcs"]["canvas.L"] = {"front": "c0>c1", "neck": "c1>c2", "shoulder": "c2>c3"}
    r = draft_caught.row(B, STEP1)
    assert r["status"] == "PASS" and "fitted to its caught edges" in r["value"]


def test_panels_form_refused_by_name():
    bad = []
    draft_panels.check([{"girth": "chest", "shares": {"front": .5, "side": .2, "yoke": .1}, "source": ""}],
                       {"front.L": {}, "side.L": {}, "back.L": {}}, bad)
    assert any("yoke" in b for b in bad) and any("sum to 0.80" in b for b in bad) and any("source" in b for b in bad)


def test_panels_sliver_side_body_fails_with_mm(monkeypatch):
    ring = {"front.L", "front.R", "side.L", "side.R", "back.L", "back.R"}
    w = {"front.L": .277, "front.R": .277, "side.L": .046, "side.R": .046, "back.L": .248, "back.R": .248}
    monkeypatch.setattr(draft_panels, "_widths", lambda B, d, T, g: [(ring, w, {"front": .029})])
    monkeypatch.setattr("hifipushie.tape_geom.tapes", lambda s3: {"chest": {"kind": "loop"}})
    monkeypatch.setattr(draft_panels, "_neighbours", lambda B, p, r: {"front.L", "back.L"} if "side" in p else {"side.L"})
    plan = {"panels": [{"girth": "chest", "shares": {"front": .40, "side": .22, "back": .38}, "source": "convention"}]}
    r = draft_panels.rows({"pieces": {p: {} for p in ring}}, plan, {}, {})[0]
    assert r["status"] == "FAIL" and "side is 76 mm a piece too narrow" in r["why"] and "move its seams out" in r["why"]
    w.update({"front.L": .2365, "front.R": .2365, "side.L": .1223, "side.R": .1223, "back.L": .2113, "back.R": .2113})
    assert draft_panels.rows({"pieces": {p: {} for p in ring}}, plan, {}, {})[0]["status"] == "PASS"


def test_panels_required_for_three_panels(monkeypatch):
    ring = {"front.L", "side.L", "back.L", "front.R", "side.R", "back.R"}
    monkeypatch.setattr(draft_panels, "_widths", lambda B, d, T, g: [(ring, {p: .1 for p in ring}, {})])
    monkeypatch.setattr("hifipushie.tape_geom.tapes", lambda s3: {"chest": {"kind": "loop"}})
    monkeypatch.setattr("hifipushie.draft_tapes.names_of", lambda d, p: ["chest"])
    r = draft_panels.rows({"pieces": {p: {} for p in ring}}, {}, {}, {})[0]
    assert r["status"] == "FAIL" and r["back_to"] == "2"


def test_turned_width_flat_and_row(monkeypatch):
    # a forepart with a lapel 80 mm wide beside a fold line from (0.1, 0) to (0.1, 0.4)
    pc = _piece("front.R", [("a", (0, 0)), ("b", (.02, .4)), ("c", (.3, .4)), ("d", (.3, 0))])
    pc["P"] = np.array([[.1, 0], [.02, .3], [.02, .4], [.3, .4], [.3, 0]], float)
    pc["names"] = {}
    B = {"pieces": {"front.R": pc}, "folds": [{"piece": "front.R", "name": "lapel_roll", "line": [[.1, 0], [.1, .4]]}]}
    assert draft_turned.flat(B, B["folds"][0]) == pytest.approx(80, abs=1)
    step2 = {"bends": [{"on": "front.R", "fold": "lapel_roll", "trace": "roll.R"}]}
    monkeypatch.setattr(draft_turned, "seen", lambda *a: {"mm": 62.0, "edge": "front_edge.R", "tol": 8.0, "how": "x"})
    r = draft_turned.row(B, {}, step2, {"plan": {"style": step2}, "at": {}})
    assert r["status"] == "FAIL" and "narrow it by 18 mm" in r["why"]


def test_seam_run_hint_names_the_corner():
    # a cap side: top sleeve top>p>t (the hind seam runs on from p up... to t), against an armhole of 300 mm
    top = _piece("st", [("f", (0, 0)), ("top", (.15, .05)), ("p", (.3, 0)), ("t", (.3, -.15)), ("h", (.3, -.5)),
                        ("w", (0, -.5))])
    B = {"pieces": {"st": top}}
    A = ["st:f>top", "st:top>p>t"]
    la = sum(1000 * np.linalg.norm(np.diff(top["P"][ix], axis=0), axis=1).sum()
             for ix in ([0, 1], [1, 2, 3]))
    r = {"a": A, "b": "arm:x>y", "len_a_mm": la, "len_b_mm": 316.0 / 1.02, "band": (0.0, 0.05)}
    h = draft_runs.hint(B, r)
    assert "ended at p, dropping p...t" in h and "started at" not in h.split(";")[0].split("(its")[1].split("ended")[0]


def test_design_path_read(tmp_path):
    f = tmp_path / "design.mjs"
    f.write_text("export default new Design({})\n")
    assert pattern_parts.read_path(str(f)).startswith("export default") and pattern_parts.read_path("@" + str(f))
    with pytest.raises(pattern_parts.InspectRefused):
        pattern_parts.read_path(str(tmp_path / "missing.mjs"))


def test_vent_is_its_details_mark():
    d = draft_vents.with_marks({"vents": [{"name": "vent.L", "over": "side.L:vent", "under": "back.L:vent"}]},
                               {"details": {"vent.L": {"build": "full"}}})
    assert d["marks"]["vent.L"] == {"piece": "side.L", "follows": ["side.L:vent"]}
