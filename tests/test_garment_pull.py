"""Pull / turn / smooth / hold until it would stretch (C142-C144, garment_pull.py): known answers.

1. A slack strip (pattern 300 x 20 mm) hung as an arc between its pinned end and a free end 200 mm away: its free end
   pulled stops within one step of where the pattern length (+ tol) runs out: along the chord at L (1 + tol) - a,
   straight up at sqrt((L (1 + tol))^2 - a^2).
2. Simon's shirt on wf_simon (the shirt spike's closed fit v1: the repo defaults + the concept's first button 34 mm
   below cfNeck) styled as the spike did y3 (gp.style): the band ends turned 30 deg about Simon's hinges by their 3
   corner vertices (patch 0, as y3 did; the area turn is test 3), the collar
   points pulled out / side / up (each grabbing a 25 mm patch that turns), collar + stand smoothed: near the spike's
   y3 / sm1 (points 142 apart (y3 147), 64 / 60 below HPS (y3 63 / 59), collar crumple p95 0.28 mm), the tips as
   clean as the closed collar's (crumple, stretch max; at most 1 folded face). NOT asserted: the right tip's twist
   (closed 35 deg, this 63, the spike's sm1 47): an open fault.
3. The same shirt styled as the spike's sp10 (C144 / C145): back + sides held where the relaxed fit has them,
   feathered, band ends turned as areas, points pulled (mirrored), the outer edge smoothed toward one curve, smoothed:
   the collar hugs the neck at CB / sides, the band corner keeps its stretch, the edge one swoop.
2 and 3 need the workspace model (HIFIPUSHIE_HOME with wf_simon, HIFIPUSHIE_ASSETS); ~4 min:
   HIFIPUSHIE_HOME=/home/joe/dev/hifipushie/workspace HIFIPUSHIE_ASSETS=/home/joe/dev/hifipushie/workspace/_templates \
     /mnt/data/hifipushie/bin/capped uv run pytest tests/test_garment_pull.py
"""
import os
from pathlib import Path

import numpy as np
import pytest
from scipy.optimize import brentq

from hifipushie import garment_pull as gp
from hifipushie import pattern_form as pf

L, WIDTH, CHORD = 0.30, 0.02, 0.20


def _strip():
    nx, ny = 61, 5
    uv = np.array([(x, y) for x in np.linspace(0, L, nx) for y in np.linspace(0, WIDTH, ny)])
    ix = lambda i, j: i * ny + j
    F = [f for i in range(nx - 1) for j in range(ny - 1)
         for f in ((ix(i, j), ix(i + 1, j), ix(i + 1, j + 1)), (ix(i, j), ix(i + 1, j + 1), ix(i, j + 1)))]
    th = brentq(lambda t: 2 * (L / t) * np.sin(t / 2) - CHORD, 1e-3, 2 * np.pi - 1e-3)  # the arc: length L, chord a
    R = L / th
    ang = uv[:, 0] / R - th / 2
    X = np.c_[R * np.sin(ang) + CHORD / 2, uv[:, 1], -(R * np.cos(ang) - R * np.cos(th / 2))]
    M = {"F": np.array(F), "uv": uv, "piece": np.zeros(len(uv), int), "names": ["strip"], "sew": [],
         "points": {"strip:tipA": ix(nx - 1, 0), "strip:tipB": ix(nx - 1, ny - 1)}}
    return M, X, uv[:, 0] < 1e-9


@pytest.mark.parametrize("d, answer", [([1, 0, 0], lambda t: L * (1 + t) - CHORD),
                                       ("up", lambda t: np.sqrt((L * (1 + t)) ** 2 - CHORD ** 2))])
def test_slack_strip_stops_where_its_length_runs_out(d, answer):
    M, X, held = _strip()
    step, tol = 0.003, 0.002
    Xn, info = gp.pull(M, X, held, [{"at": "strip:tipA..tipB", "dir": d}], step=step, tol=tol, max_move=0.4)
    moved = info["moved_mm"]["strip:tipA..tipB"] / 1000
    assert info["stopped"] == "stretch"
    assert abs(moved - answer(tol)) <= step + 1e-9, (moved, answer(tol))
    assert np.allclose(Xn[held], X[held])
    assert info["stretch_p99_end"] < 2.0


def test_side_is_never_taken_at_cf():
    M, X, held = _strip()
    X = X - [X[:, 0].max(), 0, 0]  # the free end at x = 0
    with pytest.raises(ValueError, match="side_from"):
        gp.pull(M, X, held, [{"at": "strip:tipA", "dir": "side"}])


