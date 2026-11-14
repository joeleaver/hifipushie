"""Growing locks: strips, gap roots, the hang, part roots and the walk down the head. Part of hair (hair.py has
the overview)."""
from __future__ import annotations

import numpy as np

from . import hair
from .hair import _ss, _unit, az_el, dirs, side_tuck, under
from .hair_groom import _line_at, _part, _part_x, _poisson, _region, envelope, flow, hairline, inside, weights
from .hair_head import Scalp
from .hair_seat import fit_to_head

def grow(sc: Scalp, g: dict, col=None) -> dict:
    """The first pass of locks from the groom: {name: lock}. `col`: the body's collider (hair_loose_body.collider) for
    hair that falls off the head."""
    from . import hair_drawn, hair_spec
    g = fit_to_head(g, sc)
    rng = np.random.default_rng(int(g.get("seed", 0)))
    noise = float(g.get("noise", 0.3))
    line = hairline(sc, g)
    xp = _part_x(g)
    locks = {}
    tiers = g["tiers"]
    names = {"big": "b", "crown": "c", "fill": "f", "edge": "e", "gap": "g", "clumps": "k"}
    if g.get("drawn"):  # the top drawn by hand (clumps on the top view), the rest grown round it
        locks.update(hair_drawn.drawn(sc, g, g["drawn"]))
    if g.get("loose"):  # loose hair is the whole groom too (with drawn clumps and any tie: half up)
        from . import hair_loose_grow
        locks.update(hair_loose_grow.grow(sc, g, line, rng, col))
    if g.get("tie"):  # tied hair makes the whole groom (with any drawn clumps): no generated tiers under it
        from . import hair_tied
        locks.update(hair_tied.grow(sc, g, line, rng, col))
        return locks
    if g.get("loose"):
        return locks
    if tiers.get("strip"):
        locks.update(_strips(sc, g, line, tiers["strip"], rng))
    designed = bool((tiers.get("clumps") or {}).get("list")) or bool(g.get("drawn"))
    for tier in ("clumps", "big", "crown", "fill", "edge", "gap", "gap"):  # gaps twice: a second look at what's bare
        td = tiers.get(tier)
        if not td or (designed and tier in ("big", "crown")):  # designed clumps replace the laid-out top
            continue
        if tier == "clumps" and not td.get("list"):
            continue
        kind = {"crown": "big", "gap": "fill", "clumps": "big"}.get(tier, tier)
        heading = None  # crown: big locks laid by spacing; gap: fill locks
        if tier == "gap":
            names["gap"] = "g" if not any(n.startswith("g") for n in locks) else "h"
        w0, t0 = float(td.get("width", 0.055)), float(td["thickness"])
        sp0 = w0 * float(td.get("spacing", 0.8))
        where = [hair.REGIONS.index(r) for r in td.get("where", hair.REGIONS)]
        if tier == "edge":  # along the hairline, just inside it, where it's seen: temples, sideburns, the nape
            az_all = np.arange(0.0, 360.0, 0.5)
            el_all = _line_at(line, az_all) + np.degrees(0.004 / sc.r(az_all, _line_at(line, az_all)))
            P = sc.point(az_all, el_all, 0.0)
            arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
            at = np.arange(0.5 * sp0, arc[-1], sp0)
            at = at + rng.uniform(-0.2, 0.2, len(at)) * sp0
            az = np.interp(at, arc, az_all)
            el = np.interp(at, arc, el_all)
            fa = np.abs(((az + 180) % 360) - 180)
            keep = (fa > 40) & (fa < 115)  # temples and sideburns: not the crisp front line, not the nape
            az, el = az[keep], el[keep]
        elif tier == "clumps":  # the designer's big clumps: [az, el, heading deg, length m, width m] each
            arr = np.asarray(td["list"], float)
            az, el, heading = arr[:, 0], arr[:, 1], arr[:, 2]
        elif tier == "gap":  # the artist's pass over what's still bare: roots where no lock covers the volume
            az, el = _gap_roots(sc, g, line, locks, td, rng)
        elif tier == "big" and td.get("layout", "part") == "part" and xp is not None:
            az, el, away_given = _part_roots(sc, g, line, td, xp, rng)
        else:
            def ok(a, e, where=where):
                d = inside(sc, line, a, e)
                W = weights(a, e, d)
                good = (d > (0.006 if kind == "big" else 0.004)) & (W[:, where].sum(1) > 0.5)
                if xp is not None:
                    good &= _part(sc, g, a, e, 0.006) < 0.5
                return good
            az, el = _poisson(sc, rng, lambda a, e: np.full(len(a), sp0), ok)
        if not len(az):
            continue
        if not (tier == "big" and td.get("layout", "part") == "part" and xp is not None):
            away_given = None
        d_in = inside(sc, line, az, el)
        W = weights(az, el, d_in)
        P0 = sc.point(az, el, 0.0)
        away = np.ones(len(az)) if xp is None else np.where(P0[:, 0] >= xp, 1.0, -1.0)
        if xp is None:
            away = np.sign(P0[:, 0] + 1e-9)
        if away_given is not None:
            away = away_given
        if tier == "crown" and xp is not None:  # the whole top sweeps one way, away from the part (each lock choosing
            away = np.full(len(az), -np.sign(xp) or -1.0)  # its side of the part turned the crown into a jumble)
        L = float(td["length"]) * np.ones(len(az)) if td.get("length") else _region(g, "length", W)
        if away_given is not None:  # the short side of a side part: brushed down toward the ear, not over it
            L = np.where(away_given == np.sign(_part_x(g) or 1.0), L * float(td.get("part_side_length", 0.55)), L)
        L = L * (1 + noise * 0.25 * rng.uniform(-1, 1, len(az)))
        if tier == "fill":  # shorter near the hairline: the edge tapers cleanly
            L *= 0.5 + 0.5 * _ss(d_in / 0.02)
        size = 1 + noise * 0.25 * rng.uniform(-1, 1, len(az))
        W_ = w0 * size
        T_ = t0 * size
        if tier == "clumps":
            L, W_, size = arr[:, 3], arr[:, 4], np.ones(len(az))
            T_ = t0 * W_ / 0.055
        if away_given is not None:  # the part side's locks are the short, flat, narrower ones
            ps = away_given == np.sign(_part_x(g) or 1.0)
            W_ = np.where(ps, W_ * 0.75, W_)
            T_ = np.where(ps, T_ * 0.6, T_)
            nr = int(td.get("part_row", 3))  # the row down the parting (last): narrower, lying on the crown's
            if nr:  # curve (full width, their flat edges overhung the dome in the 3/4 view)
                W_[-nr:] *= float(td.get("part_row_width", 0.7))
        # the front row lies over the ones behind it (their roots under its body)
        # what lies on what: a lock covers the roots of those downstream of it (the front row over the top, higher
        # roots over lower ones on the sides and back), consistently, or overlaps cross in a jumble
        rank = 1 - _ss(d_in / 0.08) if kind == "big" else _ss((el + 40) / 120)
        lift = T_ * (0.25 * rank + 0.08 * rng.uniform(-1, 1, len(az))) if tier == "big" else np.zeros(len(az))  # crown, fill: flush
        flat = (away_given == np.sign(_part_x(g) or 1.0)).astype(float) if away_given is not None else None
        if flat is not None:  # the part side's locks lie flat: no lift, no tip step
            lift = lift * (1 - flat)
        paths, sides = _walk(sc, g, line, az, el, L, T_, lift, away, rng, kind, flat=flat, heading=heading)
        for i in range(len(az)):
            path, sfi = paths[i], sides[i]
            if tier != "edge":  # a lock ends inside the hairline (tips standing out over the skin read as a fringe)
                pa, pe, _ = sc.coords(path)
                din = inside(sc, line, pa, pe)
                out = np.nonzero(din < float(td.get("tip_inset", 0.006)))[0]
                out = out[out > 2]
                if len(out):
                    j = int(out[0])
                    c = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(path[:j + 1], axis=0), axis=1))]
                    if c[-1] < 0.35 * L[i]:
                        continue  # too little room: the underlayer carries it
                    t = np.linspace(0, c[-1], len(path))
                    path = np.stack([np.interp(t, c, path[:j + 1, q]) for q in range(3)], 1)
                    sfi = np.interp(t, c, sfi[:j + 1])
                    Li = c[-1]
                else:
                    Li = L[i]
            else:
                Li = L[i]
            k = 5 if Li > 0.08 else (4 if Li > 0.035 else 3)
            idx = np.round(np.linspace(0, len(path) - 1, k)).astype(int)
            a_, e_, h_ = sc.coords(path[idx])
            if tier != "edge":  # the tip tucks into the layer under it (a shortened lock ended in the air)
                Ht, dt = envelope(sc, g, line, a_[-1:], e_[-1:])
                h_[-1] = min(float(h_[-1]), float(under(g, Ht, a_[-1:], e_[-1:], dt)[0]) + 0.1 * float(T_[i]))
            grey = _grey(g, az[i], el[i], line)
            rad = 1 - hair.SIDE_NARROW * sfi[idx]
            tilt = lie_tilt(sc, g, line, hair_spec._catmull(path[idx], 4 * k)[::4] if k > 1 else path[idx])
            locks[f"{names[tier]}{i:02d}"] = {
                "tier": tier,
                **({"radius": [round(float(v), 3) for v in rad]} if np.any(rad < 0.999) else {}),
                "tilt": [round(float(v), 3) for v in tilt],
                "pts": [[round(float(a_[j]), 2), round(float(e_[j]), 2), round(float(h_[j]), 4)] for j in range(k)],
                "width": round(float(W_[i]), 4), "thickness": round(float(T_[i]), 4),
                "cup": round(float(td["cup"]) * float(size[i]) if "cup" in td else lie_cup(sc, float(W_[i]), path), 4),
                "taper": float(td.get("taper", 1.0)), "belly": round(float(td.get("belly", 0.16) + 0.06 * rng.uniform(-1, 1)), 3),
                "root": float(td.get("root", 0.8)),
                "twist": round(float(rng.uniform(-15, 15) * noise), 1) if tier in ("fill", "edge") else 0.0,
                **({"grey": round(grey, 3)} if grey > 0.01 else {})}
    return locks


