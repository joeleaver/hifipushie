"""ansur_check.py <atlas npz> <ansur dir>: GNM's couplings against real people's. ANSUR II (US Army 2012, public
domain: 4082 men, 1986 women) head and face measures, correlated WITHIN each sex, against the same measures on GNM's
sampled heads (absolute mm: humanmacro's interocular-unit macros x the head's interocular), plus the male - female
mean differences (in each measure's pooled within-sex sd): the sex axis' share these measures can give."""
import csv
import sys
from pathlib import Path

import numpy as np

z = np.load(sys.argv[1], allow_pickle=True)
A, names = z["A"], [str(x) for x in z["names"]]
col = lambda k: A[:, names.index(k)]  # noqa: E731
io = col("head_size")  # mm
gnm = {"bizygomatic": col("cheekbone_width") * io, "face_height": col("face_length") * io,
       "head_breadth": col("cranium_width") * io, "head_length": col("head_depth") * io, "interpupillary": io,
       "ear_length": col("ear_size") * io}
ansur_cols = {"bizygomatic": "bizygomaticbreadth", "face_height": "mentonsellionlength", "head_breadth": "headbreadth",
              "head_length": "headlength", "interpupillary": "interpupillarybreadth", "ear_length": "earlength"}


def load(sex):
    p = Path(sys.argv[2]) / f"ANSUR_II_{sex}_Public.csv"
    with open(p, newline="", encoding="latin-1") as f:
        r = csv.DictReader(f)
        rows = list(r)
    low = {k.lower(): k for k in rows[0]}
    return {m: np.array([float(x[low[c]]) for x in rows]) for m, c in ansur_cols.items()}


men, women = load("MALE"), load("FEMALE")
keys = list(ansur_cols)
print("measure means (mm): men | women | GNM")
for k in keys:
    print(f"  {k:15s} {men[k].mean():7.1f} | {women[k].mean():7.1f} | {np.nanmean(gnm[k]):7.1f}")
pooled = {k: np.r_[men[k], women[k]] for k in keys}
print("\ncorrelations: ANSUR men | ANSUR women | ANSUR pooled | GNM (pooled; GNM has no sex)")
for i, a in enumerate(keys):
    for b in keys[i + 1:]:
        rm = np.corrcoef(men[a], men[b])[0, 1]
        rw = np.corrcoef(women[a], women[b])[0, 1]
        ok = np.isfinite(gnm[a]) & np.isfinite(gnm[b])
        rg = np.corrcoef(gnm[a][ok], gnm[b][ok])[0, 1]
        rp = np.corrcoef(pooled[a], pooled[b])[0, 1]
        flag = "  <- GNM differs from within-sex" if abs(rg - 0.5 * (rm + rw)) > 0.25 else ""
        print(f"  {a:15s} ~ {b:15s} {rm:+.2f} | {rw:+.2f} | {rp:+.2f} | {rg:+.2f}{flag}")
print("\nmale - female (mean difference / pooled within-sex sd):")
for k in keys:
    sdp = np.sqrt(0.5 * (men[k].var() + women[k].var()))
    print(f"  {k:15s} {(men[k].mean() - women[k].mean()) / sdp:+.2f}  ({men[k].mean() - women[k].mean():+.1f} mm)")
