"""smoothfold.py <src> <dst>: the fold's crease made one smooth arc (gnm_fold.smooth_crease) KEEPING its heights: the
crease_by_angle points replaced by the fitted curve's values, crease columns by its values at -60 / 0 / 90; prints the
seated crease's roughness before / after (gnm_fold.crease_roughness: rms second difference, curvature sign changes) and a
WARNING over CREASE_ROUGH. LIGHT."""
import copy, sys
import numpy as np
from hifipushie import blockin as bi, gnm_fold as gf, store
CREASE_ROUGH = (0.08, 0)
SEATED_FLIPS = 2           # turning-direction flips allowed along the seated crease ring   # d2_rms mm, sign changes
src, dst = sys.argv[1:3]
s = copy.deepcopy(store.load(src))
lf = s["base"]["head"]["lid_fold"]
for key in ("R", "L"):
    c = lf.get(key) or {}
    cba = c.get("crease_by_angle")
    if not cba:
        continue
    a = np.asarray(cba, float); a = a[np.argsort(a[:, 0])]
    xs = np.linspace(a[0, 0], a[-1, 0], 24)
    before = gf.crease_roughness(np.interp(xs, a[:, 0], a[:, 1]))
    f = gf.smooth_crease(cba)
    after = gf.crease_roughness(f(xs))
    c["crease_by_angle"] = [[float(x), round(float(f(x)), 2)] for x in a[:, 0]]
    c["crease"] = [round(float(f(x)), 2) for x in (-60.0, 0.0, 90.0)]
    bad = after["d2_rms"] > CREASE_ROUGH[0] or after["sign_changes"] > CREASE_ROUGH[1]
    print(f"eye {key}: crease roughness before {before}, after {after}" + ("  WARNING: not one smooth arc" if bad else ""))
sr = gf.seated_roughness(gf.vertices() / 1000.0, lf)
for key, r in sr.items():
    print(f"eye {key}: SEATED crease line roughness {r}" + ("  WARNING: the seated crease wobbles" if r["sign_changes"] > SEATED_FLIPS else ""))
rj = copy.deepcopy(bi._refs(src))
if rj.get("blockin"):
    rj["blockin"] = {**rj["blockin"], "root": dst}
bi._save(dst, s, "lid fold crease as one smooth arc", rj)
