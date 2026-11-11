"""garment_game known answers: two flat panels sewn along one edge, re-gridded in pattern space."""
import numpy as np

from hifipushie import garment_game as gg


def _grid(n, x0):
    xs = np.linspace(0, 0.2, n)
    U, V = np.meshgrid(xs, xs, indexing="ij")
    uv = np.stack([U.ravel(), V.ravel()], 1)
    q = np.arange(n * n).reshape(n, n)
    a, b, c, d = q[:-1, :-1].ravel(), q[1:, :-1].ravel(), q[1:, 1:].ravel(), q[:-1, 1:].ravel()
    F = np.concatenate([np.stack([a, b, c], 1), np.stack([a, c, d], 1)])
    P = np.stack([uv[:, 0] + x0, uv[:, 1], np.zeros(len(uv))], 1)
    return uv, F, P, q


def _drape(n=11):
    uvA, FA, PA, qA = _grid(n, 0.0)
    uvB, FB, PB, qB = _grid(n, 0.2)
    off = len(uvA)
    sew = np.stack([qA[-1, :], qB[0, :] + off], 1)  # A's right edge to B's left edge
    return {"name": "test", "V": np.vstack([PA, PB]), "F": np.vstack([FA, FB + off]), "uv": np.vstack([uvA, uvB]),
            "piece": np.r_[np.zeros(off, int), np.ones(off, int)], "names": ["A", "B"], "sew": sew,
            "sew_seam": np.zeros(len(sew), int), "made": [], "drop": set(), "color": "#808080", "thickness": 0.001}


def test_pierce_faces_known_answers():
    """Face-level pierce: crossing between the under sheet's vertices is caught (the vertex test misses it); two
    parallel sheets 2 mm apart are not; a plane through the sheet finds exactly the faces it cuts."""
    gg._selftest_pierce_faces()
