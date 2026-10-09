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
        assert np.abs(dL[T["X"][:, 0] < -0.002]).max() == 0, name  # the left side's field stays on the left
        # (the mouth's fields are made on GNM's whole template, symmetric only to ~0.1 mm)
        big = np.abs(dL).max() + np.abs(dR).max()
        assert np.allclose(dR, dL[mi] * [-1, 1, 1], atol=0 if name in faceslide.EYE_SLIDERS else max(6e-5, 0.03 * big)), name
        if name in faceslide.AGE_SLIDERS:  # (baked ops: their units are the ops' own)
            continue
        unit =faceslide.UNITS[name][0] * (0.001 if name != "canthal_tilt" else 0.001 * 0.27)
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
    more (past 60 deg, by 10 deg or more) than in the template), the lids' rims stay put (or, for the canthal tilt, on the ball: distance to the
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
            ang = lambda a: np.degrees(np.arccos(np.clip(a, -1, 1)))  # noqa: E731
            fold = (a1 < np.cos(np.radians(60))) & (ang(a1) - ang(a0) > 10)  # (the vermilion border is 67 deg already)
            assert not fold.any(), (name, v, int(fold.sum()))
            assert np.abs(D[eyes]).max() == 0, name
            if name in faceslide.MOUTH_SLIDERS:  # no lip through the other: the contact ring's upper side never down,
                # its lower side never up
                lmr = base._gnm_data()["lm68"]
                dy = lambda i: sum(float(w) * D[int(vv)][1] for vv, w in zip(lmr[i][0::2], lmr[i][1::2]))  # noqa: E731
                assert min(dy(i) for i in (61, 62, 63)) > -5e-5 and max(dy(i) for i in (65, 66, 67)) < 5e-5, name
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


def test_lip_roll_recovered_from_a_render():
    """The upper and lower lip rolls read from a clay render's depth (each vermilion's middle in front of the
    subnasale) and solved together by faceslide.fit: within 0.08 of the truth."""
    if not _gnm_ok():
        return
    b = humans.spec(age=40, sex=1.0, seed=None, skin=False, source="human")["base"]
    bt = copy.deepcopy(b)
    bt.setdefault("head", {})["sliders"] = {"lip_upper_roll": 0.5, "lip_lower_roll": -0.4}
    m = faceslide.read_mouth(humanfit.state(bt))
    r = faceslide.fit(b, {k: (m[k], 0.1) for k in ("upper_proj", "lower_proj")}, ["lip_upper_roll", "lip_lower_roll"],
                      read=faceslide.read_mouth, hold=0.01)
    assert abs(r["sliders"]["lip_upper_roll"] - 0.5) < 0.08 and abs(r["sliders"]["lip_lower_roll"] + 0.4) < 0.08, r


def _contact_gaps(V):
    R = faceslide._lip_rings()
    C = R["rings"][R["contact"]]
    x = V[C, 0]
    a, b = V[C[np.argmin(x)]], V[C[np.argmax(x)]]
    side = R["upper"][C]
    U, L = C[side], C[~side]
    U, L = U[np.argsort(V[U, 0])], L[np.argsort(V[L, 0])]
    xs = np.linspace(x.min(), x.max(), 21)[1:-1]
    return np.interp(xs, V[U, 0], V[U, 1]) - np.interp(xs, V[L, 0], V[L, 1])  # + = apart


