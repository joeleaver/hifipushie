"""Tied hair: hair gathered over the head to a tie point, then whatever leaves the tie (a free tail under gravity, a
coil = a bun, a plait), plus the strands that escaped the tie. One general capability, `groom.tie` (or a list of
them: bunches):

  {"at": [az, el],          where on the head the tie sits (180, 25 = the back, above the occiput)
   "out": 0.025,            m the tie stands off the scalp
   "gather": {"rows": 3, "locks": 30, "lift": 0.012, "width": 0.05, "uneven": 0.4, "from": [az0, az1]?,
              "toward": "tie", "reach": 0.75,   (where the inner rows root: "tie" = on the way from the hairline
                            to the tie (rings round a tie on the back of the head), "crown" = on the way to the top
                            of the head (a LOW or off-centre tie: rows toward it leave the far side of the top bare);
                            reach = how far along that way the innermost row gets, x (rows - 1) / rows)
              "hairline_strands": {dial: value}?,  the hairline row's own strand dials over `strands` (it alone lies
                            over bare skin at the temples: e.g. {"density": 2, "clump": 0})
              "ride": 0.003,        m each row rides over the next one in (the hairline row on top)
              "inner_roots": null,  the strand dial `roots` for the rows inside the hairline (0 = their strands all
                            start at the lock's root: staggered like the hairline row's they are stubble on the crown)
              "strands": {dial: value}?},  (strand dials for the gathered hair alone, e.g. a loose texture on top:
                            {"wave": 0.02, "wavelength": 0.06, "random": 0.8})
                            the scalp hair: rows of locks from the hairline (row 0, on top) inward, each running
                            over the head to the tie; lift = m of looseness between root and tie; false = none
   "tail": {"length": 0.3, "fullness": 0.045, "locks": 16, "stiff": 0.45, "dir": [x, y, z]?, "uneven": 0.4,
            "coil": 0, "coil_radius": 0.03, "plait": false, "taper": 0.5, "strands": {dial: value}?},
                            what leaves the tie: locks round a core line that starts along `dir` (default: out of the
                            head and down) and bends to gravity (stiff 0 = hangs at once, 1 = stands out straight);
                            fullness = the tail's radius at its fullest; coil = turns of the core wound round the tie
                            (a bun); plait = three strands crossing; false = none (a knot);
                            sway = m the tail's AXIS swings side to side (a slow S every sway_length m: big soft waves
                            of the whole tail; strand / lock waves only crimp it); flick = m the locks' ends turn out
                            of the tail (flicked tips, each lock its own amount)
   "escape": 6,             strands that never reached the tie: they fall from the temples and nape
   "curtain": {"span": 70, "to": 80, "over": 10, "lift": 0.006}?
                            the front hair from a soft part sweeps DOWN AND OUT over the temples like curtains, rounds
                            over the ears' tops and only then turns back to the tie: first-row gather locks rooted within
                            `span` deg of the front pass through a waypoint over the ear's top (azimuth `to` on their own
                            side, elevation `over`, deg from the head centre; locks rooted further back pass higher);
                            `lift` = m of extra rise at the part (soft, no bare furrow); `along` = deg the lock first
                            runs sideways at its root's height (hair lying across from the part over the forehead's top
                            before it falls: without it the two curtains diverge in a V that bares the scalp);
                            `drape` = deg BEHIND the hairline the first row roots (x the lock's closeness to the part):
                            the lock still runs along the line, so it arcs forward over the band between (hair falling
                            from a soft part over the forehead's corners; rooted on the line, the first row's strands
                            fanned apart and bared a V under the part: Tess, 2026-10-10); `dip` = deg BELOW the hairline
                            that run passes (the drape lying over the forehead's top); `sag` = deg the run on to the
                            ear's top hangs below its great circle at its middle (x closeness to the part): the hair
                            lower over the temples, the forehead a rounder arch instead of a peak under the part
                            (faces3, Tess 2026-10-10). `arch` = deg the run over the forehead is RAISED for locks
                            rooted `arch_at` deg from the part (none at the part, none past 2 x arch_at): rounds a
                            pointed forehead's upper corners without lifting its centre; `smooth` = rounds of smoothing of the way (its arcs meet
                            at corners: ridges in front of the ear); `rows` = how many rows from the hairline in take the way
                            over the ear (each a little less; 1 = the hairline row alone). "left" / "right": {key: value}
                            for that side only (the person's left = +x): an asymmetric style. Default none: every
                            lock runs the great circle to the tie.
   "frame": {"count": 3, "az": [40, 95], "length": [0.07, 0.15], "width": [0.008, 0.014], "wave": 0.014,
             "wavelength": 0.075}?
                            face-framing pieces a side: soft separate wavy locks that fall from the temples and in front
                            of the ears, of mixed lengths (styled, not strays); count may be [right, left]; default none.
                            `hairs`: n > 0 = each piece is 1..n SINGLE hairs (their own strand object) instead of a lock
                            (a lock is never under ~8 strands side by side: a comb strip): loose hairs beside the face,
                            many pieces of 1-3 hairs, width 1-3 mm; `curve`: 0..0.3, how far a piece bows off its
                            line, x its length, each in its own plane with a slow S (0 = hangs straight);
                            `strands`: {dial: value} over the pieces' own dials (hair_tied.FRAME_STRANDS)
   "band": 0.006}           the tie itself: a ring this thick round the tail's start (0 = none)

Locks on the head are ordinary [az, el, h] locks; the tail and the escaped strands leave the head, so they are
"space": "xyz" locks (metres from the head centre) with `free` 1 and, for the tail, `core` (its own axis: the cards'
outward side and bent normals come from it, not from the head centre).
"""

