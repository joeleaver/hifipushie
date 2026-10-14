"""iris_back.py <src> <model>...: give the models (copies of src with a projection) src's own skin.eyes back (the iris read
is no longer applied by default); prints what the read would say now."""
import copy, sys
from hifipushie import store
src = store.load(sys.argv[1])
for m in sys.argv[2:]:
    sp = copy.deepcopy(store.load(m))
    was = sp["skin"].get("eyes")
    sp["skin"]["eyes"] = copy.deepcopy(src["skin"].get("eyes"))
    store.save(m, sp, f"skin.eyes as {sys.argv[1]} has them (the iris read is not applied by default)", checked=False)
    print(m, (was or {}).get("iris"), "->", (sp["skin"]["eyes"] or {}).get("iris"))
