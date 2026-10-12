"""unlog.py: take THIS agent's entries (gq_*, gs_* steps made before blockin.fork existed) back out of gj_G00's
blockin_log.json, which a step appends to by design. Nothing else in gj_G00 was written."""
import json
p = "/home/joe/dev/hifipushie/workspace/gj_G00/blockin_log.json"
L = json.load(open(p))
keep = [e for e in L if not str(e.get("to", "")).startswith(("gq_", "gs_"))]
print(len(L), "->", len(keep), [e.get("to") for e in keep])
json.dump(keep, open(p, "w"), indent=1)
