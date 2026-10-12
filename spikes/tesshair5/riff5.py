"""riff5.py <dst> <head model> <carry_from | none> <style json | @file> [look=<json | @file>]: THE TOOL PATH, as
spikes/tesshair3/riff.py, + a look patch: dst (th_* only) = a copy of the head model, then
server.tie_hair(dst, style, carry_from, look) exactly as an MCP client calls it."""
import json
import shutil
import sys
import time

from hifipushie import server, store


def arg(a):
    return json.loads(open(a[1:]).read() if a.startswith("@") else a)


dst, head, src, st = sys.argv[1:5]
kw = dict(a.split("=", 1) for a in sys.argv[5:])
assert dst.startswith("th_") and dst[3] in "TSH" and dst[4] != "4", dst  # (th_T5x, th_S*, th_H*: this round's only)
d = store.HOME / dst
d.mkdir(exist_ok=True)
sp = json.loads((store.HOME / head / "spec.json").read_text())
sp.pop("hair", None)
(d / "spec.json").write_text(json.dumps(sp, indent=1))
if (store.HOME / head / "human_refs.json").exists():
    shutil.copy(store.HOME / head / "human_refs.json", d / "human_refs.json")
t = time.time()
print(server.tie_hair(dst, arg(st), carry_from=None if src == "none" else src, look=arg(kw["look"]) if kw.get("look") else None))
print(f"tie_hair {time.time() - t:.0f} s")
