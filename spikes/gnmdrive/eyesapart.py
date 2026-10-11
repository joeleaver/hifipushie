"""eyesapart.py: can GNM's identity set the eyes further apart with the face's mm proportions held? Least-norm dc moving the
pupils apart 1 mm with the other mm readouts (readouts.read: widths, heights, profile points, skull) held, and with the
macros except head_size / eye_spacing held. Reports |dc| per mm and what still moves."""
import numpy as np

import drv
import readouts as ro
from hifipushie import humanmacro as hm

keys = list(ro.read(np.zeros(170)).keys())
r0 = ro.read(np.zeros(170))
J = np.zeros((len(keys), 170))
for k in range(170):
    e = np.zeros(170)
    e[k] = 1
    r = ro.read(e)
    J[:, k] = [r[n] - r0[n] for n in keys]
i = keys.index("pupils_apart")
for label, hold in (("mm readouts held", [n for n in keys if n != "pupils_apart"]),
                    ("mm readouts held except skull/neck", [n for n in keys if n not in ("pupils_apart", "skull_width", "skull_top", "skull_back", "neck_width")])):
    rows = [keys.index(n) for n in hold]
    A = np.r_[J[[i]], J[rows]]
    b = np.r_[1.0, np.zeros(len(rows))]
    dc = A.T @ np.linalg.solve(A @ A.T + 1e-6 * np.eye(len(A)), b)
    r = ro.read(dc)
    mv = sorted(((n, r[n] - r0[n]) for n in keys), key=lambda t: -abs(t[1]))[:5]
    z = hm.read(dc[:hm.K])
    z0 = hm.read(np.zeros(hm.K))
    zm = sorted(((n, z[n] - z0[n]) for n in z), key=lambda t: -abs(t[1]))[:5]
    D = np.tensordot(dc, drv.IBH, 1) * 1000
    print(label, f"|dc| per mm {np.linalg.norm(dc):.2f}; mm moved:", [(n, round(v, 2)) for n, v in mv], "macros:", [(n, round(v, 2)) for n, v in zm],
          f"face rms {np.sqrt((D[drv.gcm.zones()['face']] ** 2).sum(1).mean()):.2f} mm")
    np.save(drv.G / "out" / f"eyesapart_{len(hold)}.npy", dc)
