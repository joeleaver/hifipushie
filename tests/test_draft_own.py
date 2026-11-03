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


def _ref(points):
    from hifipushie import draft_stand as dst
    plan = {"read": {"views": [{"view": "front", "image": "x.png"}]},
            "style": {"traces": [{"id": "top", "what": "collar_top", "view": 0, "points": points}], "body_marks": _MARKS}}
    return dst.reference(plan, _AT)


_bowl = lambda x: ((x - 0.2) / 0.2) ** 2  # 0 at the middle (CB), 1 at the strip's two ends (the front ends)
HUGS = (lambda x: 0.03 * _bowl(x), lambda x: 0.03 * _bowl(x) + 0.05)  # neck edge rising 30 mm, 50 mm tall all round
AWAY = (lambda x: -0.01 * _bowl(x), lambda x: -0.01 * _bowl(x) + 0.05 + 0.07 * _bowl(x))  # falling 10 mm, 120 mm at the ends


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


def test_shape_a_level_top_over_a_dropping_neckline_wants_taller_fronts_not_a_rise():
    r = _rows(_B(_stand(HUGS, lean_in=True)), ref=_ref(LEVEL))["shape_stand"]
    assert r["status"] == "INFO (would FAIL)" and "level" in r["value"], r
    assert "flatter / down" in r["why"] and "taller at its front ends" in r["why"] and r["back_to"] == "4", r["why"]
    ok = _rows(_B(_stand(AWAY)), ref=_ref(LEVEL))["shape_stand"]
    assert ok["status"] == "INFO (would PASS)", ok


def test_shape_a_top_that_follows_the_neckline_wants_the_hugging_rise():
    ok = _rows(_B(_stand(HUGS, lean_in=True)), ref=_ref(FOLLOWS))["shape_stand"]
    assert ok["status"] == "INFO (would PASS)" and "hugging" in ok["value"], ok
    r = _rows(_B(_stand(AWAY)), ref=_ref(FOLLOWS))["shape_stand"]
    assert r["status"] == "INFO (would FAIL)" and "up (the ends towards the free edge)" in r["why"] and "lower at its front ends" in r["why"], r


def test_shape_no_trace_reports_the_stand_and_assumes_no_style():
    for s in (_stand(HUGS), _stand(AWAY), _strip("collar", lambda x: 0.0, lambda x: 0.048)):
        r = _rows(_B(s))
        assert r["shape_stand"]["status"] == "INFO" and "no style assumed" in r["shape_stand"]["value"], r["shape_stand"]
    assert "rising (hugs)" in _rows(_B(_stand(HUGS)))["shape_stand"]["value"]
    assert "near straight (upright)" in _rows(_B(_stand(AWAY)))["shape_stand"]["value"]
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