from __future__ import annotations

import numpy as np

TIE = {"at": [180.0, 25.0], "out": 0.025, "escape": 6, "band": 0.006, "curtain": None, "frame": None, "escaped": None,
       "gather": {"rows": 3, "locks": 30, "lift": 0.012, "width": 0.05, "uneven": 0.4, "toward": "tie", "reach": 0.75, "ride": 0.003,
                  "inner_roots": None,
                  # mode "flow" (hair_flow.gather; the keys below are its own)
                  "mode": "rows", "spacing": 0.02, "body": 0.008, "puff": 0.008, "root_lift": 0.004, "sag": 0.15,
                  "part_push": 0.9, "part_length": 0.07, "overhang": 0.0, "ears": 0.0, "above": None},
       "tail": {"length": 0.3, "fullness": 0.045, "locks": 16, "stiff": 0.45, "uneven": 0.4, "coil": 0.0,
                "coil_radius": 0.03, "plait": False, "taper": 0.5, "sway": 0.0, "sway_length": 0.16, "flick": 0.0,
                "hang": False, "spread": 0.35}}
ESCAPED = {"count": 6, "where": ["temple", "ear"], "length": [0.06, 0.14], "hairs": [3, 7], "curve": 0.2,
           "wave": 0.008, "wavelength": 0.09, "strands": None}
ESCAPED_AT = {"part": (4.0, 20.0), "temple": (44.0, 66.0), "ear": (66.0, 92.0), "nape": (140.0, 176.0)}
ESCAPED_STRANDS = {"flyaway": 0.0, "clump": 0.0, "tip_spread": 0.3, "flat": 1.0, "loose": 0.8, "frizz": 0.3, "curl": 0.0}
CURTAIN = {"span": 70.0, "to": 80.0, "over": 10.0, "lift": 0.006, "along": 0.0, "hug": 0.0, "drape": 0.0, "dip": 0.0,
           "sag": 0.0, "rows": 1, "arch": 0.0, "arch_at": 25.0, "smooth": 0, "left": None, "right": None}
FRAME = {"count": 3, "az": [40.0, 95.0], "length": [0.07, 0.15], "width": [0.008, 0.014], "wave": 0.014,
         "wavelength": 0.075, "hairs": 0, "curve": 0.0, "strands": None}
# a face-framing piece's strand dials unless frame.strands says otherwise (a round wisp: flat, its few strands were
# a comb)
FRAME_STRANDS = {"flyaway": 0.25, "curl": 0.0, "clump": 0.3, "tip_spread": 0.7, "flat": 3.0}
DOWN = np.array([0.0, 0.0, -1.0])


