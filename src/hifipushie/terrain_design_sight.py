"""Sight and small grid helpers: cells, grades, switchbacks, the eye, whether a lake is seen, `sight`, the skyline. Part of the terrain design layer (terrain_design.py has the overview)."""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

def _ij(T, xy):
    return (int(np.clip(round((xy[1] - T.ys[0]) / T.cell), 0, len(T.ys) - 1)),
            int(np.clip(round((xy[0] - T.xs[0]) / T.cell), 0, len(T.xs) - 1)))


def _grades(T, xy, window=20.0, h=None):
    h = T.sample(xy) if h is None else h
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
    if d[-1] < 1:
        return np.zeros(1)
    k = max(1, min(len(d) - 1, int(np.searchsorted(d, window))))
    return np.abs(h[k:] - h[:-k]) / np.maximum(d[k:] - d[:-k], 1e-6)


def _switchbacks(xy, span=30.0):
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
    k = max(1, int(np.searchsorted(d, span)))
    if len(xy) < 2 * k + 1:
        return 0
    a = xy[k:-k] - xy[:-2 * k]
    b = xy[2 * k:] - xy[k:-k]
    cos = (a * b).sum(1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1) + 1e-9)
    sharp = cos < -0.3
    return int(ndimage.label(sharp)[1])


def _target(T, ref):
    """Where to aim at: a peak's summit, a lake's surface, {"at": address, "height": m} (a tower: its top), else 2 m
    above the ground."""
    if isinstance(ref, dict) and "at" in ref:
        xy, h, _ = T.address(ref["at"])
        if isinstance(ref["at"], str) and ref["at"] in T.sites:
            h = T.sites[ref["at"]]["level"]
        return xy, h + float(ref.get("height", 2.0)), T.cell * 2, False
    xy, h, _ = T.address(ref)
    if isinstance(ref, str) and ref in getattr(T, "mesas", {}):  # a mesa: its caprock's top, its whole top is itself
        m = T.mesas[ref]
        return xy, float(np.median(T.H[m["topmask"]])), 1.1 * m["radius"], True
    if isinstance(ref, str) and (ref in T.points or ref.startswith("highest")):
        rad = max(40 * T.k, 1.5 * T.cell)
        own = ((T.spec.get("peaks") or {}).get(ref) or {}).get("radius", 0.02 * T.size)
        if ref in getattr(T, "volcanoes", {}):  # a volcano: aim over its crater at its rim
            own = T.volcanoes[ref]["rc"] + 2 * T.cell
        rad = max(rad, 1.2 * own)  # a rounded summit's own near edge isn't in the way of seeing it
        near = np.hypot(T.X - xy[0], T.Y - xy[1]) < rad
        return xy, float(T.H[near].max()), rad, True  # aim over the summit's middle at its top height

    return xy, h + 2, T.cell * 2, False


def _compass(a):
    return ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"][int(round(a / (math.pi / 4))) % 8] + " side"


def _eye(T, eye_ref, eye_height):
    exy, eh, _ = T.address(eye_ref)
    if isinstance(eye_ref, str) and eye_ref in T.sites:
        eh = T.sites[eye_ref]["level"]
    wl = T.water.ravel()[_cells(T, np.atleast_2d(exy))[0]]
    if np.isfinite(wl):  # from a boat: on the water, not the bed
        eh = max(eh, float(wl))
    return exy, eh + eye_height


def lake_seen(T, eye_ref, lake, eye_height=1.7, angles=False, mask=None):
    """The share of a lake's surface visible from the eye (sampled water cells, each tested by a sight line); with
    angles, also how tall the visible water stands in the view (degrees from its nearest to its farthest seen point:
    at a grazing angle a lake can be 40% "seen" and still be a hairline) and how far below the horizon it lies."""
    exy, e = _eye(T, eye_ref, eye_height)
    wet = (T.lake_id == T.lakes[lake]["id"]) if mask is None else (T.lake_id == T.lakes[lake]["id"]) & mask
    wet = np.nonzero(wet.ravel())[0]
    if not len(wet):
        return (0.0, 0.0, 0.0) if angles else 0.0
    pick = wet[np.linspace(0, len(wet) - 1, min(300, len(wet))).astype(int)]
    seen = 0
    dips = []
    for k in pick:
        txy, top = T.P[k], T.lakes[lake]["level"]
        D = float(np.linalg.norm(txy - exy))
        u = np.linspace(0, 1, max(3, int(D / (T.cell / 2))))[1:-1]
        dd = u * D
        p = exy + (txy - exy) * u[:, None]
        g = np.where(np.isnan(T.water.ravel()[_cells(T, p)]), T.sample(p), -np.inf)  # water doesn't block water
        g = np.where(dd < 1.5 * T.cell, -np.inf, g)  # the ground the eye stands on isn't in the way (a crater rim hid its lake)
        line = e + (top - e) * u
        ok = not (g > line + 0.05).any()
        seen += ok
        if ok:
            dips.append(math.degrees(math.atan2(e - top, D)))
    if angles:
        return seen / len(pick), (max(dips) - min(dips)) if dips else 0.0, min(dips) if dips else 0.0
    return seen / len(pick)


