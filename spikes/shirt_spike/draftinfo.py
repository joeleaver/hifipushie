"""draftinfo.py: what our pipeline changed in Simon before the fit: the table's alter ops, the collar rule's options,
band_ends (was / now mm), and the stand / collar ends straight from FreeSewing vs after."""
import json
from hifipushie import store, cloth, pattern_form as pf
spec = store.load("wf_simon"); g = cloth.expanded(spec["cloth"]["shirt"])
tbl = cloth.designs()["simon"]
print("table alter ops:", json.dumps(tbl.get("alter"))[:800])
print("table options:", tbl.get("options"), "collar_rule:", tbl.get("collar_rule"))
res = pf.on_form("wf_simon", "shirt", spec, g=g)
B = res.get("pieces") or {}
print("draft info keys:", list((B.get("draft") or {}).keys()))
print("band_ends:", (B.get("draft") or {}).get("band_ends"), "options used:", {k: v for k, v in ((B.get("draft") or {}).get("options") or {}).items() if "ollar" in k or "Stand" in k or "button" in k.lower() or "placket" in k.lower()})
