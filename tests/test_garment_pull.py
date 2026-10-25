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


def test_smooth_border_reads_its_kink_where_it_can_move():
    """(fit round 33) the same wobbling border with a sharp fixed corner at its start (the jacket's front edge meets the
    held lapel at the break: 15 deg at 3 mm, the max of the whole border): the stop reads the kink only where the
    smooth can move the border (beyond `ends`), so it still runs and takes the wobble out; before, the end's corner was
    the max every round and it stopped at 0 rounds. A coarse border (fewer vertices than knots allow) still fits."""
    nx, ny = 81, 21
    uv = np.array([(x, y) for x in np.linspace(0, 0.2, nx) for y in np.linspace(0, 0.05, ny)])
    ix = lambda i, j: i * ny + j
    F = [f for i in range(nx - 1) for j in range(ny - 1)
         for f in ((ix(i, j), ix(i + 1, j), ix(i + 1, j + 1)), (ix(i, j), ix(i + 1, j + 1), ix(i, j + 1)))]
    X = np.c_[uv, np.zeros(len(uv))]
    top = uv[:, 1] > 0.05 - 1e-9
    X[top, 2] = 0.001 * np.sign(np.sin(uv[top, 0] / 0.2 * 2 * np.pi * 6) + 1e-9)
    corner = uv[:, 0] < 0.0101  # (the first 10 mm turned up 45 deg: a corner the smooth may not move)
    X[corner, 2] += (0.0101 - uv[corner, 0])
    M = {"F": np.array(F), "uv": uv, "piece": np.zeros(len(uv), int), "names": ["sheet"], "sew": [],
         "points": {"sheet:tl": ix(0, ny - 1), "sheet:tr": ix(nx - 1, ny - 1)}}
    held = (uv[:, 1] < 1e-9) | corner
    ch = gp.border_chain(M, "sheet:tl..tr")
    assert gp._kink3d(X[ch], 0.03) > 35  # (the corner is the border's max)
    Xn, info = gp.smooth_border(M, X, held, "sheet:tl..tr", ends=0.02)
    k0, k1 = info["kink_moving_deg"]
    assert info["rounds"] > 0 and k1 < 0.8 * k0, info
    assert np.allclose(Xn[held], X[held])
    _, info2 = gp.smooth_border(M, X, held, "sheet:tl..tr", ends=0.02, spline=60)  # (60 knots on 81 vertices)
    assert info2["rounds"] >= 0


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


def test_layer_floor_keeps_a_pulled_cloth_on_the_body():
    """C170 layer floor, the body (or the garment under): the slack strip (test 1) hanging as an arc under a block (its
    middle 5 mm below the block's underside), its free end pulled along the chord. With no floor the flat-pattern
    solve straightens the strip THROUGH the block (C157: lapels through their fronts, flaps sunk, fronts into the
    shirt). With layer_floor the strip stays on its side, within one cloth (the level is min(gap, start distance)),
    cloth sliding in under the block included."""
    M, X, pin = _strip()
    zmid = float(X[:, 2].min())
    BV, BF = _box([0.08, -0.05, zmid + 0.005], [0.12, 0.07, 0.05])
    h = [{"at": "strip:tipA..tipB", "dir": [1, 0, 0]}]

    def into(Y):  # the deepest the strip goes above the block's underside, over its footprint (m)
        over = (Y[:, 0] > 0.085) & (Y[:, 0] < 0.115)
        return float((Y[over, 2] - (zmid + 0.005)).max())
    X0, _ = gp.style(M, X, pin, [{"pull": {"handles": h, "max_move": 0.08}}])
    floor = gp.layer_floor(M, X, body=(BV, BF), flaps=False)
    assert [f["name"] for f in floor] == ["body"]
    X1, _ = gp.style(M, X, pin, [{"pull": {"handles": h, "max_move": 0.08}}], floor=floor)
    assert into(X0) > 0.01, into(X0)  # (no floor: through the block by more than 10 mm)
    assert into(X1) < 0.0015 + 1e-4, into(X1)


def test_layer_floor_keeps_a_patch_on_its_piece():
    """C170 layer floor, a stitched patch over its piece (a pocket flap on its front): a strip hanging flat 5 mm under
    a held plate (a piece of the same mesh), stitched to it at one end, its free end (past the plate) lifted. With no
    floor the strip swings up through the plate; with layer_floor (patch:strip) it stays under it within one cloth,
    bending at the plate's edge."""
    nx, ny = 41, 5
    uv = np.array([(x, y) for x in np.linspace(0, 0.2, nx) for y in np.linspace(0, 0.02, ny)])
    ix = lambda i, j: i * ny + j
    F = np.array([f for i in range(nx - 1) for j in range(ny - 1)
                  for f in ((ix(i, j), ix(i + 1, j), ix(i + 1, j + 1)), (ix(i, j), ix(i + 1, j + 1), ix(i, j + 1)))])
    X = np.c_[uv[:, 0], uv[:, 1], np.full(len(uv), -0.005)]
    BV, BF = _box([-0.01, -0.03, 0.0], [0.15, 0.05, 0.02])
    n0 = len(X)
    M = {"F": np.r_[F, BF + n0], "uv": np.r_[uv, np.c_[np.arange(len(BV)) * 1e-3, np.zeros(len(BV))]],
         "piece": np.r_[np.zeros(n0, int), np.ones(len(BV), int)], "names": ["strip", "plate"], "sew": [],
         "points": {"strip:tipA": ix(nx - 1, 0), "strip:tipB": ix(nx - 1, ny - 1)}}
    end = uv[:, 0] < 1e-9
    k = [int(np.argmin(np.linalg.norm(BV - X[v], axis=1))) for v in np.where(end)[0]]
    M["stitch"] = [[int(v), n0 + kk] for v, kk in zip(np.where(end)[0], k)]
    Ms = dict(M, sew=np.r_[np.zeros((0, 2), int), np.asarray(M["stitch"])])  # (style welds stitch pairs as sew)
    Xa = np.r_[X, BV]
    held = np.r_[end, np.ones(len(BV), bool)]
    h = [{"at": "strip:tipA..tipB", "dir": "up"}]

    def into(Y):  # the highest the strip goes above the plate's underside, over its footprint (m)
        over = (Y[:n0, 0] > 0.01) & (Y[:n0, 0] < 0.14)
        return float(Y[:n0][over, 2].max())
    X0, _ = gp.style(Ms, Xa, held, [{"pull": {"handles": h, "max_move": 0.06}}])
    floor = gp.layer_floor(Ms, Xa, flaps=True)
    assert [f["name"] for f in floor] == ["patch:strip"], [f["name"] for f in floor]
    X1, _ = gp.style(Ms, Xa, held, [{"pull": {"handles": h, "max_move": 0.06}}], floor=floor)
    assert into(X0) > 0.01, into(X0)  # (no floor: through the plate)
    assert into(X1) < 0.0015 + 1e-4, into(X1)


