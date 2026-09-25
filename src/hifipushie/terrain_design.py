"""The design layer over the terrain skeleton: what a level designer asks for, compiled onto the ground.

zones   named regions (quadrants, inside a closed ridge, polygons, near a place, elevation/slope bands, and/any/not,
        inset, feather), used by everything below and as addresses (their centroid).
walls   "unclimbable": the ground just outside a zone is raised so leaving it means a stretch at least `min_slope`
        steep for `height` metres; exceptions (a pass) are left alone. Checked per boundary point afterwards.
sites   flat pads (a village, a spawn): cut/fill to a level, with banks; kept above nearby water.
routes  least-cost paths under a grade limit (switchbacks come out of the search), smoothed, graded, carved.
cover   density/weight masks per layer (forest, rock, scree, snow, grass, ...): region x slope band x elevation band
        x gradient between two places x breakup noise, minus what it avoids (water, routes, sites, zones).
views   intent "see": how much of a target shows over the terrain, and whether it stands on the skyline.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

from . import noise
from .terrain import Line, _arclen, smoothstep

NAMED_REGIONS = ("everywhere", "centre", "north", "south", "east", "west")

COVER_TYPES = {
    "forest":    {"slope": [0, 38], "avoid": ["water", "routes", "sites"], "breakup": {"scale": 150, "amount": 0.3},
                  "color": [0.12, 0.25, 0.11], "trees": "conifer"},
    "conifer":   {"slope": [0, 38], "avoid": ["water", "routes", "sites"], "breakup": {"scale": 150, "amount": 0.3},
                  "color": [0.10, 0.22, 0.12], "trees": "conifer"},
    "deciduous": {"slope": [0, 32], "avoid": ["water", "routes", "sites"], "breakup": {"scale": 150, "amount": 0.3},
                  "color": [0.24, 0.34, 0.12], "trees": "broadleaf"},
    "rock":      {"slope": [32, 90], "breakup": {"scale": 60, "amount": 0.3}, "color": [0.45, 0.43, 0.40]},
    "scree":     {"slope": [24, 36], "breakup": {"scale": 40, "amount": 0.3}, "color": [0.58, 0.54, 0.47]},
    "grass":     {"slope": [0, 30], "avoid": ["water"], "color": [0.45, 0.56, 0.26]},
    "meadow":    {"slope": [0, 25], "avoid": ["water", "routes"], "breakup": {"scale": 80, "amount": 0.3},
                  "color": [0.55, 0.62, 0.30]},
    "snow":      {"slope": [0, 45], "color": [0.94, 0.95, 0.97]},
    "sand":      {"slope": [0, 15], "color": [0.78, 0.71, 0.52]},
    "mud":       {"slope": [0, 10], "color": [0.33, 0.27, 0.19]},
}


# ---------------------------------------------------------------- regions

def region(T, r) -> np.ndarray:
    """A soft mask 0..1 on the grid."""
    shape = T.X.shape
    (x0, y0), (x1, y1) = T.spec["extent"]
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    if isinstance(r, str):
        if r in T.zones:
            return region(T, T.zones[r])
        if r.startswith("zone:"):
            return region(T, T.zones[r[5:]])
        if r == "everywhere":
            return np.ones(shape)
        if r == "centre":
            return (np.hypot((T.X - mx) / (x1 - x0), (T.Y - my) / (y1 - y0)) < 0.25).astype(float)
        if r.startswith("quadrant:"):
            q = r.split(":")[1]
            m = np.ones(shape, bool)
            m &= (T.Y >= my) if "n" in q else (T.Y < my)
            m &= (T.X >= mx) if "e" in q else (T.X < mx)
            return m.astype(float)
        half = r.split(":")[1] if r.startswith("half:") else r
        if half in ("north", "n"):
            return (T.Y >= my).astype(float)
        if half in ("south", "s"):
            return (T.Y < my).astype(float)
        if half in ("east", "e"):
            return (T.X >= mx).astype(float)
        if half in ("west", "w"):
            return (T.X < mx).astype(float)
        raise ValueError(f"unknown region {r!r}")
    if isinstance(r, list):
        return np.max([region(T, x) for x in r], axis=0)
    m = None

    def meet(a):
        nonlocal m
        m = a if m is None else np.minimum(m, a)

    if "inside" in r:
        from skimage.draw import polygon
        L = T.lines[r["inside"]]
        if not L.props.get("closed"):
            raise ValueError(f"region inside {r['inside']!r}: that ridge isn't closed (end it where it starts)")
        rr, cc = polygon((L.xy[:, 1] - T.ys[0]) / T.cell, (L.xy[:, 0] - T.xs[0]) / T.cell, shape)
        a = np.zeros(shape)
        a[rr, cc] = 1
        meet(a)
    if "polygon" in r:
        from skimage.draw import polygon
        p = np.array(r["polygon"], float)
        rr, cc = polygon((p[:, 1] - T.ys[0]) / T.cell, (p[:, 0] - T.xs[0]) / T.cell, shape)
        a = np.zeros(shape)
        a[rr, cc] = 1
        meet(a)
    if "near" in r:
        xy = T.address(r["near"])[0]
        meet(smoothstep(r.get("radius", 200) * 1.1, r.get("radius", 200) * 0.9, np.hypot(T.X - xy[0], T.Y - xy[1])))
    if "above" in r:
        meet(smoothstep(r["above"] - 15, r["above"] + 15, T.H))
    if "below" in r:
        meet(smoothstep(r["below"] + 15, r["below"] - 15, T.H))
    if "slope" in r:
        lo, hi = r["slope"]
        s = T._slope()
        meet(smoothstep(lo - 3, lo + 3, s) * smoothstep(hi + 3, hi - 3, s))
    if "region" in r:
        meet(region(T, r["region"]))
    if "all" in r:
        meet(np.min([region(T, x) for x in r["all"]], axis=0))
    if "any" in r:
        meet(np.max([region(T, x) for x in r["any"]], axis=0))
    if "not" in r:
        meet(1 - region(T, r["not"]))
    if m is None:
        raise ValueError(f"region {r!r} says nothing (inside/polygon/near/above/below/slope/all/any/not)")
    if r.get("inset"):
        inside = ndimage.distance_transform_edt(m > 0.5) * T.cell
        m = m * smoothstep(r["inset"] - T.cell, r["inset"] + T.cell, inside)
    if r.get("feather"):
        m = ndimage.gaussian_filter(m, r["feather"] / T.cell)
    return m


def centroid(T, m):
    w = m.ravel()
    if w.sum() == 0:
        raise ValueError("empty region")
    c = (T.P * w[:, None]).sum(0) / w.sum()
    # a concave region's centroid can fall outside it: take the nearest point inside
    inside = np.nonzero(w > 0.5)[0]
    if len(inside):
        k = inside[np.argmin(np.linalg.norm(T.P[inside] - c, axis=1))]
        return T.P[k].astype(float)
    return c


# ---------------------------------------------------------------- walls, sites, routes

def apply(T):
    for name, w in (T.spec.get("walls") or {}).items():
        _wall(T, name, w)
    for name, s in (T.spec.get("sites") or {}).items():
        _site(T, name, s)
    for name, r in (T.spec.get("routes") or {}).items():
        _route(T, name, r)
    for name, w in (T.spec.get("walls") or {}).items():  # sites and routes may have eaten into a wall
        _check_wall(T, name)


def _gaps(T, w):
    g = np.ones(T.X.shape)
    for a in w.get("except", []):
        xy = T.address(a)[0]
        r = w.get("gap", 80)
        g = np.minimum(g, smoothstep(r * 0.6, r * 1.4, np.hypot(T.X - xy[0], T.Y - xy[1])))
    return g


def _wall(T, name, w):
    """Just outside the zone the ground must rise at least min_slope for `height` metres; raised where it doesn't."""
    inside = region(T, w["around"]) > 0.5
    if not inside.any():
        raise ValueError(f"wall {name!r}: its zone is empty")
    s, (iy, ix) = ndimage.distance_transform_edt(~inside, return_indices=True)
    s *= T.cell
    edge = ndimage.gaussian_filter(T.H, 2)[iy, ix]  # the height at the zone's edge nearest each outside cell
    tan = math.tan(math.radians(w.get("min_slope", 50) + 3))  # a margin: smoothing and texture soften it a little
    height = float(w.get("height", 40))
    band = height / tan
    need = edge + np.minimum(s * tan, height)
    fade = smoothstep(band + 3 * T.cell + height, band + 3 * T.cell, s) * (s > 0)
    raise_by = np.clip(need - T.H, 0, None) * fade * _gaps(T, w)
    T.H = T.H + raise_by
    T.walls[name] = {"inside": inside, "band": band, "raised": float(raise_by.max()), "spec": w}


