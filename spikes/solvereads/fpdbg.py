"""fpdbg.py <measure>...: a measure's footprint (solve_report.footprint): vertex count, the largest weights, where."""
import sys
import numpy as np
from hifipushie import solve_report as sr, gnm_mm
fp = sr.footprint()
T = gnm_mm._space()["T"] * 1000
for n in sys.argv[1:] or sr.rows()["names"]:
    ids, g = fp[n]
    o = np.argsort(-np.abs(g).max(1))[:6]
    print(f"{n}: {len(ids)} vertices, sum |g| {np.abs(g).sum(0).round(2)}, net {g.sum(0).round(2)}")
    for k in o:
        p = T[ids[k]] if ids[k] >= 0 else [0, 0, 0]
        print(f"    v {ids[k]:6d} at ({p[0]:+6.1f} {p[1]:+6.1f} {p[2]:+6.1f})  g {g[k].round(3)}")
