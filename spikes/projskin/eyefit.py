"""eyefit.py <src with lid_fold> <eyecmp dir> <dst>: one step of the FOLD AS IT READS against the photo (eyecmp.json: the
same lid reader on our render and the picture): per side and column the overhang moves by our visible platform minus the
photo's (ours smaller = too much drape), the slit depth by the photo's fold-line darkness over ours (x 0.7 .. 2). LIGHT."""
import copy, json, sys
import numpy as np
from hifipushie import blockin as bi, store
src, d, dst = sys.argv[1:4]
r = list(json.load(open(f"{d}/eyecmp.json")).values())[0]
s = copy.deepcopy(store.load(src))
lf = s["base"]["head"]["lid_fold"]
ratios = []
for e, key in ((0, "R"), (1, "L")):
    ph, ou = r["photo"][e], r["ours"][e]
    c = lf.setdefault(key, {})
    ov = list(c.get("overhang", lf.get("overhang", [0.6] * 3)))
    ov = ov if isinstance(ov, list) else [float(ov)] * 3
    new = []
    for i in range(3):
        tp, to = ph[i]["tps"], ou[i]["tps"]
        # (a column whose two reads differ by more than 2.5 mm is a MISREAD, not a fold to fix: a test head's right eye
        # read 9.2 mm on our render, the reader on another line, and the step hung a 4 mm hood on her; a step is at most 1 mm)
        ok_ = tp is not None and to is not None and abs(to - tp) <= 2.5
        new.append(round(float(np.clip(ov[i] + np.clip(to - tp, -1.0, 1.0), 0.0, 4.0)), 2) if ok_ else ov[i])
        if ph[i]["dark"] > 0.05 and ou[i]["dark"] > 0.02:
            ratios.append(ph[i]["dark"] / ou[i]["dark"])
    print(f"eye {key}: overhang {ov} -> {new}  (platform photo {[c_['tps'] for c_ in ph]}, ours {[c_['tps'] for c_ in ou]})")
    c["overhang"] = new
import os
if os.environ.get("EYEFIT_DEPTH", "0") == "1":   # (off: a deeper slit did not darken the line; the baked occlusion does: occfit.py)
    k = float(np.clip(np.median(ratios), 0.7, 2.0)) if ratios else 1.0
    lf["depth"] = round(float(lf.get("depth", 1.0)) * k, 2)
    print(f"depth x {k:.2f} -> {lf['depth']} (fold-line darkness photo / ours, median of {len(ratios)})")
rj = copy.deepcopy(bi._refs(src))
if rj.get("blockin"):
    rj["blockin"] = {**rj["blockin"], "root": dst}
bi._save(dst, s, "lid fold: one eyefit step (platform + darkness as they read against the photo)", rj)
