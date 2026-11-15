"""draft_pattern (garment step 4, T5): the agent's own FreeSewing design drafted in Node, its declarations checked against
step 1, the one converter to the flat mesh chain_garment reads, the flat gate, the Node error path, the record write.
Needs Node >= 20 and the FreeSewing pack (skipped without them)."""
import json
import os
import shutil
from pathlib import Path

import pytest
from PIL import Image

from hifipushie import assets, store

RECT = """import { Design } from '@freesewing/core'
const panel = {
  name: 'test.panel',
  measurements: ['waist'],
  draft: ({ points, Point, paths, Path, measurements, part }) => {
    const w = measurements.waist / 4, h = 300
    points.tl = new Point(0, 0); points.tr = new Point(w, 0); points.br = new Point(w, h); points.bl = new Point(0, h)
    paths.seam = new Path().move(points.tl).line(points.bl).line(points.br).line(points.tr).line(points.tl).close()
    return part
  },
}
export default new Design({ parts: [panel] })
"""
STEP1 = {"pieces": {"panel.L": {"build": "full"}, "panel.R": {"build": "full"}},
         "seams": [{"a": "panel.L:side", "b": "panel.R:side"}, {"a": "panel.L:back", "b": "panel.R:back"}]}
DECL = {"pieces": {"panel.L": {"part": "test.panel", "place": {"to": "torso", "side": "front"}},
                   "panel.R": {"part": "test.panel", "mirror": True, "place": {"to": "torso", "side": "back"}}},
        "edges": {"panel.L": {"side": "tr>br", "back": "tl>bl"}, "panel.R": {"side": "tr>br", "back": "tl>bl"}},
        "seams": [{"a": "panel.L:side", "b": "panel.R:side"}, {"a": "panel.L:back", "b": "panel.R:back"}],
        "tapes": {"panel.L": ["waist"], "panel.R": ["waist"]}}
WAIST_LOOP = [[0.15 * __import__("math").cos(t / 8), 0.1 * __import__("math").sin(t / 8), 1.0] for t in range(51)]
STEP3 = {"measurements": [{"name": "waist", "mm": 800.0, "kind": "girth", "loop": WAIST_LOOP}]}


def _pack():
    try:
        return assets.pack("freesewing")
    except FileNotFoundError:
        p = Path(os.environ.get("HIFIPUSHIE_ASSETS_FALLBACK", "/home/joe/dev/hifipushie/workspace/_templates")) / "freesewing"
        return p if (p / "node_modules").exists() else None


PACK = _pack()
pytestmark = pytest.mark.skipif(PACK is None or not shutil.which("node"), reason="needs Node and the FreeSewing pack")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setattr(assets, "pack", lambda name: PACK)
    monkeypatch.setenv("HIFIPUSHIE_APPROVED", str(tmp_path / "approved.json"))
    return tmp_path


def _record(home, model="tm", garment="g"):
    from hifipushie import garment_record as gr
    ref = home / "ref.png"
    Image.new("RGB", (40, 60), (200, 40, 40)).save(ref)
    gr.write(model, garment, "0", "done", output={"kind": "test"}, reference=str(ref))
    gr.write(model, garment, "1", "done", output=STEP1)
    gr.write(model, garment, "2", "done", output={"state": {}})
    gr.write(model, garment, "3", "done", output=STEP3)


def test_rectangle_drafts_converts_and_passes(home):
    from hifipushie import chain_garment as cg, cloth, draft_own as do
    d = home / "draft"
    out = do.node_draft(RECT, {"waist": 800}, d=d)
    assert out["parts"]["test.panel"]["points"]["tr"] == [200, 0]
    assert do.validate(DECL, STEP1, out["parts"]) == []
    (d / "draft.json").write_text(json.dumps(out))
    (d / "declarations.json").write_text(json.dumps(DECL))
    B = cloth.pieces({"pattern": {"from": "own", "dir": str(d)}}, {"waist": 800})
    M = cloth.mesh(B)
    assert {"uv", "piece", "names", "F", "sew", "sew_seam", "border"} <= {k for k in cg.PATTERN_KEYS if k in M}
    assert len(M["sew"]) > 0
    B["edge_arcs"] = do.block({"dir": str(d)})["edge_arcs"]
    rows = {r["id"]: r for r in do.gate(B, DECL, STEP1)}
    assert rows["seams"]["status"] == rows["cut"]["status"] == rows["sewn"]["status"] == "PASS"


def test_refusals_by_name(home):
    from hifipushie import draft_own as do
    bad = dict(DECL, pieces=dict(DECL["pieces"], extra={"part": "test.panel"}),
               seams=[DECL["seams"][0]], edges={"panel.L": {"side": "tr>br"}, "panel.R": {"side": "tr>br"}})
    msgs = "\n".join(do.validate(bad, STEP1, {"test.panel": {}}))
    assert "'extra' is drafted but not in step 1" in msgs
    assert "step 1 seam panel.L:back <-> panel.R:back: no drafted edge 'panel.L:back'" in msgs
    assert "panel.L:back <-> panel.R:back is not sewn" in msgs
    one = dict(DECL, pieces={"panel.L": DECL["pieces"]["panel.L"]})
    assert any("step 1 piece 'panel.R' (build full) is not drafted" in m for m in do.validate(one, STEP1))
    eased = dict(DECL, seams=[dict(DECL["seams"][0], ease=[0, 0.05]), DECL["seams"][1]])
    assert any("an eased seam says why" in m for m in do.validate(eased, STEP1))


def test_seam_lengths_beyond_ease_fail(home):
    from hifipushie import cloth, draft_own as do
    two = RECT.replace("parts: [panel]", "parts: [panel, { ...panel, name: 'test.long', draft: (a) => { panel.draft(a); "
                       "a.points.br.y = 330; a.points.bl.y = 330; a.paths.seam = new a.Path().move(a.points.tl)"
                       ".line(a.points.bl).line(a.points.br).line(a.points.tr).line(a.points.tl).close(); return a.part } }]")
    d = home / "d2"
    out = do.node_draft(two, {"waist": 800}, d=d)
    decl = json.loads(json.dumps(DECL))
    decl["pieces"]["panel.R"]["part"] = "test.long"
    (d / "draft.json").write_text(json.dumps(out))
    (d / "declarations.json").write_text(json.dumps(decl))
    B = cloth.pieces({"pattern": {"from": "own", "dir": str(d)}}, {"waist": 800})
    rows = {r["id"]: r for r in do.gate(B, decl, STEP1)}
    assert rows["seams"]["status"] == "FAIL" and "outside" in rows["seams"]["why"]


def test_node_errors_name_the_line(home):
    from hifipushie import draft_own as do
    d = home / "e"
    with pytest.raises(do.DraftRefused, match=r"design\.mjs line 6: SyntaxError.*\n  6\| cont w"):
        do.node_draft(RECT.replace("const w", "cont w"), {"waist": 800}, d=d)
    with pytest.raises(do.DraftRefused, match=r"Cannot read properties of undefined"):
        do.node_draft(RECT.replace("measurements.waist / 4", "measurements.waist.a.b / 4"), {"waist": 800}, d=d)
    with pytest.raises(do.DraftRefused, match=r"needs measurements step 3 hasn't taken: chest"):
        do.node_draft(RECT.replace("['waist']", "['waist', 'chest']"), {"waist": 800}, d=d)
    with pytest.raises(do.DraftRefused, match=r"needs measurements step 3 hasn't taken: chest"):  # (read, undeclared: C361)
        do.node_draft(RECT.replace("const w = measurements.waist / 4", "const w = (measurements.chest || 800) / 4"),
                      {"waist": 800}, d=d)
    with pytest.raises(do.DraftRefused, match=r"sets measurements: chest"):  # (t s4-1: hpsToBust supplied in the design)
        do.node_draft(RECT.replace("const w = measurements.waist / 4", "measurements.chest = 900\n    const w = measurements.waist / 4"),
                      {"waist": 800}, d=d)
    with pytest.raises(do.DraftRefused, match=r"no draft after 3 s"):
        do.node_draft(RECT.replace("const w =", "while (true) {}\n    const w ="), {"waist": 800}, d=d, timeout=3)


def test_tool_writes_step4_and_reads_steps_1_and_3(home, monkeypatch):
    from hifipushie import draft_own_tool as dot, garment_record as gr
    saved = {}
    monkeypatch.setattr(store, "load", lambda name: json.loads(json.dumps(saved.get(name) or {})))
    monkeypatch.setattr(store, "save", lambda name, spec, note="": saved.__setitem__(name, spec) or 1)
    _record(home)
    assert set(gr.reads("tm", "g", "4")) == {"1", "2", "3"}  # (C392: step 2 too, for the planned folds)
    assert "reads" in gr.next_step(gr.load("tm", "g"))["uses"]
    # (G1: the girths row needs a length tape to place the waist on each panel, and panels round the body + its gap)
    gr.write("tm", "g", "3", "done", output={"measurements": STEP3["measurements"] + [
        {"name": "len", "mm": 600.0, "kind": "length", "path": [[0.05, -0.1, 1.15], [0.05, -0.1, 0.55]]}]})
    decl = dict(DECL, tapes={"panel.L": ["waist", "len"], "panel.R": ["waist", "len"]})
    rect = RECT.replace("measurements.waist / 4", "measurements.waist * 0.53")
    sheet, txt = dot.run("tm", "g", RECT, decl)
    assert "draft_pattern: FAIL" in txt and "girths" in txt and "can't be worn" in txt, txt  # (400 round on 800)
    sheet, txt = dot.run("tm", "g", rect, decl)
    assert "draft_pattern: PASS" in txt and Path(sheet).exists(), txt
    assert "pieces (" in txt and "seams (" in txt and " ease " in txt and "SHAPES" in txt  # (C288: numbers in text)
    st = gr.load("tm", "g")["steps"]["4"]
    assert st["status"] == "done" and st["gate"]["verdict"] == "PASS" and st["look"]
    assert saved["tm"]["cloth"]["g"]["pattern"]["from"] == "own"
    assert "pattern_check (own draft, the flat gate): PASS" in dot.check_text("tm", "g")
    _, txt = dot.run("tm", "g", rect, dict(decl, seams=DECL["seams"][:1]))
    assert "REFUSED" in txt and "panel.L:back <-> panel.R:back is not sewn" in txt


