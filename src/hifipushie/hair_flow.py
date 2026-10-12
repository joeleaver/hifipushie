"""Swept-back tied hair as a groomer builds it (2026-10-11, "tesshair3"; Joe on the row / curtain construction: "flat
across her head instead of swept back and hanging down. This is a super common hairstyle, so we need to be able to get
it right and repeat/riff on it").

What groomers do (Autodesk's XGen forum on ponytails: one description for the pulled-back head hair, another for the
long hair that leaves the tie, guides rooted on the scalp and run to the tie, a clump scale that draws them into it;
SideFX's forum on long hair: guides laid in layers from the bottom up, upper layers over lower; Vellum practice: a
couple of hundred guides hung under gravity with a bend stiffness and collisions, strands generated from them
afterwards; Polycount on strays: their own description, one hair a guide) is what this module does:

  gather(): a FLOW FIELD over the scalp. Roots all over the scalp inside the hairline (blue noise + a row on the
      hairline), each traced along the head toward the tie: at every step the direction is "toward the tie along the
      surface" + "away from the parting" (where there is one) + "down the head" by looseness (sag). The way never
      leaves the hair (it stays above the hairline: over the ears, not across the temples' skin) unless `overhang` /
      `ears` let it. Height: the hair lifts off the scalp at its root (root_lift), stands off the head most halfway
      (puff), and hair rooted further from the tie lies over hair rooted nearer (body).
  tail(): every lock of the tail leaves the tie inside a cone round the tie's direction and FALLS: its direction
      turns to gravity as fast as `stiff` lets it, it lies on the neck / shoulder / back (the body's collider), and
      the bundle is scaled to `fullness` afterwards. No axis the locks are arranged round: a bundle of hanging locks.
  escaped(): pieces that never reached the tie: each a handful of single hairs that share one fall beside the face
      (or down the nape) and fray apart toward their ends.
  style(): THE STYLE. A small set of words and 0..1 numbers (`groom.tied`) -> the tie, parting, strand dials:
      a ponytail one can repeat on any head and riff on.
"""

from __future__ import annotations

import numpy as np

from .hair_tied import DOWN, _clear, _ss_t, _transport, _unit, _xyz

X = np.array([1.0, 0.0, 0.0])
Z = np.array([0.0, 0.0, 1.0])
STEP_DEG = 5.0


def _wrap(az):
    return ((np.asarray(az, float) + 180.0) % 360.0) - 180.0


# ------------------------------------------------------------------------------------------------ the gather

def _zig(ga: dict, y):
    """The parting's own line: m its x leaves the straight line at y (m back from the scalp's front). A part is
    never ruled: it wanders a few mm from side to side (gather.zig = that amplitude; phases from the groom's seed)."""
    A = float(ga.get("zig") or 0.0)
    y = np.asarray(y, float)
    if A <= 0 or ga.get("_zig") is None:
        return np.zeros(y.shape)
    p1, p2, lam = ga["_zig"]
    return A * (np.sin(2 * np.pi * y / lam + p1) + 0.45 * np.sin(2 * np.pi * y / (0.41 * lam) + p2))


def roots(sc, ga: dict, line, rng, xp=None):
    """(az, el, on_hairline, depth) of the gather's roots: a row on the hairline, blue noise inside it, and a row
    along each bank of the parting (x = xp m from the middle; without them the nearest roots stood up to a spacing off
    the line and the part was a bare zigzag furrow). With gather.edge also a BAND of fine roots between the line and
    where the inner roots begin (depth = m inside the hairline, 0 on the line; inf for inner roots)."""
    from .hair import _line_at, _poisson, inside, top_to_azel
    sp = float(ga["spacing"])
    edge = float(ga.get("edge") or 0.0)
    a = np.arange(0.0, 360.0, 2.0)
    L = sc.point(a, _line_at(line, a), 0.0)
    seg = np.linalg.norm(np.diff(L, axis=0, append=L[:1]), axis=1)
    cum = np.r_[0.0, np.cumsum(seg)]
    # (the hairline row is fine and close: where the hair runs ALONG the line (temples, behind the ears) each lock's
    # start is a cut across it, and wide locks made the edge a saw)
    n_h = max(8, int(round(cum[-1] / (0.32 * sp))))
    s = (np.arange(n_h) + 0.5 + float(ga["uneven"]) * rng.uniform(-0.3, 0.3, n_h)) / n_h * cum[-1]
    az_h = np.interp(s, cum, np.r_[a, 360.0]) % 360
    el_h = _line_at(line, az_h) + 1.5
    for _ in range(4):  # (a steep stretch of the line: up until it is inside the hair)
        out = inside(sc, line, az_h, el_h) < 0.003
        el_h = el_h + 4.0 * out
    if ga.get("feather"):
        # the SIDEBURN grows no lock to the tie: rooted below the ear's top in front of the ear, a hairline lock had
        # to climb to the flow over the ear, and its start was a dark tooth-edged tuft over bare skin (the "shaved"
        # temple of every tight style, tesshair3 / 4). That hair is short: the scalp layer and the wisps are it
        fa = np.abs(_wrap(az_h))
        e_ear = 0.5 * (float(_line_at(line, 95.0)) + float(_line_at(line, 265.0)))
        # (with an edge band the sideburn is hair again, thin and fine at its rim: only its lowest fringe, which
        # could never reach a tie, grows no lock)
        keep = ~((fa > 50) & (fa < 100) & (el_h < e_ear - (11.0 if edge > 0 else 2.0)))
        az_h, el_h = az_h[keep], el_h[keep]
    d_h = np.zeros(len(az_h))
    if edge > 0:
        # THE EDGE BAND (tesshair5; Joe: "a hard dark arc"): one row of locks on the line is a cliff, full density
        # from the first mm, and the strip behind it (up to where the inner roots begin, 0.6 x spacing) had no root at
        # all: at the temples and sideburns, where that strip is all the hair there is, it read as shaved skin. Fine
        # blue-noise roots fill it; gather() thins and narrows them toward the line (a density ramp)
        def okb(a_, e_):
            d_ = inside(sc, line, a_ % 360, e_)
            fa_ = np.abs(_wrap(a_))
            low = (fa_ > 50) & (fa_ < 100) & (e_ < 0.5 * (float(_line_at(line, 95.0)) + float(_line_at(line, 265.0))) - 11.0)
            # (to a whole spacing in, over the first inner roots: those stand 2 cm apart, and where the hair runs
            # straight AWAY from the line (a high tie's temples) the stretch between band and inner roots was bare)
            return (d_ > 0.002) & (d_ < 1.05 * sp) & (e_ > sc.EL[0] + 4) & ~low
        r0_ = float(np.median(sc.R))
        az_b, el_b = _poisson(sc, rng, lambda a_, e_: np.full(len(a_), 0.36 * sp), okb,
                              n_try=int(np.clip(2400 * r0_ * r0_ / sp ** 2, 12000, 60000)))
        # (the row's own depth too: over a steep stretch of the line its roots were lifted into the hair)
        d_h = np.clip(inside(sc, line, az_h % 360, el_h) - 0.003, 0.0, None)
        az_h, el_h = np.r_[az_h, az_b % 360], np.r_[el_h, el_b]
        d_h = np.r_[d_h, inside(sc, line, az_b % 360, el_b)]
    ok = lambda a_, e_: (inside(sc, line, a_, e_) > 0.6 * sp) & (e_ > sc.EL[0] + 4)  # noqa: E731
    r0 = float(np.median(sc.R))
    az_i, el_i = _poisson(sc, rng, lambda a_, e_: np.full(len(a_), sp), ok,
                          n_try=int(np.clip(400 * r0 * r0 / sp ** 2, 4000, 40000)))
    if xp is not None and float(ga["part_length"]) > 0:
        y0 = -float(sc.r(0.0, 30.0)) * np.cos(np.radians(30.0))
        plen = float(ga["part_length"])
        Pi = sc.point(az_i, el_i, 0.0) - sc.C
        far = (np.abs(Pi[:, 0] - xp - _zig(ga, Pi[:, 1] - y0)) > 0.55 * sp) | (Pi[:, 1] > y0 + plen + 0.5 * sp) | (Pi[:, 2] < 0.02)
        az_i, el_i = az_i[far], el_i[far]
        yy = y0 + np.arange(0.0, plen + 1e-9, 0.5 * sp)
        n_i0 = len(az_i)
        for sd in (-1.0, 1.0):
            ys = yy + (0.25 * sp if sd > 0 else 0.0)
            a_, e_ = top_to_azel(sc, np.stack([xp + sd * 0.003 + _zig(ga, ys - y0), ys], 1))
            keep = inside(sc, line, a_, e_) > 0.004
            az_i, el_i = np.r_[az_i, a_[keep]], np.r_[el_i, e_[keep]]
    az = np.r_[az_h, az_i]
    el = np.r_[el_h, el_i]
    hl = np.r_[np.ones(len(az_h), bool), np.zeros(len(az_i), bool)]
    if xp is not None and float(ga["part_length"]) > 0:
        hl = hl.astype(int)
        hl[len(az_h) + n_i0:] = 2  # (2 = on the parting)
    din = np.r_[d_h, np.full(len(az_i), np.inf)]
    if ga.get("above") is not None:  # only the hair above a level (m from the head centre): half up
        keep = ((sc.point(az, el, 0.0)[:, 2] - sc.C[2]) > float(ga["above"])) & (np.abs(_wrap(az)) < 125.0)
        az, el, hl, din = az[keep], el[keep], hl[keep], din[keep]
    return az, el, hl, din


