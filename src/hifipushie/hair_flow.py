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

def roots(sc, ga: dict, line, rng, xp=None):
    """(az, el, on_hairline) of the gather's roots: a row on the hairline, blue noise inside it, and a row along
    each bank of the parting (x = xp m from the middle; without them the nearest roots stood up to a spacing off the
    line and the part was a bare zigzag furrow)."""
    from .hair import _line_at, _poisson, inside, top_to_azel
    sp = float(ga["spacing"])
    a = np.arange(0.0, 360.0, 2.0)
    L = sc.point(a, _line_at(line, a), 0.0)
    seg = np.linalg.norm(np.diff(L, axis=0, append=L[:1]), axis=1)
    cum = np.r_[0.0, np.cumsum(seg)]
    # (the hairline row is fine and close: where the hair runs ALONG the line (temples, behind the ears) each lock's
    # start is a cut across it, and wide locks made the edge a saw)
    n_h = max(8, int(round(cum[-1] / (0.5 * sp))))
    s = (np.arange(n_h) + 0.5 + float(ga["uneven"]) * rng.uniform(-0.3, 0.3, n_h)) / n_h * cum[-1]
    az_h = np.interp(s, cum, np.r_[a, 360.0]) % 360
    el_h = _line_at(line, az_h) + 1.5
    for _ in range(4):  # (a steep stretch of the line: up until it is inside the hair)
        out = inside(sc, line, az_h, el_h) < 0.003
        el_h = el_h + 4.0 * out
    ok = lambda a_, e_: (inside(sc, line, a_, e_) > 0.6 * sp) & (e_ > sc.EL[0] + 4)  # noqa: E731
    r0 = float(np.median(sc.R))
    az_i, el_i = _poisson(sc, rng, lambda a_, e_: np.full(len(a_), sp), ok,
                          n_try=int(np.clip(400 * r0 * r0 / sp ** 2, 4000, 40000)))
    if xp is not None and float(ga["part_length"]) > 0:
        y0 = -float(sc.r(0.0, 30.0)) * np.cos(np.radians(30.0))
        plen = float(ga["part_length"])
        Pi = sc.point(az_i, el_i, 0.0) - sc.C
        far = (np.abs(Pi[:, 0] - xp) > 0.55 * sp) | (Pi[:, 1] > y0 + plen + 0.5 * sp) | (Pi[:, 2] < 0.02)
        az_i, el_i = az_i[far], el_i[far]
        yy = y0 + np.arange(0.0, plen + 1e-9, 0.5 * sp)
        n_i0 = len(az_i)
        for sd in (-1.0, 1.0):
            a_, e_ = top_to_azel(sc, np.stack([np.full(len(yy), xp + sd * 0.003), yy + (0.25 * sp if sd > 0 else 0.0)], 1))
            keep = inside(sc, line, a_, e_) > 0.004
            az_i, el_i = np.r_[az_i, a_[keep]], np.r_[el_i, e_[keep]]
    az = np.r_[az_h, az_i]
    el = np.r_[el_h, el_i]
    hl = np.r_[np.ones(len(az_h), bool), np.zeros(len(az_i), bool)]
    if xp is not None and float(ga["part_length"]) > 0:
        hl = hl.astype(int)
        hl[len(az_h) + n_i0:] = 2  # (2 = on the parting)
    if ga.get("above") is not None:  # only the hair above a level (m from the head centre): half up
        keep = ((sc.point(az, el, 0.0)[:, 2] - sc.C[2]) > float(ga["above"])) & (np.abs(_wrap(az)) < 125.0)
        az, el, hl = az[keep], el[keep], hl[keep]
    return az, el, hl


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
    x0 = sc.point(a0, e0, 0.0)[:, 0] - sc.C[0]
    xs = x0 - (xp if xp is not None else 0.0)
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
            dn[:, 1] = np.maximum(dn[:, 1], 0.0)
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
        lim = _line_at(line, az) + 1.0 - float(ga["overhang"]) * _ss_t((fa - 12) / 25) * (1 - _ss_t((fa - 62) / 22)) \
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
    from .hair import _part_x, az_el, dirs
    xp = _part_x(g)
    az, el, hl = roots(sc, ga, line, rng, xp)
    if not len(az):
        return {}
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
        onp = 0.45 if hl[i] == 2 else 1.0  # (the parting's own rows lie low: lifted like the rest they were two humps)
        puff = onp * float(ga["puff"]) * (0.55 + 0.45 * top) * min(w0[i] / np.radians(50), 1.0) * (1 + un * rng.uniform(-0.5, 0.9))
        lift = onp * float(ga["root_lift"]) * (1 + un * rng.uniform(-0.3, 0.5))
        ride = 0.002 + float(ga["body"]) * far
        h = (1 - t ** 3) * (ride * np.minimum(t * 6, 1) + lift * _ss_t(t / 0.15) * (1 - 0.5 * t) + puff * np.sin(np.pi * t) ** 0.9) \
            + t ** 3 * float(tp["out"]) * 0.8
        aa = aa + un * 4.0 * np.sin(np.pi * t) * rng.uniform(-1, 1)
        r = 0 if hl[i] == 1 else 1
        name = f"{pre}g{r}_{k[r]}"
        k[r] += 1
        lk = {"tier": "tie", "pts": [[round(float(aa[j]), 2), round(float(ee[j]), 2), round(float(h[j]), 4)] for j in range(n)],
              "width": round(sp * (0.9 if hl[i] == 1 else 1.9) * (1 + un * rng.uniform(-0.3, 0.3)), 4), "thickness": 0.004,
              "taper": 0.6, "belly": 0.45, "root": 0.8, "cup": 0.003}
        st = dict(ga.get("strands") or {})
        if hl[i] == 1:
            st.update(ga.get("hairline_strands") or {})
        else:  # (inside the hair every strand starts at its lock's root: staggered starts are stubble)
            st["roots"] = 0.0 if ga.get("inner_roots") is None else float(ga["inner_roots"])
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
    ln = 1 - un * rng.uniform(0, 0.5, n)
    ns = 20
    ds = L * ln / ns
    d = d0[None] + float(tl["spread"]) * rho[:, None] * rad
    from .hair import dirs
    out = dirs(*tp["at"])
    inw = np.minimum(d @ out - float(d0 @ out), 0.0)  # (no lock leaves the tie INTO the head: it lay over the crown)
    d = _unit(d - 0.8 * inw[:, None] * out[None])
    gap = 0.004 + 1.2 * full * rng.uniform(0, 1, n)  # (lying on a shoulder the bundle keeps its thickness)
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
    for i in range(n):
        tt = sk[i] / L
        Ki = np.stack([np.interp(sk[i], S, K[:, j]) for j in range(3)], 1)
        Kci = np.stack([np.interp(sk[i], S, Kc[:, j]) for j in range(3)], 1)
        o = Q[i] - Ki
        f = (1 + (scale - 1) * _ss_t(sk[i] / 0.04)) * (1 - float(tl["taper"]) * tt ** 2)
        Pk = Kci + o * f[:, None]
        Pk = Pk + un * 0.012 * rng.normal(0, 1, 3)[None] * (tt ** 1.5)[:, None]  # (each lock a little its own way)
        if fl > 0:  # the lock's end turns out of the bundle (and a little up): a flicked tip, each its own
            Pk = Pk + (fl * rng.uniform(0.3, 1.0) * (0.3 + rho[i]) * _ss_t((sk[i] / (L * ln[i]) - 0.6) / 0.4) ** 2)[:, None] \
                * (_unit(o + 1e-9) + [0.0, 0.0, 0.35])
        Pk[1:] = _push(sc, col, Pk[1:], 0.004)
        Pk[0] = P0 + 0.5 * (Pk[0] - P0)
        w = full * 2.2 / np.sqrt(max(n, 1)) * (1 + un * rng.uniform(-0.25, 0.35))
        locks[f"{pre}t{i}"] = {"tier": "tie", "space": "xyz", "pts": _xyz(sc, Pk[::2] if ns % 2 == 0 else Pk),
                              "core": core, "free": 1.0, "width": round(float(max(w, 0.012)), 4), "thickness": 0.005,
                              "taper": 0.9, "belly": 0.4, "root": 0.5, "cup": 0.0,
                              **({"strands": dict(tl["strands"])} if tl.get("strands") else {})}
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
            to = _unit(tie_d - (tie_d @ out) * out)
            d = _unit(out * 0.25 + (DOWN if zone == "nape" else 0.45 * to + 0.35 * DOWN))
            B = [p]
            for _ in range(10):
                d = _unit(d + 0.4 * DOWN)
                q = _push(sc, col, (B[-1] + d * ln / 10)[None], 0.004)[0]
                B.append(q)
            B = np.asarray(B)
            sl = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(B, axis=0), axis=1))]
            u = np.linspace(0, 1, 17)
            B = np.stack([np.interp(u * sl[-1], sl, B[:, c_]) for c_ in range(3)], 1)
            eo = _unit(np.array([out[0], out[1], 0.0]))
            esd = np.array([-eo[1], eo[0], 0.0])
            # the piece's own bend (a C out from the face and back, a slow S), shared by its hairs
            a = np.radians(rng.uniform(-100, 100))
            e = np.cos(a) * eo + np.sin(a) * esd
            bow = cv * ln * rng.uniform(0.4, 1.2)
            B = B + (bow * np.sin(np.pi * u ** 0.8))[:, None] * e + (0.5 * bow * u ** 3)[:, None] * eo
            nh = int(rng.integers(int(h0), int(h1) + 1))
            for q_ in range(nh):  # its hairs: one root, each its own length, drift and wave
                a2 = rng.uniform(0, 2 * np.pi)
                e2 = np.cos(a2) * eo + np.sin(a2) * esd + 0.3 * rng.uniform(-1, 1) * Z
                drift = rng.uniform(0.04, 0.2) * ln
                kq, phq = rng.uniform(0.6, 1.4), rng.uniform(0, 2 * np.pi)
                amp = cv * ln * rng.uniform(0.05, 0.3)
                cut = rng.uniform(0.5, 1.0)
                uu = u * cut
                Bq = np.stack([np.interp(uu, u, B[:, c_]) for c_ in range(3)], 1)
                Pq = Bq + (drift * uu ** 1.3)[:, None] * e2 \
                    + (amp * uu * np.sin(2 * np.pi * kq * uu + phq))[:, None] * np.cross(e2, Z)
                Pq[1:] = _push(sc, col, Pq[1:], 0.003)
                locks[f"{pre}e{k}_{q_}"] = {
                    "tier": "tie", "space": "xyz", "pts": _xyz(sc, Pq), "free": 1.0,
                    "width": round(float(rng.uniform(0.001, 0.003)), 4), "thickness": 0.002, "taper": 0.5,
                    "belly": 0.35, "root": 0.6, "cup": 0.0, "hairs": int(rng.integers(1, 3)),
                    "strands": {**ESCAPED_STRANDS, "wave": float(es["wave"]), "wavelength": float(es["wavelength"]),
                                **(es.get("strands") or {})}}
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
    "escaped": None,      # pieces that came loose: a count a side, or {"count": n | [right, left], "where":
                          # ["part", "temple", "ear", "nape"], "length": [m, m]}; default by neatness
    "neatness": 0.5,      # 0 = slept in (strays, a halo, uneven) .. 1 = every hair in place
    "half": False,        # true = half up: only the top section is tied, the rest hangs loose (`length` m of it)
    "length": 0.3,        # m: the loose hair's length for half up
    "detail": None,       # {"tie": {...}, "strands": {...}}: overrides of what the style makes (hair_tied's own keys)
}
TAIL = {"kind": "tail", "length": 0.25, "fullness": 0.5, "wave": 0.3, "to": "back"}
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
    tl = p["tail"]
    wave = float(np.clip(tl["wave"], 0, 1))
    full = 0.022 + 0.034 * float(np.clip(tl["fullness"], 0, 1))
    gather = {"mode": "flow", "spacing": 0.02, "uneven": round(0.2 + 0.6 * me, 3),
              "puff": round(0.002 + 0.016 * lift, 4), "root_lift": round(0.0015 + 0.008 * lift, 4),
              "body": round(0.005 + 0.005 * lo, 4), "sag": round(2.6 * lo, 3), "overhang": round(22.0 * lo, 2),
              "ears": 14.0 if p["ears"] == "covered" else 0.0, "part_length": round(0.035 + 0.06 * lo, 4),
              "hairline_strands": {"density": 1.6},
              "strands": {"wave": round(0.004 + 0.008 * lo, 4), "wavelength": 0.07, "random": 0.8, "flat": 1.5,
                          "flyaway": 0.0}}
    tie = {"at": [round(az, 1), el], "out": round(0.022 + 0.012 * lo, 4), "escape": 0, "gather": gather}
    kind = tl["kind"]
    if kind == "none":
        tie["tail"] = False
    else:
        tail_ = {"length": float(tl["length"]), "fullness": round(full, 4), "locks": int(round(14 + 16 * tl["fullness"])),
                 "uneven": round(0.3 + 0.7 * me, 3), "taper": 0.3,
                 "strands": {"wave": round(0.03 * wave, 4), "wavelength": 0.16, "random": 0.7, "clump": 0.55,
                             "clump_size": 0.008, "tips": 1.0, "tip_spread": 0.1}}
        if kind == "bun":
            tail_.update({"coil": 2.2, "coil_radius": round(0.02 + 0.02 * tl["fullness"], 4), "length": max(float(tl["length"]), 0.2)})
        elif kind == "plait":
            tail_.update({"plait": True, "stiff": 0.3, "fullness": round(0.6 * full, 4)})
        else:
            # a tail hangs: it stands out of a high tight tie a little longer than out of a low loose one
            tail_.update({"hang": True, "stiff": round(0.2 + 0.1 * float(np.clip((el + 10) / 60, 0, 1)) + 0.04 * T, 3),
                          "spread": round(0.3 + 0.3 * tl["fullness"], 3), "sway": round(0.034 * wave, 4),
                          "sway_length": 0.21, "flick": round(0.04 * wave, 4)})
            if tl["to"] == "shoulder":  # brought forward over the shoulder on the tie's side (the left when centred)
                sd = 1.0 if off >= 0 else -1.0
                tail_["dir"] = [round(0.75 * sd, 3), -0.35, -0.55]
            elif tl["to"] != "back":
                raise ValueError(f"hair tied tail.to {tl['to']!r}: back or shoulder")
        tie["tail"] = tail_
    es = p["escaped"]
    if es is None:
        es = int(round(8 * me))
    if isinstance(es, (int, float)):
        es = {"count": int(es)}
    if es and es.get("count"):
        tie["escaped"] = {"where": ["ear", "temple", "nape", "ear"], "length": [0.04, 0.12], "curve": 0.3, **es}
    out = {"parting": {"side": "none"} if p["part"] == "none" else
           {"side": "centre" if p["part"] == "center" else p["part"], "offset": 0.03, "length": round(0.035 + 0.06 * lo, 4),
            "width": 0.004, "depth": 0.2},
           "strands": {**STRANDS, "loose": round(0.15 + 0.6 * me, 3), "frizz": round(0.08 + 0.25 * me, 3),
                       "flyaway": round(0.03 + 0.25 * me, 3), "halo": round(0.45 * me, 3), "baby": round(0.5 + 2.5 * me, 2),
                       "clump": 0.2, "free": {"loose": round(0.1 + 0.25 * me, 3), "frizz": round(0.1 + 0.3 * me, 3),
                                              "flyaway": round(0.15 + 0.7 * me, 3), "stray": 0.6}}}
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
