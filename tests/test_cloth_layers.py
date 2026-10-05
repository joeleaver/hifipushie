"""Layered garments, geometry only (no sim): the padded body, layer crossings, hidden faces, supports' errors.
uv run python tests/test_cloth_layers.py"""
import numpy as np
from scipy.spatial import ConvexHull

from hifipushie import cloth, cloth_layers


def _sphere(r=0.1, n=1500, seed=1):
    rng = np.random.default_rng(seed)
    P = rng.normal(size=(n, 3))
    P /= np.linalg.norm(P, axis=1, keepdims=True)
    F = ConvexHull(P).simplices
    c = P[F].mean(1)
    nrm = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    flip = (nrm * c).sum(1) < 0
    F[flip] = F[flip][:, [0, 2, 1]]
    return P * r, F


def _shell(V, F, r, zmax=None):
    V2 = V / np.linalg.norm(V, axis=1, keepdims=True) * r
    if zmax is not None:
        F = F[(V2[F][:, :, 2] < zmax).all(1)]
    E = np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1)
    ue, cnt = np.unique(E, axis=0, return_counts=True)
    border = np.zeros(len(V2), bool)
    border[ue[cnt == 1].ravel()] = True
    return {"V": V2, "mesh": {"F": F, "sew": np.zeros((0, 2), np.int64), "border": border}}


def test_padded_body_covers_the_under_garment():
    V, F = _sphere()
    body = cloth.Body({"V": V, "F": [list(f) for f in F], "J": {}})
    U = V[V[:, 2] > 0] * 1.08  # a cap worn 8 mm off the upper half
    pb = cloth.padded_body(body, {}, U, air=0.003)
    r = np.linalg.norm(pb.V, axis=1)
    top, bottom = V[:, 2] > 0.03, V[:, 2] < -0.085  # (the pad runs on ~6 cm past the garment's edge)
    assert r[top].min() > 0.108 + 0.002 and np.abs(r[bottom] - 0.1).max() < 1e-9, (r[top].min(), r[bottom].max())
    assert pb.clearance(U).max() < 0  # every point of the under garment is inside the padded body


def test_crossings_between_layers():
    A = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0.0]])
    B = np.array([[0.2, 0.2, -0.5], [0.3, 0.2, 0.5], [0.2, 0.3, 0.5]])
    F = np.array([[0, 1, 2]])
    assert cloth_layers.between_crossings(A, F, B, F) >= 1
    assert cloth_layers.between_crossings(A, F, B + [0, 0, 2.0], F) == 0


def test_hidden_faces_keep_a_margin_at_the_openings():
    V, F = _sphere()
    body = cloth.Body({"V": V, "F": [list(f) for f in F], "J": {}})
    under = _shell(V, F, 0.103)
    outer = dict(_shell(V, F, 0.108, zmax=0.05), body=body)  # open above z = 0.05
    h = cloth_layers.hidden(under, outer, margin=0.02)
    z = under["V"][under["mesh"]["F"]].mean(1)[:, 2]
    assert h[z < 0.0].mean() > 0.97 and not h[z > 0.06].any(), (h[z < 0].mean(), h[z > 0.06].sum())
    assert not h[(z > 0.04)].any()  # the margin inside the opening stays


def test_support_kinds_are_checked():
    V, F = _sphere()
    body = cloth.Body({"V": V, "F": [list(f) for f in F], "J": {}})
    assert cloth.supports(body, None) is None and cloth.supports(body, ["shoulder_pad"]) is None  # no shoulders: none


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v()
            print("ok", k)
