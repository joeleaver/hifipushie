"""MakeHuman bodies with the measured growth vs the references."""
import sys
import numpy as np
from hifipushie import makehuman, anthro, headfit

rows = []
old = "old" in sys.argv
for sex, sx in ((1.0, "m"), (0.0, "f")):
    for age in (0.5, 1, 2, 3, 5, 7, 9, 11, 13, 16, 19, 22, 25):
        p = {"age": age, "sex": sex}
        if old:
            p["growth"] = False
        b = makehuman.body(p)
        P = np.asarray(b["P"], float)
        chin = P[headfit.table()["lm68"][8], 2]
        m = anthro.measure(P, b["J"], chin)
        rows.append((f"{sx} {age}", age, sex, m))
print(anthro.table(rows))
