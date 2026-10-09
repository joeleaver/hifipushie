"""setb.py <src> <dst> <json patch for base> [measure 0|1]: copy a model with base.<path> keys merged
(patch like {"body": {"weight": 0.2}, "style": {"human": {"head_size": 0.95}}}), then measure_human."""
import copy, json, os, sys
from hifipushie import server, store


def merge(a, b):
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(a.get(k), dict):
            merge(a[k], v)
        elif v is None:
            a.pop(k, None)
        else:
            a[k] = v


src, dst, patch = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
sp = copy.deepcopy(store.load(src))
merge(sp.setdefault("base", {}), patch)
v = store.save(dst, sp, f"tess: {src} + base {patch}")
if src != dst:
    rf = store.HOME / src / "human_refs.json"
    if rf.exists():
        (store.HOME / dst / "human_refs.json").write_text(rf.read_text())
print("saved", dst, "v", v)
if len(sys.argv) <= 4 or sys.argv[4] != "0":
    r = server.measure_human(dst, picture=False)
    print("\n".join(x for x in r if isinstance(x, str))[:1500] if isinstance(r, list) else str(r)[:1500])