def _nape_frame(sc: Scalp, td: dict | None = None):
    """Short back and sides are combed back and down toward the nape: flow lines are the head's sections through a
    point under the nape (N) and an axis from it toward the forehead. Returns N, axis, e1, e2. td["nape"] ([x, y, z]
    from the head centre) moves N: long hair falls, so its streams meet far below the head (at the default nape point
    they gathered into a tail)."""
    N = sc.C + np.asarray((td or {}).get("nape", [0.0, 0.06, -0.13]), float)
    axis = _unit(np.array([0.0, -0.9, 0.45]) if "nape" not in (td or {}) else
                 sc.C + np.array([0.0, -0.115, 0.0567]) - N)  # toward the forehead from N
    e1 = _unit(np.cross(axis, [1.0, 0, 0]))
    return N, axis, e1, np.cross(axis, e1)


def stream_angle(sc: Scalp, P, td: dict | None = None):
    """Each point's flow line: its angle round the nape axis (radians; constant along a combed-back stream)."""
    N, axis, e1, e2 = _nape_frame(sc, td)
    Q = np.asarray(P, float) - N
    t = Q - (Q @ axis)[..., None] * axis
    return np.arctan2(t @ e2, t @ e1)


def _strips(sc: Scalp, g: dict, line, td: dict, rng) -> dict:
    """The sides and back as long flat locks laid side by side along the combed streams (tier "strip"): each runs
    from under the top's locks (its root hidden by them) down the stream to just inside the hairline, flush with the
    groom's volume, overlapping its neighbours a little, narrowing as the streams converge on the nape. So the whole
    head is locks with one flow: no mass surface shows, and the outline stays the volume's (the fill tier's short
    locks either broke it or read as scales)."""
    from . import hair_spec
    N = _nape_frame(sc, td)[0]
    w0, t0 = float(td.get("width", 0.03)), float(td.get("thickness", 0.003))
    over = float(td.get("overlap", 1.2))
    top_start = float(td.get("start", 0.55))  # the top-region weight where a strip's root sits (under the top locks)
    inset = float(td.get("tip_inset", 0.004))
    A, E = np.meshgrid(np.arange(0.0, 360.0, 0.5), np.arange(-60.0, 89.0, 0.5), indexing="ij")
    A, E = A.ravel(), E.ravel()
    d_in = inside(sc, line, A, E)
    hair_m = d_in > inset
    A, E, d_in = A[hair_m], E[hair_m], d_in[hair_m]
    W = weights(A, E, d_in)
    topw = W[:, 0] + W[:, 1]
    P = sc.point(A, E, 0.0)
    ang = stream_angle(sc, P, td)
    dist = np.linalg.norm(P - N, axis=1)
    # the strips' start line: where the top gives way to the sides; spacing along it = the strip width
    band = np.abs(topw - top_start) < 0.08
    d_ref = float(np.median(dist[band])) if band.any() else float(np.median(dist))
    step = w0 / over / d_ref
    lo, hi = np.percentile(ang[topw < 0.9], [0.5, 99.5])
    angs = np.arange(lo + 0.5 * step, hi, step)
    angs = angs + rng.uniform(-0.15, 0.15, len(angs)) * step
    out = {}
    noise = float(g.get("noise", 0.3))
    for k, a0 in enumerate(angs):
        m = np.abs(ang - a0) < 0.35 * step
        if m.sum() < 8:
            continue
        dm, tm, Am, Em = dist[m], topw[m], A[m], E[m]
        # from the start (the farthest point from N still at top weight >= start, else the farthest) to the end
        # (the nearest to N: the hairline)
        cand = tm <= top_start + 0.1
        if not cand.any():
            continue
        d_start = dm[cand].max()
        d_end = dm.min()
        if d_start - d_end < 0.03:
            continue
        # the spine: points binned by distance to N (5 mm), their mean direction from the head centre
        bins = np.arange(d_start, d_end - 1e-6, -0.005)
        U = sc.point(Am, Em, 0.0)
        # the spine: per 5 mm of distance to N, the band's point nearest the last one (a band can hold two stretches,
        # above and behind the ear: their mean ran the strip across the ear)
        spine = []
        cur = U[cand][np.argmax(dm[cand])]
        for b in bins:
            q = np.nonzero(np.abs(dm - b) < 0.004)[0]
            if not len(q):
                continue
            j = q[np.argmin(np.linalg.norm(U[q] - cur, axis=1))]
            if np.linalg.norm(U[j] - cur) > 0.03:
                break  # the stream leaves the hair (the ear, the hairline): the strip ends
            cur = U[j]
            spine.append(_unit(cur - sc.C))
        if len(spine) < 4:
            continue
        spine = np.array(spine)
        sa, se = az_el(spine)
        H, dd = envelope(sc, g, line, sa, se)
        U_all = np.linspace(0, 1, len(spine))
        # shingles: the stream's length in `segments` overlapping pieces, each one's root dived under the tip of the
        # piece before it, each tip lifted a `step` (x thickness) off the piece it lies on, so the rows read as layered
        # clumps with a shadow line at every step, not one skin with grooves drawn on it
        nseg = max(1, int(td.get("segments", 3)))
        ov = float(td.get("overlap_along", 0.3))
        step = float(td.get("step", 0.8))
        lo_u = np.linspace(0, 1, nseg + 1)[:-1]
        hi_u = np.minimum(np.linspace(0, 1, nseg + 1)[1:] + ov / nseg, 1.0)
        size = 1 + noise * 0.15 * rng.uniform(-1, 1)
        for sgi in range(nseg):
            sel = (U_all >= lo_u[sgi] - 1e-9) & (U_all <= hi_u[sgi] + 1e-9)
            if sel.sum() < 4:
                continue
            u = (U_all[sel] - U_all[sel][0]) / max(U_all[sel][-1] - U_all[sel][0], 1e-9)
            Hs = H[sel]
            base = Hs - hair.FILL_SINK * t0 + 0.5 * t0  # back at the volume over the sunk underlayer
            last = sgi == nseg - 1
            h = (base - 0.9 * t0 * (1 - _ss(u / 0.2))  # the root dives under the tip before it
                 + (0.0 if last else step * t0) * _ss((u - 0.55) / 0.45)  # the tip lifts off the next row
                 - (0.8 * t0 * _ss((u - 0.8) / 0.2) if last and not td.get("hang") else 0.0))  # the last tucks in
            h = np.maximum(h, 0.2 * t0 * _ss(u / 0.2) - 0.6 * t0 * (1 - _ss(u / 0.2)))
            path = sc.point(sa[sel], se[sel], h)
            hang = float(td.get("hang", 0.0))
            if last and hang > 0:  # longer hair: past the hairline the stream falls, off the head and down
                path = _hang(sc, path, hang, td, rng, k)
            c = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
            L = c[-1]
            kpts = 5 if L > 0.06 else 4
            if hang > 0 and last:
                kpts = int(np.clip(L / 0.025, 5, 12))  # waves need control points
            tt = np.linspace(0, L, kpts)
            ctrl = np.stack([np.interp(tt, c, path[:, q]) for q in range(3)], 1)
            a_, e_, h_ = sc.coords(ctrl)
            Pc = sc.point(a_, e_, 0.0)
            rad = np.clip(np.linalg.norm(Pc - N, axis=1) / d_start, 0.45, 1.2)
            tilt = lie_tilt(sc, g, line, hair_spec._catmull(ctrl, 4 * kpts)[::4])
            grey = _grey(g, float(a_[0]), float(e_[0]), line)
            out[f"s{k:02d}{'abcdefgh'[sgi]}"] = {
                "tier": "strip",
                "pts": [[round(float(a_[q]), 2), round(float(e_[q]), 2), round(float(h_[q]), 4)] for q in range(kpts)],
                "radius": [round(float(v), 3) for v in rad],
                "tilt": [round(float(v), 3) for v in tilt],
                "width": round(w0 * size, 4), "thickness": round(t0, 4),
                "cup": round(float(td["cup"]) if "cup" in td else lie_cup(sc, w0 * size, path), 4),
                "taper": float(td.get("taper", 0.6)), "belly": float(td.get("belly", 0.3)), "root": 0.85,
                "twist": 0.0, **({"grey": round(grey, 3)} if grey > 0.01 else {})}
    return out


