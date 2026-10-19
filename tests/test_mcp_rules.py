"""The clothing and review rules carried by the MCP tools themselves (docs/notes/mcp_audit.md, codified M1-M8): the
tools refuse what the gates forbid, default to the diagnostic views, and end their text with the next step generated
from the result. Through the server's functions, as an MCP client would call them.

Light (no renders): /mnt/data/hifipushie/bin/slot uv run pytest tests/test_mcp_rules.py
Renders (the default diag views): HIFIPUSHIE_CAPPED is set by bin/capped, which also takes the GPU lock:
  /mnt/data/hifipushie/bin/capped uv run pytest tests/test_mcp_rules.py -k render
The first run builds a small test model (a MakeHuman base + an A-line skirt, ~90 s) under
/mnt/data/hifipushie/mcp_rules/ws, kept for later runs."""
from __future__ import annotations

import inspect
import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PILImage

from hifipushie import cloth, cloth_check as cc, next_steps, server, store

WS = Path("/mnt/data/hifipushie/mcp_rules/ws")
ASSETS = "/home/joe/dev/hifipushie/workspace/_templates"
MODEL = "t"
SKIRT = {"kind": "skirt", "from": "skirt_block", "fit": "a_line"}


@pytest.fixture(scope="module")
def home():
    old = store.HOME
    WS.mkdir(parents=True, exist_ok=True)
    store.HOME = WS
    os.environ.setdefault("HIFIPUSHIE_ASSETS", ASSETS)
    try:
        if not (WS / MODEL).exists() or "skirt" not in (store.load(MODEL).get("cloth") or {}):
            server.human(MODEL)
            server.design_garment(MODEL, "skirt", design=SKIRT)
        yield WS
    finally:
        store.HOME = old


@pytest.fixture
def gate(tmp_path, monkeypatch, home):
    monkeypatch.setenv("HIFIPUSHIE_PATTERN_GATE_DIR", str(tmp_path / "gate"))
    monkeypatch.delenv(cc.GATE_ENV_OVERRIDE, raising=False)
    return tmp_path


def _texts(out):
    return [x for x in (out if isinstance(out, list) else [out]) if isinstance(x, str)]


def _images(out):
    return [x for x in (out if isinstance(out, list) else [out]) if not isinstance(x, str)]


def _waive_all(rec):
    return {r["id"]: "test: no reading for this item" for r in rec["rows"] if r["status"] in ("FAIL", "UNMEASURED")}


# ------------------------------------------------------------------ next steps are generated from the result

def test_next_steps_follow_the_result():
    fail = {"status": "FAIL", "rows": [{"id": "seams", "status": "FAIL"}, {"id": "rise", "status": "UNMEASURED"},
                                       {"id": "drape", "status": "SIM"}]}
    t = next_steps.after_pattern_check(fail, "m", "jacket")
    assert "DON'T simulate" in t and "seams" in t and "rise" in t and "drape" not in t
    ok = dict(fail, status="PASS_WAIVED", waived={"seams": "x", "rise": "y"})
    t = next_steps.after_pattern_check(ok, "m", "jacket")
    assert "fit_garment" in t and "DON'T" not in t
    # fit: a red strain or a pierce names the pattern fix; a clean one says judge one view at a time
    assert "fix on the pattern" in next_steps.after_fit("m", "j", 30.0, 0, True)
    assert "pierce" in next_steps.after_fit("m", "j", 3.0, 12, True)
    clean = next_steps.after_fit("m", "j", 3.0, None, False)
    assert "ONE view per review_view" in clean and "not validated" in clean
    assert "no reference" in next_steps.after_look("garment", False)
    assert "BESIDE its reference" in next_steps.after_look("garment", True)
    assert "did NOT run" in next_steps.after_review(None, False)
    bad = [{"a": "front:a>b", "b": "back:a>b", "ok": False}]
    assert "match" in next_steps.after_alter(bad, "m", "j") and "pattern_check" in next_steps.after_alter([], "m", "j")


# ------------------------------------------------------------------ defaults

def test_garment_looks_default_to_diag():
    for fn in (server.pattern_check, server.fit_garment, server.look_cloth):
        assert inspect.signature(fn).parameters["diag"].default is None, fn.__name__
    rows = server._diag_rows(None)
    assert rows == [["panels", "seams", "turned"], ["strain", "layers"]]
    assert server._diag_rows(False) == [] and server._diag_rows(["strain"]) == [["strain"]]


def test_instructions_and_guide_carry_the_order():
    ins = server.INSTRUCTIONS
    assert "pattern_check" in ins and "fit_garment" in ins and "review_view" in ins
    assert "built on the drape" not in ins and "finished by hand" not in ins  # (wrong since 2026-10-19)
    assert len(ins) < 3000
    g = server.guide("cloth")
    assert "pattern_check" in g and "fit_garment" in g and "66-74" in g
    assert server.guide("traps").startswith("# Traps")
    assert server.guide("tailoring")  # the principles, or where they are while on their branch
    for t in ("pattern_check", "fit_garment", "alter_pattern", "review_view", "judge_asset", "game_garment"):
        assert server.guide(t).startswith(f"### `{t}`"), t


