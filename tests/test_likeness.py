"""The likeness checklist's measures on a synthetic face with known values (no detector, no model needed), the
checklist's own consistency, and the staged fit's wants. Run: uv run python -m pytest tests/test_likeness.py"""
import numpy as np
import pytest

from hifipushie import likeness as lk


def face(rot_deg=0.0, scale=1.0, tilt=5.0, arch=4.0, hump=3.0):
    """A synthetic 478-point face in picture pixels: nasion at (0, 0), menton at (0, 100) (the face frame's y down)."""
    P = np.zeros((478, 2))
    P[168] = [0, 0]
    P[152] = [0, 100]
    t = np.tan(np.radians(tilt))
    for inner, outer, s in ((133, 33, -1), (362, 263, 1)):        # image left = the subject's right
        P[inner] = [s * 15, 40]
        P[outer] = [s * 45, 40 - 30 * t]                            # the outer corner `tilt` degrees up
    P[159], P[145] = [-30, 36], [-30, 44]                          # lids: 8 px opening
    P[386], P[374] = [30, 36], [30, 44]
    P[468], P[473] = [-30, 40], [30, 40]
    th = np.linspace(0, 2 * np.pi, len(lk.OVAL), endpoint=False)  # the oval: a circle of radius 60 round (0, 50)
    P[lk.OVAL] = np.c_[60 * np.sin(th), 50 - 60 * np.cos(th)]
    P[168], P[152] = [0, 0], [0, 100]                              # (the oval holds 152: keep the frame's ends)
    for line, s in (([107, 66, 105, 63, 70], -1), ([336, 296, 334, 293, 300], 1)):
        x = np.linspace(10, 50, 5)
        P[line] = np.c_[s * x, 25 - arch * (1 - ((x - 30) / 20) ** 2)]
    # the dorsum seen from the side: nasion -> tip along x, a hump of `hump` px toward where the nose points (+x)
    line = [168, 6, 197, 195, 5, 4, 1]
    u = np.linspace(0, 1, len(line))
    P[line] = np.c_[30 * u, 60 * u]
    P[line, 0] += hump * np.sin(np.pi * u)
    P[129], P[358] = [-5, 55], [-5, 55]                            # wings behind the tip
    P[1], P[2], P[0] = [30, 60], [20, 66], [20, 80]               # tip, subnasale, upper lip
    c = np.radians(rot_deg)
    R = np.array([[np.cos(c), -np.sin(c)], [np.sin(c), np.cos(c)]])
    return (P @ R.T) * scale + [300, 200]


def test_tilt_and_rotation():
    for rot in (0.0, 20.0, -35.0):
        s = lk.Side(face(rot_deg=rot))
        assert lk.value(s, {"kind": "tilt", "pairs": [[[133], [33]], [[362], [263]]]}, 1.0) == pytest.approx(5.0, abs=1e-6)


def test_dist_width_ratio_level():
    s = lk.Side(face(scale=2.0, rot_deg=10))
    assert lk.value(s, {"kind": "dist", "a": [133], "b": [362], "axis": "x"}, 0.5) == pytest.approx(30.0)
    assert lk.value(s, {"kind": "dist", "pairs": [[[159], [145]], [[386], [374]]], "axis": "y"}, 1.0) == pytest.approx(16.0)
    w0 = 2 * np.sqrt(60 ** 2 - 10 ** 2)                               # the circle's chord 10 px above its centre
    w = lk.value(s, {"kind": "width", "level": [468, 473]}, 1.0)
    assert w == pytest.approx(2 * w0, rel=0.01)
    r = lk.value(s, {"kind": "ratio", "num": {"kind": "dist", "a": [168], "b": [152], "axis": "y"},
                     "den": {"kind": "width", "level": [468, 473]}}, 1.0)
    assert r == pytest.approx(100 / w0, rel=0.01)
    assert lk.value(s, {"kind": "level", "pts": [133, 362], "from": [168], "to": [152]}, 1.0) == pytest.approx(0.4)


