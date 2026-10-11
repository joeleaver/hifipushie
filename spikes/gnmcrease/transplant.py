"""transplant.py <target model> <donor npz>:<i> <out tag> [sigma_mm] [socket]: carry a donor identity's upper-lid shape onto
the target's identity with the face held: linear MAP over GNM's 170 identity comps (vertices are linear in c):
  min |dc|^2 + sum_region |B dc - D|^2 / sigma^2 + sum_hold |L dc|^2 / 0.3mm^2
D = the donor's upper-lid / orbit region minus the target's (both eyes, the region above the eyes' landmark line, each eye's
region shifted so its eye-landmark centroid matches: the shape, not the position). Holds: the 68 landmarks off the eyes
(0.3 mm) and the brows (1 mm). Reports the share of D made, |dc|, macro side effects; writes out/tp_<tag>.npy (170)."""
import sys

import numpy as np

import gk
import lidgnm
import perc
from hifipushie import blockin as bi, store

tm, donor, tag = sys.argv[1], sys.argv[2], sys.argv[3]
import os
STRIP = float(os.environ.get("STRIP", "0"))
AFFINE = os.environ.get("AFFINE") == "1"
sig = float(sys.argv[4]) if len(sys.argv) > 4 else 0.1
HC = lidgnm.HC
ct = bi.identity(store.load(tm))
if donor.startswith("npy:"):
    cd = np.load(donor[4:])
else:
    k, i = donor.split(":")
    cd = np.load(f"/mnt/data/hifipushie/gnmcrease/out/s_{k}.npz")["C"][int(i)]


def V(c):
    cc = np.zeros(len(perc.ID_NAMES)); cc[HC] = c
    return perc.world(perc.verts(cc)) * 1000      # mm, world axes


Vt, Vd = V(ct), V(cd)
Lt, Ld = perc.WLM @ Vt, perc.WLM @ Vd
reg = []
D = np.zeros_like(Vt)
for side, eyes, g in ((0, range(36, 42), "right_orbital_region"), (1, range(42, 48), "left_orbital_region")):
    m = perc.grp(g) & perc.EXT
    ce_t, ce_d = Lt[list(eyes)].mean(0), Ld[list(eyes)].mean(0)
    m &= Vt[:, 2] > ce_t[2] - 0.5
    if STRIP:
        e = list(eyes)
        xs = sorted([Lt[e[0], 0], Lt[e[3], 0]])
        m &= (Vt[:, 0] > xs[0] - 1) & (Vt[:, 0] < xs[1] + 1) & (Vt[:, 2] < ce_t[2] + STRIP)
    if AFFINE:
        # the donor's region mapped onto the target's by the best affine (scale / shear / rotation / shift): what is
        # left is the region's own relief (the fold), not the eye's size, spacing or tilt
        Xd = np.c_[Vd[m], np.ones(m.sum())]
        T = np.linalg.lstsq(Xd, Vt[m], rcond=None)[0]
        D[m] = Xd @ T - Vt[m]      # the donor placed on the target by the affine, minus the target
    else:
        D[m] = (Vd[m] - ce_d) - (Vt[m] - ce_t)
    reg.append(np.flatnonzero(m))
reg = np.concatenate(reg)
B = np.stack([perc.world(perc.IB[HC[j]]) for j in range(170)], -1) * 1000        # (N, 3, 170)
A_r = B[reg].reshape(-1, 170) / sig
y_r = D[reg].ravel() / sig
HOLD = [i for i in range(68) if not (36 <= i < 48 or 17 <= i < 27)]
BROWS = list(range(17, 27))
BL = np.einsum("ln,ndj->ldj", perc.WLM, B)
A_h = np.r_[BL[HOLD].reshape(-1, 170) / 0.3, BL[BROWS].reshape(-1, 170) / 1.0]
if os.environ.get("HOLDALL"):
    # the rest of the face held vertex by vertex (every 4th exterior skin vertex off the orbits / brows, 0.3 mm)
    off = perc.EXT.copy()
    for gname in ("left_orbital_region", "right_orbital_region", "left_brow_region", "right_brow_region"):
        off &= ~perc.grp(gname)
    face = off & (Vt[:, 1] < np.percentile(Vt[perc.EXT, 1], 40))      # the front of the head (y toward -Y = face)
    hv = np.flatnonzero(face)[::4]
    A_h = np.r_[A_h, B[hv].reshape(-1, 170) / float(os.environ["HOLDALL"])]
if len(sys.argv) > 5 and sys.argv[5] == "free":
    A_h = A_h[:0]
A = np.r_[A_r, A_h]
y = np.r_[y_r, np.zeros(len(A_h))]
dc = np.linalg.solve(A.T @ A + np.eye(170), A.T @ y)
made = 1 - np.sum((A_r @ dc - y_r) ** 2) / np.sum(y_r ** 2)
print(f"{tag}: region {len(reg)} verts, D rms {np.sqrt(np.mean(np.sum(D[reg] ** 2, 1))):.2f} mm max {np.linalg.norm(D[reg], axis=1).max():.2f}; "
      f"made {made:.2f}, |dc| {np.linalg.norm(dc):.2f} (donor-target |c| {np.linalg.norm(cd - ct):.2f}); landmark moves rms "
      f"{np.sqrt(np.mean((A_h @ dc) ** 2)) * 0.3 if len(A_h) else float('nan'):.2f} mm")
g0, g1 = gk.geo(ct)[0], gk.geo(ct + dc)[0]
gd = gk.geo(cd)[0]
for k in ("local", "x_narrow", "hsoft", "show", "up", "lo"):
    print(f"  {k:9s} target {g0[k]:6.2f} -> {g1[k]:6.2f} (donor {gd[k]:6.2f})")
k0, k1, kd = gk.clay(ct)[0], gk.clay(ct + dc)[0], gk.clay(cd)[0]
print(f"  clay line: target {k0['dark']:.2f}@{k0['tps']:.1f} -> {k1['dark']:.2f}@{k1['tps']:.1f} (donor {kd['dark']:.2f}@{kd['tps']:.1f})")
m0, m1 = gk.macro(ct), gk.macro(ct + dc)
ch = sorted(m0, key=lambda q: -abs(m1[q] - m0[q]))[:8]
print("  macros: " + ", ".join(f"{q} {m0[q]:+.2f}->{m1[q]:+.2f}" for q in ch))
np.save(f"/mnt/data/hifipushie/gnmcrease/out/tp_{tag}.npy", ct + dc)
