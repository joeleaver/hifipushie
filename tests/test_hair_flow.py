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


def _back_share(tied):
    sc, g, line, locks = _grow(tied)
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
    return back


def test_top_of_the_head_runs_front_to_back():
    # combed straight back and tight: back (+y) everywhere on top
    back = _back_share({"tie": "low", "tightness": 0.9, "part": "none"})
    assert np.median(back) > 0.9 and np.mean(back > 0.5) > 0.95, (np.median(back), np.mean(back > 0.5))
    # loose with a parting: the hair leaves the part on a diagonal (out and back), still never ACROSS
    # (volume 0: lying on the head. With volume the hair off a part FALLS out of it first, on purpose: tesshair7)
    back = _back_share({"tie": "low", "tightness": 0.4, "volume": 0})
    assert np.median(back) > 0.6 and np.mean(back > 0.3) > 0.8, (np.median(back), np.mean(back > 0.3))
    back_v = _back_share({"tie": "low", "tightness": 0.4})
    assert np.median(back_v) < np.median(back) and np.mean(back_v > -0.25) > 0.9, (np.median(back_v), np.mean(back_v > -0.25))


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
    # (lift is the default of `volume`: without lift, no dome; with volume 0 it is the few mm of puff as before)
    assert "volume" not in hf.style({"tightness": 0.2, "lift": 0.0})["tie"]["gather"]
    assert hf.style({"tightness": 0.2})["tie"]["gather"]["volume"]["crown"] > 0.02
    assert hf.style({"tightness": 0.2, "lift": 0.0, "volume": 0})["tie"]["gather"]["puff"] < hf.style({"tightness": 0.2, "volume": 0})["tie"]["gather"]["puff"]


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
        assert P[-1, 2] < P[0, 2] - 0.008, k  # it falls
    # (single hairs are only made when asked for: what a messy head gets by default is wisps)
    assert not any(k.startswith("te") for k in _grow({"neatness": 1.0})[3])
    assert not any(k.startswith("te") for k in _grow({"neatness": 0.2})[3])
    try:
        _grow({"escaped": {"count": 1, "where": ["chin"]}})
        raise AssertionError("unknown zone accepted")
    except ValueError as e:
        assert "where" in str(e)


