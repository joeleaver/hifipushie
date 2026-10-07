"""Loose hair (hair_loose.py: groom.loose), curls, and the solid surface inside a loose mass of cards
(hair_cards.mass_shell). No Blender. `uv run pytest tests/test_hair_loose.py`.

What these hold: hair that falls must never enter the head or the shoulders, keeps its length, frames the face
instead of hanging over it (the first look had a curtain over one eye), a one-length cut ends at its level, an
afro stands out all round; a curl's swing never exceeds a third of its wavelength (it folds over itself) and its
guide has the points to carry it; the Blender collision proxy faces outward (inside out, Shrinkwrap painted the
hair onto the face and shoulders)."""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(__file__))
from test_hair_strands import _hanging, _lock, _strands  # noqa: E402

from hifipushie import hair, hair_loose as hl  # noqa: E402
from hifipushie import hair_cards as hc  # noqa: E402
from hifipushie import hair_strands as hs  # noqa: E402


def _ball_head(step=0.01):
    """A head without a body: a 9.5 cm ball as the scalp's rays see it, and its signed distance as the collider
    (plus a slab of shoulders 17 cm under the centre)."""
    C = np.array([0.0, 0.0, 1.6])
    sc = hair.Scalp(C, None, {})
    sc.R = np.full((len(sc.A), len(sc.E)), 0.095)
    lo = C + np.asarray(hl.BOX[0])
    n = np.ceil((np.asarray(hl.BOX[1]) - np.asarray(hl.BOX[0])) / step).astype(int) + 1
    X = np.stack(np.meshgrid(*[lo[i] + step * np.arange(n[i]) for i in range(3)], indexing="ij"), -1)
    phi = np.minimum(np.linalg.norm(X - C, axis=-1) - 0.095, X[..., 2] - (C[2] - 0.17))
    return sc, hl.Collider(lo, step, phi)


def _grow(loose, parting="left"):
    sc, col = _ball_head()
    g = hair._merge(hair.GROOM, {"loose": loose, "parting": {"side": parting}, "seed": 2})
    line = hair.hairline(sc, g)
    return sc, col, hl.grow(sc, g, line, np.random.default_rng(2), col)


def test_loose_hair_falls_and_stays_out():
    sc, col, locks = _grow({"length": 0.3, "spacing": 0.03})
    assert len(locks) >= 25, len(locks)
    lowest, face = [], 0
    for n, lk in locks.items():
        assert lk["space"] == "xyz" and lk["free"] == 1.0 and lk["tier"] == "loose"
        P = np.asarray(lk["pts"]) + sc.C
        L = np.linalg.norm(np.diff(P, axis=0), axis=1).sum()
        assert 0.2 < L <= 0.31, (n, L)
        assert col.at(P[1:]).min() > -0.004, (n, col.at(P[1:]).min())  # (the grid is 1 cm here)
        lowest.append(P[:, 2].min() - sc.C[2])
        az, el = hair.az_el(P[3:] - sc.C)
        fa = np.abs(((az + 180) % 360) - 180)
        face += int(((fa < 35) & (el < 0) & (el > -60)).sum())
    assert np.median(lowest) < -0.1, np.median(lowest)  # it hangs below the ears
    assert min(lowest) > -0.18, min(lowest)  # and lies on the shoulders, not through them
    assert face == 0, face


def test_level_fringe_and_afro():
    sc, col, bob = _grow({"length": 0.3, "level": -0.08, "uneven": 0.0, "spacing": 0.03,
                          "fringe": {"length": 0.06, "level": -0.01}}, parting="none")
    ends = [np.asarray(lk["pts"])[-1, 2] for n, lk in bob.items() if not n.startswith("lf")]
    long = [z for z in ends if z < -0.05]
    assert len(long) > 0.6 * len(ends) and max(abs(z + 0.08) for z in long) < 0.004, sorted(ends)[:5]
    fr = [np.asarray(lk["pts"]) for n, lk in bob.items() if n.startswith("lf")]
    assert len(fr) >= 3
    for P in fr:
        az, _ = hair.az_el(P[-1:])
        assert abs(((az[0] + 180) % 360) - 180) < 60 and P[-1, 1] < P[0, 1] + 0.005, P[[0, -1]]
        assert P[-1, 2] >= -0.012
    sc, col, afro = _grow({"length": 0.08, "stiff": 1.0, "out": 1.0, "messy": 0.0, "uneven": 0.0, "body": 0.0,
                           "lift": 0.0, "spacing": 0.03}, parting="none")
    for n, lk in afro.items():
        P = np.asarray(lk["pts"])
        r = np.linalg.norm(P, axis=1)
        assert r[-1] - r[0] > 0.06, (n, r[0], r[-1])
        assert lk["radius"][-1] > 1.5
    with pytest.raises(ValueError):
        hl.params({"lenght": 0.2})


def test_collider_mesh_faces_out():
    sc, col = _ball_head()
    m = col.mesh()
    V, F = m["verts"].astype(float), m["faces"]
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    fc = V[F].mean(1)
    top = fc[:, 2] > sc.C[2]  # (the ball above the slab)
    assert ((fn[top] * (fc[top] - sc.C)).sum(1) > 0).mean() > 0.99
    P = np.array([[0.0, 0.0, 1.6], [0.0, 0.2, 1.6]])
    assert col.at(P)[0] < 0 < col.at(P)[1]
    assert abs(np.linalg.norm(col.push(P[:1] + [0.0, 0.05, 0.0], 0.01) - sc.C) - 0.105) < 0.006


def test_curl_never_folds():
    S = {**hc.STRANDS, "wave": 0.03, "wavelength": 0.012, "curl": 1.0}
    ph = hs.physical(S, free=True)
    assert ph["wave"] <= 0.35 * 0.012 + 1e-9, ph["wave"]
    lk = _lock("l0", [[0, 0.1, 0], [0, 0.1, -0.05], [0, 0.1, -0.1]])
    G = hs.lock_guides([lk], np.zeros(3), S)["free"]
    assert G["counts"][0] >= 8 * 0.1 / 0.012 - 1, G["counts"]
    off = np.linalg.norm(G["pts"][:, [0, 1]] - np.array([0, 0.1]), axis=1)
    assert off.max() < 0.3 * 0.012 * 2.3, off.max()
    # and nothing changes for hair that isn't tight (Tess's wave)
    S2 = {**hc.STRANDS, "wave": 0.012, "wavelength": 0.08}
    assert abs(hs.physical(S2, free=True)["wave"] - hs.SAFE["sub_wave"] * 0.012) < 1e-12


def test_mass_shell():
    locks = [dict(lk, tier="loose") for lk in _hanging(4)]
    D = _strands(locks, per=400, spread=0.03, n=40)
    D["pts"][:, 1] += np.random.default_rng(1).normal(0, 0.008, len(D["pts"])).astype(np.float32)
    tiles = [{"kind": "dense", "u0": 0.0, "u1": 0.13}]
    m = hc.mass_shell(D, locks, np.array([0.0, 0.0, 0.1]), tiles, triangles=600)
    assert m is not None and 100 < len(m["tris"]) <= 620, None if m is None else len(m["tris"])
    V = m["verts"]
    assert V[:, 2].min() > -0.32 and V[:, 2].max() < 0.03 and np.abs(V[:, 1] - 0.12).max() < 0.04
    assert (m["layer"] == -1).all() and m["uv"][:, 0].max() <= 0.13 + 1e-6
    assert hc.mass_shell(D, _hanging(4), np.zeros(3), tiles) is None  # (a tail's locks: tail_cores' job)
