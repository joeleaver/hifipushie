"""cut_shape (R3f-11, C510): a collar flattened as SHAPED cloth: the tailor's shrink / stretch declared per run."""
import numpy as np
import pytest

from hifipushie.cut_shape import SHAPE_MAX_PCT, ShapeRefused, flatten_shaped, resolve
from hifipushie.flatten import strain
from hifipushie.mark_split import areas

NR, NC, KS = 9, 31, 4
NECK, ROLL, OUTER = 0.02, -0.05, 0.04  # + stretch (the toile's run longer than the flat's), - shrink


def _collar():
    """A synthetic collar band: a flat rectangle (the cloth) shaped onto a surface of revolution whose rows are its
    rows times (1 + d): d = NECK at the neck row, ROLL at the roll, OUTER at the outer edge, linear between (a band
    curved in itself: no flat piece lies on it unless shaped)."""
    R0, th, h = 0.12, 1.6, 0.06
    s = np.linspace(0, h, NR)
    d = np.r_[np.linspace(NECK, ROLL, KS + 1), np.linspace(ROLL, OUTER, NR - KS)[1:]]
    R = R0 * (1 + d)
    dz = np.sqrt(np.clip(1 - (np.diff(R) / np.diff(s)) ** 2, 0, 1)) * np.diff(s)
    z = np.r_[0, np.cumsum(dz)]
    a = np.linspace(-th / 2, th / 2, NC)
    V = np.array([[R[r] * np.sin(t), -R[r] * np.cos(t), z[r]] for r in range(NR) for t in a])
    F = []
    for r in range(NR - 1):
        for c in range(NC - 1):
            i = r * NC + c
            F += [[i, i + 1, i + NC + 1], [i, i + NC + 1, i + NC]]
    half = (NC - 1) // 2
    lines = {"neck:front": (0, list(range(half))), "neck:back": (0, list(range(half, NC - 1))),
             "roll": (KS, list(range(NC - 1))), "outer": (NR - 1, list(range(NC - 1)))}
    return V, np.array(F), lines


def _mean(V, F, S):
    ar = areas(V, F)
    return float((strain(S) * ar).sum() / ar.sum() * 100)


def test_declared_shaping_flattens_with_low_strain_and_runs_at_their_ease():
    V, F, lines = _collar()
    U0, S0, F0, rep0 = flatten_shaped(V, F, (NR, NC, KS), lines, {})
    want = {"neck:front": NECK, "neck:back": NECK, "roll": ROLL, "outer": OUTER}
    U, S, Fk, rep = flatten_shaped(V, F, (NR, NC, KS), lines, want)
    assert _mean(V, Fk, S) < 0.5 < _mean(V, F0, S0)
    for k, d in want.items():  # each run's flat / toile is its declared ease (the seams equal within it)
        assert abs(rep["runs"][k]["flat_pct"] - d * 100) < 0.3, (k, rep["runs"][k])
    assert rep["runs"]["roll"]["asks_within"]


def test_ease_beyond_wool_is_refused_by_name():
    al = {"undercollar": {"roll": "roll", "fall": "outer", "outer": "outer", "neck_back.L": "neck:back.L:neck",
                          "neck_back.R": "neck:back.R:neck"}}
    with pytest.raises(ShapeRefused, match="undercollar:roll.*beyond what wool takes"):
        resolve({"undercollar:roll": -(SHAPE_MAX_PCT + 1)}, al)
    with pytest.raises(ShapeRefused, match="no run 'stand'"):
        resolve({"undercollar:stand": 2}, al)
    got = resolve({"undercollar:fall": 4, "undercollar:neck_back.L": -3}, al)
    assert got == {"outer": 0.04, "neck:back.L:neck": -0.03, "neck:back.R:neck": -0.03}
    al["collar"] = al["undercollar"]
    with pytest.raises(ShapeRefused, match="one flat, one shaping"):
        resolve({"undercollar:roll": -3, "collar:roll": -2}, al)
