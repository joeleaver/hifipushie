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
    # (3 cm squeezes the face's edges past the limit: refused, the input handed back, unless forced)
    nb2, rep2 = hf.nudge(b, "chin", move=[0.0, 0.0, -0.03])
    assert nb2 is b and "refused" in rep2
    nb2, rep2 = hf.nudge(b, "chin", move=[0.0, 0.0, -0.03], force=True)
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


def _front_cam(L):
    return {"r": [0.0, 0.0, 0.0], "t": [0.0, 0.0, 0.9], "f": 2400.0, "size": [1024, 1024], "centre": L[:68].mean(0).tolist(),
            "yaw": 0}


def test_neck_girth_ignores_the_face():
    """neck_circ is taken at one level on the body's own neck: a face fit (identity) can't move it (anthro's minimum
    up to the chin read the jaw: -9 cm "unintended" in every face fit)."""
    b = base()
    nb, _ = hf.solve(b, {"jaw_width": "+6", "chin_height": "+4"})
    m0, m1 = hf.state(b)["measures"], hf.state(nb)["measures"]
    assert 25 < m0["neck_circ"] < 50
    assert abs(m1["neck_circ"] - m0["neck_circ"]) < 1e-6


def test_hooded_lids_fitted_from_a_picture():
    """base.head.shape.hood lowers the upper lids' fold over the lid (upper lid landmarks down, lower lids where they
    were, no folds); fit_hood finds a known amount back from the upper lids' points in one picture."""
    b = base()
    st0 = hf.state(b)
    tb = hf._with_hood(b, 0.003)
    st1 = hf.state(tb)
    d = (st1["L"] - st0["L"]) * 1000
    assert (d[[37, 38, 43, 44], 2] < -0.8).all() and np.abs(d[[40, 41, 46, 47]]).max() < 0.05
    assert st1["measures"]["eye_height"] < st0["measures"]["eye_height"] - 0.8
    it = hf.integrity(tb, st1, st0)
    assert it["ok"] and it["numbers"]["folded_faces"] == 0, it
    cam = _front_cam(st1["L"])
    uv = hf.project(cam, st1["L"])
    views = [{"size": [1024, 1024], "yaw": 0, "points": {f"lm{i}": uv[i].tolist() for i in range(68)}}]
    nb, rep = hf.fit_hood(b, views, [cam])
    assert abs(rep["amount"] - 3.0) < 0.4, rep
    assert rep["rms_px_after"] < rep["rms_px_before"]


def test_outline_fit_is_symmetric_and_holds_features():
    """The silhouette of a wider-jawed face (another seed) through a front camera, as an outline below the eyes:
    the outline warp brings the silhouette to it, the face stays symmetric, the features (brows, eyes, nose, lips)
    stay put and nothing breaks."""
    b, target = base(seed=3), base(seed=3)
    target = hf.solve(target, {"jaw_width": "+10"})[0]
    stt, st0 = hf.state(target), hf.state(b)
    cam = _front_cam(st0["L"])
    P = np.asarray(stt["tpl"]["P"], float)
    head = P[:, 2] > stt["L"][8, 2] - 0.005
    uv = hf.project(cam, P[head])
    ye, yc = hf.project(cam, stt["L"][[36]])[0][1], hf.project(cam, stt["L"][[8]])[0][1]
    out = []
    for y in np.linspace(ye + 0.15 * (yc - ye), ye + 0.8 * (yc - ye), 9):
        row = uv[np.abs(uv[:, 1] - y) < 1.5]
        out += [[float(row[:, 0].min()), float(y)], [float(row[:, 0].max()), float(y)]]
    views = [{"size": [1024, 1024], "yaw": 0, "points": {}, "outline": out}]
    nb, rep = hf.fit_outline(b, views, [cam], rounds=3)
    miss = [r["miss_mm"][0] for r in rep["rounds"]]
    assert miss[-1] < 0.6 * miss[0], miss
    assert rep["integrity"]["ok"], rep["integrity"]
    L0, L1 = st0["L"], hf.state(nb)["L"]
    assert np.linalg.norm(L1[17:68] - L0[17:68], axis=1).max() < 1.5
    assert rep["integrity"]["numbers"]["asymmetry_mm"] < st0_asym(b) + 0.5


def test_hollow_cheeks_read_on_the_section():
    """base.head.shape.hollow dents the outer cheek under the cheekbone on both sides, and cheek_hollow (horizontal
    sections, the outer cheek's contour against its hull) reads it; a plain head reads ~0 there."""
    b = base()
    st0 = hf.state(b)
    h0 = hf.cheek_hollow(st0)
    assert max(h0.values()) < 1.0, h0
    b1 = hf.copy.deepcopy(b)
    b1["head"].setdefault("shape", {})["hollow"] = 0.005
    st1 = hf.state(b1)
    h1 = hf.cheek_hollow(st1)
    assert min(h1.values()) > max(h0.values()) + 1.0 and abs(h1["left"] - h1["right"]) < 0.8, (h0, h1)
    it = hf.integrity(b1, st1, st0)
    assert it["ok"] and it["numbers"]["folded_faces"] == 0, it


