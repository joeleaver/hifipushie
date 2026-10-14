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


def test_lay_presses_a_crop_onto_the_head():
    """`lay`: a short stiff crop stands off the head as a brush; laid, its tips lie close over the scalp, without
    the low stiffness that lets gravity curl short locks. Per region: only the top is laid."""
    crop = {"length": 0.03, "spacing": 0.012, "stiff": 0.6, "out": 0.1, "lift": 0.001, "body": 0.002}

    def tips(loose):
        sc, _col, locks = _grow(loose, parting="none")
        P = np.array([np.asarray(lk["pts"])[-1] + sc.C for lk in locks.values()])
        az, el, h = sc.coords(P)
        side = np.abs(np.abs(((az + 180) % 360) - 180) - 90) < 30
        return np.where(side, el, el + 1000 * (el < 30)), h  # (low tips count only at the head's sides)
    el0, h0 = tips(crop)
    el1, h1 = tips({**crop, "lay": 0.8})
    top0, top1 = h0[(el0 > 55) & (el0 < 100)], h1[(el1 > 55) & (el1 < 100)]
    assert np.median(top0) > 0.006, np.median(top0)  # the brush
    assert np.median(top1) < 0.5 * np.median(top0), (np.median(top0), np.median(top1))
    el2, h2 = tips({**crop, "lay": {"top": 0.8, "front": 0.0, "sides": 0.0, "back": 0.0, "nape": 0.0}})
    assert np.median(h2[(el2 > 60) & (el2 < 100)]) < 0.6 * np.median(top0)
    low0, low2 = h0[(el0 > -20) & (el0 < 15)], h2[(el2 > -20) & (el2 < 15)]
    assert abs(np.median(low2) - np.median(low0)) < 0.002, (np.median(low0), np.median(low2))  # the sides as they were


def test_top_lay_leaves_the_upper_sides():
    """The "top" region's weight is full from 42 deg of elevation: the head's upper SIDES. A top lay must not press
    those (Garrett's sides lost 6.7 mm of width): locks rooted at 30-46 deg stand as without any lay."""
    crop = {"length": 0.03, "spacing": 0.012, "stiff": 0.6, "out": 0.1, "lift": 0.001, "body": 0.002, "messy": 0.0,
            "uneven": 0.0}

    def stand(loose):
        sc, _col, locks = _grow(loose, parting="none")
        R = np.array([np.asarray(lk["pts"])[0] + sc.C for lk in locks.values()])
        T = np.array([np.asarray(lk["pts"])[-1] + sc.C for lk in locks.values()])
        az, el, _ = sc.coords(R)
        _, _, h = sc.coords(T)
        fa = np.abs(((az + 180) % 360) - 180)
        return h[(el > 30) & (el < 46) & (fa > 50)], h[el > 70]
    up0, top0 = stand(crop)
    up1, top1 = stand({**crop, "lay": {"top": 0.8, "front": 0.0, "sides": 0.0, "back": 0.0, "nape": 0.0}})
    assert len(up0) > 5 and len(top0) > 3
    assert abs(np.median(up1) - np.median(up0)) < 0.0015, (np.median(up0), np.median(up1))
    assert np.median(top1) < 0.6 * np.median(top0), (np.median(top0), np.median(top1))


