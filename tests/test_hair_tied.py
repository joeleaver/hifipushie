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


def test_curtain_hug_lies_down():
    """curtain.hug: the first row's front lies on the scalp where it leaves the hairline (no frayed rim)."""
    a, b = _tie(curtain={"span": 60}), _tie(curtain={"span": 60, "hug": 1.0})
    k = next(k for k in a if k.startswith("tg0_") and abs(_az(a[k])[0]) < 20)
    ha, hb = np.array([p[2] for p in a[k]["pts"]]), np.array([p[2] for p in b[k]["pts"]])
    assert hb[1] < 0.5 * ha[1] and abs(hb[-1] - ha[-1]) < 1e-6, (ha, hb)


def test_curtain_drape_arcs_forward_over_the_line():
    """curtain.drape: the first row near the part roots `drape` deg behind the hairline yet still runs along it (an
    arc forward over the band: no bare V under the part); dip lowers that run; both 0 = the old groom exactly; the
    other rows don't move."""
    sc, _ = _ball_head()
    base = {"span": 60, "along": 30}
    a, b = _tie(curtain=base), _tie(curtain={**base, "drape": 8.0})
    c = _tie(curtain={**base, "drape": 8.0, "dip": 4.0})
    assert a == _tie(curtain={**base, "drape": 0.0, "dip": 0.0})
    front = [k for k in a if k.startswith("tg0_") and abs(_az(a[k])[0]) < 12]
    assert front
    for k in front:
        ea, eb, ec = _el(a[k]), _el(b[k]), _el(c[k])
        cw = 1 - abs(_az(a[k])[0]) / 60
        assert abs((eb[0] - ea[0]) - 8.0 * cw) < 0.6, (k, ea[0], eb[0])   # rooted further back
        assert eb[1:4].min() < eb[0] - 4.0 * cw, (k, eb)                  # ...and arcing forward (down) to the line
        assert abs(eb[2:4].min() - ea[2:4].min()) < 2.0, (k, ea, eb)       # the run along the line is where it was
        assert ec[2:4].min() < eb[2:4].min() - 2.0 * cw, (k, eb, ec)       # dip: that run lower, over the forehead
    for k in a:
        if not k.startswith("tg0_"):
            assert a[k] == b[k], k


def test_gather_strand_dials():
    """gather.strands: strand dials for the gathered hair alone (a loose texture on top), carried on every gather lock."""
    locks = _tie(gather={"strands": {"wave": 0.02}})
    g = [lk for k, lk in locks.items() if k.startswith("tg")]
    assert g and all(lk.get("strands") == {"wave": 0.02} for lk in g)
    assert all("strands" not in lk for k, lk in _tie().items() if k.startswith("tg"))
    tl = _tie(tail={"strands": {"wave": 0.03}})
    assert all(lk.get("strands") == {"wave": 0.03} for k, lk in tl.items() if k.startswith("tt"))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)


def test_curtain_sag_lowers_the_run_over_the_temples():
    """curtain.sag: the first row's run on to the ear's top hangs below its great circle (the forehead a rounder arch);
    0 = the old groom exactly; roots and the other rows don't move."""
    base = {"span": 60, "along": 30, "drape": 8.0}
    a, b = _tie(curtain=base), _tie(curtain={**base, "sag": 10.0})
    assert a == _tie(curtain={**base, "sag": 0.0})
    front = [k for k in a if k.startswith("tg0_") and abs(_az(a[k])[0]) < 30]
    assert front
    for k in front:
        ea, eb = _el(a[k]), _el(b[k])
        cw = 1 - abs(_az(a[k])[0]) / 60
        assert abs(ea[0] - eb[0]) < 1e-6 and abs(ea[-1] - eb[-1]) < 1e-6, k
        assert (ea - eb).max() > 7.0 * cw, (k, ea, eb)
    for k in a:
        if not k.startswith("tg0_"):
            assert a[k] == b[k], k