def _gap_roots(sc: Scalp, g: dict, line, locks: dict, td: dict, rng):
    """Roots for gap locks: cells of the hair (inside the hairline) that the locks so far leave uncovered (their
    outer faces splatted on a 1 degree grid, grown a little), spaced like the tier, each a lock length upstream of the
    hole so the lock lies over it."""
    from . import hair_lockmesh, hair_spec
    if not locks:
        return np.array([]), np.array([])
    ext = hair_lockmesh.lock_extents(sc, hair_spec.resolve({"hair": {"locks": locks}}, sc))
    A, E = np.meshgrid(np.arange(0.0, 360.0, 1.0), np.arange(-60.0, 89.0, 1.0), indexing="ij")
    cov = hair_lockmesh.coverage(sc, A, E, ext, reach=0.001)
    d = inside(sc, line, A, E)
    bare = (cov < 0.75) & (d > 0.004)
    if td.get("where"):  # only the regions asked (a drawn top is left to its clumps: widen them, don't add small ones)
        Wg = weights(A, E, d)
        bare &= Wg[..., [hair.REGIONS.index(r) for r in td["where"]]].sum(-1) > 0.5
    if not bare.any():
        return np.array([]), np.array([])
    a0, e0 = A[bare], E[bare]
    sp = float(td.get("width", 0.025)) * float(td.get("spacing", 0.7))
    P = sc.point(a0, e0, 0.0)
    order = rng.permutation(len(a0))
    chosen, pts = [], np.zeros((0, 3))
    for i in order:
        if len(pts) and np.min(np.linalg.norm(pts - P[i], axis=1)) < sp:
            continue
        chosen.append(i)
        pts = np.vstack([pts, P[i]])
    a0, e0 = a0[chosen], e0[chosen]
    # step upstream (against the flow) by a third of the lock so its body covers the hole
    W = weights(a0, e0, inside(sc, line, a0, e0))
    P0 = sc.point(a0, e0, 0.0)
    xp = _part_x(g)
    away = np.sign(P0[:, 0] + 1e-9) if xp is None else np.where(P0[:, 0] >= xp, 1.0, -1.0)
    f = _unit(flow(sc, g, P0, W, away))
    back = P0 - f * float(td.get("length", 0.05)) * 0.35
    a1, e1 = az_el(back - sc.C)
    ok = inside(sc, line, a1, e1) > 0.004
    return np.where(ok, a1, a0), np.where(ok, e1, e0)