def test_lip_seal_closes_along_the_width_and_opens_again():
    """head.lip_seal 1: the contact ring's halves meet along the whole width (< 0.3 mm apart, never crossed), no
    skin quad of the lips turns over; a mouth-opening expression on top still opens it (it is measured without the
    expression); an explicit mouth_gap wins."""
    if not _gnm_ok():
        return
    from hifipushie import onemesh
    g = base._gnm_data()
    b = humans.spec(age=40, sex=1.0, seed=None, skin=False, source="human")["base"]
    b["head"].pop("mouth_gap", None)
    got = {}
    for seal, ex in ((0.0, None), (1.0, None), (1.0, {"lower_face_region_001": 1.0})):
        bt = copy.deepcopy(b)
        bt["head"]["lip_seal"] = seal
        if ex:
            bt["head"]["expression"] = ex
        got[(seal, bool(ex))] = np.asarray(onemesh.head_template(bt)["carry"]["V"], float)
    g0, g1, g2 = (_contact_gaps(got[k]) for k in ((0.0, False), (1.0, False), (1.0, True)))
    assert g0.mean() > 0.002 and g1.max() < 0.0003 and g1.min() > -0.00005, (g0.mean(), g1.min(), g1.max())
    assert g2.mean() > 0.001  # opens again
    Q = gnmloops._raw()["quads"]
    lips = (np.asarray(g["groups"]["upper_lip"]) > 0.5) | (np.asarray(g["groups"]["lower_lip"]) > 0.5)
    Q = Q[lips[Q].any(1) & np.asarray(g["skin"], bool)[Q].all(1)]
    X0 = got[(0.0, False)]  # (GNM's near-degenerate commissure quads, < 0.15 mm2, turn with any change at all: the
    # mouth_corner slider and humanfit.integrity's 6-face allowance know them)
    Q = Q[0.5 * np.linalg.norm(np.cross(X0[Q[:, 2]] - X0[Q[:, 0]], X0[Q[:, 3]] - X0[Q[:, 1]]), axis=1) > 1.5e-7]
    assert int((np.einsum("ij,ij->i", _normals(got[(0.0, False)], Q), _normals(got[(1.0, False)], Q)) < 0).sum()) == 0


def test_lip_seal_holds_across_identities():
    """The seal over a spread of identities (wide seeds, both sexes, and a wide-open rest mouth from a lower-face
    expression baked into the identity's starting shape): humanfit.integrity unbroken (no lip face turned, no edge
    stretched past its limit) and the lips in contact."""
    if not _gnm_ok():
        return
    from hifipushie import onemesh
    cases = [(s, sx) for s, sx in ((1, 0.0), (2, 1.0), (5, 0.0), (8, 1.0))]
    for seed, sex in cases:
        b = humans.spec(age=35, sex=sex, seed=seed, skin=False, source="human")["base"]
        b["head"]["spread"] = 1.2
        b["head"].pop("mouth_gap", None)
        b["head"]["lip_seal"] = 1.0
        st = humanfit.state(b)
        integ = humanfit.integrity(b, st)
        assert not [x for x in integ["broken"] if "lip" in x or "face" in x], (seed, integ["broken"])
        gp = _contact_gaps(np.asarray(onemesh.head_template(b)["carry"]["V"], float))
        assert gp.max() < 0.0005, (seed, gp.max())


def test_sealed_mouth_has_no_pocket_or_slit_in_the_field():
    """The built field (base.surface: what every mesher meshes) of a sealed mouth: inside all the way from the lips'
    front to 6 mm behind the contact, at 15 places across the width, every 0.25 mm (finer than the dressed ~1 mm
    meshing). Before base._sealed_field the touching lips closed a pocket of 'outside' behind the seam (Tess: a row of
    pits and fragments along the seam, in clay too)."""
    if not _gnm_ok():
        return
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "spikes", "facesliders"))
    import seam
    for seed, sex in ((1, 0.0), (5, 0.0), (8, 1.0)):
        sp = humans.spec(age=35, sex=sex, seed=seed, skin=False, source="human")
        sp["base"]["head"]["spread"] = 1.2
        sp["base"]["head"].pop("mouth_gap", None)
        sp["base"]["head"]["lip_seal"] = 1.0
        assert seam.check(sp, log=lambda *a: None) == 0, seed


def test_fit_window_follows_sex():
    lo, hi = faceslide.fit_window("eye_crease_height", 0.0)
    assert hi == 1.5 and lo > -0.5  # a woman's crease may reach its limit
    assert faceslide.fit_window("eye_crease_height", 1.0) == (-1.0, 1.0)
    assert faceslide.fit_window("brow_ridge", 0.0)[0] < -1.0
    assert faceslide.fit_window("eye_hood", 0.0) == (-1.0, 1.0)


if __name__ == "__main__":
    test_symmetric_and_ranged()
    test_no_fold_or_slot_at_the_extremes()
    test_slider_recovered_from_a_render()
    print("ok")
