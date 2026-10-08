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
    assert stages[:3] == ["proportions", "widths", "eyes"]            # big to small
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
        try:
            v = lk.value(s, it["measure"], 1.0)
            assert isinstance(v, float)          # (nan where the synthetic face has a zero-size feature)
        except lk.Unmeasurable:
            pass
    first = [stages.index(it["stage"]) for it in lk.checklist()]
    assert first == sorted(first)                                      # the file lists items in artists' order


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
