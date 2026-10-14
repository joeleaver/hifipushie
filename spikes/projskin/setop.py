"""setop.py <layer>=<opacity> <model>...: set a stack layer's opacity on stored models (a light spec edit)."""
import sys
from hifipushie import store
k, v = sys.argv[1].split("=")
for m in sys.argv[2:]:
    sp = store.load(m)
    for l in sp["skin"]["stack"]["layers"]:
        if l["name"] == k:
            l["opacity"] = float(v)
    store.save(m, sp, f"stack {k} opacity {v}", checked=False)
    print(m, [(l["name"], l["opacity"]) for l in sp["skin"]["stack"]["layers"]])
