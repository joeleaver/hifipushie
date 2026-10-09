"""neck3d.py <model>: the model's neck in 3D: chin (lm 8), the body joints round the neck and shoulders, and the
measures that name the neck / head / stature (m)."""
import sys

import numpy as np

from hifipushie import humanfit, store

b = store.load(sys.argv[1])["base"]
st = humanfit.state(b)
J = st["tpl"]["J"]
L = np.asarray(st["L"])
print("chin (lm 8) z", round(float(L[8][2]), 4), "eyes z", round(float(0.5 * (L[36][2] + L[45][2])), 4))
for k, v in J.items():
    if any(w in k for w in ("neck", "clav", "head", "spine", "chest", "shoulder")):
        print(k, np.round(np.asarray(v, float), 4).tolist())
m = st["measures"]
print({k: round(float(v), 1) for k, v in m.items() if any(w in k for w in ("neck", "head", "stature", "biacrom"))})
