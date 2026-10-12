"""gnmnative: the exterior shell's profile (axial radius -> height over the scleral sphere) and corneal sphere fits."""
import numpy as np

from hifipushie import base

g = base._gnm_data()
G = {k: np.asarray(v) > 0.5 for k, v in g["groups"].items()}
T = g["template_vertex_positions"].astype(float)
J = g["template_joint_positions"].astype(float)
m = G["left_eye"] & G["eye_exteriors"]
e = (T[m] - J[2]) * 1000
ax = np.array([0, 0, 1.0])
a = np.linalg.norm(e[:, :2], axis=1)
z = e[:, 2]
d = np.linalg.norm(e, axis=1)
front = z > 0
order = np.argsort(a[front])
rings = np.unique(np.round(a[front][order], 2))
print("axial radius -> z, |p|   (front half, unique rings)")
for r in rings[:16]:
    s = np.abs(a - r) < 0.02
    s &= front
    print(f"  a {r:6.2f}  z {z[s].mean():6.3f}  |p| {d[s].mean():6.3f}  n {s.sum()}")
apex = z.max()
for amax in (2.5, 3.5, 4.5, 5.5):
    s = front & (a < amax) & (a > 0.3)
    h = apex - z[s]
    rc = (h ** 2 + a[s] ** 2) / (2 * h)
    print(f"cornea fit a < {amax}: rc median {np.median(rc):.2f} (min {rc.min():.2f} max {rc.max():.2f})")
print(base.gnm_eyes(T, g)[0])
