"""sizeof.py <start model> <model> ...: each model's face SIZE against the start head's (similarity fit over the hockey
mask, %), and the chin / jaw measures at the model's own size (GNM mm, from GNM's mean; macros sd)."""
import sys
import numpy as np
from hifipushie import blockin as bi, solve_report as sr, store
import errmap
c0 = bi.identity(store.load(sys.argv[1]))
rw = sr.rows()
N = ("chin_width", "jaw_width", "gonial_width", "jaw_square", "jaw_angle", "gonial_height", "chin_length", "chin_forward", "under_chin", "cheekbone_width", "mouth_width")
print(f"{'model':12s} size%   |c|  max | " + " ".join(f"{n[:9]:>9s}" for n in N))
for m in sys.argv[1:]:
    c = bi.identity(store.load(m))
    s = errmap.rms(c0, c)["scale"]          # the scale that lays the START on this head = this head's size / the start's
    print(f"{m:12s} {100 * (s - 1):+5.1f} {np.linalg.norm(c):5.1f} {np.abs(c).max():4.2f} | " + " ".join(f"{float(rw['R'][rw['names'].index(n)] @ c):+9.1f}" for n in N))
