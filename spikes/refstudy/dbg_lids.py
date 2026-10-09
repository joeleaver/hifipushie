"""Which edges make humanfit.integrity call a plain sigma-1 identity BROKEN at the lids? Their lengths before / after."""
import copy
import json

import numpy as np

import rs
import subjects
from hifipushie import humanfit, onemesh, store

sp0 = json.load(open(store.HOME / "lk_garrett" / "history" / "0001.json"))
b0 = copy.deepcopy(sp0.get("spec", sp0))["base"]
g = rs.gnm()
st0 = humanfit.state(b0)
for name in subjects.names()[:10]:
    sub = subjects.load(name)
    if sub["c"] is None:
        continue
    bt = copy.deepcopy(b0)
    bt["head"]["identity"] = {g["names"][g["comps"][i]]: round(float(v), 4) for i, v in enumerate(sub["c"])}
    st = humanfit.state(bt)
    it = humanfit.integrity(bt, st, st0)
    print(name, humanfit.verdict(it).split("\n")[0][:230])
    P, P0 = np.asarray(st["tpl"]["P"]), np.asarray(st0["tpl"]["P"])
    tpl = st["tpl"]
    reg = humanfit._regions(tpl)
    Lf, Sf = np.asarray(tpl["L"]), np.asarray(tpl["S"])
    s_ = np.r_[0, np.cumsum(Sf)[:-1]]
    F = np.stack([Lf[s_], Lf[s_ + 1], Lf[s_ + 2], Lf[s_ + Sf - 1]], 1)
    E = np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 3]], F[:, [3, 0]]]
    sel = reg["lids"][E].all(1)
    l1 = np.linalg.norm(P[E[:, 0]] - P[E[:, 1]], axis=1)[sel] * 1000
    l0 = np.linalg.norm(P0[E[:, 0]] - P0[E[:, 1]], axis=1)[sel] * 1000
    r = l1 / np.maximum(l0, 1e-6)
    bad = (r > 3) | (r < 0.25)
    if bad.any():
        print(f"   {int(bad.sum())} lid edges past x3 / x0.25: before {np.round(np.sort(l0[bad])[[0, len(l0[bad]) // 2, -1]], 2)} mm, "
              f"after {np.round(np.sort(l1[bad])[[0, len(l1[bad]) // 2, -1]], 2)} mm; of them with BOTH lengths under 1 mm: {int((np.maximum(l0, l1)[bad] < 1.0).sum())}, "
              f"under 1.5 mm: {int((np.maximum(l0, l1)[bad] < 1.5).sum())}")
