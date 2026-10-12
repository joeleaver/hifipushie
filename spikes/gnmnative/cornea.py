"""gnmnative: the exterior shell's profile (axial radius -> height over the scleral sphere) for the eye identity
components, and base.gnm_eyes' read of each (the corneal sphere fit must hold over +-2.5 sd)."""
import numpy as np

from hifipushie import base

g = base._gnm_data()
G = {k: np.asarray(v) > 0.5 for k, v in g["groups"].items()}
T = g["template_vertex_positions"].astype(float)
J = g["template_joint_positions"].astype(float)
inm = [str(n) for n in g["identity_names"]]
m = G["left_eye"] & G["eye_exteriors"]
for comp in ("eyes_000", "eyes_001"):
    B = g["vertex_identity_basis"][inm.index(comp)]
    for s in (-2.5, -1, 0, 1, 2.5):
        V = T + s * B
        e = (V[m] - J[2]) * 1000
        a = np.linalg.norm(e[:, :2], axis=1)
        d = np.linalg.norm(e, axis=1)
        front = e[:, 2] > 0
        bins = np.arange(0, 12.1, 1.0)
        prof = [f"{(d[front & (a >= b) & (a < b + 1)].mean() if (front & (a >= b) & (a < b + 1)).any() else np.nan) - np.median(d[~front]):5.2f}" for b in bins]
        q = base.gnm_eyes(V, g)[0]
        print(f"{comp} {s:+.1f}: bulge over the sphere by axial mm 0..12: {' '.join(prof)} | r {q['r'] * 1000:.2f} limbus {q['limbus'] * 1000:.2f} "
              f"cornea_r {q['cornea_r'] * 1000:.2f} apex {q['apex'] * 1000:.2f} iris_r {q['iris_r'] * 1000:.2f} pupil {q['pupil']:.2f}")