# ------------------------------------------------------------------ the pattern gate through the MCP path

def test_pattern_check_fail_says_dont_simulate(gate):
    out = server.pattern_check(MODEL, "skirt", diag=False)
    (txt,) = _texts(out)
    assert len(_images(out)) == 1  # the flat pattern sheet
    assert "pattern gate t:skirt: FAIL" in txt and "UNMEASURED" in txt
    assert "DON'T simulate" in txt and 'pattern_check("t", "skirt")' in txt
    # FAIL / UNMEASURED rows are listed before the passing ones
    lines = [ln.split()[0] for ln in txt.splitlines() if ln.startswith("  ") and ln.split()[0].isupper()]
    assert lines.index("UNMEASURED") < lines.index("PASS")


def test_dress_refuses_without_a_pass_and_names_the_tool(gate):
    before = dict(cloth._JOBS)
    txt = server.dress(MODEL, "skirt")
    assert "NOT simulated" in txt and 'call_tool("pattern_check", {"name": "t", "garment": "skirt"})' in txt, txt
    assert cloth._JOBS == before  # no sim was started
    txt = server.dress(MODEL, "skirt", force=True)  # force skips the stage checks, never the pattern gate
    assert "NOT simulated" in txt and cloth._JOBS == before


def test_fit_refuses_until_the_pattern_passes(gate):
    txt = server.fit_garment(MODEL, "skirt")
    assert isinstance(txt, str) and "not fitted" in txt and "pattern_check" in txt
    rec = cc.pattern_gate(MODEL, "skirt", log=lambda *_: None)
    out = server.pattern_check(MODEL, "skirt", waive=_waive_all(rec), diag=False)
    (t,) = _texts(out)
    assert "PASS_WAIVED" in t and "fit_garment" in t and "DON'T" not in t
    assert cc.gate_status(MODEL, "skirt")["passed"]


def test_alter_pattern_drafts_before_saving_and_needs_a_new_gate(gate):
    store.save("t_alter", store.load(MODEL), "copy for test_alter_pattern")
    v0 = len(store.history("t_alter"))
    with pytest.raises(Exception):
        server.alter_pattern("t_alter", "skirt", [{"op": "no_such_op", "piece": "front"}])
    assert len(store.history("t_alter")) == v0  # a bad op saved nothing
    rec = cc.pattern_gate("t_alter", "skirt", log=lambda *_: None)
    cc.write_record(dict(rec, status="PASS"))
    assert cc.gate_status("t_alter", "skirt")["passed"]
    out = server.alter_pattern("t_alter", "skirt", [{"op": "move", "piece": "front", "point": "sideHem",
                                                     "by": [0.01, 0.0], "source": "test"}])
    (txt,) = _texts(out)
    assert "walked seams" in txt and "truing:" in txt and "next:" in txt
    assert not cc.gate_status("t_alter", "skirt")["passed"]  # the record was for the old pattern


# ------------------------------------------------------------------ review: one view per call

def _crop(path, seed, size=(300, 400)):
    rng = np.random.default_rng(seed)
    PILImage.fromarray(rng.integers(60, 200, (*size[::-1], 3), dtype=np.uint8)).save(path)
    return str(path)


def test_review_view_refuses_sheets_and_claims(tmp_path, home):
    a, b = _crop(tmp_path / "a.png", 1), _crop(tmp_path / "b.png", 2)
    g = np.random.default_rng(3).integers(60, 200, (820, 1200, 3), dtype=np.uint8)  # 3 x 2 views, white gutters
    g[:, 398:402] = 255
    g[:, 798:802] = 255
    g[408:412] = 255
    PILImage.fromarray(g).save(tmp_path / "sheet.png")
    with pytest.raises(Exception, match="refused"):
        server.review_view("collar, front", a, str(tmp_path / "sheet.png"), dry=True)
    with pytest.raises(Exception, match="claim|number"):
        server.review_view("collar, front", a, b, context="a jacket, strain fixed to 4 %", dry=True)
    out = server.review_view("collar, front", a, b, context="a game character's jacket", dry=True,
                             out_dir=str(tmp_path / "rv"))
    (txt,) = _texts(out)
    assert len(_images(out)) == 1 and "independent" in txt and "collar, front" in txt
    assert "region" in inspect.signature(server.review_view).parameters  # one region per call, by signature


# ------------------------------------------------------------------ game garments: the LOD pierce gate

def _sheet(name, z):
    from test_garment_game import _drape
    d = _drape(11)
    d["name"], d["g"] = name, {"roughness": 0.8}
    d["V"] = d["V"].copy()
    d["V"][:, 2] = z(d["V"][:, 0])
    return d


