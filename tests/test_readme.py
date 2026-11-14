"""The README's tool table is the registry (the area re-review: 12 rows, no find_tool, no call_tool, no domain)."""
import re
from pathlib import Path

from hifipushie import mcp_app

README = (Path(__file__).resolve().parent.parent / "README.md").read_text()
TABLE = README[README.index("## Tools"):README.index("## Install")]


def test_every_registered_tool_is_in_the_readme_under_its_domain_and_nothing_else_is():
    rows = {m.group(1): set(re.findall(r"`(\w+)`", m.group(2)))
            for m in re.finditer(r"^\| (\w+) \| [^|]+ \| (.+) \|$", TABLE, re.M) if m.group(1) != "domain"}
    assert list(rows) == list(mcp_app.TOOL_GROUPS)
    for g, v in mcp_app.TOOL_GROUPS.items():
        assert rows[g] == set(v["tools"]), g
    assert set().union(*rows.values()) == set(mcp_app._TOOLS)
    assert f"{len(mcp_app._TOOLS)} tools in {len(mcp_app.TOOL_GROUPS)} domains" in TABLE


def test_the_readme_says_how_an_agent_finds_a_tool():
    for s in ("`call_tool(name, args)`", "`find_tool(", "`guide`", 'guide(topic="example")'):
        assert s in TABLE, s
    assert "bin/review" not in mcp_app.TOOL_GROUPS["concept"]["about"]