def paths(sc, line, D0, tie_d, xp, ga: dict, rng, n: int = 12):
    """The way of each root (unit directions D0 from the head centre) over the head to the tie: (m, n, 3) unit
    directions, and each way's length (radians)."""
    from .hair import _line_at, az_el, dirs
    D = _unit(np.array(D0, float))
    m = len(D)
    tie_d = _unit(np.asarray(tie_d, float))
    step = np.radians(STEP_DEG)
    ang0 = np.arccos(np.clip(D @ tie_d, -1, 1))
    a0, e0 = az_el(D)
    p0_ = sc.point(a0, e0, 0.0) - sc.C
    x0 = p0_[:, 0]
    xs = x0 - (xp if xp is not None else 0.0)
    if xp is not None and ga.get("_zig") is not None:  # (its own bank of a part that wanders)
        xs = xs - _zig(ga, p0_[:, 1] + float(sc.r(0.0, 30.0)) * np.cos(np.radians(30.0)))
    side = np.where(np.abs(xs) < 0.002, rng.choice([-1.0, 1.0], m), np.sign(xs))
    push = float(ga["part_push"]) if xp is not None else 0.0
    sag = float(ga["sag"])
    # (the front and temples hang most: hair off the part falls out over the temple; behind the ears it is on its way)
    frontw = 1.0 - 0.7 * _ss_t((np.abs(_wrap(a0)) - 80.0) / 40.0)
    yf = sc.C[1] - float(sc.r(0.0, 30.0)) * np.cos(np.radians(30.0))  # the scalp's front (as hair._part)
    plen = float(ga["part_length"])
    tz, te = az_el(tie_d)
    mid_d = dirs(180.0, float(te))  # the tie brought to the back's middle: what the FRONT of the head is combed to
    e_ear = 0.5 * (float(_line_at(line, 95.0)) + float(_line_at(line, 265.0)))  # the hairline over the ears
    tie_in = float(te) > float(_line_at(line, float(tz))) + 2.0  # (a tie below the hairline: no keep-in near it)
    P = [D.copy()]
    for _ in range(int(2.5 * np.pi / step)):
        c = np.clip(D @ tie_d, -1, 1)
        ang = np.arccos(c)
        if np.all(ang < 1e-4):
            break
        # in front of the ears the hair is combed BACK (to the tie's height at the back's middle), behind them to the
        # tie itself: toward an off-centre tie all along, the far side's front crossed over the top of the head to it
        # and the two sides of the face differed
        wb = _ss_t((D[:, 1] + 0.2) / 0.6)[:, None]
        tg = _unit((1 - wb) * mid_d[None] + wb * tie_d[None])
        to = tg - (tg * D).sum(1, keepdims=True) * D
        if xp is not None:
            # with a parting the front never climbs over the top on its way back (the shortest way from the forehead
            # to the back of the head does): it runs back at its own height and the sag takes it down the side.
            # Climbing, the hair off the part stayed 3-5 cm over the temples and the forehead's corners were bare
            # (hairline 5-7 mm high by measure, Tess)
            to[:, 2] = np.where(to[:, 2] > 0, to[:, 2] * wb[:, 0], to[:, 2])
        lost = np.linalg.norm(to, axis=1) < 1e-6  # (the tie's antipode: any way is as short)
        to[lost] = np.cross(D[lost], X) + 1e-3
        to = _unit(to)
        az, el = az_el(D)
        v = to.copy()
        near = _ss_t((ang - np.radians(12)) / np.radians(20))  # (the last stretch runs straight into the tie)
        if push > 0:  # combed away from the parting, on its own side
            Q = sc.point(az, el, 0.0)
            wp = np.exp(-((Q[:, 0] - sc.C[0] - xp) / 0.035) ** 2) * (1 - _ss_t((Q[:, 1] - yf - plen) / 0.03)) \
                * _ss_t((el - 20) / 15)
            aw = side[:, None] * X[None]
            aw = aw - (aw * D).sum(1, keepdims=True) * D
            v = v + (push * wp * near)[:, None] * aw
        if sag > 0:  # loose hair hangs between its root and the tie: down the head, on its own side on top
            prog = 1 - ang / np.maximum(ang0, 1e-6)
            # (most just after the root: hair off a part falls outward over the temple before the tie takes it)
            # (only where the head is steep: on top the hair lies on it, and a pull to each side there opened the part
            # into a furrow all the way over the crown; never forward: swept-back hair doesn't hang over the face)
            dn = DOWN[None] - (D @ DOWN)[:, None] * D
            dn = dn * np.linalg.norm(dn, axis=1, keepdims=True)
            dn[:, 1] = np.maximum(dn[:, 1], -0.6 * np.linalg.norm(dn, axis=1))  # (forward only a little: over the forehead's corners)
            v = v + (sag * frontw * np.sin(np.pi * np.clip(prog, 0, 1) ** 0.35) * np.minimum(ang0 / (np.pi / 2), 1.0) * near)[:, None] * dn
        v = _unit(v)
        low = (v * to).sum(1) < 0.35  # (always on toward the tie)
        v[low] = _unit(v[low] + to[low])
        st = np.minimum(step, ang)
        Dn = _unit(D * np.cos(st)[:, None] + v * np.sin(st)[:, None])
        # the way stays in the hair: above the hairline (so over the ears' tops, not across the temples' skin or the
        # ear), but for `overhang` deg at the front and temples and `ears` deg round the ears
        az, el = az_el(Dn)
        fa = np.abs(_wrap(az))
        lim = _line_at(line, az) + 1.0 - float(ga["overhang"]) * _ss_t((fa - 4) / 22) * (1 - _ss_t((fa - 62) / 22)) \
            - float(ga["ears"]) * np.exp(-((fa - 95) / 22) ** 2)
        # ...and never further down in front of / over the ear than its top (the sideburn's line runs far below it)
        lim = np.where((fa > 52) & (fa < 112), np.maximum(lim, e_ear - 3.0 - float(ga["ears"])), lim)
        need = (el < lim) & (ang > np.radians(22)) & tie_in
        if need.any():
            Dn[need] = dirs(az[need], lim[need])
        arrived = np.arccos(np.clip(Dn @ tie_d, -1, 1)) < 1e-4
        Dn[arrived | (ang < 1e-4)] = tie_d
        D = Dn
        P.append(D.copy())
    P = np.stack(P, 1)  # (m, steps, 3)
    seg = np.arccos(np.clip((P[:, 1:] * P[:, :-1]).sum(-1), -1, 1))
    cum = np.concatenate([np.zeros((m, 1)), np.cumsum(seg, 1)], 1)
    t = np.linspace(0, 1, n)
    out = np.zeros((m, n, 3))
    for i in range(m):
        if cum[i, -1] < 1e-6:
            out[i] = tie_d
            continue
        for j in range(3):
            out[i, :, j] = np.interp(t * cum[i, -1], cum[i], P[i, :, j])
    out = _unit(out)
    for _ in range(2):  # (the keep-in turns a way at a corner)
        out[:, 1:-1] = _unit(0.25 * out[:, :-2] + 0.5 * out[:, 1:-1] + 0.25 * out[:, 2:])
    return out, cum[:, -1]


