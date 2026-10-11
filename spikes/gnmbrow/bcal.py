"""bcal.py <model> <render tag> [<model> <tag> ...]: the brow band READ on a fitted-camera render (shot.py's s_<tag>.png,
at the photo's own columns) against blockin_brows.model_band's prediction for that model's spec (the geometry the fit
uses), and against the photo's band. mm at the model; + = lower (toward the eye)."""
import json
import sys

import numpy as np
from PIL import Image

import bm
from hifipushie import blockin_brows as bb

bx = json.load(open(bm.G + "/box.json"))
for i in range(1, len(sys.argv), 2):
    name, tag = sys.argv[i], sys.argv[i + 1]
    q = bb._inputs(name)
    P, mm = q["P"], q["mm"]
    ex, ey = bb._frame(P)
    pb = bb.band(q["img"], P, mm)
    rb = bb.band(Image.open(f"{bm.G}/s_{tag}.png").convert("RGB"), P, mm, scale=bx["K"], origin=bx["box"][:2])
    hb = ((q["spec"].get("skin") or {}).get("hair") or {}).get("brows") or {}
    th = float(hb.get("thickness", bb.default_thickness(q["spec"])))
    mb = bb.model_band(q["J"], q["V"], q["cam"], hb, th, [p["xs"] for p in pb], ex, ey)
    f = lambda a: np.round(np.asarray(a, float), 2).tolist()  # noqa: E731
    print(name, tag, "mm/px", round(mm, 4), "EDGE", bb.EDGE)
    for s, side in enumerate(("right", "left")):
        r, m, p = rb[s], mb[s], pb[s]
        print(f"  {side}: render contrast {f(r['contrast'])}  photo contrast {f(p['contrast'])}")
        print(f"    mid   render - predicted {f(((0.5 * (r['low'] + r['top'])) - m['mid']) * mm)}")
        print(f"    thick render {f((r['low'] - r['top']) * mm)}  predicted {f((m['low'] - m['top']) * mm)}  photo {f((p['low'] - p['top']) * mm)}")
        print(f"    low   render - photo {f((r['low'] - p['low']) * mm)}")
        print(f"    mid   render - photo {f((0.5 * (r['low'] + r['top']) - 0.5 * (p['low'] + p['top'])) * mm)}")
    e = bb.errors(pb, rb and [{"low": r["low"], "mid": 0.5 * (r["low"] + r["top"]), "top": r["top"]} for r in rb], mm)
    print("  RENDER vs PHOTO:", bb._json(e))
    e2 = bb.errors(pb, mb, mm)
    print("  PREDICTED vs PHOTO:", bb._json(e2), flush=True)
