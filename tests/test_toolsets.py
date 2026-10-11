"""Toolsets and trimmed tool descriptions (the tool definitions were ~36k tokens on every turn).
uv run python tests/test_toolsets.py"""
import asyncio
import inspect
import json
import os
import sys

from hifipushie import server

# the 75 tools the server had before toolsets (2026-10-09): none may be lost
BEFORE = """guide list_models get_model kit_reference put_model edit_model look measure clearance set_reference compare fit
set_plan check rig style_check history revert sync pull export export_asset groom_hair look_hair export_hair
hair_reference dress look_cloth skin human measure_human fit_human nudge_human human_reference likeness fit_likeness
project_reference texture_from_reference character_read likeness_points reference_brief check_references
skin_reference look_skin garment_reference garment_from_reference check_garment_reference garment_reference_brief
design_garment look_pattern check_garment set_terrain check_terrain look_terrain export_terrain terrain_history
grow_plant edit_plant look_plant look_plants grow_stand look_stand export_stand plant_form get_plant plant_reference
export_plant wind_plant sync_plant plant_history heavy_status heavy_queue make_clutter look_clutter
clutter_kit""".split()
# added since: the artist block-in (2026-10-10)
ADDED = {"block_in_start", "block_in_look", "block_in_step", "lid_read", "block_in_expression", "gnm_controls"}


def _tokens(tools) -> int:
    return sum(len(json.dumps(t.model_dump(mode="json", exclude_none=True, by_alias=True))) // 4 for t in tools)


def test_every_tool_in_one_toolset():
    sets = [t for s in server.TOOLSETS.values() for t in s["tools"]]
    assert len(sets) == len(set(sets)), "a tool in two toolsets"
    assert set(sets) == set(server._TOOLS) - {"call_tool"}, set(sets) ^ (set(server._TOOLS) - {"call_tool"})
    assert set(BEFORE) <= set(sets), set(BEFORE) - set(sets)
    assert len(BEFORE) == 75 and set(sets) - set(BEFORE) == {"enable_toolset"} | ADDED
    for s in server.TOOLSETS.values():
        for a in s.get("also", []):
            assert a in server.TOOLSETS


def test_default_registers_core():
    # this process imported the server with HIFIPUSHIE_TOOLSETS unset: only the core is on
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    if "HIFIPUSHIE_TOOLSETS" not in os.environ:
        assert names == set(server.TOOLSETS["core"]["tools"]), names


def test_all_over_stdio():
    """HIFIPUSHIE_TOOLSETS=all: today's 75 tools + enable_toolset, from the first tools/list."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def go():
        params = StdioServerParameters(command=sys.executable, args=["-m", "hifipushie.server"],
                                       env={**os.environ, "HIFIPUSHIE_TOOLSETS": "all"})
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                init = await s.initialize()
                tools = (await s.list_tools()).tools
                return tools, init.instructions
    tools, instr = asyncio.run(go())
    names = {t.name for t in tools}
    assert names == set(BEFORE) | {"enable_toolset"} | ADDED, names ^ (set(BEFORE) | {"enable_toolset"} | ADDED)
    print(f"all: {len(tools)} tools ~{_tokens(tools)} tokens + instructions ~{len(instr) // 4} "
          f"(before toolsets: 75 tools ~36064 + 2800)")


def test_toolset_names():
    assert server._toolset_names("core") == ["core"]
    assert server._toolset_names("hair,terrain") == ["core", "hair", "scene", "terrain"]
    assert server._toolset_names("all") == list(server.TOOLSETS)
    try:
        server._toolset_names("nope")
        raise AssertionError("an unknown toolset passed")
    except ValueError as e:
        assert "toolsets:" in str(e)


def test_short_descriptions_point_at_the_guide():
    """Every description is short; whatever it leaves out is in its guide section (verbatim from the old text), and
    every parameter is named in the description or the section."""
    for name in server._TOOLS:
        doc = inspect.cleandoc(getattr(server, name).__doc__)
        assert len(doc) < 700, (name, len(doc))
        sec = server._tool_section(name)
        assert sec.startswith(f"### `{name}`"), name
        if len(sec) > len(doc) + 200:
            assert f'guide(topic="{name}")' in doc, name
        sig = inspect.signature(getattr(server, name))
        for p in sig.parameters:
            if p != "ctx":
                assert p in doc or p in sec, (name, p)
    # a domain topic still returns the whole guide; a tool name returns just its section
    assert server.guide("hair").startswith("#") and "### `groom_hair`" in server.guide("hair")
    assert server.guide("look").startswith("### `look`") and "paint_layer" in server.guide("look")
    assert "Tool reference" in server.guide("tools")


def test_compact_schema():
    s = {"properties": {"title": {"title": "Title", "type": "string"},
                        "v": {"anyOf": [{"items": {"type": "number"}, "type": "array"}, {"type": "null"}],
                              "default": None, "title": "V"},
                        "c": {"anyOf": [{"type": "object", "additionalProperties": True}, {"type": "string"},
                                        {"type": "null"}], "default": None}},
         "required": ["title"], "title": "fArguments", "type": "object"}
    c = server._compact_schema(s)
    assert c == {"properties": {"title": {"type": "string"}, "v": {"items": {"type": "number"}, "type": "array"},
                                "c": {"anyOf": [{"type": "object"}, {"type": "string"}]}},
                 "required": ["title"], "type": "object"}, c


async def _client(env: dict):
    """Start the real server over stdio with `env`; return (tool names before, after enable_toolset("hair"), the
    notifications seen, the listChanged capability, tokens before / after)."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    seen = []

    async def on_message(m):
        seen.append(repr(m))

    params = StdioServerParameters(command=sys.executable, args=["-m", "hifipushie.server"],
                                   env={**os.environ, **env})
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w, message_handler=on_message) as s:
            init = await s.initialize()
            t0 = (await s.list_tools()).tools
            res = await s.call_tool("enable_toolset", {"name": "hair"})
            for _ in range(50):
                if any("ToolListChanged" in x or "tools/list_changed" in x for x in seen):
                    break
                await asyncio.sleep(0.05)
            t1 = (await s.list_tools()).tools
            return ({t.name for t in t0}, {t.name for t in t1}, seen, init.capabilities.tools.list_changed,
                    _tokens(t0), _tokens(t1), res, init.instructions)


