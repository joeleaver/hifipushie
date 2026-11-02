"""The head route held by the tools: find_tool lands on the block-in, the fit tools refuse a block-in model, a hand step
needs the solve, expressions are parameter mixes, every human / likeness reply ends in next:.
uv run pytest tests/test_head_route.py"""
import inspect
import json

import pytest

from hifipushie import blockin as bi, faceshapes, head_route, humans, server, store
from hifipushie.spec import empty_spec


def _ranked(query: str) -> list[str]:
    return [ln.split(". ", 1)[1].split(" [")[0] for ln in server.find_tool(query, 5).splitlines() if ln[:1].isdigit()]


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    return tmp_path


def _model(home, name, blockin=None, head=None):
    (home / name).mkdir()
    (home / name / "spec.json").write_text(json.dumps({"base": {"body": {"source": "human"}, "head": head or {}}}))
    if blockin is not None:
        (home / name / "human_refs.json").write_text(json.dumps({"views": [], "cameras": [], "blockin": blockin}))


@pytest.mark.parametrize("q", ["a person's head from reference photos", "build a face from a photo", "head from pictures",
                               "model a real person from pictures", "match a face to a photograph"])
def test_find_tool_lands_on_the_block_in(q):
    assert _ranked(q)[0] == "block_in_start"


def test_find_tool_keeps_other_domains_and_finds_the_pose():
    assert _ranked("pose an expression on a finished head")[0] == "set_expression"
    assert _ranked("skin from a photo of a face")[0] != "block_in_start"
    for q in ("hair from reference photos", "a tree from a photo", "clothes from a photo"):
        assert _ranked(q)[0] != "block_in_start", q


def test_human_default_is_one_mesh_and_old_routes_are_gone():
    p = inspect.signature(server.human).parameters
    assert p["source"].default == "human"
    p = inspect.signature(server.block_in_start).parameters
    assert "attach" not in p and "gnm_base" not in p
    with pytest.raises(ValueError, match="retired"):
        server.lid_read("x", match="pose")


@pytest.mark.parametrize("call", [lambda: server.fit_human("h", {"nose_width": "+1"}),
                                  lambda: server.nudge_human("h", "chin", move=[0, 0, 0.001]),
                                  lambda: server.fit_likeness("h", "nose"),
                                  lambda: server.human_reference("h", [], fit=True)])
def test_fit_tools_refuse_a_block_in_model(home, call):
    _model(home, "h", blockin={"root": "h"})
    with pytest.raises(ValueError, match=r'block_in_step\("h".*mm:'):
        call()


def test_hand_step_needs_the_solve(home):
    _model(home, "h", blockin={"root": "h"})
    with pytest.raises(ValueError, match=r'block_in_solve\("h"\)'):
        head_route.require_solved("h")
    head_route.require_solved("h", hand_first=True)
    _model(home, "s", blockin={"root": "s", "last_dc": [0.1]})
    head_route.require_solved("s")
    _model(home, "p", blockin={"root": "s", "last_dc": [0.1]}, head={"posed": {"from": "s", "mix": {}}})
    with pytest.raises(ValueError, match="step from s"):
        head_route.require_solved("p", hand_first=True)


def test_over_one_sd_reads_mm_against_its_measure():
    from hifipushie import gnm_mm
    k, sd = next(iter(gnm_mm.sd().items()))
    assert not bi.over_sd(f"mm:{k}", 0.9 * sd) and bi.over_sd(f"mm:{k}", 1.1 * sd)
    assert not bi.over_sd("chin_height", 0.9) and bi.over_sd("chin_height", 1.1)


def test_presets_are_generic_and_mixes_are_checked():
    assert not any("_tess" in k or "_garrett" in k for k in faceshapes.EXPRESSION_PRESETS)
    for p in faceshapes.EXPRESSION_PRESETS:
        assert faceshapes.expression(p)
    with pytest.raises(ValueError, match="no preset"):
        faceshapes.expression("grin")
    with pytest.raises(ValueError, match="not ARKit"):
        faceshapes.expression({"smile": 1.0})
    with pytest.raises(ValueError, match=r"outside \[0, 1\]"):
        faceshapes.expression({"jawOpen": 1.5})


@pytest.fixture
def man(home):
    sp = {**empty_spec(), **humans.spec(age=30, sex=1.0, source="human", skin=False, outfit_kind="none")}
    sp["base"]["head"]["expression"] = {"lower_face_region_000": 0.25}   # (a lips step's closing)
    (home / "man").mkdir()
    (home / "man" / "spec.json").write_text(json.dumps(sp))
    return sp


def test_pose_is_parameters_on_a_new_model(man):
    r = head_route.pose("man", "blink")
    assert r["out"] == "man_blink" and "man_blink" in head_route.pose_text("man", r)
    hd = store.load("man_blink")["base"]["head"]
    assert any(k.startswith(("left_eye_region", "right_eye_region")) for k in hd["expression"])
    assert hd["posed"]["from"] == "man"
    assert store.load("man")["base"]["head"]["expression"] == {"lower_face_region_000": 0.25}   # the neutral untouched
    with pytest.raises(ValueError, match="pose from man"):
        head_route.pose("man_blink", "smile")
    with pytest.raises(ValueError, match="exists"):
        head_route.pose("man", "blink")
    for bad in ({"cheekPuff": 0.5}, {"eyeLookUpLeft": 0.5}):
        with pytest.raises(ValueError, match="no GNM expression parameters"):
            head_route.pose("man", bad, out="x")


@pytest.mark.parametrize("shape", ["mouthSmileLeft", "cheekSquintLeft", "jawOpen"])
def test_offset_built_shapes_have_parameters(man, shape):
    assert faceshapes.face_of(man).shape_coeffs(shape)


def test_every_human_and_likeness_tool_ends_in_next():
    skin = {"skin", "look_skin", "skin_reference", "skin_from_reference", "skin_project"}   # (the skin thread's)
    tools = set(server.TOOL_GROUPS["human"]["tools"]) | set(server.TOOL_GROUPS["likeness"]["tools"])
    missing = tools - skin - set(head_route.NEXT) - {"set_expression"}     # (set_expression writes its own)
    assert not missing, missing


def test_next_follows_the_result(home):
    def block_in_solve(name):
        ...
    a = head_route.with_next(block_in_solve, ("h",), {}, ["img", "joint solve: |dc| 3.10, |c| 4\nh2 (round 2, from h): x"])
    assert a[1].endswith('next: block_in_solve("h2") again (|dc| 3.10; until it is under 2).')
    a = head_route.with_next(block_in_solve, (), {"name": "h"}, "|dc| 1.10, |c| 4\nh2 (round 2, from h): x")
    assert 'next: face_ruler("h2")' in a
    assert head_route.with_next(block_in_solve, ("h",), {}, "done\nnext: mine") == "done\nnext: mine"