def test_a_sequence_picks_a_grip_up_again():
    """Two pulls of the same border (the first stopped short by max_move) go as far as one: re-gripping releases it."""
    M, X, held = _strip()
    h = [{"at": "strip:tipA..tipB", "dir": [1, 0, 0]}]
    _, infos = gp.style(M, X, held, [{"pull": {"handles": h, "max_move": 0.03, "tol": 0.002}},
                                     {"pull": {"handles": h, "max_move": 0.4, "tol": 0.002}}])
    a, b = infos[0]["pull"], infos[1]["pull"]
    assert a["stopped"] == "max_move" and b["stopped"] == "stretch"
    total = (a["moved_mm"]["strip:tipA..tipB"] + b["moved_mm"]["strip:tipA..tipB"]) / 1000
    assert abs(total - (L * 1.002 - CHORD)) <= 0.003 + 1e-9, total


def test_smooth_flattens_ripples_without_stretching():
    """A flat sheet with 0.5 mm ripples across it (its pattern flat): smooth takes most of them out and the stretch
    doesn't rise (the pull's rule)."""
    n = 41
    uv = np.array([(x, y) for x in np.linspace(0, 0.2, n) for y in np.linspace(0, 0.2, n)])
    ix = lambda i, j: i * n + j
    F = [f for i in range(n - 1) for j in range(n - 1)
         for f in ((ix(i, j), ix(i + 1, j), ix(i + 1, j + 1)), (ix(i, j), ix(i + 1, j + 1), ix(i, j + 1)))]
    rng = np.random.default_rng(1)
    X = np.c_[uv, 0.0005 * rng.standard_normal(len(uv))]
    M = {"F": np.array(F), "uv": uv, "piece": np.zeros(len(uv), int), "names": ["sheet"], "sew": [], "points": {}}
    edge = (uv.min(1) < 1e-9) | (uv.max(1) > 0.2 - 1e-9)
    X[edge, 2] = 0.0
    Xn, info = gp.smooth(M, X, edge, ["sheet"])
    r0, r1 = info["rough_p95_mm"]
    assert info["rounds"] > 0 and r1 < 0.5 * r0, info
    assert info["stretch_p99"][1] <= info["stretch_p99"][0] + 100 * gp.TOL, info
    assert np.allclose(Xn[edge], X[edge])


def test_smooth_border_takes_a_wobble_out_without_stretching():
    """A flat sheet whose top border wobbles +-1 mm out of plane (6 waves over 200 mm), its bottom row held: the border
    smoothed toward one fitted curve (C145) loses most of its kink and the stretch falls, not rises."""
    nx, ny = 81, 21
    uv = np.array([(x, y) for x in np.linspace(0, 0.2, nx) for y in np.linspace(0, 0.05, ny)])
    ix = lambda i, j: i * ny + j
    F = [f for i in range(nx - 1) for j in range(ny - 1)
         for f in ((ix(i, j), ix(i + 1, j), ix(i + 1, j + 1)), (ix(i, j), ix(i + 1, j + 1), ix(i, j + 1)))]
    X = np.c_[uv, np.zeros(len(uv))]
    top = uv[:, 1] > 0.05 - 1e-9
    X[top, 2] = 0.001 * np.sign(np.sin(uv[top, 0] / 0.2 * 2 * np.pi * 6) + 1e-9)
    M = {"F": np.array(F), "uv": uv, "piece": np.zeros(len(uv), int), "names": ["sheet"], "sew": [],
         "points": {"sheet:tl": ix(0, ny - 1), "sheet:tr": ix(nx - 1, ny - 1)}}
    held = uv[:, 1] < 1e-9
    Xn, info = gp.smooth_border(M, X, held, "sheet:tl..tr", ends=0.02)
    k0, k1 = info["kink_deg"]
    assert info["rounds"] > 0 and k1 < 0.65 * k0, info  # (38.7 -> 21.9 deg)
    assert info["stretch_p99"][1] <= info["stretch_p99"][0], info
    assert np.allclose(Xn[held], X[held])
    assert list(gp.border_chain(M, "sheet:tl..tr")) == [ix(i, ny - 1) for i in range(nx)]  # walked, in order


def _wf_simon_home():
    h = os.environ.get("HIFIPUSHIE_HOME")
    return h and (Path(h) / "wf_simon" / "spec.json").exists()


_FIT = {}


def _shirt_v1():
    """wf_simon's Simon shirt, closed, on the form: the shirt spike's v1 (= e3), fitted once per test session."""
    if not _FIT:
        from hifipushie import cloth, pattern_form, resources, store
        spec = store.load("wf_simon")
        g = spec["cloth"]["shirt"]
        g.update({"closures": [{"name": "front", "spacing": {"first": 0.034, "from": "cfNeck"}}]})  # base_fit v1
        g = cloth.expanded(g)
        if "worn_open" not in spec["cloth"]["shirt"]:
            g.pop("worn_open", None)
        with resources.heavy("test_garment_pull shirt", gb=6.0):
            res = pattern_form.on_form("wf_simon", "shirt", spec, g=g)
        _FIT.update(res=res)
    return _FIT["res"]


