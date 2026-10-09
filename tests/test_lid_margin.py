"""faceslide's lid_margin_upper / lid_margin_lower (eyedetail): forward along the eye's axis, zero on the rim and far
from it, upper / lower split, mirrored, one-sided, 0 by default (a face without them is unchanged)."""
import numpy as np

from hifipushie import faceslide as fs


def test_margin_fields():
    T = fs.template()
    F = fs.fields()
    X, rim = T["X"], T["rim"]
    for k, unit in (("lid_margin_upper", 0.6e-3), ("lid_margin_lower", 0.5e-3)):
        dR, dL = F[k]
        mag = np.linalg.norm(dL, axis=1)
        assert abs(mag.max() - unit) < 0.05e-3, (k, mag.max())
        assert np.abs(dL[:, :2]).max() < 1e-12  # forward only (GNM's +z)
        assert (dL[:, 2] >= 0).all()
        assert mag[rim].max() < 1e-12  # the rim stays seated on the ball
        assert mag[~T["ext"]].max() < 1e-12  # exterior skin only
        left = X[:, 0] > 0
        assert np.linalg.norm(dR[left], axis=1).max() < 1e-12 and np.linalg.norm(dL[~left], axis=1).max() < 1e-12
        # mirrored: the right eye's field is the left's through GNM's mirror map
        assert np.allclose(dR, dL[T["mirror"]] * [-1, 1, 1])
        # within 5 mm of the left rim
        from scipy.spatial import cKDTree
        d = cKDTree(X[rim[X[rim, 0] > 0]]).query(X)[0]
        assert mag[d > 5.0e-3].max() < 1e-12
    up, lo = F["lid_margin_upper"][1], F["lid_margin_lower"][1]
    on_up, on_lo = np.linalg.norm(up, axis=1) > 0, np.linalg.norm(lo, axis=1) > 0
    assert not (on_up & on_lo).any()
    mid = 0.5 * (T["lm"][42] + T["lm"][45])  # the corners
    assert np.median(X[on_up, 1]) > mid[1] > np.median(X[on_lo, 1])


def test_margin_values():
    assert fs.values({"lid_margin_upper": -1})["lid_margin_upper"] == (0.0, 0.0)  # one-sided
    assert fs.delta({}) is None and fs.delta({"lid_margin_lower": 0}) is None
    D = fs.delta({"lid_margin_upper": 1.0, "lid_margin_lower": [0.0, 1.0]})
    assert D is not None and D[:, 2].max() > 0.55e-3


if __name__ == "__main__":
    test_margin_fields()
    test_margin_values()
    print("ok")
