"""tweak.py <src> <dst> key=value ...: a hand pass on a stacked head (the agent's finishing choices, noted):
  occ=<occlusion_strength> crease=<crease_strength> fine=<stack fine_strength> <layer>=<strength (skin_layers.edit)>
  brows.<k>=<json> eyes.<k>=<json>. LIGHT."""
import copy, json, sys
from hifipushie import blockin as bi, skin_layers as sl, store
src, dst = sys.argv[1:3]
s = copy.deepcopy(store.load(src))
ed = {}
for a in sys.argv[3:]:
    k, v = a.split("=", 1)
    if k == "occ":
        s["skin"]["stack"]["occlusion_strength"] = float(v)
    elif k == "crease":
        s["skin"]["stack"]["crease_strength"] = float(v)
    elif k == "fine":
        s["skin"]["stack"]["fine_strength"] = float(v)
    elif k.startswith("brows."):
        s["skin"].setdefault("hair", {}).setdefault("brows", {})[k[6:]] = json.loads(v)
    elif k.startswith("base."):   # base.<key>=json, merged into a dict value
        cur = s["base"].get(k[5:]); nv = json.loads(v)
        s["base"][k[5:]] = {**cur, **nv} if isinstance(cur, dict) and isinstance(nv, dict) else nv
    elif k.startswith("skin."):
        s["skin"][k[5:]] = json.loads(v)
    elif k.startswith("eyes."):
        s["skin"].setdefault("eyes", {})[k[5:]] = json.loads(v)
    else:
        ed[k] = float(v)
if ed:
    s = sl.edit(s, **ed)
rj = copy.deepcopy(bi._refs(src))
if rj.get("blockin"):
    rj["blockin"] = {**rj["blockin"], "root": dst}
bi._save(dst, s, f"hand pass {sys.argv[3:]}", rj)
print(dst, {k: s["skin"]["stack"].get(k) for k in ("occlusion_strength", "crease_strength", "fine_strength")}, [(l["name"], l["opacity"]) for l in s["skin"]["stack"]["layers"]])
