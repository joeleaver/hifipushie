"""cpmodel.py <src> <dst> '<json: {"head": {key: value | null}, "hair": {...} | null, "drop_paint": [prefixes]}>':
a copy of a model with base.head keys set / removed (null) and its human_refs.json."""
import json
import shutil
import sys

from hifipushie import store

src, dst, p = sys.argv[1], sys.argv[2], json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
sp = json.loads((store.HOME / src / "spec.json").read_text())
for k, v in (p.get("head") or {}).items():
    if v is None:
        sp["base"]["head"].pop(k, None)
    else:
        sp["base"]["head"][k] = v
if "hair" in p:
    if p["hair"] is None:
        sp.pop("hair", None)
        (sp.get("parts") or {}).pop("hair", None)
    else:
        sp["hair"] = p["hair"]
for pre in p.get("drop_paint") or []:
    sp["paint"] = {k: v for k, v in sp["paint"].items() if not k.startswith(pre)}
store.save(dst, sp, f"garrett4: copy of {src} {json.dumps(p)[:80]}")
f = store.HOME / src / "human_refs.json"
if f.exists():
    shutil.copy(f, store.HOME / dst / "human_refs.json")
print("saved", dst)
