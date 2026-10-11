"""template.py: crease SHAPE templates for the eye step: the upper lid's sections at the inner third / pupil / outer third
(relative to the lid margin, (forward, up) mm at arclength 0.5 .. 8 mm), from GNM samples: "fold" = the mean of the
population's low + narrow + parallel creases (sep.py's 30 / 1200), "s376", "s540" (Joe's two). -> out/crease_templates.npz"""
import json
import numpy as np
import shapesolve as ss

G = "/mnt/data/hifipushie/gnmcrease/out/"
sel = []
for f in ("gnm_1", "ict_2"):
    S = json.loads(str(np.load(G + f"col_{f}.npz")["S"]))
    for i, s in enumerate(S):
        if s and s["h_mid"] < 3.2 and s["narrow_mean"] > 0.3 and s["h_spread"] < 1.5:
            sel.append(f"{f}:{i}")
print(len(sel), "in the fold cluster")
secs = []
for k in sel:
    import col
    c, e, _ = col.src(k)
    sec, cols = ss.sections(c, e, "gd_T12")
    if all(x is not None for x in sec):
        secs.append(np.stack(sec))
T = {"fold": np.mean(secs, 0), "fold_sd": np.std(secs, 0)}
for k in ("gnm_1:376", "gnm_1:540"):
    c, e, _ = col.src(k)
    T["s" + k.split(":")[1]] = np.stack(ss.sections(c, e, "gd_T12")[0])
np.savez(G + "crease_templates.npz", S=ss.S, members=np.array(sel), **T)
for k, v in T.items():
    print(k, v.shape, "pupil section (fwd, up) at 1, 2, 3, 4, 6, 8 mm:", v[1][[1, 3, 5, 7, 11, 15]].round(2).tolist())
