"""occfit.py <src with a stack> <eyecmp dir> <dst> [strength=<start>]: the baked occlusion's STRENGTH as the crease reads
(eyecmp.json: lidfold.read_lid's fold-line darkness on our EEVEE render vs the photo, same frame): strength x the median of
photo / ours over the columns both read (x 0.5 .. 2.5), at most 1 (laid twice it drew black cracks round an older test head's eyes). Without an eyecmp dir ("-"): sets strength=. LIGHT."""
import copy, json, sys
import numpy as np
from hifipushie import blockin as bi, store
src, d, dst = sys.argv[1:4]
kw = dict(a.split("=", 1) for a in sys.argv[4:])
s = copy.deepcopy(store.load(src))
st = s["skin"]["stack"]
key = kw.get("key", "crease_strength" if st.get("crease") else "occlusion_strength")   # (the crease line by default: the fold-line darkness is ITS measure)
k0 = float(kw.get("strength", st.get(key, 0.5 if key == "crease_strength" else 1.0)))
if d != "-":
    r = list(json.load(open(f"{d}/eyecmp.json")).values())[0]
    if key == "occlusion_strength":   # the orbit's darkness against the cheek (eyecmp "orbit"): the bake's job
        rat = [p_ / o_ for p_, o_ in zip(r.get("photo_orbit") or [], r.get("ours_orbit") or []) if p_ is not None and o_ is not None and o_ > 0.01 and p_ > 0]
    else:
        rat = [ph["dark"] / ou["dark"] for e in (0, 1) for ph, ou in zip(r["photo"][e], r["ours"][e])
               if ph["tps"] is not None and ou["tps"] is not None and abs(ph["tps"] - ou["tps"]) <= 2.5 and ph["dark"] > 0.05 and ou["dark"] > 0.02]
    k = float(np.clip(np.median(rat), 0.5, 2.5)) if rat else 1.0
    print(f"fold-line darkness photo / ours: {np.round(rat, 2).tolist()} -> x {k:.2f}")
else:
    k = 1.0
st[key] = round(float(np.clip(k0 * k, 0.0, 1.0)), 2)
print(f"{key} {k0} -> {st[key]}")
rj = copy.deepcopy(bi._refs(src))
if rj.get("blockin"):
    rj["blockin"] = {**rj["blockin"], "root": dst}
bi._save(dst, s, f"{key} {st[key]} (occfit)", rj)
