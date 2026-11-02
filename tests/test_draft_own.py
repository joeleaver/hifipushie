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
