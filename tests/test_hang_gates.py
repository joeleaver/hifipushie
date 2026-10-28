"""Hang gates (hang_reads; lesson 2 of trials t3-t7): each read finds a planted fault and passes its smooth twin, on
small synthetic bodies (closed tubes), so the measures are validated before they judge a fit (gates.md: measure first,
validate the measure). Plus the wiring: fit rows (the fit's own faults never block), after_fit, the no-reference
review checklist, and the gate targets read from the draft's rules (lesson 5)."""
import types

import numpy as np
import pytest

from hifipushie import cloth_check as cc, hang_reads as hr, next_steps, reviewgate


def tube(contour, zs):
    """A closed tube: the 2D contour (n, 2) extruded through the heights zs, capped at both ends (fans)."""
    C = np.asarray(contour, float)
    n = len(C)
    V = [np.c_[C, np.full(n, z)] for z in zs]
    V = np.concatenate(V + [np.array([[*C.mean(0), zs[0]], [*C.mean(0), zs[-1]]])])
    F = []
    for k in range(len(zs) - 1):
        for i in range(n):
            a, b = k * n + i, k * n + (i + 1) % n
            F += [[a, b, b + n], [a, b + n, a + n]]
    c0, c1 = len(V) - 2, len(V) - 1
    top = (len(zs) - 1) * n
    F += [[c0, (i + 1) % n, i] for i in range(n)] + [[c1, top + i, top + (i + 1) % n] for i in range(n)]
    from hifipushie.cloth_made import outward
    return V, outward(V, np.asarray(F))


def ellipse(a, b, n=96, cx=0.0, cy=0.0):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.c_[cx + a * np.cos(t), cy + b * np.sin(t)]


def finned(a, b, fin, n=192):
    """An ellipse whose sides run out into a thin fin `fin` m long at +-x (front and back meeting at a point)."""
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    P = np.c_[a * np.cos(t), b * np.sin(t)]
    w = np.clip(1 - np.abs(np.sin(t)) / 0.25, 0, None) ** 2  # only near the sides
    P[:, 0] += np.sign(np.cos(t)) * fin * w
    return P


TORSO = dict(a=0.15, b=0.10)
AT = {"armpit_z": 1.30, "crotch_z": 0.80}


def _body(extra=None):
    V, F = tube(ellipse(**TORSO), np.linspace(0.70, 1.45, 16))
    return types.SimpleNamespace(V=V, T=F, at=dict(AT, **(extra or {})))


def _cloth(contour, zs, name="front"):
    V, F = tube(contour, zs)
    return {"F": F, "piece": np.zeros(len(V), int), "names": [name], "points": {}}, V


def test_wings_found_and_a_round_side_passes():
    body = _body()
    zs = np.linspace(0.95, 1.28, 12)
    M, X = _cloth(ellipse(TORSO["a"] + 0.02, TORSO["b"] + 0.02), zs)
    w = hr.wing_reads(M, X, body)
    assert max(v["wing_mm"] for v in w.values()) < hr.WING_MAX_MM, w
    M2, X2 = _cloth(finned(TORSO["a"] + 0.012, TORSO["b"] + 0.012, 0.05), zs)
    w2 = hr.wing_reads(M2, X2, body)
    assert all(v["wing_mm"] > hr.WING_MAX_MM and v["side_off_mm"] > 40 for v in w2.values()), w2
    rows = {r["id"]: r for r in hr.rows({"wings": w2})}
    assert rows["hang_wings"]["status"] == "FAIL" and "wing" in rows["hang_wings"]["fix"]


def _arm_body():
    """A torso tube plus a straight arm tube from the shoulder down and out (A-pose), the arm landmarks on its axis."""
    Vt, Ft = tube(ellipse(**TORSO), np.linspace(0.70, 1.45, 16))
    S, W = np.array([0.30, 0.0, 1.38]), np.array([0.62, 0.0, 0.98])
    ax = (W - S) / np.linalg.norm(W - S)
    u = np.cross(ax, [0, 1.0, 0]); u /= np.linalg.norm(u)
    v = np.cross(ax, u)
    r, n, ts = 0.045, 64, np.linspace(0, 1, 20)
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    Va, Fa = tube(np.c_[r * np.cos(th), r * np.sin(th)], ts)  # (local: x, y round the axis, z along it)
    Va = S + np.outer(Va[:, 2], W - S) + np.outer(Va[:, 0], u) + np.outer(Va[:, 1], v)
    V = np.r_[Vt, Va, Va * [-1, 1, 1]]
    na = len(Va)
    F = np.r_[Ft, Fa + len(Vt), (Fa + len(Vt) + na)[:, ::-1]]
    at = dict(AT, **{"shoulder.L": S, "elbow.L": (S + W) / 2, "wrist.L": W})
    return types.SimpleNamespace(V=V, T=F, at=at), (S, W, u, v)