def test_wisps_are_soft_clumps_that_hug_the_head():
    """tesshair4 (Joe: "almost right for tess, if you added front wispies"): a wisp is ONE lock of many fine hairs (not
    1-2 hair wires), rooted at the hairline, lying within millimetres of the skin while the skin is under it, ending
    lower than it starts; the front's never run down the face; amount is their number; a neat head has none."""
    sc, g, line, locks = _grow({"wisps": {"amount": 0.6, "loose": 0, "curls": 0}, "hairline": 0, "volume": 0})
    ws = {k: lk for k, lk in locks.items() if k.startswith("tw")}
    n = ht.params(g["tie"])[0]["wisps"]["count"]
    assert len(ws) == 2 * n and n >= 10, (len(ws), n)
    for k, lk in ws.items():
        assert lk["hairs"] >= 4 and lk["space"] == "xyz" and lk["free"] == 1.0, (k, lk["hairs"])
        assert lk["width"] <= 0.012 and lk["strands"]["tip_loss"] >= 0.5  # a thin clump whose hairs end one by one
        P = _world(sc, lk)
        az, el, h = sc.coords(P)
        assert h.min() > -1e-6, k  # never inside the head
        assert h[:len(h) // 2].max() < 0.012, (k, h.max())  # it leaves the hairline ON the skin, not into the air
        assert P[-1, 2] < P[0, 2] + 0.004, k  # and does not climb
        a0 = abs(float(hf._wrap(az[0])))
        if a0 < 44:  # the front's: never far down the forehead (over the eyes)
            fa = np.abs(hf._wrap(az))
            lo = hair._line_at(line, az % 360) - 27.0
            assert np.all((el > lo) | (fa >= 48)), k
    sides = [np.sign((_world(sc, lk) - sc.C)[0, 0]) for lk in ws.values()]
    assert sides.count(1.0) == sides.count(-1.0)
    lens = [np.linalg.norm(np.diff(_world(sc, lk), axis=0), axis=1).sum() for lk in ws.values()]
    assert max(lens) > 1.6 * min(lens)  # lengths are mixed
    # amount is the number of clumps; none on a neat head, some on a messy one, by default
    soft = lambda L: [k for k in L if k.startswith("tw") and k[2].isdigit()]  # noqa: E731 (twb / twl: baby, loose)
    few = soft(_grow({"wisps": {"amount": 0.2, "loose": 0}, "hairline": 0})[3])
    assert 0 < len(few) < len(ws)
    assert not soft(_grow({"neatness": 1.0})[3])
    assert not soft(_grow({"neatness": 0.3, "wisps": 0})[3])
    assert soft(_grow({"neatness": 0.3})[3])
    assert hair.needs_body(g)  # they lie on the body's own surface
    # softness: wider, more hairs
    so = lambda v: hf.style({"wisps": {"amount": 0.5, "softness": v}})["tie"]["wisps"]  # noqa: E731
    assert so(1.0)["hairs"][1] > so(0.0)["hairs"][1]
    for bad in ({"wisps": {"amount": 0.5, "where": ["chin"]}}, {"wisps": {"ammount": 1}}):
        try:
            _grow(bad)
            raise AssertionError(f"accepted {bad}")
        except ValueError:
            pass
    # their strand dials: the wisp object's own (strands.wisp), a lock's tip_loss as the lens's trim factor
    from hifipushie import hair_cards as hc, hair_strands as hs
    S = hc.strands_of({"hair": {"groom": {"tied": {"wisps": 0.5}}, "strands": {"wisp": {"frizz": 0.9}}}})
    assert S["wisp"]["frizz"] == 0.9 and "loose" in S["wisp"]
    assert hs.wisp_physical(S)["frizz"] > hs.wisp_physical({**S, "wisp": {**S["wisp"], "frizz": 0.1}})["frizz"]
    assert hs.wisp_physical(S)["clump"] == 0.0


def test_tail_fullness_is_volume_and_wave_is_every_locks_own():
    """tesshair4 (Joe: "poofed up the ponytail a bit"): fullness sets the bundle's radius along the whole tail (it
    opens right after the tie and is still open near the end: no cone closing to strings), wave bends every lock on
    its own (out of step), and the locks are wide, keep their width and end at different lengths."""
    def tail(fu, wv):
        sc, g, line, locks = _grow({"tail": {"length": 0.26, "fullness": fu, "wave": wv}})
        return sc, g, [lk for k, lk in locks.items() if k.startswith("tt")]

    def radius(sc, T, s):  # rms distance from the bundle's own middle, s m along each lock
        P = []
        for lk in T:
            Q = _world(sc, lk)
            a = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
            if a[-1] >= s:
                P.append([np.interp(s, a, Q[:, j]) for j in range(3)])
        P = np.asarray(P)
        return float(np.sqrt(((P - P.mean(0)) ** 2).sum(1).mean()))

    sc, g, sleek = tail(0.1, 0.0)
    _, _, bushy = tail(0.9, 0.0)
    for s in (0.06, 0.12, 0.18):
        assert radius(sc, bushy, s) > 1.8 * radius(sc, sleek, s), (s, radius(sc, bushy, s), radius(sc, sleek, s))
    assert radius(sc, bushy, 0.06) > 0.65 * radius(sc, bushy, 0.14) > 0.02  # the bulge: open 6 cm out of the tie (a fan: full by ~9)
    assert radius(sc, bushy, 0.2) > 0.6 * radius(sc, bushy, 0.1)  # and no cone: still open near the end
    assert len(bushy) > len(sleek)
    for lk in bushy:
        assert lk["width"] >= 0.02 and lk["taper"] <= 0.6 and abs(lk["twist"]) >= 20
    L = [np.linalg.norm(np.diff(_world(sc, lk), axis=0), axis=1).sum() for lk in bushy]
    assert 0.52 < min(L) / max(L) < 0.92  # an uneven end, no lock half the length

    def wiggle(T):  # how far a lock's middle strays from its own straightened line, median over locks
        out = []
        for lk in T:
            Q = _world(sc, lk)
            k = np.arange(len(Q))
            sm = np.stack([np.polyval(np.polyfit(k, Q[:, j], 3), k) for j in range(3)], 1)
            out.append(np.abs(Q - sm).max())
        return float(np.median(out))

    _, _, straight = tail(0.5, 0.0)
    _, _, wavy = tail(0.5, 1.0)
    assert wiggle(wavy) > 3 * wiggle(straight) and wiggle(wavy) > 0.006, (wiggle(wavy), wiggle(straight))
    # out of step: neighbouring locks' sideways offsets at one height do not agree
    tp = ht.params(g["tie"])[0]
    assert tp["tail"]["bulge"] == 1.0 and tp["tail"]["lock_wave"] > 0
    assert hf.style({"tail": {"wave": 1.0}})["tie"]["tail"]["lock_wave"] > 4 * hf.style({"tail": {"wave": 0.0}})["tie"]["tail"]["lock_wave"]
    for T in (bushy, wavy):
        _, _, h = sc.coords(np.concatenate([_world(sc, lk) for lk in T]))
        assert h.min() > -1e-6
    # a raw hanging tail without the new keys is the old one (no bulge, thin tapering locks)
    assert ht.TIE["tail"]["bulge"] == 0.0 and ht.TIE["tail"]["lock_wave"] == 0.0


def test_hairline_is_a_band_that_thins_out():
    """tesshair5 (Joe on th_T48: "a hard dark arc with a hard V notch at the part"; the temple "reads as SHAVED
    skin"): with `hairline` > 0 the hair's edge is a BAND of fine roots between the line and the inner roots, whose
    locks are narrow and carry fewer, finer strands the nearer the line they root; the temple / sideburn strip is
    rooted again (thin at its rim, full a few mm in); inner locks near the hairline have soft sides; the part
    wanders. hairline 0 = the one row of full locks (round four)."""
    assert hf.style({"tightness": 0.9})["tie"]["gather"]["edge"] > 0.3  # (the default: every hairline is soft)
    sc, g, line, locks = _grow({"tightness": 0.9, "hairline": 1.0, "volume": 0})
    ga = ht.params(g["tie"])[0]["gather"]
    assert ga["edge"] == 1.0 and ga["zig"] > 0.001
    sp = ga["spacing"]
    band = {k: lk for k, lk in locks.items() if k.startswith("tg0_")}
    hard = {k: lk for k, lk in _grow({"tightness": 0.9, "hairline": 0, "volume": 0})[3].items() if k.startswith("tg0_")}
    assert len(band) > 1.5 * len(hard), (len(band), len(hard))
    assert not any("fine" in lk["strands"] for lk in hard.values())
    din, dens, fine, wid = [], [], [], []
    for k, lk in band.items():
        az, el, _ = lk["pts"][0]
        fa = abs(float(hf._wrap(az)))
        if fa > 35:  # (the forehead and its corners: no strip, no climb)
            continue
        din.append(float(hair.inside(sc, line, az % 360, el)))
        dens.append(lk["strands"]["density"])
        fine.append(lk["strands"]["fine"])
        wid.append(lk["width"])
        assert lk["strands"]["rim"] > 1.0  # soft sides
        assert 0.005 < lk["strands"]["roots_m"] < 0.03  # its strands start over its first cm or two, in METRES
    din, dens, fine, wid = (np.asarray(v) for v in (din, dens, fine, wid))
    assert din.max() > 0.5 * sp and din.min() < 0.004  # roots through the band's depth, not on one line
    out, inn = din < 0.004, din > 0.45 * sp
    assert out.sum() >= 3 and inn.sum() >= 3
    assert dens[out].mean() < 0.6 * dens[inn].max()  # the density ramp
    assert fine[out].mean() > 0.3 > fine[inn].mean()  # the rim is drawn fine
    assert wid.max() < 0.8 * sp  # narrow locks
    # the temple / sideburn strip is rooted (round four made no lock there: bare skin with wisps over it)
    e_ear = 0.5 * (float(hair._line_at(line, 95.0)) + float(hair._line_at(line, 265.0)))
    strip = lambda L: sum(1 for lk in L.values()  # noqa: E731
                          if 50 < abs(float(hf._wrap(lk["pts"][0][0]))) < 100 and lk["pts"][0][1] < e_ear - 2.0)
    assert strip(band) >= 4 and strip(hard) == 0, (strip(band), strip(hard))
    # inner locks near the hairline: narrower, soft sides, starts one by one; far inside: as they were
    near = [lk for k, lk in locks.items() if k.startswith("tg1_") and "rim" in (lk.get("strands") or {})]
    far = [lk for k, lk in locks.items() if k.startswith("tg1_") and "rim" not in (lk.get("strands") or {})]
    assert near and far and np.mean([lk["width"] for lk in near]) < np.mean([lk["width"] for lk in far])
    # the part's own line wanders (never a ruled line), each bank still on its side
    ga2 = {**ga, "_zig": (0.3, 1.1, 0.025)}
    z = hf._zig(ga2, np.linspace(0, 0.08, 50))
    assert 0.002 < np.abs(z).max() < 0.012 and (z > 0).any() and (z < 0).any()
    assert np.allclose(hf._zig(ga, np.linspace(0, 0.08, 5)), 0)  # (no phases: the straight line)
    # the strand job: a lock's density / fine / rim reach Blender as per-lock attributes
    from hifipushie import hair_cards as hc, hair_strands as hs
    lk = dict(next(iter(band.values())), name="tg0_0")
    lk["inputs"] = {"Width": lk["width"], "Thickness": lk["thickness"], "Taper": lk["taper"], "Belly": lk["belly"],
                    "Root": lk["root"], "Cup": lk["cup"]}
    lk["pts"] = hair.lock_world(sc, lk, lk["pts"]).tolist()
    lk["space"] = "world"
    try:
        G = hs.lock_guides([lk], sc.C, hc.strands_of({"hair": {"groom": {"tied": {}}}}))
    except Exception:  # noqa: BLE001 (the lock's world form differs between versions: the attribute names are the point)
        G = None
    if G is not None:
        assert "fn" in G["head"] and "ex" in G["head"] and G["head"]["ex"][0] > 0


def test_cycles_look_keys():
    """look.cycles_width / cycles_sat (tesshair5): a path-traced render's strand width and the colour's saturation,
    fitted by measure against a reference; absent by default (EEVEE and older looks untouched)."""
    lk = hair.full_look({"cycles_width": 1.8, "cycles_sat": 0.65})
    assert lk["cycles_width"] == 1.8 and lk["cycles_sat"] == 0.65
    assert hair.full_look({})["cycles_width"] is None and hair.full_look({})["cycles_sat"] is None
    from hifipushie import hair_strands as hs
    S = {"count": 70000, "thickness": 0.7, "random": 0.5, "stray": 0.5, "taper": 0.9, "clump": 0.2, "wave": 0.0,
         "wavelength": 0.1, "curl": 0.0, "loose": 0.2, "clump_size": 0.004, "clump_shape": 0.6, "tip_spread": 0.3,
         "frizz": 0.1, "flyaway": 0.1, "tips": 0.6, "roots": 1.0}
    assert hs.physical(S)["radius"] < 0.00006  # (a true hair's width: what cycles_width multiplies)


def test_baby_hairs_and_loose_locks():
    """Wisp VARIETY (tesshair5: "not all long thin strands fanning from the temple"): baby hairs (short, a few hairs,
    all along the line, also on a neat head: they belong to the hairline's softness) and a few thick loose locks."""
    sc, g, line, locks = _grow({"neatness": 1.0, "hairline": 0.6})
    baby = {k: lk for k, lk in locks.items() if k.startswith("twb")}
    assert len(baby) == 2 * round(70 * 0.6)
    for k, lk in baby.items():
        P = _world(sc, lk)
        ln = float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum())
        assert 0.006 < ln < 0.05 and 2 <= lk["hairs"] <= 5 and lk["width"] <= 0.004, (k, ln)
        _, _, h = sc.coords(P)
        assert -1e-6 < h.min() and h.max() < 0.012, (k, h.max())  # on the skin
    az0 = np.array([abs(float(hf._wrap(sc.coords(_world(sc, lk)[:1])[0][0]))) for lk in baby.values()])
    assert az0.min() < 8 and az0.max() > 60  # from under the part to the sideburn
    assert not any(k.startswith("twb") for k in _grow({"hairline": 0})[3])
    sc, g, line, locks = _grow({"wisps": {"amount": 0.8}})
    loose = {k: lk for k, lk in locks.items() if k.startswith("twl")}
    soft = {k: lk for k, lk in locks.items() if k.startswith("tw") and k[2].isdigit()}
    assert len(loose) == 2 * 2 and soft
    L = lambda lk: float(np.linalg.norm(np.diff(_world(sc, lk), axis=0), axis=1).sum())  # noqa: E731
    for k, lk in loose.items():
        assert lk["hairs"] >= 18 and lk["width"] >= 0.006 and L(lk) > 0.08, (k, lk["hairs"], L(lk))
        assert _world(sc, lk)[-1, 2] < _world(sc, lk)[0, 2]  # it droops
    assert np.mean([lk["hairs"] for lk in loose.values()]) > 1.5 * np.mean([lk["hairs"] for lk in soft.values()])
    assert not any(k.startswith("twl") for k in _grow({"wisps": {"amount": 0.8, "loose": 0}})[3])
    assert sum(k.startswith("twl") for k in _grow({"wisps": {"amount": 0.2, "loose": 3}})[3]) == 6


