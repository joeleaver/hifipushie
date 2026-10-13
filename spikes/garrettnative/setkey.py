"""setkey.py <model> '<json {dotted.path: value | null}>' [note]: set / drop spec keys on a gn_* / garrett_n* scratch model."""
import json
import sys

from hifipushie import store

m = sys.argv[1]
assert m.startswith(("gn_", "garrett_n")), m
sp = store.load(m)
for p, v in json.loads(sys.argv[2]).items():
    d = sp
    ks = p.split(".")
    for k in ks[:-1]:
        d = d.setdefault(k, {})
    old = d.get(ks[-1])
    if v is None:
        d.pop(ks[-1], None)
    else:
        d[ks[-1]] = v
    print(p, ":", old, "->", v)
store.save(m, sp, sys.argv[3] if len(sys.argv) > 3 else "garrettnative setkey")