KINK_MAX = 8.0  # deg: edge_turns kink_deg, half a 16 deg crease


def _plant_crease(M, X, a0, deg):
    """The planted fault for the edge's kink read: the collar beyond `a0` deg round the neck from CB (its sign: the
    side) turned `deg` in the side (y, z) plane about the x line through its outer edge there: a crease of `deg`."""
    pid = np.asarray(M["piece"])
    k, st = M["names"].index("collar"), M["names"].index("stand")
    cc = X[pid == st][:, :2].mean(0)
    ang = np.degrees(np.arctan2(X[:, 0] - cc[0], X[:, 1] - cc[1]))
    side = (pid == k) & (np.sign(ang) == np.sign(a0))
    on, ring = side & (np.abs(ang) > abs(a0)), side & (np.abs(np.abs(ang) - abs(a0)) < 3)
    p = X[ring][np.argmin(X[ring, 2])]
    th = np.radians(deg)
    R = np.array([[1, 0, 0], [0, np.cos(th), -np.sin(th)], [0, np.sin(th), np.cos(th)]])
    Y = X.copy()
    Y[on] = (X[on] - p) @ R.T + p
    return Y


def _fall_edge_r(M, X, angles=(0, 90, -90)):
    """The collar fall's outer edge (its lowest vertex) distance from the band's centre axis (mm) at angles round the
    neck from CB (shirt spike csec.py)."""
    pid, nm = np.asarray(M["piece"]), list(M["names"])
    S, C = X[pid == nm.index("stand")], X[pid == nm.index("collar")]
    c = S[:, :2].mean(0)
    a = np.degrees(np.arctan2(C[:, 0] - c[0], C[:, 1] - c[1]))
    out = []
    for g in angles:
        m = np.abs(((a - g + 180) % 360) - 180) < 6
        out.append(float(np.linalg.norm(C[m][np.argmin(C[m, 2]), :2] - c)) * 1000)
    return out


@pytest.mark.skipif(not _wf_simon_home(), reason="needs HIFIPUSHIE_HOME with the wf_simon workspace model")
def test_shirt_collar_points_pulled_open_give_the_spike_reads():
    res = _shirt_v1()
    X, M, body = np.asarray(res["A"], float), res["mesh"], res["body"]
    P = M["points"]
    hps = np.asarray(body.at["hps.L"], float).reshape(-1)[-3:]
    held = gp.hold_mask(M, X, ["collar", "stand", "front.L", "front.R"], "closure:front")
    bvf = (np.asarray(body.V, float), np.asarray(body.T, int))
    sides = ("left", "right")
    tips0 = {s: gp.tip_read(M, X, f"collar:{s}TopEdge") for s in sides}
    turns = [{"at": [f"stand:{s}BottomCf", f"stand:{s}BottomEdge", f"stand:{s}TopCf"], "patch": 0,  # (y3's swing:
              "about": [f"stand:{s}BottomHinge", f"stand:{s}TopHinge"], "deg": 30, "toward": "side",  # 3 vertices;
              "side_from": f"stand:{s}BottomHinge"} for s in sides]  # as an area: test 3; this way: 126 apart)
    handles = [{"at": f"collar:{s}TopEdge", "dir": {"side": 1, "out": 0.3, "up": 0.3},
                "side_from": f"collar:{s}TopHinge"} for s in sides]  # (a point grabs a 25 mm patch that turns)
    ops = [{"turn": {"turns": turns}}, {"pull": {"handles": handles}}, {"smooth": {"pieces": ["collar", "stand"]}}]
    Xn, infos = gp.style(M, X, held, ops, body=bvf)
    ti, info, sm = infos[0]["turn"], infos[1]["pull"], infos[2]["smooth"]
    l, r = Xn[P["collar:leftTopEdge"]], Xn[P["collar:rightTopEdge"]]
    apart = abs(l[0] - r[0]) * 1000
    below = [(hps[2] - p[2]) * 1000 for p in (l, r)]
    crum = float(np.percentile(gp.crumple(M, Xn, "collar"), 95))
    tips = {s: gp.tip_read(M, Xn, f"collar:{s}TopEdge") for s in sides}
    flips = {s: gp.folded(M, Xn, f"collar:{s}TopEdge") for s in sides}
    print(info, sm, apart, below, crum, tips0, tips, flips)
    assert [t["sense"] for t in ti["turns"].values()] == [-1, 1]  # each band end opens away from CF (its own side)
    assert info["stopped"] == "stretch"
    assert 140 <= apart <= 154, apart  # y3 147, this 142 (concept ~147)
    assert all(58 <= b <= 65 for b in below), below  # y3 63 / 59, this 64 / 60 (concept 50-61)
    assert crum <= 0.30, crum  # y3 0.28, this 0.28 after the smooth (0.39 before); pinned variants 0.34-0.72
    assert sm["rounds"] > 0 and sm["rough_p95_mm"][1] < sm["rough_p95_mm"][0]
    for s in sides:  # the tips as clean as the closed collar's (a point dragged by one vertex: 15-18 % / pinched)
        assert tips[s]["crumple_p95_mm"] <= tips0[s]["crumple_p95_mm"] + 0.05, (s, tips[s], tips0[s])
        assert tips[s]["thread_max_pct"] <= tips0[s]["thread_max_pct"] + 1.0, (s, tips[s], tips0[s])  # (C166: threads)
        assert tips[s]["shear_max_deg"] <= pf.SHEAR_LOCK_DEG, (s, tips[s])
        assert flips[s] <= 1, flips  # the closed collar 0; a rigid patch 18 / 28
    assert np.allclose(Xn[held], X[held])