def test_arch_angle_bow():
    s = lk.Side(face(arch=4.0, hump=3.0))
    assert lk.value(s, {"kind": "arch", "pairs": [[107, 66, 105, 63, 70], [336, 296, 334, 293, 300]]}, 1.0) == pytest.approx(4.0, abs=0.05)
    a = lk.value(s, {"kind": "angle", "a": [1], "vertex": [2], "b": [0]}, 1.0)
    u, w = np.array([10, -6]), np.array([0, 14])
    assert a == pytest.approx(np.degrees(np.arccos(u @ w / np.linalg.norm(u) / np.linalg.norm(w))))
    b = lk.value(s, {"kind": "bow", "line": [168, 6, 197, 195, 5, 4, 1]}, 1.0)
    chord = np.array([30, 60]) / np.hypot(30, 60)
    assert b == pytest.approx(3.0 * abs(chord[1]), rel=0.05)     # the hump's height across the chord, + = a hump
    assert lk.value(lk.Side(face(hump=-3.0)), {"kind": "bow", "line": [168, 6, 197, 195, 5, 4, 1]}, 1.0) < 0


def test_landmark_fallback():
    P = face()
    lm = np.full((70, 2), np.nan)
    for i, m in enumerate(lk.MP68):
        lm[i] = P[m]
    lm[68], lm[69] = P[473], P[468]
    s = lk.Side(None, lm)
    assert lk.value(s, {"kind": "dist", "a": [133], "b": [362], "axis": "x"}, 1.0) == pytest.approx(30.0)
    assert lk.value(s, {"kind": "dist", "a": [468], "b": [473], "axis": "x"}, 1.0) == pytest.approx(60.0)
    with pytest.raises(lk.Unmeasurable):
        lk.value(s, {"kind": "width", "level": [468, 473]}, 1.0)
    with pytest.raises(lk.Unmeasurable):
        lk.value(s, {"kind": "dist", "a": [129], "b": [358], "axis": "x"}, 1.0)   # wings: not in the 68


def test_checklist_is_consistent():
    stages = [s["name"] for s in lk.stage_names()]
    assert stages[:4] == ["proportions", "widths", "structure", "eyes"]  # big to small
    ids = set()
    s = lk.Side(face())
    for it in lk.checklist():
        assert it["id"] not in ids
        ids.add(it["id"])
        assert it["stage"] in stages and it["look"] and it["views"]
        assert set(it["views"]) <= {"front", "three_quarter", "profile"}
        if it["measure"]["kind"] == "judge":
            assert it["tol"] is None
            continue
        assert it["tol"] > 0
        if it["measure"]["kind"] in lk.SPECIAL:
            continue
        try:
            v = lk.value(s, it["measure"], 1.0)
            assert isinstance(v, float)          # (nan where the synthetic face has a zero-size feature)
        except lk.Unmeasurable:
            pass
    first = [stages.index(it["stage"]) for it in lk.checklist()]
    assert first == sorted(first)                                      # the file lists items in artists' order


def test_jaw_L_measures():
    """A traced L: a ramus 10 deg off vertical, a 120 deg corner, a straight border; then a soft diagonal."""
    from hifipushie import likeness_shape as ls
    ex, ey = np.array([1.0, 0]), np.array([0, 1.0])
    g = np.array([100.0, 200.0])
    up = np.array([-np.sin(np.radians(10)), -np.cos(np.radians(10))])  # from the corner up the ramus
    fw = np.array([np.cos(np.radians(-20)), -np.sin(np.radians(-20))])  # forward and down 20 deg... (angle to the ramus)
    ram = [g + up * t for t in np.linspace(60, 0, 8)]
    bor = [g + fw * t for t in np.linspace(0, 80, 10)][1:]
    m = ls.jaw_measures(np.array(ram + bor), ex, ey, 1.0, lobe=g + up * 70, mouth=g - [0, 15.0], neck=None)
    assert m["ramus_angle"] == pytest.approx(10.0, abs=0.5)
    ang = np.degrees(np.arccos(up @ fw))
    assert m["gonial_angle"] == pytest.approx(ang, abs=0.5)
    assert m["border_straightness"] < 0.5
    assert m["gonion_below_mouth"] == pytest.approx(15.0, abs=0.5)
    assert m["gonion_below_lobe"] == pytest.approx(70 * np.cos(np.radians(10)), abs=0.5)
    soft = np.array([g + [t, 0.6 * t] + [0, -8 * np.sin(np.pi * t / 100)] for t in np.linspace(-60, 40, 18)])
    assert ls.jaw_measures(soft, ex, ey, 1.0)["gonial_angle"] > m["gonial_angle"] + 25


