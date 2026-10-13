"""roots.py <model> <prefix>: each lock's root (x off centre, y back from the scalp's front, z) in cm, + its height range."""
import sys
import numpy as np
from hifipushie import hair, store
m, pre = sys.argv[1], sys.argv[2]
sp = store.load(m)
sc = hair.scalp(m, sp)
y0 = -float(sc.r(0.0, 30.0)) * np.cos(np.radians(30.0))
for n, lk in sp["hair"]["locks"].items():
    if n.startswith(pre):
        P = hair.lock_world(sc, lk, lk["pts"]) - sc.C
        h = np.asarray(lk["pts"])[:, 2]
        print(f"{n:8s} x {100*P[0,0]:6.1f} y {100*(P[0,1]-y0):6.1f} z {100*P[0,2]:5.1f}  h {1000*h.max():5.1f}  w {lk['width']:.3f}")