def _hang(sc: Scalp, path, hang: float, td: dict, rng, k: int):
    """A strip's end carried on past the hairline: it leaves the head along its last heading, turns down under
    gravity and falls `hang` m, kept off the body (the scalp model's surface + a clearance) and waved side to side
    (`wave`: {"amount", "length"} m, phase per strip)."""
    P = [p for p in np.asarray(path, float)]
    d = _unit(P[-1] - P[-2])
    step = 0.008
    n = int(hang / step)
    wv = td.get("wave") or {}
    amp, lam = float(wv.get("amount", 0.0)), float(wv.get("length", 0.06))
    ph = rng.uniform(0, 2 * np.pi)
    clear = float(td.get("clearance", 0.004))
    base = [P[-1].copy()]
    for i in range(n):
        f = min(1.0, (i + 1) / 6)
        d = _unit((1 - f) * d + f * np.array([0.0, 0.0, -1.0]) + 0.15 * _unit(np.r_[(P[-1] - sc.C)[:2], 0.0]))
        q = base[-1] + d * step
        a, e, hh = sc.coords(q[None])
        if hh[0] < clear:  # never into the head, neck or shoulders
            q = sc.point(a, e, np.array([clear]))[0]
        base.append(q)
    base = np.array(base[1:])
    if amp > 0 and len(base) > 2:
        s_ = np.arange(1, len(base) + 1) * step
        side = _unit(np.cross(np.array([0.0, 0.0, 1.0]), _unit(np.r_[(base[0] - sc.C)[:2], 0.0])))
        base = base + (amp * np.minimum(s_ / lam, 1.0) * np.sin(2 * np.pi * s_ / lam + ph))[:, None] * side
    return np.vstack([np.asarray(path, float), base])


