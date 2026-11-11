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


# ------------------------------------------------------------------ review: one view per call

def _crop(path, seed, size=(300, 400)):
    rng = np.random.default_rng(seed)
    PILImage.fromarray(rng.integers(60, 200, (*size[::-1], 3), dtype=np.uint8)).save(path)
    return str(path)


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

