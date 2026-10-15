"""necktone.py <src> <dst>: the BODY's skin tone (skin.tone, everything the head's stack does not cover) fitted to the
stack's own colour at the jaw / neck (the recomposed stack's median over the jaw-side texels): the head-body join read as a
soft band (head stack darker than the body's tone). LIGHT."""
import copy, sys
import numpy as np
from PIL import Image
from scipy.optimize import minimize
from hifipushie import blockin as bi, skin, skin_project as sp, store
src, dst = sys.argv[1:3]
s = copy.deepcopy(store.load(src))
at = sp.atlas(s["base"])
rec = sp._lin(np.asarray(Image.open(store._dir(src) / "skin_layers" / "recomposed.png").convert("RGB"), float) / 255.0)[at["ii"], at["jj"]]
regs = sp.region_masks(at)
q = regs["jaw_side"] | regs.get("chin", np.zeros(len(rec), bool))
want = sp.lab(np.median(rec[q], 0)[None])[0]
t0 = skin.params(s)["tone"]
def lab_of(x):
    t = {**t0, "melanin": float(np.clip(x[0], 0, 1)), "blood": float(np.clip(x[1], 0, 1)), "undertone": float(np.clip(x[2], -1, 1))}
    return sp.lab(sp._lin(np.asarray(skin.tone_rgb(t), float))[None])[0], t
f = lambda x: float(np.sum((lab_of(x)[0] - want) ** 2))
best = min((minimize(f, [m_, b_, u_], method="Nelder-Mead") for m_ in (0.05, 0.3) for b_ in (0.1, 0.5) for u_ in (-0.5, 0.3)), key=lambda r: r.fun)
L1, t1 = lab_of(best.x)
print("jaw stack Lab", np.round(want, 1).tolist(), "tone before Lab", np.round(lab_of([t0["melanin"], t0["blood"], t0["undertone"]])[0], 1).tolist(), "after", np.round(L1, 1).tolist())
s["skin"]["tone"] = {**(s["skin"].get("tone") or {}), **{k: round(float(t1[k]), 4) for k in ("melanin", "blood", "undertone")}}
rj = copy.deepcopy(bi._refs(src))
if rj.get("blockin"):
    rj["blockin"] = {**rj["blockin"], "root": dst}
bi._save(dst, s, "body tone fitted to the stack at the jaw (necktone)", rj)