def _grid(x0, x1, y0, y1, h):
    xs, ys = np.arange(x0, x1 + 1e-9, h), np.arange(y0, y1 + 1e-9, h)
    V = np.array([(x, y, 0.0) for x in xs for y in ys])
    ix = lambda i, j: i * len(ys) + j
    F = np.array([f for i in range(len(xs) - 1) for j in range(len(ys) - 1)
                  for f in ((ix(i, j), ix(i + 1, j), ix(i + 1, j + 1)), (ix(i, j), ix(i + 1, j + 1), ix(i, j + 1)))])
    return V, F


def test_layer_floor_reach_is_local_to_a_coarse_base():
    """C173 (garrett jacket fit round 31): a patch over the COARSE part of a piece meshed fine elsewhere (a pocket flap on
    a front meshed fine at its lapel rows) has a floor at every vertex. The plate: a fine part (2 mm) beside a coarse part
    (8 mm) under a strip stitched at one end, its vertices mid-cell (5.7 mm off the nearest plate vertex: past 1.5 x the
    2 mm median edge), pulled down through the plate. The floor's reach is the nearest plate vertex's own edge (capped):
    every strip vertex has a floor and nothing of the strip goes through the plate (measured: 45 of 45, lowest 0.0 mm); with the median-edge reach (the old rule, here
    FLOOR_REACH_CAP 1: at most the median) none had one and it went 6 mm through."""
    Vf, Ff = _grid(0.0, 0.058, -0.024, 0.032, 0.002)
    Vc, Fc = _grid(0.06, 0.204, -0.024, 0.032, 0.008)
    PV, PF = np.r_[Vf, Vc], np.r_[Ff, Fc + len(Vf)]
    su = np.array([(u, v) for u in np.arange(0.0, 0.12 + 1e-9, 0.008) for v in np.arange(0.0, 0.016 + 1e-9, 0.008)])
    ny = 3
    nx = len(su) // ny
    ix = lambda i, j: i * ny + j
    SF = np.array([f for i in range(nx - 1) for j in range(ny - 1)
                   for f in ((ix(i, j), ix(i + 1, j), ix(i + 1, j + 1)), (ix(i, j), ix(i + 1, j + 1), ix(i, j + 1)))])
    SX = np.c_[0.068 + su[:, 0], -0.004 + su[:, 1], np.full(len(su), 0.003)]
    BV, BF = _box([-0.05, -0.08, -0.12], [0.30, 0.10, -0.08])  # (a body below: orients the plate's normals up)
    n0 = len(SX)
    M = {"F": np.r_[SF, PF + n0], "uv": np.r_[su, PV[:, :2]], "piece": np.r_[np.zeros(n0, int), np.ones(len(PV), int)],
         "names": ["strip", "plate"], "sew": [], "points": {"strip:tipA": ix(nx - 1, 0), "strip:tipB": ix(nx - 1, ny - 1)}}
    end = su[:, 0] < 1e-9
    k = [int(np.argmin(np.linalg.norm(PV - SX[v], axis=1))) for v in np.where(end)[0]]
    M["stitch"] = [[int(v), n0 + kk] for v, kk in zip(np.where(end)[0], k)]
    Ms = dict(M, sew=np.asarray(M["stitch"]))
    Xa = np.r_[SX, PV]
    held = np.r_[end, np.ones(len(PV), bool)]
    ops = [{"pull": {"handles": [{"at": "strip:tipA..tipB", "dir": "down"}], "max_move": 0.03}}]

    def low(Y):  # the lowest the strip goes over the plate (m; the plate at 0)
        return float(Y[:n0][~end, 2].min())
    res = {}
    old = gp.FLOOR_REACH_CAP
    try:
        for cap in (old, 1.0):
            gp.FLOOR_REACH_CAP = cap
            fl = [f for f in gp.layer_floor(Ms, Xa, body=(BV, BF)) if f["name"] == "patch:strip"]
            assert fl, "no patch floor"
            X1, _ = gp.style(Ms, Xa, held, ops, floor=fl)
            res[cap] = (int(np.isfinite(fl[0]["level"]).sum()), low(X1))
    finally:
        gp.FLOOR_REACH_CAP = old
    assert res[old][0] == int((~end).sum()) and res[old][1] > -1e-4, res  # (on or above the plate, as the C170 KAT)
    assert res[1.0][0] == 0 and res[1.0][1] < -0.002, res  # (the control: no floor, through the plate)