def test_lift_by_region():
    """`lift` per region (hair-garrett: a short cut stands off the skull by region, a lifted top over clipped sides):
    the top's laid locks stand higher than with the sides' lift everywhere; a scalar lift is unchanged."""
    crop = {"length": 0.03, "spacing": 0.012, "stiff": 0.6, "out": 0.0, "body": 0.0, "messy": 0.0, "uneven": 0.0,
            "lay": 0.6, "thickness": 0.003}

    def h_mid(loose):
        sc, _col, locks = _grow(loose, parting="none")
        R = np.array([np.asarray(lk["pts"])[0] + sc.C for lk in locks.values()])
        M = np.array([np.asarray(lk["pts"])[len(lk["pts"]) // 2] + sc.C for lk in locks.values()])
        _, el, _ = sc.coords(R)
        _, _, h = sc.coords(M)
        return np.median(h[el > 70]), np.median(h[(el > 0) & (el < 35)])
    t0, s0 = h_mid({**crop, "lift": 0.001})
    t1, s1 = h_mid({**crop, "lift": {"top": 0.008, "front": 0.001, "sides": 0.001, "back": 0.001, "nape": 0.001}})
    assert t1 > t0 + 0.0025, (t0, t1)  # (lift comes in over the first 3 cm: half of it at mid-lock)
    assert abs(s1 - s0) < 0.0015, (s0, s1)


def test_tuck_passes_behind_the_ear_on_one_side():
    """tuck "left": hair rooted over / in front of the ear on the person's left passes behind the ear at ear height;
    the right side still hangs in front."""
    base = {"length": 0.3, "spacing": 0.025, "stiff": 0.25, "messy": 0.0, "uneven": 0.0}

    def side_az(loose, left):
        sc, _c, locks = _grow(loose, parting="none")
        out = []
        for lk in locks.values():
            P = np.asarray(lk["pts"]) + sc.C
            a, e, _ = sc.coords(P[:1])
            a0 = ((a[0] + 180) % 360) - 180
            if (a0 > 0) != left or not (55 < abs(a0) < 100) or e[0] < 0:
                continue
            k = np.argmin(np.abs(P[:, 2] - (sc.C[2] - 0.035)))  # (about the ear's middle)
            ak, _ = hair.az_el(P[k] - sc.C)
            out.append(abs(((ak + 180) % 360) - 180))
        return np.median(out)
    l0, l1 = side_az(base, True), side_az({**base, "tuck": "left"}, True)
    r0, r1 = side_az(base, False), side_az({**base, "tuck": "left"}, False)
    assert l1 > 105 and l1 > l0 + 10, (l0, l1)  # behind the ear (no ear on the ball: back at 105 deg)
    assert abs(r1 - r0) < 2, (r0, r1)


def test_curtain_bangs_part_both_ways():
    sc, _c, locks = _grow({"length": 0.3, "spacing": 0.02, "uneven": 0.0, "messy": 0.0,
                           "fringe": {"length": 0.06, "span": 35, "sweep": "away", "curtain": 0.8}}, parting="centre")
    ends, lens = [], []
    for n, lk in locks.items():
        if not n.startswith("lf"):
            continue
        P = np.asarray(lk["pts"]) + sc.C
        ends.append((np.sign(P[0, 0] - sc.C[0]), P[-1, 0] - P[0, 0], abs(P[0, 0] - sc.C[0]),
                     np.linalg.norm(np.diff(P, axis=0), axis=1).sum()))
    E = np.array(ends)
    assert len(E) > 4
    assert np.all(E[:, 0] * E[:, 1] > -0.002)  # each side swept away from the part (outward), never across it
    inner, outer = E[E[:, 2] < np.median(E[:, 2]), 3], E[E[:, 2] >= np.median(E[:, 2]), 3]
    assert np.median(outer) > np.median(inner)  # longer toward the outer edges


def test_fade_shortens_and_thins_the_nape():
    base = {"length": {"front": 0.05, "top": 0.05, "sides": 0.03, "back": 0.03, "nape": 0.02}, "spacing": 0.01,
            "messy": 0.0, "uneven": 0.0, "lay": 0.5, "thickness": 0.003, "lift": 0.002}

    def nape(loose):
        sc, _c, locks = _grow(loose, parting="none")
        L, D = [], []
        for lk in locks.values():
            P = np.asarray(lk["pts"]) + sc.C
            a, e, _ = sc.coords(P[:1])
            if abs(((a[0] + 180) % 360) - 180) > 140 and e[0] < -10:
                L.append(np.linalg.norm(np.diff(P, axis=0), axis=1).sum())
                D.append((lk.get("strands") or {}).get("density", 1.0))
        return np.median(L), np.min(D) if D else 1.0
    l0, d0 = nape(base)
    l1, d1 = nape({**base, "fade": {"width": 0.03}})
    assert l1 < l0 - 0.003 and d1 < 0.6 and d0 == 1.0, (l0, l1, d0, d1)


def test_loose_halo_is_not_quartered_but_a_tails_is():
    from hifipushie import hair_strands as hs
    S = {**hc.strands_of({"hair": {"strands": {"halo": 1.0}}})}
    assert hs.physical(S, free=True, tail=False)["halo"] == pytest.approx(4 * hs.LOOSE_HALO * hs.physical(S, free=True, tail=True)["halo"])


def test_soft_part_keeps_the_roots_at_the_part():
    """part_soft: roots beside the part are not combed sideways off it (a bare V), some cross it."""
    def spread(loose):
        sc, _c, locks = _grow(loose, parting="centre")
        dx = []
        for lk in locks.values():
            P = np.asarray(lk["pts"]) + sc.C
            a, e, _ = sc.coords(P[:1])
            if abs(P[0, 0] - sc.C[0]) < 0.008 and e[0] > 50:
                k = min(3, len(P) - 1)
                dx.append(abs(P[k, 0] - P[0, 0]))
        return np.median(dx), len(dx)
    base = {"length": 0.3, "spacing": 0.012, "messy": 0.0, "uneven": 0.0}
    d0, n0 = spread(base)
    d1, n1 = spread({**base, "part_soft": True})
    assert n0 > 3 and d1 < 0.6 * d0, (d0, d1)


def test_face_rule_by_side():
    """face {"left": 0, "right": 1}: hair on the person's left may fall over that side of the face, the right side's is
    kept off it (one long curtain over a cheek, the other side clear)."""
    def over_face(loose):
        sc, _c, locks = _grow(loose, parting="right")
        L, R = 0, 0
        for lk in locks.values():
            P = np.asarray(lk["pts"]) + sc.C
            az, el = hair.az_el(P[3:] - sc.C)
            a = ((az + 180) % 360) - 180
            inside = (np.abs(a) < 35) & (el < 0) & (el > -60)
            L += int((inside & (a > 0)).sum())
            R += int((inside & (a < 0)).sum())
        return L, R
    base = {"length": 0.3, "spacing": 0.025, "messy": 0.0, "uneven": 0.0}
    l1, r1 = over_face({**base, "face": {"left": 0.0, "right": 1.0}})
    assert l1 > 5 and r1 == 0, (l1, r1)


def test_face_over_one_holds_the_hair_back_to_the_ear():
    """face 1.5: below the hairline the hair is kept out of ~87 deg either side of the face's centre (swept back off the
    cheek and temple to the ear, lt19's profile); face 1 lets it hang over the cheek (58 deg)."""
    def cheek(face):
        sc, _c, locks = _grow({"length": 0.3, "spacing": 0.025, "messy": 0.0, "uneven": 0.0, "face": face},
                              parting="centre")
        n = 0
        for lk in locks.values():
            P = np.asarray(lk["pts"]) + sc.C
            az, el = hair.az_el(P[3:] - sc.C)
            a = np.abs(((az + 180) % 360) - 180)
            n += int(((a > 62) & (a < 80) & (el < -5) & (el > -50)).sum())
        return n
    assert cheek(1.5) < 0.5 * max(cheek(1.0), 1), (cheek(1.5), cheek(1.0))


def test_soft_halo_is_denser_shorter_and_closer():
    from hifipushie import hair_strands as hs
    S = hc.strands_of({"hair": {"strands": {"halo": 0.5}}})
    a, b = hs.physical(S), hs.physical({**S, "halo_soft": 1.0})
    assert b["halo"] > 3 * a["halo"] and b["halo_m"] < 0.5 * a["halo_m"] and b["halo_len"] < 0.5 * a["halo_len"]
    assert a["halo_m"] == hs.SAFE["halo_m"]  # (off by default: older stacks unchanged)


def test_seen_takes_srgb_floats():
    """look.seen as [r, g, b] sRGB floats: near-grey hair's hue survives (in 8 bits a 6 deg turn came back unchanged)."""
    assert np.allclose(hair._lin([0.3568, 0.3137, 0.3098]), hair._lin("#5b504f"), atol=2e-3)
    lk = hair.full_look({"seen": [0.35, 0.32, 0.3]})
    assert lk["lit"].startswith("#") and 0 < lk["eevee_sat"] <= 1


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

def test_swoop_lifts_the_front_lock_and_turns_it_over():
    """`swoop`: locks rooted at the front hairline near `at` stand higher off the forehead and their tips go over to
    the `sweep` side; locks away from it (the temples) stand as without it."""
    crop = {"length": 0.04, "spacing": 0.01, "stiff": 0.5, "out": 0.1, "lift": 0.001, "body": 0.002, "messy": 0.0,
            "uneven": 0.0, "lay": 0.4}

    def front(loose):
        sc, _col, locks = _grow(loose, parting="none")
        R = np.array([np.asarray(lk["pts"])[0] + sc.C for lk in locks.values()])
        P = [np.asarray(lk["pts"]) + sc.C for lk in locks.values()]
        az, el, _ = sc.coords(R)
        fa = np.abs(((az + 180) % 360) - 180)
        hmax = np.array([sc.coords(Q)[2].max() for Q in P])
        dx = np.array([Q[-1, 0] - Q[0, 0] for Q in P])
        fwd = np.array([Q[0, 1] - Q[:, 1].min() for Q in P])  # how far a lock pokes forward of its root (-y)
        mid = (fa < 12) & (el < np.percentile(el[fa < 12], 30))
        temple = (fa > 50) & (fa < 70) & (el < np.percentile(el[(fa > 50) & (fa < 70)], 30))
        return hmax[mid], dx[mid], hmax[temple], fwd[mid]
    h0, dx0, t0, _ = front(crop)
    h1, dx1, t1, f1 = front({**crop, "swoop": {"span": 30, "depth": 0.03, "rise": 0.4, "sweep": -1.0, "stiff": 0.8}})
    assert f1.max() < 0.003, f1.max()  # the crest rolls back: no cowlick poking forward past the hairline
    assert len(h0) > 2 and len(t0) > 2
    assert np.median(h1) > np.median(h0) + 0.001, (np.median(h0), np.median(h1))  # lifted off the forehead
    assert np.median(dx1) < np.median(dx0) - 0.003, (np.median(dx0), np.median(dx1))  # over to his right (-x)
    assert abs(np.median(t1) - np.median(t0)) < 0.001, (np.median(t0), np.median(t1))  # temples untouched
    try:
        hl.params({"swoop": {"bogus": 1}})
        raise AssertionError("unknown swoop key accepted")
    except ValueError:
        pass


def test_groom_fits_a_smaller_head():
    """groom.fit (the head a groom was made on): on a head 0.88 x the size, metre keys scale by 0.88 (loose lengths,
    volume, hairline offsets, the swoop's depth), traced hairline heights move with the head's centre and scale about
    it, unitless keys stay; the grown hair is shorter by the same share. Without fit nothing changes."""
    sc, col = _ball_head()
    ref = hair.head_ref(sc)
    small = hair.Scalp(sc.C + [0, 0, -0.01], None, {})
    small.R = sc.R * 0.88
    g = hair._merge(hair.GROOM, {"loose": {"length": 0.05, "spacing": 0.009, "swoop": {"depth": 0.04}},
                                 "volume": {"front": 0.01, "across": 0.1},
                                 "hairline": {"temples": 0.01, "front_points": [[0, 1.69], [20, 1.68]]}, "fit": ref})
    f = hair.fit_to_head(g, small)
    assert abs(f["loose"]["length"] - 0.044) < 1e-9 and abs(f["loose"]["spacing"] - 0.00792) < 1e-9
    assert abs(f["loose"]["swoop"]["depth"] - 0.0352) < 1e-9 and abs(f["volume"]["front"] - 0.0088) < 1e-9
    assert f["volume"]["across"] == 0.1 and abs(f["hairline"]["temples"] - 0.0088) < 1e-9
    z0 = sc.C[2]
    assert abs(f["hairline"]["front_points"][0][1] - (z0 - 0.01 + (1.69 - z0) * 0.88)) < 1e-9
    assert "fit" not in f and hair.fit_to_head({**g, "fit": None}, small)["loose"]["length"] == 0.05


def test_carried_groom_keeps_its_hairline_on_the_head():
    """hair.carry stamps groom.fit with the source head: worn on a head whose centre sits 4.4 mm lower (Tess's
    solved head under ts_t28's groom), the traced hairline keeps its elevation, so it stays with the stored locks
    ([az, el, h] about the centre) instead of standing up the brow over them (the bare V, 2026-10-10). A groom
    already fitted keeps its own fit; the source spec isn't changed."""
    sc, _ = _ball_head()
    low = hair.Scalp(sc.C + [0, 0, -0.0044], sc.R.copy(), {})
    groom = {"hairline": {"front_points": [[0, 1.66], [20, 1.659], [35, 1.655]]}}
    src = {"hair": {"groom": groom, "locks": {}}}
    h = hair.carry("src", src, sc=sc)
    assert h["groom"]["fit"] == hair.head_ref(sc) and "fit" not in src["hair"]["groom"]
    as_written = hair.hairline(low, hair._merge(hair.GROOM, groom))
    carried = hair.hairline(low, hair._merge(hair.GROOM, h["groom"]))
    own = hair.hairline(sc, hair._merge(hair.GROOM, groom))
    for a in (0, 20, 35):
        assert abs(carried[a] - own[a]) < 0.3, (a, carried[a], own[a])
        assert as_written[a] - own[a] > 2.0, (a, as_written[a], own[a])  # (the bug: the line climbs ~2.6 deg)
    fitted = {"hair": {"groom": {**groom, "fit": {"r": 0.1, "c": [0, 0, 1.7]}}}}
    assert hair.carry("src", fitted, sc=sc)["groom"]["fit"] == {"r": 0.1, "c": [0, 0, 1.7]}


def test_default_grey_follows_age():
    """lt19b: the default temple / sideburn grey put grey locks on a 19-year-old; it now follows the model's age
    (none to 30, all of it from 50); a groom's own grey and models without an age are unchanged."""
    g19 = hair.groom_params({"base": {"body": {"age": 19}}, "hair": {"groom": {}}})
    assert all(v == 0 for v in g19["grey"].values())
    g60 = hair.groom_params({"base": {"body": {"age": 60}}, "hair": {"groom": {}}})
    assert g60["grey"] == hair.GROOM["grey"]
    g40 = hair.groom_params({"skin": {"age": 40}, "hair": {"groom": {}}})
    assert g40["grey"]["temples"] == pytest.approx(0.5 * hair.GROOM["grey"]["temples"])
    assert hair.groom_params({"hair": {"groom": {}}})["grey"] == hair.GROOM["grey"]
    mine = {"temples": 0.2}
    assert hair.groom_params({"base": {"body": {"age": 19}}, "hair": {"groom": {"grey": mine}}})["grey"]["temples"] == 0.2
    # locks groomed earlier carry their grey: the look's grey_locks default follows age too
    assert hair.look_of({"base": {"body": {"age": 19}}, "hair": {}})["grey_locks"] == 0.0
    assert hair.look_of({"base": {"body": {"age": 19}}, "hair": {"look": {"grey_locks": 0.7}}})["grey_locks"] == 0.7
    assert hair.look_of({"hair": {}})["grey_locks"] == 1.0
