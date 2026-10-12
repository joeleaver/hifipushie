"""gnmnative: GNM's two-sphere eye, read off its vertices: template, the 3 eye identity components, the pupil
expression component, and how the 170 head components move it."""
import numpy as np

from hifipushie import base

g = base._gnm_data()
G = {k: np.asarray(v) > 0.5 for k, v in g["groups"].items()}
T = g["template_vertex_positions"].astype(float)
B = g["vertex_identity_basis"]
E = g["expression_basis"]
inm = [str(x) for x in g["identity_names"]]
enm = [str(x) for x in g["expression_names"]]
J0 = g["template_joint_positions"].astype(float)
JB = g["joint_identity_basis"]


def sphere(P):
    A = np.c_[2 * P, np.ones(len(P))]
    x = np.linalg.lstsq(A, (P ** 2).sum(1), rcond=None)[0]
    c = x[:3]
    return c, float(np.sqrt(x[3] + c @ c))


def read(V, side="left"):
    m = G[f"{side}_eye"]
    c, r = sphere(V[m & G["scleras"]])
    pup = V[m & G["pupils"]]
    ax = pup.mean(0) - c
    ax /= np.linalg.norm(ax)
    ir = V[m & G["irises"]] - c
    rad = lambda P: np.linalg.norm(P - np.outer(P @ ax, ax), axis=1)
    ex = V[m & G["eye_exteriors"]] - c
    d = np.linalg.norm(ex, axis=1)
    bulge = d > r + 0.00015
    lim_ext = rad(ex[bulge]).max() if bulge.any() else 0
    cc, rc = sphere(ex[rad(ex) < 0.8 * lim_ext] + c)
    return {"c": c, "r_sclera": r * 1000, "r_ext": np.median(d[~bulge]) * 1000, "limbus_in": rad(ir).max() * 1000,
            "iris_depth_at_limbus": (ir @ ax)[np.argmax(rad(ir))] * 1000, "pupil_depth": ((pup - c) @ ax).min() * 1000,
            "pupil_r": rad(pup - c).max() * 1000, "limbus_ext": lim_ext * 1000, "apex": (ex @ ax).max() * 1000,
            "cornea_r": rc * 1000, "cornea_c_ahead": ((cc - c) @ ax) * 1000, "axis": ax}


def show(tag, V, J=None):
    for side, j in (("left", 2), ("right", 3)):
        q = read(V, side)
        txt = " ".join(f"{k} {v:.2f}" for k, v in q.items() if k not in ("c", "axis"))
        off = "" if J is None else f" | centre - joint mm {((q['c'] - J[j]) * 1000).round(2)}"
        print(f"{tag:26s} {side:5s} {txt} axis {q['axis'].round(3)}{off}")


show("template", T, J0)
for k in ("eyes_000", "eyes_001", "eyes_002"):
    i = inm.index(k)
    for s in (-2, 2):
        show(f"{k} {s:+d}", T + s * B[i], J0 + s * JB[i])
i = enm.index("pupils_000")
for s in (-2, -1, 1, 2):
    show(f"pupils_000 {s:+d}", T + s * E[i], J0)
i = enm.index("tongue_mean")
print("tongue_mean: max |delta| mm", float(np.abs(E[i]).max() * 1000), "on tongue only", float(np.abs(E[i][~G['tongue']]).max() * 1000))
# the 170 head components: how they move the eyeball, the teeth, the tongue (rigid? scale?)
rng = np.random.default_rng(0)
hi = [k for k, s in enumerate(inm) if s.startswith("head")]
print("\nhead identity (random N(0,1) heads): the eyeball's fitted centre vs GNM's eye joint, its radius, limbus")
for n in range(4):
    c = np.zeros(len(inm))
    c[hi] = rng.normal(size=len(hi))
    V = T + np.tensordot(c, B, 1)
    J = J0 + np.tensordot(c, JB, 1)
    show(f"random head {n}", V, J)
# per piece: the head components' effect as a similarity + residual
print("\nper piece, head components 0..9 at +2: rigid+scale fit residual (mm rms), scale, translation mm")
pieces = {"left eye": G["left_eye"], "lower teeth": G["lower_teeth_and_gums"], "upper teeth": G["upper_teeth_and_gums"],
          "tongue": G["tongue"]}
for nm, m in pieces.items():
    res, scl, tr = [], [], []
    for k in hi[:40]:
        X0, X1 = T[m], T[m] + 2 * B[k][m]
        a, b = X0.mean(0), X1.mean(0)
        U, S, Vt = np.linalg.svd((X0 - a).T @ (X1 - b))
        R = (U @ Vt).T
        s = S.sum() / ((X0 - a) ** 2).sum()
        res.append(np.sqrt((((X0 - a) @ R.T * s + b - X1) ** 2).sum(1).mean()) * 1000)
        scl.append(s)
        tr.append(np.linalg.norm(b - a) * 1000)
    print(f"{nm:12s} residual max {max(res):.4f} mm, scale {min(scl):.4f}..{max(scl):.4f}, translation max {max(tr):.2f} mm")
# teeth identity
ti = [k for k, s in enumerate(inm) if s.startswith("teeth")]
print("teeth comps: max vertex move per +1 (mm):", np.round([np.abs(B[k]).max() * 1000 for k in ti[:10]], 2))
# lower-face expression on lower teeth: rigid?
li = [k for k, s in enumerate(enm) if s.startswith("lower_face")]
m = G["lower_teeth_and_gums"]
res = []
for k in li[:30]:
    X0, X1 = T[m], T[m] + 2 * E[k][m]
    a, b = X0.mean(0), X1.mean(0)
    U, S, Vt = np.linalg.svd((X0 - a).T @ (X1 - b))
    R = (U @ Vt).T
    res.append((np.sqrt((((X0 - a) @ R.T + b - X1) ** 2).sum(1).mean()) * 1000, np.abs(E[k][m]).max() * 2000))
print("lower_face comps on the lower teeth (rigid residual mm, max move mm):", np.round(res[:10], 3).tolist())
