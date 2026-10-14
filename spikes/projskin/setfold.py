"""setfold.py <src> <dst> key=value ...: base.head.lid_fold top-level keys set (json values) on a copy. LIGHT."""
import copy, json, sys
from hifipushie import blockin as bi, store
src, dst = sys.argv[1:3]
s = copy.deepcopy(store.load(src))
for a in sys.argv[3:]:
    k, v = a.split("=", 1)
    s["base"]["head"]["lid_fold"][k] = json.loads(v)
rj = copy.deepcopy(bi._refs(src))
if rj.get("blockin"):
    rj["blockin"] = {**rj["blockin"], "root": dst}
bi._save(dst, s, f"lid_fold {sys.argv[3:]}", rj)
print(dst, {k: s["base"]["head"]["lid_fold"].get(k) for k in ("depth", "thick")})
