"""riff6.py <dst> <head model> <carry_from | none> <style json | @file> [look=<json | @file>] [groom=<json | @file>]
[seed=<n>]: THE TOOL PATH (as spikes/tesshair5/riff5.py): dst (th_T6*, th_V*, th_X* only) = a copy of the head model,
then server.tie_hair(dst, style, carry_from, look) exactly as an MCP client calls it; groom= / seed= are a
server.groom_hair patch on top (seed: groom.seed, the random draw of roots, wisps and the tail)."""
import json
import shutil
import sys
import time

from hifipushie import server, store


def arg(a):
    return json.loads(open(a[1:]).read() if a.startswith("@") else a)


dst, head, src, st = sys.argv[1:5]
kw = dict(a.split("=", 1) for a in sys.argv[5:])
assert dst.startswith(("th_V7", "th_V8", "th_V9", "th_W")), dst  # (this round's names only)
d = store.HOME / dst
d.mkdir(exist_ok=True)
sp = json.loads((store.HOME / head / "spec.json").read_text())
sp.pop("hair", None)
(d / "spec.json").write_text(json.dumps(sp, indent=1))
if (store.HOME / head / "human_refs.json").exists():
    shutil.copy(store.HOME / head / "human_refs.json", d / "human_refs.json")
t = time.time()
r = server.tie_hair(dst, arg(st), carry_from=None if src == "none" else src, look=arg(kw["look"]) if kw.get("look") else None)
print(str(r)[:1500])
print(f"tie_hair {time.time() - t:.0f} s")
patch = arg(kw["groom"]) if kw.get("groom") else {}
if kw.get("seed") is not None:
    patch = {**patch, "seed": int(kw["seed"])}
if patch:
    print(str(server.groom_hair(dst, groom=patch, replace=True))[:400])
