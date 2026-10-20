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


def test_straight_silhouette_follows_the_body_at_every_size():
    """(fit round 12) R8's style: "straight" keeps the suit's CB + dart take-ins and none at the side seams: at every
    size its chest -> waist reduction is under 9 % of the chest and under the suit's, passes its gate row, and the
    straight waist is wider than the suit's by more than the side take-ins' nominal 64 % share of the suit's reduction
    (the suit's shares are scaled up to land on the target; straight's are not)."""
    for name, tape in [("TAPE", TAPE)] + sorted(BODIES.items()):
        out = {}
        for sil in ("suit", "straight"):
            ops = pj.jacket_ops(OPS, tape, 20.0)
            for op in ops:
                if op["op"] == "waist_suppression":
                    op["silhouette"] = sil
            D = pd.start("bodice", tape, BLOCK)
            pd.apply(D, ops)
            Bp = _bp(D)
            r = _rows(Bp, tape, {"design": {"details": {"pockets": "flap"}, "ops": ops}})["waist_suppression"]
            out[sil] = (r["ours"], r["status"], pj.torso_span(Bp, D["meta"]["waist_y"], half=False))
        D0 = pd.start("bodice", tape, BLOCK)
        pd.apply(D0, [op for op in pj.jacket_ops(OPS, tape, 20.0) if op["op"] != "waist_suppression"])
        red = pj.torso_span(_bp(D0), D0["meta"]["waist_y"], half=False) - out["suit"][2]
        gap = out["straight"][2] - out["suit"][2]
        print(name, out, f"suit reduction {red * 1000:.0f} mm, straight wider by {gap * 1000:.0f}")
        assert out["straight"][1] == "PASS" and out["straight"][0] < out["suit"][0], (name, out)
        assert 0.64 <= gap / red < 1.0, (name, gap, red)


def test_plumb_silhouette_falls_straight_and_its_row_catches_a_pinch():
    """(fit round 24, Joe 2026-10-20: the jacket "should basically just fall straight down") R8 "plumb": nothing taken
    in (CB, side panels, dart). With the block unfitted and no CB contour, at every size the narrowest flat girth from
    the chest to the hips is within PLUMB_TOL of the chest, waist_plumb + waist_suppression + front_dart (none) PASS;
    a pattern with the suit's take-ins (the "suit" silhouette drafted, judged as plumb) FAILs waist_plumb; the block's own
    fitted side seam narrows it (>= 20 mm)."""
    for name, tape0 in [("TAPE", TAPE)] + sorted(BODIES.items()):
        tape = dict(tape0, waist=round(0.815 * tape0["chest"]))  # (Garrett: 789 / 968)
        res = {}
        for lab, fitted, cb in (("plumb", False, False), ("fitted", True, False), ("pinched", False, False)):
            ops = [op for op in pj.jacket_ops(OPS, tape, 20.0)
                   if cb or not (op["op"] == "contour" and op.get("edge") == "centre_back")]
            for op in ops:
                if op["op"] == "waist_suppression":
                    op["silhouette"] = "suit" if lab == "pinched" else "plumb"
            D = pd.start("bodice", tape, dict(BLOCK, fitted=fitted, chest_ease=0.15, waist_ease=0.16))  # (Garrett's block)
            pd.apply(D, ops)
            Bp = _bp(D)
            judged = [dict(op, silhouette="plumb") if op["op"] == "waist_suppression" else op for op in ops]
            rows = _rows(Bp, tape, {"design": {"details": {"pockets": "flap"}, "ops": judged}})
            m = D["meta"]
            ch = pj.torso_span(Bp, m["chest_y"], half=False)
            mn = min(pj.torso_span(Bp, y, half=False) for y in np.linspace(m["chest_y"], m["hips_y"], 25))
            res[lab] = (rows["waist_plumb"]["status"], round(ch * 1000), round(mn * 1000), rows["front_dart"]["status"],
                        rows["waist_suppression"]["status"])
        print(name, res)
        assert res["plumb"][0] == "PASS" and res["plumb"][2] >= res["plumb"][1] * (1 - pj.PLUMB_TOL), (name, res)
        assert res["plumb"][3] == "PASS" and res["plumb"][4] == "PASS", (name, res)
        assert res["pinched"][0] == "FAIL" and res["fitted"][2] < res["plumb"][2] - 20, (name, res)


