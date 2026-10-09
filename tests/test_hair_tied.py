"""Tied hair (hair_tied.py: groom.tie): the front curtain and the face-framing pieces, and the parting's spelling.
No Blender. `uv run pytest tests/test_hair_tied.py`.

What these hold (Tess, 2026-10-09; the user on a ponytail combed straight back: "it didn't understand the part line,
or how the hair doesn't just go straight back, and how the wispies are intentional"): with a curtain, the front
locks first sweep DOWN AND OUT toward the ears' tops before they turn back to the tie (straight back = the great
circle, which never comes lower than its ends); locks behind the curtain's span are untouched; framing pieces fall
beside the face on both sides, in front of the ears, with mixed lengths; "center" is accepted for "centre" and a
wrong side is a clear error, not a bare KeyError."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from test_hair_loose import _ball_head  # noqa: E402

from hifipushie import hair, hair_tied as ht  # noqa: E402


def _tie(**extra):
    sc, _ = _ball_head()
    tie = {"at": [176, 25], "escape": 0, **extra}
    g = hair._merge(hair.GROOM, {"tie": tie, "parting": {"side": "centre"}, "seed": 2})
    line = hair.hairline(sc, g)
    return ht.grow(sc, g, line, np.random.default_rng(2))


def _el(lk):
    return np.array([p[1] for p in lk["pts"]], float)


def _az(lk):
    return np.array([((p[0] + 180) % 360) - 180 for p in lk["pts"]], float)


def test_curtain_sweeps_down_and_out_then_back():
    plain, cur = _tie(), _tie(curtain={"span": 60, "to": 88, "over": 10})
    front = [k for k in cur if k.startswith("tg0_") and abs(_az(cur[k])[0]) < 25]
    assert front, sorted(cur)[:10]
    for k in front:
        a, e = _az(cur[k]), _el(cur[k])
        assert e.min() < min(e[0], e[-1]) - 5 and e.min() < 20, (k, e)  # under its root and the tie: over the ear
        assert np.abs(a).max() > 70, (k, a)  # out to the side first, not over the crown
        assert e.min() < _el(plain[k]).min() - 5, k  # the plain groom runs straight back
    behind = [k for k in cur if k.startswith("tg0_") and abs(_az(cur[k])[0]) > 70]
    for k in behind:
        assert np.allclose(cur[k]["pts"], plain[k]["pts"]), k
    try:
        ht.params({"curtain": {"swing": 20}})
        raise AssertionError("unknown curtain key accepted")
    except ValueError as e:
        assert "curtain" in str(e)


def test_framing_pieces_fall_beside_the_face():
    locks = _tie(frame={"count": 3, "az": [50, 95], "length": [0.07, 0.15]})
    fr = [lk for k, lk in locks.items() if k.startswith("tf")]
    assert len(fr) == 6
    sides = [np.sign(np.asarray(lk["pts"])[0, 0]) for lk in fr]
    assert sides.count(1.0) == 3 and sides.count(-1.0) == 3
    lens = []
    for lk in fr:
        P = np.asarray(lk["pts"], float)
        assert P[-1, 2] < P[0, 2] - 0.04  # they fall
        assert P[-1, 1] < 0.03  # in front of the ear (y forward is -), beside the face
        lens.append(float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum()))
        assert lk["free"] == 1.0 and lk["strands"]["wave"] > 0
    assert max(lens) - min(lens) > 0.03, lens  # mixed lengths


def test_part_spelling():
    assert hair._part_side("center") == hair._part_side("centre") == 0.0
    try:
        hair._part_side("middle")
        raise AssertionError("bad side accepted")
    except ValueError as e:
        assert "centre" in str(e)


def test_one_sided_style():
    """An asymmetric look: framing pieces on her right only ([right, left] counts), and the curtain dropping over the
    right ear while the left sweeps back higher (a side's own values)."""
    locks = _tie(frame={"count": [3, 0]}, curtain={"over": 20, "right": {"over": 0}})
    fr = [lk for k, lk in locks.items() if k.startswith("tf")]
    assert len(fr) == 3 and all(np.asarray(lk["pts"])[0, 0] < 0 for lk in fr)  # her right = -x
    lo = {sd: min(_el(lk).min() for k, lk in locks.items() if k.startswith("tg0_") and np.sign(_az(lk)[0]) == sd
                  and abs(_az(lk)[0]) < 30) for sd in (-1.0, 1.0)}
    assert lo[-1.0] < lo[1.0] - 8, lo


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
