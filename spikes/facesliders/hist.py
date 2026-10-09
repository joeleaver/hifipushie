"""hist.py <model>: what changed in the head between history versions (keys, identity norm of the change)."""
import json
import sys
from pathlib import Path

import numpy as np

d = Path("/home/joe/dev/hifipushie/workspace") / sys.argv[1] / "history"
prev = None
for f in sorted(d.glob("*.json")) + [d.parent / "spec.json"]:
    s = json.loads(f.read_text())
    s = s.get("spec", s)
    h = s["base"]["head"]
    meta = {k: s[k] for k in ("message", "note", "op") if k in s}
    if prev is not None:
        ch = [k for k in set(h) | set(prev) if k != "identity" and h.get(k) != prev.get(k)]
        ids = set(h.get("identity", {})) | set(prev.get("identity", {}))
        di = np.array([h.get("identity", {}).get(k, 0) - prev.get("identity", {}).get(k, 0) for k in ids])
        sh = [k for k in set(h.get("shape", {})) | set(prev.get("shape", {})) if h.get("shape", {}).get(k) != prev.get("shape", {}).get(k)]
        print(f.name, "changed", ch, "shape", sh, "identity |d|", round(float(np.linalg.norm(di)), 3), meta,
              {k: v for k, v in s.items() if k not in ("base", "joints", "bones", "blobs", "kits", "skin", "paint", "parts")}.keys())
    prev = h
