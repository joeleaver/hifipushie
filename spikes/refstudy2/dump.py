"""dump.py: the head settings of the Garrett models (what each pass set)."""
import json

import garrett
from hifipushie import store


def show(tag, b):
    h = b["head"]
    print("==", tag, {k: (v if k not in ("identity", "warp") else "<%s>" % type(v).__name__) for k, v in h.items()})
    print("   style", b.get("style"))


show("read3", store.load("rs_garrett_read3")["base"])
for v in (16, 22, 23):
    show("om v%d" % v, garrett.hist("om_garrett", v)["base"])
sp = store.load("rs_garrett_read3")
print(sp.keys(), "hair" in sp, len(sp.get("hair", {}).get("locks", [])) if sp.get("hair") else 0)
print(json.dumps(json.load(open(store.HOME / "rs_garrett_read3" / "human_refs.json"))["cameras"])[:600])
