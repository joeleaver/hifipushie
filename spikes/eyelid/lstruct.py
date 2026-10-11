"""struct.py <label>=<identity source> ...: the upper lid's structure on GNM's RAW mesh, ring by ring
(lidstruct.structure), mean of the columns u = -4, 0, +4 of the left eye; + the orbit's gnm_mm measures
(eyes_forward, brows_over_eyes, pupils_apart; mm). Sources as lidstruct.ident."""
import sys

import numpy as np

import lidstruct as ls
from hifipushie import gnm_controls as gc, gnm_mm

MM = ("eyes_forward", "brows_over_eyes", "pupils_apart")
print(f"{'':12s}" + " ".join(f"{k[:9]:>9s}" for k in ls.KEYS) + " | " + " ".join(f"{k[:12]:>12s}" for k in MM) + " | stand-off rings 0..11 at the pupil")
for a in sys.argv[1:]:
    lab, src = a.split("=", 1)
    c = ls.ident(src)
    q = ls.mean_structure(c)
    rd = gnm_mm.readers(gc.vertices(c))
    print(f"{lab:12s}" + " ".join(f"{q[k]:9.2f}" for k in ls.KEYS) + " | " + " ".join(f"{float(rd[k]) if k in rd else float('nan'):12.2f}" for k in MM)
          + " | " + " ".join(f"{x:5.2f}" for x in q["s"]))
