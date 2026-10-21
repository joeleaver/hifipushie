"""Known answers for fold_checks: one family of rows for every declared fold (Joe 2026-10-20). Planted good / bad folds
on a strip meshed by cloth.mesh (the same fixture as tests/test_pattern_form.py); the form rows read planted
geometry (the flap rotated about its row by a known angle), no assembly, no Blender."""
import math

import numpy as np
import pytest

from hifipushie import cloth, fold_checks as fc
from test_pattern_form import _B, _piece, _flat

P = [[0, 0], [0.3, 0], [0.3, 0.12], [0, 0.12]]


def _strip(kind="press", angle=180, line=((0.0, 0.04), (0.3, 0.04)), run_off=None, radius=None):
    fd = {"piece": "r", "line": [list(line[0]), list(line[1])], "angle": angle, "kind": kind, "name": "f",
          "flap": "top"}
    if run_off:
        fd["run_off"] = run_off
    if radius:
        fd["radius"] = radius
    return _B({"r": _piece(P, marks={"top": [0.15, 0.1]})}, folds=[fd], refine=[{"piece": "r", "h": 0.006}]), fd


def _turned(M, theta_deg, wobble_deg=0.0, through=False):
    """The strip flat (z 0), its flap (y > 0.04) rotated about the row (y = 0.04) by theta (+ a twist along the line:
    wobble_deg x sin(2 pi x / 40 mm)), the flap lifted / sunk one cloth thickness at a full turn."""
    X = _flat(M).copy()
    uv = np.asarray(M["uv"])
    f = uv[:, 1] > 0.04 + 1e-6
    th = np.radians(theta_deg + wobble_deg * np.sin(2 * np.pi * uv[f, 0] / 0.04))
    r = uv[f, 1] - 0.04
    X[f, 1] = 0.04 + r * np.cos(th)
    X[f, 2] = r * np.sin(th) + (-0.004 if through else 0.0015) * np.clip(theta_deg / 180, 0, 1)
    return X


def test_flat_turn_allowance_run_off_pleat():
    B, _ = _strip()
    rows = {r["id"]: r for r in fc.flat_rows(B, {"fabric": "shirting"})}
    assert rows["fold_turn_allowance"]["status"] == "PASS" and rows["fold_run_off"]["status"] == "PASS", rows
    B, _ = _strip(line=((0.0, 0.118), (0.3, 0.118)))  # (2 mm of flap: no room for the turn)
    assert {r["id"]: r for r in fc.flat_rows(B, {})}["fold_turn_allowance"]["status"] == "FAIL"
    B, _ = _strip(line=((0.0, 0.04), (0.2, 0.04)))  # (stops 100 mm short, no run-off declared)
    B["folds"][0]["line"] = [[0.0, 0.04], [0.2, 0.04]]
    from hifipushie import pattern
    pattern.fold_line  # (fold_line runs a line on to the outline within 1.5 cm only)
    assert {r["id"]: r for r in fc.flat_rows(B, {})}["fold_run_off"]["status"] == "FAIL"
    B["folds"][0]["run_off"] = {"ends": "end", "off": 0.05, "over": 0.03}
    assert {r["id"]: r for r in fc.flat_rows(B, {})}["fold_run_off"]["status"] == "PASS"
    B, _ = _strip()
    B["pleats"] = [{"piece": "r", "a": [[0.10, 0.0], [0.10, 0.12]], "b": [[0.14, 0.0], [0.14, 0.12]], "depth": 0.02,
                    "press": "left"}]
    assert [r for r in fc.flat_rows(B, {}) if r["id"] == "pleat_depth"][0]["status"] == "PASS"
    B["pleats"][0]["depth"] = 0.03
    assert [r for r in fc.flat_rows(B, {}) if r["id"] == "pleat_depth"][0]["status"] == "FAIL"


def test_form_turn_achieved_vs_declared():
    B, _ = _strip(angle=0)  # (folds.py: angle 0 = folded right over, a 180 deg turn; round 9: the row read angle as turn)
    M = cloth.mesh(B, 0.012)
    good = {r["id"]: r for r in fc.form_rows(M, _turned(M, 175))}
    assert good["fold_turn"]["status"] == "PASS", good["fold_turn"]
    bad = {r["id"]: r for r in fc.form_rows(M, _turned(M, 60))}
    assert bad["fold_turn"]["status"] == "FAIL" and abs(bad["fold_turn"]["ours"]["turn_deg"] - 60) < 12, bad["fold_turn"]