def test_light_fit_and_residual():
    """A Lambert face under a known light: the light comes back; a dent the 'photo' has and the model hasn't reads
    darker than predicted."""
    from hifipushie import likeness_shape as ls
    H, W = 80, 80
    yy, xx = np.mgrid[0:H, 0:W] / 40.0 - 1
    nz = -np.sqrt(np.clip(1 - xx ** 2 - yy ** 2, 0.05, 1))
    N = np.dstack([xx, yy, nz])
    N /= np.linalg.norm(N, axis=-1, keepdims=True)
    w = np.array([-0.1, -0.2, -0.5])
    Y = 0.1 + N @ w
    mask = (xx ** 2 + yy ** 2) < 0.8
    Yd = Y.copy()
    dent = ((xx - 0.3) ** 2 + yy ** 2) < 0.02
    Yd[dent] *= 0.7
    c0, wf, rms = ls.fit_light(Yd, N, mask)
    assert c0 == pytest.approx(0.1, abs=0.02) and np.allclose(wf, w, atol=0.03)
    R = ls.residual(Yd, N, c0, wf, mask, 1.0)
    assert np.nanmean(R[dent]) < -0.1 and abs(np.nanmean(R[mask & ~dent])) < 0.03


def test_model_jaw_finds_a_step_and_not_a_smooth_slope():
    from hifipushie import likeness_shape as ls
    H, W = 100, 100
    zb = np.full((H, W), 1.0)
    zb[60:, :] = 1.05                                   # a 5 cm step at row 60: the jaw over the neck
    Q = [[x, 58.0] for x in range(20, 80, 5)]          # a trace 2 px above it
    got = ls.model_jaw(Q, zb, 1.0, (0, 0, W, H), 10.0, 1.0)
    assert got is not None and np.allclose(got[:, 1], 59.5, atol=1.0)
    zb2 = np.full((H, W), 1.0)
    nrm = np.zeros((H, W, 3))
    nrm[..., 2] = -1.0                                  # a flat front: no edge anywhere
    assert ls.model_jaw(Q, zb2, 1.0, (0, 0, W, H), 10.0, 1.0, nrm) is None


def test_points_file_round_trip(tmp_path, monkeypatch):
    from hifipushie import likeness_shape as ls, store
    monkeypatch.setattr(store, "HOME", tmp_path)
    (tmp_path / "m").mkdir()
    ls.set_points("m", "/x/a.png", {"gonion.R": [1, 2]}, {"jaw.R": [[0, 0], [1, 1]]}, by="test")
    ls.set_points("m", "/x/a.png", {"ear_lobe.R": [3, 4], "gonion.R": None})
    v = ls.load_points("m")["/x/a.png"]
    assert v["points"] == {"ear_lobe.R": [3, 4]} and v["lines"]["jaw.R"] == [[0, 0], [1, 1]]


def test_profile_items_inferred_from_three_quarter():
    it = next(i for i in lk.checklist() if i["id"] == "nasolabial_angle")
    assert lk._allowed(it, "three_quarter", ["front", "three_quarter"]) == (True, True)
    assert lk._allowed(it, "three_quarter", ["front", "three_quarter", "profile"]) == (False, False)
    assert lk._allowed(it, "front", ["front"]) == (False, False)


