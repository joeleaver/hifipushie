import sys
import numpy as np
from scipy.spatial import cKDTree
from hifipushie import rig_audit
g = rig_audit.read_glb(sys.argv[1])
names = [b["name"].split(":")[-1] for b in g["bones"]]
M = g["meshes"]
H, Bd = M[next(k for k in M if k.endswith("head"))], M[next(k for k in M if k.endswith("body"))]
d, j = cKDTree(Bd["V"]).query(H["V"])
hi = np.flatnonzero(d < 1e-6)
X = H["V"][hi]
c = X.mean(0)
o = np.argsort(np.arctan2(X[:, 0] - c[0], -(X[:, 1] - c[1])))
D = np.zeros((len(hi), len(names)))
for k in range(4):
    np.add.at(D, (np.arange(len(hi)), H["J"][hi, k]), H["W"][hi, k])
D = D[o]
for k in np.argsort(-D.sum(0))[:6]:
    print(f"{names[k]:16s} mean {D[:,k].mean():.3f} min {D[:,k].min():.3f} max {D[:,k].max():.3f} largest neighbour step {np.abs(np.diff(D[:,k])).max():.3f}")
k = names.index("Neck"); print("Neck round the ring:", np.round(D[::3, k], 2).tolist())
k = names.index("Head"); print("Head round the ring:", np.round(D[::3, k], 2).tolist())
# rows of the body below: weights by height band
z = Bd["V"][:, 2]; zr = X[:, 2].mean()
Db = np.zeros((len(z), len(names)))
for k in range(4):
    np.add.at(Db, (np.arange(len(z)), Bd["J"][:, k]), Bd["W"][:, k])
near = np.linalg.norm(Bd["V"][:, :2] - c[:2], axis=1) < 0.09
for lo in (0.0, -0.02, -0.04, -0.06):
    m = near & (z < zr + lo + 0.02) & (z >= zr + lo)
    print(f"body band {lo*1000:+.0f}..{lo*1000+20:+.0f} mm of the ring's mean height ({m.sum()} v):", {names[k]: (round(Db[m, k].mean(), 2), round(Db[m, k].std(), 2)) for k in np.argsort(-Db[m].sum(0))[:5]})
