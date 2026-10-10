"""ginfo.py <model ...>: a groom summary per model (style, head size, loose keys, lock count, the hair's last note)."""
import json, sys
from hifipushie import store

for m in sys.argv[1:]:
    try:
        s = store.load(m)
    except Exception as e:  # noqa: BLE001
        print(m, "?", e)
        continue
    h = s.get("hair") or {}
    g = h.get("groom") or {}
    print(m, "| style", h.get("style"), "| base.style", s["base"].get("style"), "| head_size",
          ((s["base"].get("style") or {}).get("human") or {}).get("head_size"), "| locks", len(h.get("locks") or {}))
    print("   loose:", json.dumps(g.get("loose"))[:400])
    print("   strands:", json.dumps(h.get("strands"))[:200], "| look:", json.dumps(h.get("look"))[:200])
