"""The suit 7 round's fixes: a dropped trouser waist, the exact start clearance against a collider's triangles (both
ways, two-sided for cloth colliders), made pieces lifted over what is under them, and a broken start refused by the
crossing search (the search that took 17 GB on 2026-10-08).
Run: uv run python tests/test_suit7.py"""
import numpy as np

from hifipushie import cloth, pattern_blocks as pb

MM = {"neck": 370.5, "shoulderSlope": 29.0, "shoulderToShoulder": 463.9, "chest": 994.0, "waist": 776.3, "hips": 920.6,
      "seat": 972.2, "biceps": 340.2, "wrist": 148.6, "shoulderToElbow": 300.3, "shoulderToWrist": 570.0,
      "hpsToWaistBack": 545.0, "hpsToBust": 331.1, "highBust": 994.0, "waistToArmpit": 230.7, "waistToHips": 145.2,
      "waistToSeat": 245.2, "waistToFloor": 1109.3, "waistToKnee": 585.4, "head": 560.0, "waistToUpperLeg": 251.1,
      "inseam": 858.2}


def _grid(n, size, z):
    xs = np.linspace(-size / 2, size / 2, n)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    V = np.c_[X.ravel(), Y.ravel(), np.full(n * n, z)]
    q = np.arange(n * n).reshape(n, n)
    a, b, c, d = q[:-1, :-1].ravel(), q[1:, :-1].ravel(), q[1:, 1:].ravel(), q[:-1, 1:].ravel()
    return V, np.r_[np.c_[a, b, c], np.c_[a, c, d]]


def test_dropped_waist_is_drafted_from_its_own_line():
    assert pb.dropped_waist(MM, 0.0) == MM["waist"]
    g4, g8 = pb.dropped_waist(MM, 0.04), pb.dropped_waist(MM, 0.08)
    assert MM["waist"] < g4 < g8 < MM["hips"], (g4, g8)
    A = pb.trouser(MM, {})
    B = pb.trouser(MM, {"waist_drop": 0.07})
    assert abs((A["meta"]["rise"] - B["meta"]["rise"]) - 0.07) < 1e-9
    for nm in ("front", "back"):
        assert B["pieces"][nm]["wrap"].get("drop") == 0.07 and "drop" not in A["pieces"][nm]["wrap"]
        ha = A["pieces"][nm]["P"][:, 1].max() - A["pieces"][nm]["P"][:, 1].min()
        hb = B["pieces"][nm]["P"][:, 1].max() - B["pieces"][nm]["P"][:, 1].min()
        assert 0.05 < ha - hb < 0.09, (nm, ha - hb)  # the piece is that much shorter (the back's top is trued)
    wa = sum(pb.edge_length(A["pieces"][k], "cWaist>sideWaist") for k in ("front", "back"))
    wb = sum(pb.edge_length(B["pieces"][k], "cWaist>sideWaist") for k in ("front", "back"))
    assert wb > wa + 0.008, (wa, wb)  # drafted from the wider girth under the waist
    try:
        pb.trouser(MM, {"waist_drop": 0.3})
    except ValueError:
        pass
    else:
        raise AssertionError("a 30 cm drop accepted")


def test_start_is_cleared_of_the_colliders_triangles_both_ways():
    bV, bT = _grid(40, 0.4, 0.0)  # a fine collider sheet, facing +z
    # a ridge on the collider under the MIDDLE of a coarse cloth triangle: every cloth vertex and edge point clear
    ridge = np.hypot(bV[:, 0] - 0.013, bV[:, 1] - 0.007) < 0.006
    bV = bV.copy()
    bV[ridge, 2] += 0.0045
    X, F = _grid(6, 0.2, 0.005)  # 4 cm triangles 5 mm over the sheet: 0.5 mm over the ridge
    free = np.ones(len(X), bool)
    s0 = cloth._start_separation(X, F, bV, bT)
    assert s0 < 0.001, s0
    Y, n = cloth._clear_exact(X, F, free, bV, bT)
    s1 = cloth._start_separation(Y, F, bV, bT)
    assert n > 0 and s1 > 0.8 * cloth.EXACT_GAP, (n, s1)
    assert np.abs(Y - X).max() < 0.006
    # held vertices never move
    held = np.zeros(len(X), bool)
    held[::2] = True
    Z, _ = cloth._clear_exact(X, F, ~held, bV, bT)
    assert np.allclose(Z[held], X[held])


def test_cloth_collider_pushes_away_on_the_side_the_point_is_on():
    bV, bT = _grid(30, 0.3, 0.0)
    bT = bT[:, ::-1]  # wound the other way (an under garment's piece as its pattern lies): normals face -z
    X, F = _grid(8, 0.1, 0.001)  # cloth 1 mm ABOVE it
    Y, n = cloth._clear_exact(X, F, np.ones(len(X), bool), bV, bT, signed=0)
    assert n == len(X) and (Y[:, 2] > 0.0028).all(), (n, Y[:, 2].min())  # away on its own side, not through it
    Y2, _ = cloth._clear_exact(X, F, np.ones(len(X), bool), bV, bT)  # read as a closed body: out through it
    assert (Y2[:, 2] < 0).all()


def test_a_broken_start_is_refused_not_searched():
    X, F = _grid(12, 0.2, 1.0)
    M = {"F": F, "piece": np.zeros(len(X), int), "names": ["front"]}
    assert cloth._piece_crossings(X, M) == set()
    X2 = X.copy()
    X2[5] += [0.4, 0.3, -0.9]  # one vertex flung away: 1 m triangles
    try:
        cloth._piece_crossings(X2, M)
    except cloth.ClothError as e:
        assert "start is broken" in str(e) and "front" in str(e)
    else:
        raise AssertionError("a start with a 1 m triangle was searched")
    X3 = X.copy()
    X3[7, 2] = np.nan
    try:
        cloth._piece_crossings(X3, M)
    except cloth.ClothError:
        pass
    else:
        raise AssertionError("a start with NaN was searched")


def test_worn_clearing_moves_are_bounded():
    assert cloth.WORN_REACH <= 0.05 and cloth.WORN_STEP <= cloth.WORN_REACH


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v()
            print("ok", k)