def test_open_jacket_is_styled_by_its_wear_as_data():
    """C174 (garrett jacket fit round 31; Joe: "I'd smooth it out, pull it down"): a jacket worn open is styled by its
    kind's "open" wear (garment_kb kinds.jacket.wear.open.style): the fronts above the break held as fitted, the edge
    below gripped part-way down (border points "piece:a..b@t") and drawn side and down, then the artist's finish:
    smooth, the hem pulled down, relax. A jacket worn closed has no wear style; a border point is the chain's vertex
    at that share of its length, and a hold "above" holds that piece from the point's height up."""
    from hifipushie import garment_design as gd
    ops = gd.wear({"design": {"kind": "jacket"}, "worn_open": {"front.L:break": 0.064}}, "style")
    kinds = [next(iter(o)) for o in ops]
    assert kinds[:2] == ["hold", "hold"] and ops[1]["hold"]["above"] == ["front.L:break", "front.R:break"], ops[:2]
    # (C186, fit round 38) the side / back hems held where the fit hung them (the un-lap flared them out like a skirt)
    assert ops[0]["hold"]["at"] == ["side.L:sideF.b..sideB.b", "back.L:sideB.b..cbHem", "side.R:sideF.b..sideB.b",
                                    "back.R:sideB.b..cbHem"], ops[0]
    assert kinds[-5:-2] == ["smooth", "pull", "relax"] and ops[-4]["pull"]["handles"][0]["dir"] == "down", kinds
    # (C185, fit round 38) ... and last each edge from the break to the cut-away's top drawn straight (the front-view
    # chord), the slide having let go of its grip above cutawayTop (it had pinched the edge in under the break)
    assert [o["smooth"]["border"] for o in ops[-2:]] == ["front.L:break..cutawayTop", "front.R:break..cutawayTop"], ops[-2:]
    assert all(o["smooth"]["spline"] == 0 for o in ops[-2:]), ops[-2:]
    assert [q.get("let_go_above") for q in ops[kinds.index("slide")]["slide"]["slides"]] == ["front.L:cutawayTop", "front.R:cutawayTop"]
    # (C178, fit round 33) the lower front swung as one panel about break -> side seam at the hem, laid back on the body
    # (down + in), then each edge smoothed into one long curve; no point grips part-way down the edge (zigzag / flare)
    tu = ops[kinds.index("turn")]["turn"]["turns"]
    assert [t["about"] for t in tu] == [["front.L:break", "front.L:sideF.b"], ["front.R:break", "front.R:sideF.b"]], tu
    # (C182, fit round 36) ... until the edge below the break hangs plumb (break -> cutawayTop), not by a fixed angle
    assert [t.get("plumb") for t in tu] == [["front.L:break", "front.L:cutawayTop"], ["front.R:break", "front.R:cutawayTop"]], tu
    # (C184, fit round 37) ... after the lapped cloth has first slid back round the body (un-lap), the side and back
    # panels following, its lap set by the hang (the edge from the break to the cut-away's top on the vertical)
    su = ops[kinds.index("turn") - 1]["slide"]["slides"]
    assert [q["at"] for q in su] == ["front.L:break..cfHem", "front.R:break..cfHem"], su
    assert [q["by"] for q in su] == [{"plumb": t["plumb"], "ramp": True} for t in tu], su
    assert [q["with"] for q in su] == [["side.L", "back.L"], ["side.R", "back.R"]], su
    lay = ops[kinds.index("turn") + 1]["pull"]["handles"]
    assert [h["at"] for h in lay] == [t["at"] for t in tu] and all(h["dir"]["out"] < 0 < h["dir"]["down"] for h in lay), lay
    assert not any("@" in h["at"] for o in ops if "pull" in o for h in o["pull"]["handles"]), ops
    assert {o["smooth"]["border"] for o in ops if "smooth" in o and "border" in o["smooth"]} == {
        "front.L:break..cfHem", "front.R:break..cfHem", "front.L:break..cutawayTop", "front.R:break..cutawayTop"}
    assert gd.wear({"design": {"kind": "jacket"}}, "style") == []
    nx, ny = 11, 5
    uv = np.array([(x, y) for x in np.linspace(0, 0.1, nx) for y in np.linspace(0, 0.04, ny)])
    ix = lambda i, j: i * ny + j
    F = np.array([f for i in range(nx - 1) for j in range(ny - 1)
                  for f in ((ix(i, j), ix(i + 1, j), ix(i + 1, j + 1)), (ix(i, j), ix(i + 1, j + 1), ix(i, j + 1)))])
    X = np.c_[uv[:, 0], np.zeros(len(uv)), uv[:, 1]]
    M = {"F": F, "uv": uv, "piece": np.zeros(len(uv), int), "names": ["s"], "sew": [],
         "points": {"s:a": ix(0, 0), "s:b": ix(nx - 1, 0), "s:c": ix(0, 2)}}
    assert gp.vertex(M, "s:a..b@0.5") == ix(5, 0) and gp.vertex(M, "s:a..b@0") == ix(0, 0)
    h = gp.hold_region(M, X, above="s:c")
    assert h.sum() == nx * 3 and h[ix(3, 2)] and not h[ix(3, 1)], int(h.sum())


