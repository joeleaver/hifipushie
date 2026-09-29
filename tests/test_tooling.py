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


# Card "Warn when a centre-named paint layer's near names only .L elements (paints one side)"
def test_one_sided_paint_warns():
    spec = {**small_spec(), "paint": {
        "paws": {"color": [0.9, 0.8, 0.7], "near": ["arm.L"]},           # the gopher's mistake
        "paws2.L": {"color": [0.9, 0.8, 0.7], "near": ["arm.L"]},        # mirrored layer: fine
        "belly": {"color": [0.9, 0.8, 0.7], "near": ["arm.L", "spine"]}}}  # mixed: fine
    out = server.put_model("sides", spec)
    assert "WARNING: paint 'paws'" in out and "'paws.L'" in out, out
    assert "paws2" not in out.split("WARNING")[-1].split("\n")[0] and out.count("WARNING") == 1, out


# Card "Paint/stroke paths: "at" misses when the point is further than the part's size from its surface"
def basket_spec(path) -> dict:
    """The disc basket's hole-number plate: a 150 mm plate 0.34 m in front of the pole, a path addressed on the
    pole's axis (x, 0, z) with the default view direction."""
    return {
        "joints": {"foot": {"pos": [0, 0, 0], "r": 0.02}, "top": {"pos": [0, 0, 1.5], "r": 0.02}},
        "bones": {"pole": {"a": "foot", "b": "top"}},
        "blobs": {"plate": {"at": [0, -0.338, 1.3], "shape": "box", "size": [0.075, 0.075, 0.004],
                            "rot": [90, 0, 0], "part": "plate"}},
        "parts": {"plate": {"color": [0.9, 0.9, 0.2]}},
        "paint": {"number": {"part": "plate", "color": [0.1, 0.1, 0.1], "width": 0.006, "path": path}},
    }


def test_path_at_any_point_on_the_line():
    out = server.put_model("basket", basket_spec([{"at": [-0.022, 0, 1.316]}, {"at": [0.02, 0, 1.28]}]))
    assert out.startswith("saved basket"), out
    # a line that never meets the plate fails at save, naming the part and its bounds
    text = _call("put_model", {"name": "basket", "spec": basket_spec([{"at": [0.5, 0, 1.316]}, {"at": [0.02, 0, 1.28]}])})
    assert "never meets part 'plate'" in text and "y -0.3" in text, text


# Card "check/fit: choose which parts the silhouette counts (props, held items)"
def _iou(text: str, view: str) -> float:
    import re
    return float(re.search(r"IoU[ =:]*([0-9.]+)", text.split(f"[{view}]")[1]).group(1))


def test_check_counts_chosen_parts():
    spec = small_spec()
    spec["joints"]["disk"] = {"pos": [0, -0.25, 0.65], "r": 0.02}
    spec["blobs"]["disk"] = {"at": "disk", "shape": "box", "size": [0.1, 0.04, 0.1], "part": "disk"}
    spec["parts"] = {"disk": {"color": [0.2, 0.2, 0.2]}}
    server.put_model("holder", spec)
    plan = {"views": {"side": {"shapes": {"torso": {"capsule": [0, 0.5, 0, 0.8], "r": 0.11},
                                          "head": {"ellipse": [0, 1.0, 0.11, 0.12]}}}}}
    server.set_plan("holder", plan)
    all_parts = server.check("holder", resolution=96)[1]
    body = server.check("holder", resolution=96, only_parts=["body"])[1]
    assert "silhouettes count parts: body" in body, body
    assert _iou(body, "side") > _iou(all_parts, "side") + 0.02, (all_parts, body)
    same = server.check("holder", resolution=96, hide_parts=["disk"])[1]
    assert _iou(same, "side") == _iou(body, "side")
    server.set_plan("holder", {**plan, "parts": ["body"]})
    assert _iou(server.check("holder", resolution=96)[1], "side") == _iou(body, "side")
    out = server.fit("holder", resolution=64, iterations=2)[-1]
    assert "silhouettes count parts: body" in out and "disk" not in out.split("changes:")[1], out
    assert "no part 'hat'" in _raises(server.check, "holder", only_parts=["hat"])


