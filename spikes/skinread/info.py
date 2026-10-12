"""info.py <model>..: the skin spec, paint layers and references of models."""
import json, sys
from hifipushie import store, likeness as lk
for m in sys.argv[1:]:
    s = store.load(m)
    print("==", m, list(s.keys()))
    print(json.dumps(s.get("skin"))[:4000])
    print("paint", list((s.get("paint") or {}).keys()))
    print("hair", list((s.get("hair") or {}).keys())[:12])
    print("base keys", list(s["base"].keys()), "head keys", list((s["base"].get("head") or {}).keys()))
    r = lk._refs(m)
    print(list(r.keys()))
    for v, c in zip(r["views"], r["cameras"]):
        print(v, c and c["size"], c and round(c["f"]), c and c["t"])
    print((r.get("blockin") or {}).get("boxes"))
