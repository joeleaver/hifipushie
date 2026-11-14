"""stackedit.py <src> <dst> layer=strength ...: skin_layers.edit (1 = as measured; > 1.25 lays the map twice). LIGHT."""
import copy, sys
from hifipushie import blockin as bi, skin_layers as sl, store
from hifipushie import skin_layers_stack
from hifipushie import blockin_models
src, dst = sys.argv[1:3]
kw = {a.split("=")[0]: float(a.split("=")[1]) for a in sys.argv[3:]}
s = skin_layers_stack.edit(store.load(src), **kw)
rj = copy.deepcopy(blockin_models._refs(src))
if rj.get("blockin"):
    rj["blockin"] = {**rj["blockin"], "root": dst}
blockin_models._save(dst, s, f"stack edit {kw}", rj)
print(dst, [(l["name"], l["opacity"]) for l in s["skin"]["stack"]["layers"]])
