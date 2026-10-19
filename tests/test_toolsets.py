"""The native core (+ find_tool / call_tool for the rest), tool groups and trimmed tool descriptions (the tool
definitions were ~36k tokens on every turn; C233: clients don't refresh tool lists, so no toolsets).
uv run python tests/test_toolsets.py"""
import asyncio
import inspect
import json
import os
import sys

from hifipushie import server

# the 75 tools the server had before toolsets (2026-10-09): none may be lost (all reachable by call_tool)
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
ADDED = {"block_in_start", "block_in_look", "block_in_step", "block_in_solve", "lid_read", "block_in_expression", "gnm_controls", "lip_read",
         "brow_read", "eye_ruler", "face_ruler", "tie_hair", "skin_from_reference", "hair_from_reference", "skin_project",
         "pattern_check", "fit_garment", "alter_pattern", "review_view", "judge_asset",  # (the garment gates as tools, 2026-10-19)
         "release_garment", "arrange_garment", "style_garment",
         "game_garment"}  # (worn open 2026-10-20; pull / turn / smooth, C142 / C143)


def _tokens(tools) -> int:
    return sum(len(json.dumps(t.model_dump(mode="json", exclude_none=True, by_alias=True))) // 4 for t in tools)


def test_every_tool_in_one_group():
    groups = [t for s in server.TOOL_GROUPS.values() for t in s["tools"]]
    assert len(groups) == len(set(groups)), "a tool in two groups"
    assert set(groups) == set(server._TOOLS), set(groups) ^ set(server._TOOLS)
    assert set(BEFORE) <= set(groups), set(BEFORE) - set(groups)
    assert len(BEFORE) == 75 and set(groups) - set(BEFORE) == {"find_tool", "call_tool"} | ADDED
    assert not hasattr(server, "enable_toolset") and not hasattr(server, "TOOLSETS")


def test_default_registers_core():
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert names == set(server.CORE), names
    assert {"find_tool", "call_tool"} <= names and len(names) <= 15, names


def test_core_over_stdio():
    """Over stdio: the first tools/list is the core; call_tool runs a non-core tool; the instructions say how."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def go():
        params = StdioServerParameters(command=sys.executable, args=["-m", "hifipushie.server"], env=dict(os.environ))
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                init = await s.initialize()
                tools = (await s.list_tools()).tools
                res = await s.call_tool("call_tool", {"name": "heavy_queue", "args": {}})
                return tools, init.instructions, res
    tools, instr, res = asyncio.run(go())
    assert {t.name for t in tools} == set(server.CORE), {t.name for t in tools}
    assert not res.is_error and "heavy jobs" in res.content[0].text, res
    assert "find_tool" in instr and "call_tool" in instr and "enable_toolset" not in instr
    print(f"core: {len(tools)} tools ~{_tokens(tools)} tokens + instructions ~{len(instr) // 4} "
          f"(before toolsets: 75 tools ~36064 + 2800)")


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
    assert server.guide("hair").startswith("#") and 'guide(topic=...)' in server.guide("hair")
    assert "### `groom_hair`" in server.guide("hair_tools")  # domain cores are rules first; tool sections in <domain>_tools
    assert server.guide("look").startswith("### `look`") and "paint_layer" in server.guide("look")
    assert "Tool reference" in server.guide("tools")
    # every tool's section is reachable through guide(): "tool:<name>" always, the bare name unless a topic shadows it
    for name in server._TOOLS:
        assert server.guide(f"tool:{name}").startswith(f"### `{name}`"), name
        if name.lower() not in server.GUIDE_TOPICS:
            assert server.guide(name).startswith(f"### `{name}`"), name
    assert server.guide("skin").startswith("#") and server.guide("tool:skin").startswith("### `skin`")


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


if __name__ == "__main__":
    test_every_tool_in_one_group()
    test_default_registers_core()
    test_core_over_stdio()
    test_short_descriptions_point_at_the_guide()
    test_compact_schema()
    print("ok")
