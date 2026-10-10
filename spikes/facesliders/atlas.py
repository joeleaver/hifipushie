"""atlas.py <n> [seed]: the GNM model atlas (Joe: "we need to comprehend the model"). Samples n heads from GNM's
identity prior (the 120 head components, N(0, 1)), measures on each every attribute we have a slider or a checklist
item for (humanmacro's macros + the lid / lip / nose / jaw attributes below, mm in GNM's frame), and writes
out/atlas_<n>.npz: c (n, 120), A (n, m) and the attribute names. Then atlas_report.py."""
import sys
import time

import numpy as np

from hifipushie import base as basemod
from hifipushie import faceslide, gnmloops, humanmacro

n = int(sys.argv[1])
seed = int(sys.argv[2]) if len(sys.argv) > 2 else 0
g = basemod._gnm_data()
names = [str(x) for x in g["identity_names"]]
comps = [i for i, x in enumerate(names) if x.startswith("head")][:humanmacro.K]
V0 = g["template_vertex_positions"].astype(float)
IB = np.asarray(g["vertex_identity_basis"])[comps].astype(np.float32).reshape(len(comps), -1)
J0 = g["template_joint_positions"].astype(float)
JB = np.asarray(g["joint_identity_basis"])[comps].astype(float)
w = lambda X: np.stack([X[..., 0], -X[..., 2], X[..., 1]], -1)  # noqa: E731  GNM -> humanmacro's world
T = faceslide.template()
ext = T["ext"]
mm = 0.001


def band_width(X, n_, ext_, y, ylo, x_max=0.016, cos=0.8):
    """x extent of the exterior skin facing forward (n.z > cos) in a 3 mm band round height y (GNM frame)."""
    s = ext_ & (np.abs(X[:, 1] - y) < 1.5 * mm) & (np.abs(X[:, 0]) < x_max) & (n_[:, 2] > cos) & (X[:, 1] > ylo)
    return float(np.ptp(X[s, 0])) * 1000 if s.sum() > 2 else np.nan


def lid_attrs(Th):
    """crease height (the fold's turn over the margin, mm; nan = no turn: a smooth lid), its overhang (mm the skin
    2 mm over the turn stands in front of it), from faceslide's own lid coordinates, the left eye's middle band."""
    faceslide._left_fields(Th)
    Hc, H0, u, up = faceslide._CACHE["last_crease"]
    X = Th["X"]
    lm = Th["lm"]
    mid = up & (u > 0.35) & (u < 0.65)
    if not np.ndim(Hc):
        return np.nan, np.nan
    hc = float(np.median(Hc[mid]))
    c_in, c_out = lm[42], lm[45]
    wd = float(np.linalg.norm(c_out - c_in))
    ex = (c_out - c_in) / wd
    uk = lambda p: float((p - c_in) @ ex / wd)  # noqa: E731
    ym = faceslide._quad(np.array([0.0, uk(lm[43]), uk(lm[44]), 1.0]), np.array([c_in[1], lm[43][1], lm[44][1], c_out[1]]))
    h = X[:, 1] - ym(np.clip(u, 0, 1))
    zat = lambda hh: float(np.median(X[mid & (np.abs(h - hh) < 0.6 * mm), 2])) if (mid & (np.abs(h - hh) < 0.6 * mm)).any() else np.nan  # noqa: E731
    return hc * 1000, (zat(hc + 2 * mm) - zat(hc)) * 1000


rng = np.random.default_rng(seed)
C = rng.normal(0, 1, (n, len(comps)))
rows, attr_names = [], None
t0 = time.time()
for i in range(n):
    V = V0 + (C[i] @ IB).reshape(-1, 3)
    J = J0 + np.tensordot(C[i], JB, 1)
    a = dict(humanmacro.measures(w(V)))
    Th = faceslide.head_template(V)
    X, nn, lm = Th["X"], Th["n"], Th["lm"]
    a["crease_height"], a["fold_overhang"] = lid_attrs(Th)
    a["lid_aperture"] = float((0.5 * (lm[43] + lm[44]) - 0.5 * (lm[46] + lm[47]))[1]) * 1000
    a["upper_vermilion"] = float(lm[51][1] - lm[62][1]) * 1000
    a["lower_vermilion"] = float(lm[66][1] - lm[57][1]) * 1000
    a["bow_depth"] = float(0.5 * (lm[50][1] + lm[52][1]) - lm[51][1]) * 1000
    a["upper_lip_proj"] = float(lm[51][2] - lm[33][2]) * 1000
    a["lower_lip_proj"] = float(lm[57][2] - lm[8][2]) * 1000
    a["lower_lip_width"] = float(abs(lm[55][0] - lm[59][0]) / max(abs(lm[54][0] - lm[48][0]), 1e-6))
    a["nostril_show"] = float(0.5 * (lm[31][1] + lm[35][1]) - lm[33][1]) * 1000
    yb = lm[33][1]
    a["radix_width"] = band_width(X, nn, ext, lm[27][1] + 0.1 * (lm[30][1] - lm[27][1]), yb)
    a["dorsum_width"] = band_width(X, nn, ext, lm[27][1] + 0.5 * (lm[30][1] - lm[27][1]), yb)
    a["tip_width"] = band_width(X, nn, ext, lm[30][1] + 0.002, yb, cos=0.6)
    a["gonion_height"] = float(0.5 * (lm[4][1] + lm[12][1]) - lm[57][1]) * 1000
    d = lm[4] - lm[2]
    a["ramus_angle"] = float(np.degrees(np.arctan2(abs(d[0]), abs(d[1]))))
    eye = J[2] if J[2][0] > 0 else J[3]
    a["eye_setback"] = float(lm[27][2] - eye[2]) * 1000
    pm = 0.5 * (lm[46] + lm[47]) + np.array([0.004, -0.016, 0.0])
    cheek = ext & (np.linalg.norm(X - pm, axis=1) < 4 * mm)
    a["malar_rise"] = float(np.median(X[cheek, 2]) - 0.5 * (lm[42][2] + lm[45][2])) * 1000 if cheek.any() else np.nan
    if attr_names is None:
        attr_names = list(a)
    rows.append([a[k] for k in attr_names])
    if i % 100 == 0:
        print(i, round(time.time() - t0, 1), "s", flush=True)
out = f"/mnt/data/hifipushie/facesliders/out/atlas_{n}.npz"
np.savez(out, c=C, A=np.array(rows, float), names=np.array(attr_names))
print(out)
