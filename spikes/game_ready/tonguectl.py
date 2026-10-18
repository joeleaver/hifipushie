"""tonguectl.py: what each of GNM's tongue expression controls does to the tongue, per unit (mm): tip (front 10% of the
tongue's length) dy (- = forward) / dz (- = down), dorsum mid-line rise vs its sides (+ = the top bows up / rounds),
and the back's dz. Uses gnm_controls.field on the GNM mean head (expr_tongue family)."""
import numpy as np
from hifipushie import gnm_controls as gc
Z = gc.zones(); g = gc.gnm()
t = np.asarray(Z["tongue"]); t = np.flatnonzero(t) if t.dtype == bool else t
V = gc.vertices()[t] if gc.vertices().ndim == 2 else gc.vertices()
print("tongue verts", len(t), "bbox mm", (V.min(0) * 1000).round(1), (V.max(0) * 1000).round(1))
# GNM frame: +y up, +z forward (front of the face)
z0, z1 = V[:, 2].min(), V[:, 2].max(); L = z1 - z0
tip = V[:, 2] > z1 - 0.12 * L; back = V[:, 2] < z0 + 0.3 * L
top = V[:, 1] > np.percentile(V[:, 1], 60)
w = np.ptp(V[:, 0]); mid = top & (np.abs(V[:, 0]) < 0.12 * w) & ~tip & ~back
side = top & (np.abs(V[:, 0]) > 0.28 * w) & ~tip & ~back
print("tip n", tip.sum(), "mid n", mid.sum(), "side n", side.sum(), "back n", back.sum())
rows = []
for n in gc.names("expr_tongue"):
    if n == "pupil": continue
    D = gc.field(n)[t] * 1000
    r = (n, D[tip, 2].mean(), D[tip, 1].mean(), D[mid, 1].mean() - D[side, 1].mean(), D[back, 1].mean(), np.sqrt((D ** 2).sum(1)).max())
    rows.append(r)
print(f"{'control':14s} {'tip fwd':>7s} {'tip up':>7s} {'bow':>7s} {'back up':>7s} {'max':>6s}")
for r in rows: print(f"{r[0]:14s} {r[1]:7.2f} {r[2]:7.2f} {r[3]:7.2f} {r[4]:7.2f} {r[5]:6.2f}")