def _check_wall(T, name):
    """For each boundary point: the steepest ground just outside it. Below min_slope = climbable there."""
    W = T.walls[name]
    w, inside = W["spec"], W["inside"]
    s, (iy, ix) = ndimage.distance_transform_edt(~inside, return_indices=True)
    s *= T.cell
    ring = (s > 0) & (s <= W["band"] + 2 * T.cell)
    slope = T._slope()
    steepest = np.zeros(T.X.shape)
    np.maximum.at(steepest, (iy[ring], ix[ring]), slope[ring])
    steepest = ndimage.maximum_filter(steepest, 5)  # boundary cells no outside cell maps to take their neighbours
    boundary = inside & ~ndimage.binary_erosion(inside)
    boundary[[0, -1], :] = boundary[:, [0, -1]] = False
    gap = _gaps(T, w) < 0.5
    ok = steepest >= w.get("min_slope", 50)
    by, bx = np.nonzero(boundary[::2, ::2])
    by, bx = by * 2, bx * 2
    W["boundary"] = np.stack([T.xs[bx], T.ys[by]], 1)
    W["ok"] = ok[by, bx] | gap[by, bx]
    bad = boundary & ~ok & ~gap
    lab, n = ndimage.label(ndimage.binary_dilation(bad, iterations=2))
    W["climbable"] = []
    for k in range(1, n + 1):
        yy, xx = np.nonzero((lab == k) & bad)
        if len(yy):
            W["climbable"].append(([float(T.xs[xx].mean()), float(T.ys[yy].mean())], len(yy) * T.cell,
                                   float(steepest[yy, xx].max())))
    W["climbable"].sort(key=lambda c: -c[1])
    W["length"] = boundary.sum() * T.cell
    W["fraction"] = 1 - bad.sum() / max(boundary.sum(), 1)


