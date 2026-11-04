"""A surface tape stays ON the body (C356), for any body: a tape laid over the surface (body_tape arcs and surface
lengths) may bridge a hollow (it lifts off, outside the skin) but never cuts through the body, and never goes the
long way round. t s3-2: an armhole arc from the armpit to the shoulder point came out as the straight chord through
the shoulder (129.6 mm, the other direction 184.9), and a shoulder tape "over the top" ran up over the head (468 mm
for 170 mm of shoulder): both written as measurements with no refusal.

INSIDE: the path sampled every SAMPLE_M; a sample more than DEPTH_M inside the skin (behind its nearest vertex,
along that vertex's normal) makes it a cut through the body.
LONG_X: a surface tape longer than this many times its straight chord goes the long way round (an arc over half
the waist is ~1.4x, from the front chest round to the back ~2x).
"""
from __future__ import annotations

import numpy as np

SAMPLE_M = 0.005
DEPTH_M = 0.008  # (a slice loop ON the skin reads up to ~4-8 mm "inside" in a hollow by its nearest vertex normal
#                   (between the shoulder blades); a chord through the shoulder is cm deep)
LONG_X = 2.5


def _normals(tape):
    if getattr(tape, "_vn", None) is None:
        V, T = tape.V, np.asarray(tape.T)
        fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
        vn = np.zeros_like(V)
        for k in range(3):
            np.add.at(vn, T[:, k], fn)
        vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
        from scipy.spatial import cKDTree
        tape._vn, tape._kd = vn, cKDTree(V)
    return tape._vn, tape._kd


def inside(tape, P) -> bool:
    """True when the path P cuts through the body anywhere."""
    P = np.asarray(P, float)
    if len(P) < 2:
        return False
    pts = []
    for p, q in zip(P, P[1:]):
        n = max(1, int(np.linalg.norm(q - p) / SAMPLE_M))
        pts.append(p + np.linspace(0, 1, n, endpoint=False)[:, None] * (q - p))
    S = np.concatenate(pts)
    vn, kd = _normals(tape)
    _, i = kd.query(S)
    depth = -np.einsum("ij,ij->i", S - tape.V[i], vn[i])
    return bool(np.max(depth) > DEPTH_M)