def test_enable_toolset_over_stdio():
    """HIFIPUSHIE_TOOLSETS=core: 12 tools; enable_toolset("hair") adds hair + scene and sends list_changed."""
    t0, t1, seen, cap, k0, k1, res, instr = asyncio.run(_client({"HIFIPUSHIE_TOOLSETS": "core"}))
    assert cap is True, "tools.listChanged not advertised"
    assert t0 == set(server.TOOLSETS["core"]["tools"]), t0
    want = t0 | set(server.TOOLSETS["hair"]["tools"]) | set(server.TOOLSETS["scene"]["tools"])
    assert t1 == want, t1 ^ want
    assert any("ToolListChanged" in x or "tools/list_changed" in x for x in seen), seen
    assert not res.is_error, res
    print(f"core: {len(t0)} tools ~{k0} tokens + instructions ~{len(instr) // 4}; after hair: {len(t1)} ~{k1}")


def test_call_tool_fallback():
    """HIFIPUSHIE_CALL_TOOL=1 adds call_tool, which runs a tool that isn't enabled."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def go():
        params = StdioServerParameters(command=sys.executable, args=["-m", "hifipushie.server"],
                                       env={**os.environ, "HIFIPUSHIE_TOOLSETS": "core", "HIFIPUSHIE_CALL_TOOL": "1"})
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                names = {t.name for t in (await s.list_tools()).tools}
                res = await s.call_tool("call_tool", {"name": "heavy_queue", "args": {}})
                return names, res
    names, res = asyncio.run(go())
    assert "call_tool" in names and "heavy_queue" not in names, names
    assert not res.is_error, res


if __name__ == "__main__":
    test_every_tool_in_one_toolset()
    test_default_registers_core()
    test_all_over_stdio()
    test_toolset_names()
    test_short_descriptions_point_at_the_guide()
    test_compact_schema()
    test_enable_toolset_over_stdio()
    test_call_tool_fallback()
    print("ok")