def _unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def params(tie) -> list:
    """The groom's tie(s) with defaults filled in; unknown keys are refused."""
    out = []
    for t in (tie if isinstance(tie, list) else [tie]):
        bad = set(t) - set(TIE)
        if bad:
            raise ValueError(f"hair tie: unknown keys {sorted(bad)} (have {', '.join(sorted(TIE))})")
        p = {**TIE, **t}
        for k, keys in (("curtain", CURTAIN), ("frame", FRAME), ("escaped", ESCAPED)):
            if p[k]:
                bad = set(p[k]) - set(keys)
                if bad:
                    raise ValueError(f"hair tie {k}: unknown keys {sorted(bad)} (have {', '.join(sorted(keys))})")
                p[k] = {**keys, **p[k]}
        for k in ("gather", "tail"):
            if t.get(k) is False or t.get(k) == 0:
                p[k] = None
                continue
            bad = set(t.get(k) or {}) - set(TIE[k]) - {"dir", "from", "strands", "hairline_strands"}
            if bad:
                raise ValueError(f"hair tie {k}: unknown keys {sorted(bad)} (have {', '.join(sorted(TIE[k]))})")
            p[k] = {**TIE[k], **(t.get(k) or {})}
        out.append(p)
    return out


def _ss_t(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _slerp(a, b, t):
    a, b = _unit(a), _unit(b)
    w = np.arccos(np.clip(float(a @ b), -1, 1))
    if w < 1e-5:
        return np.repeat(a[None], len(t), 0)
    t = np.asarray(t, float)[:, None]
    return (np.sin((1 - t) * w) * a + np.sin(t * w) * b) / np.sin(w)


def _clear(sc, P, gap):
    """Points pushed out to at least `gap` m over the head (where the head's rays reach)."""
    from .hair import dirs
    az, el, h = sc.coords(P)
    need = np.maximum(np.asarray(gap, float) - h, 0.0) * (el > sc.EL[0] + 3)
    return P + need[:, None] * dirs(az, el)


def core_line(sc, tp: dict, tl: dict, n: int = 14):
    """The tail's axis from the tie: it leaves along `dir`, turns to gravity as fast as `stiff` lets it, and stays
    clear of the head by the tail's own radius. With `coil`, the axis winds round the tie's own direction instead."""
    from .hair import dirs
    az, el = tp["at"]
    out = dirs(az, el)
    P0 = sc.point(az, el, float(tp["out"]))
    L = float(tl["length"])
    d = _unit(np.asarray(tl["dir"], float)) if tl.get("dir") is not None else _unit(0.7 * out + DOWN * 0.6)
    turns = float(tl.get("coil", 0.0))
    if turns > 0:  # a bun: the hair wound round the tie
        e1 = _unit(np.cross(out, [0, 0, 1.0]))
        e2 = np.cross(out, e1)
        r = float(tl["coil_radius"])
        t = np.linspace(0, 1, max(n, int(turns * 10)))
        ang = 2 * np.pi * turns * t
        rr = r * (0.35 + 0.65 * np.minimum(t * 3, 1.0)) * (1 - 0.35 * t)
        return P0 + rr[:, None] * (np.cos(ang)[:, None] * e1 + np.sin(ang)[:, None] * e2) + (0.012 * np.sin(np.pi * t))[:, None] * out
    ds = L / (n - 1)
    P = [P0]
    k = (1 - float(tl["stiff"])) ** 2 * 45.0  # how fast the direction falls, per metre
    for i in range(n - 1):
        d = _unit(d + k * ds * DOWN)
        q = _clear(sc, (P[-1] + ds * d)[None], float(tl["fullness"]) * 0.9 + 0.006)[0]
        d = _unit(q - P[-1])
        P.append(P[-1] + ds * d)
    return np.asarray(P)


def _transport(K):
    """Two unit vectors across a polyline, carried along it without twisting."""
    T = _unit(np.gradient(K, axis=0))
    e = np.cross(T[0], [1.0, 0, 0])
    if np.linalg.norm(e) < 0.3:
        e = np.cross(T[0], [0, 1.0, 0])
    E1 = [_unit(e)]
    for i in range(1, len(K)):
        v = E1[-1] - (E1[-1] @ T[i]) * T[i]
        E1.append(_unit(v))
    E1 = np.asarray(E1)
    return T, E1, np.cross(T, E1)


def _xyz(sc, P):
    return [[round(float(v), 4) for v in p] for p in np.asarray(P) - sc.C]


def grow(sc, g: dict, line, rng, col=None) -> dict:
    """{name: lock} for the groom's tie(s). `col`: the body's collider (hair_loose.Collider): a hanging tail and
    escaped locks lie on the neck and shoulders by it (without one: the scalp's rays, the head alone)."""
    from . import hair_flow
    from .hair import _line_at, az_el, dirs, inside
    locks = {}
    for ti, tp in enumerate(params(g["tie"])):
        pre = f"t{ti}" if ti else "t"
        az0, el0 = tp["at"]
        tie_dir = dirs(az0, el0)
        ga = tp["gather"]
        if ga and str(ga.get("mode", "rows")) == "flow":
            locks.update(hair_flow.gather(sc, g, tp, ga, line, rng, pre))
        elif ga:
            rows, n = int(ga["rows"]), int(ga["locks"])
            un = float(ga["uneven"])
            a0, a1 = ga.get("from") or (0.0, 360.0)
            for r in range(rows):
                nr = max(4, int(round(n * (1 - 0.25 * r) / sum(1 - 0.25 * q for q in range(rows)))))
                f = r / rows * float(ga.get("reach", 0.75))
                # where the inner rows root: on the way to the tie (a tie high on the back of the head: every row is
                # a ring round it), or on the way to the CROWN (a low or off-centre tie: rows toward it all root on
                # the tie's side and leave the far side of the top bare but for the first row, which then lies round
                # the hairline like a headband: Tess, 2026-10-11)
                inner = dirs(0.0, 90.0) if str(ga.get("toward", "tie")) == "crown" else tie_dir
                for i in range(nr):
                    az = a0 + (a1 - a0) * (i + 0.5 * (r % 2) + un * rng.uniform(-0.3, 0.3)) / nr
                    el = float(_line_at(line, az)) + 1.5
                    for _ in range(4):  # (a steep stretch of the line: up until it is inside the hair)
                        if float(inside(sc, line, az, el)) >= 0.003:
                            break
                        el += 4.0
                    cu = tp.get("curtain")
                    azw = ((az + 180.0) % 360.0) - 180.0  # -180..180, 0 = the front (the part)
                    if cu:  # the side's own values over the shared ones (+x = the person's left)
                        cu = {**cu, **(cu.get("left" if azw >= 0 else "right") or {})}
                    cw = float(np.clip(1.0 - abs(azw) / float(cu["span"]), 0.0, 1.0)) if cu else 0.0
                    if cw > 0 and r == 0:  # the drape: rooted behind the line, arcing forward over it
                        el += float(cu.get("drape", 0.0)) * cw
                    root = _slerp(dirs(az, el), inner, [f])[0]
                    # (curtain.rows: how many rows take that way round, each further in a little less: with the
                    # hairline row alone it lies on the rest as a band, a rolled headband over the temple)
                    crows = max(int(cu.get("rows", 1)), 1) if cu else 1
                    route = cw > 0 and r < crows
                    cwr = cw * (1.0 - r / crows)
                    if route:
                        # down and out to its own side over the temple, round the ear's top, then back to the tie
                        sd = 1.0 if azw >= 0 else -1.0
                        ra, re = az_el(root)
                        raw = ((float(ra) + 180.0) % 360.0) - 180.0
                        way = dirs(sd * max(abs(raw) + 10.0, float(cu["to"])),
                                   float(cu["over"]) + (float(re) - float(cu["over"])) * (1.0 - cwr) * 0.5)
                        al = float(cu.get("along", 0.0)) * cw * (r == 0)
                        if al > 0:  # sideways at the root's height first, then down to the ear's top, then back
                            # (just inside the hairline there: it runs over the forehead's corner, not above it)
                            # (arch: the run RAISED over the forehead's corners only, most for locks rooted arch_at
                            # deg from the part, nothing at the part or past 2 x arch_at: a round arch. A negative dip
                            # does it for every lock by its closeness to the part: the corners closed, but the centre
                            # rose 4 mm and bared a notch under the part: Tess, 2026-10-11)
                            bump = float(np.sin(np.pi * np.clip(abs(azw) / (2.0 * max(float(cu.get("arch_at", 25.0)), 1.0)), 0.0, 1.0)))
                            mid = dirs(float(ra) + sd * al, min(float(re), float(_line_at(line, float(ra) + sd * al)) + 3.0
                                                               - float(cu.get("dip", 0.0)) * cw
                                                               + float(cu.get("arch", 0.0)) * bump))
                            t = np.linspace(0, 1, 11)
                            k0, k1 = 0.25, 0.5
                            D = np.concatenate([_slerp(root, mid, t[t <= k0] / k0),
                                                _slerp(mid, way, (t[(t > k0) & (t <= k1)] - k0) / (k1 - k0)),
                                                _slerp(way, tie_dir, (t[t > k1] - k1) / (1 - k1))])
                            s_run = np.where((t > k0) & (t <= k1), (t - k0) / (k1 - k0), 0.0)
                        else:
                            t = np.linspace(0, 1, 9)
                            k1 = 0.4
                            D = np.concatenate([_slerp(root, way, t[t <= k1] / k1),
                                                _slerp(way, tie_dir, (t[t > k1] - k1) / (1 - k1))])
                            s_run = np.where(t <= k1, t / k1, 0.0)
                        sag = float(cu.get("sag", 0.0)) * cwr * np.sin(np.pi * s_run)
                        for _ in range(int(cu.get("smooth", 0))):  # the way is three arcs: round off where they
                            # meet (each corner drew as a ridge: finger waves in front of the ear)
                            D[1:-1] = _unit(0.25 * D[:-2] + 0.5 * D[1:-1] + 0.25 * D[2:])
                    else:
                        t = np.linspace(0, 1, 7)
                        D = _slerp(root, tie_dir, t)
                    aa, ee = az_el(D)
                    if route:
                        ee = ee - sag
                    lift = float(ga["lift"]) * (1 + un * rng.uniform(-0.5, 0.8))
                    hb = 0.002 + float(ga.get("ride", 0.003)) * (rows - 1 - r)
                    h = (1 - t ** 3) * (hb * np.minimum(t * 6, 1) + lift * np.sin(np.pi * t)) + t ** 3 * float(tp["out"]) * 0.8
                    if cw > 0:  # a soft part: the hair rises at it and falls away (no bare furrow)
                        # ...and the curtain lies DOWN where it leaves the hairline: the row's own height (8 mm on the
                        # first of three rows) stood its front edge off the forehead as a frayed rim (Tess, 2026-10-09)
                        hug = float(cu.get("hug", 0.0))
                        if hug > 0 and r == 0:
                            h = h * (1.0 - hug * cw * (1.0 - _ss_t(t / 0.6)))
                        h = h + float(cu["lift"]) * cw * np.sin(np.pi * np.minimum(t / 0.5, 1.0)) * (1 - t)
                    aa = aa + un * 2.0 * np.sin(np.pi * t) * rng.uniform(-1, 1)
                    locks[f"{pre}g{r}_{i}"] = {
                        "tier": "tie", "pts": [[round(float(aa[j]), 2), round(float(ee[j]), 2), round(float(h[j]), 4)]
                                               for j in range(len(t))],
                        "width": round(float(ga["width"]) * (1 + un * rng.uniform(-0.3, 0.3)), 4), "thickness": 0.004,
                        "taper": 0.6, "belly": 0.45, "root": 0.8, "cup": 0.003,
                        **({"strands": dict(ga["strands"])} if ga.get("strands") else {})}
                    if ga.get("hairline_strands") and r == 0:  # the hairline row's own dials over `strands`: it is
                        # the one row that lies over bare skin (forehead corners, temples): thin there, its sub
                        # clumps drew as contour lines on the skin (density 2, clump 0)
                        locks[f"{pre}g{r}_{i}"]["strands"] = {**(ga.get("strands") or {}), **ga["hairline_strands"]}
                    if ga.get("inner_roots") is not None and r > 0:  # rows inside the hairline: their strands'
                        # starts are not staggered along the lock like the hairline row's (a soft hairline): inside
                        # the hair they are stubble on the crown
                        locks[f"{pre}g{r}_{i}"].setdefault("strands", {})["roots"] = float(ga["inner_roots"])
        tl = tp["tail"]
        P0 = sc.point(az0, el0, float(tp["out"]))
        if tl and tl.get("hang") and not float(tl.get("coil", 0.0)) > 0 and not tl.get("plait"):
            locks.update(hair_flow.tail(sc, tp, tl, rng, col, pre, P0))
        elif tl:
            K = core_line(sc, tp, tl)
            T, E1, E2 = _transport(K)
            s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(K, axis=0), axis=1))]
            sway = float(tl.get("sway", 0.0))
            if sway > 0 and not float(tl.get("coil", 0.0)) > 0:
                # the whole tail swings: its axis a slow S (one big soft wave every sway_length m, growing from the
                # tie), every lock with it. Waves on the locks or strands alone only crimp a straight tail
                K = core_line(sc, tp, tl, n=28)
                T, E1, E2 = _transport(K)
                s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(K, axis=0), axis=1))]
                ph0 = rng.uniform(0, 2 * np.pi)
                env = _ss_t(s / 0.05)
                lam = max(float(tl.get("sway_length", 0.16)), 0.02)
                K = K + (sway * env * np.sin(2 * np.pi * s / lam + ph0))[:, None] * E1 \
                    + (0.5 * sway * env * np.sin(2 * np.pi * s / (lam * 1.37) + ph0 + 1.3))[:, None] * E2
                K[1:] = _clear(sc, K[1:], float(tl["fullness"]) * 0.5 + 0.006)  # (the tie stays where it is)
                T, E1, E2 = _transport(K)
                s = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(K, axis=0), axis=1))]
            n = int(tl["locks"])
            full, un = float(tl["fullness"]), float(tl["uneven"])
            r_tie = min(0.012, full * 0.4)
            core = _xyz(sc, K)
            coil = float(tl.get("coil", 0.0)) > 0
            for k in range(n):
                if tl.get("plait"):
                    th0, rho = 2 * np.pi * (k % 3) / 3, 0.75
                else:
                    th0, rho = k * 2.39996, np.sqrt((k + 0.5) / n)
                ln = 1 - un * rng.uniform(0, 0.4) * (0.3 if coil else 1.0)
                t = np.linspace(0, 1, 17 if (sway > 0 or float(tl.get("flick", 0.0)) > 0) else 9)
                sk = t * ln * s[-1]
                C = np.stack([np.interp(sk, s, K[:, j]) for j in range(3)], 1)
                e1 = np.stack([np.interp(sk, s, E1[:, j]) for j in range(3)], 1)
                e2 = np.stack([np.interp(sk, s, E2[:, j]) for j in range(3)], 1)
                tt = t * ln
                R = r_tie + (full - r_tie) * np.sin(np.pi / 2 * np.minimum(tt / 0.4, 1.0)) * (1 - float(tl["taper"]) * tt ** 2)
                if coil:
                    R = np.full(len(t), full * 0.45)
                th = th0 + (2 * np.pi * 1.5 * tt * s[-1] / 0.12 if tl.get("plait") else un * rng.uniform(-0.6, 0.6) * tt)
                P = C + (R * rho)[:, None] * (np.cos(th)[:, None] * e1 + np.sin(th)[:, None] * e2)
                P = P + un * 0.006 * rng.normal(0, 1, (len(t), 3)) * tt[:, None]
                fl = float(tl.get("flick", 0.0))
                if fl > 0:  # the lock's end turns out of the tail (and a little up): a flicked tip, each its own
                    rad = np.cos(th)[:, None] * e1 + np.sin(th)[:, None] * e2
                    P = P + (fl * rng.uniform(0.3, 1.0) * (0.3 + rho) * _ss_t((tt - 0.6) / 0.4) ** 2)[:, None] * (rad + [0.0, 0.0, 0.35])
                P[0] = P0 + 0.5 * (P[0] - P0)
                w = full * (3.0 if coil else 2.2) / np.sqrt(max(n, 1)) * (1 + un * rng.uniform(-0.25, 0.35))
                locks[f"{pre}t{k}"] = {"tier": "tie", "space": "xyz", "pts": _xyz(sc, _clear(sc, P, 0.004)),
                                      "core": core, "free": 1.0, "width": round(float(max(w, 0.012)), 4),
                                      "thickness": 0.005, "taper": 0.25 if coil else 0.6, "belly": 0.4, "root": 0.5,
                                      "cup": 0.0, **({"strands": dict(tl["strands"])} if tl.get("strands") else {})}
        for k in range(int(tp.get("escape") or 0)):  # strands the tie missed: out of the hairline, then down
            side = 1 if k % 2 == 0 else -1
            az = (side * rng.choice([52, 68, 84, 150], p=[0.3, 0.3, 0.2, 0.2]) + rng.uniform(-6, 6)) % 360
            el = float(_line_at(line, az)) + 4.0
            for _ in range(8):  # its root is IN the hair, a good 8 mm inside the line (at 2.5 degrees over a steep
                # sideburn or by the ear the root lay on bare skin: a wisp that started on the cheek)
                if float(inside(sc, line, az, el)) >= 0.008:
                    break
                el += 3.0
            p = sc.point(az, el, 0.002)
            # out of the hairline a little, then down along the face: it falls beside the cheek, a few mm off it
            # (leaving the head at 45 degrees, four of them a side stood out as tufts)
            d = _unit(dirs(az, el) * 0.22 + np.array([0.0, -0.25 * abs(np.sin(np.radians(az))), -0.5]))
            ln = rng.uniform(0.06, 0.15)
            P = [p]
            for _ in range(6):
                d = _unit(d + 0.6 * DOWN)
                P.append(_clear(sc, (P[-1] + d * ln / 6)[None], 0.004)[0])
            locks[f"{pre}s{k}"] = {"tier": "tie", "space": "xyz", "pts": _xyz(sc, P), "free": 1.0,
                                  "width": round(float(rng.uniform(0.006, 0.014)), 4), "thickness": 0.002,
                                  "taper": 0.8, "belly": 0.3, "root": 0.5, "cup": 0.0,
                                  "strands": {"layers": 2, "flyaway": 0.6, "curl": 0.0}}
        if tp.get("escaped"):
            locks.update(hair_flow.escaped(sc, tp, tp["escaped"], line, rng, col, pre))
        fm = tp.get("frame")
        cnt = (fm["count"] if isinstance(fm["count"], (list, tuple)) else [fm["count"]] * 2) if fm else [0, 0]
        cnt = [int(c) for c in cnt]  # [right, left]
        jobs = [(sd, j) for j in range(max(cnt)) for sd in (1, -1) if j < cnt[1 if sd > 0 else 0]]
        for k, (side, j) in enumerate(jobs):  # face-framing pieces: styled, soft, wavy, mixed lengths
            nside = cnt[1 if side > 0 else 0]
            a0f, a1f = fm["az"]
            az = (side * (a0f + (a1f - a0f) * (j + rng.uniform(0.2, 0.8)) / nside)) % 360
            el = float(_line_at(line, az)) + 3.0
            for _ in range(8):
                if float(inside(sc, line, az, el)) >= 0.006:
                    break
                el += 3.0
            p = sc.point(az, el, 0.003)
            # out of the hairline a little, forward of the ear, then down beside the face
            d = _unit(dirs(az, el) * 0.3 + np.array([0.0, -0.2, -0.5]))
            l0, l1 = fm["length"]
            ln = l0 + (l1 - l0) * ((j + rng.uniform(0, 1)) / nside)
            P = [p]
            for _ in range(8):
                d = _unit(d + 0.5 * DOWN)
                P.append(_clear(sc, (P[-1] + d * ln / 8)[None], 0.005)[0])
            w0, w1 = fm["width"]
            hairs = int(fm.get("hairs") or 0)
            cv = float(fm.get("curve") or 0.0)
            if cv > 0:  # its own bend: bowed out from the face and back (a C), with a slow S along it; each piece
                # in its own plane, so no two hang parallel (straight down, a row of them is a comb's teeth)
                P = np.asarray(P)
                sl = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
                u = np.linspace(0, 1, 17)
                P = np.stack([np.interp(u * sl[-1], sl, P[:, c_]) for c_ in range(3)], 1)
                eo = P[0] - sc.C
                eo = _unit(np.array([eo[0], eo[1], 0.0]))
                es = np.array([-eo[1], eo[0], 0.0])
                a = np.radians(rng.uniform(-110, 110))
                bow = cv * ln * rng.uniform(0.4, 1.2)
                e = np.cos(a) * eo + np.sin(a) * es
                e2 = np.cross(e, [0.0, 0.0, 1.0])
                k_, ph_ = rng.uniform(0.7, 1.3), rng.uniform(0, 2 * np.pi)
                P = (P + (bow * np.sin(np.pi * u ** 0.8))[:, None] * e
                     + (0.45 * bow * u * np.sin(2 * np.pi * k_ * u + ph_))[:, None] * e2
                     + (0.5 * bow * u ** 3)[:, None] * eo)  # (the tip flicks out)
                P = _clear(sc, P, 0.004)
            locks[f"{pre}f{k}"] = {"tier": "tie", "space": "xyz", "pts": _xyz(sc, P), "free": 1.0,
                                  "width": round(float(rng.uniform(w0, w1)), 4), "thickness": 0.003,
                                  "taper": 0.5, "belly": 0.35, "root": 0.6, "cup": 0.0,
                                  **({"hairs": int(rng.integers(1, hairs + 1))} if hairs > 0 else {}),
                                  "strands": {**FRAME_STRANDS, "wave": float(fm["wave"]),
                                              "wavelength": float(fm["wavelength"]), **(fm.get("strands") or {})}}
        if tl and float(tp.get("band") or 0) > 0:  # the tie: a short stiff ring of locks round the tail's start
            K = core_line(sc, tp, {**tl, "dir": hair_flow.tail_dir(tp, tl).tolist()} if tl.get("hang") else tl)
            T, E1, E2 = _transport(K)
            r = min(0.012, float(tl["fullness"]) * 0.4) + 0.004
            c = K[0] + T[0] * 0.012
            ang = np.linspace(0, 2 * np.pi, 9)
            ring = c + r * (np.cos(ang)[:, None] * E1[0] + np.sin(ang)[:, None] * E2[0])
            locks[f"{pre}band"] = {"tier": "tie", "space": "xyz", "pts": _xyz(sc, ring), "core": _xyz(sc, [c - T[0] * 0.02, c + T[0] * 0.02]),
                                  "free": 1.0, "width": round(float(tp["band"]) * 2, 4), "thickness": round(float(tp["band"]), 4),
                                  "taper": 0.0, "belly": 0.5, "root": 1.0, "cup": 0.0, "grey": 0.0,
                                  "strands": {"layers": 1, "flyaway": 0.0, "wave": 0.0}}
    return locks


