"""stagehang.py <tag>=<model> ...: does an overhang SURVIVE to the dressed stage's mesh (what is rendered)? On the stage
skin near the left eye (surf.eye_frame: eye frame, mm), per column u (2 mm wide strips at -4, -2, 0, 2, 4): bin the
vertices by height (0.15 mm) between the lid margin and 9 mm up; a height bin with skin at two depths more than 0.8 mm
apart is skin hidden behind skin in a front view. Printed: the overhang's depth (mm of such heights, the largest
connected run), the slit's gap there (mm between the layers), its height over the margin. Writes out/stagehang.json."""
import json
import os
import sys

import numpy as np

import surf

G = os.environ["G"] + "/out"
res = json.load(open(G + "/stagehang.json")) if os.path.exists(G + "/stagehang.json") else {}
for a in sys.argv[1:]:
    tag, model = a.split("=", 1)
    P, N, r = surf.eye_frame(model)[:3]
    out = []
    for u in (-4.0, -2.0, 0.0, 2.0, 4.0):
        m = (np.abs(P[:, 0] - u) < 1.0) & (P[:, 2] > 5.0) & (P[:, 1] > -2) & (P[:, 1] < 16)
        p = P[m]
        s = np.linalg.norm(p, axis=1) - r
        # the lid margin: the lowest lid skin over the ball (small stand-off, above the opening)
        lid = p[(s < 3.0) & (p[:, 1] > 0.5)]
        if len(lid) < 20:
            continue
        v0 = np.percentile(lid[:, 1], 1)
        best, run, gap, h_at = 0.0, 0.0, 0.0, 0.0
        cur_gap = []
        for vb in np.arange(v0 + 2.0, v0 + 9.0, 0.15):
            w = np.sort(p[(p[:, 1] >= vb) & (p[:, 1] < vb + 0.15), 2])
            two = len(w) >= 4 and (np.diff(w).max() > 0.8)
            if two:
                run += 0.15
                cur_gap.append(float(np.diff(w).max()))
                if run > best:
                    best, gap, h_at = run, float(np.median(cur_gap)), vb - v0
            else:
                run, cur_gap = 0.0, []
        n = N[m][(p[:, 1] > v0 + 2.0) & (p[:, 1] < v0 + 9.0)]
        out.append({"u": u, "hang": best, "gap": gap, "h": h_at, "down": float((n[:, 1] < -0.5).mean())})
    res[tag] = {"model": model, "cols": out}
    print(f"{tag:6s} {model:10s} stage overhang by column (mm): " + " ".join(f"{c['hang']:.2f}" for c in out)
          + f" | mean {np.mean([c['hang'] for c in out]):.2f}, slit gap {np.mean([c['gap'] for c in out]):.2f}, at {np.mean([c['h'] for c in out]):.1f} mm over the margin")
json.dump(res, open(G + "/stagehang.json", "w"))