def test_collar_fall_has_its_fold_line_and_the_gate_refuses_one_without():
    """R16 (fit round 2): the two-piece collar's fall carries a fold (roll) line across the whole fall (CB fold to both
    ends), parallel to its seam on the stand; the construction check (garment_design "fold" evidence, the gate's
    flat_pattern row for a notched lapel) refuses the fall without it (fit round 1: the form left it standing, a hood)."""
    from hifipushie import garment_design as gd
    D = ours(TAPE)
    pd.unfold(D)
    fl = [f for f in D["folds"] if f["piece"] == "collar"]
    assert len(fl) == 1 and fl[0]["kind"] == "roll" and fl[0]["angle"] < 30
    L = pattern.fold_line(D["pieces"], fl[0])
    fa = D["pieces"]["collar"]
    lo = fa["P"][pattern.arc_indices(fa, "endLow.m>cbLow>endLow")]
    assert pattern.length(L) == pytest.approx(pattern.length(lo), rel=0.08)  # runs end to end, both halves
    assert np.ptp(L[:, 0]) > 0.9 * np.ptp(lo[:, 0])
    Bp = {"pieces": D["pieces"], "folds": D["folds"], "interfaced": D["interfaced"]}
    ok, why = gd._check({"fold": "collar_fall"}, Bp, gd.roles(Bp), {}, {}, None)
    assert ok, why
    Bp["folds"] = [f for f in D["folds"] if f["piece"] != "collar"]
    for pc in D["pieces"].values():
        (pc.get("wrap") or {}).pop("fold", None)
    ok, why = gd._check({"fold": "collar_fall"}, Bp, gd.roles(Bp), {}, {}, None)
    assert not ok and "no fold line on collar_fall" in why


def test_two_piece_collar_meets_the_checklist_at_every_size():
    """R16 / R15 (fit round 2) against cloth_checklist.json's flat targets, read by the two-piece readers
    (cloth_check.collar_draft_two_piece, notch_flat): stand from the roll line 25-30 mm, fall = stand + 6..15, notch gap
    20-40 mm at 60-90 deg, at a small, a medium and a large man (necks 405 / 450 / 522 mm): the rules are relations."""
    from hifipushie import cloth_check as cc
    for nm, tape in BODIES.items():
        D = ours(tape)
        pd.unfold(D)
        r = cc.flat_readings({"pieces": D["pieces"], "seams": D["seams"], "folds": D["folds"]})
        cd = r["collar_stand_cb_mm"]
        assert cd["two_piece"] and 25 - 4 <= cd["stand_cb_mm"] <= 30 + 4, (nm, cd)
        assert 6 - 4 <= cd["fall_minus_stand_mm"] <= 15 + 4, (nm, cd)
        for side, v in r["notch_flat"].items():
            assert 20 - 15 <= v["gap_mm"] <= 40 + 15 and 60 - 15 <= v["angle_deg"] <= 90 + 15, (nm, side, v)