def _site(T, name, s):
    """A flat pad. An address on a lake shore puts the pad inland of that point, clear of the water."""
    ref = s["at"]
    xy, _, d = T.address(ref)
    r = float(s.get("radius", 60))
    if isinstance(ref, str) and ref.endswith("_shore"):
        xy = xy + d * (r + s.get("setback", 5))
    dist = np.hypot(T.X - xy[0], T.Y - xy[1])
    inside = dist <= r
    shore = isinstance(ref, str) and ref.endswith("_shore")
    wet = ~np.isnan(T.water) & (dist < r + 200)
    if "level" in s:
        level = float(s["level"])
    elif shore and wet.any():  # a lakeside pad: just above the water, cut into the bank behind
        level = float(np.nanmax(T.water[wet])) + s.get("above_water", 3.0)
    else:
        level = float(np.median(T.H[inside]))
    if wet.any():
        level = max(level, float(np.nanmax(T.water[wet])) + s.get("above_water", 2.0))
    shoulder = s.get("shoulder", max(20.0, 0.5 * r))
    # banks sized to how far the ground is from the pad (35 deg), at least `shoulder`
    bank = np.clip(np.abs(T.H - level) / math.tan(math.radians(35)), shoulder, shoulder + r)  # capped: beyond, a cliff
    w = smoothstep(r + bank, r, dist)
    before = T.H.copy()
    T.H = T.H * (1 - w) + level * w
    T.sites[name] = {"xy": xy.tolist(), "level": level, "radius": r, "cut": float((before - T.H).max()),
                     "fill": float((T.H - before).max())}
    if max(T.sites[name]["cut"], T.sites[name]["fill"]) > 25:
        T.warnings.append(f"site {name!r} is dug {T.sites[name]['cut']:.0f} m into / built {T.sites[name]['fill']:.0f} m "
                          f"out of the slope: it stands against a cliff or on a mound; move it or give it a level")
    T.masks.setdefault("sites", np.zeros(T.X.shape))
    T.masks["sites"] = np.maximum(T.masks["sites"], smoothstep(r + 8, r, dist))


