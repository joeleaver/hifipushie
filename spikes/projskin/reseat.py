"""reseat.py <head model> <skin model> <dst>: a re-seat on a new head of the SAME topology (same atlas): the head model's
base (shape, pose, its own skin.tone untouched only if the skin model has none) + the skin model's whole skin (stack, maps,
lips, brows, eyes, folds) and base.lashes; the references from the head model; then the crease / occlusion maps redone
for the new forms (recrease). LIGHT. Re-check the lid fold afterwards (the lid margin moves with the head)."""
import copy, sys, runpy
from hifipushie import blockin as bi, store
h, sk, dst = sys.argv[1:4]
s = copy.deepcopy(store.load(h)); t = store.load(sk)
s["skin"] = copy.deepcopy(t["skin"])
hd, th = s["base"].setdefault("head", {}), t["base"].get("head") or {}
if th.get("lid_fold") and not hd.get("lid_fold"):   # the lid's fold (GNM fold geometry) and the eye bag are skin-stage
    hd["lid_fold"] = copy.deepcopy(th["lid_fold"])  # tissue: carried over (re-check: the margin moves with the head)
if (th.get("shape") or {}).get("eye_bag"):
    hd["shape"] = {**(hd.get("shape") or {}), "eye_bag": copy.deepcopy(th["shape"]["eye_bag"])}
if "lashes" in t["base"]:
    s["base"]["lashes"] = copy.deepcopy(t["base"]["lashes"])
rj = copy.deepcopy(bi._refs(h))
if rj.get("blockin"):
    rj["blockin"] = {**rj["blockin"], "root": dst}
bi._save(dst, s, f"skin of {sk} re-seated on {h}", rj)
sys.argv = ["recrease.py", dst]
runpy.run_path("spikes/projskin/recrease.py", run_name="__main__")