def gather(sc, g: dict, tp: dict, ga: dict, line, rng, pre: str) -> dict:
    """The gather as a flow field: {name: lock} ([az, el, h] locks named like the rows' ones)."""
    from .hair import _line_at, _part_x, az_el, dirs
    xp = _part_x(g)
    edge = float(ga.get("edge") or 0.0)
    if float(ga.get("zig") or 0.0) > 0 and xp is not None:
        ga = {**ga, "_zig": (float(rng.uniform(0, 2 * np.pi)), float(rng.uniform(0, 2 * np.pi)), float(rng.uniform(0.02, 0.03)))}
    az, el, hl, din = roots(sc, ga, line, rng, xp)
    if not len(az):
        return {}
    e_ear = 0.5 * (float(_line_at(line, 95.0)) + float(_line_at(line, 265.0)))
    tie_d = dirs(*tp["at"])
    n = 12
    D, w0 = paths(sc, line, dirs(az, el), tie_d, xp, ga, rng, n)
    t = np.linspace(0, 1, n)
    un = float(ga["uneven"])
    sp = float(ga["spacing"])
    locks = {}
    k = [0, 0]
    for i in range(len(az)):
        aa, ee = az_el(D[i])
        far = float(np.clip(w0[i] / np.pi, 0.0, 1.0))
        top = float(np.clip(np.sin(np.radians(ee[n // 2])), 0.0, 1.0))  # (the top stands off more than the sides)
        # (the parting's own rows lie low: lifted like the rest they were two humps; the hairline row too: lifted, and
        # with its strands' starts staggered far along it, the hair's edge stood 5-7 mm behind the hairline: Tess)
        onp = 0.45 if hl[i] == 2 else 0.6 if hl[i] == 1 else 1.0
        ramp, strip = 1.0, 0.0
        if edge > 0 and hl[i] == 1:  # the edge band: lower and flatter toward the line
            # (at the temple and sideburn the band IS the hair, a strip 1-2.5 cm wide: full by 5 mm there, or the
            # whole temple was a thin gauze over skin, th_T51)
            fa_i = abs(float(_wrap(az[i])))
            strip = float(_ss_t((fa_i - 40.0) / 15.0) * (1.0 - _ss_t((fa_i - 100.0) / 10.0)))
            ramp = float(_ss_t(din[i] / ((0.6 - 0.35 * strip) * sp)))
            onp = 0.35 + 0.45 * ramp
        puff = onp * float(ga["puff"]) * (0.4 + 0.6 * top) * min(w0[i] / np.radians(50), 1.0) * (1 + un * rng.uniform(-0.5, 0.9))
        lift = onp * float(ga["root_lift"]) * (1 + un * rng.uniform(-0.3, 0.5))
        ride = 0.002 + float(ga["body"]) * far
        h = (1 - t ** 3) * (ride * np.minimum(t * 6, 1) + lift * _ss_t(t / 0.15) * (1 - 0.5 * t) + puff * np.sin(np.pi * t) ** 0.9) \
            + t ** 3 * float(tp["out"]) * 0.8
        aa = aa + un * 4.0 * np.sin(np.pi * t) * rng.uniform(-1, 1)
        r = 0 if hl[i] == 1 else 1
        name = f"{pre}g{r}_{k[r]}"
        k[r] += 1
        # (with an edge: how near the hairline an INNER lock roots, 1 on it .. 0 from 3.5 cm in. The inner locks are
        # 4 cm planks whose strands all start on one line: beside the part, where they run along the hairline, their
        # sides and starts were the hard V and its stair steps (th_T51, drawn alone))
        nearf = 0.0
        if edge > 0 and hl[i] != 1:
            from .hair import inside
            nearf = edge * (1.0 - float(_ss_t((float(inside(sc, line, az[i] % 360, el[i])) - 0.01) / 0.025))) \
                * (1.0 - float(_ss_t((abs(float(_wrap(az[i]))) - 60.0) / 30.0)))
        wx = (0.42 + 0.2 * ramp if edge > 0 else 0.6) if hl[i] == 1 else 1.9 - 0.5 * nearf
        lk = {"tier": "tie", "pts": [[round(float(aa[j]), 2), round(float(ee[j]), 2), round(float(h[j]), 4)] for j in range(n)],
              "width": round(sp * wx * (1 + un * rng.uniform(-0.3, 0.3)), 4), "thickness": 0.004,
              "taper": 0.6, "belly": 0.45, "root": 0.8, "cup": 0.003}
        st = dict(ga.get("strands") or {})
        if hl[i] == 1:
            st.update(ga.get("hairline_strands") or {})
            if edge > 0:
                # THE DENSITY RAMP: the locks nearest the line carry a fraction of the strands, drawn fine (part
                # transparent in EEVEE, which never draws a strand under a pixel wide), full by the band's inner side.
                # A sideburn lock that has to climb to the flow over the ear is thinner still, the lower it roots
                fa_i = abs(float(_wrap(az[i])))
                climb = float(_ss_t((e_ear - 2.0 - el[i]) / 10.0)) if 50.0 < fa_i < 100.0 else 0.0
                thin = (1.0 - edge * (1.0 - (0.2 + 0.8 * ramp))) * (1.0 - 0.3 * edge * climb)
                # (the strip has one layer of hair, its own; everywhere else the long hair from further up lies over
                # the band: its locks carry more strands)
                st["density"] = round(float(st.get("density", 1.0)) * thin * (1.0 + 1.5 * strip * ramp), 3)
                st["fine"] = round(float(np.clip(edge * (1.0 - ramp) * (1.0 - 0.5 * strip) + 0.3 * edge * climb, 0.0, 1.0)), 3)
                st["rim"] = round(0.8 + 1.0 * edge, 2)
                st["roots_m"] = round(0.008 + 0.02 * (1.0 - ramp), 4)
            if ga.get("feather"):
                # where the hair runs ALONG the hairline (the temples, beside the part: every lock's start is a cut
                # across the line) its strands start one by one far along the lock: a feathered edge instead of a
                # staircase of lock starts (the "shaved" temple of every tight style, the stepped notch at the part).
                # Where it runs AWAY from the line (the forehead) starts stay close: staggered there the hair's edge
                # stood 5-7 mm behind the line (tesshair3)
                da = float(_wrap(aa[2] - aa[0])) * np.cos(np.radians(float(ee[0])))
                along = abs(da) / max(float(np.hypot(da, ee[2] - ee[0])), 1e-6)
                # (not beside the part: its banks run along the line too, and feathered they bared a wide notch)
                along *= float(_ss_t((abs(float(_wrap(aa[0]))) - 28.0) / 20.0))
                st["roots"] = round(float(st.get("roots", 0.3)) + float(ga["feather"]) * (1.0 - float(st.get("roots", 0.3))) * along ** 2, 3)
                lk["root"] = round(0.8 - 0.5 * float(ga["feather"]) * along ** 2, 3)
                if along > 0.3:
                    st["roots_x"] = 4.0
        else:  # (inside the hair every strand starts at its lock's root: staggered starts are stubble)
            st["roots"] = 0.0 if ga.get("inner_roots") is None else float(ga["inner_roots"])
            if nearf > 0.05:  # soft sides, starts one by one
                st["rim"] = round(0.8 + 1.4 * nearf, 2)
                st["roots"] = round(max(st["roots"], 0.6 * nearf), 3)
                st["roots_x"] = 3.0
            if ga.get("feather") and hl[i] == 0:
                # ... but for the locks rooted just inside the hairline at the temples and sideburns: 4 cm wide, lifted
                # and all their strands starting on one line, their starts were a dark slab with a toothed front edge
                # 1-2 cm behind the line (what read as a shaved temple): narrow at the root, starts one by one
                from .hair import inside
                d_in = float(inside(sc, line, az[i] % 360, el[i]))
                nr = float(ga["feather"]) * (1 - float(_ss_t((d_in - 0.012) / 0.03))) * float(_ss_t((abs(float(_wrap(az[i]))) - 28.0) / 20.0))
                if nr > 0.05:
                    st["roots"] = round(max(st["roots"], nr), 3)
                    st["roots_x"] = 4.0
                    lk["root"] = round(0.8 - 0.55 * nr, 3)
        if st:
            lk["strands"] = st
        locks[name] = lk
    return locks


# ------------------------------------------------------------------------------------------------ the tail

def tail_dir(tp: dict, tl: dict):
    """The direction a tail leaves its tie in: `dir`, else out of the head, a high tie a little up, a low one down."""
    from .hair import dirs
    if tl.get("dir") is not None:
        return _unit(np.asarray(tl["dir"], float))
    az, el = tp["at"]
    return _unit(dirs(az, el) + Z * 0.8 * (float(el) / 90.0 - 0.06))


def _push(sc, col, P, gap):
    P = np.asarray(P, float)
    if col is not None:
        return col.push(P, gap)
    return _clear(sc, P, gap)


def tail(sc, tp: dict, tl: dict, rng, col, pre: str, P0) -> dict:
    """A tail that hangs: {name: lock} ("xyz" locks with the bundle's own mean line as `core`)."""
    d0 = tail_dir(tp, tl)
    n = int(tl["locks"])
    L, full, un = float(tl["length"]), float(tl["fullness"]), float(tl["uneven"])
    e1 = np.cross(d0, Z)
    e1 = _unit(e1 if np.linalg.norm(e1) > 0.2 else np.cross(d0, X))
    e2 = np.cross(d0, e1)
    r_tie = min(0.012, full * 0.4)
    kk = (1 - float(tl["stiff"])) ** 2 * 45.0 * (1 + 0.3 * rng.uniform(-1, 1, n))  # the direction's fall, per metre
    ks = np.arange(n)
    th, rho = ks * 2.39996, np.sqrt((ks + 0.5) / n)
    rad = np.cos(th)[:, None] * e1 + np.sin(th)[:, None] * e2
    ln = 1 - un * rng.uniform(0, 0.6, n)
    if float(tl.get("bulge", 0.0)) > 0:  # (a lock 40% short ends as a blunt chunk in the middle of a full tail)
        ln = 1 - un * rng.uniform(0, 1, n) ** 1.5 * 0.4
    rag = float(np.clip(tl.get("ragged", 0.0), 0, 1))
    if rag > 0:
        # a RAGGED end: the locks end anywhere over the last third (the outer ones no shorter than the inner: the
        # outline itself must be uneven), each narrowing to a point; `uneven` alone moved a few locks a little and
        # the end stayed one straight cut (th_T48 from behind)
        ln = np.minimum(ln, 1 - rag * 0.35 * rng.uniform(0, 1, n))
    ns = 20
    bulge = float(tl.get("bulge", 0.0))
    lwave = float(tl.get("lock_wave", 0.0))
    if lwave > 0:  # (a wave needs points: ~8 a wavelength)
        ns = int(np.clip(2 * np.ceil(4 * L / max(float(tl.get("lock_wavelength", 0.08)), 0.02)), 20, 48))
    ds = L * ln / ns
    d = d0[None] + float(tl["spread"]) * rho[:, None] * rad
    from .hair import dirs
    out = dirs(*tp["at"])
    inw = np.minimum(d @ out - float(d0 @ out), 0.0)  # (no lock leaves the tie INTO the head: it lay over the crown)
    d = _unit(d - 0.8 * inw[:, None] * out[None])
    gap = 0.004 + 0.5 * full * rng.uniform(0, 1, n)  # (lying on a shoulder the bundle keeps its thickness)
    P = P0 + (r_tie * rho)[:, None] * rad
    pts = [P]
    for _ in range(ns):
        d = _unit(d + (kk * ds)[:, None] * DOWN)
        q = _push(sc, col, P + ds[:, None] * d, gap)
        d = _unit(q - P)
        P = P + ds[:, None] * d
        pts.append(P)
    Q = np.stack(pts, 1)  # (n, ns + 1, 3)
    sk = np.linspace(0, 1, ns + 1)[None] * (L * ln)[:, None]  # each lock's length along itself
    # the bundle's own line (the mean of the locks that reach each length) and its radius -> scaled to `fullness`
    S = np.linspace(0, L, 28)
    reach = S[None] <= (L * ln)[:, None] + 1e-9
    R = np.stack([np.stack([np.interp(S, sk[i], Q[i, :, j]) for j in range(3)], 1) for i in range(n)])
    cnt = np.maximum(reach.sum(0), 1)
    K = (R * reach[..., None]).sum(0) / cnt[:, None]
    last = int(np.nonzero(reach.sum(0) >= min(3, n))[0][-1])
    K[last + 1:] = K[last] + (S[last + 1:] - S[last])[:, None] * _unit(K[last] - K[max(last - 1, 0)])
    off = R - K[None]
    rms = np.sqrt(((off ** 2).sum(-1) * reach).sum(0) / cnt)
    scale = float(np.clip(full / max(1.41 * float(rms[:last + 1].max()), 1e-4), 0.4, 3.0))
    scs = None
    if bulge > 0:
        # VOLUME as the bundle's own property (tesshair4; Joe: "poofed up the ponytail a bit"): the radius is SET
        # along the tail instead of one factor on whatever the fall gave (a cone that closes to parallel strings):
        # out of the band it opens at once (the bulge: full by ~5 cm), stays full, and draws in a little to the end
        tb = float(np.clip(0.05 / max(L, 1e-6), 0.12, 0.4))
        tS = S / max(L, 1e-6)
        prof = (0.25 + 0.75 * _ss_t(tS / tb) ** 0.7) * (1 - float(tl["taper"]) * np.clip((tS - tb) / (1 - tb), 0, 1) ** 2)
        prof = prof * (1 + 0.12 * np.exp(-((tS - 1.6 * tb) / (0.9 * tb)) ** 2))
        if rag > 0:  # (... and opens as a FAN out of the band, full by ~9 cm: full at 5 with a swell right after, the
            # bundle stood over the tie as a lump and hid it from behind)
            tb = float(np.clip(0.09 / max(L, 1e-6), 0.2, 0.5))
            prof = (0.18 + 0.82 * _ss_t(tS / tb) ** 0.9) * (1 - float(tl["taper"]) * np.clip((tS - tb) / (1 - tb), 0, 1) ** 2)
        want = full / 1.41 * prof
        scs = np.clip(want / np.maximum(rms, 1e-4), 0.3, 4.0)
        scs[last + 1:] = scs[last]
        for _ in range(3):
            scs[1:-1] = 0.25 * scs[:-2] + 0.5 * scs[1:-1] + 0.25 * scs[2:]
    T, E1, E2 = _transport(K)
    sway, lam = float(tl.get("sway", 0.0)), max(float(tl.get("sway_length", 0.16)), 0.02)
    ph0 = rng.uniform(0, 2 * np.pi)
    fl = float(tl.get("flick", 0.0))
    core = None
    locks = {}
    Kc = K.copy()
    if sway > 0:  # the whole bundle swings: one slow S, every lock with it
        env = _ss_t(S / 0.05)
        Kc = K + (sway * env * np.sin(2 * np.pi * S / lam + ph0))[:, None] * E1 \
            + (0.5 * sway * env * np.sin(2 * np.pi * S / (lam * 1.37) + ph0 + 1.3))[:, None] * E2
    core = _xyz(sc, Kc[::2])
    step_ = float(np.clip(tl.get("in_step", 0.0), 0, 1))
    wq = None
    if step_ > 0:  # (the direction across the bundle the shared wave's phase runs in, and its phase)
        wq = rng.uniform(0, 2 * np.pi, 2)
        wq = (float(np.cos(wq[0])), float(np.sin(wq[0])), float(wq[1]))
    up_k = Z[None] - (T @ Z)[:, None] * T  # "up" across the bundle's own line
    up_k = _unit(up_k + 1e-9)
    kept = []
    for i in range(n):
        tt = sk[i] / L
        Ki = np.stack([np.interp(sk[i], S, K[:, j]) for j in range(3)], 1)
        Kci = np.stack([np.interp(sk[i], S, Kc[:, j]) for j in range(3)], 1)
        o = Q[i] - Ki
        if rag > 0:
            # nothing rises over the tie: a lock's offset ABOVE the bundle's line comes in over the first 12 cm (the
            # tail leaves the band as a fan that opens downward and to the sides; the band shows from behind)
            upi = np.stack([np.interp(sk[i], S, up_k[:, j]) for j in range(3)], 1)
            o = o - (np.maximum((o * upi).sum(1), 0.0) * 0.6 * (1 - _ss_t(sk[i] / 0.12)))[:, None] * upi
        if scs is not None:
            f = np.interp(sk[i], S, scs)
        else:
            f = (1 + (scale - 1) * _ss_t(sk[i] / 0.04)) * (1 - float(tl["taper"]) * tt ** 2)
        Pk = Kci + o * f[:, None]
        Pk = Pk + (un * 0.012 + float(tl.get("air", 0.0))) * rng.normal(0, 1, 3)[None] * (tt ** 1.5)[:, None]  # (each lock a little its own way)
        if lwave > 0:
            # every lock waves ON ITS OWN: its own amplitude, wavelength, phase and plane (slowly turning: a loose
            # wave is a lazy helix, not a zigzag in one plane). The strand dials' wave keeps neighbours in step (a
            # tail that swings as one sheet); a poof is locks out of step with air between them
            e1i = np.stack([np.interp(sk[i], S, E1[:, j]) for j in range(3)], 1)
            e2i = np.stack([np.interp(sk[i], S, E2[:, j]) for j in range(3)], 1)
            lam_i = max(float(tl.get("lock_wavelength", 0.08)), 0.02) * rng.uniform(0.75, 1.3)
            a_i = lwave * rng.uniform(0.45, 1.35)
            psi = rng.uniform(0, 2 * np.pi) + rng.uniform(-1.2, 1.2) * tt
            ph_i = 2 * np.pi * sk[i] / lam_i + rng.uniform(0, 2 * np.pi)
            if wq is not None:
                # neighbours wave TOGETHER: one wave runs through the bundle (its phase by where the lock sits in the
                # section, its plane shared), each lock off it by (1 - in_step). Every lock on its own phase, plane
                # and length, a full tail was a bunch of ropes from behind (th_T48); hers moves as soft sheets
                lam_i = max(float(tl.get("lock_wavelength", 0.08)), 0.02) * (1 + (1 - step_) * (lam_i / max(float(tl.get("lock_wavelength", 0.08)), 0.02) - 1))
                x_, y_ = rho[i] * np.cos(th[i]), rho[i] * np.sin(th[i])
                ph_s = 2 * np.pi * sk[i] / lam_i + wq[2] + 2.2 * (wq[0] * x_ + wq[1] * y_)
                ph_i = ph_s + (1 - step_) * (ph_i - 2 * np.pi * sk[i] / lam_i)
                psi = step_ * (np.arctan2(wq[1], wq[0]) + 0.6 * tt) + (1 - step_) * psi
            wv = a_i * _ss_t(sk[i] / 0.05) * (0.7 + 0.5 * tt)
            Pk = Pk + (wv * np.sin(ph_i))[:, None] * (np.cos(psi)[:, None] * e1i + np.sin(psi)[:, None] * e2i) \
                + ((0.45 + 0.4 * step_) * wv * np.cos(ph_i))[:, None] * (-np.sin(psi)[:, None] * e1i + np.cos(psi)[:, None] * e2i)
            # (in step the swing is nearly round, a lazy helix: one shared plane showed its waves from one side and a
            # straight broom from the other, th_T52)
        if fl > 0:  # the lock's end turns out of the bundle (and a little up): a flicked tip, each its own
            Pk = Pk + (fl * rng.uniform(0.3, 1.0) * (0.3 + rho[i]) * _ss_t((sk[i] / (L * ln[i]) - 0.6) / 0.4) ** 2)[:, None] \
                * (_unit(o + 1e-9) + [0.0, 0.0, 0.35])
        Pk[1:] = _push(sc, col, Pk[1:], 0.004)
        Pk[0] = P0 + 0.5 * (Pk[0] - P0)
        kept.append(Pk)
        w = full * 2.2 / np.sqrt(max(n, 1)) * (1 + un * rng.uniform(-0.25, 0.35))
        if bulge > 0:  # wide locks that stay open to their ends (thin ones that taper to a point are strings: th_W1)
            # (and into each other: at 3 x full / sqrt(n) with air between them a full tail was a bunch of ropes)
            w = max(full * 4.5 / np.sqrt(max(n, 1)), 0.022) * (1 + un * rng.uniform(-0.25, 0.35))
        fine = bulge > 0 or lwave > 0
        locks[f"{pre}t{i}"] = {"tier": "tie", "space": "xyz", "pts": _xyz(sc, Pk if fine else Pk[::2] if ns % 2 == 0 else Pk),
                              "core": core, "free": 1.0, "width": round(float(max(w, 0.012)), 4), "thickness": 0.005,
                              "taper": (0.35 + 0.2 * rag) if bulge > 0 else 0.9, "belly": 0.4, "root": 0.5, "cup": 0.0,
                              # (a lock that keeps one flat side out all the way down is a plank: each turns on its way;
                              # in step they turn less: a ribbon wound 200 deg is a rope)
                              **({"twist": round(float(rng.uniform(60, 220) * (1 - 0.6 * step_) * rng.choice([-1, 1])), 1),
                                  "flip": round(float(rng.uniform(-90, 90)), 1)} if bulge > 0 else {}),
                              **({"strands": dict(tl["strands"])} if tl.get("strands") else {})}
    # STRAYS: single hairs and thin wisps that leave the tail's outline (hers: all round it, and out of its end). Each
    # rides a lock for a stretch, then lets go: out of the bundle, on its own slow curl, falling a little
    for j in range(int(tl.get("strays") or 0)):
        i = int(rng.integers(0, n))
        Pk = kept[i]
        m_ = len(Pk)
        a_ = int(rng.uniform(0.08, 0.75) * (m_ - 1))
        seg_ = float(np.linalg.norm(Pk[min(a_ + 1, m_ - 1)] - Pk[a_])) or L / m_
        ln_ = rng.uniform(0.03, 0.09)
        k_ = int(np.clip(round(ln_ / seg_), 4, 40))
        ride = int(rng.integers(1, 4))
        Ki = np.stack([np.interp(sk[i][a_], S, K[:, c_]) for c_ in range(3)])
        outw = _unit(Pk[a_] - Ki + 1e-6 * rng.normal(0, 1, 3))
        d_ = _unit(Pk[min(a_ + 1, m_ - 1)] - Pk[a_] + 1e-9)
        ax = _unit(rng.normal(0, 1, 3))
        cu_ = rng.uniform(4.0, 16.0)  # rad / m
        go = rng.uniform(0.25, 0.9)
        B = [Pk[a_] + 0.5 * w * rng.uniform(-0.4, 0.4) * outw]
        for q_ in range(k_):
            if q_ < ride and a_ + q_ + 1 < m_:
                d_ = _unit(Pk[a_ + q_ + 1] - Pk[a_ + q_])
            else:
                # (out of the bundle only a little a step, and falling: pushed out hard they were straight wires
                # standing 8 cm off the tail, th_T52)
                d_ = _unit(d_ + seg_ * (go * 3.5 * outw + cu_ * np.cross(ax, d_) + 5.0 * DOWN))
            B.append(B[-1] + seg_ * d_)
        B = np.asarray(B)
        B[1:] = _push(sc, col, B[1:], 0.004)
        locks[f"{pre}y{j}"] = {"tier": "tie", "space": "xyz", "pts": _xyz(sc, B), "free": 1.0,
                                "width": round(float(rng.uniform(0.001, 0.004)), 4), "thickness": 0.002, "taper": 0.5,
                                "belly": 0.35, "root": 0.6, "cup": 0.0, "hairs": int(rng.integers(1, 5)),
                                "strands": {"wisp_fan": 1.5, "wisp_round": 0.8, "tip_loss": 0.5, "wave": 0.004,
                                            "wavelength": 0.07, "random": 1.0, "flat": 1.0, "curl": 0.0}}
    return locks


# ------------------------------------------------------------------------------------------------ escaped pieces

def escaped(sc, tp: dict, es: dict, line, rng, col, pre: str) -> dict:
    """Pieces that never reached the tie: each a few SINGLE hairs that share one fall and fray apart toward their
    ends (parallel hairs are a comb strip, lone ones wires): {name: lock} ("xyz" locks with `hairs`)."""
    from .hair import _line_at, dirs, inside
    from .hair_tied import ESCAPED_AT, ESCAPED_STRANDS
    cnt = es["count"] if isinstance(es["count"], (list, tuple)) else [es["count"]] * 2
    cnt = [int(c) for c in cnt]  # [right, left]
    where = [w for w in (es.get("where") or ["temple"])]
    bad = set(where) - set(ESCAPED_AT)
    if bad:
        raise ValueError(f"hair tie escaped.where: unknown {sorted(bad)} (have {', '.join(ESCAPED_AT)})")
    l0, l1 = es["length"]
    h0, h1 = es["hairs"] if isinstance(es["hairs"], (list, tuple)) else (1, es["hairs"])
    cv = float(es["curve"])
    locks = {}
    k = 0
    for side, ns in ((-1, cnt[0]), (1, cnt[1])):
        for j in range(ns):
            zone = where[j % len(where)]
            a0, a1 = ESCAPED_AT[zone]
            az = (side * rng.uniform(a0, a1)) % 360
            el = float(_line_at(line, az)) + 3.0
            for _ in range(8):  # rooted IN the hair, a good 6 mm inside the line
                if float(inside(sc, line, az, el)) >= 0.006:
                    break
                el += 3.0
            p = sc.point(az, el, 0.003)
            out = dirs(az, el)
            ln = l0 + (l1 - l0) * rng.uniform(0, 1) ** 1.3
            # out of the hairline a little (forward of the ear at the face), then down: beside the cheek, on the neck
            tie_d = dirs(*tp["at"])
            to = tie_d - (tie_d @ out) * out
            to[2] = min(to[2], 0.0)  # (toward a HIGH tie they stood up and out of the temples like antennae)
            to = _unit(to + 1e-9)
            d0 = _unit(out * 0.25 + (DOWN if zone == "nape" else 0.45 * to + 0.35 * DOWN))
            eo = _unit(np.array([out[0], out[1], 0.0]))
            esd = np.array([-eo[1], eo[0], 0.0])
            u = np.linspace(0, 1, 17)
            nh = int(rng.integers(int(h0), int(h1) + 1))
            for q_ in range(nh):
                # its hairs: one root, but each FALLS on its own (its own first direction, stiffness and length), bows
                # in its own plane and waves on its own: sharing one fall they were a bundle of parallel wires
                # standing off the temple like whiskers (Tess, 2026-10-11)
                d = _unit(d0 + 0.45 * rng.normal(0, 1, 3) * np.array([1.0, 1.0, 0.5]))
                fall = rng.uniform(0.25, 0.75)
                lq = ln * rng.uniform(0.45, 1.0)
                B = [p + 0.002 * rng.normal(0, 1, 3)]
                for _ in range(10):
                    d = _unit(d + fall * DOWN)
                    B.append(_push(sc, col, (B[-1] + d * lq / 10)[None], 0.004)[0])
                B = np.asarray(B)
                sl = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(B, axis=0), axis=1))]
                Bq = np.stack([np.interp(u * sl[-1], sl, B[:, c_]) for c_ in range(3)], 1)
                a2 = rng.uniform(0, 2 * np.pi)
                e2 = np.cos(a2) * eo + np.sin(a2) * esd + 0.3 * rng.uniform(-1, 1) * Z
                bow = cv * lq * rng.uniform(0.2, 1.0)
                kq, phq = rng.uniform(0.6, 1.6), rng.uniform(0, 2 * np.pi)
                amp = cv * lq * rng.uniform(0.1, 0.4)
                Pq = Bq + (bow * np.sin(np.pi * u ** 0.8))[:, None] * e2 \
                    + (amp * u * np.sin(2 * np.pi * kq * u + phq))[:, None] * np.cross(e2, Z)
                Pq[1:] = _push(sc, col, Pq[1:], 0.003)
                locks[f"{pre}e{k}_{q_}"] = {
                    "tier": "tie", "space": "xyz", "pts": _xyz(sc, Pq), "free": 1.0,
                    "width": round(float(rng.uniform(0.001, 0.003)), 4), "thickness": 0.002, "taper": 0.5,
                    "belly": 0.35, "root": 0.6, "cup": 0.0, "hairs": int(rng.integers(1, 3)),
                    "strands": {**ESCAPED_STRANDS, "wave": float(es["wave"]), "wavelength": float(es["wavelength"]),
                                **(es.get("strands") or {})}}
            k += 1
    return locks


# ------------------------------------------------------------------------------------------------ wisps

def _surface(sc, col, P):
    """(distance to the head / body, its outward unit normal) at points P."""
    from .hair import dirs
    P = np.asarray(P, float)
    if col is not None:
        return np.asarray(col.at(P), float), np.asarray(col.grad(P), float)
    az, el, h = sc.coords(P)
    return h, dirs(az, el)


def wisps(sc, tp: dict, ws: dict, line, rng, col, pre: str) -> dict:
    """WISPS (tesshair4; Joe on the sleek low ponytail: "almost right for tess, if you added front wispies"): the short
    soft hair that never reached the tie, as small CLUMPS. A clump is one lock of `hairs` single fine strands (the
    wisp object: part transparent) that share one curve, fan a little, end one by one (a taper) and frizz slightly.
    Its line is rooted in the hair at the hairline (zones: part, front, temple, sideburn, nape) and FALLS ALONG THE
    SKIN: at every step the direction turns to gravity in the surface's tangent plane with a slow sideways curl, it
    may not lift off the surface while it is near it, and where the surface falls away under it (past the cheekbone,
    under the jaw) it hangs. Some (`tuck`) are drawn back toward the tie instead and droop over the ear's top.
    {name: lock} ("xyz" locks with `hairs`).

    Round three's escaped pieces were 1-2 hairs each on their own way, started 14 deg off the surface and bowed in
    random planes: stiff wires standing off the forehead (th_W1)."""
    from .hair import _line_at, dirs, inside
    from .hair_tied import WISP_AT
    cnt = ws["count"] if isinstance(ws["count"], (list, tuple)) else [ws["count"]] * 2
    cnt = [int(c) for c in cnt]  # [right, left]
    where = [("sideburn" if w == "ear" else w) for w in (ws.get("where") or ["temple"])]
    bad = set(where) - set(WISP_AT)
    if bad:
        raise ValueError(f"hair tie wisps.where: unknown {sorted(bad)} (have {', '.join(WISP_AT)})")
    l0, l1 = ws["length"]
    h0, h1 = ws["hairs"]
    soft = float(np.clip(ws["softness"], 0, 1))
    tuck = float(np.clip(ws["tuck"], 0, 1))
    over = float(ws.get("over", 0.008))  # m the gathered hair stands over the scalp: tucked wisps lie on it
    tie_d = dirs(*tp["at"])
    locks = {}
    k = 0
    # VARIETY (tesshair5: "not all long thin strands fanning from the temple"): besides the soft clumps ("soft"),
    #   "baby": the hairline's own short fine hair, 1-4 cm, a few hairs each, rooted ON the line and a little outside
    #       it all the way from the part to the sideburn: half lie back the way the hair was combed and end in it (the
    #       edge thins out instead of stopping), half let go and droop along the skin;
    #   "loose": a few THICK locks (30-70 hairs, 7-13 mm, 9-16 cm) out of the forehead's corner and the temple that
    #       sweep out and hang in front of the ear with one slow curve.
    jobs = [(side, where[j % len(where)], "soft") for side, ns in ((-1, cnt[0]), (1, cnt[1])) for j in range(ns)]
    n_b, n_l = ws.get("baby") or 0, ws.get("loose") or 0
    n_b = [int(c) for c in (n_b if isinstance(n_b, (list, tuple)) else [n_b] * 2)]
    n_l = [int(c) for c in (n_l if isinstance(n_l, (list, tuple)) else [n_l] * 2)]
    bz = [z for z in ("part", "front", "temple", "sideburn") if z in where] or ["front", "temple"]
    for si, side in enumerate((-1, 1)):
        jobs += [(side, "front" if j % 2 == 0 else "temple", "loose") for j in range(n_l[si])]
        jobs += [(side, None, "baby") for j in range(n_b[si])]
    lo_b, hi_b = min(WISP_AT[z][0] for z in bz), max(WISP_AT[z][1] for z in bz)
    if "part" in bz:
        lo_b = 0.0  # (the hairline under the part itself: the notch between the banks)
    for side, zone, kind in jobs:
        if True:
            m = 12 if kind == "baby" else 28
            if kind == "baby":  # anywhere along the line, by its length
                az_w = lo_b + (hi_b - lo_b) * rng.uniform(0, 1)
                zone = next((z for z in bz if WISP_AT[z][0] <= az_w <= WISP_AT[z][1]), "front" if az_w < 44 else "temple")
                az = (side * az_w) % 360
                el = float(_line_at(line, az)) + rng.uniform(-1.5, 2.5)
                want = rng.uniform(-0.003, 0.005)
            else:
                a0, a1 = WISP_AT[zone]
                if kind == "loose":
                    a0, a1 = (20.0, 40.0) if zone == "front" else (40.0, 58.0)
                az = (side * (a0 + (a1 - a0) * rng.uniform(0, 1))) % 360
                el = float(_line_at(line, az)) + 2.0
                want = 0.006 if kind == "loose" else 0.004
            for _ in range(8):  # rooted IN the hair, 4 mm inside the line (its start hides under the gather)
                if float(inside(sc, line, az, el)) >= want:
                    break
                el += 2.0
            p = sc.point(az, el, 0.002 if kind != "baby" else 0.0008)
            out = dirs(az, el)
            eo = _unit(np.array([out[0], out[1], 0.0]))
            sidev = np.array([float(side), 0.0, 0.0])
            # (not toward a high tie: "back" is then up, and held level they were straight dark blades in front of
            # the ears of a top knot, th_Q5)
            back = kind == "soft" and zone in ("temple", "sideburn") and rng.uniform() < tuck and float(tp["at"][1]) < 30.0
            # (a thick loose lock goes the way the hair was combed, out over the temple and back toward the ear, and
            # droops on the way: hanging straight down the cheek, 50 hairs were a stiff brush beside the eye, th_T51)
            back = back or (kind == "loose" and float(tp["at"][1]) < 30.0)
            comb = kind == "baby" and rng.uniform() < 0.5  # (lies back the way the hair was combed)
            # lengths: short ones at the part and front (they end at the brow / temple, never over the eye), longer
            # beside the face
            zl = {"part": 0.75, "front": 0.75, "temple": 0.9, "sideburn": 1.0, "nape": 0.6}[zone]
            ln = (l0 + (l1 - l0) * rng.uniform(0, 1) ** 1.2) * zl
            if kind == "soft" and zone in ("temple", "sideburn") and not back:
                # (what hangs in front of the ear is short: a fringe; a dozen 10 cm hangers a side were a comb down the
                # cheek in profile, th_T51. The long ones are the tucked and the loose)
                ln *= rng.choice([0.45, 0.45, 0.7, 1.0])
            if kind == "baby":
                ln = rng.uniform(0.012, 0.04) * (0.7 if zone == "part" else 1.0)
            elif kind == "loose":
                ln = rng.uniform(0.09, 0.16) * (1.0 if zone == "temple" else 1.1)
            if back:
                ln = max(ln, 0.07) * 1.2
            ds = ln / (m - 1)
            dist, nrm = _surface(sc, col, p[None])
            nrm = nrm[0]
            g_t = DOWN - (DOWN @ nrm) * nrm
            # the first direction lies ON the skin: out to its own side at the part / front (the hair off a part
            # falls outward over the forehead's corner), down in front of the ear, down the nape
            if zone in ("part", "front"):
                d = sidev * rng.uniform(0.5, 1.2) + _unit(g_t) * rng.uniform(0.3, 0.8)
            elif zone == "nape":
                d = _unit(g_t) + 0.3 * rng.normal(0, 1, 3)
            else:
                # (down in front of the ear, a little back if anything: started forward they ran across the cheek
                # toward the nose, th_T43)
                d = _unit(g_t) + np.array([0.0, -1.0, 0.0]) * rng.uniform(-0.6, 0.12)
            if back:
                to = tie_d - (tie_d @ nrm) * nrm
                to[2] = min(to[2], 0.0)
                d = _unit(to + 1e-9) + 0.5 * _unit(g_t)
            if comb:  # back into the hair, each a little its own way
                to = tie_d - (tie_d @ nrm) * nrm
                if abs(float(_wrap(az))) < 60.0:  # (the front is combed to the back's middle, up over the head)
                    to = np.array([0.0, 1.0, 0.25]) + 0.5 * sidev
                    to = to - (to @ nrm) * nrm
                d = _unit(to + 1e-9) + 0.7 * rng.normal(0, 1, 3)
            d = _unit(d - (d @ nrm) * nrm)
            fall = rng.uniform(5.0, 11.0) * (1.6 if zone in ("part", "front") else 1.0)  # per metre: how fast it turns down
            if comb:
                fall *= 0.25
            elif kind == "loose":
                fall *= 0.8
            cu0 = rng.normal(0, 1) * 6.0 * (0.4 + soft)  # its slow curl in the surface (rad per metre) ...
            # (at 6-16 rad / m every 4-9 cm, with a 4.5 cm strand wave on top, they were wet ringlets on the face)
            cu1, lam_c, ph_c = rng.uniform(8.0, 18.0) * (0.4 + soft), rng.uniform(0.05, 0.11), rng.uniform(0, 2 * np.pi)
            if kind == "baby":  # (short: it turns faster; a 3 cm hair with a 10 cm curl is a straight bristle)
                cu0, cu1, lam_c = cu0 * 4.0, cu1 * 2.0, lam_c * 0.4
            elif kind == "loose":  # (one slow curve, not a wriggle)
                cu0, cu1 = cu0 * 0.5, cu1 * 0.35
            gap0 = 0.0015 + 0.002 * rng.uniform(0, 1)
            sweep, drop = rng.uniform(0.5, 1.1), rng.uniform(10.0, 26.0)
            P = [p]
            for i in range(m - 1):
                s_ = i * ds
                dist, nrm = _surface(sc, col, P[-1][None])
                dist, nrm = float(dist[0]), nrm[0]
                g_t = DOWN - (DOWN @ nrm) * nrm
                hang = float(np.clip((dist - 0.006) / 0.006, 0, 1))  # off the skin: plain gravity
                pull = hang * DOWN + (1 - hang) * g_t
                az_, el_, _ = sc.coords(P[-1][None])
                if back:  # drawn back toward the tie, drooping on the way; it never arrives
                    oo = dirs(az_[0], el_[0])
                    to = tie_d - (tie_d @ oo) * oo
                    to[2] = min(to[2], 0.0)  # (toward a top knot they climbed the temple as dark blades: back, never up)
                    w_ = 1 - _ss_t((s_ / ln - 0.55) / 0.45)
                    pull = 0.8 * w_ * _unit(to) + (0.25 + 0.75 * (1 - w_)) * pull
                elif comb:
                    pass
                elif zone in ("part", "front"):
                    # the front's wisps go the way the hair was combed: out along the hairline toward the temple,
                    # drooping below it, and only then down. Falling straight from the part they hung over the eyes
                    # as vertical wires (th_T41)
                    sw = dirs(az_[0] + side * 3.0, el_[0]) - dirs(az_[0], el_[0])
                    sw = _unit(sw - (sw @ nrm) * nrm)
                    w_ = 1 - _ss_t((s_ / ln - 0.6) / 0.4)
                    pull = sweep * w_ * sw + (0.3 + 0.7 * (1 - w_)) * pull
                elif zone in ("temple", "sideburn"):  # beside the face they keep to the hair's side of it
                    sw = dirs(az_[0] + side * 3.0, el_[0]) - dirs(az_[0], el_[0])
                    sw = _unit(sw - (sw @ nrm) * nrm)
                    fa_ = abs(float(_wrap(az_[0])))
                    pull = pull + (0.12 + 0.9 * (1 - _ss_t((fa_ - 38.0) / 20.0))) * sw
                curl = cu0 + cu1 * np.sin(2 * np.pi * s_ / lam_c + ph_c)
                d = _unit(d + fall * ds * pull + curl * ds * np.cross(nrm, d))
                if back and d[2] > 0:  # (a tucked one never climbs: its curl took it up the head behind the ear)
                    d = _unit(d * np.array([1.0, 1.0, 0.0]) + 1e-9)
                if dist < 0.008:  # near the skin it lies along it
                    d = _unit(d - max(float(d @ nrm), 0.0) * nrm)
                q = P[-1] + ds * d
                dq, nq = _surface(sc, col, q[None])
                dq, nq = float(dq[0]), nq[0]
                az_, el_, _ = sc.coords(q[None])
                # (only the tucked ones ride over the gathered hair; the rest come out from under it at the hairline:
                # all of them lifted, the far temple's stood 1 cm off the head as a lace fringe)
                gap = gap0 + (over * _ss_t(i / 6.0) if back and float(inside(sc, line, az_[0] % 360, el_[0])) > 0.004 else 0.0) \
                    + 0.005 * soft * (s_ / ln) ** 2
                if dq < gap:
                    q = q + (gap - dq) * nq
                elif dq < 0.02 and nq[2] > -0.35:  # ... and hugs it: down onto skin that faces up or sideways
                    # (all the way: pulled 60% a step, a wisp running sideways off the part left the forehead's
                    # corner as a horizontal wire into the air)
                    q = q - (dq - gap) * nq
                if zone in ("part", "front") and i > 1:  # ... and never further down the forehead than ~2.5 cm
                    aq, eq, hq = sc.coords(q[None])
                    fq = abs(float(_wrap(aq[0])))
                    lo_ = float(_line_at(line, aq[0] % 360)) - drop
                    if fq < 48.0 and eq[0] < lo_:
                        q = sc.point(aq[0], lo_, float(hq[0]))
                d = _unit(q - P[-1])
                P.append(q)
            P = np.asarray(P)
            nh = int(rng.integers(int(h0), int(h1) + 1))
            width = (0.0025 + 0.006 * soft) * rng.uniform(0.6, 1.4) * min(1.0, 0.5 + ln / 0.12)
            if kind == "baby":
                nh, width = int(rng.integers(2, 6)), rng.uniform(0.0015, 0.004)
            elif kind == "loose":
                nh, width = int(rng.integers(18, 45)), rng.uniform(0.006, 0.011)
            elif zone == "sideburn":  # (it hangs straight down bare skin: 20 hairs there were a dark blade in front of
                # the ear, th_Q5: fewer, wider apart)
                nh, width = max(4, nh // 2), width * 1.4
            locks[f"{pre}w{'b' if kind == 'baby' else 'l' if kind == 'loose' else ''}{k}"] = {
                "tier": "tie", "space": "xyz", "pts": _xyz(sc, np.vstack([P[:-1:2], P[-1:]])), "free": 1.0,
                "width": round(float(width), 4), "thickness": 0.0015, "taper": 0.55, "belly": 0.4, "root": 0.45,
                "cup": 0.0, "hairs": nh,
                "strands": {"wisp_fan": round((0.6 + 1.2 * soft) * (0.5 if kind == "loose" else 1.0), 2), "wisp_round": 0.3,
                            "tip_loss": 0.6 if kind == "loose" else 0.75,
                            "wave": round(0.002 + 0.004 * soft, 4), "wavelength": 0.08, "random": 1.0, "flat": 1.0,
                            "curl": 0.0, **(ws.get("strands") or {})}}
            k += 1
    return locks


# ------------------------------------------------------------------------------------------------ the style

HEIGHTS = {"nape": -25.0, "low": -6.0, "mid": 15.0, "high": 40.0, "top": 65.0}
SIDES = {"centre": 0.0, "center": 0.0, "left": 30.0, "right": -30.0}
TIED = {
    "tie": "low",         # where the tie sits: nape | low | mid | high | top, or degrees of elevation from the head centre
    "side": "centre",     # centre | left | right (the person's own), or degrees round from the back's middle (+ = left)
    "tightness": 0.5,     # 0 = loose (hair sags between root and tie, stands off the head, hangs over the hairline)
                          # .. 1 = scraped back tight and flat
    "lift": None,         # 0..1: volume at the roots and over the top (default: 1 - tightness)
    "part": "centre",     # centre | left | right | none (none = combed straight back)
    "ears": "tucked",     # tucked (the hair passes over the ears' tops, behind them) | covered (it hangs over them)
    "tail": {},           # {"kind": "tail" | "bun" | "plait" | "none", "length": m, "fullness": 0..1, "wave": 0..1,
                          #  "to": "back" | "shoulder"}
    "wisps": None,        # the short soft hair that never reached the tie, as small clumps of fine hairs that fall
                          # along the face: an amount 0..1, or {"amount": 0..1, "where": ["part", "front", "temple",
                          # "sideburn", "nape"], "length": [m, m], "softness": 0..1 (0 = small defined locks, 1 = wide
                          # and frizzy)}; default by neatness (none on a neat head)
    "escaped": None,      # single stray HAIRS (wires alone: wisps are the soft ones): a count a side, or {"count":
                          # n | [right, left], "where": ["part", "temple", "ear", "nape"], "length": [m, m]}; default 0
    "hairline": None,     # 0..1: how SOFT the hair's edge is: 0 = a clean hard line (gelled, a wig's edge) .. 1 = the
                          # hairline thins out over a cm, with baby hairs along it and a part that wanders; default
                          # 0.8 - 0.3 x neatness (every real hairline is soft; only its amount is style)
    "neatness": 0.5,      # 0 = slept in (strays, a halo, uneven) .. 1 = every hair in place
    "half": False,        # true = half up: only the top section is tied, the rest hangs loose (`length` m of it)
    "length": 0.3,        # m: the loose hair's length for half up
    "detail": None,       # {"tie": {...}, "strands": {...}}: overrides of what the style makes (hair_tied's own keys)
}
TAIL = {"kind": "tail", "length": 0.25, "fullness": 0.5, "wave": 0.3, "to": "back", "tousle": None}
# tousle 0 = brushed (locks apart, an even end, nothing leaves the outline) .. 1 = tousled (a ragged end, stray hairs
# all round, strands crossing); default 0.05 + 0.75 x wave
# fullness 0 = a sleek thin tail .. 1 = bushy (the bundle's radius 1.8 .. 6 cm, more locks, more air and frizz);
# wave 0 = straight .. 1 = loose waves (every lock its own, 1.6 cm of swing at 1)
WISP_STYLE = {"amount": 0.5, "where": ["part", "front", "temple", "sideburn"], "length": [0.04, 0.12], "softness": 0.6,
              "loose": None}  # loose: THICK loose locks a side (forehead corner / temple); default round(2.5 x amount)
# the strand dials a tied style starts from (spec["hair"]["strands"] wins)
STRANDS = {"count": 70000, "thickness": 0.7, "flat": 1.4, "clump_size": 0.004, "stray": 0.8, "roots": 1.0, "under": 1.6,
           "under_length": 0.025, "soft": 0.022, "tips": 0.6, "tip_spread": 0.6, "wavelength": 0.12}


def _deep(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in (b or {}).items():
        out[k] = _deep(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def style_params(tied: dict) -> dict:
    bad = set(tied) - set(TIED)
    if bad:
        raise ValueError(f"hair tied: unknown keys {sorted(bad)} (have {', '.join(sorted(TIED))})")
    p = {**TIED, **tied}
    tl = p["tail"]
    if tl is False or tl is None:
        tl = {"kind": "none"}
    if isinstance(tl, str):
        tl = {"kind": tl}
    bad = set(tl) - set(TAIL)
    if bad:
        raise ValueError(f"hair tied tail: unknown keys {sorted(bad)} (have {', '.join(sorted(TAIL))})")
    p["tail"] = {**TAIL, **tl}
    if p["tail"]["kind"] not in ("tail", "bun", "plait", "none"):
        raise ValueError(f"hair tied tail.kind {p['tail']['kind']!r}: one of tail, bun, plait, none")
    if not isinstance(p["tie"], (int, float)) and p["tie"] not in HEIGHTS:
        raise ValueError(f"hair tied tie {p['tie']!r}: one of {', '.join(HEIGHTS)} or degrees")
    if not isinstance(p["side"], (int, float)) and p["side"] not in SIDES:
        raise ValueError(f"hair tied side {p['side']!r}: one of centre, left, right or degrees")
    if p["part"] not in ("centre", "center", "left", "right", "none"):
        raise ValueError(f"hair tied part {p['part']!r}: one of centre, left, right, none")
    if p["ears"] not in ("tucked", "covered"):
        raise ValueError(f"hair tied ears {p['ears']!r}: tucked or covered")
    return p


def style(tied: dict) -> dict:
    """{"tie": .., "parting": .., "strands": .., "loose": ..?}: what a `groom.tied` style makes (hair_tied's tie, the
    groom's parting, strand dials under the spec's own, loose hair for half up)."""
    p = style_params(tied)
    el = float(p["tie"]) if isinstance(p["tie"], (int, float)) else HEIGHTS[p["tie"]]
    off = float(p["side"]) if isinstance(p["side"], (int, float)) else SIDES[p["side"]]
    az = (180.0 - off) % 360.0
    T = float(np.clip(p["tightness"], 0, 1))
    lo = 1.0 - T
    lift = lo if p["lift"] is None else float(np.clip(p["lift"], 0, 1))
    N = float(np.clip(p["neatness"], 0, 1))
    me = 1.0 - N
    hs = float(np.clip(0.8 - 0.3 * N if p["hairline"] is None else p["hairline"], 0, 1))
    tl = p["tail"]
    wave = float(np.clip(tl["wave"], 0, 1))
    fu = float(np.clip(tl["fullness"], 0, 1))
    # (by the wave: a straight sleek tail is brushed. At 0.25 + 0.5 x wave a sleek high ponytail ended in chopped
    # chunks at five heights, th_S1)
    to_ = float(np.clip(0.05 + 0.75 * wave if tl.get("tousle") is None else tl["tousle"], 0, 1))
    full = 0.018 + 0.042 * fu
    gather = {"mode": "flow", "spacing": 0.02, "uneven": round(0.2 + 0.6 * me, 3),
              "puff": round(0.002 + 0.016 * lift, 4), "root_lift": round(0.0015 + 0.008 * lift, 4),
              "body": round(0.005 + 0.005 * lo, 4), "sag": round(2.6 * lo, 3), "overhang": round(22.0 * lo, 2),
              "ears": 14.0 if p["ears"] == "covered" else 0.0, "part_length": round(0.035 + 0.06 * lo, 4),
              "hairline_strands": {"density": 1.6, "roots": 0.3}, "feather": 1.0,
              "edge": round(hs, 3), "zig": round(0.0045 * hs, 4),
              "strands": {"wave": round(0.004 + 0.008 * lo, 4), "wavelength": 0.07, "random": 0.8, "flat": 1.5,
                          "flyaway": 0.0}}
    tie = {"at": [round(az, 1), el], "out": round(0.022 + 0.012 * lo, 4), "escape": 0, "gather": gather}
    kind = tl["kind"]
    if kind == "none":
        tie["tail"] = False
    else:
        tail_ = {"length": float(tl["length"]), "fullness": round(full, 4), "locks": int(round(26 + 30 * fu)),
                 "uneven": round(0.3 + 0.7 * me, 3), "taper": 0.3,
                 "strands": {"wave": round(0.03 * wave, 4), "wavelength": 0.16, "random": 0.7, "clump": 0.35, "flat": 2.5,
                             "clump_size": 0.008, "tips": 1.0, "tip_spread": 0.1}}
        if kind == "bun":
            tail_.update({"coil": 2.2, "coil_radius": round(0.02 + 0.02 * tl["fullness"], 4), "length": max(float(tl["length"]), 0.2)})
        elif kind == "plait":
            tail_.update({"plait": True, "stiff": 0.3, "fullness": round(0.6 * full, 4)})
        else:
            # a tail hangs: it stands out of a high tight tie a little longer than out of a low loose one
            # ... and it has VOLUME (tesshair4): the radius set along it (bulge), every lock its own wave, locks a
            # little apart toward their ends, an uneven end; the strands of a lock end over its last third and its
            # section stays open (thin locks that taper = strings, th_W1; all strands to the end = planks)
            tail_.update({"hang": True, "stiff": round(0.2 + 0.1 * float(np.clip((el + 10) / 60, 0, 1)) + 0.04 * T, 3),
                          "spread": round(0.25 + 0.45 * fu, 3), "sway": round(0.012 * wave, 4),
                          "sway_length": 0.21, "flick": round(0.01 * wave + 0.006 * fu + 0.014 * to_, 4),
                          "bulge": 1.0, "lock_wave": round(0.001 + 0.012 * wave, 4),
                          "lock_wavelength": round(0.12 - 0.025 * wave, 4), "air": round(0.002 + 0.004 * fu, 4),
                          "uneven": round(max(0.3 + 0.7 * me, 0.35 + 0.3 * fu), 3), "taper": round(0.3 - 0.15 * fu, 3),
                          "ragged": round(0.25 + 0.75 * to_, 3), "strays": int(round((10 + 50 * to_) * (0.5 + fu))),
                          "in_step": 0.7,
                          "strands": {"wave": round(0.006 * wave, 4), "wavelength": 0.16, "random": 1.0,
                                      # (tousled ends are POINTED wisps: strands gather toward their tips (free.
                                      # clump_shape) and do not open again; open, each lock ended as a flat 2 cm
                                      # chunk, a chopped broom from behind, th_T52)
                                      "clump": round(0.3 - 0.15 * fu + 0.3 * to_, 3), "flat": 2.5, "clump_size": 0.006,
                                      "tips": 0.9, "tip_spread": round(0.6 - 0.5 * to_, 3),
                                      # (more strands than its share: thin, a full tail is strings with the backdrop
                                      # between them)
                                      "density": round(1.0 + 0.8 * to_, 2)}})
            if tl["to"] == "shoulder":  # brought forward over the shoulder on the tie's side (the left when centred)
                sd = 1.0 if off >= 0 else -1.0
                tail_["dir"] = [round(0.75 * sd, 3), -0.35, -0.55]
            elif tl["to"] != "back":
                raise ValueError(f"hair tied tail.to {tl['to']!r}: back or shoulder")
        tie["tail"] = tail_
    wsp = p["wisps"]
    if wsp is None:
        wsp = round(float(np.clip(1.25 * (me - 0.1), 0, 1)), 3)
    if isinstance(wsp, (int, float)) and not isinstance(wsp, bool):
        wsp = {"amount": float(wsp)}
    if wsp:
        bad = set(wsp) - set(WISP_STYLE)
        if bad:
            raise ValueError(f"hair tied wisps: unknown keys {sorted(bad)} (have {', '.join(sorted(WISP_STYLE))})")
        wsp = {**WISP_STYLE, **wsp}
        am, so = float(np.clip(wsp["amount"], 0, 1)), float(np.clip(wsp["softness"], 0, 1))
        n_w = int(round(24 * am))
        if n_w > 0:
            tie["wisps"] = {"count": n_w, "where": list(wsp["where"]), "length": [float(v) for v in wsp["length"]],
                            "softness": so, "hairs": [6, int(round(14 + 14 * so))],
                            "tuck": 0.45, "over": round(0.004 + 0.006 * lift, 4),
                            # (none by default toward a high tie: the lock cannot lie back over the temple, it
                            # hangs down the cheek as a strap, th_S5)
                            "loose": (int(round(2.5 * am)) if el < 30.0 else 0) if wsp["loose"] is None else int(wsp["loose"])}
    if hs > 0:  # the hairline's own baby hairs belong to the EDGE, not to the wisps: a neat head has them too
        w0 = tie.get("wisps") or {"count": 0, "where": list(WISP_STYLE["where"]), "length": list(WISP_STYLE["length"]),
                                  "softness": 0.6, "hairs": [6, 20], "tuck": 0.3, "over": 0.006}
        tie["wisps"] = {**w0, "baby": int(round(70 * hs))}
    es = p["escaped"]
    if es is None:
        es = 0
    if isinstance(es, (int, float)):
        es = {"count": int(es)}
    if es and es.get("count"):
        tie["escaped"] = {"where": ["ear", "temple", "nape", "ear"], "length": [0.04, 0.12], "curve": 0.3, **es}
    out = {"parting": {"side": "none"} if p["part"] == "none" else
           {"side": "centre" if p["part"] == "center" else p["part"], "offset": 0.03, "length": round(0.035 + 0.06 * lo, 4),
            "width": 0.004, "depth": 0.2},
           "strands": {**STRANDS, "loose": round(0.15 + 0.6 * me, 3), "frizz": round(0.08 + 0.25 * me, 3),
                       "flyaway": round(0.03 + 0.25 * me, 3), "halo": round(0.45 * me, 3), "baby": round(0.5 + 2.5 * me, 2),
                       "clump": 0.2,
                       # (the tail: a full one is airier and frizzier whatever the head's neatness; its sub clumps
                       # swing out of step by `wave`)
                       # (tousle is NOT strand wander: at loose 0.45 every strand of the tail wriggled on its own, a
                       # crimped wet mop, th_T51; the tousle is in the locks: ragged, strays, flyaways)
                       "free": {"loose": round(0.1 + 0.25 * me + 0.2 * fu, 3),
                                "frizz": round(0.1 + 0.3 * me + 0.3 * fu + 0.2 * to_, 3),
                                "flyaway": round(0.15 + 0.7 * me + 0.25 * fu + 0.1 * to_, 3), "stray": round(0.6 + 0.3 * to_, 3),
                                # (sub clumps each on their own swing were pasta inside the locks: nearly in step)
                                "wave": round(0.008 * wave, 4), "wavelength": 0.1, "random": 0.35,
                                "clump_shape": round(0.6 + 0.35 * to_, 3), "tip_spread": round(0.6 - 0.5 * to_, 3)},
                       # (thickness 1.0 against the head's 0.7: at the head's strand width a clump of 6-28 hairs was a faint
                       # fuzz in EEVEE and nearly gone in Cycles, th_T47)
                       "wisp": {"loose": 0.25, "frizz": 0.2, "wave": 0.004, "wavelength": 0.08, "random": 1.0,
                                "thickness": 1.0}}}
    if p["half"]:
        gather["above"] = 0.012
        out["loose"] = {"length": float(p["length"]), "below": 0.03, "lift": 0.004, "face": 1.0}
    d = p.get("detail") or {}
    bad = set(d) - {"tie", "strands", "parting", "loose"}
    if bad:
        raise ValueError(f"hair tied detail: unknown keys {sorted(bad)} (have tie, strands, parting, loose)")
    out["tie"] = _deep(tie, d.get("tie") or {})
    for k_ in ("strands", "parting", "loose"):
        if d.get(k_):
            out[k_] = _deep(out.get(k_) or {}, d[k_])
    return out
