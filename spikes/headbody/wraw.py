import sys
import numpy as np
from hifipushie import rig_audit
g = rig_audit.read_glb(sys.argv[1])
names = [b["name"].split(":")[-1] for b in g["bones"]]
for k, m in g["meshes"].items():
    if not k.endswith("body"): continue
    V = m["V"]; top = 1.771
    s = np.flatnonzero((V[:, 2] < top - 0.40) & (V[:, 2] >= top - 0.45) & (np.abs(V[:, 0]) < 0.16))
    print(k, len(V), "J shape", m["J"].shape, m["J"].dtype, "W", m["W"].shape, "J range", m["J"].min(), m["J"].max())
    for i in s[:8]:
        print(np.round(V[i], 3), m["J"][i], np.round(m["W"][i], 3), [names[j] for j in m["J"][i]])
