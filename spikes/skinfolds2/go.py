"""go.py <model> <out> [rounds=2] [tone=<fitzpatrick>] [anchor=auto] [groups=a,b] [white=<json list>]: skin_read.apply on a
copy (the source is never written; out must be sg_*), the whole report to $G/out/go_<out>.txt, the skins to
$G/out/go_<out>.json."""
import json, os, sys, time
from hifipushie import skin_read as sr, store

m, out = sys.argv[1:3]
assert out.startswith("sg_"), out
kw = dict(a.split("=", 1) for a in sys.argv[3:])
t = time.time()
res = sr.apply(m, out=out, rounds=int(kw.get("rounds", 2)), anchor=kw.get("anchor", "auto"),
               stubble=None if "stubble" not in kw else kw["stubble"] == "1", tone=float(kw["tone"]) if "tone" in kw else None,
               groups=tuple(kw["groups"].split(",")) if "groups" in kw else sr.DEFAULT_GROUPS,
               white=json.loads(kw["white"]) if "white" in kw else None,
               log=lambda s: print(s) if "[measure]" not in str(s) else None)
G = os.environ["G"] + "/out"
open(f"{G}/go_{out}.txt", "w").write(res["text"])
json.dump({"before": store.load(m).get("skin"), "after": res["skin"]}, open(f"{G}/go_{out}.json", "w"), indent=1)
print(res["text"])
print(f"\n{time.time() - t:.0f} s")
