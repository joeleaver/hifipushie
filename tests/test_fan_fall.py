"""R3h (C513): the fall between the roll and its outer edge is a span (a ruled surface); toile_flap.fan_fall slides each
column's landing along the SAME outer edge so the roll and fall rows keep the least angle defect; and step 4's collar
row fails a collar with cone points over cut_shape.CONE_MAX_DEG (no flat piece lies there, whatever its grain)."""
import numpy as np

from hifipushie import toile_flap as tf
from hifipushie.cut_shape import CONE_MAX_DEG, defects
from hifipushie.toile_collar import GAP, KF, KS


class _Plane:
    """A body that is the plane y = 0 (the cloth on its +y side)."""
    def __init__(self):
        self.info = {}

    def grad(self, P):
        P = np.atleast_2d(P)
        return np.tile([0.0, 1.0, 0.0], (len(P), 1))

    def onto(self, P):
        P = np.array(P, float)
        P[..., 1] = 0.0
        return P

    def FD(self, P):
        return np.atleast_2d(P)[:, 1]


def _collar(nc=12, wobble=0.2):
    """A collar half on the plane: the stand a flat strip (z 0 -> 30 mm), the roll straight; the fall spans out to a
    curved outer edge (off the plane, fanning round), its landings bunched and spread unevenly along it (wobble)."""
    x = np.linspace(0.0, 0.11, nc)
    nr = KS + KF + 1
    X = np.zeros((nr, nc, 3))
    for r in range(KS + 1):
        X[r] = np.c_[x, np.zeros(nc), np.full(nc, 0.03 * r / KS)]
    u = np.linspace(0, 1, nc)
    u = u + wobble * np.sin(np.pi * u) * np.sin(2 * np.pi * u)
    L = np.c_[0.12 * np.sin(u), GAP + 0.04 * u ** 2, -0.03 * np.cos(u)]
    R = X[KS] + GAP * np.array([0.0, 1.0, 0.0])
    for r in range(KS + 1, nr):
        X[r] = R + (L - R) * (r - KS) / KF
    return X


def _fall_defect(X):
    nr, nc = X.shape[:2]
    F = tf._grid_faces(np.arange(nr * nc).reshape(nr, nc))
    return float(np.abs(defects(X.reshape(-1, 3), F, (nr, nc, KS))[KS:-1, 1:nc - 1]).sum())


def test_the_fall_fans_to_less_defect_on_the_same_outer_edge():
    t = _Plane()
    X = _collar()
    Y = tf.fan_fall(t, X.copy(), np.zeros(X.shape[1]))
    assert _fall_defect(Y) < 0.5 * _fall_defect(X), (_fall_defect(X), _fall_defect(Y))
    assert np.allclose(Y[:KS + 1], X[:KS + 1])  # (the stand and the roll untouched)
    oe = X[-1]  # (every landing still on the outer edge, in order)
    for p in Y[-1]:
        assert np.min(np.linalg.norm(np.diff(oe, axis=0)[:, None] * np.linspace(0, 1, 50)[None, :, None]
                                     + oe[:-1, None] - p, axis=2)) < 1e-3
    assert "before_deg" in t.info["fan"] and t.info["fan"]["after_deg"] <= t.info["fan"]["before_deg"] + 1e-6


def test_step4_collar_row_fails_cone_points():
    from hifipushie.toile_gate import collar_row

    class T:
        info = {"collar": {"outer_off_toile_mm": [0.1, 0.1], "lands_below_seam_cb_mm": 12.0,
                           "collar_point_miss_mm": 0.0, "stand_mm": 30, "fall_mm": 45, "roll_above_seam_cb_mm": 28,
                           "neck_half_mm": 100, "gorge_mm": 46, "roll_half_mm": 168, "outer_half_mm": 212,
                           "outer_behind_half_mm": 133},
                "collar_surface": {"cone_points": [[4, 13, 125.0], [4, 35, -5.0]], "cone_max_deg": CONE_MAX_DEG,
                                   "stand_turn_deg": 77.9, "fall_turn_deg": 8.4}}
    r = collar_row(T)[0]
    assert r["status"] == "FAIL" and "+125 deg" in r["why"] and "-5" not in r["why"] and r["back_to"] == "4", r
    T.info["collar_surface"]["cone_points"] = [[4, 13, 9.0]]
    assert collar_row(T)[0]["status"] == "PASS"
