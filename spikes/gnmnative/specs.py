"""gnmnative: what the named models' base / head hold (identity and expression lists cut short)."""
import json
import os
import sys

H = os.environ.get("HIFIPUSHIE_HOME", "/home/joe/dev/hifipushie/workspace")
for m in sys.argv[1:]:
    s = json.load(open(f"{H}/{m}/spec.json"))
    b = s.get("base", {})
    hd = dict(b.get("head", {}))
    idn, ex = hd.pop("identity", None), hd.pop("expression", None)
    print(m, {k: v for k, v in b.items() if k != "head"})
    print("  head", json.dumps(hd)[:1500], "| identity n", len(idn or {}), list(idn or {})[:3], "| expr n", len(ex or {}),
          list(ex or {})[:3])
    print("  top keys", list(s), "parts", list(s.get("parts") or {}), "skin.eyes", (s.get("skin") or {}).get("eyes"),
          "blobs", list(s.get("blobs") or {}), "kits", list(s.get("kits") or {}))
    print("  files", sorted(os.listdir(f"{H}/{m}"))[:30])
