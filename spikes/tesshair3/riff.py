"""riff.py <dst> <head model> <carry_from | none> '<style json>' [look=<save png> views=a,b size=420]: THE TOOL PATH.
dst (th_* only) = a copy of the head model, then server.tie_hair(dst, style, carry_from) exactly as an MCP client
calls it; look= also calls server.look_hair(dst, views (default around), save=) (the head-cropped hair stage)."""
import json, shutil, sys, time
from hifipushie import server, store

dst, head, src, st = sys.argv[1:5]
kw = dict(a.split("=", 1) for a in sys.argv[5:])
assert dst.startswith("th_"), dst
d = store.HOME / dst
d.mkdir(exist_ok=True)
sp = json.loads((store.HOME / head / "spec.json").read_text())
sp.pop("hair", None)
(d / "spec.json").write_text(json.dumps(sp, indent=1))
if (store.HOME / head / "human_refs.json").exists():
    shutil.copy(store.HOME / head / "human_refs.json", d / "human_refs.json")
t = time.time()
print(server.tie_hair(dst, json.loads(st), carry_from=None if src == "none" else src))
print(f"tie_hair {time.time() - t:.0f} s")
if kw.get("sync"):
    t = time.time()
    print(str(server.sync(dst))[:300])
    print(f"sync {time.time() - t:.0f} s")
if kw.get("look"):
    t = time.time()
    r = server.look_hair(dst, views=kw.get("views", "around").split(","), size=int(kw.get("size", 420)), clay=False,
                         save=kw["look"])
    print(r[-1])
    print(f"look_hair {time.time() - t:.0f} s")
