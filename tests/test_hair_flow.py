"""Swept-back tied hair as a flow field, a hanging tail, escaped pieces, and the STYLE (hair_flow.py: groom.tied).
No Blender. `uv run pytest tests/test_hair_flow.py`.

What these hold (Tess, 2026-10-11; Joe on the row / curtain gather: "flat across her head instead of swept back and
hanging down. This is a super common hairstyle, so we need to be able to get it right and repeat/riff on it"):
- the gather is rooted ALL OVER the scalp, not in rows from the hairline, and every way runs BACK to the tie: on the
  top of the head the hair's direction is front-to-back, never across;
- the two banks of a centre parting stay on their own side in front of the ears (the far side's front does not
  cross over the top to an off-centre tie), and rows of roots stand on the parting itself;
- a way never crosses bare skin: it stays above the hairline (over the ears' tops), and a tight style hugs the head
  where a loose one stands off it and sags;
- the tail HANGS: its end is below the tie and nearly vertical, however it leaves the tie; fullness is what was asked;
- escaped pieces are bundles of single hairs that fall;
- the style is a handful of words: the defaults are an ordinary ponytail, a riff changes one word, a wrong word is a
  clear error, and the old tie grooms are untouched."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from test_hair_loose import _ball_head  # noqa: E402

from hifipushie import hair, hair_flow as hf, hair_tied as ht  # noqa: E402


def _grow(tied, seed=2):
    sc, _ = _ball_head()
    spec = {"hair": {"style": "strands", "groom": {"tied": tied, "seed": seed}}}
    g = hair.groom_params(spec)
    line = hair.hairline(sc, g)
    return sc, g, line, ht.grow(sc, g, line, np.random.default_rng(seed))


def _world(sc, lk):
    return hair.lock_world(sc, lk, lk["pts"])


def test_defaults_are_an_ordinary_ponytail():
    sc, g, line, locks = _grow({})
    kinds = {k[1] for k in locks}
    assert {"g", "t", "b"} <= kinds, kinds  # gather, tail, band
    tp = ht.params(g["tie"])[0]
    assert tp["gather"]["mode"] == "flow" and tp["tail"]["hang"]
    assert g["parting"]["side"] == "centre"
    assert sum(k.startswith("tg") for k in locks) > 80  # roots all over the scalp
    # roots are spread over the scalp: far more inside the hairline than on it
    assert sum(k.startswith("tg1_") for k in locks) > 40 and sum(k.startswith("tg0_") for k in locks) > 20


def test_top_of_the_head_runs_front_to_back():
    sc, g, line, locks = _grow({"tie": "low", "tightness": 0.4})
    back = []
    for k, lk in locks.items():
        if not k.startswith("tg"):
            continue
        P = _world(sc, lk) - sc.C
        for a, b in zip(P[1:-1], P[2:]):  # (a lock's first step is its root leaving the scalp / the parting)
            m = 0.5 * (a + b)
            if m[2] > 0.06 and m[1] < 0.03 and abs(m[0]) > 0.02:  # on top, in front of the crown, off the parting
                back.append(((b - a) / np.linalg.norm(b - a))[1])
    back = np.array(back)
    assert len(back) > 30
    assert np.median(back) > 0.7 and np.mean(back > 0.3) > 0.9, (np.median(back), np.mean(back > 0.3))  # back, not across


def test_every_way_ends_in_the_tie_and_stays_in_the_hair():
    for tied in ({"tie": "low", "side": "left"}, {"tie": "high", "part": "none", "tightness": 0.9}, {"tie": "top"}):
        sc, g, line, locks = _grow(tied)
        tp = ht.params(g["tie"])[0]
        tie = hair.dirs(*tp["at"])
        for k, lk in locks.items():
            if not k.startswith("tg"):
                continue
            pts = np.asarray(lk["pts"], float)
            end = hair.dirs(pts[-1, 0], pts[-1, 1])
            assert float(end @ tie) > 0.999, (tied, k)
            assert pts[:, 2].min() >= 0.0 and pts[:, 2].max() < 0.06, (k, pts[:, 2])
            far = np.degrees(np.arccos(np.clip(hair.dirs(pts[:, 0], pts[:, 1]) @ tie, -1, 1))) > 25
            fa = np.abs(((pts[:, 0] + 180) % 360) - 180)
            over = tp["gather"]["overhang"] + 6.0  # (smoothing rounds the keep-in's corner by a few degrees)
            lim = hair._line_at(line, pts[:, 0]) - over
            ok = (pts[:, 1] >= lim) | ~far | ((fa > 52) & (fa < 112))
            assert ok.all(), (tied, k, pts[~ok])


def test_sides_of_a_parting_stay_on_their_side_in_front():
    sc, g, line, locks = _grow({"tie": "low", "side": "left", "tightness": 0.4})
    n = 0
    for k, lk in locks.items():
        if not k.startswith("tg"):
            continue
        P = _world(sc, lk) - sc.C
        if P[0, 1] > -0.03 or abs(P[0, 0]) < 0.015:
            continue  # roots in the front, off the parting
        front = P[:, 1] < 0.0
        assert np.all(np.sign(P[front, 0]) == np.sign(P[0, 0])), (k, P[front, 0])
        n += 1
    assert n > 10
    # rows of roots on the parting's banks
    on = [k for k, lk in locks.items() if k.startswith("tg1_") and abs((_world(sc, lk) - sc.C)[0, 0]) < 0.006
          and (_world(sc, lk) - sc.C)[0, 2] > 0.04 and (_world(sc, lk) - sc.C)[0, 1] < 0.03]
    assert len(on) >= 6, on
    _, _, _, none = _grow({"tie": "low", "part": "none"})
    on0 = [k for k, lk in none.items() if k.startswith("tg1_") and abs((_world(sc, lk) - sc.C)[0, 0]) < 0.006
           and (_world(sc, lk) - sc.C)[0, 2] > 0.04 and (_world(sc, lk) - sc.C)[0, 1] < 0.03]
    assert len(on0) < len(on)


def test_tightness_is_lift_and_sag():
    sc, _, _, tight = _grow({"tightness": 1.0})
    _, _, _, loose = _grow({"tightness": 0.0})
    h = lambda L: np.mean([np.max(np.asarray(lk["pts"])[:, 2]) for k, lk in L.items() if k.startswith("tg")])  # noqa: E731
    assert h(loose) > h(tight) + 0.008, (h(loose), h(tight))
    assert hf.style({"tightness": 1.0})["tie"]["gather"]["sag"] == 0.0
    assert hf.style({"tightness": 0.2, "lift": 0.0})["tie"]["gather"]["puff"] < hf.style({"tightness": 0.2})["tie"]["gather"]["puff"]


def test_tail_hangs():
    for tied in ({"tie": "low"}, {"tie": "high", "tightness": 0.9}, {"tie": "low", "side": "left", "tail": {"to": "shoulder"}}):
        sc, g, line, locks = _grow({**tied, "tail": {"length": 0.3, **(tied.get("tail") or {})}})
        tails = [_world(sc, lk) for k, lk in locks.items() if k.startswith("tt")]
        assert len(tails) >= 14
        tie = sc.point(*ht.params(g["tie"])[0]["at"], 0.0)
        ends = np.array([P[-1] for P in tails])
        assert np.median(ends[:, 2]) < tie[2] - 0.12 and np.all(ends[:, 2] < tie[2] - 0.04), (tied, ends[:, 2] - tie[2])  # ends well below the tie
        d = np.array([(P[-1] - P[-3]) / np.linalg.norm(P[-1] - P[-3]) for P in tails])
        assert np.median(d[:, 2]) < -0.8, (tied, np.median(d[:, 2]))  # and hangs there
        _, _, h = sc.coords(np.concatenate(tails))
        assert h.min() > -1e-6  # never inside the head
    # fullness is the bundle's radius
    r = {}
    for f in (0.2, 0.9):
        sc, g, line, locks = _grow({"tail": {"fullness": f, "wave": 0.0}})
        T = np.array([_world(sc, lk)[5] for k, lk in locks.items() if k.startswith("tt")])
        r[f] = float(np.sqrt(((T - T.mean(0)) ** 2).sum(1).mean()))
    assert r[0.9] > 1.4 * r[0.2], r


def test_escaped_pieces_are_bundles_of_single_hairs_that_fall():
    sc, g, line, locks = _grow({"escaped": {"count": 3, "where": ["temple", "ear"]}})
    es = {k: lk for k, lk in locks.items() if k.startswith("te")}
    pieces = {k.split("_")[0] for k in es}
    assert len(pieces) == 6 and len(es) >= 18, (len(pieces), len(es))
    for k, lk in es.items():
        assert 1 <= lk["hairs"] <= 2 and lk["space"] == "xyz"
        P = np.asarray(lk["pts"], float)
        assert P[-1, 2] < P[0, 2] - 0.02, k  # it falls
    assert not any(k.startswith("te") for k in _grow({"neatness": 1.0})[3])
    assert any(k.startswith("te") for k in _grow({"neatness": 0.2})[3])
    try:
        _grow({"escaped": {"count": 1, "where": ["chin"]}})
        raise AssertionError("unknown zone accepted")
    except ValueError as e:
        assert "where" in str(e)


def test_style_words():
    s = hf.style({})
    assert s["tie"]["at"] == [180.0, -6.0] and s["parting"]["side"] == "centre"
    assert hf.style({"tie": "high", "side": "left"})["tie"]["at"] == [150.0, 40.0]
    assert hf.style({"side": "right"})["tie"]["at"][0] == 210.0
    assert hf.style({"part": "none"})["parting"] == {"side": "none"}
    assert hf.style({"tail": "bun"})["tie"]["tail"]["coil"] > 0
    assert hf.style({"tail": {"kind": "plait"}})["tie"]["tail"]["plait"]
    assert hf.style({"tail": "none"})["tie"]["tail"] is False
    assert hf.style({"ears": "covered"})["tie"]["gather"]["ears"] > 0
    assert hf.style({"neatness": 0.1})["strands"]["halo"] > hf.style({"neatness": 0.9})["strands"]["halo"]
    assert hf.style({"detail": {"tie": {"gather": {"spacing": 0.03}}}})["tie"]["gather"]["spacing"] == 0.03
    half = hf.style({"half": True, "length": 0.35})
    assert half["loose"]["length"] == 0.35 and half["tie"]["gather"]["above"] is not None
    for bad in ({"tie": "sideways"}, {"side": "up"}, {"part": "zigzag"}, {"tail": {"kind": "mullet"}}, {"hieght": 1}):
        try:
            hf.style(bad)
            raise AssertionError(f"accepted {bad}")
        except ValueError:
            pass
    # the spec's own strand dials win over the style's
    from hifipushie import hair_cards as hc
    S = hc.strands_of({"hair": {"groom": {"tied": {"neatness": 0.0}}, "strands": {"halo": 0.05, "free": {"frizz": 0.9}}}})
    assert S["halo"] == 0.05 and S["free"]["frizz"] == 0.9 and "flyaway" in S["free"]
    try:
        hair.groom_params({"hair": {"groom": {"tied": {}, "tie": {"at": [180, 20]}}}})
        raise AssertionError("tied + tie accepted")
    except hair.HairError as e:
        assert "detail" in str(e)


def test_half_up_gathers_only_the_top():
    sc, g, line, locks = _grow({"half": True, "tie": "mid"})
    for k, lk in locks.items():
        if k.startswith("tg"):
            assert (_world(sc, lk) - sc.C)[0, 2] > 0.0, k
    assert g["loose"]["below"] is not None


def test_old_tie_grooms_are_untouched():
    assert ht.TIE["gather"]["mode"] == "rows" and ht.TIE["tail"]["hang"] is False and ht.TIE["escaped"] is None
    sc, _ = _ball_head()
    g = hair._merge(hair.GROOM, {"tie": {"at": [176, 25]}, "parting": {"side": "centre"}, "seed": 2})
    locks = ht.grow(sc, g, hair.hairline(sc, g), np.random.default_rng(2))
    assert not hair.needs_body(g)
    assert sum(k.startswith("tg0_") for k in locks) and not any(k.startswith("te") for k in locks)
