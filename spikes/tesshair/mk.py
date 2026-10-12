"""mk.py <dst> <head model> <groom model> [patch.json ...]: dst = the head model's spec + the groom model's hair
(hair.carry: groom / strands / look / style with groom.fit, NO locks) + patches {"groom": .., "strands": .., "look": ..}
deep-merged (null deletes), then the locks regrown on dst's head (hair.groom replace). Never writes an existing model
that is not a th_* scratch model."""
import copy, json, shutil, sys, time
import numpy as np
from hifipushie import hair, store

dst, head, gm = sys.argv[1:4]
assert dst.startswith("th_"), dst
sp = copy.deepcopy(store.load(head))
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


for f in sys.argv[4:]:
    merge(h, json.load(open(f)))
sp["hair"] = h
sp.setdefault("parts", {})["hair"] = copy.deepcopy((store.load(gm).get("parts") or {}).get("hair") or {})
d = store.HOME / dst
d.mkdir(exist_ok=True)
(d / "spec.json").write_text(json.dumps(sp, indent=1))
shutil.copy(store.HOME / head / "human_refs.json", d / "human_refs.json")
t = time.time()
r = hair.groom(dst, replace=True, note=f"tesshair: {gm}'s groom regrown on {head}")
print(str(r)[:1200])
sp = store.load(dst)
sc = hair.scalp(dst, sp)
print("fit", sp["hair"]["groom"].get("fit"), "head now", hair.head_ref(sc), "locks", len(sp["hair"]["locks"]), f"{time.time() - t:.0f} s")
