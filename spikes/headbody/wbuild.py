import sys
import numpy as np
from hifipushie import rig as rigmod, store, rig_audit
name = sys.argv[1]
spec = store.load(name)
bones = rigmod.rig_bones(spec)
names = [b["name"].split(":")[-1] for b in bones]
meta = store.build(name, 160)
z = np.load(meta["mesh"])
V, F = z["verts"].astype(float), z["faces"]
J, W = rigmod.skin_mesh(spec, bones, V, F, z["part"], [str(n) for n in z["part_names"]])
D = np.zeros((len(V), len(names)))
for k in range(4):
    np.add.at(D, (np.arange(len(V)), J[:, k]), W[:, k])
hi = names.index("Head"); top = V[:, 2].max()
bp = [str(n) for n in z["part_names"]].index("body")
for lo in np.arange(0.15, 0.6, 0.05):
    s = (z["part"] == bp) & (V[:, 2] < top - lo) & (V[:, 2] >= top - lo - 0.05) & (np.abs(V[:, 0]) < 0.16)
    print(f"  {lo*100:.0f}-{lo*100+5:.0f} cm under the top: {int(s.sum()):5d} v, Head mean {D[s, hi].mean():.2f} max {D[s, hi].max():.2f}; top bones {[(names[i], round(D[s, i].mean(), 2)) for i in np.argsort(-D[s].mean(0))[:3]]}")
if len(sys.argv) > 2:
    g = rig_audit.read_glb(sys.argv[2])
    print("GLB bones == rig bones:", [b["name"] for b in g["bones"]] == [b["name"] for b in bones], len(g["bones"]), len(bones), [b["name"].split(":")[-1] for b in g["bones"]][:8])
