"""dres.py <model> ..: the dense-landmark read's own error AT a model with its cameras (a truth model: network - true
vertex projection, mm): per view the mean (x, y) = the bias, the rms about it, the rms in its own sigma, per region;
and the similarity (shift, scale, turn) that would best explain the whole face's residual: what a free camera would
do with it."""
import sys
import numpy as np
from hifipushie import face_ruler as fr
import common as C

fr.DENSE = True
for name in sys.argv[1:]:
    rj = C.refs(name)
    b0 = rj.get("blockin") or {}
    head, views, notes = fr.reference_views(name, lids=True, lips=True, parse="auto", kinds=b0.get("kinds"), readers=b0.get("readers"))
    print(f"== {name}")
    for v in views:
        obs = [ob for ob in v["extra"](head, v) if ob["type"] == "dense"]
        if not obs:
            print("  no dense reads in", v["kind"]); continue
        ox = np.array([ob["o"] for ob in obs if ob["name"].endswith(".x")]); oy = np.array([ob["o"] for ob in obs if ob["name"].endswith(".y")])
        sg = np.array([ob["sig"] for ob in obs if ob["name"].endswith(".x")]); reg = np.array([ob["region"] for ob in obs if ob["name"].endswith(".x")])
        P = np.array([ob["p"] for ob in obs if ob["name"].endswith(".x")])
        mm = float(v["cam"]["t"][2]) / v["cam"]["f"] * 1000.0
        Q = (P - P.mean(0)) * mm
        # best similarity of the residual field: o = t + s * Q + w * perp(Q)
        A = np.zeros((2 * len(Q), 4)); A[0::2, 0] = 1; A[1::2, 1] = 1; A[0::2, 2] = Q[:, 0]; A[1::2, 2] = Q[:, 1]; A[0::2, 3] = -Q[:, 1]; A[1::2, 3] = Q[:, 0]
        y = np.c_[ox, oy].ravel()
        th = np.linalg.lstsq(A, y, rcond=None)[0]
        left = y - A @ th
        print(f"  {v['kind']:8s} n {len(ox):4d}: bias x {ox.mean():+5.2f} y {oy.mean():+5.2f} mm; rms {np.sqrt((ox ** 2 + oy ** 2).mean()):.2f} mm; sigma used (median) {np.median(sg):.2f} mm; "
              f"as a camera: shift {th[0]:+.2f} {th[1]:+.2f} mm, scale {100 * th[2]:+.2f} %, roll {np.degrees(th[3]):+.2f} deg; left after it {np.sqrt((left ** 2).reshape(-1, 2).sum(1).mean()):.2f} mm")
        for r in sorted(set(reg)):
            m = reg == r
            print(f"      {r:14s} n {m.sum():3d} bias x {ox[m].mean():+5.2f} y {oy[m].mean():+5.2f} rms {np.sqrt((ox[m] ** 2 + oy[m] ** 2).mean()):.2f} sigma {np.median(sg[m]):.2f}")
