"""Measuring and fitting the one human mesh with guard rails (humanfit.py): uv run python tests/test_humanfit.py
(needs the gnm and makehuman packs). The adversarial cases must come back with honest residuals, never a broken mesh
that "meets the number"."""
import numpy as np

from hifipushie import assets, humanfit as hf


def have():
    try:
        assets.path("gnm", "gnm/shape/data/versions/v3_0/gnm_head.npz")
        from hifipushie import makehuman
        makehuman.body({"age": 25, "sex": 0.5})
        return True
    except Exception as err:
        print("skipped:", str(err)[:80])
        return False


def base(seed=3, **body):
    return {"body": {"source": "human", "age": 34, "sex": 1.0, **body}, "head": {"seed": seed, "spread": 0.5}}


def _moved_unasked(rep, asked):
    return max([r["rel"] for r in rep["side_effects"]["measures"] if r["measure"] not in asked and r["measure"] in hf.FACE] or [0.0])


def test_measures_and_integrity():
    st = hf.state(base())
    m = st["measures"]
    assert 150 < m["stature"] < 195 and 7 < m["heads"] < 8.6
    assert 52 < m["interocular"] < 70 and 120 < m["face_width"] < 165 and 20 < m["eye_width"] < 34
    assert abs(hf.value(m, "eye_width/face_width") - m["eye_width"] / m["face_width"]) < 1e-12
    it = hf.integrity(base(), st)
    assert it["ok"], it
    assert "INTEGRITY: ok" in hf.verdict(it)
    try:
        hf.state({"body": {"source": "makehuman"}, "head": {"source": "gnm"}})
        raise AssertionError("a grafted human was measured as one mesh")
    except ValueError:
        pass


def test_a_measure_is_met_and_the_rest_holds():
    b = base()
    nb, rep = hf.solve(b, {"nose_width": "+3"})
    r = rep["asked"]["nose_width"]
    assert r["met"] and abs(r["got"] - r["was"] - 3) < 0.8
    assert rep["integrity"]["ok"]
    assert _moved_unasked(rep, {"nose_width"}) <= hf.COLLATERAL + 0.5
    mv = rep["side_effects"]["moved"]
    assert mv["body_max_mm"] == 0 and mv["outside_region_share"] < 0.05
    assert nb["body"] == b["body"] and "identity" in nb["head"]


def test_adversarial_requests_come_back_honest():
    b = base()
    for want in ({"eye_width": "x3"}, {"chin_height": "+50"},
                 {"eye_width": "x1.6", "nose_width": "x0.5", "mouth_width": "x1.5", "jaw_width": "x0.7", "chin_width": "x1.6",
                  "face_height": "x0.8", "interocular": "x1.3", "philtrum": "x2", "lip_height": "x0.5", "brow_height": "x1.8"}):
        nb, rep = hf.solve(b, want)
        assert rep["integrity"]["ok"], (want, rep["integrity"])
        assert not all(r["met"] for r in rep["asked"].values()), want  # none of these is a plausible identity
        assert rep["plausibility"]["max_sigma"] <= max(hf.CLIP, np.abs(hf.identity(b)).max()) + 1e-6
        if len(want) == 1:
            assert rep["held_back"] < 1.0 and _moved_unasked(rep, set(want)) <= hf.COLLATERAL + 1.0
    # forced, the same request is allowed to go further (and says what it did to the rest)
    _, forced = hf.solve(b, {"eye_width": "x3"}, force=True)
    assert forced["asked"]["eye_width"]["got"] > rep_first(b)
    assert forced["side_effects"]["unintended"]


def rep_first(b):
    return hf.solve(b, {"eye_width": "x3"})[1]["asked"]["eye_width"]["got"]


def test_nudge_moves_one_landmark():
    b = base()
    L0 = hf.state(b)["L"]
    nb, rep = hf.nudge(b, "nose_tip", move=[0.0, -0.003, 0.002])
    assert np.abs(np.array(rep["got_mm"]) - [0, -3, 2]).max() < 0.4
    L1 = hf.state(nb)["L"]
    far = np.linalg.norm(L0[:68] - L0[30], axis=1) > 0.05
    assert np.linalg.norm(L1[:68] - L0[:68], axis=1)[far].max() < 0.0015
    assert rep["integrity"]["ok"]
    # past what the sliders can do: the rest is a correction layer, said so, and it survives a later change
    nb2, rep2 = hf.nudge(b, "chin", move=[0.0, 0.0, -0.03])
    assert rep2["by_correction_mm"] > 1.0 and abs(rep2["got_mm"][2] + 30) < 1.5
    assert nb2["head"]["shape"]["push_more"]
    nb3, _ = hf.solve(nb2, {"nose_width": "+1"})
    assert nb3["head"]["shape"]["push_more"] == nb2["head"]["shape"]["push_more"]


def _rigid(A, B):
    a, b = A - A.mean(0), B - B.mean(0)
    U, _, Vt = np.linalg.svd(a.T @ b)
    R = (U @ Vt).T
    return float(np.sqrt((((a @ R.T) - b) ** 2).sum(1).mean())) * 1000


def test_fit_back_a_known_face_from_images():
    """Two synthetic views (front, three-quarter) of another seed's landmarks: cameras and identity are fitted
    together, the reprojection ends under a pixel and the 3D landmarks land within 1.5 mm of the target's."""
    b, target = base(seed=3), base(seed=17)
    Lt, L0 = hf.state(target)["L"], hf.state(b)["L"]
    ctr = Lt[:68].mean(0).tolist()
    views = []
    for yaw, r in ((0, [0.03, 0.0, 0.0]), (40, [0.0, 0.05, 0.0])):
        cam = {"r": r, "t": [0.01, -0.02, 0.9], "f": 2400.0, "size": [1024, 1024], "centre": ctr, "yaw": yaw}
        uv = hf.project(cam, Lt)
        views.append({"size": [1024, 1024], "yaw": yaw, "points": {f"lm{i}": uv[i].tolist() for i in range(68)}
                      | {"eye.L": uv[68].tolist(), "eye.R": uv[69].tolist()}})
    nb, rep = hf.fit_views(b, views)
    assert all(v["rms_px"] < 1.0 for v in rep["views"]), rep["views"]
    L1 = hf.state(nb)["L"]
    assert _rigid(L1, Lt) < 1.5 < _rigid(L0, Lt), (_rigid(L0, Lt), _rigid(L1, Lt))
    # the skull, which no landmark sees, stays (it moved 16 mm before it was held)
    P0, P1 = hf.state(b)["tpl"]["P"], hf.state(nb)["tpl"]["P"]
    crown = P0[:, 2] > L0[19, 2] + 0.05
    assert np.linalg.norm(P1 - P0, axis=1)[crown].max() < 0.007
    # one frontal view alone: fits in the image, and says nothing about depth
    nb1, rep1 = hf.fit_views(b, views[:1])
    assert rep1["views"][0]["rms_px"] < 1.5


if __name__ == "__main__":
    if have():
        for fn in (test_measures_and_integrity, test_a_measure_is_met_and_the_rest_holds, test_adversarial_requests_come_back_honest,
                   test_nudge_moves_one_landmark, test_fit_back_a_known_face_from_images):
            fn()
            print("ok", fn.__name__)