@pytest.mark.skipif(not _wf_simon_home(), reason="needs HIFIPUSHIE_HOME with the wf_simon workspace model")
def test_shirt_collar_hugs_the_neck_at_the_back_and_sides():
    """C144 / C145 + every grip an area (the shirt spike's sp10 = f2, which Joe said reads best, + the border smooth):
    relax, HOLD band + collar within 70 deg of CB where the relaxed fit has them, FEATHERED to 130 deg, turn each band
    end 40 deg as a 15 mm area, pull the points side / out (mirrored), smooth the collar's outer edge toward one curve
    (the fall released from the hug), smooth. The fall hugs the neck at CB and the sides as the closed collar
    does (73 mm vs 67-68; f2 73); the band's top corner keeps its closed stretch (3 corner vertices turned alone:
    14-22 %); clean tips; no crease in the edge's side profile (kink_deg <= KINK_MAX; a planted 20 deg crease fails)."""
    res = _shirt_v1()
    X, M, body = np.asarray(res["A"], float), res["mesh"], res["body"]
    P = M["points"]
    hps = np.asarray(body.at["hps.L"], float).reshape(-1)[-3:]
    held = gp.hold_mask(M, X, ["collar", "stand", "front.L", "front.R"], "closure:front")
    sides = ("left", "right")
    r0 = _fall_edge_r(M, X)
    tips0 = {s: gp.tip_read(M, X, f"collar:{s}TopEdge") for s in sides}
    corner0 = [gp.tip_read(M, X, f"stand:{s}TopCf", near=0.008)["thread_max_pct"] for s in sides]
    turns = [{"at": f"stand:{s}BottomEdge..{s}TopCf", "about": [f"stand:{s}BottomHinge", f"stand:{s}TopHinge"],
              "deg": 40, "toward": "side", "side_from": f"stand:{s}BottomHinge"} for s in sides]
    handles = [{"at": f"collar:{s}TopEdge", "dir": {"side": 1, "out": 0.3}, "side_from": f"collar:{s}TopHinge"}
               for s in sides]
    ops = [{"relax": {}},
           {"hold": {"pieces": ["stand", "collar"], "within_deg": 70, "feather_to": 130, "of": "back",
                     "center": "stand"}},
           {"turn": {"turns": turns}}, {"pull": {"handles": handles}},
           {"smooth": {"border": "collar:leftTopEdge..topMid..rightTopEdge", "spline": 10, "release": ["collar"]}},
           {"smooth": {"pieces": ["collar", "stand"]}}]
    Xn, infos = gp.style(M, X, held, ops, body=(np.asarray(body.V, float), np.asarray(body.T, int)))
    r = _fall_edge_r(M, Xn)
    corner = [gp.tip_read(M, Xn, f"stand:{s}TopCf", near=0.008)["thread_max_pct"] for s in sides]
    l, rr = Xn[P["collar:leftTopEdge"]], Xn[P["collar:rightTopEdge"]]
    apart, below = abs(l[0] - rr[0]) * 1000, [(hps[2] - p[2]) * 1000 for p in (l, rr)]
    tips = {s: gp.tip_read(M, Xn, f"collar:{s}TopEdge") for s in sides}
    kinks = [gp.edge_turns(M, Xn, "collar", "collar:topMid", f"collar:{s}TopEdge", center="stand") for s in sides]
    print(infos, r0, r, corner0, corner, apart, below, tips, kinks)
    assert infos[3]["pull"]["stopped"] == "stretch"
    assert all(b - a <= 7 for a, b in zip(r0, r)), (r0, r)  # hugs (this +5-6 mm; unheld: the fall +8 / +14 mm off)
    assert all(c <= c0 + 2.0 for c, c0 in zip(corner, corner0)), (corner0, corner)  # (this 1.5 / 2.5, closed 2.7)
    # points apart: the CONCEPT's ~147 (as test 2: 140-154), not one old result (C165: the 130-150 band was sp10 / f2's
    # 137-138 on the iso fit). This 153.5 on the muslin fit, styled woven (C169); the unpulled collar (66.8, turned
    # only) fails it
    assert 140 <= apart <= 154 and all(66 <= b <= 80 for b in below), (apart, below)
    assert abs(below[0] - below[1]) <= 3, below  # mirrored pulls (unmirrored: 74 / 72)
    assert infos[4]["smooth"]["rounds"] > 0
    # ONE SWOOP, NO CREASE (C168): the kink is the turn the edge's own bend doesn't explain (edge_turns kink_deg: turn
    # over 15 mm less half the turn over 30 mm; an arc 0, a crease of c deg c / 2). Smooth edges read 3-6.4 (closed
    # 3.6 / 4.0, this 6.4 / 6.3 where the leaf bends down to the point, max turn 19 / 23 there); a planted crease of
    # 15 / 20 / 29 deg reads 11-15 / 15-20 / 21-27. The limit catches a crease of 16 deg or more (the old max-turn <= 22
    # sat between one fit's result, 20, and q40's hard border, 29: the muslin fit's leaf turns 23 deg smoothly)
    assert all(k["kink_deg"] <= KINK_MAX for k in kinks), kinks
    for s, a0 in zip(sides, (-90, 90)):  # the planted fault: a 20 deg crease in the same edge fails the same read
        kp = gp.edge_turns(M, _plant_crease(M, Xn, a0, 20.0), "collar", "collar:topMid", f"collar:{s}TopEdge",
                           center="stand")
        assert kp["kink_deg"] > KINK_MAX, (s, kp)
    assert float(np.percentile(gp.crumple(M, Xn, "collar"), 95)) <= 0.30
    for s in sides:
        assert tips[s]["crumple_p95_mm"] <= tips0[s]["crumple_p95_mm"] + 0.06, (s, tips[s], tips0[s])
        assert tips[s]["thread_max_pct"] <= tips0[s]["thread_max_pct"] + 1.0, (s, tips[s], tips0[s])  # (C166: threads)
        assert tips[s]["shear_max_deg"] <= pf.SHEAR_LOCK_DEG, (s, tips[s])
        assert tips[s]["twist_deg"] <= tips0[s]["twist_deg"] + 15, (s, tips[s], tips0[s])  # this 19 / 31 vs 18 / 35
        assert gp.folded(M, Xn, f"collar:{s}TopEdge") <= 1


