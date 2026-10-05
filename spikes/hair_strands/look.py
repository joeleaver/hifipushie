"""look.py <model> <out.png> [style=cards] [views=a,b] [size=480] [k=v strands...] [look.k=v] : a hair look of a
model with spec overrides held in memory (nothing saved)."""
import json
import os
import sys
import time
from hifipushie import hair, store

name, out = sys.argv[1], sys.argv[2]
spec = store.load(name)
h = spec.setdefault("hair", {})
views = ("front", "three_quarter", "side", "back", "close_front", "close_side")
size = 480
for a in sys.argv[3:]:
    k, v = a.split("=", 1)
    if k == "style":
        h["style"] = v
    elif k == "views":
        views = tuple(v.split(","))
    elif k == "size":
        size = int(v)
    elif k.startswith("look."):
        h.setdefault("look", {})[k[5:]] = json.loads(v) if v[:1] not in "#" else v
    else:
        h.setdefault("strands", {})[k] = json.loads(v)
hair.validate(spec)
t = time.time()
sheet, sec, frames = hair.look(name, views=views, size=size, save=os.path.join(os.environ["HR"], out), spec=spec)
print("look", sec, "s", "bare", hair.look.mass_share, "gate", {k: v for k, v in (hair.look.gate or {}).items() if k != "owners"} if isinstance(hair.look.gate, dict) else hair.look.gate)
