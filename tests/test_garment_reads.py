"""Known answers for garment_reads (shirt round 2: C97 big reads on the form, C98 checklist rows, C101 collar rules,
C100 lit-vs-lit colour). Synthetic pieces / meshes: no draft, no Blender, ~1 s."""
import json
import math
import os

import numpy as np
import pytest

from hifipushie import cloth_check as cc, garment_reads as gr

HPS = 1.50


# ----------------------------------------------------------------------------------------------- C97: planted states
def _front_mesh(open_front: bool, v_drop=0.06, spread=False, standing=False):
    """front.L / front.R grids (x out from the inner edge to 0.2 m, z from HPS - 0.60 to HPS - 0.03) whose inner edges
    meet (lapped 5 mm) below v_drop and open linearly above it (to 40 mm off CF at the top); open_front: 60 mm off CF
    everywhere. A stand ring at the neck and a fall: standing (above the stand), closed (turned, points 25 mm off CF)
    or spread (turned, points 73 mm off CF, 55 mm below HPS). A front closure of 5 pairs, the top one undone when the
    V is open."""
    V, piece, names = [], [], ["front.L", "front.R", "stand", "collar"]
    zs = np.arange(HPS - 0.60, HPS - 0.03, 0.004)
    for k, sg in ((0, 1), (1, -1)):
        for z in zs:
            d = HPS - z
            inner = 0.06 if open_front else (-0.005 if d >= v_drop else 0.04 * (v_drop - d) / v_drop)
            for x in np.linspace(inner, 0.2, 12):
                V.append((sg * x, -0.12, z))
                piece.append(k)
    t = np.linspace(0, 2 * np.pi, 60, endpoint=False)
    for z in (HPS - 0.01, HPS + 0.02):  # the stand: a ring 60 mm radius
        for a in t:
            V.append((0.06 * np.sin(a), 0.06 * np.cos(a), z))
            piece.append(2)
    for a in t:  # the fall
        x, y = 0.065 * np.sin(a), 0.065 * np.cos(a)
        V.append((x, y, HPS + 0.05 if standing else HPS - 0.005))
        piece.append(3)
    if not standing:  # (turned: the points, front view)
        off, drop = (0.073, 0.055) if spread else (0.025, 0.03)
        for sg in (1, -1):
            V.append((sg * off, -0.07, HPS - drop))
            piece.append(3)
    V = np.asarray(V, float)
    piece = np.asarray(piece)
    L = np.where(piece == 0)[0]
    R = np.where(piece == 1)[0]
    pairs = []
    for drop in (0.04, 0.083, 0.17, 0.25, 0.33):
        z = HPS - drop
        a = L[np.argmin(np.abs(V[L, 2] - z) + np.abs(V[L, 0] - V[L, 0].min()))]
        b = R[np.argmin(np.abs(V[R, 2] - z) + np.abs(V[R, 0] - V[R, 0].max()))]
        if drop < v_drop and not open_front:  # (undone: the pair vertices where the V opens)
            pass
        if open_front:
            b = R[np.argmin(np.abs(V[R, 2] - z) + np.abs(V[R, 0] + 0.06))]
        pairs.append([int(a), int(b)])
    M = {"names": names, "piece": piece, "closures": [{"name": "front", "v": pairs}], "F": np.zeros((0, 3), int)}
    return V, M


def test_planted_closed_front_reads_closed_with_its_v():
    V, M = _front_mesh(open_front=False, v_drop=0.06)
    r = gr.front_reads(V, M, HPS)
    assert r["front_state"] == "closed", r
    assert abs(r["v_bottom_below_hps_mm"] - 60) <= 6, r["v_bottom_below_hps_mm"]
    assert r["buttons_total"] == 5


def test_planted_open_front_reads_open():
    V, M = _front_mesh(open_front=True)
    r = gr.front_reads(V, M, HPS)
    assert r["front_state"] == "open" and r["v_bottom_below_hps_mm"] is None, r
    assert r["buttons_done"] == 0 and r["first_done_below_hps_mm"] is None