def test_fall_outer_edge_is_the_books_spread_not_the_under_stack():
    """R18 (fit round 3, C44): the fall's outer edge lies on the jacket body, so only its own stand-off there counts
    (half the fall's stack + half the cloth), never the stand + shirt collar it wraps at the roll line; the drop tapers
    to the fall's end. Books (Aldrich / Cabrera: the undercollar slashed and spread ~1-1.5 cm per half at the outer
    edge) -> outer edge 10-15 mm over the neck seam; ours may add the stand's lean-in (neck edge - roll line, ~4 mm)."""
    t5, t6 = pj.turn_stack(under_layers=0), pj.turn_stack(under_layers=12)
    assert t5["length_mm"] == t6["length_mm"] and t5["depth_mm"] < t6["depth_mm"]
    # (R28's stand run-off reshapes the roll line, never the outer edge: the lean-in is read on the stand drafted
    # without it, and the outer edge must be the same length both ways)
    for nm, tape in BODIES.items():
        D = ours(tape)
        mc = D["meta"]["collar_two_piece"]
        st, fa = D["pieces"]["stand"], D["pieces"]["collar"]
        neck = pattern.length(st["P"][pattern.arc_indices(st, "cb>shoulderNotch>cf")]) * 1000
        outer = pattern.length(fa["P"][pattern.arc_indices(fa, "endOuter>cbOuter")]) * 1000
        pj.STAND_RUN_OFF["on"] = True
        try:
            fa0 = ours(tape)["pieces"]["collar"]
        finally:
            pj.STAND_RUN_OFF["on"] = False
        roll = pattern.length(fa["P"][pattern.arc_indices(fa, "cbLow>endLow")]) * 1000
        outer0 = pattern.length(fa0["P"][pattern.arc_indices(fa0, "endOuter>cbOuter")]) * 1000
        assert abs(outer - outer0) < 0.5, (nm, outer, outer0)
        lean = neck - roll
        assert 10 - 3 <= outer - neck <= 15 + lean + 3, (nm, round(outer - neck, 1), round(lean, 1))
        assert mc["spread_deg"] < 25, (nm, mc["spread_deg"])


def test_stand_runs_off_where_the_lapel_roll_crosses_the_gorge():
    """R28 (fit round 18, Joe's notch tab): the stand's height falls to STAND_RUN_OFF["end"] where the lapel's roll
    line crosses the gorge (R14: one line when worn) and stays there to the collar's end, so the end lies flat on the
    lapel. The gate row collar_stand_end passes the R28 draft and fails the round 2-17 draft (stand_front at the end:
    13-16 mm), at a small, a medium and a large man; full height is kept over the back."""
    for nm, tape in BODIES.items():
        pj.STAND_RUN_OFF["on"] = True
        try:
            D = ours(tape)
        finally:
            pj.STAND_RUN_OFF["on"] = False
        ro = D["meta"]["collar_two_piece"]["stand_run_off"]
        assert ro is not None and ro["before_end_mm"] > 50, (nm, ro)
        st = D["pieces"]["stand"]
        assert np.linalg.norm(_pt(st, "cbTop") - _pt(st, "cb")) * 1000 > 20
        assert _rows(_bp(D), tape)["collar_stand_end"]["status"] == "PASS", nm
        r0 = _rows(_bp(ours(tape)), tape)["collar_stand_end"]
        assert r0["status"] == "FAIL" and r0["ours"] > 10, (nm, r0)


def test_undercollar_a_turn_smaller_on_the_bias_and_the_facing_let_out():
    """R18 / R27 (fit round 3, C45): the undercollar = the fall with its outer edge a turn in (pi/2 x the fall stack,
    books ~3 mm), bias grain, fused to the fall; the lapel facing let out the same turn at the lapel point, nothing at
    the break."""
    tu = np.pi / 2 * pj.turn_stack()["t_fall_mm"]
    D = ours(TAPE)
    fa, un = D["pieces"]["collar"], D["pieces"]["undercollar"]
    h = lambda p: float(np.linalg.norm(p["P"][p["names"]["cbOuter"]] - p["P"][p["names"]["cbLow"]])) * 1000
    assert abs(h(fa) - h(un) - tu) < 0.2 and un["grain"] == 45.0 and un["wrap"]["fused"] == "collar"
    D2 = {"pieces": {"front_facing": {"P": np.array([[0, -0.4], [0, -0.1], [0.05, -0.05], [0.08, -0.1], [0.08, -0.4]]),
                                      "names": {"edge.a": 0, "edge.m": 1, "edge.b": 2},
                                      "marks": {"lapelPoint": np.array([0, -0.1])}}},
          "seams": [["front_facing:edge.a>edge.m>edge.b", "front:x"]], "notes": {}, "log": []}
    P0 = D2["pieces"]["front_facing"]["P"].copy()
    pj.op_lapel_turn(D2)
    d = np.linalg.norm(D2["pieces"]["front_facing"]["P"] - P0, axis=1) * 1000
    assert d[0] < 0.01 and abs(d[1] - tu) < 0.05 and abs(d[2] - tu) < 0.05 and d[3] == 0
    assert D2["pieces"]["front_facing"]["P"][1, 0] < 0  # let out, away from the facing's body


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
        # (the fall diverges from Jaeger on purpose since fit round 2: R16 from practice, fall = stand + 10 mm from the
        # roll line, C42; Jaeger's fall is deeper. Ours stays shallower by 0-20 mm, never deeper)
        assert 0.0 <= fj - np.linalg.norm(_pt(fa, "cbOuter") - _pt(fa, "cbLow")) <= 0.020, name
        # overlap (R12): ours from the button, Jaeger 1.5 % of chest: within 8 mm
        assert abs(_pt(D["pieces"]["front"], "break")[0]) == pytest.approx(ov_j, abs=0.008)


