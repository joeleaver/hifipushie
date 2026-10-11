"""expr.py <model|mean> <class> [t ...]: GNM's raw lid rows at the pupil column of the LEFT eye while an expression
prototype of the sampler (wink_left, squint, surprise ...) is dialled t (default -0.5 0 0.5 1). Per t, per ring 0..10:
v (up, mm from the ball centre) / distance to GNM's own ball; the margin's height, the arclength margin -> ring 6 (does
the platform's skin keep its length = slide, or stretch?), the lowest point of rings 6..9 against ring 5 (overhang)."""
import sys

import numpy as np

import lidmap as lm
from hifipushie import blockin as bi, gnm_controls as gc, gnm_sampler as gs, store

name, cls = sys.argv[1], sys.argv[2]
ts = [float(x) for x in sys.argv[3:]] or [-0.5, 0.0, 0.5, 1.0]
c = None if name == "mean" else bi.identity(store.load(name))
if cls.startswith("pc"):     # a raw left-eye component
    e1 = np.zeros(383)
    e1[int(cls[2:])] = 1.0
else:
    e1 = gs.prototype(cls)
g = gc.gnm()
le = [i for i, n in enumerate(g["ex_names"]) if n.startswith("left_eye")]
print(f"{cls}: |e| all {np.linalg.norm(e1):.2f}, left-eye comps {np.linalg.norm(e1[le]):.2f}, top", [(g['ex_names'][i][-3:], round(float(e1[i]), 2)) for i in np.argsort(-np.abs(e1[le]))[:6]])
ctr, r = lm.eye_frame_raw(c)
cols = {}
for t in ts:
    V = gc.vertices(c, t * e1) * 1000
    up = {k: (v, w) for k, v, w in lm.column(V, ctr, 0.0)}
    lo = {k: (v, w) for k, v, w in lm.column(V, ctr, 0.0, upper=False)}
    cols[t] = (up, lo)
print(f"\n{name} + t x {cls}; ball r {r:.1f}. Per ring: v / to ball")
print("ring " + "".join(f"   t={t:+.2f}     " for t in ts))
for k in range(-2, 12):
    row = f"{k:4d} "
    for t in ts:
        up = cols[t][0]
        if k in up:
            v, w = up[k]
            row += f" {v:6.2f} /{np.hypot(v, w) - r:5.2f}  "
        else:
            row += "       -        "
    print(row)
for t in ts:
    up, lo = cols[t]
    ks = [k for k in range(0, 7) if k in up]
    arc = sum(np.hypot(up[b][0] - up[a][0], up[b][1] - up[a][1]) for a, b in zip(ks[:-1], ks[1:]))
    arc2 = sum(np.hypot(up[b][0] - up[a][0], up[b][1] - up[a][1]) for a, b in zip(range(6, 10), range(7, 11)))
    hang = min(up[k][0] for k in range(6, 10)) - up[5][0]
    fwd = max(np.hypot(*up[k]) for k in range(6, 9)) - min(np.hypot(*up[k]) for k in range(3, 7))
    print(f"t {t:+.2f}: upper margin v {up[0][0]:5.2f}, lower margin v {lo[0][0] if 0 in lo else float('nan'):5.2f}, opening {up[0][0] - (lo[0][0] if 0 in lo else np.nan):5.2f}; "
          f"arc 0->6 {arc:5.2f}, arc 6->10 {arc2:5.2f}; fold (rings 6-8 over the platform's lowest) {fwd:4.2f}; rings 6-9 below ring 5 by {min(hang, 0):.2f}")
