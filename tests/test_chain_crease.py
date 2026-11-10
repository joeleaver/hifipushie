"""chain_crease (R3d): every planned fold turned to its turn_deg, lying on its lies_on, lengths exact. A rectangular soft
panel laid on a cylinder (the body a cylinder inside it), with a fold row across it: turned 180 onto itself (one LAYER
outside, lengths within the 2 % rule, the fold line still), 90 free, a row cutting off a corner (a lapel: only the cut-off
region turns, nothing tears), a row that stops inside the piece (the turn fades past its end), a piece with no planned fold
untouched bit for bit, a FALL's fold not turned twice, and the gate's row."""
import types

import numpy as np
import pytest

from hifipushie import chain_crease as cc, chain_net as cn, chain_stages as cst
from hifipushie.chain_core import LAYER, MAX_FREE_PCT, Body

H = 0.01
NX, NY = 31, 21  # 0.30 x 0.20 m
R = 0.15  # the panel's radius on the cylinder


def _grid(z0=0.0):
    uv = np.array([[i * H, j * H] for j in range(NY) for i in range(NX)])
    F = []
    for j in range(NY - 1):
        for i in range(NX - 1):
            a = j * NX + i
            F += [[a, a + 1, a + NX + 1], [a, a + NX + 1, a + NX]]  # (diagonals (i, j) -> (i+1, j+1))
    X = np.c_[R * np.sin(uv[:, 0] / R), -R * np.cos(uv[:, 0] / R), uv[:, 1] + z0]
    return uv, np.array(F), X


def vid(i, j, off=0):
    return off + j * NX + i


def _body():
    th = np.linspace(0, 2 * np.pi, 160, endpoint=False)
    zs = np.linspace(-0.2, 0.8, 60)
    V = np.array([[(R - 0.01) * np.cos(t), (R - 0.01) * np.sin(t), z] for z in zs for t in th])
    T = []
    m = len(th)
    for k in range(len(zs) - 1):
        for i in range(m):
            a, b_, c, d = k * m + i, k * m + (i + 1) % m, (k + 1) * m + (i + 1) % m, (k + 1) * m + i
            T += [[a, b_, c], [a, c, d]]  # (outward)
    return Body(V, np.array(T), {})


BODY = _body()


def _build(rows, turn_deg, lies_on, kind="press", second=False, holds=None, plan=True):
    uv, F, X = _grid()
    piece = np.zeros(len(uv), int)
    names = ["panel"]
    if second:  # a second panel, no fold, higher up
        uv2, F2, X2 = _grid(z0=0.3)
        F = np.r_[F, F2 + len(uv)]
        uv, X = np.r_[uv, uv2 + [0.5, 0]], np.r_[X, X2]
        piece = np.r_[piece, np.ones(len(uv2), int)]
        names.append("other")
    M = {"uv": uv, "F": F, "piece": piece, "names": names, "sew": np.zeros((0, 2), int),
         "folds": [{"piece": "panel", "name": "crease", "kind": kind, "rows": [list(r) for r in rows]}]}
    net = cn.Network(M)
    w = {"folds": {"crease.bend": {"on": "panel", "fold": "crease", "turn_deg": turn_deg, "lies_on": lies_on}}} if plan else {}
    return types.SimpleNamespace(net=net, X=X.copy(), body=BODY, wear=w, reads={}, holds=holds,
                                 pat=types.SimpleNamespace(fold_radius={}))


def _links_pct(b):
    net = b.net
    l = np.linalg.norm(b.X[net.link_j] - b.X[net.link_i], axis=1)
    return float(np.abs(l / net.link_L - 1).max() * 100)


def _radial(X):
    return np.linalg.norm(X[:, :2], axis=1) - R


ROW13 = [vid(i, 13) for i in range(NX)]


def test_turned_180_onto_itself_sits_one_layer_outside_lengths_exact_fold_line_still():
    b = _build([ROW13], 180, "panel")
    X0 = b.X.copy()
    rd = cc.turn_all(b)["crease.bend"]
    uv = b.net.uv
    far = uv[:, 1] > 0.13 + 0.015
    assert abs(float(np.median(_radial(b.X[far]))) - LAYER) < 0.0005  # (one LAYER outside the held side)
    j = np.where(far)[0]
    assert np.allclose(b.X[j, 2], 0.26 - uv[j, 1], atol=0.001)  # (folded right back: v -> 2 * 0.13 - v)
    assert _links_pct(b) < MAX_FREE_PCT
    mv = np.linalg.norm(b.X[ROW13] - X0[ROW13], axis=1)
    assert mv.max() < 0.001 and np.median(mv) < 0.0001  # (the fold line doesn't move; its two end points < 1 mm)
    assert abs(rd["measured_deg"] - 180) < 5 and rd["off_least_mm"] >= -0.5
    assert b.reads["stages"]["crease"]["verdict"] == "PASS"
    assert np.allclose(b.X[uv[:, 1] < 0.12], X0[uv[:, 1] < 0.12], atol=1e-4)  # (the held side stays)


def test_turned_90_free_stands_out_at_its_angle():
    row = [vid(20, j) for j in range(NY)]  # (up the cylinder: a flange standing out along it is isometric)
    b = _build([row], 90, "free")
    rd = cc.turn_all(b)["crease.bend"]
    uv = b.net.uv
    edge = uv[:, 0] > 0.295
    assert abs(rd["measured_deg"] - 90) < 5
    assert 0.09 < float(np.median(_radial(b.X[edge]))) < 0.101  # (stands out its 0.10 m, its laid curvature kept)
    assert _links_pct(b) < MAX_FREE_PCT and "off_least_mm" not in rd