_OFFS = [(0, 1), (1, 0), (1, 1), (1, -1), (1, 2), (2, 1), (2, -1), (1, -2),
         (1, 3), (3, 1), (3, -1), (1, -3), (2, 3), (3, 2), (3, -2), (2, -3)]  # 32 headings: steep slopes need near-contour ones


def _path(T, H, cell, a, b, maxg, blocked):
    """Least-cost grid path from a to b (row, col) on 32 headings; edges steeper than 1.2 x maxg are left out,
    gentler ones cost more as they near the limit, so the search winds (switchbacks) where it must."""
    ny, nx = H.shape
    idx = np.arange(ny * nx).reshape(ny, nx)
    rows, cols, wts = [], [], []
    for dy, dx in _OFFS:
        ys0, ys1 = max(0, -dy), ny - max(0, dy)
        xs0, xs1 = max(0, -dx), nx - max(0, dx)
        A = idx[ys0:ys1, xs0:xs1]
        B = idx[ys0 + dy:ys1 + dy, xs0 + dx:xs1 + dx]
        length = cell * math.hypot(dy, dx)
        g = np.abs(H.ravel()[B] - H.ravel()[A]) / length
        ok = (g <= maxg) & ~blocked.ravel()[A] & ~blocked.ravel()[B]
        wt = length * (1 + 3 * (g / (0.85 * maxg)) ** 2) + 0.2 * length  # slack below the limit: smoothing adds grade
        for p, q in ((A, B), (B, A)):
            rows.append(p[ok]); cols.append(q[ok]); wts.append(wt[ok])
    G = coo_matrix((np.concatenate(wts), (np.concatenate(rows), np.concatenate(cols))), shape=(ny * nx, ny * nx)).tocsr()
    dist, pred = dijkstra(G, indices=idx[a], return_predecessors=True)
    if not np.isfinite(dist[idx[b]]):
        return None
    out, k = [], idx[b]
    while k >= 0 and k != idx[a]:
        out.append(k)
        k = pred[k]
    out.append(idx[a])
    return np.array(out[::-1])


