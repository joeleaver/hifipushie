"""ladder.py raw <out.npz> | gap <model> ...: the outer-corner isolation ladder.
raw: GNM's female class-mean head exactly as GNM evaluates it (template + identity; skin with its socket lining and
     mouth sock, both eyes' inner shells: sclera, iris, pupil) as a mesh for raw_blender.py, and its lateral gaps.
gap: for built models, the same gaps: the lid margin (ring 0) and the socket lining (rings -1 .. -3) against the
     scleral sphere over the LATERAL third of the eye (the template's x beyond 5 mm from the eye centre toward the
     outer corner), the outer canthus vertex, and how far out the ball shows: the lateral end of the margin ring
     against the sphere's own lateral silhouette, seen from the front (mm)."""
import sys

import numpy as np

from hifipushie import base as basemod
from hifipushie import blockin, lidrings

g = basemod._gnm_data()
G = {k: np.asarray(v) > 0.5 for k, v in g["groups"].items()}
T = g["template_vertex_positions"].astype(float)
J = g["template_joint_positions"].astype(float)
t = lidrings.topo()


def gaps(tag, W, c, r, lat, fwd, up):
    """W: every GNM vertex (any frame, metres); c, r: the left ball; lat / fwd / up: unit axes (lat toward the outer corner)."""
    out = []
    for k in (0, -1, -2, -3):
        ids = t["loops"][k]
        P0 = (T[ids] - J[2]) * 1000
        sel = (P0[:, 0] > 5.0)
        d = (np.linalg.norm(W[ids[sel]] - c, axis=1) - r) * 1000
        out.append(f"ring {k:+d}: {d.mean():+.2f} (min {d.min():+.2f}, max {d.max():+.2f})")
    ring0 = t["loops"][0]
    canth = ring0[np.argmax(T[ring0, 0])]
    q = W[canth] - c
    # seen from the front: the margin's lateral end against the ball's lateral edge at that height
    h = float(q @ up)
    edge = np.sqrt(max(r * r - h * h, 0.0))
    lining = t["loops"][-1]
    ql = W[lining[np.argmax(T[lining, 0])]] - c
    print(f"{tag}: ball r {r * 1000:.2f} mm | lateral third, stand-off from the ball: " + "; ".join(out))
    print(f"   outer canthus vertex: {(np.linalg.norm(q) - r) * 1000:+.2f} mm off the ball, {q @ lat * 1000:.2f} mm lateral of the centre, {q @ fwd * 1000:.2f} mm "
          f"ahead; the ball's own edge at that height {edge * 1000:.2f} mm lateral -> the ball passes UNDER the canthus by {(edge - q @ lat) * 1000:+.2f} mm; "
          f"lining's lateral end {(np.linalg.norm(ql) - r) * 1000:+.2f} mm off the ball")
    # how much of the opening's lateral end is ball: along the eye line from the centre outwards, the last margin point
    P = W[ring0] - c
    width = P @ lat
    print(f"   margin ring spans {width.min() * 1000:.2f} .. {width.max() * 1000:.2f} mm across (the iris axis at 0): outer end {width.max() / r:.2f} r, inner {abs(width.min()) / r:.2f} r")


if sys.argv[1] == "raw":
    D = blockin.data()
    c = np.zeros(len(g["identity_names"]))
    c[:170] = np.asarray(D["m_f"], float)
    V = T + np.tensordot(c, g["vertex_identity_basis"], 1)
    eg = basemod.gnm_eyes(V, g)
    keep = np.asarray(g["groups"]["skin"]) > 0.5
    keep |= G["eye_interiors"]
    Q = np.asarray(g["quads"])
    Q = Q[keep[Q].all(1)]
    mat = np.zeros(len(Q), int)
    eye = G["eye_interiors"][Q].all(1)
    mat[eye] = 1
    mat[eye & G["irises"][Q].all(1)] = 2
    mat[eye & G["pupils"][Q].all(1)] = 3
    np.savez(sys.argv[2], verts=V, quads=Q, mat=mat, eyes=np.array([eg[0]["c"], eg[1]["c"]]), r=eg[0]["r"])
    gaps("RUNG 1 raw GNM, female class mean", V, eg[0]["c"], eg[0]["r"], np.array([1.0, 0, 0]), np.array([0, 0, 1.0]), np.array([0, 1.0, 0]))
else:
    from hifipushie import onemesh, store
    for name in sys.argv[2:]:
        ht = onemesh.head_rest(store.load(name)["base"])
        fwd = np.asarray(ht["forward"], float)
        up = np.array([0, 0, 1.0])
        gaps(name, np.asarray(ht["gnm_world"], float), np.asarray(ht["eyes"][0], float), float(ht["eye_r"]), np.cross(up, fwd) * -1 if np.cross(up, fwd)[0] < 0 else np.cross(up, fwd), fwd, up)
