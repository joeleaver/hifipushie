"""lidbias.py: before believing fit_hood's "the picture's upper lids are HIGHER than the head's": the definition bias
of the lid points. On front renders of heads of known shape (8 identities; neutral, and with the lids lowered 1.3 mm
as a squint) the detector's lid points read as GNM's 68 (the MP68 table: what fit_hood compares) against GNM's true
lid landmarks projected: vertical offset in mm (+ = the detector's point is ABOVE GNM's landmark), per lid."""
import numpy as np

import rs
from hifipushie import humanfit

rng = np.random.default_rng(4)
UP, LO = [37, 38, 43, 44], [40, 41, 46, 47]
rows = {"neutral": [], "squint": []}
imgs, meta = [], []
for i in range(8):
    c = rng.normal(0, 0.8, rs.K_TRUE)
    for tag, e in (("neutral", None), ("squint", rs.expression({"lid_upper": 0.0013}))):
        V = rs.head(c, e)
        cam = rs.make_cam(V, lens=70.0, size=(768, 768))
        img, zb = rs.render(V, cam, albedo=rs.skinned_albedo(i))
        imgs.append(img)
        meta.append((tag, V, cam))
det = rs.detect(imgs)
for d, (tag, V, cam) in zip(det, meta):
    if d is None:
        continue
    L = rs.landmarks(V)
    P = humanfit.project(cam, L[:68])
    Q = d["P"][rs.LM_FROM_MP[:68], :2]
    mm = cam["t"][2] / cam["f"] * 1000
    dv = -(Q - P)[:, 1] * mm                       # + = the detector's point is higher in the picture
    open_true = (P[LO, 1] - P[UP, 1]).mean() * mm
    open_det = (Q[LO, 1] - Q[UP, 1]).mean() * mm
    rows[tag].append([dv[UP].mean(), dv[LO].mean(), open_true, open_det])
for tag, r in rows.items():
    r = np.array(r)
    print(f"{tag:8s} n {len(r)}: detector's UPPER lid points {r[:, 0].mean():+.2f} mm (sd {r[:, 0].std():.2f}) against GNM's lid landmarks, "
          f"LOWER {r[:, 1].mean():+.2f} (sd {r[:, 1].std():.2f}); the opening: true {r[:, 2].mean():.2f} mm, detector's {r[:, 3].mean():.2f} mm")
n, s = np.array(rows["neutral"]), np.array(rows["squint"])
k = min(len(n), len(s))
print(f"a 1.3 mm lowering of the upper lid: true opening changes {np.mean(s[:k, 2] - n[:k, 2]):+.2f} mm, the detector's {np.mean(s[:k, 3] - n[:k, 3]):+.2f} mm")
