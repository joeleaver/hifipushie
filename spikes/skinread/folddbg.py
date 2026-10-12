"""folddbg.py <model>: the fold layers' masks at the front view's pixels (max, mean where on), and the landmarks'
heights round the eye (where lid_fold's nominal path sits over the lid margin)."""
import sys
import numpy as np
from hifipushie import skin_read as sr, store, paint, skin, skin_folds as sf

m = sys.argv[1]
f = sr.capture(m, views=[0], render=False, log=lambda s: None)[0]
sk = f["skin"]
st = sr.stage_spec(store.load(m))
alb = sr.Albedo(st, f["X"][sk], f["n"][sk])
ms = {}
A = alb(masks=ms)
for k, v in ms.items():
    if "fold" in k:
        print(k, "max", v.max().round(3), "px > 0.1:", int((v > 0.1).sum()))
for n, ly in paint.layers(st).items():
    if "fold" in n:
        print(n, {k: (v if k != "mask" else "...") for k, v in ly.items()}, ly.get("mask"))
J = skin._joints(st)
io = skin.interocular(J)
for k in ("lm_eye_inner.L", "lm_eye_outer.L", "lm_lid_upper.L", "lm_lid_lower.L", "lm_lid_upper_in.L", "lm_lid_upper_out.L", "lm_brow_mid.L", "eye.L", "eye_front.L"):
    if k in J:
        print(k, (J[k] * 1000).round(1))
print("io mm", round(io * 1000, 1))
ps = sf.paths(st, "body", J, None, names=["lid_fold", "tear_trough"])
for k, q in ps.items():
    print(k, "z mm", (q["P"][[0, len(q["P"]) // 2, -1], 2] * 1000).round(1), "y", (q["P"][[0, len(q["P"]) // 2, -1], 1] * 1000).round(1))