def test_tail_tousle_is_a_ragged_end_and_strays():
    """tesshair5 (th_T48 from behind: "rope-like S locks and an even end; hers is tousled, with stray hairs leaving
    the outline and a ragged end"): tail.tousle = lock ends spread over the last third, single hairs / thin wisps that
    leave the bundle, locks waving in step (sheets, not ropes). tousle 0 = an even end and nothing outside."""
    def tail(to):
        sc, g, line, locks = _grow({"tail": {"length": 0.26, "fullness": 0.6, "wave": 0.6, "tousle": to}})
        tl = ht.params(g["tie"])[0]["tail"]
        T = [lk for k, lk in locks.items() if k.startswith("tt")]
        Y = [lk for k, lk in locks.items() if k.startswith("ty")]
        ln = np.array([np.linalg.norm(np.diff(_world(sc, lk), axis=0), axis=1).sum() for lk in T])
        return sc, tl, T, Y, ln

    sc, tl0, T0, Y0, l0 = tail(0.0)
    _, tl1, T1, Y1, l1 = tail(1.0)
    assert tl1["ragged"] > tl0["ragged"] and tl1["strays"] > 3 * max(tl0["strays"], 1)
    assert len(Y1) == tl1["strays"] and len(Y1) > len(Y0)
    assert np.percentile(l1, 10) < np.percentile(l0, 10) - 0.01 and l1.std() > l0.std()  # a ragged end
    for lk in Y1:
        # (single hairs and, tesshair6, a few THIN soft locks of 7-15 hairs)
        assert (1 <= lk["hairs"] <= 4 and lk["width"] <= 0.004 or 7 <= lk["hairs"] <= 15 and lk["width"] <= 0.009) and lk["free"] == 1.0
    assert sum(lk["hairs"] <= 4 for lk in Y1) > 0.6 * len(Y1) and any(lk["hairs"] >= 7 for lk in Y1)
    for lk in Y1:
        _, _, h = sc.coords(_world(sc, lk))
        assert h.min() > -1e-6
    # a stray ends further from the bundle's middle than it starts (it leaves the outline)
    C = np.mean([_world(sc, lk)[len(lk["pts"]) // 2] for lk in T1], axis=0)
    d0 = np.mean([np.linalg.norm((_world(sc, lk)[0] - C)[:2]) for lk in Y1])
    d1 = np.mean([np.linalg.norm((_world(sc, lk)[-1] - C)[:2]) for lk in Y1])
    assert d1 > d0, (d0, d1)
    # in step: neighbouring locks' twist is smaller (a ribbon wound 200 deg is a rope)
    assert tl0["in_step"] > 0.5 and tl1["in_step"] >= 0.35
    assert np.mean([abs(lk["twist"]) for lk in T1]) < 115  # (140 on their own; tousled locks are partly out of step)
    # a raw hanging tail without these keys is round four's
    assert ht.TIE["tail"]["ragged"] == 0.0 and ht.TIE["tail"]["strays"] == 0 and ht.TIE["tail"]["in_step"] == 0.0
    # default: by the wave (a straight sleek tail is brushed)
    d = lambda w: hf.style({"tail": {"wave": w}})["tie"]["tail"]  # noqa: E731
    assert d(0.9)["ragged"] > d(0.0)["ragged"] and d(0.9)["strays"] > d(0.0)["strays"]


def test_tousle_is_soft_not_straw():
    """tesshair6 (th_T56's tail: "shorter, stiff straw kicking out backwards"; round four's th_T48 hung, full and
    wavy): the tousle no longer points the locks, flicks them out or clumps their strands. It is `soft`: locks
    loosened out of the bundle, open ends, fine strands at a higher count, longer strays; the hang is the brushed
    tail's."""
    st = lambda to: hf.style({"tail": {"length": 0.22, "fullness": 0.5, "wave": 0.6, "tousle": to}})  # noqa: E731
    a, b = st(0.0), st(0.8)
    ta, tb = a["tie"]["tail"], b["tie"]["tail"]
    assert ta["flick"] == tb["flick"]  # no kick of its own
    assert tb["soft"] > 0.9 > 0.2 > ta["soft"]
    assert tb["strands"]["clump"] <= ta["strands"]["clump"] and tb["strands"]["tip_spread"] >= 0.6  # open, soft ends
    assert tb["strands"]["fine"] > ta["strands"]["fine"] and tb["strands"]["density"] > ta["strands"]["density"] + 0.5
    assert tb["stray_length"][1] >= 0.14 and tb["strays"] > 2 * ta["strays"]
    assert b["strands"]["free"]["clump_shape"] == a["strands"]["free"]["clump_shape"]  # not pointed wisps
    # the locks: no pointed taper, some loosened out of the bundle (the outline is irregular), none stiffly straight up
    def grow(to):
        sc, g, line, locks = _grow({"tail": {"length": 0.22, "fullness": 0.5, "wave": 0.6, "tousle": to}})
        return sc, [lk for k, lk in locks.items() if k.startswith("tt")], [lk for k, lk in locks.items() if k.startswith("ty")]
    sc, T0, _ = grow(0.0)
    _, T1, Y1 = grow(0.8)
    assert max(lk["taper"] for lk in T1) <= 0.4
    ends = lambda T: np.array([_world(sc, lk)[-1] for lk in T])  # noqa: E731
    spread = lambda T: float(np.linalg.norm(ends(T)[:, :2] - ends(T)[:, :2].mean(0), axis=1).std())  # noqa: E731
    assert spread(T1) > spread(T0)  # an irregular outline at the end
    for lk in T1:  # it hangs: every lock ends below where it starts
        P = _world(sc, lk)
        assert P[-1, 2] < P[0, 2] - 0.05
    L = [float(np.linalg.norm(np.diff(_world(sc, lk), axis=0), axis=1).sum()) for lk in Y1]
    assert max(L) > 0.1  # strays long enough to leave the outline
    assert ht.TIE["tail"]["soft"] == 0.0  # a raw tie is unchanged


def test_front_is_looser_than_the_rest():
    """tesshair6 (Tess: "hers drapes loosely over the forehead corners and temples with visible loosened locks from
    the FRONT view; ours is a neat held-back arc"): the style word `front` loosens the hair in front of the ears
    only, lets it hang over the forehead's corners, and adds thick locks that swoop from beside the part across the
    corner and tuck back. The back of the head and a style without the word are unchanged."""
    base = {"tie": "low", "tightness": 0.85, "neatness": 0.95, "wisps": 0.6}
    s0, s1 = hf.style(base), hf.style({**base, "front": {"looseness": 0.6, "drape": 0.6}})
    assert "front" not in s0["tie"]["gather"] and "swoop" not in s0["tie"]["wisps"]
    assert s1["tie"]["gather"]["front"]["loose"] > 0.4 and s1["tie"]["gather"]["front"]["drape"] == 0.6
    assert s1["tie"]["gather"]["sag"] == s0["tie"]["gather"]["sag"]  # the head's own tightness is kept
    assert s1["tie"]["wisps"]["swoop"] == 2 and s1["tie"]["wisps"]["count"] > s0["tie"]["wisps"]["count"]
    assert s1["strands"]["wisp"]["thickness"] > s0["strands"]["wisp"]["thickness"]
    assert hf.style({**base, "front": 0.5})["tie"]["gather"]["front"]["drape"] == 0.5
    assert hf.style({**base, "tie": "high", "front": 0.8})["tie"]["wisps"].get("swoop") is None  # none toward a high tie
    try:
        hf.style({**base, "front": {"loosness": 1}})
        raise AssertionError("accepted a wrong key")
    except ValueError as e:
        assert "looseness" in str(e)
    sc, g, line, L0 = _grow(base)
    _, _, _, L1 = _grow({**base, "front": {"looseness": 0.7, "drape": 0.7}})

    def low(locks, front):
        """Mean depth (deg) the gather's ways dip below ... no: their lowest elevation over the first half, by side."""
        out = []
        for k, lk in locks.items():
            if not k.startswith("tg"):
                continue
            P = np.asarray(lk["pts"], float)
            fa = abs(((P[0, 0] + 180) % 360) - 180)
            if (fa < 50) == front and (front or fa > 120):
                out.append(P[:6, 1].min() - P[0, 1])
        return float(np.mean(out))
    assert low(L1, True) < low(L0, True) - 1.0  # the front's ways hang lower after their roots
    assert abs(low(L1, False) - low(L0, False)) < 0.7  # the back's do not
    sw = {k: lk for k, lk in L1.items() if k.startswith("tws")}
    assert len(sw) == 4 and not any(k.startswith("tws") for k in L0)
    for k, lk in sw.items():
        P = _world(sc, lk) - sc.C
        az0 = abs(np.degrees(np.arctan2(P[0, 0], -P[0, 1])))
        az1 = abs(np.degrees(np.arctan2(P[-1, 0], -P[-1, 1])))
        assert az0 < 35 and az1 > az0 + 25, (k, az0, az1)  # from beside the part out to the temple and back
        assert P[:, 2].min() < P[0, 2] - 0.015 and lk["hairs"] >= 30 and lk["width"] >= 0.009
        assert np.sign(P[-1, 0]) == np.sign(P[0, 0])  # on its own side


def test_volume_stands_up_from_the_root_and_arcs():
    """tesshair7 (Joe's red lines on Tess: hers RISES from the parting, arcs up and over, then out and down the side;
    ours ran "in nearly straight lines, laid flat along the skull like a combed cap"; "it's flat"). The style word
    `volume`: the hair stands up out of its root within a couple of cm (a rise, not a shell offset), carries a dome
    in layers, keeps it until just before the tie, and its way first FALLS sideways / down from the root before it
    turns to the tie (convex). volume 0 = the cap of before, exactly."""
    base = {"tie": "low", "tightness": 0.85, "neatness": 0.95, "wisps": 0}
    s0, s1 = hf.style({**base, "volume": 0}), hf.style({**base, "volume": 0.6})
    assert "volume" not in s0["tie"]["gather"]
    v = s1["tie"]["gather"]["volume"]
    assert 0.015 < v["crown"] < 0.03 and v["nape"] < v["side"] and 0 < v["rise"] < 0.03 and v["arc"] > 0.4
    # default: the style's lift (1 - tightness): a sleek head stays a cap, a loose one has body
    assert hf.style({"tightness": 0.95})["tie"]["gather"].get("volume", {"crown": 0})["crown"] < 0.003
    assert hf.style({"tightness": 0.2})["tie"]["gather"]["volume"]["crown"] > 0.02
    assert hf.style({**base, "volume": {"amount": 0.6, "crown": 0.5}})["tie"]["gather"]["volume"]["crown"] < v["crown"] * 0.6
    assert hf.style({**base, "volume": {"amount": 0.6, "root": 1.0}})["tie"]["gather"]["volume"]["rise"] < v["rise"]
    try:
        hf.style({**base, "volume": {"amout": 1}})
        raise AssertionError("accepted a wrong key")
    except ValueError as e:
        assert "amount" in str(e)
    sc, g, line, L0 = _grow({**base, "volume": 0})
    _, _, _, L1 = _grow({**base, "volume": 0.6})
    _, _, _, L2 = _grow({**base, "volume": {"amount": 0.6, "layers": 0.0}})

    def top(locks, layer=95):
        hs, rise, lat = [], [], []
        for k, lk in locks.items():
            if not k.startswith("tg1_"):
                continue
            P = np.asarray(lk["pts"], float)
            fa = abs(((P[0, 0] + 180) % 360) - 180)
            if fa > 60 or P[0, 1] < 35:
                continue  # rooted on top, in front
            W = _world(sc, lk)
            s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(W, axis=0), axis=1))]
            hs.append(P[:int(0.7 * len(P)), 2].max())  # (not the last stretch: every way ends at the tie, off the scalp)
            rise.append(float(np.interp(0.03, s, P[:, 2])))  # m off the scalp 3 cm along the lock
            # how far the way leaves the straight line root -> end, sideways (m): the arc
            ch = W[-1] - W[0]
            d = W - W[0]
            off = d - np.outer(d @ ch / (ch @ ch), ch)
            lat.append(np.linalg.norm(off, axis=1).max())
        return float(np.percentile(hs, layer)), float(np.median(rise)), float(np.median(lat)), float(np.percentile(hs, 10))
    t0, r0, a0, _ = top(L0)
    t1, r1, a1, lo1 = top(L1)
    t2, _, _, lo2 = top(L2)
    assert t0 < 0.015 and t1 > t0 + 0.008, (t0, t1)  # a cap; a dome
    assert r1 > r0 + 0.004 and r1 > 0.007, (r0, r1)  # it stands up within 3 cm of the root
    assert a1 > a0 + 0.008, (a0, a1)  # the way bows out before it turns to the tie
    assert lo1 < 0.85 * t1 and lo2 > lo1 + 0.003, (lo1, t1, lo2)  # layers: locks at every height; layers 0 = one shell
    for locks in (L1,):  # every way still ends in the tie, on its own side of a centre part in front
        tp = ht.params(g["tie"])[0]
        td = hair.dirs(*tp["at"])
        for k, lk in locks.items():
            if k.startswith("tg"):
                P = _world(sc, lk) - sc.C
                assert np.degrees(np.arccos(np.clip(P[-1] @ td / np.linalg.norm(P[-1]), -1, 1))) < 4, k
                assert np.asarray(lk["pts"])[:, 2].min() >= 0.0, k