def test_a_grip_overlapping_a_hold_is_refused():
    M, X, held = _strip()
    with pytest.raises(ValueError, match="held vertices"):
        gp.pull(M, X, held, [{"at": "strip:tipA..tipB", "dir": [1, 0, 0], "patch": 0.5}])


def _sheet(n=31, size=0.2):
    uv = np.array([(x, y) for x in np.linspace(0, size, n) for y in np.linspace(0, size, n)])
    ix = lambda i, j: i * n + j
    F = [f for i in range(n - 1) for j in range(n - 1)
         for f in ((ix(i, j), ix(i + 1, j), ix(i + 1, j + 1)), (ix(i, j), ix(i + 1, j + 1), ix(i, j + 1)))]
    return {"F": np.array(F), "uv": uv, "piece": np.zeros(len(uv), int), "names": ["sheet"], "sew": [], "points": {}}


def test_push_lifts_only_the_named_pieces_off_the_body():
    """C146 push: a sheet lying 3 mm INSIDE a flat body (z = 0 plane, normal +z) is lifted to the gap; with the piece
    not named nothing moves (a push on every piece dented the shirt's band)."""
    M = _sheet()
    X = np.c_[M["uv"], np.full(len(M["uv"]), -0.003)]
    g = np.linspace(-0.1, 0.3, 21)
    BV = np.array([(x, y, 0.0) for x in g for y in g])
    ix = lambda i, j: i * 21 + j
    BF = np.array([f for i in range(20) for j in range(20)
                   for f in ((ix(i, j), ix(i + 1, j), ix(i + 1, j + 1)), (ix(i, j), ix(i + 1, j + 1), ix(i, j + 1)))])
    Xn, info = gp.push(M, X, np.zeros(len(X), bool), ["sheet"], (BV, BF), gap=0.002)
    assert info["inside"][0] == len(X) and info["inside"][1] == 0, info
    assert np.allclose(Xn[:, 2], 0.002, atol=2e-4)
    M2 = dict(M, names=["sheet", "other"])
    Xo, info2 = gp.push(M2, X, np.zeros(len(X), bool), ["other"], (BV, BF))
    assert np.allclose(Xo, X) and info2["inside"] == [0, 0]


