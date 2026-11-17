"""R3f-12 (C511): a collar's roll is a FOLD; a fold lies in flat cloth only where the roll's turning seen in the stand
and in the fall cancel (cut_shape.crease); their sum is the angle defect a cone point is made of. And the cut's neck
girth ring is the collar alone (draft_girths: CROSSED, twins), not the fronts below it."""
import numpy as np

from hifipushie.cut_shape import CONE_MAX_DEG, cone_points, crease

NR, NC, KS = 9, 41, 4
GAP = 0.003


def _folded(bend):
    """A stand (a vertical strip, x across, z up to the roll) and its fall folded back down over it GAP behind; the
    roll at z = H - bend * smooth |x| (bend 0: straight). The fall is the stand mirrored about the roll row (a crease
    that is exact only for a straight roll)."""
    x = np.linspace(-0.1, 0.1, NC)
    roll = 0.04 - bend * np.sqrt(x ** 2 + 0.01 ** 2)
    X = np.zeros((NR, NC, 3))
    for r in range(KS + 1):
        X[r] = np.c_[x, np.zeros(NC), roll * r / KS]
    for r in range(KS + 1, NR):
        k = r - KS
        X[r] = np.c_[x, np.full(NC, GAP * min(k, 1)), roll - roll * k / KS]
    F = []
    for r in range(NR - 1):
        for c in range(NC - 1):
            i = r * NC + c
            F += [[i, i + 1, i + NC + 1], [i, i + NC + 1, i + NC]]
    return X.reshape(-1, 3), np.asarray(F)


def test_a_straight_fold_has_no_cone_point_a_bent_roll_has_twice_its_turn():
    V, F = _folded(0.0)
    assert all(abs(c[2]) < 1.0 for c in cone_points(V, F, (NR, NC, KS))), cone_points(V, F, (NR, NC, KS))
    cr = crease(V, (NR, NC, KS))
    assert abs(cr["stand_turn_deg"]) < 1 and abs(cr["fall_turn_deg"]) < 1, cr
    V, F = _folded(0.3)  # (the roll peaks at CB and turns down either side: ~2 x atan(0.3) = 33 deg in the stand)
    cr = crease(V, (NR, NC, KS))
    assert 10 < cr["stand_turn_deg"] and 10 < cr["fall_turn_deg"], cr  # (the folded fall turns WITH the stand: no flare)
    top = cone_points(V, F, (NR, NC, KS))[0]
    assert top[0] == KS and abs(top[1] - NC // 2) <= 2 and abs(top[2]) > CONE_MAX_DEG, top


def test_the_cuts_neck_ring_is_the_collar_alone():
    from hifipushie import draft_girths as dg
    from test_draft_own import _tube
    tp = {"a": ["len"], "b": ["len"], "c": ["len", "waist"], "u": ["len", "waist"]}
    B, s3 = _tube({"a": 0.44, "b": 0.45, "c": 0.38, "u": 0.38}, tp)
    for p in ("c", "u"):  # (a collar and its undercollar: one toile region, cut twice)
        B["pieces"][p]["P3"] = [[0.0, 0.1, 1.5], [0.1, 0.0, 1.5], [0.0, -0.1, 1.5]]
    drafted = dg.rows(B, s3, {})[0]["value"]
    assert "a " in drafted, drafted  # (a drafted pattern's declared ring: unchanged)
    B["girth_ring"] = dg.CROSSED
    r = dg.rows(B, s3, {})[0]
    assert "waist: pattern 380 mm" in r["value"] and "[c 380]" in r["value"] and "OPEN" in r["value"], r
    assert dg.twins(B, {"c", "u"}, "u") == {"c"} and dg.twins(B, {"a", "b"}, "b") == set()
