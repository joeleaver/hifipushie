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


def ours(tape, rules=True):
    D = pd.start("bodice", tape, BLOCK)
    pd.apply(D, pj.jacket_ops(OPS, tape, 20.0) if rules else copy.deepcopy(OPS))
    return D


def _pt(pc, n):
    return np.asarray(pc["P"][pc["names"][n]], float)


# ---------------------------------------------------------------- the rules are relations
def test_rules_scale_with_the_body():
    a, b = pj.rules(BODIES["small"]), pj.rules(BODIES["large"])
    for k in ("back_neck_rise", "collar_stand_cb", "collar_fall_cb"):  # proportional to the neck girth
        assert a[k]["value"] / b[k]["value"] == pytest.approx(BODIES["small"]["neck"] / BODIES["large"]["neck"], rel=1e-6)
    assert all(v["source"].startswith(pj.DOC) for v in a.values())
    # stand : fall = 30 : 70 of the collar's CB height (R16)
    assert a["collar_stand_cb"]["value"] / a["collar_fall_cb"]["value"] == pytest.approx(0.3 / 0.7)
    # overlap follows the button, not the body (R12)
    assert pj.rules(BODIES["large"], 25.0)["overlap"]["value"] == pytest.approx(0.025)


def test_drafted_values_follow_the_rules_at_every_size():
    for tape in BODIES.values():
        D = ours(tape)
        R = pj.rules(tape)
        bk = D["pieces"]["back"]
        assert abs(_pt(bk, "hps")[0] - _pt(bk, "cbNeck")[0]) == pytest.approx(R["back_neck_width"]["value"], abs=0.001)
        assert _pt(bk, "hps")[1] - _pt(bk, "cbNeck")[1] == pytest.approx(R["back_neck_rise"]["value"], abs=0.001)
        wy = D["meta"]["waist_y"]
        assert pj.torso_span(D, wy) - 2 * R["overlap"]["value"] == pytest.approx(  # (CF to CF: the overlaps out)
            tape["waist"] * (1 + pj.EASE["waist"]) / 1000, rel=0.01)
        assert pj.torso_span(D, D["meta"]["hips_y"]) - 4 * R["overlap"]["value"] / 2 >= tape["hips"] * 1.04 / 1000
        assert "frontDart" in D["pieces"]["front"]["fisheyes"]
        assert abs(_pt(D["pieces"]["front"], "break")[0]) == pytest.approx(0.020, abs=1e-4)
        st, fa = D["pieces"]["stand"], D["pieces"]["collar"]
        E = st["P"][pattern.arc_indices(st, "cb>shoulderNotch>cf")]
        assert pattern.length(E) == pytest.approx(pd.edge_length(D, D["edges"]["neck_back"] + D["edges"]["neck_front"]),
                                                  rel=0.005)  # the stand is the neckline's length (R17)
        assert pj.sagitta_ratio(E) < 0.08  # a band, not the neckline's crescent
        lo = pattern.length(fa["P"][pattern.arc_indices(fa, "cbLow>endLow")])
        out = pattern.length(fa["P"][pattern.arc_indices(fa, "endOuter>cbOuter")])
        assert out > lo  # sprung: the fall's outer edge longer than the roll line (R18)
        assert {"flap"} <= set(D["pieces"])


# ---------------------------------------------------------------- the gate rows on known answers
def _bp(D):
    pd.unfold(D)
    return {"pieces": D["pieces"], "draft": {"meta": D["meta"], "measurements": D["meta"]["measurements"]},
            "closures": D.get("closures") or []}


def _rows(Bp, tape, g=None):
    return {r["id"]: r for r in pj.tailor_rows(Bp, tape, g or {"design": {"details": {"pockets": "flap"}}})}


def test_gate_rows_pass_the_rule_draft():
    rows = _rows(_bp(ours(TAPE)), TAPE)
    for k in ("back_neck_width", "back_neck_rise", "waist_suppression", "hips_clearance", "front_dart", "front_overlap",
              "collar_neck_edge_straight", "collar_stand_cb", "collar_fall_cb", "pockets"):
        assert rows[k]["status"] == "PASS", (k, rows[k])
        assert rows[k]["rule"].startswith(pj.DOC)


