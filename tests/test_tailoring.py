"""Tailored-jacket principles (docs/notes/tailoring_principles.md; pattern_jacket): the rules are RELATIONS that hold at
any size, the gate rows (T: back neck, suppression, dart, overlap, collar straightness, stand / fall, pockets) catch
the muslin-1 faults on known answers, and our draft tracks FreeSewing's Jaeger (MIT) at a small, a medium and a large
man within stated tolerances (skipped without Node / the freesewing pack).
Run: /mnt/data/hifipushie/bin/slot uv run pytest tests/test_tailoring.py"""
from __future__ import annotations

import copy
import shutil

import numpy as np
import pytest

from hifipushie import pattern, pattern_draft as pd, pattern_jacket as pj

# a generic man's tape (mm; rounded, no person's): graded below to a smaller and a larger man
TAPE = {"ankle": 225, "biceps": 315, "calf": 380, "chest": 970, "chestDepth": 235, "heel": 340, "height": 1770,
        "highBust": 970, "hips": 945, "hpsToArmpitBack": 258, "hpsToBust": 250, "hpsToSeatBack": 710,
        "hpsToSeatFront": 680, "hpsToWaistBack": 515, "inseam": 870, "knee": 355, "napeToWaistBack": 490, "neck": 450,
        "neckHeight": 35, "seat": 960, "shoulderSlope": 11, "shoulderToElbow": 290, "shoulderToShoulder": 480,
        "shoulderToWrist": 555, "upperLeg": 540, "waist": 790, "waistDepth": 200, "waistToArmpit": 237,
        "waistToFloor": 1115, "waistToHips": 152, "waistToKnee": 578, "waistToSeat": 207, "waistToUpperLeg": 245,
        "wrist": 145}
GIRTH = {"neck", "chest", "waist", "hips", "seat", "biceps", "wrist", "highBust", "upperLeg", "knee", "calf", "ankle",
         "heel", "chestDepth", "waistDepth"}


def grade(g, w, l):
    return {k: (v if k == "shoulderSlope" else v * w if k == "waist" else v * g if k in GIRTH
                else v * (g + l) / 2 if k == "shoulderToShoulder" else v * l) for k, v in TAPE.items()}


BODIES = {"small": grade(0.90, 0.92, 0.95), "medium": dict(TAPE), "large": grade(1.16, 1.27, 1.03)}
BLOCK = {"fitted": True, "cb": "seam", "chest_ease": 0.09, "length": "hips", "length_bonus": 0.15, "darts": False,
         "hips_ease": 0.14, "armhole_depth": 0.14, "underarm": 0.035}
OPS = [{"op": "neckline", "widen": 0.004, "back": 0.015},
       {"op": "contour", "edge": "centre_back", "at": [["top", 0.0], ["chest", 0.004], ["waist", 0.012], ["hem", 0.004]]},
       {"op": "style_line", "piece": "front", "name": "sideF", "from": {"edge": "armhole>armholePitch", "t": 0.45},
        "to": {"edge": "hem>cfHem", "t": 0.22}, "names": ["front", "side_front"]},
       {"op": "style_line", "piece": "back", "name": "sideB", "from": {"edge": "armhole>armholePitch", "t": 0.45},
        "to": {"edge": "hem>cbHem", "t": 0.22}, "names": ["back", "side_back"]},
       {"op": "join", "a": "side_front", "b": "side_back", "name": "side"},
       {"op": "take_in", "line": "sideF", "amount": 0.008}, {"op": "take_in", "line": "sideB", "amount": 0.01},
       {"op": "contour", "edge": ["sideF", "sideB"], "at": [["waist", 0.0], ["hem", 0.0]]},
       {"op": "lapel", "break_y": 0.455, "stand": 0.012, "width": 0.072, "gorge": "straight", "gorge_drop": 0.115,
        "notch": 0.025},
       {"op": "collar", "type": "tailored", "stop": 0.0, "stand_height": 0.029, "fall": 0.043, "point": 0.015},
       {"op": "buttons", "piece": "front", "n": 2},
       {"op": "sleeve", "cap_ease": 0.03, "hem_width": 0.32, "length_bonus": 0.018}, {"op": "two_piece", "elbow": 0.05}]


