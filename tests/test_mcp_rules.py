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


@pytest.fixture(scope="module")
def skirt_waive(home, tmp_path_factory):
    """The waivers for every FAIL / UNMEASURED row of the test skirt's gate, read once per module (cc.pattern_gate on
    the same model and pattern: two tests used to read it each), in a gate dir of its own."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("HIFIPUSHIE_PATTERN_GATE_DIR", str(tmp_path_factory.mktemp("waive_gate")))
        mp.delenv(cc.GATE_ENV_OVERRIDE, raising=False)
        return _waive_all(cc.pattern_gate(MODEL, "skirt", log=lambda *_: None))


def _texts(out):
    return [x for x in (out if isinstance(out, list) else [out]) if isinstance(x, str)]


def _images(out):
    return [x for x in (out if isinstance(out, list) else [out]) if not isinstance(x, str)]


def _waive_all(rec):
    return {r["id"]: "test: no reading for this item" for r in rec["rows"] if r["status"] in ("FAIL", "UNMEASURED")}


# ------------------------------------------------------------------ next steps are generated from the result


# ------------------------------------------------------------------ defaults


def test_instructions_and_guide_carry_the_order():
    ins = server.INSTRUCTIONS
    assert "pattern_check" in ins and "chain_garment" in ins and "review_view" in ins
    assert "built on the drape" not in ins and "finished by hand" not in ins  # (wrong since 2026-10-19)
    assert len(ins) < 3000
    g = server.guide("cloth")
    assert "pattern_check" in g and "chain_garment" in g
    assert server.guide("traps").startswith("# Traps")
    assert server.guide("tailoring")  # the principles, or where they are while on their branch
    for t in ("pattern_check", "chain_garment", "look_chain", "alter_pattern", "review_view", "judge_asset"):
        assert server.guide(t).startswith(f"### `{t}`"), t


# ------------------------------------------------------------------ the pattern gate through the MCP path

def test_pattern_check_fail_says_dont_simulate(gate):
    out = server.pattern_check(MODEL, "skirt", diag=False)
    (txt,) = _texts(out)
    assert len(_images(out)) == 1  # the flat pattern sheet
    assert "pattern gate t:skirt: FAIL" in txt and "UNMEASURED" in txt
    assert "refuses until it passes" in txt and 'pattern_check("t", "skirt")' in txt
    # FAIL / UNMEASURED rows are listed before the passing ones
    lines = [ln.split()[0] for ln in txt.splitlines() if ln.startswith("  ") and ln.split()[0].isupper()]
    assert lines.index("UNMEASURED") < lines.index("PASS")


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


def test_review_view_without_a_reference_runs_the_hang_checklist(tmp_path, home):
    b = _crop(tmp_path / "b.png", 2)
    out = server.review_view("whole garment, front", "", b, context="a game character's hoodie", dry=True,
                             out_dir=str(tmp_path / "rv"))
    (txt,) = _texts(out)
    assert "NO reference" in txt and "wings" in txt and "between the legs" in txt and "REFERENCE on the left" not in txt
    with pytest.raises(ValueError, match="checklist"):
        server.review_view("whole garment, front", b, b, checklist="hang", dry=True)


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


# ------------------------------------------------------------------ renders (under bin/capped)

needs_gpu = pytest.mark.skipif(not os.environ.get("HIFIPUSHIE_CAPPED"), reason="renders: run under bin/capped")

