"""takestack.py <head model> <stack model> <dst>: the head model (its base, forms, hand pass) with the other model's skin
stack (same atlas), its strengths kept; then the crease / occlusion maps redone for the head's own forms (recrease). LIGHT."""
import copy, sys, runpy
from hifipushie import blockin as bi, store
h, st_m, dst = sys.argv[1:4]
s = copy.deepcopy(store.load(h)); t = store.load(st_m)
keep = {k: s["skin"]["stack"][k] for k in ("occlusion_strength", "crease_strength") if k in s["skin"]["stack"]}
s["skin"]["stack"] = {**copy.deepcopy(t["skin"]["stack"]), **keep}
lay = {l["name"]: l["opacity"] for l in s["skin"].get("_", [])}
rj = copy.deepcopy(bi._refs(h))
if rj.get("blockin"):
    rj["blockin"] = {**rj["blockin"], "root": dst}
bi._save(dst, s, f"skin stack from {st_m} on {h}", rj)
sys.argv = ["recrease.py", dst]
runpy.run_path("spikes/projskin/recrease.py", run_name="__main__")
