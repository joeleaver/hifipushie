"""ear.py <model>: where the EAR really is against the hairline's idea of it: the scalp rays' radius by elevation at
az 80..110 (the ear is the bump), the hairline there, and the landmarks hair.hairline derives the ear's top from."""
import sys

import numpy as np

from hifipushie import hair, store

m = sys.argv[1]
spec = store.load(m)
sc = hair.scalp(m, spec)
g = hair.groom_params(spec)
line = hair.hairline(sc, g)
print("brow_outer z", round(float(sc.lm["lm_brow_outer.L"][2] - sc.C[2]), 4), "-> hairline's ear top", round(float(sc.lm["lm_brow_outer.L"][2] - sc.C[2]) + 0.004, 4))
els = np.arange(20, -45, -4.0)
for az in (70, 80, 90, 100, 110):
    P = sc.point(np.full(len(els), float(az)), els, 0.0) - sc.C
    r = np.hypot(P[:, 0], P[:, 1])
    print(f"az {az}: hairline el {line[az]:.0f} (z {float((sc.point(float(az), float(line[az]), 0.0) - sc.C)[2]):+.3f})  "
          + " ".join(f"{e:.0f}:{z * 100:+.1f}/{rr * 100:.1f}" for e, z, rr in zip(els, P[:, 2], r)))
print("(el : z cm / horizontal radius cm; the ear = where the radius jumps out)")