def _route(T, name, r):
    maxg = float(r.get("max_grade", 0.12))
    width = float(r.get("width", 5))
    stops = [r["from"], *r.get("via", []), r["to"]]
    f = 2 if T.X.size > 90_000 else 1
    # judge grades on ground smoothed over ~30 m: the carve evens out bumps smaller than that anyway
    H = ndimage.gaussian_filter(T.H, 30 / T.cell / 2)[::f, ::f]
    cell = T.cell * f
    blocked = ~np.isnan(T.water[::f, ::f])
    for a in r.get("avoid", []):
        blocked |= region(T, a)[::f, ::f] > 0.5
    if r.get("stay_in"):
        blocked |= region(T, r["stay_in"])[::f, ::f] < 0.5
    pts = []
    relaxed = 1.0
    for a, b in zip(stops[:-1], stops[1:]):
        ca, cb = [T.address(x)[0] for x in (a, b)]
        ga, gb = [(int(round((c[1] - T.ys[0]) / cell)), int(round((c[0] - T.xs[0]) / cell))) for c in (ca, cb)]
        path = None
        for relax in (1.0, 1.4, 2.0, 3.0):
            bl = blocked.copy()
            bl[ga] = bl[gb] = False
            path = _path(T, H, cell, ga, gb, maxg * relax * 0.95, bl)
            if path is not None:
                relaxed = max(relaxed, relax)
                break
        if path is None:
            T.warnings.append(f"route {name!r}: no way from {a!r} to {b!r} (blocked by water/avoid zones?)")
            return
        iy, ix = np.divmod(path, H.shape[1])
        leg = np.stack([T.xs[0] + ix * cell, T.ys[0] + iy * cell], 1)
        leg[0], leg[-1] = ca, cb
        pts.append(leg if not pts else leg[1:])
    if relaxed > 1:
        T.warnings.append(f"route {name!r}: nothing within {100 * maxg:.0f}% connects its stops; searched at "
                          f"{100 * maxg * relaxed:.0f}% (the carve then eases what it can)")
    xy = np.vstack(pts)
    # smooth the staircase of grid steps, then resample evenly
    xy = np.vstack([xy[:1], (xy[:-2] + 2 * xy[1:-1] + xy[2:]) / 4, xy[-1:]])  # once: more cuts switchback corners
    s, length = _arclen(xy)
    n = max(2, int(length / (T.cell / 2)))
    u = np.linspace(0, 1, n)
    xy = np.stack([np.interp(u, s, xy[:, 0]), np.interp(u, s, xy[:, 1])], 1)
    step = np.linalg.norm(np.diff(xy, axis=0), axis=1)  # true steps: shorter than length/(n-1) at corners
    ds = length / (n - 1)
    ground = T.sample(xy)
    h = ndimage.gaussian_filter1d(ground, 30 / ds, mode="nearest")
    for _ in range(30):  # grade limit both ways, pulled back toward the ground
        for i in range(1, n):
            h[i] = np.clip(h[i], h[i - 1] - maxg * step[i - 1], h[i - 1] + maxg * step[i - 1])
        for i in range(n - 2, -1, -1):
            h[i] = np.clip(h[i], h[i + 1] - maxg * step[i], h[i + 1] + maxg * step[i])
        h = 0.8 * h + 0.2 * ndimage.gaussian_filter1d(ground, 10 / ds, mode="nearest")
    for i in range(1, n):
        h[i] = np.clip(h[i], h[i - 1] - maxg * step[i - 1], h[i - 1] + maxg * step[i - 1])
    if r.get("carve", True):
        # each cell follows the leg nearest in 3D (plan distance + height): where switchback legs pass close,
        # plan distance alone gave cells between them the other leg's height
        dk, ik = cKDTree(xy).query(T.P, k=6, distance_upper_bound=width / 2 + 120)
        hk = np.where(np.isfinite(dk), h[np.minimum(ik, n - 1)], np.inf)
        score = dk + np.abs(hk - T.H.ravel()[:, None])
        j = np.argmin(score, axis=1)
        d = dk[np.arange(len(j)), j].reshape(T.X.shape)
        i = ik[np.arange(len(j)), j].reshape(T.X.shape)
        near = np.isfinite(d)
        hr = np.where(near, h[np.minimum(i, n - 1)], T.H)
        half = max(width / 2, 0.75 * T.cell)  # narrower than the grid can't be flat on it
        bank = np.clip(np.abs(T.H - hr) / math.tan(math.radians(34)), 4.0, 40.0)
        w = np.where(near, smoothstep(half + bank, half, d), 0)
        before = T.H.copy()
        T.H = T.H * (1 - w) + hr * w
        cut, fill = float((before - T.H).max()), float((T.H - before).max())
        T.masks.setdefault("routes", np.zeros(T.X.shape))
        T.masks["routes"] = np.maximum(T.masks["routes"], np.where(near, smoothstep(width / 2 + 3, width / 2, d), 0))
    else:
        cut = fill = 0.0
    if max(cut, fill) > 15:
        T.warnings.append(f"route {name!r} cuts {cut:.0f} m / fills {fill:.0f} m somewhere: a trench or embankment; "
                          f"a gentler max_grade, a 'via' point, or accept it")
    s, _ = _arclen(xy)
    T.routes[name] = Line(name, "route", xy, h, s, {"length": length, "max_grade": maxg, "width": width,
                                                   "cut": cut, "fill": fill})


