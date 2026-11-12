"""iris2.py <model> <scratch name> [start hex]: skin_from_reference's eyeballs group alone on a fork whose iris is set
back to the default brown (or the given colour), two rounds: what the default path now sets."""
import sys
from hifipushie import blockin as bi, skin_read as sr, store
from hifipushie import blockin_models, skin_read_fit

src, name = sys.argv[1], sys.argv[2]
blockin_models.fork(src, name, replace=True)
sp = store.load(name)
e = dict((sp.get("skin") or {}).get("eyes") or {})
old = e.get("iris")
if len(sys.argv) > 3:
    e["iris"] = sys.argv[3]
else:
    e.pop("iris", None)
sp.setdefault("skin", {})["eyes"] = e
store.save(name, sp, "readmix iris2: the iris set back")
print("iris before:", old, "-> start", e.get("iris", "default #5a3a1e"))
r = skin_read_fit.apply(name, groups=("eyeballs",), rounds=2, log=print)
for f in r["fits"]:
    print([c for c in f["changes"] if c[0] == "eyes.iris"])
print("iris after:", (store.load(name)["skin"].get("eyes") or {}).get("iris"))