def _game_inputs(cross: bool):
    """A shirt sheet (0.4 m, two panels sewn) under a jacket sheet over its middle (x 0.1-0.3), 1 cm above it, or
    tilted through it near the jacket's free edge (x 0.113, inside the cull's margin: where real crossings survive)."""
    sh = _sheet("shirt", lambda x: 0 * x)
    jk = _sheet("jacket", (lambda x: 0.04 * (x - 0.026)) if cross else (lambda x: 0 * x + 0.01))
    jk["V"][:, 0] = jk["V"][:, 0] * 0.5 + 0.1
    X, Y = np.meshgrid(np.linspace(-0.1, 0.5, 13), np.linspace(-0.1, 0.3, 9))
    body = np.stack([X.ravel(), Y.ravel(), np.full(X.size, -0.1)], 1)
    return {"shirt": sh, "jacket": jk}, {"shirt": ["jacket"], "jacket": []}, body, []


def test_game_garment_refuses_a_crossing_lod_and_names_the_fix(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_game_drapes", lambda name, spec, garments: _game_inputs(True))
    monkeypatch.setattr(store, "load", lambda name: {})
    txt = server.game_garment("m", lods=[0.03, 0.06], out_dir=str(tmp_path / "gg"))
    assert "pierce shirt through jacket: 14 faces" in txt and "LOD1" in txt
    assert "NOT baked, no GLB written" in txt and "finer edge at that LOD" in txt and "gap_rings=2" in txt
    assert "by hand" in txt and 'game_garment("m") again' in txt and "judge_asset" not in txt
    assert not (tmp_path / "gg").exists()  # refused: nothing written, nothing baked


def test_game_garment_clean_writes_lods_and_says_judge(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_game_drapes", lambda name, spec, garments: _game_inputs(False))
    monkeypatch.setattr(store, "load", lambda name: {})
    txt = server.game_garment("m", lods=[0.03, 0.06], bake=False, out_dir=str(tmp_path / "gg"))
    assert "pierce shirt through jacket: 0 faces" in txt and "faces culled under its covers" in txt
    assert "NOT baked" not in txt and "bake=True) writes the GLBs" in txt and "rest pose only" in txt
    for k in (0, 1):
        for g in ("shirt", "jacket"):
            assert (tmp_path / "gg" / f"LOD{k}" / f"low_{g}.npz").exists()
    # baked: judge each GLB, then one crop per review_view call
    L = [{"lod": 0, "h": 0.03, "pierce": [{"under": "shirt", "cover": "jacket", "faces": 0}], "cracks": {"shirt": 0}}]
    t = next_steps.after_game_garment(L, "m", ["/x/LOD0/game_shirt.glb"], True)
    assert 'judge_asset("/x/LOD0/game_shirt.glb")' in t and "ONE per review_view" in t and "rest pose" not in t
    L[0]["cracks"] = {"shirt": 3}
    assert "crack" in next_steps.after_game_garment(L, "m", None, True)


def test_game_garment_needs_a_drape(home):
    with pytest.raises(Exception, match="no drape for skirt"):
        server._game_drapes(MODEL, store.load(MODEL), ["skirt"])
    with pytest.raises(ValueError, match="no garment"):
        server._game_drapes(MODEL, store.load(MODEL), ["cape"])


# ------------------------------------------------------------------ renders (under bin/capped)

needs_gpu = pytest.mark.skipif(not os.environ.get("HIFIPUSHIE_CAPPED"), reason="renders: run under bin/capped")


@needs_gpu
def test_render_pattern_check_and_fit_default_to_diag(gate):
    out = server.pattern_check(MODEL, "skirt", views=["front", "back"], size=320)
    assert len(_images(out)) == 2  # flat sheet + diag sheet (two rows)
    rec = cc.pattern_gate(MODEL, "skirt", log=lambda *_: None)
    server.pattern_check(MODEL, "skirt", waive=_waive_all(rec), diag=False)
    out = server.fit_garment(MODEL, "skirt", views=["front", "back"], size=320)
    (txt,) = _texts(out)
    assert len(_images(out)) == 3  # clay + diag + own colour under the game light (C107)
    assert "strain vs the flat pattern: p99" in txt and "next:" in txt
    assert list((store.HOME / "_looks" / MODEL).glob("fit_skirt_diag_r0_*.png"))  # single views for review_view


def test_one_form_switch_for_gate_and_tools():
    """The gate, the MCP tools and next_steps read ONE dress-form switch: cloth_check.form_validated() (the manual
    override or pattern_form.form_validated(): flag + a record whose rows all pass). fit_garment reads on_form's
    under garment ("A", "mesh"; its name is the garment key "over"); alter_pattern reads the junctions rows' fields."""
    fit = inspect.getsource(server.fit_garment)
    assert "cc.form_validated()" in fit and "pattern_form.form_validated" not in fit
    assert 'u["A"]' in fit and 'u["mesh"]' in fit and '.get("over")' in fit
    alt = inspect.getsource(server.alter_pattern)
    assert "cc.junctions(" in alt and "truing_corners" in alt
    assert all(k in alt for k in ("['at']", "['turn_deg']", "['seam']", '["ok"]'))
    for mod in (server, next_steps):
        src = inspect.getsource(mod)
        assert "FORM_VALIDATED" not in src and "pattern_form.form_validated" not in src
    gate = inspect.getsource(cc.pattern_gate)
    assert "form_validated()" in gate and "FORM_VALIDATED" not in gate