# ---------------------------------------------------------------- cover

def _spec_cover(T, name):
    c = (T.spec.get("cover") or {})[name]
    base = COVER_TYPES.get(c.get("type", name), {})
    return {**base, **c}


def cover_colour(T, name):
    c = _spec_cover(T, name)
    col = c.get("color", [0.5, 0.5, 0.5])
    if isinstance(col, str):
        col = [int(col[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return col


def tree_kind(T, name):
    return _spec_cover(T, name).get("trees")


def cover(T) -> dict:
    out = {}
    slope = T._slope()
    pts = np.c_[T.P, np.zeros(len(T.P))]
    for k, name in enumerate(T.spec.get("cover") or {}):
        c = _spec_cover(T, name)
        m = np.full(T.X.shape, float(c.get("density", 1.0)))
        if "in" in c:
            m *= region(T, c["in"])
        lo, hi = c.get("slope", [0, 90])
        m *= smoothstep(lo - 4, lo + 4, slope) if lo > 0 else 1
        m *= smoothstep(hi + 4, hi - 4, slope) if hi < 90 else 1
        if "elevation" in c:
            lo, hi = c["elevation"]
            fade = c.get("fade", 40)
            m *= smoothstep(lo - fade, lo + fade, T.H) * smoothstep(hi + fade, hi - fade, T.H)
        if "gradient" in c:
            g = c["gradient"]
            a, b = T.address(g["from"])[0], T.address(g["to"])[0]
            ax = b - a
            u = np.clip(((T.P - a) @ ax) / (ax @ ax), 0, 1).reshape(T.X.shape)
            v0, v1 = g.get("range", [0, 1])
            m *= v0 + (v1 - v0) * u
        if "near" in c:
            what, within = c["near"]["what"], c["near"].get("within", 50)
            if what == "water":
                d = ndimage.distance_transform_edt(np.isnan(T.water)) * T.cell
            else:
                xy = T.address(what)[0]
                d = np.hypot(T.X - xy[0], T.Y - xy[1])
            m *= smoothstep(within, within * 0.6, d)
        br = c.get("breakup")
        if br and br.get("amount"):
            n = noise.fbm(pts, br.get("scale", 100), 3, seed=41 + k).reshape(T.X.shape)
            m *= np.clip(1 + br["amount"] * 4 * (n - 0.5), 0, 1)
        for a in c.get("avoid", []):
            if a == "water":
                wet = ~np.isnan(T.water)
                m *= smoothstep(0, 3 * T.cell, ndimage.distance_transform_edt(~wet) * T.cell) if wet.any() else 1
            elif a in ("routes", "sites"):
                if a in T.masks:
                    m *= 1 - T.masks[a]
            else:
                m *= 1 - region(T, a)
        out[name] = np.clip(m, 0, 1)
    return out


# ---------------------------------------------------------------- report and intent

def report(T):
    out = []
    for name, s in T.sites.items():
        wet = ~np.isnan(T.water)
        dw = (np.hypot(T.X - s["xy"][0], T.Y - s["xy"][1])[wet].min() - s["radius"]) if wet.any() else None
        out.append(f"site {name}: pad {2 * s['radius']:.0f} m across at {s['level']:.0f} m, centre "
                   f"[{s['xy'][0]:.0f}, {s['xy'][1]:.0f}]; cut {s['cut']:.0f} m, fill {s['fill']:.0f} m"
                   + (f"; edge {dw:.0f} m from water" if dw is not None else ""))
    for name, R in T.routes.items():
        g = _grades(T, R.xy, h=R.h)  # the road as built (its own graded profile)
        ok = g.max() <= R.props["max_grade"] + 0.01
        turns = _switchbacks(R.xy)
        worst = int(np.argmax(g))
        out.append(f"route {name}: {R.props['length']:.0f} m, climbs {np.abs(np.diff(R.h)).sum():.0f} m, "
                   f"{turns} switchbacks, steepest 20 m {100 * g.max():.0f}% (limit {100 * R.props['max_grade']:.0f}%) "
                   + ("OK" if ok else f"FAIL at [{R.xy[worst, 0]:.0f}, {R.xy[worst, 1]:.0f}]")
                   + f"; cut up to {R.props['cut']:.0f} m, fill {R.props['fill']:.0f} m")
        off = np.abs(T.sample(R.xy) - R.h) > 1.0  # the ground under the road isn't the road: legs crowd each other
        if off.any():
            lab, n = ndimage.label(off)
            spots = sorted(((lab == k).sum(), k) for k in range(1, n + 1))[::-1][:3]
            out.append(f"    ground and road disagree over {off.sum() * R.props['length'] / len(R.xy):.0f} m (switchback legs"
                       f" too close to carve both): " + ", ".join(
                           f"[{R.xy[lab == k][:, 0].mean():.0f}, {R.xy[lab == k][:, 1].mean():.0f}]" for _, k in spots))
    for name, W in T.walls.items():
        out.append(f"wall {name}: {W['length'] / 1000:.1f} km of edge, {100 * W['fraction']:.0f}% at least "
                   f"{W['spec'].get('min_slope', 50)} deg for {W['spec'].get('height', 40)} m "
                   f"(raised up to {W['raised']:.0f} m)")
        for xy, length, steep in W["climbable"][:5]:
            out.append(f"    climbable: {length:.0f} m near [{xy[0]:.0f}, {xy[1]:.0f}] (steepest {steep:.0f} deg)")
    for name, m in T.cover.items():
        line = f"cover {name}: {m.sum() * T.cell ** 2 / 1e4:.0f} ha equivalent ({100 * m.mean():.0f}% of the frame)"
        zs = [z for z in T.zones][:4]
        if zs:
            line += "; " + ", ".join(f"{z} {100 * (m * region(T, z)).sum() / max(region(T, z).sum(), 1):.0f}%" for z in zs)
        out.append(line)
    for a in (T.spec.get("probe") or []):
        xy, h, _ = T.address(a)
        out.append(f"probe {a}: [{xy[0]:.0f}, {xy[1]:.0f}] ground {h:.0f} m, slope {T._slope()[_ij(T, xy)]:.0f} deg")
    return out


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
    """Where to aim at: a peak's summit, a lake's surface, else 2 m above the ground."""
    xy, h, _ = T.address(ref)
    if isinstance(ref, str) and (ref in T.points or ref.startswith("highest")):
        near = np.hypot(T.X - xy[0], T.Y - xy[1]) < 40
        k = np.argmax(np.where(near, T.H, -np.inf))
        return T.P[k], float(T.H.ravel()[k]), 40.0, True

    return xy, h + 2, T.cell * 2, False


def _eye(T, eye_ref, eye_height):
    exy, eh, _ = T.address(eye_ref)
    if isinstance(eye_ref, str) and eye_ref in T.sites:
        eh = T.sites[eye_ref]["level"]
    return exy, eh + eye_height


def lake_seen(T, eye_ref, lake, eye_height=1.7):
    """The share of a lake's surface visible from the eye (sampled water cells, each tested by a sight line)."""
    exy, e = _eye(T, eye_ref, eye_height)
    wet = np.nonzero((T.lake_id == T.lakes[lake]["id"]).ravel())[0]
    if not len(wet):
        return 0.0
    pick = wet[np.linspace(0, len(wet) - 1, min(300, len(wet))).astype(int)]
    seen = 0
    for k in pick:
        txy, top = T.P[k], T.lakes[lake]["level"]
        D = float(np.linalg.norm(txy - exy))
        u = np.linspace(0, 1, max(3, int(D / (T.cell / 2))))[1:-1]
        dd = u * D
        p = exy + (txy - exy) * u[:, None]
        g = np.where(np.isnan(T.water.ravel()[_cells(T, p)]), T.sample(p), -np.inf)  # water doesn't block water
        line = e + (top - e) * u
        seen += not (g > line + 0.05).any()
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
    keep = (dd > 5) & (dd < D - skip)
    p = exy + (txy - exy) * u[keep, None]
    ground = T.sample(p)
    need = e + (ground - e) * D / dd[keep]  # the target height a sight line over each sample needs
    k = int(np.argmax(need)) if len(need) else 0
    need_max = float(need.max()) if len(need) else -np.inf
    res = {"visible": top - need_max, "block": p[k] if len(need) else None, "dist": D}
    if summit:  # on the skyline: nothing beyond it rises above the line of sight to its top
        beyond = exy + (txy - exy) * np.linspace(1.02, 4, 200)[:, None]
        (x0, y0), (x1, y1) = T.spec["extent"]
        inb = (beyond[:, 0] >= x0) & (beyond[:, 0] <= x1) & (beyond[:, 1] >= y0) & (beyond[:, 1] <= y1)
        beyond = beyond[inb]
        if len(beyond):
            db = np.linalg.norm(beyond - exy, axis=1)
            res["skyline"] = bool(((T.sample(beyond) - e) / db).max() <= (top - e) / D)
        else:
            res["skyline"] = True
    return res


def intent(T):
    out = []
    for name, it in (T.spec.get("intent") or {}).items():
        if "above_flood" in it:
            xy, h, _ = T.address(it["at"])
            if isinstance(it["at"], str) and it["at"] in T.sites:
                h = T.sites[it["at"]]["level"]
            rivers = [L for L in T.lines.values() if L.kind == "river"]
            lvls = [(L.name, L.h[cKDTree(L.xy).query(xy)[1]], cKDTree(L.xy).query(xy)[0]) for L in rivers]
            lvls += [(n, lk["level"], np.linalg.norm(np.array(lk["xy"]) - xy)) for n, lk in T.lakes.items()]
            wname, wl, _ = min(lvls, key=lambda x: x[2])
            ok = h - wl >= it["above_flood"]
            out.append(f"intent {name}: {h - wl:.0f} m above {wname} (want >= {it['above_flood']}) {'OK' if ok else 'FAIL'}")
        if "path" in it:
            pts = [T.address(a)[0] for a in it["path"]]
            xy = np.vstack([np.linspace(a, b, max(2, int(np.linalg.norm(b - a) / (T.cell / 2))))
                            for a, b in zip(pts, pts[1:])])
            g = _grades(T, xy, 50)
            d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
            w = int(np.argmax(g))
            ok = g.max() <= it["max_grade"]
            out.append(f"intent {name}: straight legs {d[-1]:.0f} m, steepest 50 m {100 * g.max():.0f}% "
                       f"(want <= {100 * it['max_grade']:.0f}%) "
                       + ("OK" if ok else f"FAIL at [{xy[w, 0]:.0f}, {xy[w, 1]:.0f}], {d[w]:.0f} m along "
                                          f"(a route would wind there: use \"routes\")"))
        if "see" in it:
            for tgt in it["see"]:
                want = it.get("min_visible", 0)
                if isinstance(tgt, str) and tgt in T.lakes:
                    f = lake_seen(T, it["from"], tgt)
                    out.append(f"intent {name}: {tgt}: {100 * f:.0f}% of its surface visible" + ("" if f > 0 else " FAIL"))
                    continue
                r = sight(T, it["from"], tgt)
                if r["visible"] > want:
                    s = f"intent {name}: {tgt} visible, top {r['visible']:.0f} m showing ({r['dist']:.0f} m away)"
                    if "skyline" in r:
                        s += ", on the skyline" if r["skyline"] else ", against higher ground behind"
                    if it.get("skyline") and not r.get("skyline", True):
                        s += " FAIL (wanted on the skyline)"
                    out.append(s)
                else:
                    b = r["block"]
                    out.append(f"intent {name}: {tgt} hidden: needs {want - r['visible']:.0f} m more; the ground at "
                               f"[{b[0]:.0f}, {b[1]:.0f}] blocks it" if b is not None else f"intent {name}: {tgt} hidden")
    return out
