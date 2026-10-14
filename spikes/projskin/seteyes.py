"""seteyes.py <src> <dst> key=json ...: skin.eyes / skin.hair.brows keys set on a copy (eyes.caruncle=1.0, brows.density=0.5).
LIGHT. A hand pass: the agent's finishing choice after the measured base."""
import copy, json, sys
from hifipushie import blockin as bi, store
src, dst = sys.argv[1:3]
s = copy.deepcopy(store.load(src))
for a in sys.argv[3:]:
    k, v = a.split("=", 1)
    grp, key = k.split(".", 1)
    tgt = s["skin"].setdefault("eyes", {}) if grp == "eyes" else s["skin"].setdefault("hair", {}).setdefault("brows", {})
    tgt[key] = json.loads(v)
rj = copy.deepcopy(bi._refs(src))
if rj.get("blockin"):
    rj["blockin"] = {**rj["blockin"], "root": dst}
bi._save(dst, s, f"hand pass: {sys.argv[3:]}", rj)
print(dst, s["skin"].get("eyes"), s["skin"]["hair"].get("brows"))