def test_jaw_angle_is_a_symmetric_bony_corner():
    """base.head.shape.jaw_angle stands the jaw's angle out (behind and under GNM's lm 3 / 13) and tucks the
    under-jaw: both sides alike, nothing folded, the face's landmarks above the jaw line held."""
    b = base()
    st0 = hf.state(b)
    b1 = hf.copy.deepcopy(b)
    b1["head"].setdefault("shape", {})["jaw_angle"] = 0.004
    st1 = hf.state(b1)
    P0, P1 = np.asarray(st0["tpl"]["P"]), np.asarray(st1["tpl"]["P"])
    d = np.linalg.norm(P1 - P0, axis=1)
    side = {}
    for nm, sg in (("right", -1), ("left", 1)):
        sel = (np.sign(P0[:, 0]) == sg) & (np.abs(P0[:, 0]) > 0.03)
        side[nm] = d[sel].max()
    assert 0.003 < min(side.values()) and abs(side["left"] - side["right"]) < 0.0008, side
    L0, L1 = st0["L"], st1["L"]
    assert np.linalg.norm(L1[17:48] - L0[17:48], axis=1).max() < 0.0005
    it = hf.integrity(b1, st1, st0)
    assert it["ok"] and it["numbers"]["folded_faces"] < hf.FOLD_LIMIT, it


def test_jawline_is_an_L_and_ears_nose_controls_hold_the_face():
    """base.head.shape.jawline carries the jaw line onto an L: the jaw-contour landmark that was level with the ear lobe
    (lm 3 / 13) goes down by centimetres, both sides alike, eyes / nose / lips landmarks stay, the mesh holds. ears
    and nose_tip move only their own part."""
    b = base()
    st0 = hf.state(b)
    b1 = hf.copy.deepcopy(b)
    b1["head"].setdefault("shape", {})["jawline"] = {"below_lobe": 0.055, "tuck": 0.004, "smooth": 5}
    st1 = hf.state(b1)
    L0, L1 = st0["L"], st1["L"]
    down = [float(L0[i][2] - L1[i][2]) for i in (3, 13)]
    assert min(down) > 0.004 and abs(down[0] - down[1]) < 0.002, down
    assert np.linalg.norm(L1[17:68] - L0[17:68], axis=1).max() < 0.001
    assert np.linalg.norm(L1[8] - L0[8]) < 0.002
    it = hf.integrity(b1, st1, st0)
    assert it["ok"], it["broken"]
    for key, val, moved in (("ears", {"out": 25, "size": 1.1, "blend": 0.02}, "ears"), ("nose_tip", 8, "nose")):
        b2 = hf.copy.deepcopy(b)
        b2["head"].setdefault("shape", {})[key] = val
        st2 = hf.state(b2)
        P0, P2 = np.asarray(st0["tpl"]["P"]), np.asarray(st2["tpl"]["P"])
        d = np.linalg.norm(P2 - P0, axis=1)
        reg = hf._regions(st0["tpl"])
        assert d[reg[moved]].max() > 0.002, (key, d.max())
        other = ~reg[moved] & reg["head"]
        assert d[other].max() < (0.012 if key == "ears" else 0.004), (key, d[other].max())
        assert np.linalg.norm(st2["L"][36:48] - L0[36:48], axis=1).max() < 0.0005
        assert hf.integrity(b2, st2, st0)["ok"], key
    b3 = hf.copy.deepcopy(b)
    b3["head"].setdefault("shape", {})["nose_tip"] = -8
    assert hf.state(b3)["L"][30][2] < L0[30][2] < hf.state(b2)["L"][30][2]


def test_a_broken_solve_is_refused():
    """A mouth widened until lip faces fold: solve hands back the base it was given (rep["refused"] says why, the
    broken result's integrity is reported), and returns the broken one only with force=True."""
    b = base()
    m0 = hf.state(b)["measures"]["mouth_width"]
    nb, rep = hf.solve(b, {"mouth_width": m0 * 1.35})
    if rep["integrity"]["ok"]:  # (if this face can take it, nothing to refuse: the guard is tested below directly)
        nb2, rep2 = hf._guarded(b, {"x": 1}, {"integrity": {"ok": False, "broken": ["test"], "warnings": []}}, False)
        assert nb2 is b and "refused" in rep2
        return
    assert nb is b and "refused" in rep and "BROKEN" in hf.report_text(rep)
    nbf, repf = hf.solve(b, {"mouth_width": m0 * 1.35}, force=True)
    assert nbf is not b and "refused" not in repf


def st0_asym(b):
    return hf.integrity(b)["numbers"]["asymmetry_mm"]


if __name__ == "__main__":
    if have():
        for fn in (test_measures_and_integrity, test_a_measure_is_met_and_the_rest_holds, test_adversarial_requests_come_back_honest,
                   test_nudge_moves_one_landmark, test_fit_back_a_known_face_from_images, test_neck_girth_ignores_the_face,
                   test_hooded_lids_fitted_from_a_picture, test_outline_fit_is_symmetric_and_holds_features,
                   test_hollow_cheeks_read_on_the_section, test_jaw_angle_is_a_symmetric_bony_corner,
                   test_a_broken_solve_is_refused):
            fn()
            print("ok", fn.__name__)