def _sleeve(frame, gap, drop):
    """A sleeve tube round the arm, `gap` m wider all round, its centre `drop` m below the arm's (in the vertical plane)."""
    S, W, u, v = frame
    ax = (W - S) / np.linalg.norm(W - S)
    up = np.array([0, 0, 1.0]) - ax[2] * ax
    up /= np.linalg.norm(up)
    th = np.linspace(0, 2 * np.pi, 64, endpoint=False)
    r = 0.045 + gap
    out = []
    for sx in (1, -1):
        Vs, Fs = tube(np.c_[r * np.cos(th), r * np.sin(th)], np.linspace(0.05, 0.95, 18))
        X = S + np.outer(Vs[:, 2], W - S) + np.outer(Vs[:, 0], u) + np.outer(Vs[:, 1], v) - drop * up
        out.append((X * [sx, 1, 1], Fs if sx > 0 else Fs[:, ::-1]))
    X = np.r_[out[0][0], out[1][0]]
    F = np.r_[out[0][1], out[1][1] + len(out[0][0])]
    piece = np.r_[np.zeros(len(out[0][0]), int), np.ones(len(out[1][0]), int)]
    return {"F": F, "piece": piece, "names": ["sleeve.L", "sleeve.R"], "points": {}}, X


def test_sleeve_standing_off_found_and_a_hanging_sleeve_passes():
    body, fr = _arm_body()
    M, X = _sleeve(fr, 0.016, 0.0)  # a tube all round the arm: 16 mm over its top
    s = hr.sleeve_reads(M, X, body)
    assert set(s) == {"L", "R"} and all(v["top_gap_mm"] > hr.SLEEVE_TOP_GAP_MAX_MM for v in s.values()), s
    assert all(v["axis_deg"] is not None and v["axis_deg"] < 2 for v in s.values())
    M2, X2 = _sleeve(fr, 0.016, 0.013)  # the same sleeve resting on the top of the arm: 3 mm over it, 29 under
    s2 = hr.sleeve_reads(M2, X2, body)
    assert all(v["top_gap_mm"] < hr.SLEEVE_TOP_GAP_MAX_MM and v["under_gap_mm"] > 20 for v in s2.values()), s2
    st = {r["id"]: r["status"] for r in hr.rows({"sleeves": s})}
    assert st["hang_sleeves"] == "FAIL"
    assert {r["id"]: r["status"] for r in hr.rows({"sleeves": s2})}["hang_sleeves"] == "PASS"


def test_shoulder_spike_found():
    body = _body({"shoulder.L": np.array([0.15, 0.0, 1.40])})
    M, X = _cloth(ellipse(TORSO["a"] + 0.008, TORSO["b"] + 0.008), np.linspace(1.30, 1.44, 15))
    smooth = hr.shoulder_reads(M, X, body)
    assert all(v["spike_mm"] < 2 for v in smooth.values()), smooth
    Xs = X.copy()
    i = int(np.argmin(np.linalg.norm(X - [0.158, 0.0, 1.40], axis=1)))
    Xs[i, 0] += 0.015  # one point pulled 15 mm out at the shoulder point
    sp = hr.shoulder_reads(M, Xs, body)
    assert sp["L"]["spike_mm"] > hr.SHOULDER_SPIKE_MAX_MM > sp["R"]["spike_mm"], sp
    assert {r["id"]: r["status"] for r in hr.rows({"shoulders": sp})}["hang_shoulders"] == "FAIL"


def _legs():
    Vl, Fl = tube(ellipse(0.07, 0.08, cx=0.085), np.linspace(0.40, 0.84, 12))
    Vt, Ft = tube(ellipse(0.17, 0.10), np.linspace(0.84, 1.20, 10))
    Vr = Vl * [-1, 1, 1]
    V = np.r_[Vt, Vl, Vr]
    F = np.r_[Ft, Fl + len(Vt), Fl[:, ::-1] + len(Vt) + len(Vl)]
    return types.SimpleNamespace(V=V, T=F, at=dict(AT, crotch_z=0.84))


def test_drawn_between_the_legs_found_and_a_bridging_hem_passes():
    body = _legs()
    zs = np.linspace(0.70, 1.0, 10)
    M, X = _cloth(ellipse(0.175, 0.105), zs)
    assert hr.hollow_reads(M, X, body)["depth_mm"] < hr.HOLLOW_MAX_MM
    # a hem drawn in between the legs at the front: the contour pinched in to y = -0.03 at x = 0 below the crotch
    C = ellipse(0.175, 0.105)
    pinch = np.exp(-(C[:, 0] / 0.03) ** 2) * (C[:, 1] < 0)
    C2 = C.copy()
    C2[:, 1] = np.where(pinch > 0.01, C[:, 1] + pinch * (-C[:, 1].min() - 0.03), C[:, 1])  # (front centre -> y -0.03)
    M2, X2 = _cloth(C2, np.linspace(0.70, 0.83, 6))
    h = hr.hollow_reads(M2, X2, body)
    assert h["depth_mm"] > hr.HOLLOW_MAX_MM and h["where"] == "between the legs", h


