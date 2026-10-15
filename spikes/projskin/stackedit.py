"""stackedit.py <src> <dst> layer=strength ...: skin_layers.edit (1 = as measured; > 1.25 lays the map twice). LIGHT."""
import copy, sys
from hifipushie import blockin as bi, skin_layers as sl, store
src, dst = sys.argv[1:3]
kw = {a.split("=")[0]: float(a.split("=")[1]) for a in sys.argv[3:]}
s = sl.edit(store.load(src), **kw)
rj = copy.deepcopy(bi._refs(src))
if rj.get("blockin"):
    rj["blockin"] = {**rj["blockin"], "root": dst}
bi._save(dst, s, f"stack edit {kw}", rj)
print(dst, [(l["name"], l["opacity"]) for l in s["skin"]["stack"]["layers"]])