def test_form_twist_along_the_fold():
    B, _ = _strip(angle=90)
    M = cloth.mesh(B, 0.012)
    ok = {r["id"]: r for r in fc.form_rows(M, _turned(M, 90))}
    assert ok["fold_twist"]["status"] == "PASS", ok["fold_twist"]
    tw = {r["id"]: r for r in fc.form_rows(M, _turned(M, 90, wobble_deg=40))}  # (+-40 deg every 40 mm: ~40 / cm)
    assert tw["fold_twist"]["status"] == "FAIL", tw["fold_twist"]
    assert ok["fold_twist"]["ours"]["twist_deg_cm_p90"] < 5, ok["fold_twist"]


def test_form_crisp_press_vs_soft_roll():
    B, _ = _strip(angle=90)
    M = cloth.mesh(B, 0.012)
    r = {x["id"]: x for x in fc.form_rows(M, _turned(M, 90))}
    assert r["fold_crisp"]["status"] == "PASS" and r["fold_crisp"]["ours"]["pressed"], r["fold_crisp"]
    B, _ = _strip(kind="roll", angle=90, radius=0.012)  # (declared a soft roll, planted as a sharp hinge)
    M = cloth.mesh(B, 0.012)
    r = {x["id"]: x for x in fc.form_rows(M, _turned(M, 90))}
    assert r["fold_crisp"]["status"] == "FAIL", r["fold_crisp"]


@pytest.mark.parametrize("kind,angle,extra", [("press", 180, {}), ("roll", 120, {"radius": 0.008}),
                                              ("press", 90, {"band": True}), ("roll", 170, {"in_wrap": True})])
def test_every_fold_kind_runs_through_the_same_rows(kind, angle, extra):
    """(the table test) a hem / cuff turn-back (press 180), a lapel / collar roll (roll 120), a placket band (press 90,
    band), a wrapped roll (in_wrap): the same flat and form rows, each with a status."""
    B, fd = _strip(kind=kind, angle=angle, radius=extra.get("radius"))
    B["folds"][0].update({k: v for k, v in extra.items() if k != "radius"})
    flat = {r["id"] for r in fc.flat_rows(B, {})}
    assert {"fold_turn_allowance", "fold_run_off"} <= flat
    M = cloth.mesh(B, 0.012)
    # (planted as declared: the turn is 180 - angle, folds.py)
    form = {r["id"]: r["status"] for r in fc.form_rows(M, _turned(M, 180 - angle))}
    # (a fold declared flat, angle 180, turns nothing: no crispness to judge)
    assert {"fold_turn", "fold_twist"} | ({"fold_crisp"} if angle != 180 else set()) <= set(form), form
    assert all(s in ("PASS", "FAIL", "INFO", "UNMEASURED") for s in form.values())
    assert form["fold_turn"] == "PASS", form


def _collar_flat_case(fall_h=0.055, stand_h=0.035, r0=0.10, span=2.2):
    """A body piece whose neckline is an arc (radius r0: the flattened shoulders round the neck), a straight stand band
    and a straight FALL band (outer edge = its sewn edge: no spring) sewn as a shirt's: stand to the neckline, fall to
    the stand's top, the fall's roll 6 mm above its seam (angle 0)."""
    th = np.linspace(-span / 2, span / 2, 41)
    L = r0 * span
    neck = np.c_[r0 * np.sin(th), -r0 * np.cos(th)]
    outer = np.c_[0.25 * np.sin(th), -0.25 * np.cos(th)][::-1]
    body = _piece(np.r_[neck, outer], names={"nl.l": 0, "nl.c": 20, "nl.r": 40})
    xs = np.linspace(-L / 2, L / 2, 41)

    def band(h, nm):
        P = np.r_[np.c_[xs, np.zeros(41)], np.c_[xs[::-1], np.full(41, h)]]
        return _piece(P, names={f"{nm}L": 0, f"{nm}M": 20, f"{nm}R": 40, f"{nm}TR": 41, f"{nm}TM": 61, f"{nm}TL": 81})
    B = _B({"bodice": body, "stand": band(stand_h, "s"), "collar": band(fall_h, "c")},
           seams=[["stand:sL>sM>sR", ["bodice:nl.l>nl.c>nl.r"]], ["collar:cL>cM>cR", "stand:sTL>sTM>sTR"]],
           folds=[{"name": "collar roll", "piece": "collar", "line": {"edge": "cL>cM>cR", "offset": 0.006}, "angle": 0,
                   "kind": "roll", "radius": 0.0015, "strength": 0.6}])
    return B