def test_hang_rows_are_the_patterns_once_the_fit_hangs():
    """C244: with the hang step a hang FAIL is the pattern's: owner "pattern", its fix names the pattern move, and it
    blocks the detail rows like any big read."""
    assert hr.HANG_STEP
    w = hr.rows({"wings": {"L": {"wing_mm": 46.0, "z": 1.12, "side_off_mm": 77.0}}})[0]
    assert w["status"] == "FAIL" and w["owner"] == "pattern" and "PATTERN" in w["fix"] and "side seams" in w["fix"]
    detail = {"id": "collar_corners", "stage": 3, "status": "PASS"}
    assert cc.big_first([w, detail])[-1]["status"] == "BLOCKED"


def test_hang_rows_are_the_fits_until_a_hang_step_and_never_block(monkeypatch):
    monkeypatch.setattr(hr, "HANG_STEP", False)
    rows = hr.rows({"wings": {"L": {"wing_mm": 46.0, "z": 1.12, "side_off_mm": 77.0}}})
    w = rows[0]
    assert w["status"] == "FAIL" and w["owner"] == "fit" and "no hang step yet" in w["fix"]
    detail = {"id": "collar_corners", "stage": 3, "status": "PASS"}
    out = cc.big_first([w, detail])
    assert out[-1]["status"] == "PASS"  # (the fit's own fault blocks no detail row, C52)
    assert cc.big_first([dict(w, owner="pattern"), dict(detail)])[-1]["status"] == "BLOCKED"


def test_fit_rows_carry_the_hang_rows_and_after_fit_lists_them(monkeypatch):
    monkeypatch.setattr(hr, "HANG_STEP", False)  # (the fit's-fault listing; with the hang step they are pattern rows)
    monkeypatch.setattr(hr, "reads", lambda res, X: {"wings": {"L": {"wing_mm": 40.0, "z": 1.1, "side_off_mm": 70.0}}})
    rows = cc.fit_rows({"mesh": {}, "body": None}, None, 0.5, False, model="m", garment="g")
    assert {r["id"] for r in rows} >= {"fit_threads_p99", "hang_wings"}
    txt = next_steps.after_fit("m", "g", 0.5, None, True)
    assert "hang faults" in txt and "hang_wings" in txt and "FIT's" in txt
    assert "judge the clay" in txt  # (the pattern itself has no fault: the judging step still follows)
    assert "hang_wings" not in next_steps.after_fit("m", "g", 0.5, None, True)  # (consumed: no stale rows)


def test_no_reference_review_checklist():
    p = reviewgate.checklist_prompt("hang")
    for w in ("wings", "follow the arm", "shoulder", "between the legs", "collar or hood"):
        assert w in p
    with pytest.raises(ValueError, match="hang"):
        reviewgate.checklist_prompt("nope")


def test_gate_targets_are_the_drafts_rules():
    # the designed cap judged on the kind's rule, not on the ask (hoodie t6: ask 0.6 % landed -0.45 %)
    note = {"ease": [0.006 - 0.012, 0.006 + 0.012], "why": "sleeve cap ease 0.6% (designed)"}
    assert cc.note_band(note, "hoodie")["ease"] == [-0.03, 0.03]
    assert cc.note_band(note, "no_such_kind") == note
    other = {"ease": [0.0, 0.02], "why": "dart released into gathers"}
    assert cc.note_band(other, "hoodie") is other
    # the collar stand from the neck (shirt t7: neckHeight 35 mm -> 22 mm stand; practice 30..35 contradicted it)
    d = cc.rule_dims("shirt", {"neckHeight": 35.0})["stand_cb"]
    assert d[0] == 20.0 and 22.0 <= d[1] <= 23.0
    res = {"details": {"collar": {"choice": "shirt_collar", "kb": {"dims": {"stand_cb": [30, 35], "fall_cover": [6, 12]}}}}}
    r2 = cc.with_rule_dims(res, "shirt", {"neckHeight": 35.0})
    assert r2["details"]["collar"]["kb"]["dims"] == {"stand_cb": d, "fall_cover": [6, 12]}
    assert res["details"]["collar"]["kb"]["dims"]["stand_cb"] == [30, 35]  # (the kb itself untouched)
    assert cc.rule_dims("hoodie", {"neckHeight": 35.0}) == {}