def test_reference_brief_shape():
    from hifipushie import likeness_brief as lb
    b = lb.reference_brief("figure", "test")
    ids = [s["id"] for s in b["shots"]]
    assert {"front", "profile_left", "three_quarter_left", "front_raking", "figure_front"} <= set(ids)
    for s in b["shots"]:
        assert s["prompt"].startswith(b["common"]["prompt"]) and s["must_show"] and s["light"] in ("even", "raking")
    covered = {i for s in b["shots"] for i in s["purpose"]}
    assert {it["id"] for it in lk.checklist() if it["measure"]["kind"] != "judge"} <= covered | {"stature"}


def test_expression_on_a_reference_goes_to_the_pose():
    pics = [{"view": "front", "expressions": {"squint": 0.7}}, {"view": "three_quarter", "expressions": {"smile": 0.5}}]
    b = lk.expression_bias(pics)
    assert "eye_opening" in b and "brow_eye" in b and "mouth_corner_tilt" not in b     # front pictures only
    rows = [{"id": "eye_width", "view": "front", "score": 3.0, "miss": 2.5},
            {"id": "brow_eye", "view": "front", "score": 3.0, "miss": 2.5}]
    want, _, _ = lk.stage_wants({"rows": rows}, "brows", skip=b)
    assert want == {}                                                  # the squinted brow isn't an identity ask
    assert lk.EXPR_LEVERS["eye_opening"][0].startswith("pose.")
    for ids in lk.EXPR_BIAS.values():
        assert all(any(it["id"] == i for it in lk.checklist()) for i in ids)


def test_nested_levers():
    base = {"head": {"shape": {"hollow": 0.005}}}
    nb, _ = lk.with_lever(base, "shape.jawline.below_lobe", 0.05)
    assert nb["head"]["shape"]["jawline"] == {"below_lobe": 0.05} and "jawline" not in base["head"]["shape"]
    assert lk.lever_value(nb, "shape.jawline.below_lobe", 0.045) == 0.05
    assert lk.lever_value(base, "shape.jawline.forward", 0.004) == 0.004
    assert lk.lever_value(base, "shape.hollow", 0.0) == 0.005


def test_stage_wants_pin_earlier_stages():
    rows = [{"id": "face_height", "view": "front", "score": 2.0, "miss": -4.0},
            {"id": "eye_width", "view": "front", "score": 3.0, "miss": 2.5},
            {"id": "pupil_distance", "view": "front", "score": 0.5, "miss": 0.4},
            {"id": "canthal_tilt", "view": "front", "score": 2.0, "miss": 4.0},
            {"id": "eye_width", "view": "three_quarter", "score": 9.0, "miss": 9.0}]
    want, pins, gaps = lk.stage_wants({"rows": rows}, "eyes")
    assert want == {"eye_width": "-2.50"}                              # asked by the miss, front view only
    assert pins == {"face_height": "+0"}                               # the earlier stage's measure held
    assert any("Canthal tilt" in g for g in gaps)                      # no solver measure: said, not guessed


def _synthetic_contour(chin=0.0, nose=0.0):
    """A far-side contour in picture px (1 mm / px), top to bottom: forehead, brow bump, orbit dip, cheek, a notch
    between two lips, a chin corner, the under-jaw going back."""
    v = np.arange(-60.0, 150.0, 1.0)
    c = 40.0 - 0.15 * np.abs(v + 12)                       # forehead sloping back, brow peak at v = -12
    c += 6.0 * np.exp(-((v + 12) / 6.0) ** 2) - 5.0 * np.exp(-((v - 10) / 8.0) ** 2)
    c -= np.clip(v - 40, 0, None) * 0.12                   # the lower face falls in
    c += 2.0 * np.exp(-((v - 86) / 3.0) ** 2) + 1.5 * np.exp(-((v - 100) / 3.0) ** 2) - 1.0 * np.exp(-((v - 93) / 2.0) ** 2)
    c += chin * np.exp(-((v - 132) / 10.0) ** 2)
    c -= np.clip(v - 136, 0, None) * 1.3                   # under the jaw
    return v, c