# ---------------------------------------------------------------- the flat gate's SHAPE rows (T5b, C295): no Node
def _piece(name, pts, names, to="torso"):
    import numpy as np
    return {"name": name, "P": np.asarray(pts, float), "names": names, "wrap": {"to": to}}


def _strip(name, lo, hi, n=21, to="neck"):
    """A strip: its bottom edge y = lo(x), top y = hi(x), x over [0, 0.4]; outline bl..br, tr..tl."""
    import numpy as np
    xs = np.linspace(0, 0.4, n)
    bot = [(x, lo(x)) for x in xs]
    top = [(x, hi(x)) for x in xs[::-1]]
    names = {"bl": 0, "bm": n // 2, "br": n - 1, "tr": n, "tm": n + n // 2, "tl": 2 * n - 1}
    return _piece(name, bot + top, names, to)


def _neckline():
    """A body piece whose neck edge drops 70 mm to CF on a curve (a front)."""
    import numpy as np
    t = np.linspace(0, np.pi / 2, 12)
    neck = [(0.08 * (1 - np.cos(u)), -0.07 * np.sin(u)) for u in t]  # hps (0, 0) -> cf (0.08, -0.07)
    pts = neck + [(0.08, -0.5), (0.25, -0.5), (0.2, 0.0)]
    return _piece("front", pts, {"hps": 0, "cf": 11, "hem": 12, "side": 13, "sh": 14})


def _B(stand, fall=None, fall_outer=None):
    B = {"pieces": {"front": _neckline(), "collar": stand}, "seams": [["collar:bl>bm>br", "front:hps>cf"]],
         "edge_arcs": {"front": {"neck": "hps>cf"}, "collar": {"neck": "bl>bm>br"}}, "folds": []}
    if fall is not None:
        B["pieces"]["fall"] = fall
        B["seams"].append(["fall:bl>bm>br", "collar:tl>tm>tr"])
        B["edge_arcs"]["fall"] = {"stand": "bl>bm>br", "outer": "tl>tm>tr"}
        B["folds"].append({"name": "roll", "piece": "fall", "kind": "roll", "line": {"edge": "bl>bm>br", "offset": 0.005}})
    return B


def _rows(B, role="collar_stand", ref=None):
    from hifipushie import draft_shape as ds
    decl = {"pieces": {"collar": {"role": role}}, "stiff": ["collar"]}
    return {r["id"]: r for r in ds.rows(B, decl, {"pieces": {}}, ref)}


# the stand's reference (T5c, C300): a front view at 1 mm/px, the body's hps 1.5 m up, 70 mm either side of CF
_AT = {"hps.L": [0.07, 0.0, 1.5], "shoulder.L": [0.2, 0.0, 1.45]}
_MARKS = [{"view": 0, "at": {"hps.R": [330, 100], "hps.L": [470, 100], "shoulder.R": [200, 150], "shoulder.L": [600, 150]}}]
LEVEL = [[340, 50], [370, 50], [400, 50], [430, 50], [460, 50]]  # the top 50 mm above the side neck, level to its ends
FOLLOWS = [[330, 120], [350, 90], [370, 65], [400, 50], [430, 65], [450, 90], [470, 120]]  # down the whole 70 mm drop


def _ref(points, corners=()):
    from hifipushie import draft_stand as dst
    plan = {"read": {"views": [{"view": "front", "image": "x.png"}]},
            "style": {"traces": [{"id": "top", "what": "collar_top", "view": 0, "points": points,
                                  "corners": list(corners)}], "body_marks": _MARKS}}
    return dst.reference(plan, _AT)


_bowl = lambda x: ((x - 0.2) / 0.2) ** 2  # 0 at the middle (CB), 1 at the strip's two ends (the front ends)
HUGS = (lambda x: 0.03 * _bowl(x), lambda x: 0.03 * _bowl(x) + 0.05)  # neck edge rising 30 mm, 50 mm tall all round
_slope = lambda x: (1 + (0.07 * 2 * (x - 0.2) / 0.04) ** 2) ** 0.5  # 1 / cos of the falling neck edge's slope
AWAY = (lambda x: -0.07 * _bowl(x), lambda x: -0.07 * _bowl(x) + (0.05 + 0.07 * _bowl(x)) * _slope(x))  # upright: neck
# edge falling 70 mm, 120 mm at the ends square to it, its top near straight
LEANS = (lambda x: -0.01 * _bowl(x), lambda x: -0.01 * _bowl(x) + 0.05 + 0.07 * _bowl(x))  # falling 10 mm only: the top
# curves up 60 mm in the flat, so the band leans with the neckline's plane (r-hussar build r1)


def _stand(lo_hi, lean_in=False):
    s = _strip("collar", *lo_hi)
    if lean_in:  # the free edge brought in 3 % about the middle: shorter than the neck edge
        c = s["P"][21:]
        c[:, 0] = 0.2 + 0.97 * (c[:, 0] - 0.2)
    return s


def test_stand_reference_reads_the_traced_top():
    r = _ref(LEVEL)
    assert abs(r["h_side"] - 50) < 0.5 and abs(r["T"]) < 0.5 and abs(r["tol"] - 6.0) < 0.5, r
    f = _ref(FOLLOWS)
    assert abs(f["T"] - 70) < 0.5, f


def test_a_traced_corner_ends_the_top_and_a_cut_away_front_isnt_held_to_a_front_height():  # (t s4-7; C377)
    cut = [[300, 130], [340, 90], [350, 55], [400, 50], [450, 55], [460, 90], [500, 130]]  # front ends slanting 45 deg
    assert _ref(cut)["T"] > 70 and not _ref(cut)["cut_away"]  # (no corners: the 45 deg slant reads as the top)
    r = _ref(cut, corners=[2, 4])
    assert abs(r["T"] - 5) < 0.5 and r["cut_away"], r
    row = _rows(_B(_stand(HUGS, lean_in=True)), ref=r)["shape_stand"]
    assert "cut away" in row["value"] and "h_side + D - T" not in row["why"], row


def test_shape_a_level_top_over_a_dropping_neckline_wants_taller_fronts_not_a_rise():
    r = _rows(_B(_stand(HUGS, lean_in=True)), ref=_ref(LEVEL))["shape_stand"]
    assert r["status"] == "FAIL" and "level" in r["value"], r
    assert "flatter / down" in r["why"] and "taller at its front ends" in r["why"] and r["back_to"] == "4", r["why"]
    ok = _rows(_B(_stand(AWAY)), ref=_ref(LEVEL))["shape_stand"]
    assert ok["status"] == "PASS", ok
    lean = _rows(_B(_stand(LEANS)), ref=_ref(LEVEL))["shape_stand"]  # tall fronts but a near-straight neck edge: not upright
    assert lean["status"] == "INFO (curve would FAIL)" and "flatter / down" in lean["why"] and "taller" not in lean["why"], lean


def test_shape_a_top_that_follows_the_neckline_wants_the_hugging_rise():
    ok = _rows(_B(_stand(HUGS, lean_in=True)), ref=_ref(FOLLOWS))["shape_stand"]
    assert ok["status"] == "PASS" and "hugging" in ok["value"], ok
    r = _rows(_B(_stand(AWAY)), ref=_ref(FOLLOWS))["shape_stand"]
    assert r["status"] == "FAIL" and "up (the ends towards the free edge)" in r["why"] and "lower at its front ends" in r["why"], r


def test_shape_no_trace_reports_the_stand_and_assumes_no_style():
    for s in (_stand(HUGS), _stand(AWAY), _strip("collar", lambda x: 0.0, lambda x: 0.048)):
        r = _rows(_B(s))
        assert r["shape_stand"]["status"] == "INFO" and "no style assumed" in r["shape_stand"]["value"], r["shape_stand"]
    assert "rising (hugs)" in _rows(_B(_stand(HUGS)))["shape_stand"]["value"]
    assert "near straight (upright)" in _rows(_B(_stand(LEANS)))["shape_stand"]["value"]
    falls = _strip("collar", lambda x: -0.03 * _bowl(x), lambda x: 0.05 - 0.03 * _bowl(x))
    assert "falling (stands away)" in _rows(_B(falls))["shape_stand"]["value"]
    sc = _rows(_B(_strip("collar", lambda x: 0.0, lambda x: 0.048)))["shape_seam_curve"]  # still named: straight on curved
    assert sc["status"] == "FAIL" and "collar:neck is straight" in sc["why"]


def test_shape_a_fall_shorter_outside_fails_and_longer_passes():
    rise = lambda x: 0.01 * ((x - 0.2) / 0.2) ** 2
    band = _strip("collar", rise, lambda x: rise(x) + 0.032)
    short = _strip("fall", rise, lambda x: rise(x) + 0.04)
    s = short["P"][21:]
    s[:, 0] = 0.2 + 0.95 * (s[:, 0] - 0.2)  # outer edge 5 % shorter than its stand seam: can't turn down
    r = _rows(_B(band, short), role="collar_band")
    assert r["shape_fall"]["status"] == "FAIL" and "change:" in r["shape_fall"]["why"]
    assert r["shape_stand"]["value"].startswith("collar (band)")
    long = _strip("fall", rise, lambda x: rise(x) + 0.04)
    q = long["P"][21:]
    q[:, 0] = 0.2 + 1.05 * (q[:, 0] - 0.2)
    assert _rows(_B(band, long), role="collar_band")["shape_fall"]["status"] == "PASS"


def test_shape_a_curved_edge_sewn_to_a_straight_one_fails():
    import numpy as np
    from hifipushie import draft_shape as ds
    a = _piece("a", [(x, 0.02 * np.sin(np.pi * x / 0.3)) for x in np.linspace(0, 0.3, 15)] + [(0.3, -0.1), (0, -0.1)],
               {"s": 0, "e": 14})
    b = _piece("b", [(0, 0), (0.15, 0), (0.3, 0), (0.3, 0.1), (0, 0.1)], {"s": 0, "m": 1, "e": 2})
    B = {"pieces": {"a": a, "b": b}, "seams": [["a:s>e", "b:s>m>e"]], "edge_arcs": {"a": {"curve": "s>e"}, "b": {"line": "s>m>e"}}}
    r = ds.seam_curve_rows(B, {}, {})
    assert r["status"] == "FAIL" and "b:line is straight" in r["why"]


def test_shape_stand_takes_the_neckline_drop_seen_not_the_flat():
    """r-hussar: a tilted front drops 70 mm on the flat but only 30 mm in the view (the collar_front traces' bottoms below
    the hps marks): a level top 50 mm above the side neck wants fronts ~80 mm tall, not 120; CB from the body's cb_neck."""
    from hifipushie import draft_stand as dst
    fronts = [{"id": "cf_R", "what": "collar_front", "view": 0, "points": [[385, 52], [390, 130]]},
              {"id": "cf_L", "what": "collar_front", "view": 0, "points": [[415, 52], [410, 130]]}]
    plan = {"read": {"views": [{"view": "front", "image": "x.png"}]},
            "style": {"traces": [{"id": "top", "what": "collar_top", "view": 0, "points": LEVEL}] + fronts,
                      "body_marks": _MARKS}}
    ref = dst.reference(plan, dict(_AT, cb_neck=[0.0, 0.05, 1.49]))
    assert abs(ref["D"] - 30) < 0.5 and abs(ref["D_back"] - 10) < 0.5 and "collar_front" in ref["D_how"], ref
    r = _rows(_B(_stand(AWAY)), ref=ref)["shape_stand"]  # 120 mm fronts: the flat's 70 mm drop asked for them
    assert "FAIL" in r["status"] and "lower at its front ends" in r["why"] and "wants h_side + D - T = 50 + 30 - 0 = 80" in r["why"], r
    # no collar_front trace: the body's cf_neck is the neckline seen
    ref2 = dst.reference({"read": plan["read"], "style": dict(plan["style"], traces=plan["style"]["traces"][:1])},
                         dict(_AT, cf_neck=[0.0, -0.08, 1.48]))
    assert abs(ref2["D"] - 20) < 0.5 and "cf_neck" in ref2["D_how"], ref2


# ---------------------------------------------------------------- fix run F2 (t8 findings 3, 4, 5)
def test_pattern_parts_lists_a_designs_parts_points_and_outline_order(home):
    from hifipushie import pattern_parts as pp
    _, txt = pp.run("brian")
    assert "measurements it needs" in txt and "waistToArmpit" in txt and "brian.base HIDDEN" in txt
    assert "brian.back: from brian.base" in txt and "seam runs (@ mm along it): cbNeck @0 >" in txt and "DEFAULT values" in txt
    look, one = pp.run("brian", part="brian.front", look_part=True)
    assert "points (x right, y down, mm): " in one and "cfNeck (" in one and "path seam: cfNeck @0 >" in one
    assert Path(look).exists()
    import re  # (t s4-25: a cap chain ran past the cap's end, 725 vs 481 mm: every point of a seam with its arc position)
    _, ts = pp.run("jaeger", part="jaeger.topsleeve")
    seam = next(x for x in ts.splitlines() if x.startswith("path seam: "))
    at = {m[0]: int(m[1]) for m in re.findall(r"([A-Za-z]\w*)(?:=\w+)* @(\d+)", seam)}
    assert {"tsRightEdge", "backPitchPoint", "top", "frontPitchPoint", "tsLeftEdge"} <= set(at), seam
    assert at["tsRightEdge"] < at["backPitchPoint"] < at["top"] < at["frontPitchPoint"] < at["tsLeftEdge"], at
    assert 50 < at["frontPitchPoint"] - at["backPitchPoint"] < 600 and "difference" in ts, at
    own = pp.inspect(RECT, {"waist": 800.0})  # the agent's own design: its parts, no measurement missing
    assert not own["missing"] and "test.panel" in own["parts"] and own["parts"]["test.panel"]["paths"]["seam"]["ops"]
    bad = pp.inspect(RECT.replace("measurements.waist / 4", "measurements.nope / 4"), {"waist": 800.0})  # (C361: NaN)
    assert {"tr", "br"} <= set(bad["nan"]["test.panel"])  # (x = waist / 4 is NaN; tl and bl sit at x 0)
    t = pp.text("own", bad)
    assert "points with NO value" in t and "tr" in t and "(no value)" in t


def test_draft_pattern_names_a_missing_measurement_before_drafting(home):
    from hifipushie import draft_own as do, draft_own_tool as dot, pattern_parts as pp
    src = ("import { Design } from '@freesewing/core'\nimport { back } from '@freesewing/brian'\n"
           "const b = { name: 'my.back', from: back, draft: ({ part }) => part }\nexport default new Design({ parts: [b] })\n")
    assert "waistToArmpit" in pp.missing(src, {"chest": 1000.0})
    _record(home)  # step 3 took only the waist
    with pytest.raises(do.DraftRefused, match=r"needs measurements step 3 hasn't taken: .*waistToArmpit"):
        dot.run("tm", "g", src, {"pieces": {}})


def test_shape_stand_reads_a_folded_stand_whole_and_its_fall_as_a_fall():
    """t8: a stand cut on the fold, sewn to front:neck and back:neck as two half edges, read as two stands each 'near
    straight' while its front ends rose; the fall sewn on its top (no role, no roll fold) read as no fall."""
    import numpy as np
    s = _stand(HUGS)  # neck edge rising 30 mm at both ends from CB (the middle)
    n = 21
    s["names"] = {"fe.m": 0, "sh.m": n // 2 - 3, "cb": n // 2, "sh": n // 2 + 3, "fe": n - 1, "ft": n, "cbt": n + n // 2,
                  "ft.m": 2 * n - 1}
    back = _piece("back", [(0, 0), (0.035, -0.015), (0.07, -0.02), (0.07, -0.5), (0.2, -0.5), (0.2, 0)],
                  {"hps": 0, "cb": 2})
    fall = _strip("fall", lambda x: 0.0, lambda x: 0.04 + 0.01 * _bowl(x))
    B = {"pieces": {"front": _neckline(), "back": back, "collar": s, "fall": fall},
         "seams": [["collar:sh>fe", "front:hps>cf"], ["collar:cb>sh", "back:hps>cb"], ["fall:bl>bm>br", "collar:ft>cbt"]],
         "edge_arcs": {"front": {"neck": "hps>cf"}, "back": {"neck": "hps>cb"},
                       "collar": {"bottom": "sh>fe", "bottom_back": "cb>sh", "top": "ft>cbt"},
                       "fall": {"bottom": "bl>bm>br", "outer": "tl>tm>tr"}}, "folds": []}
    from hifipushie import draft_shape as ds
    r = {x["id"]: x for x in ds.rows(B, {"pieces": {}, "stiff": ["collar", "fall"]}, {"pieces": {}})}
    v = r["shape_stand"]["value"]
    assert v.count("collar (") == 1 and "fall" not in v.split(";")[0].split(":")[0], v
    assert "collar (band): neck edge rising (hugs) +30.0 mm" in v, v
    assert "fall's outer edge" in r["shape_fall"]["value"].split(";")[0], r["shape_fall"]
    assert ds.full_arc(s, ["sh>fe", "cb>sh"]) == "fe.m>cb>fe" and ds.full_arc(s, ["ft>cbt"]) == "ft.m>cbt>ft"
    assert np.isfinite(ds.rise(s["P"][:n], s["P"][n + n // 2]))


def test_a_dart_open_on_the_outline_is_sewn(home):  # (t s4-1: no way to declare a dart; C361)
    import copy
    from hifipushie import cloth, draft_own as do
    src = RECT.replace(
        "paths.seam = new Path().move(points.tl).line(points.bl).line(points.br).line(points.tr).line(points.tl).close()",
        "points.d1 = new Point(w / 2 - 15, 0); points.tip = new Point(w / 2, 90); points.d2 = new Point(w / 2 + 15, 0)\n"
        "    paths.seam = new Path().move(points.tl).line(points.bl).line(points.br).line(points.tr).line(points.d2)"
        ".line(points.tip).line(points.d1).line(points.tl).close()")
    d = home / "dart"
    out = do.node_draft(src, {"waist": 800}, d=d)
    decl = copy.deepcopy(DECL)
    for p in ("panel.L", "panel.R"):
        decl["edges"][p].update({"in": "d1>tip", "out": "d2>tip"})
    decl["darts"] = [{"piece": "panel.L", "legs": ["in", "out"]}]
    assert do.validate(decl, STEP1, out["parts"]) == []
    (d / "draft.json").write_text(json.dumps(out))
    (d / "declarations.json").write_text(json.dumps(decl))
    B = cloth.pieces({"pattern": {"from": "own", "dir": str(d)}}, {"waist": 800})
    blk = do.block({"dir": str(d)})
    assert blk["darts"] and ["panel.L:d1>tip", "panel.L:d2>tip"] in blk["seams"]
    B["edge_arcs"], B["darts"] = blk["edge_arcs"], blk["darts"]
    rows = {r["id"]: r for r in do.gate(B, decl, STEP1)}
    assert rows["darts"]["status"] == "PASS" and rows["seams"]["status"] == "PASS"
    M = cloth.mesh(B)
    k = B["seams"].index(["panel.L:d1>tip", "panel.L:d2>tip"])
    assert k in set(int(x) for x in M["sew_seam"]), (k, sorted(set(int(x) for x in M["sew_seam"])))  # (the dart is sewn)
    decl["darts"] = [{"piece": "panel.L", "legs": ["in", "nope"]}]
    assert any("no edge nope" in b for b in do.validate(decl, STEP1, out["parts"]))


def test_a_slit_cut_by_hand_to_open_a_dart_fails(home):  # (t s4-22 / s4-23: 1 mm slits to the hem; C416)
    import copy
    from hifipushie import cloth, draft_own as do
    src = RECT.replace(
        "paths.seam = new Path().move(points.tl).line(points.bl).line(points.br).line(points.tr).line(points.tl).close()",
        "points.d1 = new Point(w / 2 - 0.5, 0); points.tip = new Point(w / 2, 90); points.d2 = new Point(w / 2 + 0.5, 0)\n"
        "    paths.seam = new Path().move(points.tl).line(points.bl).line(points.br).line(points.tr).line(points.d2)"
        ".line(points.tip).line(points.d1).line(points.tl).close()")
    d = home / "slit"
    out = do.node_draft(src, {"waist": 800}, d=d)
    decl = copy.deepcopy(DECL)
    for p in ("panel.L", "panel.R"):
        decl["edges"][p].update({"in": "d1>tip", "out": "d2>tip"})
    decl["darts"] = [{"piece": "panel.L", "legs": ["in", "out"]}]
    (d / "draft.json").write_text(json.dumps(out))
    (d / "declarations.json").write_text(json.dumps(decl))
    B = cloth.pieces({"pattern": {"from": "own", "dir": str(d)}}, {"waist": 800})
    blk = do.block({"dir": str(d)})
    B["edge_arcs"], B["darts"] = blk["edge_arcs"], blk["darts"]
    r = {x["id"]: x for x in do.gate(B, decl, STEP1)}["darts"]
    assert r["status"] == "FAIL" and "slit cut by hand" in r["why"] and "inside" in r["why"], r


def test_a_dart_inside_the_piece_is_cut_through_and_sewn(home):  # (t s4-23: a fish dart slit to the hem by hand; C416)
    import copy
    import numpy as np
    from hifipushie import cloth, draft_own as do, draft_dart_cut as dcut, pattern
    src = RECT.replace(
        "paths.seam = new Path().move(points.tl).line(points.bl).line(points.br).line(points.tr).line(points.tl).close()",
        "points.bm = new Point(w / 2, h); points.dt = new Point(w / 2, 60); points.dr = new Point(w / 2 + 15, 150)\n"
        "    points.db = new Point(w / 2, 240); points.dl = new Point(w / 2 - 15, 150); points.pk = new Point(w / 2, 255)\n"
        "    points.lm = new Point(0, 200); points.pr = new Point(w / 2 + 40, 200)\n"
        "    paths.seam = new Path().move(points.tl).line(points.bl).line(points.bm).line(points.br).line(points.tr)"
        ".line(points.tl).close()\n"
        "    paths.dart = new Path().move(points.dt).line(points.dr).line(points.db).line(points.dl).line(points.dt)"
        ".close().hide()")
    d = home / "idart"
    out = do.node_draft(src, {"waist": 800}, d=d)
    decl = copy.deepcopy(DECL)
    for p in ("panel.L", "panel.R"):
        decl["edges"][p].update({"hem_a": "bl>bm", "hem_b": "bm>br"})
    decl["darts"] = [{"piece": "panel.L", "inside": "dart", "release": ["pk", "bm"]}]
    assert do.validate(decl, STEP1, out["parts"]) == []
    (d / "draft.json").write_text(json.dumps(out))
    (d / "declarations.json").write_text(json.dumps(decl))
    B = cloth.pieces({"pattern": {"from": "own", "dir": str(d)}}, {"waist": 800})
    blk = do.block({"dir": str(d)})
    pc = blk["pieces"]["panel.L"]
    assert dcut._simple(np.asarray(pc["P"]))
    L = lambda e: pattern.length(pc["P"][pattern.arc_indices(pc, e.split(":", 1)[1])])
    (ca, cb), (la, lb) = ([L(e) for e in dt_["legs"]] for dt_ in blk["darts"])  # (the cut, then the dart's sides)
    assert abs(ca / cb - 1) < 0.005 and abs(ca - 0.060) < 0.002, (ca, cb)  # (bm up to pk, on to the bottom tip)
    assert abs(la / lb - 1) < 0.005 and abs(la - 0.1825) < 0.002, (la, lb)
    assert pc["names"]["dt"] == pc["names"]["dart.tip"]  # (the part's own tip keeps its name: a mark can use it)
    legs = blk["darts"][1]["legs"]
    ha, hb = (pattern.length(pc["P"][pattern.arc_indices(pc, blk["edge_arcs"]["panel.L"][e])]) for e in ("hem_a", "hem_b"))
    assert abs(ha - 0.1) < 0.002 and abs(hb - 0.1) < 0.002, (ha, hb)  # (each hem half keeps its own side of the cut)
    B["edge_arcs"], B["darts"] = blk["edge_arcs"], blk["darts"]
    rows = {r["id"]: r for r in do.gate(B, decl, STEP1)}
    assert rows["darts"]["status"] == "PASS" and rows["seams"]["status"] == "PASS", (rows["darts"], rows["seams"])
    M = cloth.mesh(B)
    k = B["seams"].index(legs)
    assert k in set(int(x) for x in M["sew_seam"])
    cross = copy.deepcopy(decl)  # (a pocket mouth crossing the dart's side: the cut stops at the side, C416)
    cross["edges"]["panel.L"].update({"back_a": "tl>lm", "back_b": "lm>bl"})
    cross["edges"]["panel.L"].pop("back")
    cross["seams"][1]["a"] = ["panel.L:back_a", "panel.L:back_b"]
    cross["darts"] = [{"piece": "panel.L", "inside": "dart", "release": ["pr", "lm"]}]
    (d / "declarations.json").write_text(json.dumps(cross))
    blk = do.block({"dir": str(d)})
    pc = blk["pieces"]["panel.L"]
    assert dcut._simple(np.asarray(pc["P"])) and len(blk["darts"]) == 3
    (ca, cb), (ua, ub), (wa, wb) = ([L(e) for e in dt_["legs"]] for dt_ in blk["darts"])
    assert abs(ca / cb - 1) < 0.005 and abs(ca - (0.1 - 0.015 * 50 / 90)) < 0.002, (ca, cb)  # (lm across to the left side)
    assert abs(ua / ub - 1) < 0.005 and abs(wa / wb - 1) < 0.01 and abs(ua + wa - 0.1825) < 0.002, (ua, ub, wa, wb)
    B = cloth.pieces({"pattern": {"from": "own", "dir": str(d)}}, {"waist": 800})
    B["edge_arcs"], B["darts"] = blk["edge_arcs"], blk["darts"]
    rows = {r["id"]: r for r in do.gate(B, cross, STEP1)}
    assert rows["darts"]["status"] == "PASS" and rows["seams"]["status"] == "PASS", (rows["darts"], rows["seams"])
    assert len(set(int(x) for x in cloth.mesh(B)["sew_seam"])) == len(B["seams"])
    bad = copy.deepcopy(decl)
    bad["darts"] = [{"piece": "panel.L", "inside": "nodart", "release": ["bm"], "legs": ["x", "y"]}]
    why = " ".join(do.validate(bad, STEP1, out["parts"]))
    assert "no legs" in why and "not a path of the part" in why, why
    run = copy.deepcopy(decl)  # (the release lands partway along a sewn edge: t s4-25, through a pocket to the side seam)
    run["darts"] = [{"piece": "panel.L", "inside": "dart", "release": ["pr", "lm"]}]
    (d / "declarations.json").write_text(json.dumps(run))
    blk = do.block({"dir": str(d)})
    pc, ea = blk["pieces"]["panel.L"], blk["edge_arcs"]["panel.L"]
    assert "back" not in ea and dcut._simple(np.asarray(pc["P"]))
    b1, b2 = (pattern.length(pc["P"][pattern.arc_indices(pc, ea[e])]) for e in ("back.1", "back.2"))
    assert abs(b1 - 0.2) < 0.002 and abs(b2 - 0.1) < 0.002, (b1, b2)  # (each half keeps its length)
    chain = [s_ for s_ in blk["seams"] if any(isinstance(x, list) for x in s_)]
    assert len(chain) == 1 and chain[0][0] == [f"panel.L:{ea['back.1']}", f"panel.L:{ea['back.2']}"], blk["seams"]
    B = cloth.pieces({"pattern": {"from": "own", "dir": str(d)}}, {"waist": 800})
    B["edge_arcs"], B["darts"] = blk["edge_arcs"], blk["darts"]
    rows = {r["id"]: r for r in do.gate(B, run, STEP1)}
    for r in ("darts", "seams", "sewn"):
        assert rows.get(r, {"status": "PASS"})["status"] == "PASS", rows.get(r)
    M = cloth.mesh(B)
    k = B["seams"].index(chain[0])
    assert len(set(int(x) for x in M["sew_seam"])) == len(B["seams"]), "every seam sewn"
    sw, P = np.asarray(M["sew"]).reshape(-1, 2), M["points"]
    mate = lambda v: {int(b) for a, b in sw if a == v} | {int(a) for a, b in sw if b == v}
    assert mate(P["panel.L:dart.cut_a"]) & mate(P["panel.L:dart.cut_b"]) == {P["panel.R:lm"]}  # (one partner vertex)
    assert abs(np.linalg.norm(M["uv"][P["panel.R:lm"]] - M["uv"][P["panel.R:tl"]]) - 0.2) < 0.002  # (0.2 m down its back)
    lap = copy.deepcopy(decl)  # (two sewn edges overlapping: said by piece and point names, never indices; t s4-25)
    lap.pop("darts")
    for p in ("panel.L", "panel.R"):
        lap["edges"][p]["low"] = "lm>bl"
    lap["seams"].append({"a": "panel.L:low", "b": "panel.R:low"})
    (d / "declarations.json").write_text(json.dumps(lap))
    with pytest.raises(ValueError, match=r"overlap: panel\.\w:tl>bl \(seam 2\) and panel\.\w:lm>bl \(seam 3\)"):
        cloth.mesh(cloth.pieces({"pattern": {"from": "own", "dir": str(d)}}, {"waist": 800}))



def test_s4_2_gaps_options_exports_edges_blocks(home):  # (C362)
    import copy
    from hifipushie import body_tape_record as btr, draft_own as do, draft_own_tool as dt, pattern_parts as pp
    cfg = {"sleevecapEase": {"pct": 1, "min": 0, "max": 10}}
    assert "did you mean 0.04" in dt.option_errors({"sleevecapEase": 4}, cfg)[0]
    assert dt.option_errors({"sleevecapEase": 0.04}, cfg) == []
    _, t = pp.run("jaeger")
    assert "jaeger.front: from jaeger.frontBase" in t and "NOT EXPORTED: import an exported part and reach it as" in t
    d = home / "zero"
    src = RECT.replace("points.tr = new Point(w, 0)", "points.tr = new Point(w, 0); points.tr2 = new Point(w, 0)").replace(
        ".line(points.tr).line(points.tl)", ".line(points.tr).line(points.tr2).line(points.tl)")
    out = do.node_draft(src, {"waist": 800}, d=d)
    decl = copy.deepcopy(DECL)
    decl["edges"]["panel.L"]["nil"] = "tr>tr2"
    (d / "draft.json").write_text(json.dumps(out))
    (d / "declarations.json").write_text(json.dumps(decl))
    with pytest.raises(do.DraftRefused, match=r"edges\.panel\.L\.nil = 'tr>tr2'.*0 mm long"):
        do.block({"dir": str(d)})
    msg = btr.blocks({"chest", "waist"})
    assert "FreeSewing's blocks" in msg and "brian needs" in msg and "hpsToBust" in msg


def test_a_pair_declared_once_validates_and_builds(home):  # (t s4-3: pair never produced the .R pieces; C364)
    from hifipushie import cloth, draft_own as do
    d = home / "pair"
    out = do.node_draft(RECT, {"waist": 800}, d=d)
    decl = {"pieces": {"panel": {"part": "test.panel", "pair": True, "place": {"to": "torso", "side": "front"}}},
            "edges": {"panel": {"side": "tr>br", "back": "tl>bl"}},
            "seams": [{"a": "panel:side", "b": "panel:side"}, {"a": "panel:back", "b": "panel:back"}]}
    assert do.validate(decl, STEP1, out["parts"]) == []
    (d / "draft.json").write_text(json.dumps(out))
    (d / "declarations.json").write_text(json.dumps(decl))
    B = cloth.pieces({"pattern": {"from": "own", "dir": str(d)}}, {"waist": 800})
    assert {"panel.L", "panel.R"} <= set(B["pieces"])


def test_an_unsewn_step1_seam_names_the_chain_way():  # (t s4-4: a two-piece sleeve's cap as one chained seam; C365)
    from hifipushie import draft_own as do
    decl = {"pieces": {"panel.L": {"part": "p"}, "panel.R": {"part": "p"}},
            "edges": {"panel.L": {"side": "a>b", "back": "c>d"}, "panel.R": {"side": "a>b", "back": "c>d"}}, "seams": []}
    bad = do.validate(decl, STEP1)
    assert any("is not sewn" in b and "as ONE seam" in b for b in bad), bad


def test_a_canvas_sewn_edge_to_edge_is_a_layer_and_neck_named_edges_count():  # (t s4-7; C377)
    import numpy as np
    from hifipushie import draft_own as do, draft_shape as ds
    sq = lambda n: {"name": n, "P": np.asarray([[0, 0], [0.1, 0], [0.1, 0.04], [0, 0.04]], float),
                    "names": {"a": 0, "b": 1, "c": 2, "d": 3}}
    arcs = {"collar": {"neck_front": "a>b", "top": "c>d"}, "canvas": {"neck_front": "a>b", "top": "c>d"},
            "front": {"neckline": "a>b"}}
    B = {"pieces": {k: sq(k) for k in arcs}, "edge_arcs": arcs, "folds": [],
         "seams": [["collar:a>b", "front:a>b"], ["canvas:c>d", "collar:c>d"], ["canvas:a>b", "collar:a>b"]]}
    assert ds.layers(B) == {"canvas": "collar"}
    assert ds.is_neck("neck_front") and ds.is_neck("neckline") and not ds.is_neck("top")
    assert "canvas" not in ds.fall_pieces(B, {"stiff": ["collar"]}, {})
    bad = do.validate({"pieces": {"x": {"part": "p", "role": "stand"}}}, {"pieces": {"x": {}}}, None)
    assert any("role 'stand' is not a role" in b and "collar_stand" in b for b in (bad if isinstance(bad, list) else [str(bad)])), bad


def test_pairs_expand_side_named_seams_darts_and_marks(home):  # (t s4-5: half the pair handling; C366)
    from hifipushie import draft_own as do, draft_pairs as dp
    out = do.node_draft(RECT, {"waist": 800}, d=home / "pairs2")
    decl = {"pieces": {"front": {"part": "test.panel", "pair": True}, "back": {"part": "test.panel", "pair": True}},
            "edges": {"front": {"side": "tr>br", "in": "tl>bl"}, "back": {"side": "tr>br", "in": "tl>bl"}},
            "seams": [{"a": "front.L:side", "b": "back.L:side"}],
            "darts": [{"piece": "front", "legs": ["side", "in"]}],
            "marks": {"pocket.R": {"piece": "front", "at": [{"point": "tl"}]}, "pad": {"piece": "front", "follows": ["front:side"]}}}
    D = dp.expand(decl, out["parts"])
    ends = {(s["a"], s["b"]) for s in D["seams"]}
    assert ("front.L:side", "back.L:side") in ends and ("front.R:side", "back.R:side") in ends  # (the .R twin)
    assert {d["piece"] for d in D["darts"]} == {"front.L", "front.R"}
    assert D["marks"]["pocket.R"]["piece"] == "front.R"
    assert D["marks"]["pad"]["piece"] == "front.L" and D["marks"]["pad"]["follows"] == ["front.L:side"] and D["marks"]["pad"]["mirror"]


def test_a_centre_pieces_side_named_seam_is_twinned(home):  # (t s4-6: the collar's .R seams by hand; C376)
    from hifipushie import draft_own as do, draft_pairs as dp
    out = do.node_draft(RECT, {"waist": 800}, d=home / "pairs3")
    decl = {"pieces": {"front": {"part": "test.panel", "pair": True}, "collar": {"part": "test.panel"}},
            "edges": {"front": {"neck": "tl>tr"}, "collar": {"neck.L": "tl>tr", "neck.R": "br>bl"}},
            "seams": [{"a": "collar:neck.L", "b": "front.L:neck"}]}
    ends = {(s["a"], s["b"]) for s in dp.expand(decl, out["parts"])["seams"]}
    assert ("collar:neck.R", "front.R:neck") in ends, ends


def test_a_gate_rows_reasons_print_in_full():  # (t s4-8: one line cut at 600 characters hid `change:`; C378)
    from hifipushie import draft_own_tool as dot
    why = "; ".join(f"collar.{s}: {'x' * 400} change: make it 26 mm taller at the back" for s in "LR")
    ln = dot.row_lines({"status": "FAIL", "id": "shape_stand", "value": "v" * 900, "why": why, "fix": "redraft"})
    assert sum("change: make it 26 mm taller" in x for x in ln) == 2 and ln[-1] == "      fix: redraft", ln
    assert dot.row_lines({"status": "PASS", "id": "seams", "value": "ok", "why": "", "fix": "redraft"}) == ["  PASS seams: ok"]


def test_an_edge_sewn_in_two_seams_is_sampled_once():  # (t s4-9: a collar's neck edge on the neckline and its canvas; C379)
    import numpy as np
    from hifipushie import cloth

    def rect(nm, w, h):
        return {"name": nm, "P": np.array([[0, 0], [w, 0], [w, h], [0, h]], float),
                "names": {"a": 0, "b": 1, "c": 2, "d": 3}, "marks": {}, "lines": {}, "wrap": {"to": "torso"}}
    # the collar's a>b (100 mm) sewn to the neckline (eased: 121 mm, 7 samples at 20 mm) and to its canvas (100 mm, 5)
    B = {"pieces": {"collar": rect("collar", 0.1, 0.04), "canvas": rect("canvas", 0.1, 0.04),
                    "front": rect("front", 0.121, 0.3)},
         "seams": [["collar:a>b", "front:a>b"], ["canvas:a>b", "collar:a>b"]], "stitches": []}
    M = cloth.mesh(B, 0.02)
    per = [int(np.sum(np.asarray(M["sew_seam"]) == k)) for k in (0, 1)]
    assert per[0] == per[1] and per[0] >= 7, per


def test_step4_places_every_mark_and_compares_step1s_lengths():  # (t s4-10: marks unplaced until step 7; C380)
    import numpy as np
    from hifipushie import cloth, draft_body_lengths as dbl, draft_marks, garment_details as gd

    def rect(nm, w, h):
        return {"name": nm, "P": np.array([[0, 0], [w, 0], [w, h], [0, h]], float),
                "names": {"a": 0, "b": 1, "c": 2, "d": 3}, "marks": {}, "lines": {}, "wrap": {"to": "torso"}}
    B = {"pieces": {"front.L": rect("front.L", 0.2, 0.5), "front.R": rect("front.R", 0.2, 0.5)},
         "seams": [["front.L:a>b", "front.R:a>b"]], "stitches": []}
    M = cloth.mesh(B, 0.02)
    step1 = {"details": {"braid.L": {"build": "full", "on": ["front.L"]}}}
    edges = {"front.L": {"cf": "b>c"}, "front.R": {"cf": "b>c"}}
    ok = {"edges": edges, "marks": {"braid.L": {"piece": "front.L", "mirror": True, "path": [
        {"point": "c", "dx": -50, "dy": -10}, {"point": "c", "dx": -50, "dy": -300}]}}}
    row, drawn = draft_marks.place(M, ok, step1)
    assert row["status"] == "PASS" and set(drawn) == {"front.L", "front.R"}, row  # (the mirrored pass is the .R detail)
    down = {"edges": edges, "marks": {"braid.L": {"piece": "front.L", "path": [{"point": "c", "dx": -50, "dy": 300}]}}}
    row = draft_marks.place(M, down, step1)[0]
    assert row["status"] == "FAIL" and "dy runs UP" in row["why"], row
    # step 1's estimate against the drafted seam, both sides named by their sides (front.L / front.R)
    B["decl"] = {"seams": [{"a": "front.L:hem", "b": "front.R:hem"}]}
    s1 = {"seams": [{"a": "front.L:hem", "b": "front.R:hem", "length": {"style": {"value_mm": 240, "source": "seen"}}}]}
    r = dbl.style_rows(B, s1, {"measurements": []})[0]
    assert r["status"] == "INFO" and "drafted 200 mm, step 1 240 mm" in r["info"], r
    assert gd.DY_HINT


def test_s4_11_step1_departures_fold_halves_whole_stands_mirrored_marks_and_layers():  # (t s4-11; C381)
    import numpy as np
    from hifipushie import cloth, draft_body_lengths as dbl, draft_marks, draft_own as do, draft_shape as ds
    from hifipushie import pattern_sheet as ps

    def rect(nm, w, h, sgn=1):
        return {"name": nm, "P": np.array([[0, 0], [sgn * w, 0], [sgn * w, h], [0, h]], float)[::sgn],
                "names": {"a": 0, "b": 1, "c": 2, "d": 3} if sgn > 0 else {"a": 3, "b": 2, "c": 1, "d": 0},
                "marks": {}, "lines": {}, "wrap": {"to": "torso"}}
    # 1. far off step 1's approved estimate: refused unless `departs` says why
    B = {"pieces": {"front.L": rect("front.L", 0.2, 0.5), "front.R": rect("front.R", 0.2, 0.5)},
         "seams": [["front.L:a>b", "front.R:a>b"]], "stitches": [],
         "decl": {"seams": [{"a": "front.L:hem", "b": "front.R:hem"}]}}
    s1 = {"seams": [{"a": "front.L:hem", "b": "front.R:hem", "length": {"style": {"value_mm": 400, "source": "seen"}}}]}
    r = dbl.style_rows(B, s1, {"measurements": []})[0]
    assert r["status"] == "FAIL" and "-50%" in r["why"] and "departs" in r["fix"], r
    B["decl"]["departs"] = {"front:hem": "the reference's hem is shorter: the tab ends at the side"}
    r = dbl.style_rows(B, s1, {"measurements": []})[0]
    assert r["status"] == "INFO" and "departs: the reference" in r["info"], r
    # 2. step 1's two halves joined by a fold: a fold on one half doesn't join them; one piece cut on the fold does
    step1 = {"pieces": {"collar.L": {"build": "full"}, "collar.R": {"build": "full"}},
             "seams": [{"a": "collar.L:cb", "b": "collar.R:cb", "kind": "fold"}]}
    half = {"pieces": {"collar.L": {"part": "x"}, "collar.R": {"part": "x"}},
            "edges": {"collar.L": {"cb": "a>b"}, "collar.R": {"cb": "a>b"}},
            "folds": [{"name": "cb", "piece": "collar.L", "line": "cb", "kind": "press"}]}
    assert any("joins two halves" in b for b in do.validate(half, step1)), do.validate(half, step1)
    sewn = dict(half, folds=[], seams=[{"a": "collar.L:cb", "b": "collar.R:cb"}])
    assert not do.validate(sewn, step1), do.validate(sewn, step1)
    one = {"pieces": {"collar": {"part": "x", "fold": "x0"}}, "edges": {"collar": {"cb": "a>b"}}}
    assert not do.validate(one, step1), do.validate(one, step1)
    # 3. a {point, dx} mark mirrored onto a pair's mirrored copy: dx runs the other way
    B = {"pieces": {"front.L": rect("front.L", 0.2, 0.5), "front.R": rect("front.R", 0.2, 0.5, -1)},
         "seams": [["front.L:a>b", "front.R:a>b"]], "stitches": []}
    M = cloth.mesh(B, 0.02)
    st = {"details": {"braid.L": {"build": "full", "on": ["front.L"]}}}
    mk = {"edges": {}, "marks": {"braid.L": {"piece": "front.L", "mirror": True, "path": [
        {"point": "c", "dx": -50, "dy": -10}, {"point": "c", "dx": -50, "dy": -300}]}}}
    row, drawn = draft_marks.place(M, mk, st)
    assert row["status"] == "PASS" and set(drawn) == {"front.L", "front.R"}, row
    # 4. a half stand sewn to its mirror at CB is judged whole: the rise of the whole, not the half's sagitta
    from test_draft_own import _B, _ref, _piece, HUGS, FOLLOWS, _strip
    whole = {r["id"]: r for r in ds.rows(_B(_strip("collar", *HUGS)), {"pieces": {"collar": {"role": "collar_stand"}},
                                         "stiff": ["collar"]}, {"pieces": {}}, _ref(FOLLOWS))}["shape_stand"]
    lo, hi = HUGS
    xs = np.linspace(0.2, 0.4, 11)

    def h(nm, sgn):
        return _piece(nm, [(0.2 + sgn * (x - 0.2), lo(x)) for x in xs] + [(0.2 + sgn * (x - 0.2), hi(x)) for x in xs[::-1]],
                      {"bl": 0, "br": 10, "tr": 11, "tl": 21}, "neck")
    Bh = _B(_strip("collar", *HUGS))
    Bh["pieces"] = {"front": Bh["pieces"]["front"], "collar.L": h("collar.L", 1), "collar.R": h("collar.R", -1)}
    Bh["seams"] = [["collar.L:bl>br", "front:hps>cf"], ["collar.L:tl>bl", "collar.R:tl>bl"]]
    Bh["edge_arcs"] = {"front": {"neck": "hps>cf"}, "collar.L": {"neck": "bl>br", "cb": "tl>bl"}, "collar.R": {"cb": "tl>bl"}}
    r = {x["id"]: x for x in ds.rows(Bh, {"pieces": {"collar.L": {"role": "collar_stand"}}, "stiff": ["collar.L"]},
                                     {"pieces": {}}, _ref(FOLLOWS))}["shape_stand"]
    assert "whole: mirrored at collar.L:cb" in r["value"] and "+30.0 mm" in r["value"] and "+30.0 mm" in whole["value"], r
    # 5. a canvas sewn edge to edge onto a piece is listed as its layer, with the host's role
    Bl = {"pieces": {"collar": rect("collar", 0.2, 0.05), "collar_canvas": rect("collar_canvas", 0.2, 0.05),
                     "back": rect("back", 0.2, 0.5)},
          "seams": [["collar:a>b", "collar_canvas:a>b"], ["collar:c>d", "back:c>d"]],
          "edge_arcs": {"collar": {"top": "a>b", "neck": "c>d"}, "collar_canvas": {"top": "a>b"}, "back": {"neck": "c>d"}}}
    txt = "\n".join(ps.text_lines(Bl, decl={"pieces": {"collar": {"role": "collar_stand"}}}))
    assert "collar_canvas: " in txt and "layer of collar (its role: collar_stand)" in txt, txt



def test_s4_12_a_fold_piece_takes_step1s_half_names_and_mirror_seams_arent_hosts(home):  # (t s4-12; C382)
    from hifipushie import draft_own as do, draft_pairs as dp, draft_shape as ds
    out = do.node_draft(RECT, {"waist": 800}, d=home / "fold12")
    decl = {"pieces": {"front": {"part": "test.panel", "pair": True}, "collar": {"part": "test.panel", "fold": "x0",
                                                                                       "place": {"to": "neck"}}},
            "edges": {"front": {"neck": "tl>tr"}, "collar": {"neck": "tl>tr"}},
            "seams": [{"a": "front.L:neck", "b": "collar.L:neck"}],
            "marks": {"binding.L": {"piece": "collar.L", "follows": ["collar.L:neck"]}}}
    ex = dp.expand(decl, out["parts"])
    got = {(s["a"], s["b"]) for s in ex["seams"]}
    assert {b for _, b in got} == {"collar:neck", "collar:neck.m"} and {a for a, _ in got} == {"front.L:neck", "front.R:neck"}, got
    assert ex["marks"]["binding.L"]["piece"] == "collar" and ex["edges"]["collar"].get("neck.m") or \
        ex["marks"]["binding.L"]["follows"] == ["collar:neck"], ex["marks"]
    fl = dict(decl, seams=[{"a": "collar.L:neck", "b": "collar.R:neck"}])
    s1 = {"pieces": {n: {"build": "full"} for n in ("front.L", "front.R", "collar.L", "collar.R")}}
    assert any("fold line" in b for b in do.validate(fl, s1, out["parts"])), do.validate(fl, s1, out["parts"])
    # a facing sewn top to top on its stand AND to its own mirror at CB is still the stand's layer, not a fall
    B = {"pieces": {n: {} for n in ("collar.L", "collar.R", "facing.L", "facing.R", "front")},
         "seams": [["collar.L:a>b", "facing.L:a>b"], ["facing.L:c>d", "facing.R:c>d"], ["collar.L:e>f", "front:e>f"]],
         "edge_arcs": {"collar.L": {"top": "a>b"}, "facing.L": {"top": "a>b", "cb": "c>d"}, "facing.R": {"cb": "c>d"},
                       "front": {"neck": "e>f"}}}
    assert ds.layers(B).get("facing.L") == "collar.L", ds.layers(B)


def test_a_cut_away_stand_isnt_held_to_the_neck_girth():  # (t s4-12: its top doesn't close round the neck; C382)
    cut = [[300, 130], [340, 90], [350, 55], [400, 50], [450, 55], [460, 90], [500, 130]]
    r = _ref(cut, corners=[2, 4])
    r["top_girth"] = {"at": None, "nearest": {"name": "neck", "mm": 1000.0, "dz": -50.0}}
    row = _rows(_B(_stand(HUGS, lean_in=True)), ref=r)["shape_stand"]
    assert "the top doesn't close round the neck" in row["value"] and "grips" not in row["why"], row


def _tube(widths, tapes, closure=None, cut=0.0):
    """Pieces in a ring (rectangles 0.9 m long, flat y up), a waist loop of 800 mm at z 1.0, a length tape from z 1.5."""
    import numpy as np
    names = list(widths)
    pcs = {}
    for i, (nm, w) in enumerate(widths.items()):
        P = [[0, 0], [w, 0], [w, -0.9], [0, -0.9]]
        if cut and i == 0:
            P[3] = [cut, -0.9]  # (its free front edge runs in: a cut-away)
        if cut and i == len(names) - 1:
            P[2] = [w - cut, -0.9]
        pcs[nm] = {"name": nm, "P": np.array(P, float), "names": {"tl": 0, "tr": 1, "br": 2, "bl": 3}, "marks": {},
                   "wrap": {"to": "torso"}}
    seams = [[f"{a}:tr>br", f"{b}:tl>bl"] for a, b in zip(names, names[1:])]
    if closure is None:
        seams.append([f"{names[-1]}:tr>br", f"{names[0]}:tl>bl"])
    r = 800 / (2000 * np.pi)
    th = np.linspace(0, 2 * np.pi, 65)[:-1]
    s3 = {"measurements": [{"name": "waist", "mm": 800.0, "loop": [[r * np.cos(t), r * np.sin(t), 1.0] for t in th]},
                           {"name": "len", "mm": 900.0, "path": [[0.05, -r, 1.5], [0.05, -r, 0.6]]}]}
    B = {"pieces": pcs, "seams": seams, "edge_arcs": {}, "closures": closure or [], "decl": {"tapes": tapes}}
    return B, s3


def test_g1_the_pattern_round_every_girth_vs_body_plus_the_plans_ease():  # (G1: D2's jacket, 70-130 mm under its plan)
    from hifipushie import draft_girths as dg
    tp = {"a": ["len", "waist"], "b": ["len", "waist"]}
    B, s3 = _tube({"a": 0.425, "b": 0.425}, tp)  # (850 round: 30 under 800 + 80)
    r = dg.rows(B, s3, {"waist": {"ease_mm": 80.0}})[0]
    assert r["status"] == "FAIL" and "waist: pattern 850 mm, body 800, planned ease 80" in r["value"], r
    assert "30 mm too tight" in r["why"] and "widen a, b at the waist line by 30 mm" in r["why"], r
    B, s3 = _tube({"a": 0.44, "b": 0.44}, tp)
    assert dg.rows(B, s3, {"waist": {"ease_mm": 80.0}})[0]["status"] == "PASS"
    assert dg.rows(B, s3, {"waist": {"ease_mm": 200.0}})[0]["status"] == "FAIL"  # (off by 120 > 15 % of 200)
    B, s3 = _tube({"a": 0.405, "b": 0.405}, tp)  # (810: under 800 + the cloth's gap, no plan ease stated)
    r = dg.rows(B, s3, {})[0]
    assert r["status"] == "FAIL" and "can't be worn" in r["why"] and "none stated" in r["value"], r
    # a piece in the ring whose tapes don't name the girth: a missing declaration, by name
    B, s3 = _tube({"a": 0.44, "b": 0.44}, {"a": ["len", "waist"], "b": ["len"]})
    r = dg.rows(B, s3, {"waist": {"ease_mm": 80.0}})[0]
    assert r["status"] == "FAIL" and "b lie(s) in the waist ring but its tapes don't name 'waist'" in r["why"], r
    B, s3 = _tube({"a": 0.44, "b": 0.44}, {"a": ["waist"], "b": ["waist"]})  # (no length tape: no level)
    assert "no length tape declared" in dg.rows(B, s3, {})[0]["why"]


def test_g1_a_closures_lap_comes_off_and_an_open_front_is_cloth_only():
    from hifipushie import draft_girths as dg
    tp = {p: ["len", "waist"] for p in ("fl", "bk", "fr")}
    cl = [{"name": "front", "over": "fl", "under": "fr", "edge": {"over": "tl>bl", "under": "tr>br"},
           "pairs": [["h1", "b1"], ["h2", "b2"]]}]
    B, s3 = _tube({"fl": 0.24, "bk": 0.44, "fr": 0.24}, tp, closure=cl)
    B["pieces"]["fl"]["marks"] = {"h1": [0.02, -0.2], "h2": [0.02, -0.6]}
    B["pieces"]["fr"]["marks"] = {"b1": [0.22, -0.2], "b2": [0.22, -0.6]}
    r = dg.rows(B, s3, {"waist": {"ease_mm": 80.0}})[0]  # (920 of cloth less 40 of lap = 880)
    assert r["status"] == "PASS" and "pattern 880 mm" in r["value"] and "lap -40" in r["value"], r
    B["pieces"]["fl"]["marks"] = {}
    assert "no fastening marks" in dg.rows(B, s3, {})[0]["why"]
    # cut away below the button: the edges stand short of the centre line at the waist: open, cloth only, no
    # can't-be-worn FAIL; the plan's girth (the garment closed) still holds it
    B, s3 = _tube({"fl": 0.2, "bk": 0.4, "fr": 0.2}, tp, closure=cl, cut=0.09)
    B["pieces"]["fl"]["marks"] = {"h1": [0.02, -0.05], "h2": [0.021, -0.1]}
    B["pieces"]["fr"]["marks"] = {"b1": [0.18, -0.05], "b2": [0.179, -0.1]}
    r = dg.rows(B, s3, {})[0]
    assert r["status"] == "PASS" and "OPEN at the front" in r["value"], r
    assert dg.rows(B, s3, {"waist": {"ease_mm": 80.0}})[0]["status"] == "FAIL"
    # no closure at all: an open chain round the body, said
    B, s3 = _tube({"fl": 0.24, "bk": 0.44, "fr": 0.24}, tp, closure=[])
    B["seams"] = B["seams"][:2]
    r = dg.rows(B, s3, {})[0]
    assert "OPEN: no closure or seam closes it" in r["value"], r


def test_s4_15_a_span_ratio_doesnt_crash_and_a_reversed_seam_carries_the_level():  # (t s4-15; C385)
    import numpy as np
    from hifipushie import draft_body_lengths as dbl, draft_girths as dg

    def rect(nm, w, h):
        return {"name": nm, "P": np.array([[0, 0], [w, 0], [w, -h], [0, -h]], float),
                "names": {"tl": 0, "tr": 1, "br": 2, "bl": 3}, "marks": {}, "wrap": {"to": "torso", "side": "front"}}
    B = {"pieces": {"a": rect("a", 0.2, 0.5), "b": rect("b", 0.2, 0.5)}, "seams": [["a:tr>br", "b:tl>bl"]],
         "stitches": [], "decl": {"seams": [{"a": "a:side", "b": "b:side"}]}}
    s1 = {"seams": [{"a": "a:side", "b": "b:side", "length": {"style": {"ratio": 0.9, "of": ["armpit", "hem"], "source": "x"}}}],
          "seam_lengths_checked": [[0, 300.0, 280.0]]}
    r = dbl.style_rows(B, s1, {"measurements": []})[0]  # (crashed: "unhashable type: 'list'")
    assert r["status"] == "FAIL" and "step 1 300 mm" in r["why"], r
    s1["seam_lengths_checked"] = []
    assert dbl.style_rows(B, s1, {"measurements": []})[0]["status"] == "INFO"  # (unresolved here: skipped, not guessed)
    # the level carried over a seam declared one edge up, one down still crosses the panel square
    side = dict(rect("side", 0.05, 0.6), wrap={"to": "torso", "side": "side"})
    back = dict(rect("back", 0.2, 0.6), wrap={"to": "torso", "side": "back"})
    B2 = {"pieces": {"front": rect("front", 0.2, 0.6), "side": side, "back": back},
          "seams": [["front:tr>br", "side:bl>tl"], ["side:tr>br", "back:tl>bl"], ["back:tr>br", "front:tl>bl"]],
          "edge_arcs": {"front": {"neck": "tl>tr"}, "back": {"neck": "tl>tr"}}}
    import numpy as np
    loop = np.array([[0.1 * np.cos(t), 0.1 * np.sin(t), 1.3] for t in np.linspace(0, 6.2, 40)])
    T = {"len": {"kind": "path", "path": np.array([[0.05, -0.1, 1.5], [0.05, -0.1, 0.9]])}}
    lines = dg.place(B2, loop, T, {"tapes": {"front": ["len"], "back": ["len"]}})[0]
    w = dg.width(B2["pieces"]["side"]["P"], *lines["side"])[0]
    assert abs(w - 0.05) < 2e-3, w  # (read across its length, 0.6 m, before)


def test_s4_16_a_darts_seams_dont_stop_the_length_rows():  # (t s4-16: "seams not one to one"; C386)
    import numpy as np
    from hifipushie import draft_body_lengths as dbl

    def rect(nm, w, h):
        return {"name": nm, "P": np.array([[0, 0], [w, 0], [w, -h], [0, -h]], float),
                "names": {"tl": 0, "tr": 1, "br": 2, "bl": 3}, "marks": {}, "wrap": {"to": "torso"}}
    B = {"pieces": {"a": rect("a", 0.2, 0.5), "b": rect("b", 0.2, 0.5)},
         "seams": [["a:tr>br", "b:tl>bl"], ["a:tl>tr", "a:bl>br"]], "stitches": [],
         "darts": [{"piece": "a", "legs": ["a:tl>tr", "a:bl>br"]}], "decl": {"seams": [{"a": "a:side", "b": "b:side"}]}}
    s1 = {"seams": [{"a": "a:side", "b": "b:side", "length": {"style": {"value_mm": 300, "source": "x"}}}]}
    r = dbl.style_rows(B, s1, {"measurements": []})[0]
    assert r["status"] == "FAIL" and "drafted 500 mm, step 1 300 mm" in r["why"], r


def test_s4_17_a_closures_holes_go_on_over_and_its_buttons_on_under():  # (t s4-16 / s4-17; C387)
    from hifipushie import garment_details_tool as gdt
    s1 = {"details": {"front_buttons": {"on": ["front.R"], "build": "full"},
                      "front_buttonholes": {"on": ["front.L"], "build": "full"}},
          "closures": {"front_closure": {"pieces": ["front.L", "front.R"], "details": ["front_buttons", "front_buttonholes"]}}}
    M = {"closures": [{"name": "front_closure", "kind": "buttons", "over": "front.L", "under": "front.R",
                       "pairs": [["hole1", "btn1"], ["hole2", "btn2"]]}]}
    mk = gdt.marks({"steps": {"1": {"output": s1}}}, M, {})
    assert mk["front_buttonholes"][0]["piece"] == "front.L" and mk["front_buttonholes"][0]["at"][0]["point"] == "hole1", mk
    assert mk["front_buttons"][0]["piece"] == "front.R" and mk["front_buttons"][0]["at"][1]["point"] == "btn2", mk


def test_planned_folds_row():
    """R2 (C392): every fold step 2 turns is declared on its piece by name; every declared roll has a planned turn."""
    from hifipushie import fold_bends as fb
    decl = {"folds": [{"name": "lapel_roll", "piece": "front", "line": ["a", "b"], "kind": "roll"},
                      {"name": "hem", "piece": "sleeve", "line": ["c", "d"], "kind": "press"}]}
    lapel = [{"id": f"lapel_roll.{s}", "on": f"front.{s}", "fold": "lapel_roll", "turn_deg": 170, "lies_on": f"front.{s}",
              "source": "x"} for s in "LR"]
    assert fb.draft_row(decl, {"bends": lapel})["status"] == "PASS"
    assert fb.draft_row(decl, None) is None  # (no step 2 read: no row)
    r = fb.draft_row(decl, {"bends": []})
    assert r["status"] == "FAIL" and "roll fold 'lapel_roll' on front: no step-2 bend turns it" in r["why"]
    r = fb.draft_row(decl, {"bends": lapel + [{"id": "c", "on": "collar", "fold": "collar_roll", "turn_deg": 175,
                                               "lies_on": "collar", "source": "x"}]})
    assert r["status"] == "FAIL" and "fold 'collar_roll' on collar (c); the draft declares none" in r["why"]
    assert fb.wear({"bends": lapel})["lapel_roll.L"] == {"on": "front.L", "fold": "lapel_roll", "turn_deg": 170,
                                                         "lies_on": "front.L"}


def test_seam_links_row_fails_what_the_build_refuses():
    """C395: step 4 FAILs a seam whose two sides differ past chain_core.SEAM_LINK_MM over one link (the hussar's
    approved draft was refused at step 5 for 4.9 mm at the underarm while step 4's truing row was INFO)."""
    import numpy as np
    from test_chain_loops import _pattern
    from hifipushie import draft_links
    pat, vid = _pattern({"a": (0.0, 0.2, 0.0, 0.05, 11, 3), "b": (0.0, 0.2, 0.05, 0.1, 11, 3)}, sew_rows=[("a", -1, "b", 0)])
    assert draft_links.row(pat.M)["status"] == "PASS"
    pat.M["uv"][vid("b", 10, 0), 0] += 0.006  # (one side's last link 6 mm longer: the corners don't meet)
    r = draft_links.row(pat.M)
    assert r["status"] == "FAIL" and "a / b: one side 20.00 mm, the other 26.00 mm" in r["why"] and r["back_to"] == "4"


def test_seams_crossed_row_names_two_points_sewn_into_one():
    """C403: step 4 runs the build's own crossed check: a seam sewn end to end the wrong way joins a piece's two ends."""
    from test_chain_loops import _pattern
    from hifipushie import draft_links
    pat, vid = _pattern({"a": (0.0, 0.2, 0.0, 0.05, 11, 3), "b": (0.0, 0.2, 0.05, 0.1, 11, 3),
                         "c": (0.0, 0.05, 0.1, 0.15, 3, 3)}, sew_rows=[("a", -1, "b", 0)])
    assert draft_links.crossed_row(pat.M)["status"] == "PASS"
    import numpy as np
    extra = [[vid("c", 0, 0), vid("a", 0, 0)], [vid("c", 0, 0), vid("a", 10, 0)]]  # (c's corner sewn to both ends of a)
    pat.M["sew"] = np.r_[pat.M["sew"], np.array(extra, np.int64)]
    r = draft_links.crossed_row(pat.M)
    assert r["status"] == "FAIL" and "sewn into one point" in r["why"] and r["back_to"] == "4"


# ---------------------------------------------------------------- P1: the step-3 tapes each piece was drafted on
def test_tapes_merge_into_piece_measurements_and_edge_tapes():
    from hifipushie import draft_tapes as dt, piece_start
    decl = {"pieces": {"panel": {"part": "test.panel", "pair": True}}, "edges": {"panel": {"side": "tr>br"}},
            "tapes": {"panel": {"side": "side_line"}, "panel.L": ["waist"]}}
    pm = piece_start.piece_measurements({}, decl, {"test.panel": {"measurements": []}}, ["panel.L", "panel.R"])
    assert pm == {"panel.L": ["side_line", "waist"], "panel.R": ["side_line"]}
    et = dt.edge_tapes(decl, ["panel.L", "panel.R"], {"panel.L": {"side": "tr>br"}})
    assert et["panel.L"]["side"] == {"tape": "side_line", "arc": "tr>br"} and et["panel.R"]["side"]["tape"] == "side_line"
    bad = "\n".join(dt.validate(dict(decl, tapes={"sleeve": ["waist"], "panel": {"hem": "waist"}, "panel.R": "waist"})))
    assert "tapes.sleeve: not a drafted piece" in bad and "tapes.panel.hem: no edge 'hem' declared on 'panel'" in bad
    assert "tapes.panel.R: 'waist': a list of step-3 tape names" in bad
    assert dt.validate(decl) == []


def _tape_row(decl):
    from hifipushie import draft_tapes as dt
    return dt.row({"pieces": {"panel.L": {}, "panel.R": {}}}, decl, STEP3)


def test_piece_tapes_row_fails_each_way_and_passes():
    r = _tape_row({k: v for k, v in DECL.items() if k != "tapes"})
    assert r["status"] == "FAIL" and "no step-3 tape with geometry: panel.L (no tapes), panel.R (no tapes)" in r["why"], r
    r = _tape_row(dict(DECL, tapes={"panel.L": ["waist"], "panel.R": ["neckline"]}))
    assert r["status"] == "FAIL" and r["back_to"] == "3" and "tape 'neckline' is not in step 3" in r["why"], r
    assert "measure that line in step 3" in r["why"]
    stiff = dict(DECL, stiff=["panel.L"])
    r = _tape_row(stiff)
    assert r["status"] == "FAIL" and "stiff panel.L:side is sewn to soft panel.R but names no tape" in r["why"], r
    assert "panel.R:" not in r["why"]  # (the soft side needs no edge tape)
    r = _tape_row(dict(stiff, tapes={"panel.L": {"side": "waist", "back": "waist"}, "panel.R": ["waist"]}))
    assert r["status"] == "PASS" and r["value"].startswith("2 of 2"), r
    assert _tape_row(DECL)["status"] == "PASS"
