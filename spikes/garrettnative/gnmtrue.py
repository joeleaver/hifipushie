"""gnmtrue.py <model> ..: IS THE BUILT HEAD GNM? GNM evaluated directly for the model's identity (template + every
identity component; + GNM's own lip_close move solved on that raw head) against the built head's GNM vertices
(onemesh.head_rest(base)["gnm_world"]) after the best similarity (one scale, rotation, translation; fitted on the
face = the hockey mask's exterior skin): rms / max deviation in mm (GNM's own millimetres: the built head divided by
the fitted scale) by region, and how the deviation grows down the neck against onemesh.neck_fade."""
import sys

import numpy as np

from hifipushie import base as bm, headfit, onemesh, store  # noqa: F401


def similarity(A, B):
    """s, R, t with s * A @ R.T + t ~ B (Umeyama)."""
    ma, mb = A.mean(0), B.mean(0)
    X, Y = A - ma, B - mb
    U, S, Vt = np.linalg.svd(Y.T @ X / len(A))
    d = np.sign(np.linalg.det(U @ Vt))
    D = np.diag([1, 1, d])
    R = U @ D @ Vt
    s = float(np.trace(np.diag(S) @ D) / (X ** 2).sum() * len(A))
    return s, R, mb - s * ma @ R.T


g = bm._gnm_data()
G = {k: np.asarray(v) > 0.5 for k, v in g["groups"].items()}
T = g["template_vertex_positions"].astype(float)
names = [str(n) for n in g["identity_names"]]
fade = onemesh.neck_fade()
lm = np.asarray(g["lm68"])
for m in sys.argv[1:]:
    base = store.load(m)["base"]
    hd = base["head"]
    c = np.array([float((hd.get("identity") or {}).get(n, 0.0)) for n in names])
    V0 = T + np.tensordot(c, g["vertex_identity_basis"], 1)
    try:
        dp = bm.lip_close_delta(V0, g, 1.0) if hd.get("lip_close") else np.zeros_like(V0)
    except Exception as e:  # noqa: BLE001
        print("lip_close on the raw head failed:", e)
        dp = np.zeros_like(V0)
    V = V0 + dp
    W = np.asarray(onemesh.head_rest(base)["gnm_world"], float)
    ext = G["skin_exterior"]
    face = G["hockey_mask"] & ext
    try:
        Lr = lm if lm.ndim == 1 else None
        ylip = float(V[lm[57], 1]) if Lr is not None else float(np.percentile(V[G["lower_lip_region"], 1], 20))
    except Exception:  # noqa: BLE001
        ylip = float(np.percentile(V[G["lower_lip_region"], 1], 20))
    reg = {"face (hockey mask)": face, "jaw and chin (face below the lower lip)": face & (V[:, 1] < ylip),
           "mouth (lip regions)": (G["upper_lip_region"] | G["lower_lip_region"]) & ext,
           "skull (exterior skin off the face, off the ears, fade 1)": ext & ~G["hockey_mask"] & ~G["ears"] & (fade >= 1),
           "ears": G["ears"] & ext, "neck (fade < 1)": ext & (fade < 1), "eye sockets' lining": G["eye_sockets"]}
    s, R, t = similarity(V[face], W[face])
    D = (W - (s * V @ R.T + t)) / s * 1000.0
    d = np.linalg.norm(D, axis=1)
    print(f"== {m}: head keys { {k: v for k, v in hd.items() if k != 'identity'} }; style {base.get('style')}")
    print(f"   similarity fitted on the face: scale {s:.4f} (the body carries GNM at this), lip_close's own move on the raw head: max {1000 * np.linalg.norm(dp, axis=1).max():.2f} mm")
    for k, msk in reg.items():
        print(f"   {k:58s} n {int(msk.sum()):5d}  rms {np.sqrt((d[msk] ** 2).mean()):6.3f} mm  max {d[msk].max():6.3f} mm")
    d0 = np.linalg.norm((W - (s * V0 @ R.T + t)) / s * 1000.0, axis=1)
    print(f"   (against GNM WITHOUT lip_close: face rms {np.sqrt((d0[face] ** 2).mean()):.3f} max {d0[face].max():.3f} mm)")
    # a second fit on the SKULL: is the face one similarity with the skull?
    sk = reg["skull (exterior skin off the face, off the ears, fade 1)"]
    s2, R2, t2 = similarity(V[sk | face], W[sk | face])
    d2 = np.linalg.norm((W - (s2 * V @ R2.T + t2)) / s2 * 1000.0, axis=1)
    print(f"   fitted on face + skull together: scale {s2:.4f}; face rms {np.sqrt((d2[face] ** 2).mean()):.3f} max {d2[face].max():.3f}; skull rms {np.sqrt((d2[sk] ** 2).mean()):.3f} max {d2[sk].max():.3f} mm")
    # down the neck: deviation against the fade, and against height above the lowest exterior vertex (GNM mm)
    y = (V[:, 1] - V[ext, 1].min()) * 1000
    for lo, hi in ((0.999, 1.01), (0.9, 0.999), (0.7, 0.9), (0.4, 0.7), (0.1, 0.4), (-0.01, 0.1)):
        k = ext & (fade > lo) & (fade <= hi)
        if k.any():
            print(f"   fade {lo:5.2f}..{hi:4.2f}: n {int(k.sum()):5d}, GNM height {y[k].min():6.1f}..{y[k].max():6.1f} mm over the bib's edge, deviation rms {np.sqrt((d[k] ** 2).mean()):6.2f} max {d[k].max():6.2f} mm")
    far = ext & (fade >= 1) & (d > 0.3)
    print(f"   exterior skin at fade 1 further than 0.3 mm from GNM: {int(far.sum())} vertices" + (f" (lowest at {y[far].min():.0f} mm, highest at {y[far].max():.0f} mm; by group: " + ", ".join(f"{k} {int((far & v).sum())}" for k, v in G.items() if k.endswith('_region') and (far & v).sum()) + ")" if far.any() else ""))
    chin_y = float(y[face].min())
    k = ext & (fade < 1)
    print(f"   the fade starts (fade < 1) at {y[k].max():.0f} mm; the chin's lowest face vertex is at {chin_y:.0f} mm; first deviation > 0.3 mm going down: " + (f"{y[ext & (d > 0.3)].max():.0f} mm" if (ext & (d > 0.3)).any() else "none (a native head: GNM to the bib)"))
