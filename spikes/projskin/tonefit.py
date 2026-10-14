"""tonefit.py <model with an atlas>: skin.tone (melanin, blood, undertone) fitted so the base tone's Lab = the de-lit atlas'
measured plain-skin median (grid + refine), saved. Prints before / after."""
import numpy as np
from PIL import Image
from hifipushie import skin, skin_project as sp, store, images
from scipy.optimize import minimize
import sys
m = sys.argv[1]
spec = store.load(m); at = sp.atlas(spec["base"])
pj = spec["skin"]["projection"]
alb = sp._lin(np.asarray(Image.open(images.id_path(pj["albedo"])).convert("RGB"), float) / 255.0)[at["ii"], at["jj"]]
cf = np.asarray(Image.open(images.id_path(pj["confidence"])).convert("RGB"), float)[..., 0][at["ii"], at["jj"]] / 255.0
q = sp._plain(at) & (cf > 0.6)
want = sp.lab(np.median(alb[q], 0)[None])[0]
t0 = skin.params(spec)["tone"]
def lab_of(x):
    t = {**t0, "melanin": float(np.clip(x[0], 0, 1)), "blood": float(np.clip(x[1], 0, 1)), "undertone": float(np.clip(x[2], -1, 1))}
    return sp.lab(sp._lin(np.asarray(skin.tone_rgb(t), float))[None])[0], t
f = lambda x: float(np.sum((lab_of(x)[0] - want) ** 2))
best = min((minimize(f, [m_, b_, u_], method="Nelder-Mead", options={"xatol": 1e-3, "fatol": 1e-4, "maxiter": 400}) for m_ in (0.1, 0.3) for b_ in (0.05, 0.3) for u_ in (-0.5, 0.3)), key=lambda r: r.fun)
L1, t1 = lab_of(best.x)
print(m, "atlas plain skin Lab", np.round(want, 1).tolist(), "| tone before", {k: round(float(t0[k]), 3) for k in ("melanin", "blood", "undertone")},
      "Lab", np.round(lab_of([t0["melanin"], t0["blood"], t0["undertone"]])[0], 1).tolist(), "| after", {k: round(float(t1[k]), 3) for k in ("melanin", "blood", "undertone")}, "Lab", np.round(L1, 1).tolist())
spec["skin"]["tone"] = {**(spec["skin"].get("tone") or {}), **{k: round(float(t1[k]), 4) for k in ("melanin", "blood", "undertone")}}
store.save(m, spec, "skin.tone fitted to the de-lit atlas' plain skin (tonefit)", checked=False)
