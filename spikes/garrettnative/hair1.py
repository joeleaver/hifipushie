"""hair1.py <model> <groom model> [patch.json ..]: the groom model's hair worn on <model> IN PLACE (a gn_* / garrett_n*
scratch model only): hair.carry (groom / strands / look / style with groom.fit = the head it was made on; no locks),
patches deep-merged (null deletes), parts.hair copied, then the locks regrown on THIS head's scalp (hair.groom replace)."""
import copy
import json
import sys
import time

from hifipushie import hair, store

dst, gm = sys.argv[1:3]
assert dst.startswith(("gn_", "garrett_n")), dst
sp = store.load(dst)
h = hair.carry(gm)
h.pop("locks", None)
h.pop("removed", None)


def merge(a, b):
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(a.get(k), dict):
            merge(a[k], v)
        elif v is None:
            a.pop(k, None)
        else:
            a[k] = v


for f in sys.argv[3:]:
    merge(h, json.load(open(f)))
sp["hair"] = h
sp.setdefault("parts", {})["hair"] = copy.deepcopy((store.load(gm).get("parts") or {}).get("hair") or {})
store.save(dst, sp, f"garrettnative: {gm}'s groom carried (fit {h['groom'].get('fit')})")
t = time.time()
r = hair.groom(dst, replace=True, note=f"garrettnative: {gm}'s groom regrown on {dst}")
print(str(r)[:800])
sp = store.load(dst)
print("fit", sp["hair"]["groom"].get("fit"), "head now", hair.head_ref(hair.scalp(dst, sp)), "locks", len(sp["hair"]["locks"]), f"{time.time() - t:.0f} s")
