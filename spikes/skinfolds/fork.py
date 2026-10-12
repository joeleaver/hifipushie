"""fork.py <src> <dst> [skin=<json file>] [folds=<json>]: a block-in fork (references and cameras come along), optionally
with another skin / other folds. Never onto an accepted model (a1, sr_*)."""
import json, os, sys
from hifipushie import blockin as bi, store
src, dst = sys.argv[1:3]
assert dst.startswith(("sf_", "_sf")), dst
kw = dict(a.split("=", 1) for a in sys.argv[3:])
bi.fork(src, dst, replace=True)
sp = store.load(dst)
if "skin" in kw:
    sp["skin"] = json.load(open(kw["skin"]))
if "folds" in kw:
    sp["skin"] = {k: v for k, v in sp["skin"].items() if k != "folds"}
    if kw["folds"]:
        sp["skin"]["folds"] = json.load(open(kw["folds"])) if os.path.exists(kw["folds"]) else json.loads(kw["folds"])
store.save(dst, sp, f"skinfolds: fork of {src}")
print(dst, json.dumps(sp["skin"].get("folds")))
