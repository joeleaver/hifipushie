"""fronttrace.py <model> <out.json> [regions=front,top] [patch.json]: the photo's hair OUTLINE traced through the fitted
cameras, as stand-off samples on the scalp, beside ours (screen's flat raster of the model's groom).

Per fitted view (0 front, 1 three-quarter, 2 profile) and per outline ray (hair_read.outline_rays, 1 deg, the rays
where the hair meets the backdrop): the skull edge's scalp point G (onto_scalp, as screen.standoff) and the hair's
stand-off there (mm, in the image plane at the head centre's scale). Same rays on the photo and on ours, so each
sample pairs (az, el) with h_photo and h_ours. Written for groom.loose.trace (hair_loose: locks over the traced area
are held at the traced height) and printed as the profile curve by ray angle.
"""
import json
import sys

import numpy as np

from hifipushie import hair, hair_read as hr, hair_strands as hs, store
from screen import Flat


def samples(sc, f):
    hn = hr.hairness(f["image"], f["hair"], f["bg"], f["mm"])
    o = hr.outline_rays(f["skull"], hn["solid"], hn["a"], f["bg"], f["c"], f["mm"])
    th = np.radians(o["ang"])
    uv = np.stack([f["c"][0] + np.sin(th) * o["skull_px"], f["c"][1] - np.cos(th) * o["skull_px"]], 1)
    _, hit, G = hr.onto_scalp(sc, f["cam"], uv, step=0.0015)
    az, el, _ = sc.coords(G)
    return {"ang": o["ang"], "meets": o["meets"] & hit, "h": o["standoff_mm"], "az": az, "el": el,
            "reg": hr.region_name(az, el)}


def main(m, out, regions=("front", "top"), patch=None):
    import copy
    from laygeo import merge
    spec = store.load(m)
    if patch:
        spec = copy.deepcopy(spec)
        merge(spec["hair"], json.load(open(patch)))
    sc = hair.scalp(m, spec)
    sd = hair.job(m, spec)["strands"]
    fl = Flat(m, spec, hs.strands_of_model(sd), sc, sd)
    fp = {f["i"]: f for f in hr.frames(m, spec)}
    rows = []
    for ci in (0, 1, 2):
        sp, so = samples(sc, fp[ci]), samples(sc, fl.frame(ci))
        k = sp["meets"] & np.isin(sp["reg"], regions)
        print(f"view {ci}: {k.sum()} photo rays in {regions}")
        for j in np.nonzero(k)[0]:
            ho = float(so["h"][j]) if so["meets"][j] else None
            rows.append({"view": ci, "ang": float(sp["ang"][j]), "az": round(float(sp["az"][j]), 2),
                         "el": round(float(sp["el"][j]), 2), "reg": str(sp["reg"][j]),
                         "h_photo": round(float(sp["h"][j]), 2), "h_ours": None if ho is None else round(ho, 2)})
        for j in np.nonzero(k)[0][::4]:
            r = rows[-1] if False else None
            ho = so["h"][j] if so["meets"][j] else np.nan
            print(f"  v{ci} ang {sp['ang'][j]:+6.0f} az {sp['az'][j]:6.1f} el {sp['el'][j]:5.1f} {sp['reg'][j]:6s} "
                  f"photo {sp['h'][j]:5.1f} ours {ho:5.1f}")
    for r_ in regions:
        hp = [r["h_photo"] for r in rows if r["reg"] == r_]
        ho = [r["h_ours"] for r in rows if r["reg"] == r_ and r["h_ours"] is not None]
        if hp:
            print(f"region {r_}: photo median {np.median(hp):.1f} (n {len(hp)}) ours median "
                  f"{np.median(ho) if ho else float('nan'):.1f} (n {len(ho)})")
    json.dump({"model": m, "regions": list(regions), "samples": rows}, open(out, "w"), indent=0)
    print("WROTE", out, len(rows))


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if "=" not in x]
    kw = dict(x.split("=", 1) for x in sys.argv[1:] if "=" in x)
    main(a[0], a[1], tuple(kw.get("regions", "front,top").split(",")), a[2] if len(a) > 2 else None)