def test_plumb_lays_a_slid_seam_back_on_the_vertical():
    """C181 (garrett jacket fit round 35): a plumb jacket's side seam hangs on the vertical below its underarm. A sheet
    hanging in x-z (100 mm wide, 300 tall), its rows turned about its held left edge more and more toward the hem (0 at
    the top, 35 deg at the bottom: the right edge, the seam, slid forward round the body in -y, as the muslin fit slid
    the front panel's side seam). The plumb op lays the right border back on the vertical through its top: y within
    3 mm of the top's below the ramp, x out to the top's, and the threads stretch less, not more."""
    nx, ny = 11, 31
    uv = np.array([(x, y) for x in np.linspace(0, 0.1, nx) for y in np.linspace(0, 0.3, ny)])
    ix = lambda i, j: i * ny + j
    F = [f for i in range(nx - 1) for j in range(ny - 1)
         for f in ((ix(i, j), ix(i + 1, j), ix(i + 1, j + 1)), (ix(i, j), ix(i + 1, j + 1), ix(i, j + 1)))]
    th = np.radians(35.0) * (0.3 - uv[:, 1]) / 0.3
    X = np.c_[uv[:, 0] * np.cos(th), -uv[:, 0] * np.sin(th), uv[:, 1]]
    M = {"F": np.array(F), "uv": uv, "piece": np.zeros(len(uv), int), "names": ["sheet"], "sew": [],
         "points": {"sheet:tr": ix(nx - 1, ny - 1), "sheet:br": ix(nx - 1, 0)}}
    held = uv[:, 0] < 1e-9
    Xn, info = gp.plumb(M, X, held, ["sheet:tr..br"], ramp=0.03, tol=None)
    seam = gp.border_chain(M, "sheet:tr..br")
    low = seam[uv[seam, 1] < 0.3 - 0.03]
    assert np.abs(X[low, 1]).max() > 0.05  # (slid 57 mm forward at the hem)
    assert np.abs(Xn[low, 1]).max() < 0.003, np.abs(Xn[low, 1]).max()
    assert Xn[low, 0].min() > 0.1 - 0.003
    assert info["stretch_p99_end"] <= info["stretch_p99_start"], info
    assert np.allclose(Xn[held], X[held])
    # as a styling op: what it laid stays where it put it for the ops after it
    Xs, infos = gp.style(M, X, held, [{"plumb": {"borders": ["sheet:tr..br"], "ramp": 0.03, "tol": None}},
                                      {"relax": {"iters": 10}}])
    assert np.abs(Xs[low, 1]).max() < 0.003 and list(infos[0]) == ["plumb"]
    assert gp.ops_pieces(M, [{"plumb": {"borders": ["sheet:tr..br"]}}]) == ["sheet"]


def test_turn_stops_where_the_line_hangs_plumb():
    """C182 (garrett jacket fit round 36): an open jacket's lower front swings until its edge below the break hangs
    plumb in the front view, not by a fixed angle (r35's 48 deg, tuned on Garrett when the side seam sat further
    forward, threw the hem corners out 30 mm past the concept). A sheet (100 x 300 mm, on the +x side) whose left edge
    leans in toward the centre line by 30 mm at the hem (lapped, as the closed fit leaves the front), the top row held:
    its lower-left corner turned about the diagonal top-left -> bottom-right. With "plumb": [top-left, bottom-left] the
    turn stops where the bottom-left lies on the vertical through the top-left (within 2 mm), before the deg allows;
    without it the full deg throws the corner past the vertical."""
    nx, ny = 11, 31
    uv = np.array([(x, y) for x in np.linspace(0, 0.1, nx) for y in np.linspace(0, 0.3, ny)])
    ix = lambda i, j: i * ny + j
    F = [f for i in range(nx - 1) for j in range(ny - 1)
         for f in ((ix(i, j), ix(i + 1, j), ix(i + 1, j + 1)), (ix(i, j), ix(i + 1, j + 1), ix(i, j + 1)))]
    X = np.c_[uv[:, 0] + 0.05 - 0.03 * (0.3 - uv[:, 1]) / 0.3, np.zeros(len(uv)), uv[:, 1]]
    M = {"F": np.array(F), "uv": uv, "piece": np.zeros(len(uv), int), "names": ["s"], "sew": [],
         "points": {"s:tl": ix(0, ny - 1), "s:bl": ix(0, 0), "s:br": ix(nx - 1, 0)}}
    held = uv[:, 1] > 0.3 - 1e-9
    t = {"at": "s:bl", "patch": 0.03, "about": ["s:tl", "s:br"], "deg": 60, "toward": "side"}
    Xa, ia = gp.turn(M, X, held, [t], steps=12, tol=None)
    Xp, ip = gp.turn(M, X, held, [dict(t, plumb=["s:tl", "s:bl"])], steps=12, tol=None)
    tl, bl = ix(0, ny - 1), ix(0, 0)
    assert X[bl, 0] < X[tl, 0] - 0.025  # (leans in 30 mm)
    assert Xa[bl, 0] > Xa[tl, 0] + 0.01, (Xa[bl], Xa[tl])  # (the fixed angle throws it past the vertical)
    assert ip["stopped"] == "plumb" and ip["deg_turned"][0] < 60, ip
    assert abs(Xp[bl, 0] - Xp[tl, 0]) < 0.002, (Xp[bl, 0], Xp[tl, 0])
    assert next(iter(ip["plumb"].values()))["hung"], ip["plumb"]
    assert np.allclose(Xp[held], X[held])


