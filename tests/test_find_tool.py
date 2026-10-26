"""find_tool + call_tool: a small native core reaches every tool in any host (C233: clients don't refresh their tool
list mid-session, so enable_toolset's tools were never seen).
uv run python tests/test_find_tool.py"""
import asyncio

from mcp.server.mcpserver import Image
from mcp.server.mcpserver.exceptions import ToolError

from hifipushie import server

GARMENT_TOOLS = set(server.TOOL_GROUPS["cloth"]["tools"])


def _ranked(query: str, limit: int = 5) -> list[str]:
    return [line.split(". ", 1)[1].split(" [")[0] for line in server.find_tool(query, limit).splitlines()
            if line[:1].isdigit()]


def _call(name: str, args: dict):
    return asyncio.run(server.mcp.call_tool("call_tool", {"name": name, "args": args}))


def _error(name: str, args: dict) -> str:
    try:
        _call(name, args)
    except ToolError as e:
        return str(e)
    raise AssertionError("expected a tool error")


def test_garment_query_ranks_a_garment_tool():
    top = _ranked("dress a character in a garment", 3)
    assert GARMENT_TOOLS & set(top), top
    top = _ranked("dress a character in a hoodie", 3)
    assert GARMENT_TOOLS & set(top), top
    # the workflow leads: design before the sim; no other domain's stray word match ("dressed brow")
    full = _ranked("dress a character in a hoodie", 10)
    assert full.index("design_garment") < full.index("dress"), full
    assert set(full[:5]) <= GARMENT_TOOLS, full
    assert server.find_tool("dress a character in a hoodie").startswith("Clothes come from the pattern: design_garment")
    assert _ranked("groom hair")[0] == "groom_hair"


def test_find_tool_gives_params_and_an_example():
    text = server.find_tool("fit garment on the dress form", 1)
    assert "fit_garment" in text and "params: name: str, garment: str" in text, text
    assert 'call_tool(name="fit_garment", args={"name": "...", "garment": "..."})' in text, text
    assert server.find_tool("put a model", 3)  # core tools are found too (shown as native calls)


def test_empty_query_lists_every_tool():
    text = server.find_tool("")
    for t in server._TOOLS:
        assert t in text, t
    for g in server.TOOL_GROUPS:
        assert f"\n{g} (" in text, g


def test_call_tool_runs_a_non_core_tool():
    assert "heavy_queue" not in server.CORE
    res = _call("heavy_queue", {})
    assert not res.is_error and "heavy jobs" in res.content[0].text, res


def test_call_tool_returns_images_like_a_native_call():
    import io
    from PIL import Image as PILImage
    buf = io.BytesIO()
    PILImage.new("RGB", (4, 4), (200, 10, 10)).save(buf, format="PNG")

    def _img_probe(label: str = "ok"):
        """A test tool returning a look-style [Image, str]."""
        return [Image(data=buf.getvalue(), format="png"), label]

    server._TOOLS["_img_probe"] = (None, _img_probe)  # (not registered natively: reached only by call_tool)
    server._img_probe = _img_probe
    try:
        res = _call("_img_probe", {"label": "probe"})
        kinds = [c.type for c in res.content]
        assert kinds == ["image", "text"], kinds
        assert res.content[0].mime_type == "image/png" and res.content[1].text == "probe"
    finally:
        del server._TOOLS["_img_probe"], server._img_probe
        server._CALL_TOOLS.pop("_img_probe", None)


def test_bad_args_name_the_expected_parameters():
    e = _error("design_garment", {"nme": "x"})
    assert "unknown argument(s) nme" in e and "missing required name, garment" in e, e
    assert "design_garment expects: name: str, garment: str" in e, e
    e = _error("fit_garment", {"name": "x", "garment": "y", "size": "big"})
    assert "bad argument(s): size" in e and "fit_garment expects:" in e, e
    e = _error("fit_garmnt", {})
    assert "no tool 'fit_garmnt'" in e and "fit_garment" in e and "find_tool" in e, e


def test_every_tool_reachable_through_call_tool():
    for name in server._TOOLS:
        if name == "call_tool":
            continue
        tool = server._tool_obj(name)  # the SDK Tool call_tool validates and runs through
        want = {p[0] for p in server._params(name)}
        assert set(tool.fn_metadata.arg_model.model_fields) == want, name
        assert server._param_text(name) and server._example(name), name


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
    print("ok")
