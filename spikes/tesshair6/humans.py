"""humans.py: every model in the workspace with hair: base kind, groom mode, hairline overrides, whether a scalp is
cached. (private subjects' models: listed by name only, never opened further.)"""
import json

from hifipushie import store

for d in sorted(store.HOME.iterdir()):
    f = d / "spec.json"
    if not f.exists():
        continue
    try:
        sp = json.loads(f.read_text())
    except Exception:
        continue
    h = sp.get("hair")
    if not h:
        continue
    b = sp.get("base") or {}
    g = h.get("groom") or {}
    kind = (b.get("body") or {}).get("source") or b.get("template") or ("kit" if not b else "?")
    print(d.name, "| base", kind, "| head", (b.get("head") or {}).get("source") if isinstance(b.get("head"), dict) else b.get("head"),
          "| mode", h.get("mode"), "| tied" if g.get("tied") else ("| tie" if g.get("tie") else "|"),
          "| hairline", json.dumps(g.get("hairline") or {})[:90], "| scalp", len(list(d.glob("hair_scalp_*.npz"))),
          "| mtime", int(f.stat().st_mtime))
