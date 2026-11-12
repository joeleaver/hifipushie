"""The gather: roots, paths over the head, and `gather`. Part of hair flow (hair_flow.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import hair_flow
from .hair_tied import DOWN, _ss_t, _unit
from .hair_flow import _wrap

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
    from .hair_drawn import top_to_azel
    from .hair_groom import _line_at, _poisson, inside
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
        # (the row itself is not ruled: at the temples its roots stand up to ~7 mm inside the line, each its own depth
        # (no random draw: the stream stays). On one line, locks that run straight off it were a saw, tesshair6)
        fa = np.abs(_wrap(az_h))
        jit = (np.arange(len(az_h)) * 0.6180339887) % 1.0
        el_h = el_h + 5.0 * edge * jit * _ss_t((fa - 28.0) / 14.0) * (1.0 - _ss_t((fa - 105.0) / 10.0))
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


def paths(sc, line, D0, tie_d, xp, ga: dict, rng, n: int = 12, t=None):
    """The way of each root (unit directions D0 from the head centre) over the head to the tie: (m, n, 3) unit
    directions, and each way's length (radians). `t`: where along the way the n points stand (default evenly)."""
    from .hair import az_el, dirs
    from .hair_groom import _line_at
    D = _unit(np.array(D0, float))
    m = len(D)
    tie_d = _unit(np.asarray(tie_d, float))
    step = np.radians(hair_flow.STEP_DEG)
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
    # THE FRONT ON ITS OWN (tesshair6, gather.front {"loose", "drape"}): hair off the part and the forehead's corners
    # hangs looser than the rest of a held-back head: more sag for roots in front of the ears (loose), and its way may
    # pass further below the hairline over the forehead's corners and temples (drape, deg). One tightness for the
    # whole head gave either a neat held-back arc or a loose head all round
    fr_ = ga.get("front") or {}
    f_loose, f_drape = float(fr_.get("loose") or 0.0), float(fr_.get("drape") or 0.0)
    if f_loose > 0:
        sag = sag + 1.4 * f_loose * (1.0 - _ss_t((np.abs(_wrap(a0)) - 55.0) / 30.0))
    # (the front and temples hang most: hair off the part falls out over the temple; behind the ears it is on its way)
    frontw = 1.0 - 0.7 * _ss_t((np.abs(_wrap(a0)) - 80.0) / 40.0)
    yf = sc.C[1] - float(sc.r(0.0, 30.0)) * np.cos(np.radians(30.0))  # the scalp's front (as hair._part)
    plen = float(ga["part_length"])
    tz, te = az_el(tie_d)
    mid_d = dirs(180.0, float(te))  # the tie brought to the back's middle: what the FRONT of the head is combed to
    e_ear = 0.5 * (float(_line_at(line, 95.0)) + float(_line_at(line, 265.0)))  # the hairline over the ears
    tie_in = float(te) > float(_line_at(line, float(tz))) + 2.0  # (a tie below the hairline: no keep-in near it)
    # THE ARC (tesshair7, gather.volume.arc; Joe's red lines on her picture: three nested convex arcs from the part up,
    # out and down the side to the temple, ours straight diagonals to the tie): loose hair first FALLS from its root,
    # down the head on its own side (off a part: sideways out of it while the head is still flat), and only then is
    # taken back by the tie. `arc` is how much of the first stretch (arc_len rad) belongs to the fall
    vo_ = ga.get("volume") or {}
    arc = float(vo_.get("arc") or 0.0)
    arc_len = float(vo_.get("arc_length") or 0.6)
    # (not the hair that is already on its way: rooted near the tie, or under it)
    arc_w = arc * np.minimum(ang0 / (np.pi / 2), 1.0) ** 2 * _ss_t((e0 - float(te)) / 25.0)
    trav = np.zeros(m)
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
        to[lost] = np.cross(D[lost], hair_flow.X) + 1e-3
        to = _unit(to)
        az, el = az_el(D)
        v = to.copy()
        near = _ss_t((ang - np.radians(12)) / np.radians(20))  # (the last stretch runs straight into the tie)
        if push > 0:  # combed away from the parting, on its own side
            Q = sc.point(az, el, 0.0)
            wp = np.exp(-((Q[:, 0] - sc.C[0] - xp) / 0.035) ** 2) * (1 - _ss_t((Q[:, 1] - yf - plen) / 0.03)) \
                * _ss_t((el - 20) / 15)
            aw = side[:, None] * hair_flow.X[None]
            aw = aw - (aw * D).sum(1, keepdims=True) * D
            v = v + (push * wp * near)[:, None] * aw
        if np.any(sag > 0):  # loose hair hangs between its root and the tie: down the head, on its own side on top
            prog = 1 - ang / np.maximum(ang0, 1e-6)
            # (most just after the root: hair off a part falls outward over the temple before the tie takes it)
            # (only where the head is steep: on top the hair lies on it, and a pull to each side there opened the part
            # into a furrow all the way over the crown; never forward: swept-back hair doesn't hang over the face)
            dn = DOWN[None] - (D @ DOWN)[:, None] * D
            dn = dn * np.linalg.norm(dn, axis=1, keepdims=True)
            dn[:, 1] = np.maximum(dn[:, 1], -0.6 * np.linalg.norm(dn, axis=1))  # (forward only a little: over the forehead's corners)
            v = v + (sag * frontw * np.sin(np.pi * np.clip(prog, 0, 1) ** 0.35) * np.minimum(ang0 / (np.pi / 2), 1.0) * near)[:, None] * dn
        v = _unit(v)
        thr = 0.35
        if arc > 0:
            # (not from the first mm: tied hair was pulled BACK first, so off a part it leans back along the part before
            # it falls out of it; falling sideways at once, the two banks stood apart as a wide open valley, th_V70)
            wa = arc_w * _ss_t(trav / 0.12) * (1.0 - _ss_t(trav / arc_len)) * near
            # (... and the fall ends well above where the hair may hang to: falling all the way to that line, every
            # way then ran along it and the side was a bob's curtain with a thick lower edge over the ear, th_V73)
            fa_ = np.abs(_wrap(az))
            lim_ = np.maximum(_line_at(line, az) + 1.0, np.where((fa_ > 40) & (fa_ < 120), e_ear + 4.0, -90.0))
            # (over the forehead's corners it may come down to the line: held 8 deg above it there, the corners were
            # left to the thin edge band alone, a grey veil over skin, th_V77/78)
            side_ = _ss_t((fa_ - 35.0) / 15.0)
            wa = wa * _ss_t((el - lim_ - 8.0 * side_) / (6.0 + 12.0 * side_))
            dn = DOWN[None] - (D @ DOWN)[:, None] * D  # (its length = how steep the head is here)
            stp = np.linalg.norm(dn, axis=1)
            fall = dn
            if xp is not None:
                Q = sc.point(az, el, 0.0)
                inpart = 1.0 - _ss_t((Q[:, 1] - yf - plen) / 0.04)
                lat = side[:, None] * hair_flow.X[None]
                lat = lat - (lat * D).sum(1, keepdims=True) * D
                fall = dn + (inpart * (1.0 - stp))[:, None] * lat
            fl_ = np.linalg.norm(fall, axis=1)
            fall[:, 1] = np.maximum(fall[:, 1], 0.0)  # (never forward: at -0.3 the front hung as a bob's curtain, th_V70)
            wf = (wa * np.minimum(fl_, 1.0))[:, None]
            v = _unit((1.0 - wf) * v + wf * 1.6 * fall)
            thr = 0.35 - 0.8 * wa  # (falling, a way may run across the tie's direction, even a little off it)
        low = (v * to).sum(1) < thr  # (always on toward the tie)
        v[low] = _unit(v[low] + to[low])
        st = np.minimum(step, ang)
        trav = trav + st
        Dn = _unit(D * np.cos(st)[:, None] + v * np.sin(st)[:, None])
        # the way stays in the hair: above the hairline (so over the ears' tops, not across the temples' skin or the
        # ear), but for `overhang` deg at the front and temples and `ears` deg round the ears
        az, el = az_el(Dn)
        fa = np.abs(_wrap(az))
        lim = _line_at(line, az) + 1.0 - float(ga["overhang"]) * _ss_t((fa - 4) / 22) * (1 - _ss_t((fa - 62) / 22)) \
            - float(ga["ears"]) * np.exp(-((fa - 95) / 22) ** 2) \
            - 11.0 * f_drape * _ss_t((fa - 8) / 14) * (1 - _ss_t((fa - 56) / 20))
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
    t = np.linspace(0, 1, n) if t is None else np.asarray(t, float)
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
    from .hair import az_el, dirs
    from .hair_groom import _line_at, _part_x
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
    t = np.linspace(0, 1, n)
    # VOLUME (tesshair7, gather.volume; Joe: "it's flat"): the hair STANDS UP out of its root and bends over (a rise
    # with a bend radius, not a shell offset by a few mm), carries a dome over the crown / the sides / the nape, in
    # LAYERS (each lock its own height: the mass has thickness, the under-layers lie tighter), and is drawn in to the
    # tie only over the last stretch (hold). More points near the root: the bend is 1-2 cm long
    vo = ga.get("volume") or None
    if vo and max(float(vo.get(k_) or 0.0) for k_ in ("crown", "side", "nape")) <= 0 and not vo.get("arc"):
        vo = None
    if vo:
        n = 18
        t = np.linspace(0, 1, n) ** 1.6
    D, w0 = paths(sc, line, dirs(az, el), tie_d, xp, ga, rng, n, t)
    r_med = float(np.median(sc.R))
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
            # (under hair with VOLUME the band is seen: the mass stands up behind it instead of lying over it, and 1-2 cm
            # of thin fine hair on the forehead's corners was a grey veil over skin, th_V75/76: full by 5 mm there too)
            v_b = float(np.clip((max(float((ga.get("volume") or {}).get(k_) or 0.0) for k_ in ("crown", "side")) - 0.006) / 0.008, 0.0, 1.0))  # (not on a near-sleek head)
            ramp = float(_ss_t(din[i] / ((0.6 - 0.35 * max(strip, v_b)) * sp)))
            onp = 0.35 + 0.45 * ramp
        f_l = float((ga.get("front") or {}).get("loose") or 0.0)
        if f_l > 0:  # (a loose front stands off the head at its roots: the rest stays as tight as the style)
            onp = onp * (1.0 + 1.4 * f_l * float(1.0 - _ss_t((abs(float(_wrap(az[i]))) - 50.0) / 30.0)))
        puff = onp * float(ga["puff"]) * (0.4 + 0.6 * top) * min(w0[i] / np.radians(50), 1.0) * (1 + un * rng.uniform(-0.5, 0.9))
        lift = onp * float(ga["root_lift"]) * (1 + un * rng.uniform(-0.3, 0.5))
        ride = 0.002 + float(ga["body"]) * far
        h = (1 - t ** 3) * (ride * np.minimum(t * 6, 1) + lift * _ss_t(t / 0.15) * (1 - 0.5 * t) + puff * np.sin(np.pi * t) ** 0.9) \
            + t ** 3 * float(tp["out"]) * 0.8
        if vo:
            u_l = (i * 0.6180339887 + 0.37) % 1.0  # the lock's layer (no draw: the random stream stays)
            if hl[i] == 1:
                # (the hairline's own narrow locks all at ONE height: each at its own, side by side and parallel
                # where the hair runs straight off the line (a high ponytail, a top knot), they were pleats, th_V9a3)
                u_l = 0.6
            lay = 1.0 - float(np.clip(vo.get("layers", 0.7), 0, 1)) * (1.0 - u_l ** 0.6)
            s_m = w0[i] * r_med * t  # m along the way
            rb = max(float(vo.get("rise", 0.012)) * (0.6 if hl[i] == 1 else 0.75 + 0.5 * ((i * 0.7548776662) % 1.0)), 1e-3)
            if xp is not None:
                # (the banks of a part stand up at once: at the general bend radius the two banks leaned apart and
                # the part was a 2 cm wide valley, the head a heart with two lobes from the front, th_V73)
                p0_ = sc.point(az[i], el[i], 0.0) - sc.C
                dx_ = float(p0_[0] - xp - _zig(ga, p0_[1] + float(sc.r(0.0, 30.0)) * np.cos(np.radians(30.0))))
                rb = rb * (1.0 - 0.65 * float(np.exp(-(dx_ / 0.02) ** 2)))
            rise = 1.0 - np.exp(-s_m / rb)
            er = np.radians(ee)
            wc = np.clip(np.sin(er), 0.0, 1.0) ** 1.5  # over the top
            wn = _ss_t((np.abs(_wrap(aa)) - 105.0) / 40.0) * (1.0 - _ss_t((ee + 5.0) / 35.0))  # the nape
            fa_p = np.abs(_wrap(aa))
            wb_ = _ss_t((fa_p - 100.0) / 40.0)  # the BACK of the head: the dome runs on down to the tie there
            # (the sides are fullest above the temple and lie close where the hair passes over the ear: full down to
            # the ear the head was widest at the cheek, a bob, th_V74; hers is widest high and tapers in to the ear)
            sd_ = float(vo.get("side") or 0.0) * (0.3 + 0.7 * _ss_t((ee - e_ear) / 24.0))
            bk_ = float(vo.get("crown") or 0.0) * (1 - wn) + float(vo.get("nape") or 0.0) * wn
            Hd = float(vo.get("crown") or 0.0) * wc + (1 - wc) * (sd_ * (1 - wb_) + bk_ * wb_)
            hold = float(np.clip(vo.get("hold", 0.5), 0, 1))
            th_ = 0.4 + 0.45 * hold
            env = 1.0 - _ss_t((t - th_) / max(1.0 - th_, 1e-3))
            # (the edge band rises less toward the line: it is the thin rim; hair rooted near the tie has no way to rise)
            # (the band's thin fine rim stays low: lifted, it was a grey gauze standing over the forehead's corners, th_V74)
            # (round two: the veil was the wisps, not this rim (th_V80). The hair over the forehead stands up from the
            # line itself: hers is 13-15 mm off the skull there, ours lay at 6-11)
            onv = (0.7 + 0.3 * ramp) if (edge > 0 and hl[i] == 1) else 0.85 if hl[i] == 1 else 1.0
            onv *= min(w0[i] / np.radians(40), 1.0) * (1 + (0.0 if hl[i] == 1 else 0.5) * un * rng.uniform(-0.5, 0.5))
            if hl[i] == 2:  # (the part's banks a little higher than the dome beside them: the two lobes meet over the
                # line instead of a notch between them, th_W13; rule 5)
                onv *= 1.2
            # LOCKS, not a shell (tesshair7 round two; Joe: "the color/texture ... dialed in"; the read: a smooth
            # helmet): `locks` 0..1 = each inner lock's height swells and sinks along it on its own wavelength, it
            # wanders sideways a little (locks cross), a few are LIFTED off the mass, widths differ, and its strands
            # gather into clumps of its own size (gaps with the darker under-layer showing between them)
            lk_ = float(np.clip(vo.get("locks", 0.0), 0, 1))
            hsh = [(i * c_ + o_) % 1.0 for c_, o_ in ((0.3819660113, 0.11), (0.5698402910, 0.53), (0.7548776662, 0.29), (0.2360679775, 0.71))]
            mod_ = 1.0
            lifted = False
            if lk_ > 0 and hl[i] != 1:
                lam_h = 0.05 + 0.06 * hsh[0]
                mod_ = 1.0 + 0.35 * lk_ * np.sin(2 * np.pi * s_m / lam_h + 2 * np.pi * hsh[1]) * _ss_t(s_m / 0.02)
                lifted = hsh[2] < 0.08 * lk_
                if lifted:
                    # (+ 25 %: at + 45 % the lifted locks stood over the dome as arches 3 cm off the skull, th_W02)
                    mod_ = mod_ * (1.0 + 0.25 * np.sin(np.pi * np.clip(t / 0.8, 0, 1)) ** 2)
                    lay = max(lay, 0.95)
            h = (1 - t ** 3) * (ride * np.minimum(t * 6, 1) + onv * lay * Hd * rise * env * mod_) + t ** 3 * float(tp["out"]) * 1.0
            if lk_ > 0 and hl[i] != 1:
                aa = aa + 2.5 * lk_ * np.sin(2 * np.pi * (1.0 + hsh[3]) * t + 2 * np.pi * hsh[0]) * np.sin(np.pi * t)
            if xp is not None and hl[i] == 2 and float(vo.get("cross", 0.0)) > 0 and hsh[1] < 0.5 * float(vo["cross"]):
                # hair CROSSES a part: a share of each bank's own locks leans over the line before it falls to its
                # side, so the part is no clean valley between two lobes (hers: short, soft, hair across it)
                Pw = sc.point(aa, ee, h)
                bump = np.exp(-((s_m - 0.014) / 0.012) ** 2)
                # (3-7 mm: at 5-14 mm the crossing locks stood as a dark scribbly tuft at the part's start, th_W05)
                Pw = Pw - (np.sign(dx_) or 1.0) * (0.003 + 0.004 * hsh[2]) * bump[:, None] * hair_flow.X[None]
                aa, ee, h = (np.asarray(v_, float) for v_ in sc.coords(Pw))
                h = np.maximum(h, 0.0)
            vo_thick = 0.25 * onv * float(np.max(Hd))  # (a lock of a standing mass is not a 4 mm sheet: layers run into each other)
            # (how deep in the mass this lock lies, 0 = the top layer: the look's `depth` darkens the under-layers,
            # the self-shadow EEVEE's strands do not cast on each other)
            vo_shade = round(float(np.clip(vo.get("layers", 0.7), 0, 1)) * (1.0 - u_l ** 0.6), 3)
        aa = aa + un * 4.0 * np.sin(np.pi * t) * rng.uniform(-1, 1)
        r = 0 if hl[i] == 1 else 1
        name = f"{pre}g{r}_{k[r]}"
        k[r] += 1
        # (with an edge: how near the hairline an INNER lock roots, 1 on it .. 0 from 3.5 cm in. The inner locks are
        # 4 cm planks whose strands all start on one line: beside the part, where they run along the hairline, their
        # sides and starts were the hard V and its stair steps (th_T51, drawn alone))
        nearf = 0.0
        if edge > 0 and hl[i] != 1:
            from .hair_groom import inside
            nearf = edge * (1.0 - float(_ss_t((float(inside(sc, line, az[i] % 360, el[i])) - 0.01) / 0.025))) \
                * (1.0 - float(_ss_t((abs(float(_wrap(az[i]))) - 60.0) / 30.0)))
        wx = (0.42 + 0.2 * ramp if edge > 0 else 0.6) if hl[i] == 1 else 1.9 - 0.5 * nearf
        lk = {"tier": "tie", "pts": [[round(float(aa[j]), 2), round(float(ee[j]), 2), round(float(h[j]), 4)] for j in range(n)],
              "width": round(sp * wx * (1 + un * rng.uniform(-0.3, 0.3))
                             * ((1.0 + lk_ * ((0.5 if lifted else 0.5 + 0.65 * hsh[3]) - 1.0)) if (vo and lk_ > 0 and hl[i] != 1) else 1.0), 4),
              "thickness": round(0.004 + (vo_thick if vo else 0.0), 4),
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
                # hair that runs straight AWAY from the line at the temple (an up-style: high ponytail, top knot)
                # shows every lock's start end-on: a row of teeth 8 mm wide (th_S1 / S5). Its strands start one by
                # one ACROSS the band (over the first 3-4.5 cm of the lock, which is the band's depth and more), the
                # lock is narrower and drawn finer: the edge is a gradient of single starts, not lock ends
                da_ = float(_wrap(aa[2] - aa[0])) * np.cos(np.radians(float(ee[0])))
                away = 1.0 - min(abs(da_) / max(float(np.hypot(da_, ee[2] - ee[0])), 1e-6), 1.0) ** 2
                away *= float(_ss_t((fa_i - 28.0) / 14.0) * (1.0 - _ss_t((fa_i - 105.0) / 10.0)))
                if away > 0.05:
                    st["roots_m"] = round(st["roots_m"] + away * (0.022 + 0.015 * ((i * 0.6180339) % 1.0)), 4)  # (no draw: the stream stays)
                    st["fine"] = round(float(np.clip(st["fine"] + 0.3 * away * (1.0 - ramp), 0.0, 1.0)), 3)
                    st["rim"] = round(st["rim"] + 0.8 * away, 2)
                    st["density"] = round(st["density"] * (1.0 - 0.7 * away * (1.0 - ramp)), 3)
                    lk["width"] = round(lk["width"] * (1.0 - 0.3 * away), 4)
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
                from .hair_groom import inside
                d_in = float(inside(sc, line, az[i] % 360, el[i]))
                nr = float(ga["feather"]) * (1 - float(_ss_t((d_in - 0.012) / 0.03))) * float(_ss_t((abs(float(_wrap(az[i]))) - 28.0) / 20.0))
                if nr > 0.05:
                    st["roots"] = round(max(st["roots"], nr), 3)
                    st["roots_x"] = 4.0
                    lk["root"] = round(0.8 - 0.55 * nr, 3)
        if vo and vo_shade > 0:
            st["shade"] = vo_shade
        if vo and hl[i] == 2:
            # the part's own banks stand up out of the line and are seen END-ON from the side: drawn opaque with dark
            # roots they were black tangled loops at the part's start in every three-quarter view (th_T66 .. th_W06;
            # isolated: not wisps, halo, wave, clumps, fly-aways, the arc or crossing: dropping these rows only moved
            # the loops to the next locks). Hers are fine light hairs there: drawn fine (no dark root), denser
            st["fine"] = 0.85  # (0.55 and density x 1.3: lighter but still a dark tangle end-on, th_W09 / W11)
            st["bank"] = 1.0 if dx_ >= 0 else -1.0  # (which bank: hair_flow_wisps.halo crosses the part from it)
            st["density"] = round(float(st.get("density", 1.0)) * 0.7, 3)  # (fewer: the end-on knot, th_W13)
        if vo:
            # where the sun reaches (the look's highlights gather there): the top layers, most round the face and
            # over the top; -0.5 .. 0.5
            fa0_ = abs(float(_wrap(az[i])))
            st["sun"] = round(float(np.clip((u_l ** 0.6) * (0.55 + 0.45 * (1.0 - _ss_t((fa0_ - 60.0) / 60.0))), 0, 1)) - 0.5, 3)
            if lk_ > 0 and hl[i] != 1:
                st["clump"] = round(0.2 + 0.4 * lk_, 3)
                st["clump_size"] = round(0.004 + 0.008 * lk_ * (0.5 + hsh[0]), 4)
                if lifted:
                    st["flyaway"] = 0.5
        if st:
            lk["strands"] = st
        locks[name] = lk
    return locks