# Card "Let blobs/bones hang on kit-generated joints (teeth, claws, accessories)"
def test_elements_on_kit_joints():
    import json
    from pathlib import Path
    from hifipushie.spec import compile_prims, expand_mirror
    spec = json.loads((Path(__file__).parents[1] / "examples" / "gopher.json").read_text())
    spec.pop("plan", None)
    spec["blobs"]["tooth"] = {"at": "face_nose_tip", "offset": [0, -0.004, -0.02], "size": [0.006, 0.003, 0.009]}
    spec["bones"]["claw.L"] = {"a": "hand_f1_3.L", "b": "claw_tip.L", "r_a": 0.004, "r_b": 0.001}
    spec["blobs"]["claw_nub.L"] = {"at": {"bone": "claw.L", "t": 0.5}, "size": [0.002] * 3}  # hangs on the claw
    spec["joints"]["claw_tip.L"] = {"pos": [0.2, -0.05, 0.3], "r": 0.002}
    out = server.put_model("gopher_kitjoints", spec)
    assert out.startswith("saved"), out
    s = expand_mirror(spec)
    assert {"tooth", "claw.R", "claw_nub.R"} <= set(s["bones"]) | set(s["blobs"])
    names = {p.name for p in compile_prims(spec)}
    assert "tooth" in names and "claw.L" in names and "claw.R" in names, sorted(names)[:20]
    # the tooth follows the face kit: moving the head moves it
    moved = json.loads(json.dumps(spec))
    moved["joints"]["head"]["pos"][2] += 0.01
    z0 = next(p for p in compile_prims(spec) if p.name == "tooth").lo[2]
    z1 = next(p for p in compile_prims(moved) if p.name == "tooth").lo[2]
    assert abs(z1 - z0 - 0.01) < 0.004, (z0, z1)
    # a real typo still fails, by name
    spec["blobs"]["tooth"]["at"] = "face_nose_tipp"
    assert "face_nose_tipp" in _raises(server.put_model, "gopher_kitjoints", spec)


# Card "Durable home for pipeline assets (templates, patched builds)"
def test_assets_fetch_by_checksum():
    """fetch/verify on a fake pack served from file:// URLs (no network): a missing pack says how to fetch it;
    fetch places files only when their sha256 matches, repairs a corrupt one, extracts a zip member."""
    import hashlib
    import json
    import zipfile
    from pathlib import Path
    from hifipushie import assets
    src = Path(tempfile.mkdtemp(prefix="hp_src_"))
    (src / "a.txt").write_text("alpha\n")
    with zipfile.ZipFile(src / "b.zip", "w") as z:
        z.writestr("bundle-v1/b.bin", b"beta" * 100)
    sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731
    man = {"demo": {"needed_by": "the test", "source": "here", "licence": "CC0", "files": [
        {"path": "a.txt", "url": (src / "a.txt").as_uri(), "sha256": sha(b"alpha\n")},
        {"path": "deep/b.bin", "url": (src / "b.zip").as_uri(), "member": "bundle-v1/b.bin", "sha256": sha(b"beta" * 100)}]}}
    mp = src / "assets.json"
    mp.write_text(json.dumps(man))
    old, old_env = assets.MANIFEST, os.environ.get("HIFIPUSHIE_ASSETS")
    assets.MANIFEST = mp
    os.environ["HIFIPUSHIE_ASSETS"] = str(src / "assets")
    try:
        msg = _raises(assets.pack, "demo")
        assert "hifipushie-assets fetch demo" in msg, msg
        assets.fetch(["demo"], log=lambda *_: None)
        assert assets.verify(["demo"]) == {"demo": []}
        assert (assets.pack("demo") / "deep" / "b.bin").read_bytes() == b"beta" * 100
        assert "Licence: CC0" in (src / "assets" / "demo" / "SOURCE.txt").read_text()
        (src / "assets" / "demo" / "a.txt").write_text("corrupt")
        assert assets.verify(["demo"])["demo"] == ["checksum mismatch a.txt"]
        assets.fetch(["demo"], log=lambda *_: None)
        assert assets.verify(["demo"]) == {"demo": []}
        (src / "a.txt").write_text("changed upstream\n")  # the source moved: refuse, leave nothing half-written
        (src / "assets" / "demo" / "a.txt").unlink()
        assert "sha256" in _raises(assets.fetch, ["demo"], log=lambda *_: None)
        assert sorted(p.name for p in (src / "assets" / "demo").iterdir()) == ["SOURCE.txt", "deep"]
    finally:
        assets.MANIFEST = old
        if old_env is None:
            os.environ.pop("HIFIPUSHIE_ASSETS", None)
        else:
            os.environ["HIFIPUSHIE_ASSETS"] = old_env
    # the real manifest: every file has a URL and a checksum, packs say what needs them
    for name, p in assets.manifest().items():
        assert p["needed_by"] and p["licence"] and all(f["url"].startswith("https://") and len(f["sha256"]) == 64
                                                      for f in p["files"]), name


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
