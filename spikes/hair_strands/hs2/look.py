"""look.py <model> <out.png> [style=strands] [views=a,b] [size=480] [engine=cycles] [count=N] [k=v strands...] [look.k=v] [groom.a.b=v]:
a hair look with spec overrides held in memory (nothing saved)."""
import json, os, sys, time
from hifipushie import hair, store
name, out = sys.argv[1], sys.argv[2]
spec = store.load(name)
h = spec.setdefault("hair", {})
h["style"] = "strands"
views = ("front", "three_quarter", "side", "back", "close_front", "close_side")
size, kw = 480, {}
for a in sys.argv[3:]:
    k, v = a.split("=", 1)
    if k == "style": h["style"] = v
    elif k == "views": views = tuple(v.split(","))
    elif k == "size": size = int(v)
    elif k == "engine": kw["engine"] = v
    elif k == "count": kw["count"] = int(v)
    elif k == "budget": kw["budget"] = int(v) if v.isdigit() else v
    elif k == "samples": kw["samples"] = int(v)
    elif k == "clay": kw["clay"] = bool(int(v))
    elif k.startswith("look."): h.setdefault("look", {})[k[5:]] = json.loads(v) if v[:1] != "#" else v
    elif k.startswith("groom."):
        d = h.setdefault("groom", {})
        ks = k[6:].split(".")
        for q in ks[:-1]: d = d.setdefault(q, {})
        d[ks[-1]] = json.loads(v)
    else: h.setdefault("strands", {})[k] = json.loads(v)
from hifipushie import hair_strands as HS
skip = [q for q in os.environ.get("HS_SKIP", "").split(",") if q]
_st = HS.stacks
def stacks(*a, **k):
    d = _st(*a, **k)
    return {n: [m for m in st if not any(q in m[0] for q in skip)] for n, st in d.items()}
HS.stacks = stacks
hair.validate(spec)
t = time.time()
sheet, sec, fr = hair.look(name, views=views, size=size, save=os.path.join(os.environ["HR"], out), spec=spec, **kw)
print("\n".join(l for l in fr if "strands" in l), [l.split()[1] for l in fr if "frame" in l])
print("look", sec, "s", "bare", hair.look.mass_share)
g = hair.look.gate
print("gate", {k: v for k, v in g.items() if k != "owners"} if isinstance(g, dict) else g)
