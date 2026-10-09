"""Macros measured on a picture (humanmeasure.py). uv run python tests/test_humanmeasure.py"""
import sys

import numpy as np

from hifipushie import assets, humanmacro as hm, humanmeasure as hx


def test_features_do_not_see_the_camera():
    """The point features are the same whatever the picture's scale, place and roll."""
    rng = np.random.default_rng(2)
    P = rng.normal(0, 40, (478, 2)) + [300, 300]
    P[468], P[473], P[152] = [270, 280], [330, 282], [301, 400]
    f0 = hx.features(P)["pts"]
    a = np.radians(17.0)
    R = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
    f1 = hx.features((P - 300) @ R.T * 2.3 + [800, 150])["pts"]
    assert np.abs(f0 - f1).max() < 1e-9


def test_model_and_sigmas():
    """The packaged regression speaks humanmacro's names; a measurement gives only the macros a picture can measure,
    each with a sigma no better than the calibration's (x SIGMA, floor 0.25)."""
    M = hx.model()
    assert M["names"] == list(hm.NAMES)
    rng = np.random.default_rng(1)
    P = rng.normal(0, 30, (478, 2)) + [300, 300]
    P[468], P[473], P[152] = [270, 280], [330, 282], [301, 400]
    r = hx.measure(np.full((600, 600, 3), 200, np.uint8), P, backdrop=False)
    assert r["used"] == "points" and "RENDERS" in r["note"]
    rms = dict(zip(M["names"], M["points_rms"]))
    assert r["macros"] and all(rms[k] < hx.CUT for k in r["macros"])
    assert all(v[1] >= 0.25 * hx.SIGMA - 1e-6 and v[1] >= rms[k] * hx.SIGMA - 0.011 for k, v in r["macros"].items())
    for k in ("jaw_angle", "chin_cleft", "forehead_slope"):       # a front picture's points cannot measure these
        assert k not in r["macros"]
    assert "jaw_width" in r["macros"] and "face_length" in r["macros"] and "brow_height" in r["macros"]


def test_a_wider_jaw_measures_wider():
    """Two rendered heads that differ by the jaw_width macro (+2 / -2 sigma, held): the detector's points on their
    renders measure them apart, the right way round. Needs the detector and the asset packs."""
    try:
        assets.pack("gnm")
        assets.pack("makehuman")
        from hifipushie import humanfit as hf, likeness as lk
        if not lk.detector_available():
            raise RuntimeError("no detector")
    except Exception as err:
        print("skipped:", str(err)[:80])
        return
    b = {"body": {"source": "human", "age": 34, "sex": 1.0}, "head": {"seed": 3, "spread": 0.3}}
    got = {}
    for z in (-2.0, 2.0):
        bb = hf._with_identity(b, hm.apply(hf.identity(b), {"jaw_width": z}, held=True))
        mesh = lk.model_mesh(bb)
        L = np.asarray(mesh["L"], float)
        cam = {"r": [0.0, 0.0, 0.0], "yaw": 0.0, "centre": L[:68].mean(0).tolist(), "t": [0.0, 0.0, 1.5], "f": 2000.0, "size": [640, 640]}
        im = lk.render(mesh, cam, (0.0, 0.0, 640.0, 640.0), px=640)[0].convert("RGB")
        d = lk.detect([im])[0]
        assert d is not None
        P = d["P"] if isinstance(d, dict) else d
        got[z] = hx.measure(np.asarray(im), np.asarray(P)[:, :2], backdrop=False)["macros"]["jaw_width"][0]
    assert got[2.0] - got[-2.0] > 1.5, got


if __name__ == "__main__":
    for k in sys.argv[1:] or [k for k in dict(globals()) if k.startswith("test_")]:
        globals()[k]()
        print("ok", k)
