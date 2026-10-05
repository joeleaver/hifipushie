"""Call a vegetation MCP tool from a shell, exactly as the server runs it (for when the MCP server running in a
session predates the tools). Images come back as files.

uv run python examples/plant_tool.py help                         # the tools and their descriptions
uv run python examples/plant_tool.py guide '{"topic": "vegetation"}'
uv run python examples/plant_tool.py grow_plant '{"name": "old_oak", "spec": {"species": "oak", "age": 120}}'
uv run python examples/plant_tool.py look_plant '{"name": "old_oak", "views": ["clay", "far"]}'
An argument starting with @ is read from that file: grow_plant @args.json
"""
import json
import sys
from pathlib import Path

from hifipushie import server

TOOLS = ["guide", "get_plant", "grow_plant", "edit_plant", "look_plant", "look_plants", "plant_reference", "export_plant",
         "plant_history"]

if len(sys.argv) < 2 or sys.argv[1] == "help":
    for t in TOOLS:
        print(f"== {t}\n{getattr(server, t).__doc__}\n")
    sys.exit(0)
tool = sys.argv[1]
if tool not in TOOLS:
    sys.exit(f"unknown tool {tool!r}: {TOOLS}")
arg = sys.argv[2] if len(sys.argv) > 2 else "{}"
args = json.loads(Path(arg[1:]).read_text() if arg.startswith("@") else arg)
try:
    out = getattr(server, tool)(**args)
except (ValueError, KeyError) as e:  # as the MCP client would see it: the message, not a traceback
    sys.exit(f"ERROR: {e}")
for o in out if isinstance(out, list) else [out]:
    if isinstance(o, str):
        print(o)  # (look_plant's text names the image files it wrote)