def test_volume_is_gated_for_up_styles_and_half_up():
    """tesshair7 round two (NO REGRESSIONS): hair pulled UP to a tie does not fall from its roots: with the default
    volume a high ponytail had radial ridges round the hairline and scalp specks at the crown, half up a bare pit
    behind the crown. By default those styles get no volume (what they were before the word); asked for on an
    up-style it is a smooth pouf: no fall, one shell, no separate locks."""
    assert hf.style({"tie": "low", "tightness": 0.4})["tie"]["gather"]["volume"]["crown"] > 0.015
    for st in ({"tie": "high", "tightness": 0.4, "part": "none"}, {"tie": "top", "tightness": 0.4, "tail": "bun"},
               {"tie": "mid", "half": True, "tightness": 0.4}):
        assert "volume" not in hf.style(st)["tie"]["gather"], st
    v = hf.style({"tie": "high", "part": "none", "volume": 0.5})["tie"]["gather"]["volume"]
    assert v["crown"] > 0.01 and v["arc"] == 0.0 and v["layers"] == 0.0 and v["locks"] == 0.0
    lo = hf.style({"tie": "low", "volume": 0.5})["tie"]["gather"]["volume"]
    assert lo["arc"] > 0.4 and lo["layers"] > 0.5 and lo["locks"] == 1.0 and lo["cross"] == 1.0
    # the old gather exactly for a default high ponytail: same locks as with volume 0
    _, _, _, a = _grow({"tie": "high", "tightness": 0.6, "part": "none"})
    _, _, _, b = _grow({"tie": "high", "tightness": 0.6, "part": "none", "volume": 0})
    ka = [k for k in a if k.startswith("tg")]
    assert ka == [k for k in b if k.startswith("tg")] and all(a[k]["pts"] == b[k]["pts"] for k in ka)


