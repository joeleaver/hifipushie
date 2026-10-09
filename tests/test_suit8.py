"""The suit 8 round: an under garment's collar fall pressed down under a worn top (pressed(fall=), _fall_down), a notched
collar draped from the neck's side forward (_draped_ends), the keys' defaults.
Run: uv run python tests/test_suit8.py"""
import numpy as np
from scipy.spatial import cKDTree

from hifipushie import cloth


def test_under_fall_is_for_worn_tops():
    assert cloth.under_fall({"worn_top": True}) == cloth.UNDER_FALL
    assert cloth.under_fall({}) is None  # trousers over a shirt: nothing changes (their cache keys too)
    assert cloth.under_fall({"worn_top": True, "under_fall": False}) is None
    assert cloth.under_fall({"under_fall": 0.006}) == 0.006


def _fall_case(nz):
    """A fall of 20 vertices in a row, 0..38 mm from its fold, 20 mm over a body whose normal has `nz` upward."""
    n = 20
    d0 = np.linspace(0.0, 0.038, n)
    V = np.c_[d0, np.zeros(n), np.full(n, 0.02)]
    vn = np.tile([np.sqrt(1 - nz * nz), 0.0, nz], (n, 1))
    bodyV = np.c_[d0, np.zeros(n), np.zeros(n)]
    M = {"folds": [{"piece": "collar", "_g": {"rows": [{"v": np.arange(n)}], "d0": d0}},
                   {"piece": "front.L", "_g": {"rows": [{"v": np.arange(n)}], "d0": d0}}]}
    res = {"pieces": {"pieces": {"collar": {"wrap": {"to": "neck"}}, "front.L": {"wrap": {"to": "torso"}}}}}
    return cloth._fall_down(res, M, V, None, vn, cKDTree(bodyV), np.full(n, 0.02), 0.007), d0


def test_fall_is_pressed_onto_the_shoulder_not_the_nape():
    mv, d0 = _fall_case(0.95)  # the top of the shoulder
    assert mv[d0 < cloth.FALL_KEEP].max() == 0.0  # the roll next to the fold stays as made
    far = d0 > 2 * cloth.FALL_KEEP + 1e-6
    assert np.allclose(mv[far], 0.02 - 0.007), mv[far]  # to `to` off the body
    assert (np.diff(mv) >= -1e-12).all()  # eased in between
    mv2, _ = _fall_case(0.1)  # behind the neck the body faces back: the fall hangs, nothing presses it into its stand
    assert mv2.max() == 0.0


def test_collar_is_draped_from_the_necks_side():
    names = ["back", "collar"]
    piece = np.r_[np.zeros(5, int), np.ones(10, int)]
    M = {"names": names, "piece": piece}
    end_w = np.r_[np.zeros(6), [0.2, 0.6, 1.0, 1.0]]
    end_u = np.r_[[-0.16, -0.12, -0.09, -0.065, -0.05, -0.03, -0.02, -0.005, 0.02, 0.05]]
    Bp = {"open_lay": {"collar": {"end_w": end_w, "end_u": end_u}}}
    made = cloth._draped_ends({"collar_ends": "made"}, Bp, M)
    assert len(made) == 0
    dr = cloth._draped_ends({"collar_ends": "draped"}, Bp, M)  # from END_BACK before the meeting point
    assert list(dr) == [5 + i for i in range(10) if end_u[i] >= -cloth.END_BACK], dr
    only = cloth._draped_ends({"collar_ends": {"back": 0.0}}, Bp, M)  # the ends alone
    assert list(only) == [12, 13, 14], only
    assert len(cloth._draped_ends({"collar_ends": "draped"}, {}, M)) == 0 and len(cloth._draped_ends({}, Bp, M)) == 0  # no notched collar: nothing; the default is made


def test_draped_part_starts_closed():
    M = {"names": ["collar"], "piece": np.zeros(6, int)}
    end_u = np.array([-0.20, -0.13, -0.10, -0.07, -0.02, 0.03])
    Bp = {"open_lay": {"collar": {"end_w": np.zeros(6), "end_u": end_u}}}
    w = cloth._open_share({"collar_ends": "draped"}, Bp, M)
    assert w[0] == 1.0 and 0.0 < w[2] < 1.0  # the held band opens in full in its middle, less toward the draped part
    assert (w[end_u >= -cloth.END_BACK] == 0.0).all()  # what is draped starts as made (closed)
    assert (np.diff(w) <= 1e-12).all()
    assert (cloth._open_share({}, {}, M) == 1.0).all()


def test_worn_top_pad_rule():
    assert 1.0 < cloth.PAD_OVER_WORN < 1.5


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v()
            print("ok", k)
