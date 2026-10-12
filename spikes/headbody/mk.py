"""mk.py <src> <dst> [key=json ...]: <dst> = <src>'s spec with base.head.attach "native" (+ dotted keys set; value
null drops). The source is never written. Hair / cloth are dropped (they were made for the other head)."""
import copy, json, sys
from hifipushie import store

src, dst = sys.argv[1:3]
assert dst.startswith("hb_")
sp = copy.deepcopy(store.load(src))
for k in ("hair", "cloth"):
    sp.pop(k, None)
sp["base"]["head"]["attach"] = "native"
for a in sys.argv[3:]:
    p, v = a.split("=", 1)
    d = sp
    ks = p.split(".")
    for k in ks[:-1]:
        d = d.setdefault(k, {})
    v = json.loads(v)
    if v is None:
        d.pop(ks[-1], None)
    else:
        d[ks[-1]] = v
print(dst, "version", store.save(dst, sp, f"headbody mk from {src}: {sys.argv[3:]}"), {k: v for k, v in sp["base"]["head"].items() if k != "identity"})