def _cells(T, p):
    iy = np.clip(np.round((p[:, 1] - T.ys[0]) / T.cell).astype(int), 0, len(T.ys) - 1)
    ix = np.clip(np.round((p[:, 0] - T.xs[0]) / T.cell).astype(int), 0, len(T.xs) - 1)
    return iy * len(T.xs) + ix


def sight(T, eye_ref, tgt_ref, eye_height=1.7):
    exy, e = _eye(T, eye_ref, eye_height)
    txy, top, skip, summit = _target(T, tgt_ref)
    D = float(np.linalg.norm(txy - exy))
    n = max(3, int(D / (T.cell / 2)))
    u = np.linspace(0, 1, n)[1:-1]
    dd = u * D
    if summit:
        # a hill's own flanks are the hill: from below a rounded top you only ever see its shoulder. What shows is
        # how far its silhouette (the highest sight line into its own ground) rises above everything in front of it.
        near = dd > 5
        p = exy + (txy - exy) * u[near, None]
        g = T.sample(p)
        # the target's own mass: back along the line from it to where the ground has fallen halfway to the lowest
        half = (top + g.min()) / 2
        low = np.nonzero(g < half)[0]
        zone = max(skip, D - dd[near][low[-1]]) if len(low) else D
        ang = (g - e) / dd[near]
        # (the far half at most: from the target's own flank, the slope right in front of the eye is foreground, not
        # its silhouette: it had an island's summit "2176 m above the skyline")
        own = dd[near] >= max(D - zone, 0.5 * D)
        sil = max(ang[own].max() if own.any() else -np.inf, (top - e) / D)
        front = ang[~own].max() if (~own).any() else -np.inf
        k = int(np.argmax(np.where(~own, ang, -np.inf))) if (~own).any() else 0
        # what shows is from its top down to whichever is higher: the sight line over what's in front, or its own foot
        # (a sight line grazing near ground falls away fast: it had a 90 m mesa "264 m showing")
        base = float(g[own].min()) if own.any() else top
        if isinstance(tgt_ref, str) and tgt_ref in getattr(T, "mesas", {}):
            from .terrain_forms import measure_mesa
            base = top - measure_mesa(T, tgt_ref)["rise"]
        res = {"visible": e + sil * D - max(e + front * D, base), "block": p[k] if (~own).any() else None, "dist": D,
               "base": base}
        top = e + sil * D
    else:
        keep = (dd > 5) & (dd < D - skip)
        p = exy + (txy - exy) * u[keep, None]
        ground = T.sample(p)
        need = e + (ground - e) * D / dd[keep]  # the target height a sight line over each sample needs
        k = int(np.argmax(need)) if len(need) else 0
        need_max = float(need.max()) if len(need) else -np.inf
        res = {"visible": top - need_max, "block": p[k] if len(need) else None, "dist": D}
    # on the skyline: nothing beyond it rises above the line of sight to its top
    top_ang = (top - e) / D
    behind = _skyline(T, exy, e, txy - exy, D + skip)
    res["skyline"] = bool(behind <= top_ang)
    if summit:
        # how far it stands out: its top above the skyline just beside it (the crest it sits on, or the hills around
        # it) and behind it. A peak on a ring wall showed "286 m" (its own flanks) where the picture had a flat skyline
        own = ((T.spec.get("peaks") or {}).get(tgt_ref) or {}).get("radius", 0) if isinstance(tgt_ref, str) else 0
        lateral = max(4 * max(own, skip), 0.05 * T.size)
        v = txy - exy
        side = np.array([-v[1], v[0]]) / (np.linalg.norm(v) + 1e-9)
        # (from 60% of the way out: ground beside the eye is its own foreground, not the crest beside the peak)
        beside = [_skyline(T, exy, e, txy + sgn * side * lateral - exy, 0.6 * D) for sgn in (1, -1)]
        around = max(max(beside), behind)  # the higher shoulder: a peak reads against whichever side is higher
        # never more than its own height above its foot (sea or open sky beside it isn't a skyline: an island's
        # summit "stood 2956 m above the skyline" on a 750 m island)
        res["standout"] = min((top_ang - around) * D, top - res["base"])
    return res


def _label(tgt):
    return f"{tgt['at']} (+{tgt.get('height', 2):g} m)" if isinstance(tgt, dict) and "at" in tgt else str(tgt)


def _skyline(T, exy, e, direction, start):
    """The highest elevation angle of the ground along a bearing from the eye, from `start` metres out to the frame's
    edge (-inf where there is none)."""
    (x0, y0), (x1, y1) = T.spec["extent"]
    u = direction / (np.linalg.norm(direction) + 1e-9)
    far = 2 * T.size
    d = np.arange(start, far, T.cell / 2)
    p = exy + u * d[:, None]
    inb = (p[:, 0] >= x0) & (p[:, 0] <= x1) & (p[:, 1] >= y0) & (p[:, 1] <= y1)
    if not inb.any():
        return -np.inf
    return float(((T.sample(p[inb]) - e) / d[inb]).max())
