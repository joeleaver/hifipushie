"""h1.py <src model> <dst> [groom patch json] [look patch json] [strands patch json]: dst = src + hs_tess's strand groom
(groom / strands / look / style, its hair part), regrown on dst's head (groom_hair replace) and synced."""
import copy, json, sys, time
from hifipushie import server, store

src, dst = sys.argv[1], sys.argv[2]
gp = json.loads(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else {}
lp = json.loads(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4] else {}
spp = json.loads(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5] else {}
sp = copy.deepcopy(store.load(src))
if not sp.get("hair"):
    hs = store.load("hs_tess")
    sp["hair"] = {k: copy.deepcopy(v) for k, v in hs["hair"].items() if k != "locks"}
    sp.setdefault("parts", {})["hair"] = copy.deepcopy((hs.get("parts") or {}).get("hair") or {})
h = sp["hair"]
for key, p in (("groom", gp), ("look", lp), ("strands", spp)):
    for k, v in p.items():
        if isinstance(v, dict) and isinstance(h.setdefault(key, {}).get(k), dict):
            h[key][k].update(v)
        else:
            h[key][k] = v
store.save(dst, sp, f"tess: {src} + strand groom (hs_tess's, regrown)")
rf = store.HOME / src / "human_refs.json"
if rf.exists():
    (store.HOME / dst / "human_refs.json").write_text(rf.read_text())
t = time.time()
print(str(server.groom_hair(dst, replace=True, note="tess: regrow on the one-mesh head"))[:1500])
print(f"groom {time.time() - t:.0f} s")
t = time.time()
r = server.sync(dst)
print(str(r)[:600], f"sync {time.time() - t:.0f} s")