def test_gate_rows_catch_the_muslin1_faults():
    """muslin 1: back neck 103 x 37 (widened, CB dropped), a boxy waist with no dart, 12 mm overlap, a one-piece
    crescent collar, no pockets: each row fails."""
    rows = _rows(_bp(ours(TAPE, rules=False)), TAPE)
    for k in ("back_neck_rise", "front_dart", "front_overlap", "collar_neck_edge_straight", "pockets"):
        assert rows[k]["status"] == "FAIL", (k, rows[k])
    assert rows["collar_stand_cb"]["status"] == "UNMEASURED"
    assert rows["waist_suppression"]["ours"] < 11.0


def test_sagitta_tells_a_band_from_a_crescent():
    t = np.linspace(0, 1, 50)
    band = np.c_[t * 0.24, 0.012 * t ** 2]
    a = np.linspace(0, 1.2, 50)
    crescent = np.c_[0.2 * np.sin(a), 0.2 * (1 - np.cos(a))]  # a neckline-like arc
    assert pj.sagitta_ratio(band) < 0.08 < pj.sagitta_ratio(crescent)


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


@pytest.mark.skipif(not _jaeger_ok(), reason="needs Node and the freesewing pack")
def test_tracks_jaeger_at_three_sizes():
    from hifipushie import cloth, freesewing
    for name, tape in BODIES.items():
        d = freesewing.draft("jaeger", cloth.length_level(dict(tape), {}), {}, 10.0)
        P = {k.split(".")[1]: v for k, v in d["parts"].items()}
        jp = lambda part, n: np.asarray(P[part]["points"][n], float) / 1000  # noqa: E731
        D = ours(tape)
        bk = D["pieces"]["back"]
        # back neck (R3, R4): within 6 mm
        assert abs(_pt(bk, "hps")[0] - _pt(bk, "cbNeck")[0]) == pytest.approx(jp("back", "neck")[0] - jp("back", "cbNeck")[0], abs=0.006)
        assert _pt(bk, "hps")[1] - _pt(bk, "cbNeck")[1] == pytest.approx(jp("back", "cbNeck")[1] - jp("back", "neck")[1], abs=0.006)
        # waist girth CF to CF (R8): within 6 %; Jaeger's front dart is drawn inside its outline
        ov_j = abs(jp("front", "neckEdge")[0] - jp("front", "cfNeck")[0])
        dart_j = jp("front", "dartRight")[0] - jp("front", "dartLeft")[0]
        y = jp("back", "cbWaist")[1] + 0.0004
        wj = 2 * sum(pj._span_at(_outline(P[p]["paths"]["seam"]["ops"]) / 1000 * [1, -1], -y)
                     for p in ("back", "side", "front")) - 2 * dart_j - 2 * ov_j
        wo = pj.torso_span(D, D["meta"]["waist_y"]) - 2 * abs(_pt(D["pieces"]["front"], "break")[0])
        assert wo == pytest.approx(wj, rel=0.06), name
        fe = D["pieces"]["front"]
        assert np.linalg.norm(_pt(fe, "frontDartAm") - _pt(fe, "frontDartBm")) == pytest.approx(dart_j, abs=0.008)
        # collar stand / fall at CB (R16) within 5 / 10 mm; both stands near-straight (R17)
        st, fa = D["pieces"]["stand"], D["pieces"]["collar"]
        sj = np.linalg.norm(jp("collarStand", "collarstandCbTop") - jp("collarStand", "collarstandCbBottom"))
        fj = np.linalg.norm(jp("collar", "collarCbTopRoll") - jp("collar", "collarstandCbTop"))
        assert np.linalg.norm(_pt(st, "cbTop") - _pt(st, "cb")) == pytest.approx(sj, abs=0.005)
        assert np.linalg.norm(_pt(fa, "cbOuter") - _pt(fa, "cbLow")) == pytest.approx(fj, abs=0.010)
        # overlap (R12): ours from the button, Jaeger 1.5 % of chest: within 8 mm
        assert abs(_pt(D["pieces"]["front"], "break")[0]) == pytest.approx(ov_j, abs=0.008)
