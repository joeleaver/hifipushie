"""Reproductions of the tooling cards' incidents (Overboard project hifipushie, tag "tooling").

Run: uv run python tests/test_tooling.py   (or pytest, if installed). Uses a throwaway HIFIPUSHIE_HOME.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile

os.environ["HIFIPUSHIE_HOME"] = tempfile.mkdtemp(prefix="hp_tooling_")

from hifipushie import server, store  # noqa: E402
from hifipushie.spec import SpecError  # noqa: E402


def small_spec() -> dict:
    return {
        "joints": {"pelvis": {"pos": [0, 0, 0.5], "r": 0.1}, "chest": {"pos": [0, 0, 0.8], "r": 0.12},
                   "head": {"pos": [0, 0, 1.0], "r": 0.1},
                   "shoulder.L": {"pos": [0.15, 0, 0.8], "r": 0.05}, "hand.L": {"pos": [0.4, 0, 0.6], "r": 0.04}},
        "bones": {"spine": {"a": "pelvis", "b": "chest"}, "neck": {"a": "chest", "b": "head"},
                  "arm.L": {"a": "shoulder.L", "b": "hand.L"}},
        "blobs": {"skull": {"at": "head", "size": [0.1, 0.11, 0.12]}},
    }


def _raises(fn, *a, **k) -> str:
    try:
        fn(*a, **k)
    except Exception as e:
        return str(e)
    raise AssertionError("expected an error")


def _call(tool: str, args: dict) -> str:
    """Call a tool the way the MCP client does; return the error text the caller sees."""
    from mcp.server.mcpserver.exceptions import ToolError
    try:
        asyncio.run(server.mcp.call_tool(tool, args))
    except ToolError as e:
        return str(e)
    raise AssertionError("expected a tool error")


# Card "MCP tool errors arrive empty: surface the SpecError text"
def test_tool_errors_carry_the_message():
    server.put_model("errs", small_spec())
    text = _call("edit_model", {"name": "errs", "ops": [
        {"op": "set", "kind": "joints", "name": "tail", "value": {"pos": [0, 0.2, 0.5], "r": 0.03}},
        {"op": "set", "kind": "blobs", "name": "tooth.L", "value": {"at": "face_mouth_upper_0", "size": [0.01] * 3}},
        {"op": "set", "kind": "joints", "name": "tail2", "value": {"pos": [0, 0.3, 0.5], "r": 0.03}}]})
    assert "face_mouth_upper_0" in text, text
    assert "op 1 (set blobs tooth.L)" in text, text
    # a crash that isn't a ValueError still says what and where
    text = _call("measure", {"name": "no_such_model", "along": "spine"})
    assert "no model" in text, text


# Card "edit_model can't touch top-level keys; put_model silently drops the plan"
def test_top_level_keys_and_plan_kept():
    server.put_model("keys", small_spec())
    server.set_plan("keys", {"views": {"front": {"shapes": {"torso": {"ellipse": [0, 0.75, 0.2, 0.35]}}}}})
    out = server.put_model("keys", small_spec())
    assert "kept the stored plan" in out and "plan" in store.load("keys")
    server.put_model("keys", {**small_spec(), "plan": None})
    assert "plan" not in store.load("keys")
    server.edit_model("keys", [{"op": "set", "kind": "anatomy", "name": "shoulder.L", "value": {"back": 0}},
                               {"op": "set_key", "key": "story", "value": {"age": "new"}}])
    s = store.load("keys")
    assert s["anatomy"] == {"shoulder.L": {"back": 0}}
    assert s["story"]["age"] == "new"
    server.edit_model("keys", [{"op": "set_key", "key": "story", "value": None}])
    assert "story" not in store.load("keys")
    msg = _raises(store.apply_ops, store.load("keys"), [{"op": "set", "kind": "blend", "name": "x", "value": {}}])
    assert "set_key" in msg and "op 0" in msg, msg
    assert isinstance(_exc(store.apply_ops, {}, [{"op": "nope"}]), SpecError)


def _exc(fn, *a):
    try:
        fn(*a)
    except Exception as e:
        return e
    return None


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn) and (len(sys.argv) < 2 or any(a in name for a in sys.argv[1:])):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, e)
    sys.exit(1 if fails else 0)
