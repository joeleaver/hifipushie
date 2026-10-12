"""tonegrid.py <L> <a> <b>: which (melanin, blood, undertone) triples make a base tone within 1.0 Lab of a target, and
the constants behind the sliders."""
import sys
import numpy as np
from hifipushie import skin as sk, skin_read as sr

tgt = np.array([float(x) for x in sys.argv[1:4]])
print("FITZPATRICK", sk.FITZPATRICK, "BLOOD", sk.BLOOD, "MELANIN", sk.MELANIN, "FAIR", sk.FAIR_CAROTENE, sk.FAIR_TO)
L = lambda t: sr.lab(sr._lin(np.asarray(sk.tone_rgb(t), float)))
print("prior F1-ish (0.02, 0.25, 0.15):", L({"melanin": 0.02, "blood": 0.25, "undertone": 0.15}).round(2))
rows = []
for m in np.linspace(0, 0.3, 16):
    for b in np.linspace(0, 0.6, 13):
        for u in np.linspace(-0.6, 0.8, 15):
            l = L({"melanin": float(m), "blood": float(b), "undertone": float(u)})
            rows.append((float(np.linalg.norm(l - tgt)), m, b, u, *l))
rows.sort()
for r in rows[:25]:
    print("  d %.2f  melanin %.3f blood %.3f undertone %+.2f  Lab %.1f %.1f %.1f" % r)
