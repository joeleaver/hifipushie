import sys
import numpy as np
from hifipushie import rig_audit
g = rig_audit.read_glb(sys.argv[1])
names = [b["name"].split(":")[-1] for b in g["bones"]]
M = g["meshes"]
m = M[next(k for k in M if k.endswith("body"))]
V = m["V"]; top = max(mm["V"][:, 2].max() for mm in M.values())
D = np.zeros((len(V), len(names)))
for k in range(4):
    np.add.at(D, (np.arange(len(V)), m["J"][:, k]), m["W"][:, k])
hi = names.index("Head")
print(sys.argv[1].split("/")[-1], "top", round(top, 3))
for lo in np.arange(0.20, 0.75, 0.05):
    s = (V[:, 2] < top - lo) & (V[:, 2] >= top - lo - 0.05) & (np.abs(V[:, 0]) < 0.16)
    if s.any():
        print(f"  {lo*100:.0f}-{lo*100+5:.0f} cm under the top: {int(s.sum()):5d} v, Head weight mean {D[s, hi].mean():.2f} max {D[s, hi].max():.2f}, share with Head > 0.5: {(D[s, hi] > 0.5).mean():.2f}")
