"""hipprof.py: per height in the hip band, the slab's x extent on the left side and its gaps (a woman, hips 0.5 / 1)."""
import numpy as np

from hifipushie import makehuman

for hv in (0.5, 1.0):
    b = makehuman.body({"sex": 0.0, "age": 30, "weight": 0.5, "hips": hv})
    P, J = np.asarray(b["P"]), b["J"]
    hx = abs(float(J["hip.L"][0]))
    print("hips", hv, "hip joint x", round(hx * 100, 1), "pelvis z", round(float(J["pelvis"][2]), 3))
    for z in np.linspace(float(J["pelvis"][2]) - 0.15, float(J["pelvis"][2]) + 0.05, 9):
        s = P[(np.abs(P[:, 2] - z) < 0.004) & (P[:, 0] > 0)][:, 0]
        x = np.sort(s)
        d = np.diff(x)
        gaps = [(round(x[i] * 100, 1), round(d[i] * 100, 1)) for i in np.flatnonzero(d > 0.006)]
        print("  z", round(z, 3), "max x", round(x.max() * 100, 1), "gaps (x cm, size cm)", gaps)
