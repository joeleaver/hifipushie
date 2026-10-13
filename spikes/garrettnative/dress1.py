"""dress1.py <solved head> <out> [rounds=2]: the SKIN step. A block-in fork of the solved head (the source is never
written), skin.eyes.pupil 0.33 (GNM's rest pupil 0.50 is a dim-room pupil) and skin.eyes.canthus 0.8 (the lateral
corner), then skin_from_reference (skin_read.apply: tone bounded by the stated tone, zones, lips, stubble, brows, the
folds checklist -> skin.folds as geometry). The whole report to $G/out/skin_<out>.txt."""
import json
import sys
import time

from hifipushie import blockin as bi, skin_read as sr, store

G = "/mnt/data/hifipushie/garrettnative/out"
src, out = sys.argv[1:3]
kw = dict(a.split("=", 1) for a in sys.argv[3:])
assert out.startswith("gn_"), out
bi.fork(src, out, replace=True)
sp = store.load(out)
e = sp["skin"].setdefault("eyes", {})
e.pop("iris_size", None)
e.update(pupil=0.33, canthus=0.8)
bi._save(out, sp, f"garrettnative dress1 from {src}: pupil 0.33, canthus 0.8", bi._refs(out))
t = time.time()
res = sr.apply(out, rounds=int(kw.get("rounds", 2)), log=lambda s: print(s) if "[measure]" not in str(s) else None)
open(f"{G}/skin_{out}.txt", "w").write(res["text"])
json.dump({"before": store.load(src).get("skin"), "after": res["skin"]}, open(f"{G}/skin_{out}.json", "w"), indent=1)
print(res["text"])
print(f"\n{time.time() - t:.0f} s")
