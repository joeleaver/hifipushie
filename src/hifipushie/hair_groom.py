"""The groom's parameters and the head's regions: ears, hairline, what is inside it, the part, flow, root fill.
Part of hair (hair.py has the overview)."""
from __future__ import annotations

import copy
import json

import numpy as np

from . import hair
from .hair import HairError, _part_side, _ss, _unit, az_el, full_look
from .hair_head import Scalp

# ------------------------------------------------------------------------------------------------ the groom
def _merge(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return {**a, **{k: _merge(a.get(k), v) for k, v in b.items()}}
    return copy.deepcopy(b) if b is not None else copy.deepcopy(a)


def groom_params(spec: dict) -> dict:
    g = (spec.get("hair") or {}).get("groom") or {}
    bad = set(g) - set(hair.GROOM)
    if bad:
        raise HairError(f"hair groom: unknown keys {sorted(bad)} (have {', '.join(sorted(hair.GROOM))})")
    if g.get("tied") is not None:  # the style makes the tie, the parting (and loose hair for half up)
        from . import hair_flow
        if g.get("tie"):
            raise HairError("hair groom: `tied` (a style) makes the tie: give tie keys in tied.detail.tie, not groom.tie")
        try:
            st = hair_flow.style(g["tied"])
        except ValueError as e:
            raise HairError(str(e)) from None
        g = {**g, "tie": st["tie"], "parting": {**st["parting"], **{k: v for k, v in (g.get("parting") or {}).items() if k != "side"}}}
        if st.get("loose"):
            g["loose"] = {**st["loose"], **(g.get("loose") or {})}
    if g.get("tie"):
        from . import hair_tied
        try:
            hair_tied.params(g["tie"])
        except ValueError as e:
            raise HairError(str(e)) from None
    if g.get("loose"):
        from . import hair_loose
        try:
            hair_loose.params(g["loose"])
        except ValueError as e:
            raise HairError(str(e)) from None
    out = _merge(hair.GROOM, g)
    if "grey" not in g:   # greying temples / sideburns by AGE (the default 0.35 / 0.5 put grey locks on a young head)
        a = grey_age(spec)
        out["grey"] = {k: round(v * a, 4) for k, v in hair.GROOM["grey"].items()}
    return out


def needs_body(g: dict) -> bool:
    """Tied hair that hangs (a hanging tail, escaped pieces) lies on the body's own surface (hair_loose.collider)."""
    tie = g.get("tie")
    if not tie:
        return False
    return any(((t.get("tail") or {}).get("hang") if isinstance(t.get("tail"), dict) else False) or t.get("escaped") or t.get("wisps")
               for t in (tie if isinstance(tie, list) else [tie]))


GREY_AGES = (30.0, 50.0)   # the default groom grey: none before the first age, all of it from the second


def grey_age(spec: dict) -> float:
    """0..1: the share of the default temple / sideburn grey a groom gets, by the model's age (base.body.age, else
    skin.age); a model without an age keeps the full default."""
    age = ((spec.get("base") or {}).get("body") or {}).get("age")
    if age is None:
        age = (spec.get("skin") or {}).get("age")
    if age is None:
        return 1.0
    return float(np.clip((float(age) - GREY_AGES[0]) / (GREY_AGES[1] - GREY_AGES[0]), 0.0, 1.0))


def look_of(spec: dict, h: dict | None = None) -> dict:
    """The hair look with its defaults; look.grey_locks (x each lock's own grey) defaults to grey_age: locks groomed
    earlier carry their grey in the spec, so a young model's look draws none of it unless asked."""
    from . import hair_spec
    h = hair_spec.hair_of(spec) if h is None else h
    lk = full_look(h.get("look"))  # defaults + colours derived from `seen`
    if "grey_locks" not in (h.get("look") or {}):
        lk["grey_locks"] = grey_age(spec)
    return lk


POCKET = 0.012  # m: (one mesh) air this deep along a scalp ray is outside the head, not a pocket in it (an ear canal)


HAIRLINE_JOIN = 25.0  # deg of azimuth over which the default line past traced front_points eases onto their end


EAR_OPEN = 19  # cells of azimuth (x Scalp.STEP deg = 38): what stands off the head narrower than this is "a bump"


EAR_BUMP = 0.004  # m a ray must stand off the head without the bump to count as ear


EAR_LOW = 0.0015  # m: ... and what the ear is grown into from there


EAR_OVER = 0.006  # m the line runs over the found ear's top by default (groom.hairline.ear)


EAR_CLEAR = 0.003  # m: the hairline never runs lower over the found ear than this above its top


SIDEBURNS = 0.014  # m the sideburn reaches below the found ear's top by default


def ear(sc: Scalp) -> dict | None:
    """The EAR found on the head itself (the scalp's rays; every base, no landmark needed): the ear is the bump that
    stands off the side of the head, narrower round the head than any of the skull's own curves. Per row of elevation
    the rays' radius is opened along the azimuth (a flat grey opening EAR_OPEN cells wide: it removes what is narrower
    and keeps the head), left and right averaged; what is left over EAR_BUMP at the side of the head, between brow
    and jaw, is the ear. {"top", "lobe": world z (m) of its highest / lowest point, "front", "back": the azimuths
    (deg, the left ear) its upper two thirds span, "az_top", "cells": [[az, el], ...]}, or None when the head has
    no such bump (a creature, hair or a hat modelled into the body): callers then keep their old rule.
    (hairline() guessed the ear's top at the outer brow + 4 mm: 0.7 - 3.2 cm too high on ten heads of three bases.)"""
    got = getattr(sc, "_ear", False)
    if got is not False:
        return got
    from scipy import ndimage
    R = np.asarray(sc.R, float)
    na = len(sc.A)
    Rs = 0.5 * (R + R[(-np.arange(na)) % na])
    pad = EAR_OPEN + 4
    Rp = np.concatenate([Rs[-pad:], Rs, Rs[:pad]], 0)
    D = Rs - ndimage.grey_opening(Rp, size=(EAR_OPEN, 1))[pad:-pad]
    ia = np.nonzero((sc.A >= 66) & (sc.A <= 126))[0]
    W = D[ia]
    AA, EE = np.meshgrid(sc.A[ia], sc.E, indexing="ij")
    Zw = sc.point(AA, EE, 0.0)[..., 2]
    if "lm_brow_mid.L" in sc.lm and "lm_nose_base" in sc.lm:
        z1 = sc.lm["lm_brow_mid.L"][2] + 0.02
        z0 = sc.lm["lm_nose_base"][2] - 0.05
    else:
        z1, z0 = sc.C[2] + 0.06, sc.C[2] - 0.12
    M = (W > EAR_BUMP) & (W < 0.055) & (Zw < z1) & (Zw > z0) & (EE > sc.EL[0] + 4)
    lab, n = ndimage.label(M, structure=np.ones((3, 3), int))
    best, cells = 0.0, None
    for c in range(1, n + 1):
        m = lab == c
        ca = float((AA[m] * W[m]).sum() / W[m].sum())
        if not 80.0 <= ca <= 116.0:
            continue
        sz = float(W[m].sum())
        if sz > best:
            best, cells = sz, m
    sc._ear = None
    if cells is None or int(cells.sum()) < 10:
        return None
    # ... grown into what stands off less but belongs to it (hysteresis): the helix's top and front lie nearly flat
    # on the head, and the bump over EAR_BUMP alone was the ear's back half (the line then crossed the ear's top)
    lo = (W > EAR_LOW) & (W < 0.055) & (Zw < z1) & (Zw > z0) & (EE > sc.EL[0] + 4)
    lab2, _ = ndimage.label(lo, structure=np.ones((3, 3), int))
    cells = np.isin(lab2, np.unique(lab2[cells])) & lo
    thr = EAR_LOW
    # its top, between the highest cell over the threshold and the one above it
    jj = np.arange(W.shape[1])
    top, az_top = -np.inf, 0.0
    for i in np.nonzero(cells.any(1))[0]:
        j = int(jj[cells[i]].max())
        f = 0.0
        if j + 1 < W.shape[1]:
            f = float(np.clip((W[i, j] - thr) / max(W[i, j] - W[i, j + 1], 1e-6), 0.0, 1.0))
        z = float(sc.point(float(AA[i, j]), float(EE[i, j]) + f * sc.STEP, 0.0)[2])
        if z > top:
            top, az_top = z, float(AA[i, j])
    lobe = float(Zw[cells].min())
    if not 0.02 <= top - lobe <= 0.13:
        return None
    up = cells & (Zw > top - 0.67 * (top - lobe))
    sc._ear = {"top": top, "lobe": lobe, "front": float(AA[up].min()) - 0.5 * sc.STEP,
               "back": float(AA[up].max()) + 0.5 * sc.STEP, "az_top": az_top,
               "cells": np.stack([AA[cells], EE[cells]], 1).tolist()}
    return sc._ear


def hairline(sc: Scalp, g: dict) -> np.ndarray:
    """The hairline's elevation (degrees) at each whole degree of azimuth (360,), symmetric left/right: from the
    landmarks (front height in brow-to-nose units, temples receding, sideburns, clear of the ears, the nape)."""
    from . import hair_seat
    g = hair_seat.fit_to_head(g, sc)
    hl = g["hairline"]
    if hl.get("points"):
        ctrl = [(float(a), float(z)) for a, z in hl["points"]]
    elif "lm_brow_mid.L" not in sc.lm:  # no landmarks: elevations (degrees from the centre) per azimuth
        dflt = {"ear_az": 95.0, "front_el": 35.0, "temple_el": 40.0, "sideburn_el": -5.0, "ear_el": 18.0, "nape_el": -25.0}
        # (only a human base's head: a creature's ear is whatever its maker built, and its elevations were set by eye)
        er = ear(sc) if str(hl.get("ear_from") or "mesh") == "mesh" and getattr(sc, "human", False) else None
        if er is not None:  # (a head without landmarks that HAS ears, e.g. a template body: the line over the found
            # ear instead of 18 deg above the head joint; explicit elevations still win)
            _, e_t, _ = sc.coords(sc.point(er["az_top"], 0.0, 0.0) * [1, 1, 0] + [0, 0, er["top"] + 0.01])
            _, e_s, _ = sc.coords(sc.point(er["front"] - 8.0, 0.0, 0.0) * [1, 1, 0] + [0, 0, er["top"] - SIDEBURNS])
            dflt.update({"ear_az": er["front"] + 6.0, "ear_el": float(e_t), "sideburn_el": float(e_s)})
        ea = float(hl.get("ear_az", dflt["ear_az"]))
        el = {k: float(hl.get(k, dflt[k])) for k in ("front_el", "temple_el", "sideburn_el", "ear_el", "nape_el")}
        eb = ea + 20.0 if er is None or "ear_az" in hl else max(er["back"] + 1.0, ea)
        pts = [(0, el["front_el"]), (ea - 55, el["temple_el"]), (ea - 30, el["temple_el"] - 12),
               (ea - 18, el["sideburn_el"]), (ea - 10, el["sideburn_el"]), (ea - 6, el["ear_el"]),
               (eb, el["ear_el"]), (eb + 12, el["nape_el"] + 15), (180, el["nape_el"])]
        ctrl = [(a, float(sc.point(a, e, 0.0)[2])) for a, e in pts]
    else:
        lm = sc.lm
        bz = lm["lm_brow_mid.L"][2]
        fore = bz - lm["lm_nose_base"][2]
        zf = bz + float(hl.get("front", 0.9)) * fore
        tmp = float(hl.get("temples", 0.012))
        j0 = np.array(lm["lm_jaw_0.L"]) - sc.C
        az_j = float(np.degrees(np.arctan2(j0[0], -j0[1])))
        brow_top = lm["lm_brow_outer.L"][2] + 0.004  # (the old guess of the ear's top: 1-3 cm over the real one)
        ear_bot = lm["lm_nose_base"][2] - 0.01
        nape = ear_bot - 0.015 + float(hl.get("nape", 0.0))
        # nape_v: m the nape line's CENTRE comes down below its sides (a rounded point, not a level cut; Garrett's
        # back photo, the blind review: "narrows to a rounded point at the centre"); 0 = the old near-level line
        nv = float(hl.get("nape_v", 0.0) or 0.0)
        front = [(0, zf), (18, zf - 0.002), (az_j - 44, zf - 0.004 + tmp * 0.5), (az_j - 36, zf - 0.006 + tmp),
                 (az_j - 28, zf - float(hl.get("temple_dip", 0.02)) + tmp), (az_j - 18, brow_top + 0.012)]
        er = ear(sc) if str(hl.get("ear_from") or "mesh") == "mesh" else None
        if er is None:
            ear_top = brow_top
            clear = float(0.01 if hl.get("ear") is None else hl["ear"])
            sb = ear_top - float(0.028 if hl.get("sideburns") is None else hl["sideburns"])
            ctrl = front + [(az_j - 10, sb + 0.006), (az_j - 7, sb), (az_j - 3, sb + 0.006), (az_j + 3, ear_top + clear),
                            (az_j + 22, ear_top + clear), (az_j + 34, ear_bot + 0.006), (150, nape + 0.006 + 0.5 * nv), (165, nape + 0.2 * nv), (180, nape - 0.5 * nv)]
        else:
            # THE EAR AS IT IS ON THIS HEAD (tesshair6): the line passes `ear` m over the found ear's top from its
            # front to its back, the sideburn hangs `sideburns` m below that top just in front of the ear's front
            # attachment, and behind the ear the line comes down its back. (With the ear guessed from the brow the
            # line ran 1-3 cm above the ear on every base: a bare band over the ear, the "shaved temple" of tied
            # hair, and sideburns that ended above the ear's top.) The line never dips onto the ear itself: an
            # `ear` below EAR_CLEAR (old grooms patched the high guess with negative values) is raised to it
            ear_top = er["top"]
            af, ab = er["front"], er["back"]
            clear = max(float(EAR_OVER if hl.get("ear") is None else hl["ear"]), EAR_CLEAR)
            sb = ear_top - max(float(SIDEBURNS if hl.get("sideburns") is None else hl["sideburns"]), 0.004 - clear)
            lob = max(min(ear_bot, ear_top - 0.02), er["lobe"])
            ctrl = [c for c in front if c[0] < af - 16] + [
                (af - 11, sb + 0.007), (af - 7.5, sb), (af - 3.5, sb + 0.003), (af + 0.5, ear_top + clear),
                (ab - 1, ear_top + clear), (ab + 4, ear_top + clear - 0.4 * (ear_top + clear - lob)),
                (ab + 11, lob + 0.006), (150, nape + 0.006 + 0.5 * nv), (165, nape + 0.2 * nv), (180, nape - 0.5 * nv)]
    if hl.get("front_points"):  # traced (e.g. from the reference through the matched camera): [[az, z], ...] over the
        fp = sorted((float(x), float(z)) for x, z in hl["front_points"])  # front; the rest of the line kept
        # ...eased onto the traced end (HAIRLINE_JOIN deg): joined as it was, the default temple stood ~4 mm off the
        # traced front's end and the hairline stepped up and down again at the temple corner (a notch in the edge)
        ca = np.array([c[0] for c in ctrl])
        cz = np.array([c[1] for c in ctrl])
        dz = fp[-1][1] - float(np.interp(fp[-1][0], ca, cz))
        ctrl = fp + [(a, z + dz * max(0.0, 1.0 - (a - fp[-1][0]) / HAIRLINE_JOIN)) for a, z in ctrl
                     if a > fp[-1][0] + 4]
    # z -> elevation on the scalp, per control's azimuth (the column's first height reaching z, from the bottom)
    A, E = [], []
    for a, z in ctrl:
        el = np.arange(-60.0, 89.0, 0.25)
        zz = sc.point(np.full(len(el), a), el, 0.0)[:, 2]
        k = int(np.argmax(zz >= z)) if np.any(zz >= z) else len(el) - 1
        A.append(a)
        E.append(el[k])
    from scipy.interpolate import PchipInterpolator
    a = np.array(A, float)
    e = np.array(E, float)
    AA = np.r_[-a[::-1][:-1], a, 360 - a[::-1][1:]]
    EE = np.r_[e[::-1][:-1], e, e[::-1][1:]]
    AA, idx = np.unique(AA, return_index=True)
    return PchipInterpolator(AA, EE[idx])(np.arange(360.0))


def _line_at(line, az):
    f = np.asarray(az, float) % 360
    i0 = np.floor(f).astype(int) % 360
    return line[i0] + (f - np.floor(f)) * (line[(i0 + 1) % 360] - line[i0])


def inside(sc: Scalp, line, az, el):
    """Signed distance (m) inside the hairline over the scalp (> 0 in the hair): the distance to the hairline curve
    (along the elevation alone, the steep run from temple to sideburn measured long and creased the mass)."""
    from scipy.spatial import cKDTree
    key = (id(sc), float(np.sum(line)))
    tree = _LINES.get(key)
    if tree is None:
        a = np.arange(0.0, 360.0, 0.1)
        e = _line_at(line, a)
        L = sc.point(a, e, 0.0)
        # densify steep stretches: consecutive points closer than 1 mm
        seg = np.linalg.norm(np.diff(L, axis=0, append=L[:1]), axis=1)
        extra = [L]
        for i in np.nonzero(seg > 0.001)[0]:
            n = int(seg[i] / 0.001) + 1
            t = np.linspace(0, 1, n + 1)[1:-1]
            a1 = a[i] + 0.1 * t
            e1 = e[i] + (e[(i + 1) % len(e)] - e[i]) * t
            extra.append(sc.point(a1, e1, 0.0))
        tree = cKDTree(np.concatenate(extra))
        if len(_LINES) > 8:
            _LINES.clear()
        _LINES[key] = tree
    az, el = np.asarray(az, float), np.asarray(el, float)
    d, _ = tree.query(sc.point(az, el, 0.0).reshape(-1, 3))
    d = d.reshape(az.shape)
    return np.where(el >= _line_at(line, az), d, -d)


_LINES: dict = {}


def weights(az, el, d_in, blend: float = 1.0):
    """Region weights (n, 5) in REGIONS order from where a point sits: front = the first few cm behind the front
    hairline, top above ~30 deg, sides round the ears, back behind, nape low at the back. `blend` x: every transition
    that many times wider about its middle (groom.loose.blend: no ledge where a lifted top meets close sides)."""
    fa = np.abs(((np.asarray(az) + 180) % 360) - 180)  # 0 front .. 180 back
    k = max(float(blend), 0.1)
    front = (1 - _ss((d_in - 0.035 + 0.015 * k) / (0.03 * k))) * (1 - _ss((fa - 42.5 + 12.5 * k) / (25 * k)))
    top = _ss((np.asarray(el) - 32 + 10 * k) / (20 * k))
    back = _ss((fa - 125 + 20 * k) / (40 * k))
    nape = _ss((-np.asarray(el) + 10 - 10 * k) / (20 * k))
    rest = (1 - front) * (1 - top)
    W = np.stack([front, (1 - front) * top, rest * (1 - back), rest * back * (1 - nape), rest * back * nape], -1)
    return W / np.maximum(W.sum(-1, keepdims=True), 1e-9)


def _region(g: dict, key: str, W):
    v = g[key]
    vals = np.array([float(v[r]) for r in hair.REGIONS])
    return W @ vals


def envelope(sc: Scalp, g: dict, line, az, el):
    """The hair's outer surface height above the scalp (m): `_envelope` made convex round the sides (`_fill`)."""
    H, d_in = _envelope(sc, g, line, az, el)
    return np.maximum(H, _fill(sc, g, line)(az, el) * (d_in > 0)), d_in


_FILLS: dict = {}


def _fill(sc: Scalp, g: dict, line):
    """Per azimuth round the sides, the hair's profile (in the vertical plane through the centre) filled out to its
    convex hull: where the full top meets the close sides the outline pinched in above the temples (a waist in the
    front view). Returns an interpolator (az, el) -> the height the hull asks for (0 where nothing is filled)."""
    from scipy.interpolate import RegularGridInterpolator
    from scipy.spatial import ConvexHull
    key = (id(sc), json.dumps(g, sort_keys=True, default=float), float(np.sum(line)))
    if key in _FILLS:
        return _FILLS[key]
    A = np.arange(0.0, 361.0, 2.0)
    E = np.arange(-60.0, 90.01, 1.0)
    out = np.zeros((len(A), len(E)))
    for i, a in enumerate(A):
        fa = abs(((a + 180) % 360) - 180)
        w = _ss((fa - 25) / 15) * (1 - _ss((fa - 140) / 20))  # the sides the front and 3/4 views outline
        if w <= 0:
            continue
        aa = np.full(len(E), a)
        H, d_in = _envelope(sc, g, line, aa, E)
        hair = d_in > 0
        if hair.sum() < 3:
            continue
        rho = sc.r(aa, E) + H
        e = np.radians(E)
        pts = np.stack([rho * np.cos(e), rho * np.sin(e)], 1)[hair]
        pts = np.vstack([pts, [0.0, 0.0]])
        hull = ConvexHull(pts)
        # the hull's radius along each hair ray: the nearest facet the ray leaves through
        u = np.stack([np.cos(e), np.sin(e)], 1)
        best = np.full(len(E), np.inf)
        for eq in hull.equations:  # n.x + c <= 0 inside
            nd = u @ eq[:2]
            t = np.where(nd > 1e-9, -eq[2] / np.maximum(nd, 1e-12), np.inf)
            best = np.minimum(best, t)
        need = np.where(hair & np.isfinite(best), best - sc.r(aa, E), 0.0)
        out[i] = np.maximum(need - H, 0.0) * w + H * (need > H) * w
    fill = RegularGridInterpolator((A, E), out, bounds_error=False, fill_value=0.0)

    def f(az, el):
        az, el = np.asarray(az, float), np.asarray(el, float)
        return fill(np.stack([az % 360, np.clip(el, -60, 90)], -1).reshape(-1, 2)).reshape(np.shape(az))
    if len(_FILLS) > 8:
        _FILLS.clear()
    _FILLS[key] = f
    return f


def _envelope(sc: Scalp, g: dict, line, az, el):
    """The hair's outer surface height above the scalp (m). On top a dome: highest a few cm behind the front hairline
    (volume "front"), falling smoothly to "crown" at the back of the top; the front edge rounds up off the hairline
    like a bull nose (no square wall); the side of the parting the hair is combed away from (his right, for a left
    part) carries more than the other; sides, back and nape their own volume with a short clean ramp."""
    d_in = inside(sc, line, az, el)
    W = weights(az, el, d_in)
    vol = g["volume"]
    fa = np.abs(((np.asarray(az) + 180) % 360) - 180)
    P = sc.point(az, el, 0.0)
    # the top's dome, by distance back from the front hairline (m)
    vf, vt, vc = float(vol["front"]), float(vol["top"]), float(vol["crown"])
    back = np.clip(d_in, 0, None)
    dome = vc + (vf - vc) * np.exp(-((back - 0.03) / 0.075) ** 2)
    dome = np.where(back < 0.03, vf, dome)
    dome = np.minimum(dome, vt + (vf - vt) * (1 - _ss((back - 0.02) / 0.05))) if vt < vf else dome
    # rounded across as well: the dome's height falls off toward the sides, so the front view is a curve over the top
    # and the sides stay close (a dome as full at its edges as on the crest made square shoulders and a bucket back)
    vs = float(vol["sides"])
    # volume.across: how much of the dome's height is gone over the upper sides (0.65: a crest down the middle; less, a
    # broad flat top like a side-swept cut's, where the top outline in the front view is a wide curve, not a peak)
    # volume.crest: where across the head (x, m, his left +) the top's crest runs: a quiff swept off a side part is
    # highest just across the part and falls away toward the swept side (0: down the middle)
    dome = vs + (dome - vs) * (1 - float(vol.get("across", 0.65))
                               * _ss((np.abs(P[..., 0] - sc.C[0] - float(vol.get("crest", 0.0))) - 0.02) / 0.06))
    topw = W[..., 0] + W[..., 1]
    side = W[..., 2] * float(vol["sides"]) + W[..., 3] * float(vol["back"]) + W[..., 4] * float(vol["nape"])
    tp = vol.get("taper")
    if tp:  # volume.taper {"from": el, "to": el, "floor": f}: sides and back full down to elevation `from` (deg),
        # easing to `floor` x their volume at `to`: short tapered sides and back under a full top (a back as full at
        # the nape as at the occiput reads as a bucket)
        e0, e1, fl = float(tp.get("from", 30.0)), float(tp.get("to", -15.0)), float(tp.get("floor", 0.35))
        side = side * (fl + (1 - fl) * _ss((np.asarray(el, float) - e1) / max(e0 - e1, 1e-6)))
    v = topw * dome + side
    xp = _part_x(g)
    if xp is not None:  # the combed-away side is fuller; the part side lies flatter
        sgn = 1.0 if xp >= 0 else -1.0
        # parting.flat: how much flatter the part side lies (top and side); parting.full: how much fuller the side
        # the hair is swept onto (a side-swept cut piles up over the far temple)
        pw = topw + W[..., 2]
        flat, full = float(g["parting"].get("flat", 0.22)), float(g["parting"].get("full", 0.0))
        v = v * (1 - flat * pw * _ss(sgn * (P[..., 0] - xp) / 0.03)) \
            * (1 + full * pw * _ss(-sgn * (P[..., 0] - xp + sgn * 0.02) / 0.05))
        # along the parting the volume goes down to the scalp: the roots on both sides grow out of it there, and
        # the part is a thin line of scalp and shadow between clumps (a dip left the volume as a smooth patch)
        # parting.front (m): the part's dip fades in over this far behind the front hairline, so the front roll stays
        # whole and the hairline one clean sweep (dipping right to the hairline it cut a V notch into the edge)
        pf = float(g["parting"].get("front", 0.015))
        fade = _ss(d_in / pf) if pf > 0 else 1.0
        v = v * (1 - float(g["parting"].get("depth", 0.9)) * fade
                 * _part(sc, g, az, el, float(g["parting"].get("width", 0.012))))
    # volume.ramp: how far back from the front hairline the top reaches its height (m): short, the front stands as a
    # wall and the front locks over it jut like a cap's peak; longer, the front face leans back (a quiff's wave)
    ramp = topw * float(vol.get("ramp", 0.028)) + (1 - topw) * (0.8 * v + 0.002)  # continuous: a switch creased the temples
    x = np.clip(d_in / ramp, 0, 1)
    return v * np.sin(0.5 * np.pi * x) ** 0.8, d_in


def _part(sc: Scalp, g: dict, az, el, width):
    """How much a scalp point is in the parting (0..1) within `width` m of its line."""
    from . import hair_spec
    pt = g["parting"]
    side = pt.get("side", "left")
    if side == "none":
        return np.zeros(np.shape(az))
    xp = _part_side(side) * float(pt.get("offset", 0.03))
    P = sc.point(az, el, 0.0)
    if pt.get("line"):  # a drawn/traced part: distance to its polyline on the scalp, faded in past its front end
        q = np.asarray(pt["line"], float)
        L = hair_spec._catmull(sc.point(q[:, 0], q[:, 1], 0.0), 40)
        A, AB = L[:-1], L[1:] - L[:-1]
        sh = np.shape(az)
        X = P.reshape(-1, 3)
        best = np.full(len(X), np.inf)
        tf = np.zeros(len(X))
        cum = np.r_[0.0, np.cumsum(np.linalg.norm(AB, axis=1))]
        for k in range(len(A)):
            t = np.clip(((X - A[k]) @ AB[k]) / max(AB[k] @ AB[k], 1e-12), 0, 1)
            d = np.linalg.norm(X - (A[k] + t[:, None] * AB[k]), axis=1)
            m = d < best
            best[m], tf[m] = d[m], (cum[k] + t[m] * np.linalg.norm(AB[k]))
        # past the front end the distance keeps growing (t clipped): fades there by itself; soft at the back end
        fade = 1 - _ss((tf - cum[-1] + 0.015) / 0.015)
        return (np.exp(-(best / width) ** 2) * np.maximum(fade, 0.0)).reshape(sh) * _ss((np.asarray(el) - 20) / 10)
    yf = sc.C[1] - sc.r(0.0, 30.0) * np.cos(np.radians(30.0))
    along = _ss((P[..., 1] - yf + 0.005) / 0.01) * (1 - _ss((P[..., 1] - yf - float(pt.get("length", 0.1))) / 0.02))
    return along * np.exp(-((P[..., 0] - xp) / width) ** 2) * _ss((np.asarray(el) - 20) / 10)


def part_line(sc: Scalp, g: dict):
    """The parting as [[az, el], ...] from its front end back: groom.parting.line (e.g. carried from a traced
    reference), else a straight line at x = offset from the front of the scalp back `length`."""
    from . import hair_drawn
    pt = g.get("parting") or {}
    if pt.get("line"):
        return np.asarray(pt["line"], float)
    xp = _part_x(g)
    if xp is None:
        return None
    y0 = -sc.r(0.0, 30.0) * np.cos(np.radians(30.0))
    t = np.linspace(0.0, float(pt.get("length", 0.1)), 6)
    a, e = hair_drawn.top_to_azel(sc, np.stack([np.full(6, xp), y0 + t], 1))
    return np.stack([a, e], 1)


def part_side_of(sc: Scalp, g: dict):
    """A function roots (k, 3) -> (side -1 / +1 of the parting, distance m to its line) for the clump cut
    (hair_clumps.cut: no card spans the part), or None if the groom has no parting."""
    from . import hair_spec
    try:
        pl = part_line(sc, g)
    except (KeyError, TypeError):
        return None
    if pl is None or len(pl) < 2:
        return None
    L = hair_spec._catmull(sc.point(np.asarray(pl)[:, 0], np.asarray(pl)[:, 1], 0.0), 40)

    def f(Rt):
        Rt = np.asarray(Rt, float)
        A, AB = L[:-1], L[1:] - L[:-1]
        t = np.clip(((Rt[:, None] - A[None]) * AB[None]).sum(-1) / np.maximum((AB * AB).sum(-1), 1e-12)[None], 0, 1)
        near = A[None] + t[..., None] * AB[None]
        d = np.linalg.norm(Rt[:, None] - near, axis=-1)
        k = d.argmin(1)
        i = np.arange(len(Rt))
        nb = near[i, k]
        radial = _unit(nb - sc.C)
        side = np.sign((np.cross(AB[k], radial) * (Rt - nb)).sum(-1))
        return side, d[i, k]
    return f


def _part_x(g):
    pt = g["parting"]
    side = pt.get("side", "left")
    return None if side == "none" else _part_side(side) * float(pt.get("offset", 0.03))


def flow(sc: Scalp, g: dict, P, W, away):
    """The combing direction at points P (tangent to the scalp), from the regions' direction words."""
    fl = g["flow"]
    out = np.zeros(P.shape)
    for ri, r in enumerate(hair.REGIONS):
        words = fl.get(r) or {}
        if isinstance(words, str):
            words = {words: 1.0}
        v = np.zeros(P.shape)
        for wd, amt in words.items():
            if wd not in hair.WORDS:
                raise HairError(f"hair flow {r}: unknown direction {wd!r} (have {', '.join(hair.WORDS)})")
            vec = away[..., None] * np.array([1.0, 0, 0]) if wd == "away" else np.array(hair.WORDS[wd], float)
            v = v + float(amt) * vec
        out += W[..., ri:ri + 1] * v
    n = _unit(P - sc.C)
    t = out - (out * n).sum(-1, keepdims=True) * n
    return t


def _poisson(sc: Scalp, rng, spacing_at, ok, n_try=6000):
    """Blue-noise roots (az, el) over the scalp where ok(az, el), at least spacing_at(az, el) apart (dart throwing)."""
    U = _unit(rng.normal(size=(n_try, 3)))
    az, el = az_el(U)
    keep = ok(az, el)
    az, el = az[keep], el[keep]
    P = sc.point(az, el, 0.0)
    sp = spacing_at(az, el)
    chosen, pts = [], np.zeros((0, 3))
    for i in rng.permutation(len(az)):
        if len(pts) and np.any(np.linalg.norm(pts - P[i], axis=1) < 0.5 * (sp[i] + sp[chosen])):
            continue
        chosen.append(i)
        pts = np.vstack([pts, P[i]])
    return az[chosen], el[chosen]


# the groom's keys in metres (scaled with the head by `fit`); lists of [az, z] keep az and scale z about the centre
_METRE_KEYS = {("length",), ("volume",), ("hairline", "temples"), ("hairline", "temple_dip"), ("hairline", "ear"),
               ("hairline", "sideburns"), ("hairline", "nape"), ("parting", "offset"), ("parting", "width"),
               ("parting", "length"), ("parting", "front"), ("loose", "length"), ("loose", "spacing"), ("loose", "lift"), ("loose", "lift_ramp"),
               ("loose", "body"), ("loose", "thickness"), ("loose", "level"), ("loose", "swoop", "depth"),
               ("loose", "swoop", "length"), ("loose", "fringe", "length"), ("loose", "fringe", "depth"),
               ("loose", "fringe", "level"), ("tie", "out"), ("tie", "gather", "lift"), ("tie", "gather", "width"),
               ("tie", "tail", "length"), ("tie", "tail", "fullness"), ("tie", "curtain", "lift"),
               ("tie", "frame", "length"), ("tie", "frame", "width")}


_UNITLESS = {"across", "ramp"}  # (volume.across / ramp are shares, not metres)


# The tie's own geometry that a tied STYLE writes in absolute metres (hair_flow.style: the dome's stand-off, wisp and
# stray lengths, the tail's sway / air / lock waves). Until 2026-10-14 fit_to_head did not scale these: th_W18 carried
# onto tp_h3 (a 15 % bigger scalp) kept its dome and face wisps at the old head's size while its tail scaled (review:
# "shorter face wisps", a flatter top). They scale by this head over the one they were last GROWN at (`fit.abs_r`,
# stamped by carry), so a groom regrown on its own head is unchanged. Value: the dict's keys that are NOT metres.
_TIE_KEYS = {("tie", "gather", "volume"): {"arc", "layers", "locks", "cross", "hold"}, ("tie", "gather", "puff"): set(),
             ("tie", "gather", "zig"): set(), ("tie", "gather", "above"): set(), ("tie", "wisps", "length"): set(),
             ("tie", "wisps", "over"): set(), ("tie", "tail", "stray_length"): set(), ("tie", "tail", "sway"): set(),
             ("tie", "tail", "sway_length"): set(), ("tie", "tail", "flick"): set(), ("tie", "tail", "air"): set(),
             ("tie", "tail", "lock_wave"): set(), ("tie", "tail", "lock_wavelength"): set(),
             ("tie", "tail", "coil_radius"): set(), ("tie", "escaped", "length"): set()}


def head_ref(sc: Scalp) -> dict:
    """The head a groom is made on, for `groom.fit`: its scalp's median radius and centre (m)."""
    return {"r": round(float(np.median(sc.R)), 5), "c": [round(float(x), 5) for x in sc.C]}