def test_planted_collars_standing_closed_spread():
    for kw, want in (({"standing": True}, "standing"), ({}, "closed"), ({"spread": True}, "spread")):
        V, M = _front_mesh(open_front=False, **kw)
        r = gr.collar_reads(V, M, HPS)
        assert r["collar_state"] == want, (kw, r)
    V, M = _front_mesh(open_front=False, spread=True)
    r = gr.collar_reads(V, M, HPS)
    assert abs(r["collar_points_apart_mm"] - 146) <= 4 and abs(r["collar_points_below_hps_mean_mm"] - 55) <= 1, r


# ----------------------------------------------------------------------------------------------- C98: checklist rows
ITEMS = [{"id": "front_state", "stage": 1, "read": "front_state", "equals": "closed", "on": "fit"},
         {"id": "v", "stage": 1, "read": "v_bottom_below_hps_mm", "range": [45, 75], "on": "fit"},
         {"id": "spread", "stage": 1, "read": "collar_points_apart_mm", "range": [127, 167], "on": "fit"},
         {"id": "band", "stage": 3, "read": "collar_stand_cb_mm", "range": [30, 38], "on": "flat"},
         {"id": "words", "stage": 2, "ref": "no machine target: not a row"}]


def test_checklist_items_become_rows_ordered_big_first(tmp_path, monkeypatch):
    from hifipushie import store
    monkeypatch.setattr(store, "HOME", tmp_path)
    (tmp_path / "checklists").mkdir()
    (tmp_path / "checklists" / "t_shirt.json").write_text(json.dumps({"items": ITEMS}))
    piece, items = gr.checklist_items({"checklist": "t_shirt"})
    assert piece == "t_shirt" and len(items) == 5
    V, M = _front_mesh(open_front=False, spread=False)  # closed front, CLOSED collar: spread fails
    rd = {**gr.front_reads(V, M, HPS), **gr.collar_reads(V, M, HPS)}
    rows = {r["id"]: r for r in gr.checklist_rows(items, rd, "fit")}
    assert "checklist:words" not in rows
    assert rows["checklist:front_state"]["status"] == "PASS" and rows["checklist:v"]["status"] == "PASS"
    assert rows["checklist:spread"]["status"] == "FAIL"
    assert rows["checklist:band"]["status"] == "LATER"  # (read on the flat draft)
    assert gr.checklist_rows(items, {}, "flat")[-1]["status"] == "UNMEASURED"  # (flat item, no reading: blocks)
    # the fit record path: rows from the spec's checklist, a failing big read blocks the detail rows (C52)
    res = {"mesh": M, "body": type("B", (), {"at": {"hps.L": np.array([0.08, 0.0, HPS])}})()}
    fr = cc.fit_rows(res, V, 3.0, False, g={"checklist": "t_shirt"})
    st = {r["id"]: r["status"] for r in fr}
    assert st["checklist:spread"] == "FAIL" and st["fit_strain_p99"] == "PASS"
    assert cc.verdict(fr) == "FAIL"
    assert [r.get("stage", 3) for r in fr] == sorted(r.get("stage", 3) for r in fr)
    V2, M2 = _front_mesh(open_front=False, spread=True)
    fr2 = cc.fit_rows({"mesh": M2, "body": res["body"]}, V2, 3.0, False, g={"checklist": "t_shirt"})
    assert cc.verdict(fr2) == "PASS", [(r["id"], r["status"]) for r in fr2]


def test_worn_big_reads_without_a_checklist_item_are_unmeasured():
    kind_items = [{"id": "front", "measure": "front_state"}, {"id": "c", "measure": "collar_state"}]
    assert gr.uncovered_form_reads(kind_items, ITEMS[:1]) == ["collar_state"]
    assert gr.uncovered_form_reads(kind_items, ITEMS) == []
    row = cc.gate_rows({"pieces": {}, "seams": []}, [{"id": "front", "stage": 1, "measure": "front_state"}])[-1]
    assert row["status"] == "FORM", row  # (C97: not "SIM" on a path with no sim)