def test_smooth_near_points_brushes_only_round_them():
    """C146 local smooth: ripples everywhere; smoothing `near` one point (radius 40 mm) flattens there and leaves the
    cloth further away as it was (the shirt's tips: a whole-collar smooth missed them)."""
    M = _sheet(41)
    uv = M["uv"]
    rng = np.random.default_rng(2)
    X = np.c_[uv, 0.0005 * rng.standard_normal(len(uv))]
    edge = (uv.min(1) < 1e-9) | (uv.max(1) > 0.2 - 1e-9)
    X[edge, 2] = 0.0
    centre = int(np.argmin(np.linalg.norm(uv - [0.1, 0.1], axis=1)))
    M["points"] = {"sheet:mid": centre}
    Xn, info = gp.smooth(M, X, edge, ["sheet"], near=["sheet:mid"], radius=0.04)
    d = np.linalg.norm(uv - uv[centre], axis=1)
    assert info["rounds"] > 0 and info["rough_p95_mm"][1] < 0.6 * info["rough_p95_mm"][0], info
    assert np.allclose(Xn[d > 0.041], X[d > 0.041])


def test_open_collar_reads_tell_an_s_edge_from_one_arc():
    """C146 gate: the closed collar fails the open rows; a collar edge with an S (x5) fails the one-arc row; c1 passes
    (fixtures: the shirt spike's saved fits, skipped where the data disk isn't there)."""
    import pickle
    D = Path("/mnt/data/hifipushie/shirt_spike")
    if not (D / "c1.pkl").exists():
        pytest.skip("needs the shirt spike's fits on the data disk")
    st = {}
    for t in ("e5", "x5", "c1"):
        d = pickle.load(open(D / f"{t}.pkl", "rb"))
        st[t] = {r["id"]: r["status"] for r in gp.open_collar_rows(d["mesh"], np.asarray(d["A"], float))}
    assert st["e5"]["corners apart / neck"] == "FAIL" and st["e5"]["tips apart / neck"] == "FAIL"
    assert st["x5"]["edge max turn per 40 mm (deg)"] == "FAIL"
    assert all(v == "PASS" for v in st["c1"].values()), st["c1"]


@pytest.mark.skipif(not _wf_simon_home(), reason="needs HIFIPUSHIE_HOME with the wf_simon workspace model")
def test_a_shirt_without_a_tie_is_styled_open_by_default():
    """C146 KAT: wf_simon's Simon shirt from the REPO DEFAULTS alone (no overrides): the closed form fit, then the
    no-tie wear's style ops (garment_kb kinds.shirt.wear.no_tie.style: the shirt spike's c1 as data) give an open
    collar whose every OPEN_COLLAR_TARGETS row passes (Joe's photo / trace: corners, tips, V, one-arc edge, clean tips)."""
    from hifipushie import cloth, pattern_form, resources, store
    spec = store.load("wf_simon")
    g = cloth.expanded(spec["cloth"]["shirt"])
    assert not g.get("worn_open")
    with resources.heavy("test_garment_pull default style", gb=6.0):
        res = pattern_form.on_form("wf_simon", "shirt", spec, g=g)
    M, body = res["mesh"], res["body"]
    X, infos = gp.worn_style(M, np.asarray(res["A"], float), (np.asarray(body.V, float), np.asarray(body.T, int)), g)
    assert infos is not None and len(infos) == 9
    rows = gp.open_collar_rows(M, X)
    print(rows)
    assert all(r["status"] == "PASS" for r in rows), [r for r in rows if r["status"] != "PASS"]
    # unstretched, read as THREADS with shear apart (C169: an edge read counts the bias shear the woven styling allows,
    # 7.5 % here at threads p99 well under); planted fault: the collar grown 10 % fails the same read
    pcs = ["collar", "stand", "front.L", "front.R"]
    t99, sh99 = gp.thread_p99(M, X, pcs)
    print("threads p99", t99, "shear p99 by piece", sh99, "edge", gp.stretch_p99(M, X, pcs))
    assert t99 <= 0.07 and all(sh99 <= pf.SHEAR_LOCK_DEG), (t99, sh99)
    on = np.asarray(M["piece"]) == M["names"].index("collar")
    Xb = X.copy()
    Xb[on] = X[on].mean(0) + 1.1 * (X[on] - X[on].mean(0))
    assert gp.thread_p99(M, Xb, pcs)[0] > 0.07


