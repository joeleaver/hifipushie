"""ROUGH CHECK ONLY (the lip-edge reader is the offset). lipoffset.py <model>...: front view: the picture's lip edges (MediaPipe outer lip contour: upper edge top point 0, lower
edge bottom point 17, the corners 61 / 291) against the model's (68-point landmarks 51 upper, 57 lower, 48 / 54 corners)
projected through the fitted camera; mm (+ = the picture's edge lies LOWER / further out than ours)."""
import sys
import numpy as np
from PIL import Image
from hifipushie import blockin as bi, humanfit, store
for m in sys.argv[1:]:
    rj = bi._refs(m); vi = bi._front(rj); v, cam = rj["views"][vi], rj["cameras"][vi]
    P = np.asarray(bi.detect_view(Image.open(v["image"]).convert("RGB"), v), float)[:, :2]
    st = humanfit.state(bi.view_base(store.load(m)["base"], rj, vi)); L = st["L"]
    M = humanfit.project(cam, L[:68])
    mmpx = 1000.0 * float(np.linalg.norm(L[36] - L[45])) / float(np.linalg.norm(M[36] - M[45]))
    up = np.array([0.0, -1.0])
    def dv(p, q): return float((p - q)[1]) * mmpx
    lower = dv(P[17], M[57]); upper = dv(P[0], M[51])
    thick_p = float(np.linalg.norm(P[17] - P[14])) * mmpx; thick_m = float(np.linalg.norm(M[57] - M[66])) * mmpx
    w_p = float(np.linalg.norm(P[61] - P[291])) * mmpx; w_m = float(np.linalg.norm(M[48] - M[54])) * mmpx
    print(f"{m}: lower lip edge {lower:+.1f} mm (+ = picture lower), upper lip edge {upper:+.1f} mm; lower vermilion height picture {thick_p:.1f} / model {thick_m:.1f} mm; mouth width picture {w_p:.1f} / model {w_m:.1f} mm")
