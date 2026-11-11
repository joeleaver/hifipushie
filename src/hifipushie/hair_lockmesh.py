"""Lock geometry: lift, trim, lock meshes and extents, the hull lift, the silhouette fill, the cap mesh. Part of
hair (hair.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import hair, hair_spec
from .hair import HairError, _ss, _unit, az_el, dirs, under
from .hair_groom import _line_at, envelope, groom_params, hairline, inside, weights
from .hair_head import Scalp
from .hair_spec import _catmull, lock_width

def lift(spec: dict, sc: Scalp, by: dict, fill: bool = False) -> tuple:
    """(new spec, report): the whole groom made fuller (or closer) by region, as a barber's "more at the sides":
    by = {region: m} (REGIONS: front, top, sides, back, nape). Every lock point on the head ([az, el, h] locks; their
    handles too) rises by the region weights there (`weights`, the volume's own) x those metres, and groom.volume
    takes the same amounts, so the underlayer stays under the locks. Hand locks stay hand locks (their shapes are
    kept, only lifted); locks in "xyz" space are left alone and listed.
    fill=True (strand grooms): each lock also grows THICKER by twice its mean lift, so its lens still reaches down to
    where it lay and its strands fill the new volume from the scalp up (lifted alone, a strand groom's sides stood off
    the head as a shell over the short scalp layer; solid locks lifted alone read as a stiff helmet)."""
    import copy as _copy
    bad = set(by) - set(hair.REGIONS)
    if bad:
        raise HairError(f"hair lift: unknown regions {sorted(bad)} (have {', '.join(hair.REGIONS)})")
    out = _copy.deepcopy(spec)
    hs = out.setdefault("hair", {})
    g = groom_params(out)
    line = hairline(sc, g)
    vals = np.array([float(by.get(r, 0.0)) for r in hair.REGIONS])

    def dh(az, el):
        az, el = np.asarray(az, float), np.asarray(el, float)
        d_in = inside(sc, line, az, el)
        # eased in from the hairline (LIFT_RAMP): lifted at the line itself, the hair's edge stood off the skin as
        # a shelf with a dark gap under it at the temples
        return (weights(az, el, d_in) @ vals) * _ss(d_in / hair_spec.LIFT_RAMP)

    moved, skipped, mx = 0, [], 0.0
    for n, lk in (hs.get("locks") or {}).items():
        if lk.get("space") == "xyz":
            skipped.append(n)
            continue
        P = np.asarray(lk["pts"], float).reshape(-1, 3)
        d_ = dh(P[:, 0], P[:, 1])
        P[:, 2] += d_
        lk["pts"] = [[round(float(a), 2), round(float(e), 2), round(float(h), 4)] for a, e, h in P]
        if fill and float(np.mean(d_)) > 0:
            th0 = float(lk.get("thickness", hair.LOCK_DEFAULTS.get("thickness", 0.004)))
            lk["thickness"] = round(th0 + 2.0 * float(np.mean(d_)), 5)
        mx = max(mx, float(np.abs(d_).max()))
        if lk.get("handles"):
            nh = []
            for hd in lk["handles"]:
                if hd:
                    q = np.asarray(hd, float).reshape(2, 3)
                    q[:, 2] += dh(q[:, 0], q[:, 1])
                    nh.append([round(float(v), 4) for v in q.ravel()])
                else:
                    nh.append(hd)
            lk["handles"] = nh
        moved += 1
    gr = hs.setdefault("groom", {})
    vol = gr.setdefault("volume", {})
    for r, v in zip(hair.REGIONS, vals):
        if v:
            vol[r] = round(float(vol.get(r, hair.GROOM["volume"][r])) + float(v), 5)
    return out, {"locks": moved, "skipped_xyz": skipped, "max_lift_mm": round(mx * 1000, 2),
                 "volume": {r: vol.get(r) for r in hair.REGIONS}}


def trim(spec: dict, sc: Scalp, below: float, where=("sides", "back", "nape")) -> tuple:
    """(new spec, report): a barber's clean-up of the outline: every lock on the head ([az, el, h]) is cut where it
    runs more than `below` m outside the hairline (over the skin of the neck or past the sideburns) in the regions
    `where` (a point counts when its region weight there is over a half). The cut point is interpolated along the
    lock; per-point radius / tilt / handles are cut with it. Locks that would keep under two points are left whole
    and listed. A short back and sides: below 0.01 (strands fall past their lock's end by their own spread)."""
    import copy as _copy
    bad = set(where) - set(hair.REGIONS)
    if bad:
        raise HairError(f"hair trim: unknown regions {sorted(bad)} (have {', '.join(hair.REGIONS)})")
    out = _copy.deepcopy(spec)
    hs = out.setdefault("hair", {})
    line = hairline(sc, groom_params(out))
    wi = [hair.REGIONS.index(r) for r in where]
    cut, kept, short = 0, 0, []
    for n, lk in (hs.get("locks") or {}).items():
        if lk.get("space") == "xyz":
            continue
        P = np.asarray(lk["pts"], float).reshape(-1, 3)
        d_in = inside(sc, line, P[:, 0], P[:, 1])
        w = weights(P[:, 0], P[:, 1], d_in)[:, wi].sum(1)
        over = (d_in < -below) & (w > 0.5)
        over[0] = False
        if not over.any():
            kept += 1
            continue
        k = int(np.argmax(over))  # the first point past the line: cut between k - 1 and k
        if k < 1:
            short.append(n)
            continue
        a, b = d_in[k - 1] + below, d_in[k] + below  # a >= 0 > b
        t = float(np.clip(a / max(a - b, 1e-9), 0.0, 1.0))
        end = P[k - 1] + t * (P[k] - P[k - 1])
        Q = np.r_[P[:k], end[None]]
        if len(Q) < 2 or np.linalg.norm(Q[-1] - Q[0]) < 1e-6:
            short.append(n)
            continue
        lk["pts"] = [[round(float(x), 2), round(float(y), 2), round(float(z), 4)] for x, y, z in Q]
        for key in ("radius", "tilt"):
            if isinstance(lk.get(key), list) and len(lk[key]) == len(P):
                v = lk[key]
                lk[key] = v[:k] + [round(float(v[k - 1] + t * (v[k] - v[k - 1])), 4)]
        if isinstance(lk.get("handles"), list) and len(lk["handles"]) == len(P):
            lk["handles"] = lk["handles"][:k] + [None]
        cut += 1
    return out, {"cut": cut, "untouched": kept, "too_short": short}


def lock_meshes(sc: Scalp, locks: list, n: int = 40, across: int = 7) -> tuple:
    """(V, F): every lock as a closed lens-section tube in numpy (its spine as Blender curves it, the lens across it
    sized and turned like the node group: lock_extents' outer face plus the cupped inner face). For quick renders and
    silhouettes without Blender; the material, flips and twists of the node group are not reproduced."""
    Vs, Fs, k = [], [], 0
    cs = np.linspace(-1, 1, across)
    for lk in locks:
        S = _catmull(lk["pts"], n)
        u = np.linspace(0, 1, n)
        tg = _unit(np.gradient(S, axis=0))
        nr = _unit(S - sc.C)
        nr = _unit(nr - (nr * tg).sum(1, keepdims=True) * tg)
        if lk.get("tilt"):
            ti = np.interp(u, np.linspace(0, 1, len(lk["tilt"])), lk["tilt"])[:, None]
            nr = nr * np.cos(ti) + np.cross(tg, nr) * np.sin(ti)
        b = _unit(np.cross(nr, tg))
        inp = lk["inputs"]
        f = lock_width(inp, u)[:, None]
        ring = []  # round the lens: the outer face from one edge to the other, then the inner face back
        for side in (1.0, -1.0):
            for c in (cs if side > 0 else cs[::-1][1:-1]):
                sy = side * np.sqrt(max(1 - c * c, 0.0)) ** 0.8
                ring.append(S + f * (c * 0.5 * inp["Width"] * b + (sy * 0.5 * inp["Thickness"] - inp.get("Cup", 0.0) * c * c) * nr))
        R = np.stack(ring, 1)  # (n, m, 3)
        m = R.shape[1]
        idx = k + np.arange(n * m).reshape(n, m)
        a, b_, c_, d_ = idx[:-1, :], idx[1:, :], np.roll(idx[1:, :], -1, 1), np.roll(idx[:-1, :], -1, 1)
        Fs.append(np.stack([a, b_, c_, d_], -1).reshape(-1, 4))
        Vs.append(R.reshape(-1, 3))
        k += n * m
    if not Vs:
        return np.zeros((0, 3)), np.zeros((0, 4), int)
    return np.concatenate(Vs), np.concatenate(Fs)


def lock_extents(sc: Scalp, locks: list, n: int = 40):
    """Points on every lock's outer face (the spine as Blender curves it, the lens across it at 7 places, pushed
    out by half the thickness less the cup, sized along the lock like the node group): what the locks add to the
    silhouette."""
    out = []
    cs = np.linspace(-1, 1, 7)
    for lk in locks:
        S = _catmull(lk["pts"], n)
        u = np.linspace(0, 1, n)
        tg = _unit(np.gradient(S, axis=0))
        nr = _unit(S - sc.C)
        nr = _unit(nr - (nr * tg).sum(1, keepdims=True) * tg)
        if lk.get("tilt"):  # Blender turns the flat side by the (interpolated) tilt about the spine
            ti = np.interp(u, np.linspace(0, 1, len(lk["tilt"])), lk["tilt"])[:, None]
            nr = nr * np.cos(ti) + np.cross(tg, nr) * np.sin(ti)
        b = _unit(np.cross(nr, tg))
        inp = lk["inputs"]
        f = lock_width(inp, u)[:, None]
        for c in cs:
            sy = np.sqrt(max(1 - c * c, 0.0)) ** 0.8
            off = c * 0.5 * inp["Width"] * b + (sy * 0.5 * inp["Thickness"] - inp.get("Cup", 0.0) * c * c) * nr
            out.append(S + f * off)
    return np.concatenate(out) if out else np.zeros((0, 3))


def _hull_lift(sc: Scalp, AA, EE, H, d_in, extra, band=12.0):
    """Raise the underlayer round the sides to the convex hull of itself and the locks' outsides, per azimuth plane
    (a waist under wide top locks read as a divot at the temples). Sides only (the top keeps its lock separations),
    below 60 degrees of elevation."""
    from scipy.spatial import ConvexHull
    if not len(extra):
        return H
    ea, ee = az_el(extra - sc.C)
    rho_x = np.linalg.norm(extra - sc.C, axis=1)
    H = H.copy()
    for i, a in enumerate(AA[:, 0]):
        fa = abs(((a + 180) % 360) - 180)
        wa = _ss((fa - 30) / 15) * (1 - _ss((fa - 140) / 15))
        if wa <= 0:
            continue
        near = np.abs(((ea - a + 180) % 360) - 180) < band / 2
        if near.sum() < 3:
            continue
        e = EE[i]
        hair = d_in[i] > 0
        rho = sc.r(np.full(len(e), a), e) + H[i]
        er = np.radians(e)
        pts = np.stack([rho * np.cos(er), rho * np.sin(er)], 1)[hair]
        ex = np.radians(ee[near])
        pts = np.vstack([pts, np.stack([rho_x[near] * np.cos(ex), rho_x[near] * np.sin(ex)], 1), [[0.0, 0.0]]])
        try:
            hull = ConvexHull(pts)
        except Exception:
            continue
        uu = np.stack([np.cos(er), np.sin(er)], 1)
        best = np.full(len(e), np.inf)
        for eq in hull.equations:
            nd = uu @ eq[:2]
            best = np.minimum(best, np.where(nd > 1e-9, -eq[2] / np.maximum(nd, 1e-12), np.inf))
        need = np.where(hair & np.isfinite(best), best - sc.r(np.full(len(e), a), e) - 0.001, 0.0)
        we = wa * (1 - _ss((e - 62) / 12))
        H[i] = np.maximum(H[i], H[i] + (need - H[i]) * we * (need > H[i]))
    return H


GATE_VIEWS = (("front", 0.0, ("left", "right")), ("three_quarter", 40.0, ("left",)),
              ("three_quarter_r", -40.0, ("right",)))


def _outline(sc: Scalp, P, az: float, sgn: float, edges):
    """The outline (outermost lateral extent, m) of points P per height bin, seen along azimuth az, one side."""
    a = np.radians(az)
    right = np.array([np.cos(a), np.sin(a), 0.0]) * sgn
    x, z = (P - sc.C) @ right, P[:, 2]
    k = np.clip(((z - edges[0]) / (edges[1] - edges[0])).astype(int), -1, len(edges))
    prof = np.full(len(edges), -np.inf)
    ok = (k >= 0) & (k < len(edges))
    np.maximum.at(prof, k[ok], x[ok])
    return prof, right


def _envelope_of(prof, edges):
    """The convex envelope of an outline over its heights (what a hull would give), and the deficit per height."""
    from scipy.spatial import ConvexHull
    good = np.isfinite(prof)
    P = np.stack([prof[good], edges[good]], 1)
    base = P[:, 0].min() - 1.0
    P2 = np.vstack([P, [[base, P[0, 1]], [base, P[-1, 1]]]])
    hv = P2[ConvexHull(P2).vertices]
    hv = hv[hv[:, 0] > base + 0.5]
    hv = hv[np.argsort(hv[:, 1])]
    hx = np.full(len(prof), np.nan)
    hx[good] = np.interp(edges[good], hv[:, 1], hv[:, 0])
    return hx, np.where(good, hx - prof, 0.0)


def _silhouette_fill(sc: Scalp, AA, EE, H, d_in, extra, rounds: int = 14, cap=None):
    """Raise the underlayer where the hair's outline (underlayer + the locks' outsides) dents inside its own convex
    envelope in the front and 3/4 views, below the crown band: under the wide top locks the sides pinched in at
    the temples (a divot either side). The underlayer is pushed out only near the outline, where it can fill it."""
    from . import hair_look
    from scipy.ndimage import gaussian_filter
    hair_m = d_in > 0.002
    H = H.copy()
    for _ in range(rounds):
        V = sc.point(AA, EE, H)
        P = np.vstack([V[hair_m], extra]) if len(extra) else V[hair_m]
        z0 = (sc.lm["lm_brow_mid.L"][2] if "lm_brow_mid.L" in sc.lm else float(sc.C[2])) + 0.02
        ztop = P[:, 2].max() - 0.01 - hair_look.CROWN_BAND
        edges = np.arange(z0, ztop, 0.002)
        raise_ = np.zeros(H.shape)
        worst = 0.0
        for _n, az, sides in GATE_VIEWS:
            for side in sides:
                sgn = 1.0 if side == "left" else -1.0
                prof, right = _outline(sc, P, az, sgn, edges)
                if np.isfinite(prof).sum() < 4:
                    continue
                _hx, deficit = _envelope_of(prof, edges)
                deficit = np.nan_to_num(deficit)
                worst = max(worst, float(deficit.max()))
                x = (V - sc.C) @ right
                kz = ((V[..., 2] - edges[0]) / 0.002).astype(int)
                inb = (kz >= 0) & (kz < len(edges)) & hair_m
                kz = np.clip(kz, 0, len(edges) - 1)
                need = np.where(inb, deficit[kz], 0.0)
                near = _ss((x - (np.where(inb, prof[kz], np.inf) - 0.015)) / 0.012)
                lat = np.maximum((dirs(AA, EE) @ right), 0.25)
                raise_ = np.maximum(raise_, need * near / lat)
        if worst * 1000 <= 0.3 * hair_look.GATE_MM:  # the python outline (lock_extents) runs ~1 mm short of Blender's
            break
        r = gaussian_filter(raise_, sigma=(4.0, 4.0), mode=("wrap", "nearest"))  # broad: a sharp raise read as a shelf
        H = H + 1.5 * r
        if cap is not None:  # never above the volume itself: raised past it, the filler buried the crown locks
            H = np.minimum(H, cap)
    return H


def coverage(sc: Scalp, AA, EE, P, reach: float = 0.004):
    """0..1 on an (az, el) grid: how far each cell is covered by the locks' outer points P (their footprint splatted,
    grown by `reach` m and softened)."""
    from scipy.ndimage import binary_dilation, gaussian_filter
    step = float(AA[1, 0] - AA[0, 0])
    a, e = az_el(np.asarray(P, float) - sc.C)
    ia = np.round((a - AA[0, 0]) / step).astype(int) % AA.shape[0]
    ie = np.clip(np.round((e - EE[0, 0]) / step).astype(int), 0, AA.shape[1] - 1)
    grid = np.zeros(AA.shape, bool)
    grid[ia, ie] = True
    r = max(1, int(round(np.degrees(reach / 0.1) / step)))
    grid = binary_dilation(grid, iterations=r)
    return np.clip(gaussian_filter(grid.astype(float), sigma=r, mode=("wrap", "nearest")) * 1.6, 0, 1)


SHELL_MIN_GAP = 0.0004  # (sh6) m: each shell stands at least this far over the layer below it, the hairline included


# (eased to 0 there, cap and shells were the same triangles: coincident alpha-tested layers render as holes / z-fight)
SHELL_HROW_DROP = None  # (sh6) {"fa": [a0, a1], "el_max": deg}: the shells style's hairline-row cards whose middle lies


# a0..a1 deg from the front and under el_max deg over the scalp centre are dropped (Garrett's sideburn: dense cards drew
# flat grey dabs with round ends at game distance; the cap's tapered strands are the sideburn there)
def shell_gaps(dhs, gap=None) -> list:
    """(sh6) The shells' offsets over the cap (one array per shell, inner first), each raised to at least `gap`
    (SHELL_MIN_GAP) over the one below. Eased to 0 at the hairline, cap and shells were the SAME triangles there: two
    alpha-tested layers on one surface render holes (Garrett's black specks along the nape and the sideburn top: shells
    1 + 2 alone made them, each alone none) or z-fight in an engine."""
    g = SHELL_MIN_GAP if gap is None else float(gap)
    out, prev = [], None
    for d in dhs:
        d = np.asarray(d, float)
        prev = np.maximum(d, (0.0 if prev is None else prev) + g)
        out.append(prev)
    return out


def _hrow_dropped(sc, c_) -> bool:
    """(sh7: SHELL_HROW_DROP may be a list of regions: the sideburn, and over the ear / the nape where the fade is paint)"""
    if not c_.get("hrow") or not SHELL_HROW_DROP:
        return False
    a_, e_, _h = sc.coords(np.asarray(c_["P"], float).mean(0)[None])
    fa_ = abs(((float(a_[0]) + 180) % 360) - 180)
    for r_ in (SHELL_HROW_DROP if isinstance(SHELL_HROW_DROP, list) else [SHELL_HROW_DROP]):
        lo_, hi_ = r_.get("fa", (0.0, 180.0))
        if lo_ <= fa_ <= hi_ and float(e_[0]) < float(r_.get("el_max", 90.0)):
            return True
    return False


SHELL_EDGE_LIFT = None  # (sh4) m: the shells cap's lift at the hairline (None = the full lift everywhere)


SHELL_LIFT_EASE = 0.005  # (sh4) m in from the hairline over which the lift eases to SHELL_EDGE_LIFT


CAP_RELAX_FLOOR = True  # (round 30) the relaxed cap keeps the floor cap_under_cards gave it (lift off the scalp)


CAP_RELAX = 60  # (round 26) iterations: the card cap's radius relaxed over its mesh, only lowered (0 = off)


CAP_SMOOTH = 0.0  # deg: the mass cap's height smoothed over this (gaussian sigma, 0 = off; round 26)


def cap_mesh(sc: Scalp, g: dict, height: float, mass: bool = False, step: float = 1.0, sunk: bool = False,
             extra=None, ease: float = 0.0):
    """The scalp inside the hairline pushed out: the dark underlayer (height m) or, mass=True, the groom's whole
    volume (stage a). Its edge dives under the skin just outside the hairline, so the line is crisp."""
    line = hairline(sc, g)
    A = np.arange(0.0, 360.0, step)
    # rows follow the hairline: per column, two rows just outside it (the edge dives under the skin), one ON it, then
    # evenly up to the pole (a hole there read as a groove). On a fixed elevation grid the edge was a staircase of
    # cells crossing the line: fine serrations all along the hairline, read as a torn edge in close-ups
    la = _line_at(line, A)
    n = int(np.ceil((90.0 - la.min()) / step))
    t = np.linspace(0.0, 1.0, n + 1)
    AA = np.repeat(A[:, None], n + 3, 1)
    dive = min(step, 1.0)  # (a coarse cap, for exports, still dives just outside the line)
    EE = np.concatenate([(la - 2.5 * dive)[:, None], (la - 1.2 * dive)[:, None],
                         la[:, None] + t[None, :] * (90.0 - la)[:, None]], 1)
    if mass:
        H, d_in = envelope(sc, g, line, AA, EE)
        if sunk:
            H0 = H
            H = under(g, H, AA, EE, d_in)
            if extra is not None:  # the filler under the partings: where locks part at the outline, the sunk
                H = _silhouette_fill(sc, AA, EE, H, d_in, extra, cap=H0)  # underlayer rises to close the dent (only there)
        if ease > 0:  # the volume comes up from the hairline over `ease` m (a far tier's cap: at full height from
            H = H * (0.3 + 0.7 * _ss(d_in / ease))  # the line it was a thick brim over the forehead)
        if CAP_SMOOTH > 0:  # (round 26) the sunk volume smoothed over the head: its top was a flat block with notches
            # (cards' gaps between) that stood up at the front crown's outline (the RC review's "flat spike" at 1 / 3 m)
            from scipy.ndimage import gaussian_filter
            sg = CAP_SMOOTH / max(step, 1e-3)
            H = np.where(d_in > 0, gaussian_filter(H, (sg, sg), mode=("wrap", "nearest")), H)
        H = np.maximum(H, 0.0015 * _ss(d_in / 0.004))
    else:
        d_in = inside(sc, line, AA, EE)
        H = height * _ss(d_in / 0.006)
    H = np.where(d_in > 0, H, np.maximum(d_in, -0.004) * 0.8)
    V = sc.point(AA, EE, H).reshape(-1, 3)
    na, ne = AA.shape
    idx = np.arange(na * ne).reshape(na, ne)
    live = d_in > -0.003
    faces = []
    for i in range(na):
        i1 = (i + 1) % na
        a, b, c, d = idx[i, :-1], idx[i1, :-1], idx[i1, 1:], idx[i, 1:]
        ok = live[i, :-1] | live[i1, :-1] | live[i1, 1:] | live[i, 1:]
        faces.append(np.stack([a[ok], b[ok], c[ok], d[ok]], 1))
    F = np.concatenate(faces)
    used = np.unique(F)
    remap = -np.ones(len(V), int)
    remap[used] = np.arange(len(used))
    return V[used].astype(np.float32), remap[F].astype(np.int32)
