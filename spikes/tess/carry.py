"""carry.py <groom model> <head model> <dst> [fit 0|1]: dst = the head model (everything) + the groom model's hair
(groom / strands / look / style, its hair part), the groom's `fit` = the groom model's own head (hair.head_ref), so
its metres scale onto the new head; regrown (groom_hair replace) and synced."""
import copy, sys, time
from hifipushie import hair, server, store

src, head, dst = sys.argv[1:4]
fit = len(sys.argv) <= 4 or sys.argv[4] != "0"
a, b = store.load(src), copy.deepcopy(store.load(head))
b["hair"] = {k: copy.deepcopy(v) for k, v in a["hair"].items() if k != "locks"}
b.setdefault("parts", {})["hair"] = copy.deepcopy((a.get("parts") or {}).get("hair") or {})
if fit:
    b["hair"]["groom"]["fit"] = hair.head_ref(hair.scalp(src))
    print("fit", b["hair"]["groom"]["fit"], "-> this head", hair.head_ref(hair.scalp(head)))
store.save(dst, b, f"{head} + {src}'s groom" + (" (fit to the head)" if fit else ""))
rf = store.HOME / head / "human_refs.json"
if rf.exists():
    (store.HOME / dst / "human_refs.json").write_text(rf.read_text())
t = time.time()
print(str(server.groom_hair(dst, replace=True, note="carried groom regrown"))[:600], f"{time.time() - t:.0f} s")
print(str(server.sync(dst))[:200])