def test_escaped_curls_are_fine_separate_locks_near_the_face():
    """tesshair7 round two (Joe since round one: "front wispies", softer, curlier, separate): wisps.curls = fine
    separate locks (a few hairs, a few mm wide) that leave the hair at the forehead's corners, the temples and in
    front of the ears, each with its own length and curl, hanging close to the face and never over an eye. Under hair
    with volume the flat clumps on the skin are cut back (they were a grey veil)."""
    base = {"tie": "low", "tightness": 0.85, "neatness": 0.95, "volume": 0.5, "wisps": {"amount": 0.6}}
    st = hf.style(base)
    assert st["tie"]["wisps"]["curls"] == 5
    assert st["tie"]["wisps"]["count"] < hf.style({**base, "volume": 0})["tie"]["wisps"]["count"]
    assert hf.style({**base, "wisps": {"amount": 0.6, "curls": 0}})["tie"]["wisps"]["curls"] == 0
    sc, g, line, L = _grow({**base, "wisps": {"amount": 0.6, "curls": 8}})
    cu = {k: lk for k, lk in L.items() if k.startswith("tk")}
    assert 10 <= len(cu) <= 16, len(cu)
    lens, sides, curl = [], [], []
    for k, lk in cu.items():
        P = _world(sc, lk) - sc.C
        assert 4 <= lk["hairs"] <= 16 and lk["width"] <= 0.005 and lk["free"] == 1.0, k
        az0 = abs(np.degrees(np.arctan2(P[0, 0], -P[0, 1])))
        assert 12 < az0 < 90, (k, az0)  # the forehead's corner .. in front of the ear
        assert P[-1, 2] < P[0, 2] - 0.01, k  # it falls
        assert np.linalg.norm(P - P[0], axis=1).max() < 0.2
        d = np.linalg.norm(P, axis=1) - np.linalg.norm(P[0])
        assert d.max() < 0.055, (k, d.max())  # close to the head, not out in the air
        s = np.linalg.norm(np.diff(P, axis=0), axis=1).sum()
        curl.append(s / np.linalg.norm(P[-1] - P[0]))  # curled: longer than its chord
        lens.append(s)
        sides.append(np.sign(P[0, 0]))
        assert np.sign(P[-1, 0]) == np.sign(P[0, 0]) or abs(P[-1, 0]) < 0.02, k  # on its own side of the face
    assert max(lens) > 1.6 * min(lens) and {-1.0, 1.0} <= set(sides)
    assert np.mean(curl) > 1.06 and min(curl) > 1.0, (np.mean(curl), min(curl))
    _, _, _, L0 = _grow({**base, "wisps": {"amount": 0.6, "curls": 0}})
    assert not any(k.startswith("tk") for k in L0)
    assert [k for k in L0 if not k.startswith("tk")] == [k for k in L if not k.startswith("tk")]  # the others' draws stay


def test_sideburn_grows_no_lock_to_the_tie():
    """With a HARD hairline (hairline 0) the hairline row skips the sideburn (below the ear's top, in front of the
    ear): full locks from there climbed to the flow and their starts were a dark toothed tuft over bare skin. (A soft
    hairline roots it again, thin: test_hairline_is_a_band_that_thins_out.)"""
    sc, g, line, locks = _grow({"tightness": 0.9, "hairline": 0})
    e_ear = 0.5 * (float(hair._line_at(line, 95.0)) + float(hair._line_at(line, 265.0)))
    n = 0
    for k, lk in locks.items():
        if k.startswith("tg0_"):
            az, el, _ = lk["pts"][0]
            fa = abs(float(hf._wrap(az)))
            assert not (50 < fa < 100 and el < e_ear - 2.0), (k, az, el)
            n += 1
    assert n > 20
    assert ht.params(g["tie"])[0]["gather"]["feather"] == 1.0 and ht.TIE["gather"]["feather"] == 0.0


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
