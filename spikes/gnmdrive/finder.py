"""finder.py: for the phrases the drivers could not solve, rank vocabulary moves by how much they move the phrase's
reader (mm) per unit prior cost and how CLEAN they are (the reader's change vs the rms change of the other readouts).
Readers in mm on GNM's head (GNM frame: y up, z forward). -> out/finder.txt"""
import numpy as np

import drv
import gnmc
import score
from hifipushie import humanmacro as hm

S = hm.space()["sets"]
Z = drv.gcm.zones()


def zmean(V, z, ax):
    return V[Z[z], ax].mean()


def readers(c):
    V = drv.verts(c) * 1000
    L = gnmc.WLM @ V
    fh = V[S["forehead"]].mean(0)
    r = {
        "forehead_ahead_of_nasion": fh[2] - L[27, 2],
        "philtrum_length": L[33, 1] - L[51, 1],
        "mouth_height_vs_chin": L[57, 1] - L[8, 1],
        "lower_face_width_at_mouth": L[13, 0] - L[3, 0],
        "jaw_angle_width": L[12, 0] - L[4, 0],
        "cheekbone_width": np.ptp(V[S["zyg"], 0]),
        "eyes_over_nose_base": 0.5 * (L[36, 1] + L[45, 1]) - L[33, 1],
        "brows_over_eyes": L[[19, 24], 1].mean() - 0.5 * (L[37, 1] + L[44, 1]),
        "brow_arch": L[[19, 24], 1].mean() - L[[17, 26], 1].mean(),
        "under_eye_hollow (lower lid vs cheek fwd)": zmean(V, "lower_lid", 2) - zmean(V, "infraorbital", 2),
        "tear_trough_depth (trough vs lid & cheek)": zmean(V, "tear_trough", 2) - 0.5 * (zmean(V, "lower_lid", 2) + zmean(V, "malar", 2)),
        "dorsum_width (walls vs ridge)": zmean(V, "dorsum", 2) - zmean(V, "bridge_walls", 2),
        "submental_slope (under-chin vs chin bottom height)": V[S["under_chin"], 1].mean() - L[8, 1],
        "occiput_back": -V[S["cranium"], 2].min(),
        "cheek_fwd_in_3q (cheeks zone fwd vs mouth corners)": zmean(V, "cheeks", 2) - zmean(V, "mouth_corners", 2),
    }
    return r


names, D = score.dictionary()
r0 = readers(np.zeros(170))
R = np.array([[readers(D[:, j])[k] - r0[k] for k in r0] for j in range(D.shape[1])])   # (moves, readers) per unit
cost = np.linalg.norm(D, axis=0)
sd = R.std(0) + 1e-9
lines = []
for i, k in enumerate(r0):
    eff = np.abs(R[:, i]) / cost
    others = np.delete(R / sd, i, axis=1)
    clean = np.abs(R[:, i] / sd[i]) / (np.sqrt((others ** 2).mean(1)) + 0.05)
    sc = eff * np.minimum(clean, 3)
    top = np.argsort(-sc)[:6]
    lines.append(f"== {k}: " + "; ".join(f"{names[j]} {R[j, i]:+.2f} mm/unit (|dc| {cost[j]:.2f}, clean {clean[j]:.1f})" for j in top))
(drv.G / "out" / "finder.txt").write_text("\n".join(lines))
print("\n".join(lines))