def _part_roots(sc: Scalp, g: dict, line, td: dict, xp: float, rng):
    """The big locks' roots, laid out the way the cut is designed: along the front hairline on each side of the
    parting (most on the side the hair is combed to) and in a row down the parting behind it. Returns az, el, away."""
    sgn = 1.0 if xp >= 0 else -1.0  # the part's side; the hair is combed away from it
    P = sc.point(np.array([0.0]), np.array([60.0]), 0.0)[0]
    az_p = float(az_el(np.array([xp, sc.C[1] - 0.12, P[2]]) - sc.C)[0][()])
    az_p = (az_p + 180) % 360 - 180
    nf_away, nf_part, n_row = int(td.get("front_away", 5)), int(td.get("front_part", 2)), int(td.get("part_row", 3))
    far = float(td.get("front_span", 42.0))  # degrees of azimuth the front row reaches round from the middle
    A, E, AW = [], [], []
    inset = float(td.get("inset", 0.016))  # behind the hairline: the roots grow out of the mass, not the skin
    for n, lo, hi, aw in ((nf_away, az_p - sgn * 3, -sgn * far, -sgn), (nf_part, az_p + sgn * 5, sgn * far, sgn)):
        if n <= 0:
            continue
        a = np.linspace(lo, hi, n + 1)[:-1] + (hi - lo) / (2 * n) * 0.3 + rng.uniform(-1, 1, n) * 1.5
        e = _line_at(line, a % 360) + np.degrees(inset / sc.r(a % 360, _line_at(line, a % 360)))
        A += list(a % 360)
        E += list(e)
        AW += [aw] * n
    if n_row > 0:  # down the parting, behind the front row, combed away from it
        L = float(g["parting"].get("length", 0.1))
        y0 = sc.point(0.0, float(_line_at(line, 0.0)), 0.0)[1]
        for k in range(n_row):
            y = y0 + L * (k + 0.9) / (n_row + 0.4)
            q = np.array([xp - sgn * 0.006, y, sc.C[2] + 0.12]) - sc.C
            a, e = az_el(q)
            A.append(float(a))
            E.append(float(e))
            AW.append(-sgn)
    return np.array(A), np.array(E), np.array(AW)


