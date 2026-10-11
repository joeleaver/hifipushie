"""The face ruler on clay pictures of known GNM heads: what it reads off the pictures against the mesh truth."""
import numpy as np
import pytest

from hifipushie import assets, face_ruler as fr, gnm_mm

try:
    assets.pack("gnm")
    HAVE = True
except Exception:  # noqa: BLE001
    HAVE = False
pytestmark = pytest.mark.skipif(not HAVE, reason="GNM asset pack not installed")
KINDS = ("front", "3q", "profile")


def _views(c, kinds=KINDS, **kw):
    B = fr.gnm_head(c)
    return [{"img": fr.clay(B, fr.camera(k)), "cam": fr.camera(k), "kind": k, "style": "clay", **kw} for k in kinds]


def _pair(seed=3):
    rng = np.random.default_rng(seed)
    cA = 0.6 * rng.normal(size=170)
    moves = {"pupils_apart": 4.0, "chin_forward": 3.0, "tip_forward": -2.0, "jaw_width": 6.0}
    cB = cA + sum(v * gnm_mm.direction(k) for k, v in moves.items())
    return cA, cB, moves


def test_observations_move_as_their_jacobian_says():
    cA, cB, _ = _pair()
    cB = cA + 0.3 * (cB - cA)
    obs = fr.observe(fr.gnm_head(cA), _views(cB))
    assert len(obs) > 600
    o = np.array([ob["o"] for ob in obs])
    pred = np.array([ob["J"] for ob in obs]) @ (cB - cA)
    for typ in ("outline", "iris", "lips", "brows"):
        s = np.array([ob["type"] == typ for ob in obs])
        assert s.sum() >= 2, typ
        assert np.sqrt(np.mean((o[s] - pred[s]) ** 2)) < 0.3, typ
    assert np.sqrt(np.mean(o ** 2)) > 0.3          # there WAS something to read


def test_reads_the_gaps_that_were_made():
    cA, cB, moves = _pair()
    res = fr.read(fr.gnm_head(cA), _views(cB))
    got = {r["measure"]: r for r in res["gaps"]}
    for k, v in moves.items():
        assert abs(got[k]["gap"] - v) < (1.6 if k == "jaw_width" else 0.8), (k, got[k]["gap"])   # widths read +-1-1.7 mm
    for k in gnm_mm.NAMES:                          # the other measures were held by the mm: moves
        if k not in moves:
            assert abs(got[k]["gap"]) < (2.5 if k in gnm_mm.ORBIT[2:] else 1.5), (k, got[k]["gap"])   # (the orbit rims: no direct read on clay)
    assert [r["measure"] for r in res["gaps"][:4]] != [], res["gaps"][0]
    assert set(r["measure"] for r in res["gaps"][:5]) >= {"pupils_apart", "chin_forward"}
    assert '"mm:pupils_apart": +' in fr.text(res["gaps"])


def test_a_measure_the_pictures_do_not_show_is_not_read():
    cA, cB, _ = _pair()
    res = fr.read(fr.gnm_head(cA), _views(cB, kinds=("front",), hair=True))
    got = {r["measure"]: r for r in res["gaps"]}
    assert got["pupils_apart"]["read"] > 0.9 and abs(got["pupils_apart"]["gap"] - 4.0) < 0.5
    assert got["tip_forward"]["read"] < 0.5 and got["skull_back"]["err"] > 3.0     # a front picture: no profile in it
    assert "NOT READ" in fr.text(res["gaps"])


def test_a_fitted_camera_costs_the_absolute_sizes():
    """With each picture's shift / scale / roll left free the posterior error of a width grows; a local profile step
    (the lower lip against the upper) stays readable."""
    cA, cB, _ = _pair()
    head, views = fr.gnm_head(cA), _views(cB)
    obs = fr.observe(head, views)
    a = {r["measure"]: r for r in fr.solve(obs, head, views=views)["gaps"]}
    b = {r["measure"]: r for r in fr.solve(obs, head, views=views, cam_sd=fr.CAM_SD)["gaps"]}
    assert b["pupils_apart"]["err"] > 1.5 * a["pupils_apart"]["err"]
    assert b["skull_back"]["err"] > 1.3 * a["skull_back"]["err"]
    assert b["lower_lip_forward"]["err"] < 1.0
