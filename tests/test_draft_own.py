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
        "seams": [{"a": "panel.L:side", "b": "panel.R:side"}, {"a": "panel.L:back", "b": "panel.R:back"}]}


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
    gr.write(model, garment, "3", "done", output={"measurements": [{"name": "waist", "mm": 800.0, "kind": "girth"}]})


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
    assert set(gr.reads("tm", "g", "4")) == {"1", "3"}
    assert "reads" in gr.next_step(gr.load("tm", "g"))["uses"]
    sheet, txt = dot.run("tm", "g", RECT, DECL)
    assert "draft_pattern: PASS" in txt and Path(sheet).exists()
    assert "pieces (" in txt and "seams (" in txt and " ease " in txt and "SHAPES" in txt  # (C288: numbers in text)
    st = gr.load("tm", "g")["steps"]["4"]
    assert st["status"] == "done" and st["gate"]["verdict"] == "PASS" and st["look"]
    assert saved["tm"]["cloth"]["g"]["pattern"]["from"] == "own"
    assert "pattern_check (own draft, the flat gate): PASS" in dot.check_text("tm", "g")
    _, txt = dot.run("tm", "g", RECT, dict(DECL, seams=DECL["seams"][:1]))
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
    assert "brian.back: from brian.base" in txt and "seam runs: cbNeck >" in txt and "DEFAULT values" in txt
    look, one = pp.run("brian", part="brian.front", look_part=True)
    assert "points (x right, y down, mm): " in one and "cfNeck (" in one and "path seam: cfNeck >" in one
    assert Path(look).exists()
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
    assert r["shape_fall"]["value"].startswith("fall: outer edge"), r["shape_fall"]
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


def test_s4_13_the_pattern_round_the_body_at_each_girths_level():  # (t s4-13: a waist 5 cm under the plan passed; C383)
    import numpy as np
    from hifipushie import draft_girths as dg
    th = np.linspace(0, 2 * np.pi, 49)[:-1]
    zs = np.linspace(0.0, 1.6, 81)
    V = np.array([[0.14 * np.cos(t), 0.14 * np.sin(t), z] for z in zs for t in th])
    n = len(th)
    T = np.array([[i * n + j, i * n + (j + 1) % n, (i + 1) * n + j] for i in range(len(zs) - 1) for j in range(n)] +
                 [[i * n + (j + 1) % n, (i + 1) * n + (j + 1) % n, (i + 1) * n + j] for i in range(len(zs) - 1) for j in range(n)])
    body = {"V": V, "T": T, "at": {"hps.L": [0.06, 0.0, 1.5]}}

    def rect(nm, w, side):
        return {"name": nm, "P": np.array([[0, 0], [w, 0], [w, -0.7], [0, -0.7]], float),
                "names": {"tl": 0, "tr": 1, "br": 2, "bl": 3}, "marks": {}, "wrap": {"to": "torso", "side": side}}
    pcs = {"front.L": rect("front.L", 0.2, "front"), "front.R": rect("front.R", 0.2, "front"),
           "side.L": rect("side.L", 0.05, "side"), "side.R": rect("side.R", 0.05, "side"),
           "back.L": rect("back.L", 0.2, "back"), "back.R": rect("back.R", 0.2, "back"),
           "facing.L": rect("facing.L", 0.08, "front")}
    seams = [[f"front.{s}:tr>br", f"side.{s}:tl>bl"] for s in "LR"] + [[f"side.{s}:tr>br", f"back.{s}:tr>br"] for s in "LR"]
    seams += [["back.L:tl>bl", "back.R:tl>bl"], ["facing.L:tl>bl", "front.L:tl>bl"]]
    B = {"pieces": pcs, "seams": seams, "edge_arcs": {},
         "closures": [{"over": "front.L", "under": "front.R", "edge": {"over": "tl>bl", "under": "tl>bl"}, "pairs": []}]}
    loop = [[0.14 * np.cos(t), 0.14 * np.sin(t), 1.2] for t in th]
    s3 = {"measurements": [{"name": "waist", "mm": 850.0, "loop": loop}]}
    r = dg.rows(B, s3, {"waist": {"ease_mm": 80.0}}, body)[0]
    assert r["status"] == "FAIL" and "pattern 900 mm round" in r["value"] and "30 mm tight" in r["why"], r
    assert "facing.L" not in r["value"], r["value"]  # (a facing lying on the front isn't round the body)
    assert dg.rows(B, s3, {"waist": {"ease_mm": 40.0}}, body)[0]["status"] == "PASS"
    s3["measurements"][0]["mm"] = 950.0
    assert "can't close" in dg.rows(B, s3, {}, body)[0]["why"]
    # a side panel placed on the back, with no neck edge: its line comes over its seams, not from its own top (C384)
    s3["measurements"][0]["mm"] = 850.0
    for sd in "LR":
        pcs[f"side.{sd}"]["P"] = pcs[f"side.{sd}"]["P"] + [0, -0.3]  # (its top at the armpit, 300 mm below the hps)
        pcs[f"side.{sd}"]["wrap"]["side"] = "back"
    B["edge_arcs"] = {p: {"neck": "tl>tr"} for p in pcs if p.startswith(("front", "back"))}
    r = dg.rows(B, s3, {"waist": {"ease_mm": 40.0}}, body)[0]
    assert r["status"] == "PASS" and "pattern 900 mm round" in r["value"], r


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
    w = dg.level(B2, {"front": 0.2, "back": 0.2})[0]
    assert abs(w.get("side", 0) - 0.05) < 2e-3, w  # (read across its length, 0.6 m, before)


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
