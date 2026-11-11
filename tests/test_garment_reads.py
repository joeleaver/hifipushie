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