def _two_fronts(n=21, w=0.1, h=0.2):
    """Two flat 'fronts' in the x-z plane meeting at x = 0 (separate pieces), fastened by a closure 'front' at z 0.05
    and 0.12 (pairs of coincident vertices on the meeting edges)."""
    F, uv, pid, X = [], [], [], []
    for k, x0 in enumerate((-w, 0.0)):
        o = len(uv)
        for i in range(n):
            for j in range(n):
                u, v = x0 + w * i / (n - 1), h * j / (n - 1)
                uv.append((u, v))
                X.append((u, 0.0, v))
                pid.append(k)
        ix = lambda i, j: o + i * n + j
        F += [f for i in range(n - 1) for j in range(n - 1)
              for f in ((ix(i, j), ix(i + 1, j), ix(i + 1, j + 1)), (ix(i, j), ix(i + 1, j + 1), ix(i, j + 1)))]
    uv, X = np.array(uv), np.array(X)
    at = lambda k, x, z: int(np.argmin(np.linalg.norm(X - [x, 0, z], axis=1) + 1e3 * (np.array(pid) != k)))
    pairs = [(at(0, 0.0, z), at(1, 0.0, z)) for z in (0.05, 0.12)]
    M = {"F": np.array(F), "uv": uv, "piece": np.array(pid), "names": ["front.L", "front.R"], "sew": [],
         "points": {"front.L:top": at(0, 0.0, h), "front.R:top": at(1, 0.0, h)},
         "closures": [{"name": "front", "state": "closed", "v": [list(p) for p in pairs]}]}
    return M, X, pairs


def test_worn_style_holds_the_fastened_buttons():
    """2026-10-22 (garrett collar round 1): styling holds every FASTENED pair of the front closure with the cloth round
    it, not only the cloth below the top button: Garrett's styled shirt pulled its first fastened button 8.7 / 19.4 mm
    open (probe s1 / s2), so the first done button read 203 mm below HPS (concept 83). Control: the old mask (below the
    top button less 5 mm only) lets the same pull open the top pair."""
    M, X, pairs = _two_fronts()
    hs = [{"at": "front.L:top", "dir": [-1, 0, 0], "turn": False}, {"at": "front.R:top", "dir": [1, 0, 0], "turn": False}]
    old = X[:, 2] < 0.12 - 0.005
    Xo, _ = gp.pull(M, X, old, hs, step=0.003, max_move=0.03, tol=1.0)
    a, b = pairs[1]
    assert np.linalg.norm(Xo[a] - Xo[b]) > 0.003, "control: the old mask should let the top pair open"
    held = gp.hold_mask(M, X, ["front.L", "front.R"], "closure:front")
    assert held[a] and held[b]
    Xn, info = gp.pull(M, X, held, hs, step=0.003, max_move=0.03, tol=1.0)
    for a, b in pairs:
        assert np.linalg.norm(Xn[a] - Xn[b]) < 1e-6
    # the tops still part, as far as the cloth lets them (C169: tol 1.0 switches the thread stop off, not the shear
    # lock: the free corner dragged in its own plane jams at 15 mm, shear p99 36.5 deg; the isometric solve sheared it
    # 30 mm to max_move)
    assert info["stopped"] in ("shear", "max_move"), info
    assert np.linalg.norm(Xn[M["points"]["front.L:top"]] - X[M["points"]["front.L:top"]]) > 0.01


def test_a_garment_edits_its_wear_style_by_op_kind():
    """garrett collar round 1: a garment's own "style" dict sets params on every op of a kind in the wear's list (the
    rest as the KB has it); a list replaces the list; false none; an unknown kind is refused."""
    g = {"design": {"kind": "shirt"}}
    base = gp.style_ops(g)
    assert any("turn" in o for o in base) and all("tol" not in o["turn"] for o in base if "turn" in o)
    ed = gp.style_ops(dict(g, style={"turn": {"tol": 0.005, "steps": 16}}))
    assert [list(o) for o in ed] == [list(o) for o in base]
    t = next(o["turn"] for o in ed if "turn" in o)
    assert t["tol"] == 0.005 and t["steps"] == 16 and t["turns"] == next(o["turn"] for o in base if "turn" in o)["turns"]
    assert gp.style_ops(dict(g, style=[{"relax": {}}])) == [{"relax": {}}]
    assert gp.style_ops(dict(g, style=False)) == []
    with pytest.raises(ValueError):
        gp.style_ops(dict(g, style={"twirl": {}}))


