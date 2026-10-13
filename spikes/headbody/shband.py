import sys
import numpy as np
from hifipushie import rig_audit
g = rig_audit.read_glb(sys.argv[1])
m = g["meshes"][next(k for k in g["meshes"] if k.endswith("body"))]
V = m["V"]; top = V[:, 2].max()
T = m["targets"]
print(len(T), "targets; vertices", len(V))
for lo in np.arange(0.15, 0.8, 0.1):
    s = (V[:, 2] < top - lo) & (V[:, 2] >= top - lo - 0.1)
    worst = sorted(((float(np.linalg.norm(d[s], axis=1).max()), nm) for nm, d in T.items()), reverse=True)[:3]
    cnt = int((np.max([np.linalg.norm(d[s], axis=1) for d in T.values()], 0) >= 0.003).sum())
    print(f"  {lo*100:.0f}-{lo*100+10:.0f} cm under the top: {int(s.sum())} v; moved >= 3 mm by some shape: {cnt}; largest: {[(n, round(1e3*x, 1)) for x, n in worst]}")