# ---------------------------------------------------------------- R25: the cutaway front (fit round 13)
def _cut_ops(tape, cutaway=True):
    ops = copy.deepcopy(OPS)
    i = next(i for i, o in enumerate(ops) if o["op"] == "lapel")
    ops.insert(i + 1, {"op": "round_corner", "piece": "front", "corner": "stand.b", "along": [0.09, 0.06]})
    ops = pj.jacket_ops(ops, tape, 20.0)
    if not cutaway:  # the old free corner radius (the planted fault)
        ops = [({"op": "round_corner", "piece": "front", "corner": "stand.b", "along": [0.09, 0.06]}
                if o["op"] == "front_cutaway" else o) for o in ops]
    D = pd.start("bodice", tape, BLOCK)
    pd.apply(D, ops)
    return D


def _status(rows):
    return {r["id"]: r["status"] for r in rows}


def test_cutaway_rows_pass_the_r25_draft_and_catch_a_square_corner():
    """R25 drafted (op_front_cutaway, from the free round_corner by jacket_ops) passes its three flat rows at every size;
    the old free corner (90 / 60 mm) fails the cut start and angle (the planted fault the gate must catch)."""
    for name, tape in BODIES.items():
        fe = _cut_ops(tape)["pieces"]["front"]
        st = _status(pj.cutaway_rows(fe))
        assert set(st.values()) == {"PASS"}, (name, pj.cutaway_rows(fe))
        old = _status(pj.cutaway_rows(_cut_ops(tape, cutaway=False)["pieces"]["front"]))
        assert old["front_cutaway_angle"] == "FAIL" and old["front_cutaway_start"] == "FAIL", (name, old)


@pytest.mark.skipif(not _jaeger_ok(), reason="needs Node and the freesewing pack")
def test_cutaway_reads_the_same_on_jaegers_front():
    """Known answer: the same rows read on Jaeger's own front outline (its cutawayPoint as the lower button) pass, and
    our cut angle agrees with Jaeger's within 1 deg."""
    from hifipushie import cloth, freesewing
    for name, tape in BODIES.items():
        d = freesewing.draft("jaeger", cloth.length_level(dict(tape), {}), {}, 10.0)
        P = {k.split(".")[1]: v for k, v in d["parts"].items()}
        fr = P["front"]
        O = _outline(fr["paths"]["seam"]["ops"]) / 1000 * [1, -1]
        jp = lambda n: np.asarray(fr["points"][n], float) / 1000 * [1, -1]  # noqa: E731
        pc = {"P": np.r_[O, [jp("lapelBreakPoint")]], "names": {"break": len(O)}, "marks": {"button2": jp("cutawayPoint")}}
        rj = {r["id"]: r for r in pj.cutaway_rows(pc)}
        ro = {r["id"]: r for r in pj.cutaway_rows(_cut_ops(tape)["pieces"]["front"])}
        print(name, {k: (rj[k]["ours"], ro[k]["ours"]) for k in rj})
        assert rj["front_cutaway_angle"]["status"] == "PASS", (name, rj)
        assert rj["front_hem_round"]["status"] == "PASS" and rj["front_cutaway_start"]["status"] == "PASS", (name, rj)
        assert abs(rj["front_cutaway_angle"]["ours"] - ro["front_cutaway_angle"]["ours"]) <= 1.0
