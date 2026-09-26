"""Call a terrain MCP tool from a shell, exactly as the server runs it (for when the MCP server running in a session
predates the tools). Images come back as files.

uv run python examples/terrain_tool.py help                      # the tools and their descriptions
uv run python examples/terrain_tool.py guide '{"topic": "terrain"}'
uv run python examples/terrain_tool.py set_terrain '{"name": "vale", "spec": {...}}'
uv run python examples/terrain_tool.py set_terrain '{"name": "vale", "patch": {...}}'
uv run python examples/terrain_tool.py look_terrain '{"name": "vale", "masks": true}'
An argument starting with @ is read from that file: set_terrain @args.json
"""
import json
import sys
from pathlib import Path

from hifipushie import server

TOOLS = ["guide", "set_terrain", "check_terrain", "look_terrain", "export_terrain", "terrain_history"]

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
from hifipushie import terrain_tools as tt
if not isinstance(out, list):
    out = [out]
k = 0
for o in out:
    if isinstance(o, str):
        print(o)
    else:  # an image: saved beside the terrain
        k += 1
        d = tt._dir(args["name"]) / "returned"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{tool}_v{len(tt.history(args['name']))}_{k}.png"
        p.write_bytes(o.data)
        print(f"[image {k}: {p}]")