# ----------------------------------------------------------------------------------------------- C101: collar rules
def _collar_bp(neck_mm, stand_mm=35.0, stand_end_mm=30.0, fall_mm=55.0, run_off=False):
    """A stand + fall collar for a neck girth: the stand's neck edge = the neck girth (slight curve), its CB height
    stand_mm tapering to stand_end_mm at the ends; the fall sewn to the stand's top, fall_mm deep, a roll fold 4 mm
    above its seam (run_off: the fold runs off before the ends)."""
    h = neck_mm / 2000
    xs = np.linspace(-h, h, 21)
    bow = 0.01 * (1 - (xs / h) ** 2)
    top_h = (stand_mm - (stand_mm - stand_end_mm) * (xs / h) ** 2) / 1000
    P = np.r_[np.c_[xs, bow], np.c_[xs[::-1], (bow + top_h)[::-1]]]
    sn = {"lb": 0, "bm": 10, "rb": 20, "rt": 21, "tm": 31, "lt": 41}
    Q = np.r_[np.c_[xs, bow + top_h], np.c_[xs[::-1], (bow + top_h + fall_mm / 1000)[::-1]]]
    fnm = {"flb": 0, "fbm": 10, "frb": 20, "frt": 21, "ftm": 31, "flt": 41}
    fold = {"piece": "collar", "kind": "roll", "line": {"edge": "flb>fbm>frb", "offset": 0.004}}
    if run_off:
        fold["run_off"] = {"ends": "both", "off": 0.03}
    return {"pieces": {"stand": {"name": "stand", "P": P, "names": sn, "marks": {}},
                       "collar": {"name": "collar", "P": Q, "names": fnm, "marks": {}}},
            "seams": [("stand:lb>bm>rb", ["front.R:a>b", "yoke:c>d", "front.L:e>f"]), ("collar:flb>fbm>frb", "stand:lt>tm>rt")],
            "folds": [fold]}


@pytest.mark.parametrize("neck", [360.0, 406.5, 450.0])
def test_collar_rules_any_stand_and_fall_three_necks(neck):
    g = {"fabric": "shirting"}
    r = gr.collar_draft_reads(_collar_bp(neck), g)
    assert abs(r["collar_stand_cb_mm"] - 35) <= 0.6 and abs(r["collar_fall_cb_mm"] - 55) <= 0.6, r
    assert r["collar_roll_above_seam_mm"] == 4.0 and 1.5 < r["collar_turn_mm"] < 3.0, r  # (C43: from the stack)
    assert abs(min(r["collar_stand_ends_mm"]) - 30) <= 2.0, r
    rows = {x["id"]: x["status"] for x in cc.collar_rule_rows(_collar_bp(neck), g)}
    assert rows == {"collar_fall_cover": "PASS", "collar_fold_run": "PASS"}, rows
    # a fall too shallow to cover the stand seam; a fold that runs off where the stand still stands (points flip)
    assert {x["id"]: x["status"] for x in cc.collar_rule_rows(_collar_bp(neck, fall_mm=42), g)}["collar_fall_cover"] == "FAIL"
    assert {x["id"]: x["status"] for x in cc.collar_rule_rows(_collar_bp(neck, run_off=True), g)}["collar_fold_run"] == "FAIL"
    # a jacket-like stand that runs off at its ends with a fold that runs off: agrees
    rj = gr.collar_draft_reads(_collar_bp(neck, stand_end_mm=2.0, run_off=True), g)
    assert rj["collar_stand_runs_off"] and rj["collar_fold_agrees"], rj


