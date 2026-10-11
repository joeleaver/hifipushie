"""mmtest.py: each mm: move's cost (|dc| per mm), the face's skin moved (rms mm), and the macros it drags."""
import numpy as np

import drv
from hifipushie import blockin as bi, gnm_mm, humanmacro as hm

Z = drv.gcm.zones()
z0 = hm.read(np.zeros(hm.K))
for n in gnm_mm.NAMES:
    d = bi.direction("mm:" + n)
    D = np.tensordot(d, drv.IBH, 1) * 1000
    fr = np.sqrt((D[Z["face"]] ** 2).sum(1).mean())
    r = gnm_mm.readers(drv.gnmc.TPL + np.tensordot(d, drv.IBH, 1))
    r0 = gnm_mm.readers(drv.gnmc.TPL)
    z = hm.read(d[:hm.K])
    zm = sorted(((k, z[k] - z0[k]) for k in z), key=lambda t: -abs(t[1]))[:3]
    print(f"mm:{n}: |dc| {np.linalg.norm(d):.2f} per mm, face rms {fr:.2f} mm, self {r[n] - r0[n]:+.2f}, macros "
          + ", ".join(f"{k} {v:+.2f}" for k, v in zm))
