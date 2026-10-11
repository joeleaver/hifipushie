"""call.py <tool> '<json kwargs>': a server tool called directly; images saved by the tool's own save=, text printed."""
import sys, json
from hifipushie import server
r = getattr(server, sys.argv[1])(**json.loads(sys.argv[2]))
print(r if isinstance(r, str) else "\n".join(x for x in r if isinstance(x, str)))
