"""readouts.py: what each control does in MILLIMETRES a driver can see (per +1 unit, on GNM's template; GNM is linear,
so the same on any head): profile points forward (+ = toward the viewer), heights (+ up), front widths, eyeballs.
-> out/readouts.txt / .json"""
import json

import numpy as np

import drv
import gnmc
from hifipushie import blockin as bi, humanmacro as hm

sp = hm.space()
S = sp["sets"]


def read(c):
    V = drv.verts(c) * 1000            # GNM frame: x left, y up, z forward
    L = gnmc.WLM @ V
    eL, eR = V[gnmc.GROUPS["left_eye"]].mean(0), V[gnmc.GROUPS["right_eye"]].mean(0)
    pog = V[S["pog"]].mean(0) if len(S["pog"]) else L[8]
    cr = V[S["cranium"]]
    r = {"pupils_apart": abs(eL[0] - eR[0]), "eyeball_fwd_vs_nasion": 0.5 * (eL[2] + eR[2]) - L[27, 2],
         "eyes_height": 0.5 * (eL[1] + eR[1]),
         "brow_fwd": L[[19, 24], 2].mean(), "nasion_fwd": L[27, 2], "tip_fwd": L[30, 2], "subnasale_fwd": L[33, 2],
         "upper_lip_fwd": L[51, 2], "lower_lip_fwd": L[57, 2], "pogonion_fwd": pog[2],
         "brow_height": L[[19, 24], 1].mean(), "tip_height": L[30, 1], "subnasale_height": L[33, 1],
         "mouth_height": L[[51, 57], 1].mean(), "chin_bottom_height": L[8, 1],
         "cheekbone_width": np.ptp(V[S["zyg"], 0]), "jaw_angle_width": L[12, 0] - L[4, 0], "chin_width": L[10, 0] - L[6, 0],
         "mouth_width": L[54, 0] - L[48, 0], "nose_width": L[35, 0] - L[31, 0],
         "skull_width": np.ptp(cr[:, 0]), "skull_top": cr[:, 1].max(), "skull_back": cr[:, 2].min(),
         "neck_width": np.ptp(V[S["neck"], 0]), "under_chin_drop": V[S["under_chin"], 1].mean() if len(S["under_chin"]) else 0.0}
    return r


NAMES = []
for m in hm.NAMES:
    NAMES += [m, m + "!"]
NAMES += ["nd:" + n for n in bi.gap_names()]
from hifipushie import base as basemod  # noqa: E402
regs = sorted(k for k in basemod._gnm_data()["groups"] if k.endswith("_region") and not k.startswith(("left_", "right_")))
NAMES += [f"pc:{r}{k}" for r in regs for k in range(4)]
NAMES += [f"sculpt:{z}" for z in ("radix", "dorsum", "nose_tip", "alae", "upper_vermilion", "lower_vermilion", "chin",
                                  "pogonion", "under_chin", "jowls", "cheeks", "malar", "temples", "brows", "glabella",
                                  "upper_lid", "lower_lid", "tear_trough", "jawline", "jaw_angle", "parotid")]
NAMES += [f"relief:{z}" for z in ("lid_fold", "nasolabial", "mentolabial_sulcus", "alar_crease", "tear_trough", "marionette")]
r0 = read(np.zeros(170))
out = {}
lines = []
for n in NAMES:
    d = bi.direction(n)
    r1 = read(d)
    dd = {k: round(float(r1[k] - r0[k]), 2) for k in r0}
    out[n] = {"dc": round(float(np.linalg.norm(d)), 2), "mm": dd}
    top = sorted(dd.items(), key=lambda kv: -abs(kv[1]))[:6]
    lines.append(f"{n} (|dc| {out[n]['dc']}): " + ", ".join(f"{k} {v:+.1f}" for k, v in top))
(drv.G / "out" / "readouts.json").write_text(json.dumps(out, indent=1))
(drv.G / "out" / "readouts.txt").write_text("\n".join(lines))
print("\n".join(lines))