def test_slide_unlaps_along_the_body_keeping_its_offset():
    """C184 (garrett jacket fit round 37): an unbuttoned front's lapped cloth slides back ROUND the body, it doesn't swing
    out like a door. A sheet lying 10 mm off a cylinder (the body, r 150 mm, axis z), its edge 20 mm round from the
    front (-y), 300 mm tall, lapped: the edge runs 25 mm of arc nearer the front at the bottom than at the top (held,
    as a front above its break). slide "by" plumb [top, bottom] with "ramp": the edge's bottom slides round until it
    lies on the vertical through its top (front view x within 4 mm), the cloth keeps its offset off the body (2 mm),
    and with the whole sheet following (follow beyond its width) the threads stretch < 1 %."""
    ns, zs = 96, np.linspace(-0.25, 0.55, 33)  # (a closed cylinder: rings + two capped ends)
    th = 2 * np.pi * np.arange(ns) / ns
    BV = [(0.15 * np.cos(t), 0.15 * np.sin(t), z) for z in zs for t in th] + [(0, 0, zs[0]), (0, 0, zs[-1])]
    rv = lambda r, k: r * ns + k % ns
    BF = [f for r in range(len(zs) - 1) for k in range(ns)
          for f in ((rv(r, k), rv(r, k + 1), rv(r + 1, k + 1)), (rv(r, k), rv(r + 1, k + 1), rv(r + 1, k)))]
    c0, c1 = len(zs) * ns, len(zs) * ns + 1
    BF += [(c0, rv(0, k + 1), rv(0, k)) for k in range(ns)] + [(c1, rv(len(zs) - 1, k), rv(len(zs) - 1, k + 1)) for k in range(ns)]
    body = (np.array(BV, float), np.array(BF, int))
    na, nz, R = 13, 16, 0.16
    phi0 = np.radians(8.0)
    arc = np.linspace(0.0, 0.12, na)
    zz = np.linspace(0.0, 0.3, nz)
    uv = np.array([(a, z) for a in arc for z in zz])
    ix = lambda i, j: i * nz + j
    F = np.array([f for i in range(na - 1) for j in range(nz - 1)
                  for f in ((ix(i, j), ix(i + 1, j), ix(i + 1, j + 1)), (ix(i, j), ix(i + 1, j + 1), ix(i, j + 1)))])
    # (lapped: the edge's lower rows sit nearer the front than its top: phi grows 0 -> 25 mm of arc up the edge)
    ph = lambda a, z: phi0 + (a + 0.025 * z / 0.3) / R
    X = np.array([(R * np.sin(ph(a, z)), -R * np.cos(ph(a, z)), z) for a, z in uv])
    M = {"F": F, "uv": uv, "piece": np.zeros(len(uv), int), "names": ["s"], "sew": [],
         "points": {"s:top": ix(0, nz - 1), "s:bot": ix(0, 0)}}
    held = np.zeros(len(X), bool)
    held[[ix(i, nz - 1) for i in range(na)]] = True  # (the top row held: above the break)
    sl = {"at": "s:top..bot", "patch": 0.012, "follow": 1.0, "by": {"plumb": ["s:top", "s:bot"], "ramp": True}}
    Y, info = gp.slide(M, X, held, [sl], body=body, steps=8, tol=None)
    top, bot = Y[ix(0, nz - 1)], Y[ix(0, 0)]
    assert abs(bot[0] - top[0]) < 0.004, (bot, top, info)
    r = np.hypot(Y[:, 0], Y[:, 1])
    assert np.abs(r - R).max() < 0.002, np.abs(r - R).max()
    t0, _ = gp.thread_p99(M, X)
    t1, sh1 = gp.thread_p99(M, Y)
    assert t1 < 0.01 and t1 < t0 + 0.01, (t0, t1, sh1)
    # ... and the op runs as a styling op; its "with" pieces that the garment hasn't are skipped
    Z, infos = gp.style(M, X, held, [{"slide": {"slides": [dict(sl, **{"with": ["side.L"]})], "steps": 8, "tol": None}}],
                        body=body)
    assert np.allclose(Z, Y, atol=1e-6) and "slide" in infos[0]