def test_a_row_cutting_off_a_corner_turns_only_that_region_and_nothing_tears():
    row = [vid(20 + k, k) for k in range(11)]  # (the bottom edge at u 0.20 to the right edge at v 0.10: a lapel's corner)
    b = _build([row], 170, "panel")
    X0 = b.X.copy()
    rd = cc.turn_all(b)["crease.bend"]
    uv = b.net.uv
    cut = uv[:, 0] - uv[:, 1] > 0.20 + 1e-9
    rest = uv[:, 0] - uv[:, 1] < 0.20 - 1e-9
    assert rd["split"] and rd["turned_v"] == int(cut.sum())
    assert np.linalg.norm(b.X[rest] - X0[rest], axis=1).max() < 0.001  # (only the cut-off region turns)
    corner = vid(NX - 1, 0)
    assert np.linalg.norm(b.X[corner] - X0[corner]) > 0.08  # (the corner turned back over the line)
    assert _links_pct(b) < MAX_FREE_PCT  # (nothing tears: the right edge bends at the row's end)
    assert abs(rd["measured_deg"] - 170) <= cc.TURN_TOL and rd["off_least_mm"] >= -0.5
    assert b.reads["stages"]["crease"]["verdict"] == "PASS"


def test_a_row_stopping_inside_the_piece_turns_its_span_and_fades_past_its_end():
    row = [vid(i, 13) for i in range(15, NX)]  # (from the right edge to u 0.15, inside the piece)
    b = _build([row], 90, "free")
    X0 = b.X.copy()
    rd = cc.turn_all(b)["crease.bend"]
    uv = b.net.uv
    assert not rd["split"]
    below = (uv[:, 1] < 0.12) & (uv[:, 0] > 0.15 + cc.FADE)  # (the held side under the line, away from its inner end:
    #   round the end the cloth bends, a crease dying inside a piece is a cone)
    inside = (uv[:, 0] > 0.18) & (uv[:, 1] > 0.17)
    assert np.linalg.norm(b.X[below] - X0[below], axis=1).max() < 0.003  # (the held side stays)
    assert rd["turned_v"] < int((uv[:, 1] > 0.13).sum())  # (not the whole far side: the span and its fade)
    assert np.linalg.norm(b.X[inside] - X0[inside], axis=1).min() > 0.02  # (its span turned)
    assert _links_pct(b) < MAX_FREE_PCT  # (the cloth past the end bends, never tears)


def test_a_piece_with_no_planned_fold_is_untouched_bit_for_bit():
    b = _build([ROW13], 180, "panel", second=True)
    X0 = b.X.copy()
    cc.turn_all(b)
    o = b.net.verts("other")
    assert np.array_equal(b.X[o], X0[o])
    b = _build([ROW13], 180, "panel", plan=False)  # (nothing planned: nothing turned, no stage)
    X0 = b.X.copy()
    cc.turn_all(b)
    assert np.array_equal(b.X, X0) and "stages" not in b.reads and "crease" not in b.reads


def test_a_fall_is_not_turned_twice():
    holds = types.SimpleNamespace(folds=[{"piece": "panel", "name": "crease", "fall": True}], plies={}, layers={})
    b = _build([ROW13], 180, "panel", kind="roll", holds=holds)
    X0 = b.X.copy()
    rd = cc.turn_all(b)
    assert np.array_equal(b.X, X0) and rd["crease.bend"]["turned_by"] == "fall"


def test_a_roll_keeps_its_radius_two_radii_apart_at_180():
    b = _build([ROW13], 180, "free", kind="roll")
    cc.turn_all(b)
    far = b.net.uv[:, 1] > 0.13 + 0.015
    assert abs(float(np.median(_radial(b.X[far]))) - 2 * LAYER) < 0.0005


def test_a_planned_fold_the_draft_has_no_row_for_is_refused():
    b = _build([ROW13], 180, "panel")
    b.wear["folds"]["crease.bend"]["fold"] = "nothing"
    with pytest.raises(cc.ChainRefused, match="step 4"):
        cc.turn_all(b)


def test_the_gate_fails_a_turn_off_its_plan_and_a_side_sunk_inside():
    b = types.SimpleNamespace(reads={"crease": {
        "a": {"measured_deg": 150.0, "planned_deg": 170.0, "lies_on": "front", "piece": "front", "fold": "roll",
              "off_least_mm": 1.0, "off_median_mm": 3.0, "gap_mm": 3.0, "worst_link_pct": 0.1},
        "b": {"measured_deg": 168.0, "planned_deg": 170.0, "lies_on": "body", "piece": "front", "fold": "roll",
              "off_least_mm": -2.0, "off_median_mm": 3.0, "gap_mm": 4.5, "worst_link_pct": 0.1},
        "c": {"measured_deg": 160.0, "planned_deg": 170.0, "lies_on": "free", "piece": "front", "fold": "roll",
              "worst_link_pct": 0.1}}})
    g = cc.gate(b, None)
    st = {r["id"]: r["status"] for r in g["rows"]}
    assert st == {"fold:a": "FAIL", "fold:b": "FAIL", "fold:c": "PASS"} and g["back_to"] == "2"
    assert "step 4's fold line" in next(r for r in g["rows"] if r["id"] == "fold:a")["change"]
    assert "crease" in cst.STAGES
