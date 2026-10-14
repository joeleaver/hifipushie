"""toggle.py <model> <tag> <change> [ref= own=]: a copy of <model> (ps_tg_<tag>) with ONE change, its front mouth rendered lit
and unlit into out/toggle/<tag>/. Changes: stack:<layer>=<opacity> | stack:fine=<s> | stack:base=<s> | skin:<key>=<json>
| none. A test for "which layer draws this"."""
import copy, json, os, runpy, sys
from hifipushie import blockin as bi, store
m, tag, ch = sys.argv[1:4]
s = copy.deepcopy(store.load(m))
if ch != "none":
    k, v = ch.split("=", 1)
    kind, name = k.split(":", 1)
    if kind == "stack":
        st = s["skin"]["stack"]
        if name == "fine":
            st["fine_strength"] = float(v)
        elif name == "base":
            st["base_opacity"] = float(v)
        else:
            for l in st["layers"]:
                if l["name"].rstrip("+") == name:
                    l["opacity"] = float(v)
    elif kind == "skin":
        s["skin"][name] = json.loads(v)
cp = "ps_tg_" + tag
rj = copy.deepcopy(bi._refs(m))
bi._save(cp, s, f"toggle {ch}", rj)
out = f"/mnt/data/hifipushie/projskin/out/toggle/{tag}"
rest = sys.argv[4:]
for flat in ("0", "1"):
    sys.argv = ["cu.py", cp, out, "only=mouth", "views=0", f"flat={flat}"] + rest
    runpy.run_path("spikes/projskin/cu.py", run_name="__main__")