def test_profile_contour_measures():
    from hifipushie import likeness_profile as lp
    lv = {"brow": -14.0, "sn": 68.0, "sto": 94.0, "chin": 138.0, "nasion": 0.0}
    v, c = _synthetic_contour()
    kp = lp.keypoints(v, c, lv)
    assert abs(kp["brow"][0] + 12) <= 1.5 and abs(kp["sto"][0] - 93) <= 1.5      # found on the contour, not at the levels
    assert 128 <= kp["chin"][0] <= 140                                            # the corner before the under-jaw
    m0 = lp.measures(kp)
    assert m0["brow_ridge"] > 4 and m0["upper_lip"] > 1.0 and m0["lower_lip"] > 0.5
    v2, c2 = _synthetic_contour(chin=6.0)
    m1 = lp.measures(lp.keypoints(v2, c2, lv))
    assert 3.0 < m1["chin_projection"] - m0["chin_projection"] < 7.5              # a stronger chin reads stronger
    # no notch between the lips -> the lip items are not invented
    vs, cs = v, 40.0 - 0.1 * np.abs(v + 12)
    assert "upper_lip" not in lp.measures(lp.keypoints(vs, cs, lv))
    # the nose's own contour: tip, base, bridge bow (a hump reads +)
    vn = np.arange(0.0, 70.0, 1.0)
    cn = 5.0 + 0.4 * vn - np.clip(vn - 56, 0, None) * 1.6
    nk = lp.nose_keypoints(vn, cn, base_v=68.0, nasion_v=0.0)
    mn = lp.measures({}, nk, (vn, cn), (v, c))
    assert abs(nk["tip"][0] - 56) <= 1 and mn["nose_tip"] > 10 and abs(mn["bridge_bow"]) < 0.3
    hump = cn + 2.0 * np.exp(-((vn - 30) / 8.0) ** 2)
    assert lp.measures({}, lp.nose_keypoints(vn, hump, 68.0, 0.0), (vn, hump))["bridge_bow"] > 1.2
    assert mn["nose_gap"] > 0


def test_profile_snap_and_envelope():
    from PIL import Image
    from hifipushie import likeness_profile as lp
    yy, xx = np.mgrid[0:200, 0:200]
    edge = 120 + 8 * np.sin(yy / 25.0)                      # a bright face left of a wavy edge, dark background right
    img = Image.fromarray(np.where(xx < edge, 200, 25).astype(np.uint8)).convert("RGB")
    anchors = [(120 + 8 * np.sin(y / 25.0) + 2.5 * (-1) ** i, float(y)) for i, y in enumerate(range(20, 181, 20))]   # +-2.5 px off
    Q = lp.snap_edge(img, anchors)
    err = np.abs(Q[:, 0] - (120 + 8 * np.sin(Q[:, 1] / 25.0)))
    assert np.median(err) < 0.8 and err.max() < 2.5
    fr = (np.array([100.0, 100.0]), np.array([1.0, 0.0]), np.array([0.0, 1.0]))
    v, c = lp.envelope(Q, fr, 1.0)
    assert abs(float(np.interp(0.0, v, c)) - (20 + 8 * np.sin(100 / 25.0))) < 1.0


def test_contour_items_in_the_checklist():
    from hifipushie import likeness_profile as lp
    items = [it for it in lk.checklist() if it["measure"]["kind"] == "contour"]
    assert len(items) >= 10 and all(it["measure"]["key"] in lp.KEYS for it in items)
    ids = {it["id"] for it in lk.checklist()}
    assert all(r in ids for it in items for r in it.get("replaces", []))
    assert all(i in ids for part in lk.PROFILE_ITEMS.values() for i in part)
