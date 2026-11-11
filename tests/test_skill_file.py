"""The Claude Code skill (.claude/skills/hifipushie/SKILL.md) names only tools and guide topics that exist.

Why (C400): it went on telling agents to call enable_toolset after that tool was removed (C233), so an agent that
followed the skill started with a call that fails. The skill is the first thing an agent reads; nothing checked it.
uv run python tests/test_skill_file.py"""
import re
from pathlib import Path

from hifipushie import server
from hifipushie import mcp_app, tools_find

SKILL = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "hifipushie" / "SKILL.md"


def test_skill_names_only_real_tools_and_topics():
    text = SKILL.read_text()
    assert "enable_toolset" not in text and "toolset" not in text.lower()
    # a backticked snake_case name, and anything written as a call, is a tool
    named = set(re.findall(r"`([a-z]+_[a-z_]+)", text)) | set(re.findall(r"`([a-z_]+)\(", text))
    assert named and not named - set(mcp_app._TOOLS), named - set(mcp_app._TOOLS)
    topics = set(re.findall(r'guide\(topic="([a-z_]+)"\)', text)) | set(re.findall(r'`"([a-z_]+)"`', text))
    assert topics and not {t for t in topics if t not in tools_find.GUIDE_TOPICS and t not in mcp_app._TOOLS}, topics


def test_skill_lists_the_native_core_and_the_clothes_path():
    text = SKILL.read_text()
    for t in server.CORE:
        assert f"`{t}`" in text, t
    assert {t.name for t in __import__("asyncio").run(server.mcp.list_tools())} == set(server.CORE)
    steps = [s for s in server.TOOL_GROUPS["cloth"]["steps"] if f"`{s}`" in text]
    assert steps[:4] == ["garment_plan", "body_tape", "draft_pattern", "chain_garment"], steps
    at = [text.index(f"`{s}`") for s in steps]
    assert at == sorted(at), steps  # (in the workflow's order)


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
    print("ok")
