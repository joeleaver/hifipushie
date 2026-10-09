"""MoGe's lens estimate against the true camera, per picture.  run.sh lens.py <model>"""
import sys
import numpy as np
import mm
r = []
for iid in mm.ids():
    p = mm.pred(sys.argv[1], iid)
    if p is None or "intrinsics" not in p:
        continue
    it = mm.item(iid)
    f = float(p["intrinsics"][0, 0]) * it["cam"]["size"][0]      # normalised by the width
    r.append((it["view"], it["cam"]["f"] / it["cam"]["size"][0] * 36, f / it["cam"]["size"][0] * 36))
r = np.array(r, dtype=object)
for vw in ("front", "tq", "profile", "tq2"):
    m = r[:, 0] == vw
    t, e = r[m, 1].astype(float), r[m, 2].astype(float)
    q = np.log(e / t)
    print(f"{vw:8s} n {m.sum():3d}  true lens 35-105 mm; estimate / true: median {np.exp(np.median(q)):.2f}, log sd {q.std():.2f} (x{np.exp(q.std()):.2f}), corr(log) {np.corrcoef(np.log(t), np.log(e))[0, 1]:.2f}; median estimate {np.median(e):.0f} mm")
