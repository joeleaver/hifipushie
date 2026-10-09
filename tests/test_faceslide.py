"""Face sliders (faceslide.py): symmetric, ranged, no fold / slot at the extremes, the lids kept on the eyeball, and
a known value recovered from a render by the least-change fit."""
import copy
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hifipushie import assets, base, faceslide, gnmloops, humanfit, humans  # noqa: E402


def _gnm_ok():
    try:
        assets.path("gnm", base.GNM)
        return True
    except Exception:
        return False


def _skin_quads():
    T = faceslide.template()
    Q = gnmloops.plan()["quads"]
    return Q[T["skin"][Q].all(1)]


def _normals(X, Q):
    n = np.cross(X[Q[:, 2]] - X[Q[:, 0]], X[Q[:, 3]] - X[Q[:, 1]])
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-18)


def test_symmetric_and_ranged():
    if not _gnm_ok():
        return
    T = faceslide.template()
    X, mi = T["X"], T["mirror"]
    for name, (dR, dL) in faceslide.fields().items():
        assert np.abs(dL[T["X"][:, 0] < -0.002]).max() == 0, name  # the left eye's field stays on the left
        assert np.allclose(dR, dL[mi] * [-1, 1, 1]), name
        unit = faceslide.UNITS[name][0] * (0.001 if name != "canthal_tilt" else 0.001 * 0.27)
        assert 0.5 * unit < np.linalg.norm(dL, axis=1).max() < 1.4 * unit + 1e-4, name
    v = faceslide.values({"eye_hood": 3.0, "canthal_tilt": [-0.2, 0.4]})
    assert v["eye_hood"] == (1.5, 1.5) and v["canthal_tilt"] == (-0.2, 0.4)
    try:
        faceslide.values({"eye_wink": 1})
        raise AssertionError("an unknown slider must be refused")
    except ValueError:
        pass


def test_no_fold_or_slot_at_the_extremes():
    """At -1 and +1 (both eyes): no skin quad turns over, no two neighbouring quads fold (normals turned > 60 deg
    more than in the template), the lids' rims stay put (or, for the canthal tilt, on the ball: distance to the
    eye's centre held) and the eyeballs don't move."""
    if not _gnm_ok():
        return
    T = faceslide.template()
    X = T["X"]
    Q = _skin_quads()
    n0 = _normals(X, Q)
    # neighbouring quads (sharing an edge)
    ef = {}
    for qi, q in enumerate(Q):
        for k in range(4):
            ef.setdefault(tuple(sorted((int(q[k]), int(q[(k + 1) % 4])))), []).append(qi)
    pairs = np.array([v for v in ef.values() if len(v) == 2])
    a0 = np.einsum("ij,ij->i", n0[pairs[:, 0]], n0[pairs[:, 1]])
    rim = T["rim"]
    J = T["J"][2:4]
    g = base._gnm_data()
    eyes = np.flatnonzero(np.asarray(g["groups"]["eyes"]) > 0.5)
    for name in faceslide.NAMES:
        for v in (-1.0, 1.0):
            D = faceslide.delta({name: v})
            if D is None:  # (a one-sided slider below 0)
                assert name in faceslide.ONE_SIDED
                continue
            X1 = X + D
            n1 = _normals(X1, Q)
            turned = int((np.einsum("ij,ij->i", n0, n1) < 0).sum())
            assert turned == 0, (name, v, turned)
            a1 = np.einsum("ij,ij->i", n1[pairs[:, 0]], n1[pairs[:, 1]])
            fold = (a1 < np.cos(np.radians(60))) & (a1 < a0 - 0.05)
            assert not fold.any(), (name, v, int(fold.sum()))
            assert np.abs(D[eyes]).max() == 0, name
            if name == "canthal_tilt":
                dist = lambda Y: np.min([np.linalg.norm(Y[rim] - j, axis=1) for j in J], axis=0)  # noqa: E731
                assert np.abs(dist(X1) - dist(X)).max() < 5e-5, name
            elif name != "epicanthal":
                assert np.linalg.norm(D[rim], axis=1).max() < 5e-5, (name, np.linalg.norm(D[rim], axis=1).max())


def test_slider_recovered_from_a_render():
    """A known crease height (on a lid with a defined crease) and canthal tilt, rendered, read back (luminance up the
    lid; the rim's corners) and solved by faceslide.fit through the built head: within 0.05 of the truth."""
    if not _gnm_ok():
        return
    b = humans.spec(age=40, sex=1.0, seed=None, skin=False, source="human")["base"]
    b.setdefault("head", {})["sliders"] = {"eye_crease_depth": 0.8}
    for name, key, v in (("eye_crease_height", "crease", 0.6), ("canthal_tilt", "canthal_tilt", -0.5)):
        bt = copy.deepcopy(b)
        bt["head"]["sliders"][name] = v
        m = faceslide.read_eyes(humanfit.state(bt))
        r = faceslide.fit(b, {key: (m[key], 0.1)}, [name])
        assert abs(r["sliders"][name] - v) < 0.05, (name, r)


if __name__ == "__main__":
    test_symmetric_and_ranged()
    test_no_fold_or_slot_at_the_extremes()
    test_slider_recovered_from_a_render()
    print("ok")
