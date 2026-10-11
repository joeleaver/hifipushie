"""eyechk.py <case>...: eyeball size / placement and the eye macros for A, B and the driver's head."""
import json
import sys

import numpy as np

import drv
import gnmc
from hifipushie import humanmacro as hm

for case in sys.argv[1:]:
    h = json.loads((drv.HIDDEN / f"{case}.json").read_text())
    st = json.loads((drv.CASES / case / "state.json").read_text())
    for lab, c in (("A", h["A"]), ("B", h["B"]), ("drv", st["c"])):
        V = drv.verts(c)
        out = []
        for side in ("left_eye", "right_eye"):
            P = V[gnmc.GROUPS[side]]
            out.append((np.ptp(P[:, 0]) * 1000, P.mean(0) * 1000))
        io = abs(out[0][1][0] - out[1][1][0])
        z = hm.read(np.asarray(c)[:hm.K])
        print(case, lab, f"eyeball width {out[0][0]:.2f} mm, centres {io:.2f} mm apart, eye height {out[0][1][1]:.1f} fwd {out[0][1][2]:.1f}",
              {k: round(z[k], 2) for k in ("head_size", "eye_spacing", "eye_height", "eye_width", "eye_depth", "lower_orbit", "face_width")})
