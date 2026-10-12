"""holes.py <glb>: why the posed chest shows holes: the body mesh's open edges (faces dropped under garments), the
garment that should cover them, and how far each moves in the neck-bent pose."""
import sys
import numpy as np
from scipy.spatial import cKDTree
from hifipushie import rig as rigmod, rig_audit
g = rig_audit.read_glb(sys.argv[1])
bones, M = g["bones"], g["meshes"]
names = [b["name"] for b in bones]
P_ = rigmod.PREFIX
turns = {P_ + "Neck": ([1.0, 0, 0], -20.0), P_ + "Head": ([1.0, 0, 0], -15.0)}
print("meshes:", list(M))
body = M[next(k for k in M if k.endswith("body"))]
rep, F = rig_audit.weld(body["V"], body["F"])
e = np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1)
u, c = np.unique(e, axis=0, return_counts=True)
open_v = np.unique(u[c == 1])
Vo = body["V"][open_v]
chest = Vo[(Vo[:, 2] > 1.05) & (Vo[:, 2] < 1.33)]
print(f"body mesh: {len(open_v)} vertices on open edges; {len(chest)} of them between z 1.05 and 1.33 (chest): x {chest[:,0].min():.3f}..{chest[:,0].max():.3f}, z {chest[:,2].min():.3f}..{chest[:,2].max():.3f}")
for k, m in M.items():
    Pp = rigmod.pose(bones, m["V"], m["J"], m["W"], turns)
    mv = np.linalg.norm(Pp - m["V"], axis=1)
    sel = (m["V"][:, 2] > 1.05) & (m["V"][:, 2] < 1.33) & (np.abs(m["V"][:, 0]) < 0.2)
    D = np.zeros(len(names))
    np.add.at(D, m["J"][sel].ravel(), m["W"][sel].ravel())
    top = [(names[i].split(":")[-1], round(D[i] / max(D.sum(), 1e-9), 2)) for i in np.argsort(-D)[:4]]
    print(f"{k:8s} chest-height vertices {int(sel.sum()):5d}: moved by the neck-bent pose max {1e3*(mv[sel].max() if sel.any() else 0):.1f} mm, mean {1e3*(mv[sel].mean() if sel.any() else 0):.1f}; weights {top}")
if "top" in M or any(k.endswith("top") for k in M):
    t = M[next(k for k in M if k.endswith("top"))]
    d = cKDTree(t["V"]).query(chest)[0]
    print(f"open chest edges of the skin lie {1e3*np.median(d):.1f} mm (median) from the garment 'top' at rest: covered by it")
