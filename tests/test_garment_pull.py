"""Pull until it would stretch (C142, garment_pull.py): known answers.

1. A slack strip (pattern 300 x 20 mm) hung as an arc between its pinned end and a free end 200 mm away: its free end
   pulled stops within one step of where the pattern length (+ tol) runs out: along the chord at L (1 + tol) - a,
   straight up at sqrt((L (1 + tol))^2 - a^2).
2. Simon's shirt on wf_simon (the shirt spike's closed fit v1: the repo defaults + the concept's first button 34 mm
   below cfNeck), the band ends turned 30 deg about Simon's hinges, the collar points pulled out / side / up: the
   shirt spike's y3 reads (points 147 apart, 59-63 below HPS, collar crumple p95 <= 0.3 mm).
   Needs the workspace model: HIFIPUSHIE_HOME=<workspace with wf_simon> and HIFIPUSHIE_ASSETS; ~2 min:
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


def _wf_simon_home():
    h = os.environ.get("HIFIPUSHIE_HOME")
    return h and (Path(h) / "wf_simon" / "spec.json").exists()


@pytest.mark.skipif(not _wf_simon_home(), reason="needs HIFIPUSHIE_HOME with the wf_simon workspace model")
def test_shirt_collar_points_pulled_open_give_the_spike_reads():
    from hifipushie import cloth, pattern_form, resources, store
    spec = store.load("wf_simon")
    g = spec["cloth"]["shirt"]
    g.update({"closures": [{"name": "front", "spacing": {"first": 0.034, "from": "cfNeck"}}]})  # base_fit v1
    g = cloth.expanded(g)
    if "worn_open" not in spec["cloth"]["shirt"]:
        g.pop("worn_open", None)
    with resources.heavy("test_garment_pull shirt", gb=6.0):
        res = pattern_form.on_form("wf_simon", "shirt", spec, g=g)
    X, M, body = np.asarray(res["A"], float), res["mesh"], res["body"]
    P = M["points"]
    hps = np.asarray(body.at["hps.L"], float).reshape(-1)[-3:]
    held = gp.hold_mask(M, X, ["collar", "stand", "front.L", "front.R"], "closure:front")
    bvf = (np.asarray(body.V, float), np.asarray(body.T, int))
    sides = ("left", "right")
    turns = [{"at": [f"stand:{s}BottomCf", f"stand:{s}BottomEdge", f"stand:{s}TopCf"],
              "about": [f"stand:{s}BottomHinge", f"stand:{s}TopHinge"], "deg": 30, "toward": "side",
              "side_from": f"stand:{s}BottomHinge"} for s in sides]
    X, ti = gp.turn(M, X, held, turns, body=bvf)
    assert [t["sense"] for t in ti["turns"].values()] == [-1, 1]  # each band end opens away from CF (its own side)
    for t in turns:
        held[gp.vertices(M, t["at"])] = True
    handles = [{"at": f"collar:{s}TopEdge", "dir": {"side": 1, "out": 0.3, "up": 0.3},
                "side_from": f"collar:{s}TopHinge"} for s in sides]
    Xn, info = gp.pull(M, X, held, handles, body=bvf)
    l, r = Xn[P["collar:leftTopEdge"]], Xn[P["collar:rightTopEdge"]]
    apart = abs(l[0] - r[0]) * 1000
    below = [(hps[2] - p[2]) * 1000 for p in (l, r)]
    crum = float(np.percentile(gp.crumple(M, Xn, "collar"), 95))
    print(info, apart, below, crum)
    assert info["stopped"] == "stretch"
    assert 140 <= apart <= 154, apart  # y3 147 (concept ~147)
    assert all(58 <= b <= 64 for b in below), below  # y3 63 / 59 (concept 50-61)
    assert crum <= 0.30, crum  # y3 0.28; pinned variants 0.34-0.72
    assert np.allclose(Xn[held], X[held])
