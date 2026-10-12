"""mk.py <src> <dst> [drop=a.b.c,d.e] [set='{"a.b.c": value}']: a block-in FORK of <src> (its own log; the source is
never written) with keys dropped / set by dotted path under the spec (e.g. drop=base.head.eye_radius,skin.eyes.iris_size)."""
import json
import sys

from hifipushie import blockin as bi
from hifipushie import store

src, dst = sys.argv[1:3]
kw = dict(a.split("=", 1) for a in sys.argv[3:])
bi.fork(src, dst, replace=True)
sp = store.load(dst)


def walk(path):
    d = sp
    ks = path.split(".")
    for k in ks[:-1]:
        d = d.setdefault(k, {})
    return d, ks[-1]


for p in [x for x in kw.get("drop", "").split(",") if x]:
    d, k = walk(p)
    print("drop", p, "=", d.pop(k, None))
for p, v in json.loads(kw.get("set", "{}")).items():
    d, k = walk(p)
    d[k] = v
    print("set", p, "=", v)
bi._save(dst, sp, f"gnmnative mk from {src}: {kw}", bi._refs(dst))
print(dst, "saved; head keys:", {k: v for k, v in sp["base"]["head"].items() if k != "identity"}, "cornea", sp["base"].get("cornea"),
      "skin.eyes", (sp.get("skin") or {}).get("eyes"))
