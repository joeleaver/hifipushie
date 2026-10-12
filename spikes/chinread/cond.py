"""cond.py: how well GNM's own population predicts the chin / jaw widths from the measures the pictures DO read (comps ~
N(0, 1): the measures' covariance is R R'). Per conditioning set: the residual sd of each unread measure given the set
(mm; macros sd) beside its population sd: what a tie to the conditional expectation could be worth at best."""
import numpy as np
from hifipushie import solve_report as sr
rw = sr.rows()
R = {n: rw["R"][i] for i, n in enumerate(rw["names"])}
U = ("chin_width", "jaw_width", "gonial_width", "jaw_square", "jaw_angle", "cheekbone_width", "under_chin")
SETS = {"nothing": (),
        "irises": ("pupils_apart",),
        "profile line": ("chin_forward", "pogonion_forward", "chin_length", "tip_forward", "subnasale_forward", "upper_lip_forward", "lower_lip_forward", "nose_length", "philtrum_length", "forehead_forward", "mentolabial_depth"),
        "profile + front features": ("chin_forward", "pogonion_forward", "chin_length", "tip_forward", "subnasale_forward", "upper_lip_forward", "lower_lip_forward", "nose_length", "philtrum_length", "forehead_forward", "mentolabial_depth", "pupils_apart", "mouth_width", "eyes_height", "nose_width"),
        "+ cheekbone_width": ("chin_forward", "pogonion_forward", "chin_length", "tip_forward", "subnasale_forward", "upper_lip_forward", "lower_lip_forward", "nose_length", "philtrum_length", "forehead_forward", "mentolabial_depth", "pupils_apart", "mouth_width", "eyes_height", "nose_width", "cheekbone_width"),
        "+ cheekbone + skull_width": ("chin_forward", "pogonion_forward", "chin_length", "tip_forward", "subnasale_forward", "upper_lip_forward", "lower_lip_forward", "nose_length", "philtrum_length", "forehead_forward", "mentolabial_depth", "pupils_apart", "mouth_width", "eyes_height", "nose_width", "cheekbone_width", "skull_width")}
print(f"{'given':28s} " + " ".join(f"{u[:12]:>12s}" for u in U))
for k, S in SETS.items():
    out = []
    for u in U:
        ru = R[u]
        if S and u not in S:
            A = np.array([R[s] for s in S])
            ru = ru - A.T @ np.linalg.solve(A @ A.T, A @ ru)
        out.append(float(np.linalg.norm(ru)) if u not in S else 0.0)
    print(f"{k:28s} " + " ".join(f"{x:12.2f}" for x in out))
print("\ncorrelations:")
for a in ("chin_width", "jaw_width", "gonial_width"):
    print(a, ", ".join(f"{b} {float(R[a] @ R[b] / np.linalg.norm(R[a]) / np.linalg.norm(R[b])):+.2f}" for b in ("pupils_apart", "cheekbone_width", "skull_width", "mouth_width", "chin_length", "jaw_width", "gonial_width", "chin_width", "neck_width", "nose_width")))
