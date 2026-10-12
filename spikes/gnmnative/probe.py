"""gnmnative: what GNM's mesh holds besides the skin (components, groups, the eye's parts)."""
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from hifipushie import base

g = base._gnm_data()
V = g["template_vertex_positions"].astype(float)
Q = g["quads"]
n = len(V)
e = np.concatenate([Q[:, [0, 1]], Q[:, [1, 2]], Q[:, [2, 3]], Q[:, [3, 0]]])
nc, lab = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n)), directed=False)
G = {k: np.asarray(v) for k, v in g["groups"].items()}
print("joints", g["template_joint_positions"])
for c in range(nc):
    m = lab == c
    names = [(k, int((G[k][m] > 0.5).sum())) for k in G
             if (G[k][m] > 0.5).any() and not k.endswith("_region") and k not in ("left", "right")]
    print(c, int(m.sum()), "idx", np.flatnonzero(m)[[0, -1]], "bbox", V[m].min(0).round(4), V[m].max(0).round(4), names)
print({k: (str(v.dtype), float(v.min()), float(v.max()), int((v > 0.5).sum())) for k, v in G.items()
       if not k.endswith("_region")})
J = g["template_joint_positions"].astype(float)


def sphere(P):
    A = np.c_[2 * P, np.ones(len(P))]
    x = np.linalg.lstsq(A, (P ** 2).sum(1), rcond=None)[0]
    c = x[:3]
    return c, float(np.sqrt(x[3] + c @ c))


for nm, j in (("left_eye", 2), ("right_eye", 3)):
    m = G[nm] > 0.5
    for sub in ("scleras", "irises", "pupils", "eye_interiors", "eye_exteriors"):
        mm = m & (G[sub] > 0.5)
        P = V[mm]
        if len(P) > 4:
            c, r = sphere(P) if sub == "scleras" else (None, None)
            d = np.linalg.norm(P - J[j], axis=1)
            ax = np.linalg.norm((P - J[j])[:, :2], axis=1)
            print(nm, sub, len(P), "d joint", d.min().round(5), np.median(d).round(5), d.max().round(5),
                  "z-zj", (P[:, 2].min() - J[j][2]).round(5), (P[:, 2].max() - J[j][2]).round(5), "sphere", c, r,
                  "axis r", ax.min().round(5), ax.max().round(5))
B = g["vertex_identity_basis"]
E = g["expression_basis"]
inm = [str(x) for x in g["identity_names"]]
enm = [str(x) for x in g["expression_names"]]
comp = {"skin": lab == lab[np.flatnonzero(g["skin"])[0]]}
for c in range(nc):
    comp[f"c{c}"] = lab == c
for fam in ("head", "eyes", "teeth"):
    ii = [i for i, s in enumerate(inm) if s.startswith(fam)]
    print("identity", fam, len(ii), {k: float(np.abs(B[ii][:, m]).max() * 1000) for k, m in comp.items()})
for fam in ("left_eye", "right_eye", "lower_face", "tongue", "pupils"):
    ii = [i for i, s in enumerate(enm) if s.startswith(fam)]
    print("expression", fam, len(ii), {k: float(np.abs(E[ii][:, m]).max() * 1000) for k, m in comp.items()})
print("joint basis by family (mm):", {fam: float(np.abs(g["joint_identity_basis"][[i for i, s in enumerate(inm) if s.startswith(fam)]]).max() * 1000) for fam in ("head", "eyes", "teeth")})
