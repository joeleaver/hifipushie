"""salience.py: the perceptual weight of each facial REGION (faces4 M0b): K random smooth surface moves confined to the
region (Gaussian bumps along the normal, radius RAD, random signs, 0.5 mm rms over the region's exterior skin, eased to
0 at its edge), rendered at -1 / +1 on the heads (perc.py's renderer and embedding), the face-ID distance per mm of rms
move. The weights the solve's geometry terms get per region come from these, relative to the cheeks'."""
import json
import os
import sys

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(__file__))
import perc  # noqa: E402

K = int(os.environ.get("K", "6"))
RAD = float(os.environ.get("RAD", "0.004"))
RMS = 0.0005
g = perc.g
TPL = perc.TPL
ext = perc.EXT
# vertex normals of the template
q = perc.Q
fn = np.cross(TPL[q[:, 2]] - TPL[q[:, 0]], TPL[q[:, 3]] - TPL[q[:, 1]])
vn = np.zeros_like(TPL)
for k in range(4):
    np.add.at(vn, q[:, k], fn)
vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-15)
REG = {
    "eyes (orbits)": ["left_orbital_region", "right_orbital_region"],
    "brows": ["left_brow_region", "right_brow_region", "middle_brow_region"],
    "nose": ["nose_region"],
    "upper lip": ["upper_lip_region"],
    "lower lip": ["lower_lip_region"],
    "chin": ["chin_region"],
    "cheeks": ["left_cheek_region", "right_cheek_region"],
    "infraorbital": ["left_infraorbital_region", "right_infraorbital_region"],
    "zygomatic": ["left_zygomatic_region", "right_zygomatic_region"],
    "forehead": ["forehead_region"],
    "temples": ["left_temple_region", "right_temple_region"],
    "jaw / parotid": ["left_parotid_region", "right_parotid_region"],
}
rng = np.random.default_rng(1)
heads = {h: perc.head(h) for h in os.environ.get("HEADS", "mean,tess,garrett").split(",")}
rows = []
mi_tree = cKDTree(TPL * [-1, 1, 1])
for name, groups in REG.items():
    m = np.zeros(len(TPL), bool)
    for gname in groups:
        m |= np.asarray(g["groups"][gname], float) > 0.5
    m &= ext
    idx = np.flatnonzero(m)
    dist = cKDTree(TPL[idx]).query(TPL)[0]
    x = np.clip(1 - dist / 0.004, 0, 1)
    win = np.where(ext, x * x * (3 - 2 * x), 0.0)
    per = []
    for k in range(K):
        cen = idx[rng.choice(len(idx), size=max(2, len(idx) // 400), replace=False)]
        amp = np.zeros(len(TPL))
        for c in cen:
            s = rng.choice([-1.0, 1.0])
            r2 = ((TPL - TPL[c]) ** 2).sum(1)
            amp += s * np.exp(-r2 / (2 * RAD ** 2))
            # mirror bump (faces are compared symmetric)
            r2m = ((TPL - TPL[c] * [-1, 1, 1]) ** 2).sum(1)
            amp += s * np.exp(-r2m / (2 * RAD ** 2))
        D = (amp * win)[:, None] * vn
        D *= RMS / max(np.sqrt((np.linalg.norm(D[idx], axis=1) ** 2).mean()), 1e-12)
        r = perc.measure(f"{name} #{k}", lambda c, D=D: perc.verts(c, D=D), lambda c, D=D: perc.verts(c, D=-D), heads)
        per.append(r["id"]["sface"])
    rows.append({"region": name, "sface_per_mm": float(np.mean(per)) / (2 * RMS * 1e3), "spread": float(np.std(per)) / (2 * RMS * 1e3),
                 "n": int(len(idx))})
    print(f"{name:16s} 1-cos per mm rms (between -/+): {rows[-1]['sface_per_mm']:.4f} +- {rows[-1]['spread']:.4f}  ({len(idx)} verts)",
          flush=True)
ref = next(r["sface_per_mm"] for r in rows if r["region"] == "cheeks")
print("relative to the cheeks:", ", ".join(f"{r['region']} {r['sface_per_mm'] / ref:.2f}" for r in
                                          sorted(rows, key=lambda r: -r["sface_per_mm"])))
(perc.OUT / "salience.json").write_text(json.dumps(rows))
