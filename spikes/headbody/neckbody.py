"""neckbody.py <model>: the body's own neck girth (at the head's narrowest ring) by base.body weight / muscle."""
import sys
import numpy as np
from hifipushie import onemesh, store, headfit
b = store.load(sys.argv[1])["base"]
p0 = onemesh.body_params(b)
lp = onemesh._ring_loop(19)
for w in (0.15, 0.25, 0.35, 0.45, 0.5, 0.6):
    row = []
    for mu in (0.4, 0.5, 0.65):
        B = onemesh.bound({**p0, "weight": w, "muscle": mu}, 1.0)["B"]
        row.append(f"muscle {mu}: {1e3*np.linalg.norm(B[lp]-np.roll(B[lp],-1,0),axis=1).sum():.0f}")
    print(f"weight {w}: " + "  ".join(row))