def test_neck_lump_reads_tell_garretts_lump_from_a_smooth_shoulder():
    """garrett collar r2 (Joe on gc1: "the only real issue is the lumpy part here"): the shoulder seam bridging the
    neck-shoulder corner as a fin with a pillow (gc1, closed and styled) fails both NECK_LUMP_TARGETS rows; wf_simon's
    smooth dome (closed and styled) passes (fixtures: round 1's saved fits, skipped where the data disk isn't there)."""
    import pickle
    D = Path("/mnt/data/hifipushie/garrett_collar")
    if not (D / "gc1_closed.pkl").exists():
        pytest.skip("needs garrett collar round 1's fits on the data disk")
    for t, want in (("gc1_closed", "FAIL"), ("gc1_styled", "FAIL"), ("w2_closed", "PASS"), ("w2_styled", "PASS")):
        d = pickle.load(open(D / f"{t}.pkl", "rb"))
        rows = gp.neck_lump_rows(d["mesh"], np.asarray(d["A"], float), (d["bodyV"], d["bodyF"]))
        assert len(rows) == 2 and all(r["status"] == want for r in rows), (t, rows)


def _box(lo, hi, n=25):
    """A closed box mesh (each face an n x n grid), wound outward."""
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    V, F = [], []
    for ax in range(3):
        for s in (0, 1):
            a, b = [k for k in range(3) if k != ax]
            g = np.linspace(0, 1, n)
            base = len(V)
            for i in g:
                for j in g:
                    p = np.zeros(3)
                    p[ax] = (lo if s == 0 else hi)[ax]
                    p[a], p[b] = lo[a] + i * (hi[a] - lo[a]), lo[b] + j * (hi[b] - lo[b])
                    V.append(p)
            ix = lambda i, j: base + i * n + j
            F += [f for i in range(n - 1) for j in range(n - 1)
                  for f in ((ix(i, j), ix(i + 1, j), ix(i + 1, j + 1)), (ix(i, j), ix(i + 1, j + 1), ix(i, j + 1)))]
    V, F = np.array(V), np.array(F)
    c, nrm = V[F].mean(1), np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    F[((c - (lo + hi) / 2) * nrm).sum(1) < 0] = F[((c - (lo + hi) / 2) * nrm).sum(1) < 0][:, ::-1]  # (each face out)
    return V, F


@pytest.mark.parametrize("as_layer", ["body", "patch"])
def test_layer_floor_keeps_a_pulled_cloth_on_its_side(as_layer):
    """C170 layer floor: the slack strip (test 1) hanging as an arc under a block (its middle 5 mm below the block's
    underside), its free end pulled along the chord. With no floor the flat-pattern solve straightens the strip
    THROUGH the block (C157: lapels through their fronts, flaps sunk, fronts into the shirt). With layer_floor the
    strip stays on its side of the block (within one cloth thickness of its start gap: the level is min(gap, start)),
    whether the block is the body or a held piece the strip is stitched to (a pocket flap over its front)."""
    M, X, pin = _strip()
    zmid = float(X[:, 2].min())
    BV, BF = _box([0.08, -0.05, zmid + 0.005], [0.12, 0.07, 0.05])
    body = (BV, BF)
    held = pin.copy()
    if as_layer == "patch":  # the block as a held piece of the same mesh, the strip stitched to it at its pinned end
        n0 = len(X)
        Mb = {"F": np.r_[M["F"], BF + n0], "uv": np.r_[M["uv"], BV[:, :2] * 0 + np.c_[np.arange(len(BV)) * 1e-3, np.zeros(len(BV))]],
              "piece": np.r_[np.zeros(n0, int), np.ones(len(BV), int)], "names": ["strip", "block"], "sew": [],
              "points": M["points"]}
        k = int(np.argmin(np.linalg.norm(BV - X[np.where(pin)[0][0]], axis=1)))
        Mb["stitch"] = [[int(np.where(pin)[0][0]), n0 + k]]
        M, X, held, body = Mb, np.r_[X, BV], np.r_[held, np.ones(len(BV), bool)], (np.array([[9.0, 9, 9], [9.1, 9, 9], [9, 9.1, 9]]) + 0, np.array([[0, 1, 2]]))
    h = [{"at": "strip:tipA..tipB", "dir": [1, 0, 0]}]

    def under_block(Y):  # the deepest the strip's vertices over the block's footprint go above its underside (m)
        s = np.arange(len(_strip()[1]))
        over = (Y[s, 0] > 0.085) & (Y[s, 0] < 0.115)
        return float((Y[s][over, 2] - (zmid + 0.005)).max())
    X0, _ = gp.style(M, X, held, [{"pull": {"handles": h, "max_move": 0.08}}])
    floor = gp.layer_floor(M, X, body=body if as_layer == "body" else None,
                           flaps=as_layer == "patch")
    assert [f["name"] for f in floor] == (["body"] if as_layer == "body" else ["patch:strip"]), [f["name"] for f in floor]
    X1, inf = gp.style(M, X, held, [{"pull": {"handles": h, "max_move": 0.08}}], floor=floor)
    assert under_block(X0) > 0.01, under_block(X0)  # (no floor: through the block by more than 10 mm)
    assert under_block(X1) < 0.0015 + 1e-4, under_block(X1)  # (the floor: never above its underside past one cloth)
