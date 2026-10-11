"""rawgnm.py: GNM's own mean head around the left eye (GNM frame: x left, y up, z forward; mm): the margin ring, the
lm68 corners, its own eyeball (sclera sphere, iris), how its ball fills the ring, and the same with a smaller ball."""
import numpy as np

from hifipushie import base as basemod

g = basemod._gnm_data()
T = np.asarray(g["template_vertex_positions"], float) * 1000
gr = {k: np.asarray(v, float) > 0.5 for k, v in g["groups"].items()}
skin = np.asarray(g["skin"]).astype(bool)
Q = np.asarray(g["quads"])
J = np.asarray(g["template_joint_positions"], float) * 1000
print("EYE_R", basemod.EYE_R, "EYE_SEAT", basemod.EYE_SEAT, "eye joints", np.round(J[2:4], 1))
WL = np.zeros((68, len(T)))
for i, r in enumerate(g["lm68"]):
    for v, x in zip(r[0::2], r[1::2]):
        WL[i, int(v)] += float(x)
L = WL @ T


def sphere(P):
    A = np.c_[2 * P, np.ones(len(P))]
    sol = np.linalg.lstsq(A, (P ** 2).sum(1), rcond=None)[0]
    c = sol[:3]
    r = np.sqrt(sol[3] + c @ c)
    return c, r, float(np.abs(np.linalg.norm(P - c, axis=1) - r).max())


left = gr["left_eye"]
for name in ("scleras", "irises", "pupils", "eye_exteriors", "eye_interiors"):
    m = left & gr[name]
    if m.sum() > 8:
        c, r, e = sphere(T[m])
        print(f"left {name}: n {m.sum()} sphere centre {np.round(c, 1)} r {r:.2f} max dev {e:.2f}; x {T[m][:, 0].min():.1f}..{T[m][:, 0].max():.1f} z max {T[m][:, 2].max():.1f}")
ext = left & gr["eye_exteriors"] & gr["scleras"]
cs, rs, _ = sphere(T[ext]) if ext.sum() > 8 else sphere(T[left & gr["scleras"]])
ir = left & gr["irises"]
print(f"iris: centre {np.round(T[ir].mean(0), 1)} radius (max from its centre in xy) {np.linalg.norm((T[ir] - T[ir].mean(0))[:, :2], axis=1).max():.2f}")
# the lid margin ring (skin next to the socket lining) of the left eye
sock = gr["eye_sockets"]
e = np.concatenate([Q[:, [0, 1]], Q[:, [1, 2]], Q[:, [2, 3]], Q[:, [3, 0]]])
m = (sock[e[:, 0]] != sock[e[:, 1]]) & skin[e[:, 0]] & skin[e[:, 1]]
ring = np.unique(np.where(sock[e[m, 0]], e[m, 1], e[m, 0]))
ring = ring[np.linalg.norm(T[ring] - cs, axis=1) < 2.2 * rs]
R = T[ring]
print(f"ring: n {len(R)} x {R[:, 0].min():.1f}..{R[:, 0].max():.1f} (width {np.ptp(R[:, 0]):.1f}) y {R[:, 1].min():.1f}..{R[:, 1].max():.1f} (open {np.ptp(R[:, 1]):.1f})")
print(f"lm68 42 (inner) {np.round(L[42], 1)}  45 (outer) {np.round(L[45], 1)}  width {np.linalg.norm(L[45] - L[42]):.1f}; pupils apart {abs(T[gr['left_eye']].mean(0)[0] - T[gr['right_eye']].mean(0)[0]):.1f}")
d = np.linalg.norm(R - cs, axis=1) - rs
o = np.argsort(R[:, 0])
print("ring vertex distance to GNM's own sclera sphere (mm), by x (inner -> outer):")
print("   x   ", np.round(R[o, 0][::3] - cs[0], 1))
print("   dist", np.round(d[o][::3], 2))
# a front view (along -z): where does a ball's silhouette end against the ring's ends?
for label, c, r in (("GNM's own", cs, rs),):
    print(f"{label} ball: silhouette x {c[0] - r:.1f}..{c[0] + r:.1f}; ring x {R[:, 0].min():.1f}..{R[:, 0].max():.1f}")
print("sock rows near the inner corner: x range of lining verts", np.round([T[sock & (T[:, 0] > 0)][:, 0].min(), T[sock & (T[:, 0] > 0)][:, 0].max()], 1))