def mass_normal(sc: Scalp, g: dict, line, az, el, d: float = 1.0):
    """The outward normal of the groom's volume (the envelope surface) at (az, el): what a lock lies flat on."""
    def pt(a, e):
        H, _ = envelope(sc, g, line, a, e)
        return sc.point(a, e, H)
    ea = pt(az + d, el) - pt(az - d, el)
    ee = pt(az, el + d) - pt(az, el - d)
    n = _unit(np.cross(ea, ee))
    out = dirs(az, el)
    return np.where((n * out).sum(-1, keepdims=True) < 0, -n, n)


def lie_cup(sc: Scalp, width: float, path) -> float:
    """The cup that makes a lock's flat back follow the head's curve across it (its edges drop by the sag of the
    head over half its width), so neighbours lie flush: a fixed cup tucked narrow locks' edges deep (grooves that
    dented the outline) and let wide ones stand on their edges."""
    P = np.asarray(path, float)
    R = float(np.median(np.linalg.norm(P - sc.C, axis=1)))
    return (0.5 * width) ** 2 / (2 * R)


def lie_tilt(sc: Scalp, g: dict, line, P):
    """Per control point, the tilt (radians about the spine) that turns the node group's flat side (facing away
    from the head centre) to face the volume's own normal: facing the centre, a lock across the steeply curving
    upper side stood on one edge (the fill poked 2-4 mm out of the outline)."""
    P = np.asarray(P, float)
    tg = _unit(np.gradient(P, axis=0))
    n0 = _unit(P - sc.C)
    n0 = _unit(n0 - (n0 * tg).sum(1, keepdims=True) * tg)
    a, e = az_el(P - sc.C)
    n1 = mass_normal(sc, g, line, a, e)
    n1 = _unit(n1 - (n1 * tg).sum(1, keepdims=True) * tg)
    return np.arctan2((np.cross(n0, n1) * tg).sum(1), (n0 * n1).sum(1))


