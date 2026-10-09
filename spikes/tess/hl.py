"""hl.py <model> <out png> [views csv] [strands patch json]: look_hair (EEVEE) of the model, optionally with a strands
patch applied to a scratch copy first (nothing saved on the model)."""
import copy, json, os, sys
from hifipushie import server, store

name, out = sys.argv[1], sys.argv[2]
views = sys.argv[3].split(",") if len(sys.argv) > 3 and sys.argv[3] else ["front", "three_quarter"]
sp_patch = json.loads(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4] else None
nm = name
if sp_patch:
    nm = name + "__hl"
    sp = copy.deepcopy(store.load(name))
    sp["hair"].setdefault("strands", {}).update(sp_patch)
    store.save(nm, sp, "tess: hair look scratch")
    server.sync(nm)
r = server.look_hair(nm, views=views, size=560, save=out)
print("\n".join(x for x in r if isinstance(x, str))[:1200] if isinstance(r, list) else str(r)[:1200])