def test_fall_spring_read_and_op_on_a_straight_band():
    """(shirt round 9, the funnel) KNOWN ANSWER, flat: a straight fall band on a curved neckline is short of its landing
    path (the neckline offset by the fall's cover below the seam, here 55 - 6 - turn - (35 + 6) ~ 6 mm at CB, more at
    the ends, + pi x its stand-off): collar_fall_spring FAILs; cloth.spring_fall bends it so its outer edge is the path
    (within the tolerance) with its sewn edge unchanged (+-0.5 mm: it still matches the stand); a fall already sprung
    is left alone."""
    from hifipushie import garment_reads as gr, cloth_check as cc
    B = _collar_flat_case()
    rd = gr.fall_spring_reads(B, {"fabric": "shirting"})
    assert rd and rd["fall_short_mm"] > 6, rd
    row = [r for r in cc.collar_rule_rows(B, {"fabric": "shirting"}) if r["id"] == "collar_fall_spring"][0]
    assert row["status"] == "FAIL", row
    rec = cloth.spring_fall(B["pieces"], B["seams"], B["folds"], {"fabric": "shirting"})
    assert rec, rec
    now = gr.fall_spring_reads(B, {"fabric": "shirting"})
    assert abs(now["fall_sewn_mm"] - rd["fall_sewn_mm"]) < 0.5, (rd, now)
    assert gr.SPRING_TOL_MM[0] <= -now["fall_short_mm"] <= gr.SPRING_TOL_MM[1], now
    assert [r for r in cc.collar_rule_rows(B, {"fabric": "shirting"}) if r["id"] == "collar_fall_spring"][0]["status"] == "PASS"
    assert cloth.spring_fall(B["pieces"], B["seams"], B["folds"], {"fabric": "shirting"}) == {}
    # (C125) the landing line is the neckline at the CB cover all the way round (a shirt fall lands close round the
    # neck), not tapered to the points' height: every neckline part offset by the same drop (Garrett: 127 -> 81 mm)
    assert all(abs(p["drop_mm"] - now["drop_cb_mm"]) < 0.05 for p in now["parts"].values()), now


def test_two_piece_collar_rows_on_their_known_answer():
    """(shirt round 9, C119 + the turn convention) the two-piece collar known answer (tests/test_pattern_form.py: a fall
    on its stand on a neck cylinder, assembled, ~165-175 deg in section, angle 10 declared: a 170 deg turn): fold_turn
    PASS read in section with the base across the seam, fold_on_base PASS (0 through, the STAND as base, not the fall's
    4 mm strip); planted: the fall opened 90 deg -> fold_turn FAIL; the fall sunk 6 mm into its stand -> fold_on_base
    FAIL."""
    from hifipushie import folds as fm, pattern_form as pf
    from test_pattern_form import _two_piece_collar_case
    c = _two_piece_collar_case(0.028, 0.045, 0.004)
    M = c["M"]
    V = pf.assemble({"mesh": M, "X0": c["X0"], "pieces": c["B"]}, c["body"], iters=120, ease=0.004)["V"]
    rows = lambda X: {r["id"]: r for r in fc.form_rows(M, X, c["body"])}
    good = rows(V)
    assert good["fold_turn"]["status"] == "PASS" and "across" in good["fold_turn"]["ours"]["read"], good["fold_turn"]
    assert good["fold_on_base"]["status"] == "PASS" and good["fold_on_base"]["ours"]["share"] < 0.02, good["fold_on_base"]
    fd = M["folds"][0]
    g = fm._geom(M, fd)
    opened = fm.turn_flap(V, M, fd, -math.radians(90) / (len(g["rows"]) * fd["turn"]))
    op = rows(opened)["fold_turn"]
    assert op["status"] == "FAIL" and op["ours"]["turn_deg"] < 120, op
    sunk = V.copy()
    fl = np.asarray(g["rows"][-1]["v"])
    sunk[fl, :2] -= 0.006 * sunk[fl, :2] / np.linalg.norm(sunk[fl, :2], axis=1, keepdims=True)
    assert rows(sunk)["fold_on_base"]["status"] == "FAIL"