# ----------------------------------------------------------------------------------------------- C100: lit vs lit
def test_colour_row_compares_lit_with_lit(tmp_path):
    from PIL import Image
    a = np.zeros((40, 40, 3), np.uint8)
    a[:, :20] = (173, 169, 167)
    a[:, 20:] = (120, 117, 115)  # (shadow side)
    Image.fromarray(a).save(tmp_path / "a.png")
    pa = gr.colour_patch(tmp_path / "a.png", (0, 0, 1, 1))
    it = {"id": "colour_lit", "ref_rgb": [173, 169, 167], "tol_rgb": 8, "hue_rb": [4, 8]}
    assert gr.colour_row(it, pa)["status"] == "PASS", pa
    b = a.copy()
    b[:, :20] = (158, 160, 157)  # (round 1 under the clay rig: cool, dark)
    Image.fromarray(b).save(tmp_path / "b.png")
    assert gr.colour_row(it, gr.colour_patch(tmp_path / "b.png", (0, 0, 1, 1)))["status"] == "FAIL"


# ----------------------------------------------------------------------------------------------- tucked (design key)
def _cylinder(r, z0, z1, n=48, m=30):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    zs = np.linspace(z0, z1, m)
    V = np.array([(r * np.cos(a), r * np.sin(a), z) for z in zs for a in t])
    F = []
    for j in range(m - 1):
        for i in range(n):
            a, b, c, d = j * n + i, j * n + (i + 1) % n, (j + 1) * n + i, (j + 1) * n + (i + 1) % n
            F += [(a, b, d), (a, d, c)]
    return V, np.asarray(F)


def test_tucked_pulls_the_cloth_below_the_line_to_the_body_and_reads_it():
    import types
    from hifipushie import pattern_form as pf
    BV, BT = _cylinder(0.15, 0.6, 1.4)
    body = types.SimpleNamespace(V=BV, T=BT, at={"waist_z": np.array([1.0]), "hps.L": np.array([0.08, 0, 1.5])})
    t = np.linspace(0, 2 * np.pi, 48, endpoint=False)
    zs = np.arange(0.75, 1.2, 0.01)  # (a shirt body flaring 30 mm off below the waist, 5 mm above)
    X = np.array([((0.15 + (0.03 if z < 1.0 else 0.005)) * np.cos(a), (0.15 + (0.03 if z < 1.0 else 0.005)) * np.sin(a), z)
                  for z in zs for a in t])
    M = {"names": ["front.L"], "piece": np.zeros(len(X), int)}
    res = {"body": body, "mesh": M}
    g = {"tucked": True}
    before = gr.tuck_reads(X, body, gr.tuck_line_z(body, g))
    assert before["tuck_standoff_p90_mm"] > 25, before
    X2, info = pf.tuck(res, X, g)
    after = gr.tuck_reads(X2, body, gr.tuck_line_z(body, g))
    assert after["tuck_standoff_p90_mm"] <= pf.TUCK_CAP * 1000 + 0.5, after
    assert info["moved"] > 0 and len(info["hidden"]) == int((X[:, 2] < 1.0).sum())
    above = X[:, 2] >= 1.0
    assert np.allclose(X2[above], X[above])  # (C109: above the LINE nothing moves: no faded ring over the waistband)
    assert gr.tuck_line_z(body, {}) is None