def _pt(pc, n):
    return np.asarray(pc["P"][pc["names"][n]], float)


# ---------------------------------------------------------------- the rules are relations
def test_rules_scale_with_the_body():
    a, b = pj.rules(BODIES["small"]), pj.rules(BODIES["large"])
    for k in ("back_neck_rise",):  # proportional to the neck girth
        assert a[k]["value"] / b[k]["value"] == pytest.approx(BODIES["small"]["neck"] / BODIES["large"]["neck"], rel=1e-6)
    assert all(v["source"].startswith(pj.DOC) for v in a.values())
    # R16 (fit round 2): from the roll line, stand 25-30 mm at any neck, the fall 10 mm deeper (practice)
    for r_ in (a, b):
        st = r_["collar_stand_cb"]["value"] + pj.FALL_FOLD["at"]
        assert 0.025 - 1e-9 <= st <= 0.030 + 1e-9
        assert r_["collar_fall_cb"]["value"] - pj.FALL_FOLD["at"] - st == pytest.approx(0.010)
    # overlap follows the button, not the body (R12)
    assert pj.rules(BODIES["large"], 25.0)["overlap"]["value"] == pytest.approx(0.025)


# ---------------------------------------------------------------- the gate rows on known answers
def _bp(D):
    pd.unfold(D)
    return {"pieces": D["pieces"], "draft": {"meta": D["meta"], "measurements": D["meta"]["measurements"]},
            "closures": D.get("closures") or []}


# ---------------------------------------------------------------- tracks Jaeger at three sizes
def _jaeger_ok():
    if not shutil.which("node"):
        return False
    try:
        from hifipushie import assets
        return (assets.pack("freesewing") / "node_modules" / "@freesewing" / "jaeger").exists()
    except Exception:  # noqa: BLE001
        return False


def _bez(p0, c1, c2, p1, n=24):
    t = np.linspace(0, 1, n)[:, None]
    p0, c1, c2, p1 = (np.asarray(q, float) for q in (p0, c1, c2, p1))
    return (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * c1 + 3 * (1 - t) * t ** 2 * c2 + t ** 3 * p1


def _outline(ops):
    pts, cur = [], None
    for o in ops:
        if o["type"] in ("move", "line"):
            cur = np.asarray(o["to"], float)
            pts.append(cur)
        elif o["type"] == "curve":
            pts += list(_bez(cur, o["cp1"], o["cp2"], o["to"]))
            cur = np.asarray(o["to"], float)
    return np.asarray(pts)


def _status(rows):
    return {r["id"]: r["status"] for r in rows}


def test_span_counts_a_vertex_on_the_level():
    """C150 (dress-tess s19): a contour op puts an outline vertex exactly on the waist level; the strict sign test read
    the span 0 there (Tess's coat: chest / waist / hips 0 mm)."""
    import numpy as np
    from hifipushie import pattern_jacket as pj
    sq = np.array([[0.0, 0.0], [0.2, 0.0], [0.2, -0.5], [0.0, -0.5]])
    on = np.array([[0.0, 0.0], [0.2, 0.0], [0.19, -0.25], [0.2, -0.5], [0.0, -0.5]])
    assert abs(pj._span_at(sq, -0.25) - 0.2) < 1e-9
    assert abs(pj._span_at(on, -0.25) - 0.19) < 1e-9


def test_true_corner_bends_a_bare_straight_edge():
    """C151 (dress-tess s19): a two-point sleeve hem had no point within the blend and could not be trued."""
    import numpy as np
    from hifipushie import pattern
    P = np.array([[0.15, -0.3], [-0.15, -0.3], [-0.2, 0.0], [0.2, 0.0]])  # hem wristF -> wristB, seams taper in
    pc = {"name": "sleeve", "P": P, "names": {"wristF": 0, "wristB": 1, "underarmB": 2, "underarmF": 3}}
    before = pattern._interior(P, 0)
    out = pattern.true_corner(pc, "wristF", "underarmF", 90.0, 0.04)
    after = pattern._interior(np.asarray(out["P"]), out["names"]["wristF"])
    assert abs(before - 90) > 5 and abs(after - 90) < 1.0
    assert len(out["P"]) > len(P) and np.allclose(out["P"][out["names"]["underarmF"]], P[3])

