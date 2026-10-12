"""gnmnative: what the one mesh's hook does to GNM's loose pieces (eyeballs, teeth, tongue): are they still GNM's
shapes (a similarity of the posed GNM piece) after the body's head, gnm_base, dimorphism and the style sliders?"""
import sys

import numpy as np

from hifipushie import base as basemod
from hifipushie import onemesh, store

g = basemod._gnm_data()
G = {k: np.asarray(v) > 0.5 for k, v in g["groups"].items()}
a = onemesh.asset()
f = a["g_fade"].astype(float)
nf = onemesh.neck_fade()
pieces = {"left eye": G["left_eye"], "right eye": G["right_eye"], "lower teeth": G["lower_teeth_and_gums"],
          "upper teeth": G["upper_teeth_and_gums"], "tongue": G["tongue"], "sock": G["mouth_sock"]}
for k, m in pieces.items():
    print(f"{k:12s} g_fade {f[m].min():.3f}..{f[m].max():.3f}  neck_fade {nf[m].min():.3f}..{nf[m].max():.3f}  g_part "
          f"{np.unique(a['g_part'][m])} g_lev {np.unique(a['g_lev'][m])[:4]} valid {a['g_valid'][m].mean():.2f}")
T = g["template_vertex_positions"].astype(float)
for name in sys.argv[1:]:
    b = store.load(name)["base"]
    b = {**b, "head": {k: v for k, v in b["head"].items() if k != "eye_radius"}}
    ht = onemesh.head_template(b)
    hd = onemesh.head_desc(b)
    print(name, {k: (v if k not in ("identity", "bound") else "...") for k, v in hd.items()})
    Vp = ht["carry"]["V"]  # GNM frame, posed, after the hook
    ci = basemod._gnm_coeffs(g["identity_names"], hd.get("identity"))
    Vg = T + np.tensordot(ci, g["vertex_identity_basis"], 1)  # GNM's own
    for k, m in pieces.items():
        X0, X1 = Vg[m], Vp[m]
        c0, c1 = X0.mean(0), X1.mean(0)
        U, S, Vt = np.linalg.svd((X0 - c0).T @ (X1 - c1))
        R = (U @ Vt).T
        sc = S.sum() / ((X0 - c0) ** 2).sum()
        res = np.sqrt((((X0 - c0) @ R.T * sc + c1 - X1) ** 2).sum(1))
        # anisotropy: per-axis scale
        ax = [float(np.ptp(X1[:, j]) / np.ptp(X0[:, j])) for j in range(3)]
        print(f"   {k:12s} similarity scale {sc:.4f} rot {np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1))):.2f} deg, "
              f"residual rms {1000 * res.mean():.3f} max {1000 * res.max():.3f} mm; extent ratios x/y/z {ax[0]:.3f} {ax[1]:.3f} {ax[2]:.3f}")
    print("   scale s", ht["carry"]["s"], "eye_gnm", {k: (round(1000 * v, 2) if isinstance(v, float) else None) for k, v in (ht.get("eye_gnm") or {}).items()})