def band_mesh(lk: dict, tiles: list, sides: int = 8) -> dict:
    """The tie as a solid ring (a torus round the band lock's ring of points), in hair_cards' mesh form, wearing
    the atlas's plain "band" tile."""
    P = np.asarray(lk["pts"], float)[:-1]
    c = P.mean(0)
    n = len(P)
    r = float(lk["inputs"]["Thickness"]) * 0.75
    ax = _unit(np.cross(P[1] - P[0], P[2] - P[1]))
    t = next(t for t in tiles if t["kind"] == "band")
    V, N = [], []
    for i in range(n):
        o = _unit(P[i] - c)
        for j in range(sides):
            a = 2 * np.pi * j / sides
            d = np.cos(a) * o + np.sin(a) * ax
            V.append(P[i] + r * d)
            N.append(d)
    V, N = np.asarray(V), np.asarray(N)
    F = []
    for i in range(n):
        for j in range(sides):
            a, b = i * sides + j, i * sides + (j + 1) % sides
            c2, d2 = ((i + 1) % n) * sides + (j + 1) % sides, ((i + 1) % n) * sides + j
            F += [[a, b, c2], [a, c2, d2]]
    m = len(V)
    tan = np.repeat(_unit(np.roll(P, -1, 0) - np.roll(P, 1, 0)), sides, 0)
    return {"verts": V.astype(np.float32), "tris": np.asarray(F, np.int32),
            "uv": np.tile([[0.5 * (t["u0"] + t["u1"]), 0.5]], (m, 1)).astype(np.float32),
            "normal": N.astype(np.float32), "tangent": tan.astype(np.float32), "col": np.ones((m, 3), np.float32),
            "along": np.full(m, 0.5, np.float32), "layer": np.full(m, 9.0, np.float32), "card": np.zeros(m, np.int32)}
