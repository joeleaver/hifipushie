"""The design tools' contract is strict (trials lesson 4, codified C241): every key design_garment / alter_pattern
takes is checked; an unknown one is an error naming the valid ones with units, sign and default; an op a route
can't run is refused with the reason; an option that replaces a default says so; a failed call saves nothing.

Light: uv run pytest tests/test_design_contract.py (the transactional tests reuse test_mcp_rules' small model under
/mnt/data/hifipushie/mcp_rules/ws and skip without it; the workspace-model tests skip models not on this machine)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from hifipushie import cloth, design_schema as ds, garment_design as gd, pattern, pattern_draft as pdm, server, store

WS = Path("/mnt/data/hifipushie/mcp_rules/ws")
WORKSPACE = Path("/home/joe/dev/hifipushie/workspace")
ASSETS = "/home/joe/dev/hifipushie/workspace/_templates"
HOODIE = {"kind": "hoodie", "block": "knit"}


def _err(fn, *a, **k) -> str:
    with pytest.raises(ValueError) as e:
        fn(*a, **k)
    return str(e.value)


# ------------------------------------------------------------------ draft ops


def test_sleeve_ease_is_refused_and_names_biceps_ease():
    """hoodie t6: sleeve {"ease": 0.18} was swallowed by **kwargs ("biceps width 346 mm (ease 5%)" unchanged)."""
    msg = _err(ds.check_ops, [{"op": "sleeve", "ease": 0.18}], "design")
    assert 'ops[0] (sleeve): unknown parameter "ease"' in msg
    assert "biceps_ease (fraction of the biceps girth" in msg and "bodice 0.15, knit 0.05" in msg and "cap_ease" in msg
    ds.check_ops([{"op": "sleeve", "biceps_ease": 0.32, "length": "short", "source": "t"}], "design")


def test_missing_required_parameter_is_named_at_design_time():
    """hoodie t6: reshape with "move" passed design_garment and failed at look_pattern ("missing ... 'by'")."""
    msg = _err(ds.check_ops, [{"op": "reshape", "piece": "front", "point": "shoulder", "move": [0, 0.01]}])
    assert 'unknown parameter "move"' in msg and "y UP" in msg
    msg = _err(ds.check_ops, [{"op": "reshape", "piece": "front", "point": "shoulder"}])
    assert 'missing "by"' in msg and "REQUIRED" in msg


def test_unknown_op_lists_ops_and_an_alteration_name_says_where_it_goes():
    msg = _err(ds.check_ops, [{"op": "rounded_corner", "piece": "front"}])
    assert "unknown draft op 'rounded_corner'" in msg and "round_corner" in msg and "sleeve" in msg
    msg = _err(ds.check_ops, [{"op": "move", "piece": "front"}])
    assert "ALTERATION op" in msg and "alter_pattern" in msg


def test_every_registered_op_has_a_closed_parameter_set():
    """An op whose kwargs the scan can't follow is "open" (accepts anything): the silent drop this contract ends.
    New ops (pattern_draft.OPS, any module) are read from their code; one that escapes needs a KWARGS_FROM entry."""
    T = ds.op_table()
    assert set(pdm.OPS) <= set(T)
    opened = {k: t["escapes"] for k, t in T.items() if t["open"]}
    assert not opened, opened


def test_a_new_op_is_covered_without_edits():
    def op_contract_probe(D, piece: str, depth: float = 0.02, **o):
        if o.get("curve", True):
            return float(o.get("tilt", 0.0))
    pdm.OPS["contract_probe"] = op_contract_probe
    try:
        t = ds.op_table()["contract_probe"]["params"]
        assert {"piece", "depth", "curve", "tilt"} <= set(t) and t["piece"]["required"]
        ds.check_ops([{"op": "contract_probe", "piece": "front", "tilt": 0.1}])
        assert 'unknown parameter "tlit"' in _err(ds.check_ops, [{"op": "contract_probe", "piece": "f", "tlit": 1}])
    finally:
        del pdm.OPS["contract_probe"]


def test_draft_apply_refuses_before_any_op_runs():
    D = {"log": []}
    with pytest.raises(pdm.DraftError) as e:
        pdm.apply(D, [{"op": "sleeve", "ease": 0.2}])
    assert "biceps_ease" in str(e.value) and D == {"log": []}


# ------------------------------------------------------------------ block options, routes, sheet keys


def test_block_options_unknown_names_the_block_options_with_units():
    msg = _err(ds.check_block_options, "knit", {"chest": 0.2}, "design")
    assert 'unknown for the knit block: "chest"' in msg and "chest_ease (fraction of the chest girth" in msg
    assert "length_bonus (m ADDED to the bodice length" in msg
    ds.check_block_options("knit", {"chest_ease": 0.2, "armhole_depth": 0.18, "length": 0.58}, "design")
    ds.check_block_options("trouser", {"waist_drop": 0.07, "dart_taper": 0.6}, "design")


def test_ops_on_a_freesewing_draft_are_refused_with_the_reason():
    """shirt t7: round_corner on a Simon draft saved with no error and did nothing."""
    g = {"design": {"kind": "shirt", "from": "simon", "ops": [{"op": "round_corner", "piece": "front",
                                                                 "corner": "hem"}]}}
    msg = _err(ds.check_garment, g, "cloth 'shirt'")
    assert "never runs them" in msg and "alter_pattern" in msg and '"ops": null' in msg
    gd.validate(g["design"], "cloth 'shirt'")  # (every other save still takes a model saved before the contract)
    msg = _err(ds.check_garment, {"design": {"kind": "shirt", "from": "simon", "block_options": {"x": 1}}}, "g")
    assert "block options run only on a design drafted from a block" in msg


def test_detail_params_are_checked():
    msg = _err(gd.validate, {"kind": "shirt", "from": "simon", "details": {"cuff": {"type": "barrel", "opts": {}}}})
    assert 'details.cuff: unknown key "opts"' in msg and '"options"' in msg


def test_design_sheet_keys_name_the_valid_ones():
    msg = _err(gd.validate, {"kind": "tee", "colour": "#fff"})
    assert "colour" in msg and "kind" in msg and "auto_true" in msg


def test_auto_true_and_truing_corners_are_design_and_garment_keys():
    """shirt t7: the gate's fix text named "auto_true" and the garment refused it; truing_corners: true then crashed
    alter_pattern ("'bool' object is not iterable")."""
    sheet = dict(HOODIE, auto_true=True, truing_corners=["collar:standTip"])
    gd.validate(sheet)
    comp = gd.compile_sheet(sheet)
    assert comp["auto_true"] is True and comp["truing_corners"] == ["collar:standTip"]
    assert "auto_true" in cloth.GARMENT_KEYS
    ds.check_garment({"design": dict(HOODIE), "auto_true": False}, "g")
    msg = _err(ds.check_garment, {"design": dict(HOODIE), "truing_corners": True}, "g")
    assert "list of seam-end labels" in msg and '"auto_true": true' in msg
    assert "true / false" in _err(gd.validate, dict(HOODIE, auto_true="yes"))


# ------------------------------------------------------------------ FreeSewing options


def test_freesewing_option_table_and_unknown_option():
    T = ds.fs_options("simon")
    assert T["lengthBonus"]["type"] == "pct" and T["lengthBonus"]["default"] == pytest.approx(0.25)
    msg = _err(ds.check_fs_options, "simon", {"lengthBonnus": 0.05}, "design")
    assert 'no option "lengthBonnus"' in msg and "lengthBonus (fraction, default 0.25 = FreeSewing pct 25" in msg
    assert "REPLACES the default" in msg
    assert "one of straight, baseball, slashed" in _err(ds.check_fs_options, "simon", {"hemStyle": "curved"})


def test_an_option_that_replaces_a_default_says_so():
    """shirt t7: lengthBonus 0.05 REPLACED the default 0.25 and two probes cut 17 cm."""
    notes = ds.design_notes({"design": {"kind": "shirt", "from": "simon", "pattern": {"options": {"lengthBonus": 0.05}}}})
    assert any(n.startswith("lengthBonus 0.05 replaces FreeSewing's default 0.25 (pct 25): total 0.05") for n in notes), notes
    # the pattern word "length" is Simon's lengthBonus too
    notes = ds.design_notes({"design": {"kind": "shirt", "from": "simon", "pattern": {"length": 0.3}}})
    assert any(n.startswith("lengthBonus 0.3 replaces") for n in notes), notes


# ------------------------------------------------------------------ alteration ops


def test_alteration_errors_name_the_op_and_its_keys():
    """shirt t7: move -> KeyError 'piece' / 'by'; match -> "not enough values to unpack (expected 2, got 1)" x3."""
    msg = _err(pattern.check_alter, [{"op": "move", "point": "hem", "by": [0, -0.01]}])
    assert 'alter[0] (move): missing "piece"' in msg and "y UP" in msg
    msg = _err(pattern.check_alter, [{"op": "match", "piece": "stand", "edge": "stand", "to": ["front:a>b"],
                                       "line": "x"}])
    assert 'edge is one string "piece:a>b"' in msg
    msg = _err(pattern.check_alter, [{"op": "match", "piece": "stand", "edge": "stand:a>b", "to": "front:a>b",
                                       "line": "x"}])
    assert "to is a list" in msg
    msg = _err(pattern.check_alter, [{"op": "trim", "piece": "cuff", "edge": "a>b", "lenght": 0.2}])
    assert 'unknown key "lenght"' in msg and "length (m from a" in msg
    msg = _err(pattern.check_alter, [{"op": "round_corner", "piece": "front", "corner": "hem"}])
    assert "unknown alteration op 'round_corner'" in msg and "is a DRAFT op" in msg and "slash_spread takes" in msg


def test_alteration_apply_checks_all_ops_before_changing_anything():
    pc = pattern.from_spec("sq", {"rect": [0.4, 0.4]})  # (corners sw se ne nw; mid-edge s e n w; centred)
    pcs = {"sq": pc}
    with pytest.raises(pattern.AlterError):
        pattern.apply(pcs, [{"op": "move", "piece": "sq", "point": "n", "by": [0, 0.01]},
                            {"op": "move", "piece": "sq", "point": "n"}])
    with pytest.raises(pattern.AlterError) as e:
        pattern.apply(pcs, [{"op": "move", "piece": "sq", "point": "nope", "by": [0, 0.01]}])
    assert "alter[0] (move)" in str(e.value) and "no point 'nope'" in str(e.value)
    out = pattern.apply(pcs, [{"op": "move", "piece": "sq", "point": "n", "by": [0, 0.01]}])
    assert out["sq"]["P"][pc["names"]["n"]][1] == pytest.approx(0.21)  # y UP: +dy raises the point


# ------------------------------------------------------------------ the knowledge base and workspace models


def test_every_kind_default_sheet_passes_the_contract():
    """A false refusal is worse than a silent drop: every kind's defaults (their draft ops, block options, detail
    ops) pass, route included."""
    for kind in (k for k in gd.kb()["kinds"] if not k.startswith("_")):
        ds.check_sheet({"kind": kind}, f"kind {kind}", route=True)


def test_design_table_alterations_pass():
    for d, t in cloth.designs().items():
        if d.startswith("_") or not isinstance(t, dict):
            continue
        pattern.check_alter(t.get("alter") or [], f"{d} alter")
        for nm, op in (t.get("fit_alterations") or {}).items():
            pattern.check_alter([dict(op, amount=0.01)], f"{d} {nm}")


@pytest.mark.parametrize("model,design", [("trial_tshirt_t5", True), ("trial_hoodie_t6", True),
                                          ("trial_shirt_t7", False), ("gc_garrett", True), ("wf_simon", True)])
def test_workspace_models_still_validate(model, design):
    if not (WORKSPACE / model / "spec.json").exists():
        pytest.skip(f"no {model} here")
    old = store.HOME
    store.HOME = WORKSPACE
    try:
        sp = store.load(model)
    finally:
        store.HOME = old
    for gn, g in (sp.get("cloth") or {}).items():
        if isinstance(g, dict) and not g.get("frozen"):
            ds.check_garment(g, f"{model}:{gn}", design=design)
            if g.get("design"):
                gd.validate(g["design"], f"{model}:{gn}")


# ------------------------------------------------------------------ a failed call saves nothing


@pytest.fixture
def home(monkeypatch):
    if not (WS / "t" / "spec.json").exists():
        pytest.skip("test_mcp_rules' model not built here")
    monkeypatch.setattr(store, "HOME", WS)
    os.environ.setdefault("HIFIPUSHIE_ASSETS", ASSETS)
    store.save("t_contract", store.load("t"), "copy for test_design_contract")
    return WS


def test_design_garment_failing_saves_nothing(home, monkeypatch):
    v0 = len(store.history("t_contract"))
    with pytest.raises(ValueError):
        server.design_garment("t_contract", "skirt", design={"ops": [{"op": "sleeve", "ease": 0.1}]})
    assert len(store.history("t_contract")) == v0
    from hifipushie import cloth_workflow

    def boom(*a, **k):
        raise RuntimeError("stage crashed")
    monkeypatch.setattr(cloth_workflow, "run", boom)
    with pytest.raises(RuntimeError):
        server.design_garment("t_contract", "skirt", design={"notes": "a change"})
    assert len(store.history("t_contract")) == v0
    assert "notes" not in store.load("t_contract")["cloth"]["skirt"]["design"]


def test_alter_pattern_failing_after_the_draft_saves_nothing(home, monkeypatch):
    """shirt t7: alter_pattern crashed AFTER saving (the truing read) and the next call applied its ops twice."""
    v0 = len(store.history("t_contract"))
    n0 = len(store.load("t_contract")["cloth"]["skirt"].get("alter") or [])
    with pytest.raises(ValueError) as e:
        server.alter_pattern("t_contract", "skirt", [{"op": "move", "piece": "front", "point": "sideHem"}])
    assert 'missing "by"' in str(e.value)
    from hifipushie import cloth_check as cc

    def boom(*a, **k):
        raise TypeError("'bool' object is not iterable")
    monkeypatch.setattr(cc, "junctions", boom)
    with pytest.raises(TypeError):
        server.alter_pattern("t_contract", "skirt", [{"op": "move", "piece": "front", "point": "sideHem",
                                                      "by": [0.0, -0.005], "source": "test"}])
    assert len(store.history("t_contract")) == v0
    assert len(store.load("t_contract")["cloth"]["skirt"].get("alter") or []) == n0