def test_tucked_cloth_slides_into_the_trousers_instead_of_stretching():
    """C109: a tube hanging straight past a hollow (the small of the back) is pulled into the hollow below the line;
    held where it hung, its vertical edges stretch (the round-2 tuck: back p99 50 %); the slide gives the hidden edges
    their pattern length back while the cloth above the line stays put."""
    import types
    from hifipushie import pattern_form as pf
    t = np.linspace(0, 2 * np.pi, 48, endpoint=False)
    zs = np.arange(0.70, 1.2, 0.01)
    rb = lambda z: 0.15 - 0.03 * np.exp(-((z - 0.9) / 0.06) ** 2)  # (a 30 mm hollow 100 mm below the line)
    BV = np.array([(rb(z) * np.cos(a), rb(z) * np.sin(a), z) for z in np.arange(0.6, 1.3, 0.01) for a in t])
    _, BT = _cylinder(0.15, 0.6, 1.3, n=48, m=len(np.arange(0.6, 1.3, 0.01)))
    body = types.SimpleNamespace(V=BV, T=BT, at={"waist_z": np.array([1.0]), "hps.L": np.array([0.08, 0, 1.5])})
    X = np.array([(0.16 * np.cos(a), 0.16 * np.sin(a), z) for z in zs for a in t])
    _, F = _cylinder(0.16, 0.7, 1.19, n=48, m=len(zs))
    ang = np.arange(len(X)) % 48 * (2 * np.pi * 0.16 / 48)
    uv = np.c_[ang, X[:, 2]]  # (the tube unrolled: its pattern; the seam column's wrap is ignored below)
    M = {"names": ["back"], "piece": np.zeros(len(X), int), "F": F, "uv": uv}
    res = {"body": body, "mesh": M}
    E = np.unique(np.sort(np.r_[F[:, [0, 1]], F[:, [1, 2]]], 1), axis=0)
    vert = E[np.abs(E[:, 1] - E[:, 0]) == 48]  # (the vertical edges)
    lo = vert[X[vert[:, 0], 2] < 0.98]

    def stretch(Y):
        return np.linalg.norm(Y[lo[:, 0]] - Y[lo[:, 1]], axis=1) / np.linalg.norm(uv[lo[:, 0]] - uv[lo[:, 1]], axis=1) - 1

    held = pf.TUCK_SLIDE_ITERS
    try:
        pf.TUCK_SLIDE_ITERS = 0
        X0, _ = pf.tuck(res, X, {"tucked": True})
    finally:
        pf.TUCK_SLIDE_ITERS = held
    X2, info = pf.tuck(res, X, {"tucked": True})
    assert stretch(X0).max() > 0.08, stretch(X0).max()  # (held where it hung: the hollow stretches it)
    s2 = stretch(X2)
    assert s2.max() < 0.03, (s2.max(), X[lo[np.argsort(-s2)[:5], 0], 2])  # (slid: its length back)
    assert np.allclose(X2[X[:, 2] >= 1.0], X[X[:, 2] >= 1.0]) and info["slide_max_mm"] > 0
    d = pf._body_surface(body).signed(X2[X[:, 2] < 0.98])[0]
    assert d.max() <= pf.TUCK_CAP + 1e-6  # (and still under the cap)


# ----------------------------------------------------------------------------------------------- C100: own colour
def test_own_colour_objects_take_the_spec_colour_and_stripe(monkeypatch):
    from hifipushie import server, store
    spec = {"cloth": {"shirt": {"color": "#bdb8b4", "stripe": {"pitch_mm": 2.5, "contrast": 0.03}, "roughness": 0.8}}}
    monkeypatch.setattr(store, "load", lambda name: spec)
    objs = [{"name": "body", "V": np.zeros((3, 3)), "F": np.zeros((1, 3), int), "color": "#c9b8a6"},
            {"name": "shirt", "V": np.zeros((3, 3)), "F": np.zeros((1, 3), int), "color": "#5b7fa6",
             "mesh": {"uv": np.zeros((3, 2))}}]
    out = server.own_colour_objects("m", objs)
    assert out[0]["color"] == "#c9b8a6"  # (the body keeps its own)
    assert out[1]["color"] == "#bdb8b4" and out[1]["stripe"]["pitch_mm"] == 2.5 and out[1]["roughness"] == 0.8
    assert out[1]["uv"].shape == (3, 2) and objs[1]["color"] == "#5b7fa6"  # (the clay objects unchanged)