def _grey(g, az, el, line):
    """Grey at the temples and sideburns: by azimuth band and how low the root sits."""
    gr = g.get("grey") or {}
    fa = abs(((az + 180) % 360) - 180)
    temple = float(gr.get("temples", 0)) * float(_ss((fa - 35) / 15) * (1 - _ss((fa - 95) / 15)))
    low = float(_ss((30 - el) / 25))
    burn = float(gr.get("sideburns", 0)) * float(_ss((fa - 60) / 10) * (1 - _ss((fa - 90) / 10))) * low
    return max(temple * (0.4 + 0.6 * low), burn)


def _walk(sc: Scalp, g: dict, line, az, el, L, T, lift, away, rng, tier, n=24, flat=None, heading=None):
    """Lock spines (m, n, 3): from the root on the scalp along the flow, held under the envelope (the top layer's
    spine half a thickness under it), rising out of the scalp over the first fifth, the tip tucking down."""
    m = len(az)
    P = np.zeros((m, n, 3))
    SF = np.zeros((m, n))
    a, e = np.asarray(az, float).copy(), np.asarray(el, float).copy()
    P[:, 0] = sc.point(a, e, -0.3 * T)
    ds = L / (n - 1)
    W = weights(a, e, inside(sc, line, a, e))
    flat = np.zeros(m) if flat is None else np.asarray(flat, float)

    def flow_flat(q, W):  # locks marked flat comb back and down only (the part side: brushed toward the ear)
        if heading is not None:  # a designed clump keeps its heading on the surface: 0 back, 90 his right, 180 fwd
            n = _unit(q - sc.C)
            v = np.array([0.0, 1.0, 0.8])  # back over the crown (from the forehead, that is up: +Y alone vanished there)
            back = _unit(v - (n @ v)[:, None] * n)
            right = _unit(np.cross(n, back))  # n x back: toward his right (-X) on the top
            hr = np.radians(heading)[:, None]
            return np.cos(hr) * back + np.sin(hr) * right
        f = flow(sc, g, q, W, away)
        return f - flat[:, None] * np.maximum(f[:, 2:3], 0) * np.array([0.0, 0.0, 1.0])
    d = _unit(flow_flat(P[:, 0], W))
    turn = np.radians(rng.uniform(-1, 1, m) * 6 * float(g.get("noise", 0.3)))
    nrm = _unit(P[:, 0] - sc.C)
    c, s_ = np.cos(turn)[:, None], np.sin(turn)[:, None]
    d = _unit(d * c + np.cross(nrm, d) * s_)
    for k in range(1, n):
        x = k / (n - 1)
        q = P[:, k - 1] + d * ds[:, None]
        a, e = az_el(q - sc.C)
        H, d_in = envelope(sc, g, line, a, e)
        under_h = under(g, H, a, e, d_in)  # the mass under the locks (the blockout kept as the underlayer)
        if tier == "edge":
            h = np.full(m, 0.6) * T + 0.0005 + under_h
        else:  # the lock lies on the mass, its back just proud of the silhouette; the root dives into the mass
            # the lock's back flush with the groom's volume (the fill: relief pressed into the mass, not scales on it)
            surf = under_h + (0.35 if tier == "big" else hair.FILL_SINK - 0.4) * T + lift
            h = (under_h - 0.4 * T) + (surf - under_h + 0.4 * T) * _ss(x / 0.18)
        # over the upper sides a top lock lies down onto the side mass (and narrows: `radius` per point below):
        # standing as proud there as on the crown it overhung the sides and pinched the outline at the temples
        sf = side_tuck(a, e) if tier == "big" else np.zeros(m)
        SF[:, k] = sf
        h = h - sf * np.maximum(lift, 0)  # no lift where it lies down the side (the mass is sunk there too now)
        if tier == "big":  # the tip lifts a step off the lock it lies on (shingles: the next one's root is under it)
            h = h + (hair.TIP_STEP if heading is None else 0.1) * T * _ss((x - 0.55) / 0.45) * (1 - 0.5 * sf) * (1 - flat)  # designed
            # clumps lie calm (a lifted tip on a long clump curled up like a claw)
        else:  # the fill's tips tuck (a row of visible points read as feathers)
            h = h - 1.3 * T * _ss((x - 0.72) / 0.28)
        if tier == "fill":  # relief within the volume: its back never stands out of the groom's silhouette
            h = np.minimum(h, H - 0.8 * T)
        floor = np.where(d_in > 0, 0.15, 0.55) * T  # past the hairline (a fringe) it lies on the skin, not in it
        h = np.maximum(h, floor * _ss(x / 0.25) - 0.6 * T * (1 - _ss(x / 0.25)))  # the root grows out of the scalp
        # (floored above the skin from the start, a lock's squared-off root end stood on the forehead as a black notch)
        q = sc.point(a, e, h)
        P[:, k] = q
        seg = _unit(P[:, k] - P[:, k - 1])
        W = weights(a, e, d_in)
        f = _unit(flow_flat(q, W))
        f = _unit(f * c + np.cross(_unit(q - sc.C), f) * s_)
        d = _unit(0.55 * seg + 0.45 * f)
    SF[:, 0] = SF[:, 1]
    return P, SF
