"""setkey.py <sg model> <source model> <skin key> [..]: copy spec["skin"][key] from the source model onto an sg_* copy
(e.g. the lips back to the a1 start before a lips-only refit). setkey.py <sg model> - <key>=<json> sets a value."""
import json, sys
from hifipushie import store

dst, src = sys.argv[1:3]
assert dst.startswith("sg_"), dst
sp = store.load(dst)
for k in sys.argv[3:]:
    if "=" in k:
        key, v = k.split("=", 1)
        d = sp.setdefault("skin", {})
        path = key.split(".")
        for q in path[:-1]:
            d = d.setdefault(q, {})
        d[path[-1]] = json.loads(v)
    else:
        v = (store.load(src).get("skin") or {}).get(k)
        if v is None:
            sp["skin"].pop(k, None)
        else:
            sp["skin"][k] = v
store.save(dst, sp, f"skinfolds2: skin {sys.argv[3:]} set")
print(dst, json.dumps({k.split('=')[0].split('.')[0]: sp["skin"].get(k.split('=')[0].split('.')[0]) for k in sys.argv[3:]})[:600])
