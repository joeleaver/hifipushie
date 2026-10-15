"""toggle2.py <model> <tag> <drop prefixes, comma> [hair=0] [ref= own=]: render the front mouth (lit + unlit) with skin
layers whose names start with any prefix DROPPED (patched in this process: the stage syncs here), hair optional."""
import copy, runpy, sys
from hifipushie import blockin as bi, skin, store
m, tag, drops = sys.argv[1:4]
pre = [d for d in drops.split(",") if d and d != "none"]
_b = skin._build
def build(spec, J):
    out = _b(spec, J)
    return {k: v for k, v in out.items() if not any(k.startswith("skin:" + d) for d in pre)}
skin._build = build
cp = "ps_tg2_" + tag
s = copy.deepcopy(store.load(m)); s["skin"]["seed"] = int(s["skin"].get("seed", 0)) + 0   # (a copy so its stage is its own)
s["skin"]["_tg"] = None if False else None
s["skin"].pop("_tg")
s.setdefault("meta", {})
rj = copy.deepcopy(bi._refs(m))
s["skin"]["variation"] = float(s["skin"].get("variation", 1.0)) + 1e-6 * (hash(tag) % 997)   # distinct stage key per tag
bi._save(cp, s, f"toggle2 drop {drops}", rj)
out = f"/mnt/data/hifipushie/projskin/out/toggle2/{tag}"
rest = sys.argv[4:]
for flat in ("0", "1"):
    sys.argv = ["cu.py", cp, out, "only=" + __import__("os").environ.get("TG_ONLY", "mouth"), "views=0", f"flat={flat}"] + rest
    runpy.run_path("spikes/projskin/cu.py", run_name="__main__")
