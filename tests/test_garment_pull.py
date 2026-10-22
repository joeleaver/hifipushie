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
3. The same shirt styled as the spike's q40 (C144): back + sides held where the relaxed fit has them, band ends turned
   as areas, points pulled, smoothed: the collar hugs the neck at CB / sides, the band corner keeps its stretch.
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
        assert tips[s]["stretch_max_pct"] <= tips0[s]["stretch_max_pct"] + 1.0, (s, tips[s], tips0[s])
        assert flips[s] <= 1, flips  # the closed collar 0; a rigid patch 18 / 28
    assert np.allclose(Xn[held], X[held])


@pytest.mark.skipif(not _wf_simon_home(), reason="needs HIFIPUSHIE_HOME with the wf_simon workspace model")
def test_shirt_collar_hugs_the_neck_at_the_back_and_sides():
    """C144 + every grip an area (the shirt spike's q40): relax, HOLD band + collar within 110 deg of CB where the
    relaxed fit has them, turn each band end 40 deg as a 15 mm area, pull the points side / out, smooth. The fall hugs
    the neck at CB and the sides as the closed collar does (q40: 73 / 70 / 70 mm vs closed 67 / 68 / 67); the band's
    top corner keeps its closed stretch (3 corner vertices turned alone: 14-22 %); clean tips."""
    res = _shirt_v1()
    X, M, body = np.asarray(res["A"], float), res["mesh"], res["body"]
    P = M["points"]
    hps = np.asarray(body.at["hps.L"], float).reshape(-1)[-3:]
    held = gp.hold_mask(M, X, ["collar", "stand", "front.L", "front.R"], "closure:front")
    sides = ("left", "right")
    r0 = _fall_edge_r(M, X)
    tips0 = {s: gp.tip_read(M, X, f"collar:{s}TopEdge") for s in sides}
    corner0 = [gp.tip_read(M, X, f"stand:{s}TopCf", near=0.008)["stretch_max_pct"] for s in sides]
    turns = [{"at": f"stand:{s}BottomEdge..{s}TopCf", "about": [f"stand:{s}BottomHinge", f"stand:{s}TopHinge"],
              "deg": 40, "toward": "side", "side_from": f"stand:{s}BottomHinge"} for s in sides]
    handles = [{"at": f"collar:{s}TopEdge", "dir": {"side": 1, "out": 0.3}, "side_from": f"collar:{s}TopHinge"}
               for s in sides]
    ops = [{"relax": {}}, {"hold": {"pieces": ["stand", "collar"], "within_deg": 110, "of": "back", "center": "stand"}},
           {"turn": {"turns": turns}}, {"pull": {"handles": handles}}, {"smooth": {"pieces": ["collar", "stand"]}}]
    Xn, infos = gp.style(M, X, held, ops, body=(np.asarray(body.V, float), np.asarray(body.T, int)))
    r = _fall_edge_r(M, Xn)
    corner = [gp.tip_read(M, Xn, f"stand:{s}TopCf", near=0.008)["stretch_max_pct"] for s in sides]
    l, rr = Xn[P["collar:leftTopEdge"]], Xn[P["collar:rightTopEdge"]]
    apart, below = abs(l[0] - rr[0]) * 1000, [(hps[2] - p[2]) * 1000 for p in (l, rr)]
    tips = {s: gp.tip_read(M, Xn, f"collar:{s}TopEdge") for s in sides}
    print(infos, r0, r, corner0, corner, apart, below, tips)
    assert infos[3]["pull"]["stopped"] == "stretch"
    assert all(b - a <= 7 for a, b in zip(r0, r)), (r0, r)  # hugs (q40 +3-6 mm; unheld: the fall +8 / +14 mm off)
    assert all(c <= c0 + 2.0 for c, c0 in zip(corner, corner0)), (corner0, corner)  # (this 1.5 / 2.5, closed 2.7)
    assert 135 <= apart <= 155 and all(66 <= b <= 80 for b in below), (apart, below)  # this 150 / 73-71; q40 137 / 76
    assert float(np.percentile(gp.crumple(M, Xn, "collar"), 95)) <= 0.30
    for s in sides:
        assert tips[s]["crumple_p95_mm"] <= tips0[s]["crumple_p95_mm"] + 0.06, (s, tips[s], tips0[s])
        assert tips[s]["stretch_max_pct"] <= tips0[s]["stretch_max_pct"] + 1.0, (s, tips[s], tips0[s])
        assert tips[s]["twist_deg"] <= tips0[s]["twist_deg"] + 15, (s, tips[s], tips0[s])  # this 31 / 33 vs 18 / 35
        assert gp.folded(M, Xn, f"collar:{s}TopEdge") <= 1


def test_a_grip_overlapping_a_hold_is_refused():
    M, X, held = _strip()
    with pytest.raises(ValueError, match="held vertices"):
        gp.pull(M, X, held, [{"at": "strip:tipA..tipB", "dir": [1, 0, 0], "patch": 0.5}])
