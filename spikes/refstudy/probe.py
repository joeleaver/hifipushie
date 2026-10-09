"""What is in GNM's data: shapes, scale of the identity basis, groups."""
import numpy as np
from hifipushie import base, headfit

g = base._gnm_data()
for k, v in g.items():
    if hasattr(v, "shape"):
        print(k, v.shape, v.dtype)
print("groups", list(g["groups"]))
names = [str(n) for n in g["identity_names"]]
print("identity names", names[:6], "...", names[-6:], len(names))
print("heads", sum(n.startswith("head") for n in names))
en = [str(n) for n in g["expression_names"]]
print("expression names", en[:12], len(en))
B = np.asarray(g["vertex_identity_basis"], float)
sk = g["skin"]
rms = np.sqrt((B[:, sk] ** 2).sum(-1).mean(1)) * 1000
print("rms mm per unit of component (skin):", np.round(rms[:30], 2), "...", np.round(rms[100:130], 2))
V0 = g["template_vertex_positions"].astype(float)
print("template bbox", V0.min(0), V0.max(0))
print("joints", g["template_joint_positions"])
gg = headfit._gnm()
print("comps", len(gg["comps"]), gg["comps"][:5], "L0", gg["L0"].shape)
E = np.asarray(g["expression_basis"], float)
print("expr rms mm", np.round(np.sqrt((E[:, sk] ** 2).sum(-1).mean(1))[:20] * 1000, 2))