def test_open_edge_is_drawn_straight_after_the_slide_lets_go():
    """C185 (garrett jacket fit round 38; Joe's red arrows on r37: the fronts pinch in under the break): (1) smooth_border
    "spline" 0 draws a border toward its CHORD in the front view (x, z), its depth y left as it lies: a sheet's edge bowed
    20 mm in between two held ends comes out within 1.5 mm of the straight line, the threads within tol. (2) a slide's
    "let_go_above" lets go of its grip above that point after the slide, so a later op can move that cloth; without it the
    slide's grip stays held and the chord smooth can't move the edge."""
    nx, nz = 9, 25
    uv = np.array([(a, z) for a in np.linspace(0.0, 0.08, nx) for z in np.linspace(0.0, 0.24, nz)])
    ix = lambda i, j: i * nz + j
    F = np.array([f for i in range(nx - 1) for j in range(nz - 1)
                  for f in ((ix(i, j), ix(i + 1, j), ix(i + 1, j + 1)), (ix(i, j), ix(i + 1, j + 1), ix(i, j + 1)))])
    bow = lambda z: 0.02 * np.sin(np.pi * z / 0.24)  # (the edge bowed in toward x = 0... here toward -x)
    X = np.c_[uv[:, 0] + 0.05 - bow(uv[:, 1]) * np.clip(1 - uv[:, 0] / 0.04, 0, 1), 0.01 * uv[:, 0], uv[:, 1]]
    M = {"F": F, "uv": uv, "piece": np.zeros(len(uv), int), "names": ["s"], "sew": [],
         "points": {"s:top": ix(0, nz - 1), "s:mid": ix(0, nz // 2), "s:bot": ix(0, 0)}}
    held = (uv[:, 1] > 0.24 - 1e-9) | (uv[:, 1] < 1e-9) | (uv[:, 0] > 0.08 - 1e-9)
    ch = gp.border_chain(M, "s:top..bot")
    Y, info = gp.smooth_border(M, X, held, "s:top..bot", spline=0, ends=0.005, tol=0.03, rounds=60)
    assert info["rounds"] > 0, info
    chord = lambda P: np.abs(P[:, 0] - (P[0, 0] + (P[-1, 0] - P[0, 0]) * (P[:, 2] - P[0, 2]) / (P[-1, 2] - P[0, 2]))).max()
    assert chord(X[ch]) > 0.018 and chord(Y[ch]) < 0.0015, (chord(X[ch]), chord(Y[ch]), info)
    assert np.allclose(Y[held], X[held])
    # (2) a slide's grip is held for later ops unless it lets go above a point
    BV = [(0.0, 0.0, 0.0)]  # (slide needs a body; a large flat slab behind the sheet, y > 0)
    gx, gz = np.meshgrid(np.linspace(-0.2, 0.3, 11), np.linspace(-0.1, 0.35, 10))
    BV = np.c_[gx.ravel(), np.full(gx.size, 0.02), gz.ravel()]
    r = lambda i, j: i * 10 + j
    BF = np.array([f for i in range(10) for j in range(9) for f in ((r(i, j), r(i + 1, j), r(i + 1, j + 1)), (r(i, j), r(i + 1, j + 1), r(i, j + 1)))])
    sl = {"at": "s:mid..bot", "patch": 0.012, "follow": 0.001, "by": 0.0}
    ops = lambda extra: [{"slide": {"slides": [dict(sl, **extra)], "steps": 2, "tol": None}},
                         {"smooth": {"border": "s:top..bot", "spline": 0, "ends": 0.005, "tol": 0.03, "rounds": 60}}]
    held2 = (uv[:, 1] > 0.24 - 1e-9) | (uv[:, 0] > 0.08 - 1e-9)
    _, i_keep = gp.style(M, X, held2, ops({}), body=(BV, BF))
    _, i_go = gp.style(M, X, held2, ops({"let_go_above": "s:bot"}), body=(BV, BF))
    assert i_go[1]["smooth"]["rounds"] > i_keep[1]["smooth"]["rounds"], (i_keep[1], i_go[1])
    # (C186) a hold "at" a border of a piece the garment hasn't (a jacket with no side panel) is skipped
    assert gp.hold_region(M, X, at=["side.L:sideF.b..sideB.b", "s:mid..bot"]).sum() == len(gp.border_chain(M, "s:mid..bot"))


def _hung_sheet(W=0.3, H=0.4, n=(21, 28), tilt=30.0):
    """A woven rectangle (pattern W x H, grain along its height) whose top edge (uv y = H) is held, the rest started
    TILTED `tilt` deg off plumb toward -y: what a hand holding a cloth up by its top edge would let fall."""
    nx, ny = n
    uv = np.array([(x, y) for y in np.linspace(0, H, ny) for x in np.linspace(0, W, nx)])
    ix = lambda i, j: j * nx + i
    F = [f for j in range(ny - 1) for i in range(nx - 1)
         for f in ((ix(i, j), ix(i + 1, j), ix(i + 1, j + 1)), (ix(i, j), ix(i + 1, j + 1), ix(i, j + 1)))]
    t = np.radians(tilt)
    s = H - uv[:, 1]
    X = np.c_[uv[:, 0] - W / 2, -s * np.sin(t), 1.0 - s * np.cos(t)]
    M = {"F": np.array(F), "uv": uv, "piece": np.zeros(len(uv), int), "names": ["sheet"], "sew": [], "points": {}}
    return M, X, uv[:, 1] > H - 1e-9


def test_hang_sheet_from_its_top_edge(verbose=True):
    """SUPPORTS, NOT HOLDS (supports thread, 2026-10-23; garment_pull.HANG / STYLE_HANG): a plain woven rectangle (300 x
    400 mm) held by its top edge only, started tilted 30 deg: a styling relax WITH the hang lets it fall plumb and stop
    at its thread length (its spread off the top edge's plane (y) <= 12 mm, the hem within 1.5 % of 400 mm below the
    top, threads p99 <= 2.5 %: the weight's own strain, under the jacket fit's 7-8 %; the Jacobi thread cap leaves ~2 %
    on the rows under the held edge); the same relax without the hang leaves it tilted (y spread > 150 mm: no weight, nothing
    moves it)."""
    M, X, top = _hung_sheet()
    reads = {}
    for hang in (False, True):
        Xn, inf = gp.relax(M, X, top, hang=hang)
        sp = float(Xn[:, 1].max() - Xn[:, 1].min())
        drop = 1.0 - float(Xn[:, 2].min())
        th = gp.thread_p99(M, Xn)[0]
        reads[hang] = (sp, drop, th)
        if verbose:
            print(f"style hang {hang}: y spread {sp * 1000:.1f} mm, drop {drop * 1000:.1f} mm (400), threads p99 "
                  f"{th * 100:.2f} %, {inf}")
    sp, drop, th = reads[True]
    assert sp <= 0.012, sp
    assert abs(drop - 0.4) <= 0.015 * 0.4, drop
    assert th <= 0.025, th
    assert reads[False][0] > 0.15, reads[False]


def test_a_hand_lets_go(verbose=True):
    """C199 THE HAND LETS GO (canvas s4; supports, not holds, C190): a styling grip with "let_go": true is not held for
    later ops. The hung sheet (top edge held, tilted 30 deg): a pull grips its hem's middle, then a hung relax. Held
    where the pull left it (the old rule), the hem stays tilted (y spread > 100 mm); let go, the sheet falls plumb
    (spread <= 12 mm, as test_hang_sheet_from_its_top_edge). And a relax's "keep" holds only for that relax."""
    M, X, top = _hung_sheet()
    reads = {}
    for lg in (False, True):
        ops = [{"pull": {"handles": [{"at": 10, "dir": "down"}], "max_move": 0.006, "let_go": lg}},
               {"relax": {"hang": True}}]
        Xn, _ = gp.style(M, X, top, ops)
        reads[lg] = float(Xn[:, 1].max() - Xn[:, 1].min())
        if verbose:
            print(f"let_go {lg}: y spread {reads[lg] * 1000:.1f} mm")
    assert reads[False] > 0.10, reads
    assert reads[True] <= 0.012, reads
    Xk, _ = gp.style(M, X, top, [{"relax": {"hang": True, "keep": {"at": list(range(21))}}}])
    assert np.allclose(Xk[:21], X[:21]) and float(Xk[:, 1].max() - Xk[:, 1].min()) > 0.10


def test_a_floor_has_a_side(monkeypatch):
    """C197 A FLOOR HAS A SIDE: a thin two-sided leaf under the cloth (a shirt's open collar beside a jacket's gorge: a
    3 mm slab, top face out +z, bottom face out -z). The cloth starts 5 mm over it; a round takes part of it 1 mm into
    the leaf, nearer the bottom face. Without the side rule the floor reads those vertices as 1 mm off the BOTTOM face
    and shoves them out through it to the far side (the jacket's lapel cloth 260 % in one relax); with it the push only
    acts from the side each vertex is tracked on, so none ends on the far side. And a vertex that starts behind the
    floor, not over it, keeps its own depth as its level (it is never shoved through from behind)."""
    M = _sheet(n=21, size=0.1)
    X = np.c_[M["uv"] - 0.05, np.full(len(M["uv"]), 0.005)]
    LV, LF = _box([-0.04, -0.04, -0.0015], [0.04, 0.04, 0.0015])
    for side in (False, True):
        monkeypatch.setattr(gp, "FLOOR_SIDE", side)
        floor = gp.layer_floor(M, X, under=(LV, LF), flaps=False, gap=0.0015)
        A = gp.FlatARAP(dict(M, _floor=floor), X)
        W = A.weld(X)
        inside = (np.abs(W[:, 0]) < 0.03) & (np.abs(W[:, 1]) < 0.03)
        W[inside, 2] = -0.0005  # (into the leaf, nearer its bottom face)
        Y = A._floor(W, np.zeros(A.n, bool))
        through = int((Y[inside, 2] < -0.0015).sum())
        if side:
            assert through == 0, through
        else:
            assert through > 0.5 * inside.sum(), through  # (the old floor shoves them out through the far face)
    monkeypatch.setattr(gp, "FLOOR_SIDE", True)
    Xb = X.copy()
    Xb[:, 2] = -0.004  # (all of it starts BEHIND the leaf: the bottom face's side for those under it, beside it for the rest)
    Xb[np.abs(Xb[:, 0]) < 0.045, 2] = 0.004
    fl = gp.layer_floor(M, Xb, under=(LV, LF), flaps=False, gap=0.0015)[0]
    d, _, dist, _ = gp._signed_i(fl["surf"], Xb)
    beh = d < 0
    assert beh.any() and np.allclose(np.asarray(fl["level"])[beh], np.minimum(d[beh], 0.0015))


def test_thread_stop_never_tears_a_face():
    """C198 THREADS FIRST FOR A PINNED MOVE: the slack strip's free end dragged along the chord with a loose p99 stop
    (tol 10 %): by the p99 the drag goes on while the faces at the grip tear. With "thread_stop" the drag stops before
    any face's warp / weft passes max(its start, STYLE_THREAD_CAP) + BORDER_LOCAL_TOL."""
    M, X, held = _strip()
    h = [{"at": "strip:tipA..tipB", "dir": [1, 0, 0]}]
    F, _ = gp.thread_faces(M)
    worst = lambda Y: float(gp.thread_strain(M, Y)[0].max())
    X0, i0 = gp.pull(M, X, held, h, step=0.003, tol=0.10, max_move=0.4)
    X1, i1 = gp.pull(M, X, held, h, step=0.003, tol=0.10, max_move=0.4, thread_stop=True)
    assert worst(X0) > 0.05, worst(X0)
    assert i1["stopped"] == "thread" and worst(X1) <= gp.STYLE_THREAD_CAP + gp.BORDER_LOCAL_TOL + 0.01, (i1["stopped"], worst(X1))
    assert i1["moved_mm"]["strip:tipA..tipB"] < i0["moved_mm"]["strip:tipA..tipB"]


def test_a_patch_covers_what_is_under_it():
    """C201 WHAT A PATCH COVERS LIES UNDER IT: a coarse patch (5 x 5 vertices, 10 mm apart) stitched along its top row
    onto a fine base (2.5 mm) lying in z = 0; the patch lies 1 mm out, but the base bulges 3 mm out under it, so its
    vertices between the patch's stand outside the patch (the ragged pocket flap). patch_lie lays every covered base
    vertex THICK behind the patch; base cloth beside the patch is not moved."""
    from hifipushie import pattern_form as pf
    B = _sheet(n=41, size=0.1)
    P = _sheet(n=5, size=0.04)
    nb = len(B["uv"])
    M = {"F": np.r_[B["F"], P["F"] + nb], "uv": np.r_[B["uv"], P["uv"] + 0.03], "piece": np.r_[np.zeros(nb, int), np.ones(len(P["uv"]), int)],
         "names": ["front", "flap"], "sew": np.zeros((0, 2), int), "points": {}}
    X = np.c_[np.r_[B["uv"], P["uv"] + 0.03] - 0.05, np.zeros(len(M["uv"]))]
    X[nb:, 2] = 0.001
    under = (np.abs(X[:nb, 0] - 0.0) < 0.019) & (np.abs(X[:nb, 1] - 0.0) < 0.019)
    X[:nb][under, 2] = 0.003
    top = nb + np.where(np.isclose(P["uv"][:, 1], 0.04))[0]  # (the flap's top row stitched to the base under it)
    st = [(int(np.argmin(np.linalg.norm(X[:nb, :2] - X[t, :2], axis=1))), int(t)) for t in top]
    M["stitch"] = np.asarray(st)
    BV = np.array([(x, y, -0.02) for x in np.linspace(-0.2, 0.2, 9) for y in np.linspace(-0.2, 0.2, 9)])
    ix = lambda i, j: i * 9 + j
    BF = np.array([f for i in range(8) for j in range(8) for f in ((ix(i, j), ix(i + 1, j), ix(i + 1, j + 1)), (ix(i, j), ix(i + 1, j + 1), ix(i, j + 1)))])
    Y, info = gp.patch_lie(M, X, body=(BV, BF))
    cov = under & ~np.isin(np.arange(nb), M["stitch"][:, 0])
    assert info["flap"]["moved"] >= 0.9 * cov.sum(), (info, int(cov.sum()))
    assert (Y[:nb][cov, 2] <= 0.001 - pf.THICK + 1e-6).all(), Y[:nb][cov, 2].max()
    far = (np.abs(X[:nb, 0]) > 0.035) | (np.abs(X[:nb, 1]) > 0.035)
    assert np.allclose(Y[:nb][far], X[:nb][far])


def test_made_pieces_move_with_what_they_are_sewn_to(monkeypatch):
    """C202 A MADE PIECE MOVES WITH THE CLOTH IT IS SEWN TO (canvas s6): worn_style held every piece no op names, so a
    jacket worn open kept its stand + collar where the fit left them while the fronts relaxed, and the plain gorge cloth
    sewn to the held stand tore (front plain p99 9.5 -> 13.8 % in one relax, weft +16-24 % by the stand seam; freed:
    8.1 %). A made piece sewn to a moved piece is free, through a chain (collar -> stand -> front); a made piece sewn
    only to held cloth stays held. And under = (V, F, mesh): the under garment's made pieces are no floor for this
    garment's own cloth, only for its made pieces (cloth on cloth, made on made)."""
    S = _sheet(n=5, size=0.04)
    k = len(S["uv"])
    names = ["front", "stand", "collar", "pocket", "back"]
    M = {"F": np.vstack([S["F"] + i * k for i in range(5)]), "uv": np.vstack([S["uv"] + [0.05 * i, 0] for i in range(5)]),
         "piece": np.repeat(np.arange(5), k), "names": names, "made": ["stand", "collar", "pocket"], "points": {},
         "sew": np.array([[0 * k + 4, 1 * k + 0], [1 * k + 4, 2 * k + 0], [4 * k + 4, 3 * k + 0]])}
    X = np.c_[M["uv"], np.zeros(len(M["uv"]))]
    seen = {}

    def fake_style(Ms, X_, held, ops, body=None, log=None, floor=None):
        seen["held"], seen["floor"] = np.asarray(held, bool), floor
        return X_, []
    monkeypatch.setattr(gp, "style", fake_style)
    monkeypatch.setattr(gp, "PATCH_LIE", False)
    g = {"worn_open": {"front:x": 0.06}, "style": [{"smooth": {"pieces": ["front"]}}]}
    monkeypatch.setattr(gp, "style_ops", lambda g_: g_["style"])
    pid = M["piece"]
    for on in (True, False):
        monkeypatch.setattr(gp, "MADE_FREE", on)
        gp.worn_style(M, X, None, g)
        h = seen["held"]
        assert not h[pid == 0].any() and h[pid == 4].all() and h[pid == 3].all()  # (the pocket sewn to held cloth: held)
        assert (not h[pid == 1].any() and not h[pid == 2].any()) if on else (h[pid == 1].all() and h[pid == 2].all())
    UV = np.array([[-1, -1, -0.01], [1, -1, -0.01], [0, 1, -0.01], [-1, -1, -0.02], [1, -1, -0.02], [0, 1, -0.02]], float)
    um = {"F": np.array([[0, 1, 2], [3, 4, 5]]), "piece": np.array([0, 0, 0, 1, 1, 1]), "names": ["front", "collar"], "made": ["collar"]}
    gp.worn_style(M, X, None, g, under=(UV, um["F"], um))
    fl = {f["name"]: f for f in seen["floor"]}
    made_v = np.where(np.isin(pid, [1, 2, 3]))[0]
    assert set(fl["under"]["v"]).isdisjoint(made_v) and set(fl["under1"]["v"]) == set(made_v)
    assert np.allclose(fl["under"]["surf"].V[:, 2], -0.01) and np.allclose(fl["under1"]["surf"].V[:, 2], -0.02)