# ----------------------------------------------------------------------------------- C218: the lapel FACE (canvas s12)
def _lapel_mesh(lean_deg=0.0, yaw_deg=0.0, end=386.0, taper=0.25):
    """front.L / front.R: a forepart sheet (y -0.12) from the roll edge out to 0.2 m, and a turned lapel (y -0.125)
    from the roll edge out by w(d) = taper x (end - d) mm (d below HPS, 90..end), yawed yaw_deg about the roll (its
    outer edge swung back in y); the roll edge leans lean_deg toward CF going down (60 mm off CF at 90 below HPS).
    Returns X, M, turned (bool per face)."""
    V, piece, F, turned = [], [], [], []
    ds = np.arange(90.0, 600.0, 4.0)
    for k, sg in ((0, 1), (1, -1)):
        for part in ("front", "lapel"):
            base = len(V)
            for d in ds:
                e = 60.0 - (d - 90.0) * math.tan(math.radians(lean_deg))
                w = max(taper * (end - d), 0.0) if part == "lapel" else 200.0 - e
                for u in np.linspace(0.0, 1.0, 9):
                    x = e + u * w * math.cos(math.radians(yaw_deg))
                    y = -0.12 if part == "front" else -0.125 + u * w * math.sin(math.radians(yaw_deg)) / 1000
                    V.append((sg * x / 1000, y, HPS - d / 1000))
                    piece.append(k)
            n = len(ds)
            for i in range(n - 1):
                if part == "lapel" and ds[i] >= end:
                    break
                for j in range(8):
                    a, b, c, dd = base + i * 9 + j, base + i * 9 + j + 1, base + (i + 1) * 9 + j, base + (i + 1) * 9 + j + 1
                    F += [(a, b, dd), (a, dd, c)]
                    turned += [part == "lapel"] * 2
    M = {"names": ["front.L", "front.R"], "piece": np.asarray(piece), "F": np.asarray(F), "closures": []}
    return np.asarray(V, float), M, np.asarray(turned)



def test_lapel_face_reads_a_known_flat_lapel():
    """C218: a flat lapel w = 0.25 x (386 - d) mm reads its own width at each row (+-1 mm), both sides, and its face ends
    at the break (386, the concept's)."""
    X, M, t = _lapel_mesh()
    r = gr.lapel_face_reads(X, M, HPS, turned=t)
    for s in "LR":
        for d in (150, 200, 250, 300, 350):
            assert abs(r[f"lapel_face_{s}_{d}_mm"] - 0.25 * (386 - d)) <= 1.0, (s, d, r)
        assert abs(r[f"lapel_face_end_below_hps_{s}_mm"] - 386) <= 4.0, r


def test_lapel_face_is_perpendicular_to_the_roll_and_shows_the_turn_aside():
    """C218: a roll edge leaning 15 deg reads the face perpendicular to it (horizontal width x cos 15); a lapel turned 40
    deg aside (C212's sideways faces) reads foreshortened (x cos 40): the front view, like the traced concept."""
    X, M, t = _lapel_mesh(lean_deg=15.0)
    r = gr.lapel_face_reads(X, M, HPS, turned=t)
    assert abs(r["lapel_face_L_200_mm"] - 0.25 * 186 * math.cos(math.radians(15))) <= 1.5, r
    X, M, t = _lapel_mesh(yaw_deg=40.0)
    r = gr.lapel_face_reads(X, M, HPS, turned=t)
    assert abs(r["lapel_face_L_200_mm"] - 0.25 * 186 * math.cos(math.radians(40))) <= 1.0, r
    # a lapel whose face ends 55 mm high (Garrett d2: 330) reads 0 at 350, not the outer edge's offset
    X, M, t = _lapel_mesh(end=331.0)
    r = gr.lapel_face_reads(X, M, HPS, turned=t)
    assert r["lapel_face_L_350_mm"] == 0.0 and abs(r["lapel_face_end_below_hps_L_mm"] - 331) <= 4.0, r
