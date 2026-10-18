"""eyecause.py <glb>: the visible sclera's baked colour against the paint's two eye_shade masks: distance to the head
surface (the "near base" lid-contact band) and height over the eye centre (the upper lid's axis shadow), per side."""
import sys, numpy as np
from scipy.spatial import cKDTree
exec(open("/mnt/data/hifipushie/assembly/eyealb.py").read().split("E = g[")[0])
E = g["meshes"]["eyes"]; Hh = g["meshes"]["head"]
TH0 = Hh["V"][Hh["F"]]
kd = cKDTree(np.concatenate([Hh["V"], TH0.mean(1)]))
paint = np.array([233, 227, 220.])
for side, sg in (("left(+x)", 1), ("right(-x)", -1)):
    ev = E["V"][E["V"][:, 0] * sg > 0]; c0 = np.array([np.median(ev[:, 0]), ev[:, 1].min() + 0.012, np.median(ev[:, 2])])
    T = E["V"][E["F"]]; n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]); n /= np.linalg.norm(n, axis=1)[:, None] + 1e-12
    C = T.mean(1); lat = np.hypot(C[:, 0] - c0[0], C[:, 2] - c0[2])
    f = np.where((C[:, 0] * sg > 0) & (n[:, 1] < -0.3) & (lat > .0065) & (lat < .011))[0]
    s, P = samples("eyes", f)
    near = (np.abs(TH0.mean(1)[:, 0] - c0[0]) < .02) & (np.abs(TH0.mean(1)[:, 2] - c0[2]) < .02)
    vis = seen_front(P, TH0[near]); s, P = s[vis], P[vis]
    dist = kd.query(P)[0] * 1e3; dz = (P[:, 2] - c0[2]) * 1e3; ratio = s / paint
    print(f"{side}: n {len(s)}, mean ratio to paint {ratio.mean(0).round(2)}; dist to head p10/50/90 {np.percentile(dist,[10,50,90]).round(2)} mm")
    for lo, hi in ((0, .5), (.5, 1), (1, 1.5), (1.5, 2.5), (2.5, 9)):
        m = (dist >= lo) & (dist < hi)
        if m.any(): print(f"   dist {lo}-{hi} mm: n {m.sum():4d} ratio {ratio[m].mean(0).round(2)}")
    for lo, hi in ((-12, -3), (-3, 0), (0, 3), (3, 12)):
        m = (dz >= lo) & (dz < hi)
        if m.any(): print(f"   dz {lo}..{hi} mm: n {m.sum():4d} ratio {ratio[m].mean(0).round(2)}")
    # r26 prediction: the shade keyed to the unsigned distance from the head (mesh distance ~ |SDF|)
    r = 0.0123e3; col = np.array([0.6, 0.43, 0.41])
    def ramp(x, a, b): u = np.clip((x - a) / (b - a), 0, 1); return u * u * (3 - 2 * u)
    nn = 1 - ramp(dist, 0.02 * r, 0.11 * r); nw = 1 - ramp(dist, 0.04 * r, 0.2 * r); ax = ramp(dz, 0.1 * r, 0.55 * r)
    m = np.maximum(0.85 * ax * nw, nn); fac = 1 - 0.6 * (1 - col) * m[:, None]
    base = ratio / (1 - 0.6 * (1 - col))  # the ball's colour without the (saturated) old shade
    print(f"   predicted r26 ratio {(base * fac).mean(0).round(2)}, sRGB {(paint * base * fac).mean(0).round()}")
