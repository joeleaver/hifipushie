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
from .terrain import Line, _arclen, _area, smoothstep

NAMED_REGIONS = ("everywhere", "centre", "north", "south", "east", "west")

COVER_TYPES = {
    "forest":    {"slope": [0, 40], "avoid": ["water", "routes", "sites"], "breakup": {"scale": 150, "amount": 0.3},
                  "color": [0.12, 0.25, 0.11], "trees": "conifer"},
    "conifer":   {"slope": [0, 42], "avoid": ["water", "routes", "sites"], "breakup": {"scale": 150, "amount": 0.3},
                  "color": [0.10, 0.22, 0.12], "trees": "conifer"},
    "deciduous": {"slope": [0, 36], "avoid": ["water", "routes", "sites"], "breakup": {"scale": 150, "amount": 0.3},
                  "color": [0.24, 0.34, 0.12], "trees": "broadleaf"},
    "rock":      {"slope": [40, 90], "breakup": {"scale": 60, "amount": 0.3}, "color": [0.45, 0.43, 0.40]},
    "scree":     {"slope": [32, 42], "density": 0.7, "breakup": {"scale": 60, "amount": 0.6}, "color": [0.58, 0.54, 0.47]},
    "grass":     {"slope": [0, 42], "avoid": ["water"], "color": [0.45, 0.56, 0.26]},
    "meadow":    {"slope": [0, 25], "avoid": ["water", "routes"], "breakup": {"scale": 80, "amount": 0.3},
                  "color": [0.55, 0.62, 0.30]},
    "snow":      {"slope": [0, 45], "color": [0.94, 0.95, 0.97]},
    "sand":      {"slope": [0, 15], "color": [0.78, 0.71, 0.52]},
    "mud":       {"slope": [0, 10], "color": [0.33, 0.27, 0.19]},
    "orchard":   {"slope": [0, 20], "avoid": ["water", "routes", "sites"], "rows": 6, "color": [0.30, 0.42, 0.16],
                  "trees": "fruit"},
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
        if r == "water":
            return (~np.isnan(T.water)).astype(float)
        if r in ("routes", "sites"):
            return T.masks.get(r, np.zeros(shape))
        if r in T.lakes and hasattr(T, "lake_id"):
            return (T.lake_id == T.lakes[r]["id"]).astype(float)
        if r.startswith("zone:"):
            return region(T, T.zones[r[5:]])
        if r == "everywhere":
            return np.ones(shape)
        if r == "centre":
            return (np.hypot((T.X - mx) / (x1 - x0), (T.Y - my) / (y1 - y0)) < 0.25).astype(float)
        # compass regions have soft edges (a tenth of the frame): a straight hard line reads as a map, not a place
        soft = 0.05 * max(x1 - x0, y1 - y0)
        north, east = smoothstep(my - soft, my + soft, T.Y), smoothstep(mx - soft, mx + soft, T.X)
        if r.startswith("quadrant:"):
            q = r.split(":")[1]
            return (north if "n" in q else 1 - north) * (east if "e" in q else 1 - east)
        half = r.split(":")[1] if r.startswith("half:") else r
        if half in ("north", "n"):
            return north
        if half in ("south", "s"):
            return 1 - north
        if half in ("east", "e"):
            return east
        if half in ("west", "w"):
            return 1 - east
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
        rad = r.get("radius", 200 * T.k)
        meet(smoothstep(rad * 1.1, rad * 0.9, np.hypot(T.X - xy[0], T.Y - xy[1])))
    if "above" in r:
        meet(smoothstep(r["above"] - 15 * T.k, r["above"] + 15 * T.k, T.H))
    if "below" in r:
        meet(smoothstep(r["below"] + 15 * T.k, r["below"] - 15 * T.k, T.H))
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
    for name, p in (T.spec.get("passes") or {}).items():
        _pass(T, name, p)
    for name, b in T.basins.items():  # a basin's wall is its own inner face: only checked, never raised
        spec = (T.spec.get("basins") or {})[name].get("walls", {})
        T.walls[name] = {"inside": b["floor"], "band": b["width"], "raised": 0.0, "basin": True,
                         "spec": {"min_slope": b["min_slope"], "height": spec.get("height", 30),
                                  "except": spec.get("except", []) + list(T.passes), "gap": spec.get("gap", 90 * T.k)}}
    for name, w in (T.spec.get("walls") or {}).items():
        _wall(T, name, w)
    for name, s in (T.spec.get("sites") or {}).items():
        _site(T, name, s)
    for name, r in (T.spec.get("routes") or {}).items():
        _route(T, name, r)


def check(T):
    for name in T.walls:  # checked last: sites, routes and erosion all change the ground
        _check_wall(T, name)


def _gaps(T, w):
    g = np.ones(T.X.shape)
    for a in w.get("except", []):
        if a in T.passes:  # a pass is exempt along its whole corridor
            g = np.minimum(g, 1 - ndimage.binary_dilation(T.passes[a]["corridor"], iterations=2))
            continue
        xy = T.address(a)[0]
        r = w.get("gap", 80 * T.k)
        g = np.minimum(g, smoothstep(r * 0.6, r * 1.4, np.hypot(T.X - xy[0], T.Y - xy[1])))
    return g


def _pass(T, name, p):
    """A notch through a ridge: a way `width` wide, highest (`floor`) on the crest, falling at `max_grade` both ways
    until it daylights (the ground drops below it), flanked by `sides`-degree walls. It notches the crest mass only:
    the descent beyond is the routes' job (they can switchback). A fixed-length ramp ran kilometres across a basin,
    built a causeway, and drowned the lake it crossed."""
    xy = T.address(p["at"])[0]
    ridges = [L for L in T.lines.values() if L.kind == "ridge"] if not p.get("through") else [T.lines[p["through"]]]
    L = min(ridges, key=lambda L: cKDTree(L.xy).query(xy)[0])
    i = int(cKDTree(L.xy).query(xy)[1])
    c = L.xy[i]
    tan = L.xy[min(i + 2, len(L.xy) - 1)] - L.xy[max(i - 2, 0)]
    tan /= np.linalg.norm(tan)
    nrm = np.array([-tan[1], tan[0]])
    maxg = float(p.get("max_grade", 0.15))
    half = float(p.get("width", min(60, 0.03 * T.size))) / 2
    look = float(p.get("length", 600 * T.k + 200))
    us = np.arange(0, 4 * look, T.cell / 2)
    near = [T.height(c + sgn * nrm * min(look / 3, 150 * T.k + 50)) for sgn in (1, -1)]
    floor = float(p.get("floor", max(near) + 2))  # default: just above the higher side, close in
    lens, ends, reach_ok = [], [], []
    for sgn in (1, -1):
        g = T.sample(c + sgn * nrm * us[:, None])
        ramp = floor - maxg * us
        # it ends where it daylights (ground below the way) or leaves the crest (ground no higher than the saddle)
        below = np.nonzero((g <= ramp + 0.5) | (g <= floor + 1.0))[0]
        below = below[us[below] > 2 * T.cell]
        if len(below):
            lens.append(float(us[below[0]]) + 2 * T.cell)
            ends.append(float(us[below[0]]))
            reach_ok.append(True)
        else:  # the ground never drops below a way at this grade within reach: it would need to wind (a route)
            lens.append(float(us[-1]))
            ends.append(float(us[-1]))
            reach_ok.append(False)
    v = np.stack([T.X - c[0], T.Y - c[1]], -1)
    u, w = v @ nrm, v @ tan  # across the ridge, along it
    ln = np.where(u >= 0, lens[0], lens[1])
    ramp = floor - maxg * np.abs(u)
    off = np.clip(np.abs(w) - half, 0, None)
    cut = ramp + off * math.tan(math.radians(p.get("sides", 60)))  # the flanks above the way
    fill = np.minimum(ramp - off * math.tan(math.radians(35)), T.H + float(p.get("fill_max", 3.0)))  # small hollows only
    reach = smoothstep(ln + 3 * T.cell, ln, np.abs(u))
    T.H = np.where(reach > 0, T.H * (1 - reach) + np.clip(T.H, np.minimum(fill, cut), cut) * reach, T.H)
    corridor = (reach > 0) & (np.abs(w) < half + 3 * T.cell)
    for sgn, ok, n in zip((1, -1), reach_ok, lens):
        if not ok:
            T.warnings.append(f"pass {name!r}: on its {'left' if sgn > 0 else 'right'} side the ground doesn't fall "
                              f"below a {100 * maxg:.0f}% way within {n:.0f} m: that side needs a winding route "
                              f"(\"routes\" from the pass), not a straight ramp")
    T.passes[name] = {"xy": c.tolist(), "floor": floor, "ridge": L.name, "width": 2 * half, "grades": [maxg, maxg],
                      "lengths": [min(n, us[-1]) for n in lens], "ends": ends, "corridor": corridor,
                      "axis": nrm.tolist(), "max_grade": maxg}


def rugged(T):
    """Ruggedness as geometry, not paint: crags (ridged noise) and ledges (the ground stepped into benches and risers)
    in patches, scaled by `amount` over a zone, optionally ramped by a gradient. Rock cover then finds the steep bits."""
    pts = np.c_[T.P, np.zeros(len(T.P))]
    for k, (name, g) in enumerate((T.spec.get("rugged") or {}).items()):
        R = np.full(T.X.shape, float(g.get("amount", 0.6)))
        if "in" in g:
            R *= region(T, g["in"])
        if "gradient" in g:
            gr = g["gradient"]
            a, b = T.address(gr["from"])[0], T.address(gr["to"])[0]
            ax = b - a
            u = np.clip(((T.P - a) @ ax) / (ax @ ax), 0, 1).reshape(T.X.shape)
            v0, v1 = gr.get("range", [0, 1])
            R *= v0 + (v1 - v0) * u
        sc = float(g.get("scale", T.world["crag"] if T.world["kind"] else 80 * T.k))  # player-scale crags
        crag = 1 - np.abs(2 * noise.fbm(pts, sc, 3, seed=61 + k) - 1)
        fine = noise.fbm(pts, sc / 3, 2, seed=62 + k)
        T.H += R * (0.25 * sc * (crag.reshape(T.X.shape) - 0.5) + 0.06 * sc * (fine.reshape(T.X.shape) - 0.5))
        step = float(g.get("ledges", 0.15 * sc))
        if step > 0:
            f = T.H / step
            stepped = (np.floor(f) + smoothstep(0.65, 1.0, f - np.floor(f))) * step  # flat benches, steep risers
            patch = smoothstep(0.45, 0.6, noise.fbm(pts, 2.5 * sc, 2, seed=63 + k).reshape(T.X.shape))
            patch *= smoothstep(40, 25, T._slope())  # on walls, stepped risers stacked into organ pipes
            T.H += R * patch * (stepped - T.H)


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
    rim = isinstance(ref, str) and "_rim" in ref.split("@")[0]
    if rim:  # d points into the canyon: back from the lip, on the plateau, looking in
        xy = xy - d * (r + s.get("setback", 3))
        s = {**s, "level": s.get("level", T.height(xy + -d * r))}
    dist = np.hypot(T.X - xy[0], T.Y - xy[1])
    inside = dist <= r
    shore = isinstance(ref, str) and ref.endswith("_shore")
    wet = ~np.isnan(T.water) & (dist < r + 200 * T.k)
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
    if rim:  # a lookout on a rim: cut to the plateau, never fill out over the lip (the fill mound hid the view)
        w = np.where(T.H >= level, w, 0)
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


def _path(T, H, cell, a, b, maxg, blocked, reach_only=False, penalty=None):
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
        if penalty is not None:
            wt = wt + penalty.ravel()[B]
        for p, q in ((A, B), (B, A)):
            rows.append(p[ok]); cols.append(q[ok]); wts.append(wt[ok])
    G = coo_matrix((np.concatenate(wts), (np.concatenate(rows), np.concatenate(cols))), shape=(ny * nx, ny * nx)).tocsr()
    dist, pred = dijkstra(G, indices=idx[a], return_predecessors=True)
    if reach_only:
        return (np.isfinite(dist).reshape(ny, nx), b) if not np.isfinite(dist[idx[b]]) else None
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
    lakes = getattr(T, "lake_id", np.zeros(T.X.shape, int)) > 0
    blocked = lakes[::f, ::f].copy()
    river = getattr(T, "river_water", np.zeros(T.X.shape, bool)) & ~getattr(T, "ford_mask", np.zeros(T.X.shape, bool))
    penalty = ndimage.binary_dilation(river, iterations=f)[::f, ::f] * 40.0 * cell  # wading/bridging costs: use fords
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
        strict = _path(T, H, cell, ga, gb, maxg * 0.95, blocked, reach_only=True, penalty=penalty)  # how far the asked grade gets
        for relax in (1.0, 1.4, 2.0, 3.0):
            bl = blocked.copy()
            bl[ga] = bl[gb] = False
            path = _path(T, H, cell, ga, gb, maxg * relax * 0.95, bl, penalty=penalty)
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
        msg = (f"route {name!r}: nothing within {100 * maxg:.0f}% connects its stops; searched at "
               f"{100 * maxg * relaxed:.0f}% (the carve then eases what it can)")
        if strict is not None:  # say where the asked grade runs out and what's in the way
            reach, (gy, gx) = strict
            yy, xx = np.nonzero(reach)
            end = np.array([T.xs[0] + gx * cell, T.ys[0] + gy * cell])
            k = int(np.argmin(np.hypot(T.xs[0] + xx * cell - end[0], T.ys[0] + yy * cell - end[1])))
            near = np.array([T.xs[0] + xx[k] * cell, T.ys[0] + yy[k] * cell])
            dz = T.height(end) - T.height(near)
            dd = max(float(np.linalg.norm(end - near)), 1.0)
            msg += (f". At {100 * maxg:.0f}% it gets as far as [{near[0]:.0f}, {near[1]:.0f}], {dd:.0f} m short; from "
                    f"there the ground {'rises' if dz > 0 else 'falls'} {abs(dz):.0f} m to the stop ({100 * abs(dz) / dd:.0f}% "
                    f"straight): lower/raise the stop, add a 'via' where it can wind, or allow a steeper grade")
        T.warnings.append(msg)
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
        if "sites" in T.masks:  # a road arrives at a site; it doesn't bury or trench it
            w *= 1 - T.masks["sites"]
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
    straight = sum(float(np.linalg.norm(T.address(b)[0] - T.address(a)[0])) for a, b in zip(stops[:-1], stops[1:]))
    climb = abs(float(h[-1] - h[0]))
    need = max(straight, climb / maxg)  # winding down a 700 m wall at 15% needs 4.7 km: that's not a detour
    if length > 2 * max(need, 1.0):
        T.warnings.append(f"route {name!r} is {length:.0f} m where {need:.0f} m would do (the crow flies {straight:.0f} m, "
                          f"the climb needs {climb / maxg:.0f} m at its grade): it's detouring round something; check "
                          f"the map for what, or add a 'via'")
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
        if c.get("rows"):  # an orchard or plantation: trees in rows `rows` metres apart, along contours or an axis
            along = c.get("along", "contour")
            if along == "contour":
                u = T.H / max(float(np.mean(np.hypot(*np.gradient(T.H, T.cell)))) + 1e-3, 1e-3)  # ~distance across the slope
            else:
                ang = math.radians({"east": 90, "west": 90, "north": 0, "south": 0}.get(along, float(along) if
                                   isinstance(along, (int, float)) else 0))
                u = T.X * math.cos(ang) - T.Y * math.sin(ang)
            m *= smoothstep(0.55, 0.85, 0.5 + 0.5 * np.cos(2 * np.pi * u / float(c["rows"])))
        br = c.get("breakup")
        if br and br.get("amount"):
            user = ((T.spec.get("cover") or {})[name].get("breakup") or {}).get("scale")
            sc = user if user else br.get("scale", 100) * T.k  # the type defaults are landscape-scale
            n = noise.fbm(pts, sc, 3, seed=41 + k).reshape(T.X.shape)
            m *= np.clip(1 + br["amount"] * 4 * (n - 0.5), 0, 1)
        if not c.get("under_water") and "water" not in c.get("avoid", []):
            m *= np.isnan(T.water)  # nothing grows under water unless asked ("under_water": true)
        for a in c.get("avoid", []):
            if a == "water":
                wet = ~np.isnan(T.water)
                m *= smoothstep(0, 3 * T.cell, ndimage.distance_transform_edt(~wet) * T.cell) if wet.any() else 1
            elif a in ("routes", "sites"):
                if a in T.masks:
                    m *= 1 - T.masks[a]
            else:
                m *= 1 - region(T, a)
        m = np.clip(m, 0, 1)
        if c.get("count") and c.get("trees"):  # "a few trees": scale the density so about this many stand
            expect = m.sum() * T.cell ** 2 * TREES_PER_M2
            if expect > 0:
                m = np.clip(m * c["count"] / expect, 0, 1)
        out[name] = m
    return out


TREES_PER_M2 = 0.02  # the preview's (and a reasonable engine's) density at mask 1: one tree per 50 m2


def trees(T, limit=250_000):
    """Tree instances (x, y, z, kind, layer) for every tree layer: a jittered grid a tree apart, each point kept with
    the mask's probability; an orchard's points sit on its rows (so rows read as rows, in the preview and the engine)."""
    rng = np.random.default_rng(11)
    out = []
    (x0, y0), (x1, y1) = T.spec["extent"]
    for li, (name, m) in enumerate(T.cover.items()):
        c = _spec_cover(T, name)
        kind = c.get("trees")
        if not kind or m.max() <= 0:
            continue
        if c.get("rows"):
            step = float(c.get("spacing", c["rows"]))
            gx, gy = np.meshgrid(np.arange(x0, x1, step / 2), np.arange(y0, y1, step / 2))
            pts = np.stack([gx.ravel(), gy.ravel()], 1) + rng.normal(0, 0.15, (gx.size, 2))
            keep = T.sample(pts, m) > 0.75  # on the rows' centres only
        else:
            step = 1 / math.sqrt(TREES_PER_M2)
            gx, gy = np.meshgrid(np.arange(x0, x1, step), np.arange(y0, y1, step))
            pts = np.stack([gx.ravel(), gy.ravel()], 1) + rng.uniform(-0.45, 0.45, (gx.size, 2)) * step
            keep = rng.random(len(pts)) < T.sample(pts, m)
        pts = pts[keep]
        out.append(np.c_[pts, T.sample(pts), np.full(len(pts), li)])
        T.tree_layers = getattr(T, "tree_layers", {}) | {li: (name, kind)}
    if not out:
        return np.zeros((0, 4))
    allp = np.vstack(out)
    if len(allp) > limit:
        allp = allp[rng.choice(len(allp), limit, replace=False)]
    return allp


# ---------------------------------------------------------------- report and intent

# what real landscapes look like, for the realism check: share of ground steeper than 30 / 45 / 60 deg in rugged
# mountain terrain (alpine DEMs), and the slope real mountainsides average
REAL = {"over_30": 0.35, "over_45": 0.12, "over_60": 0.03, "face": (25, 40)}


def realism(T):
    """Slope statistics against real terrain, and whether each basin's relief fits its ring at a realistic slope."""
    land = np.isnan(T.water)
    sl = T._slope()[land]
    f30, f45, f60 = (sl > 30).mean(), (sl > 45).mean(), (sl > 60).mean()
    W = T.world
    real45 = W["steep"] if W["kind"] else REAL["over_45"]
    what = f"a real {W['kind'].replace('_', ' ')}" if W["kind"] else "rugged real mountains"
    out = [f"realism: median slope {np.median(sl):.0f} deg; {100 * f30:.0f}% of the ground over 30 deg, "
           f"{100 * f45:.0f}% over 45, {100 * f60:.0f}% over 60 ({what}: about {100 * real45:.0f}% over 45)"]
    for name, b in T.basins.items():
        inner = T._slope()[b["inside"] & land]
        out.append(f"realism: inside basin {name}: {100 * (inner > 45).mean():.0f}% over 45 deg, "
                   f"{100 * (inner > 60).mean():.0f}% over 60")
    edge = np.zeros(T.X.shape, bool)
    edge[:, :3] = edge[:, -3:] = True
    edge[:3, :] = edge[-3:, :] = True
    ring = ndimage.binary_dilation(edge, iterations=max(3, int(0.08 * T.size / T.cell)))
    if (T._slope()[ring & land] > 45).mean() > 0.3 and isinstance(T.spec.get("border"), (int, float, dict)):
        T.warnings.append("the frame's edge is fixed low close to high ground, so the ground falls off it in cliffs "
                          "(a moat around the level); open the edge (\"border\": \"open\") or fix it higher")
    if not W["kind"] and f30 < 0.2:  # gentle country: the mountain comparison doesn't apply
        out[0] = f"realism: median slope {np.median(sl):.0f} deg; {100 * f30:.0f}% of the ground over 30 deg (gentle country)"
    elif f45 > 2 * real45 + 0.02:
        T.warnings.append(f"steeper than {what}: {100 * f45:.0f}% of the ground is over 45 deg (~{100 * real45:.0f}% in "
                          f"reality); faces steep all the way down read as draped curtains. Lower the relief, widen the "
                          f"frame, or give walls cliff bands rather than steepness everywhere")
    if W["kind"]:
        mean_face = float(np.mean(sl[sl > 5])) if (sl > 5).any() else 0.0
        lo_f, hi_f = __import__("hifipushie.terrain_world", fromlist=["K"]).KINDS[W["kind"]]["face"][1:]
        if W["kind"] and not lo_f * 0.5 <= mean_face <= hi_f * 1.25:
            T.warnings.append(f"slopes average {mean_face:.0f} deg where there's any slope; a {W['kind'].replace('_', ' ')} "
                              f"is more like {lo_f:.0f}-{hi_f:.0f}: check the relief against the frame")
    for name, b in T.basins.items():
        need = b["relief"] / math.tan(math.radians(b["avg"]))
        across = 2 * math.sqrt(b["inside"].sum() / math.pi) * T.cell  # the ring's rough diameter
        floor_share = b["floor"].sum() / max(b["inside"].sum(), 1)
        out.append(f"realism: basin {name}: {b['relief']:.0f} m from floor edge to lowest crest at {b['avg']:.0f} deg "
                   f"needs {need:.0f} m of mountainside; the ring is ~{across:.0f} m across, leaving "
                   f"{100 * floor_share:.0f}% of it as floor")
        if floor_share < 0.6 * T.world["floor"]:  # (alpine valleys really are ~25% floor)
            T.warnings.append(f"basin {name!r}: its walls leave only {100 * floor_share:.0f}% of the ring as floor. The "
                              f"relief ({b['relief']:.0f} m) is big for a ring ~{across:.0f} m across: lower the crest, "
                              f"widen the ring/frame, or make the walls steeper rock (\"walls\": {{\"average\": 45}}: "
                              f"granite-like; real alpine faces average 25-40 deg)")
    return out


def report(T):
    out = realism(T)
    for name, b in T.basins.items():
        on_wall = [n for n, lk in T.lakes.items() if b["wall"][_ij(T, np.array(lk["xy"]))]]
        on_wall += [n for n, st in T.sites.items() if b["wall"][_ij(T, np.array(st["xy"]))]]
        if on_wall:
            T.warnings.append(f"{', '.join(on_wall)} stand(s) on basin {name!r}'s wall, not its floor: its walls take "
                              f"{b['width']:.0f} m (a {b['avg']:.0f} deg mountainside), so the floor is smaller than the ring")
        fl = T.H[b["floor"]]
        out.append(f"basin {name}: floor {b['floor'].sum() * T.cell ** 2 / 1e6:.2f} km2 from {fl.min():.0f} to "
                   f"{np.percentile(fl, 98):.0f} m, drains to [{b['falls'][0]:.0f}, {b['falls'][1]:.0f}]; "
                   f"walls {b['width']:.0f} m wide, averaging {b['avg']:.0f} deg with a {b['band']:.0f} m cliff band")
    for name, c in getattr(T, "canyons", {}).items():
        out.append(f"canyon {name}: {c['depth']:.0f} m deep at its deepest, {2 * c['half']:.0f} m rim to rim, floor "
                   f"{c['floor']:.0f} m; walls in horizontal strata: cliffs over ledges at {c['ledge']:.0f} deg, talus at the foot")
    for name, m in getattr(T, "mesas", {}).items():
        out.append(f"mesa {name}: top {m['top']:.0f} m, {2 * m['radius']:.0f} m across")
    for name, p in T.passes.items():
        c, ax = np.array(p["xy"]), np.array(p["axis"])
        sides = []
        worst = None
        for sgn, n, side in ((1, p["ends"][0], "left"), (-1, p["ends"][1], "right")):  # measured as built
            xy = c + sgn * ax * np.arange(0, max(n, 2 * T.cell), T.cell / 2)[:, None]  # the way itself, to its end
            g = _grades(T, xy, window=min(20.0, max(n, T.cell)))
            k = int(np.argmax(g))
            beyond = c + sgn * ax * np.arange(n, n + 60 * T.k + 40, T.cell / 2)[:, None]
            gb = _grades(T, beyond).max() if len(beyond) > 4 else 0
            sides.append(f"{side} {n:.0f} m at up to {100 * g.max():.0f}%, then the ground runs on at "
                         f"{100 * gb:.0f}%" + (" (a route continues)" if gb > p["max_grade"] else ""))
            if g.max() > p["max_grade"] * 1.1 and (worst is None or g.max() > worst[0]):
                worst = (g.max(), xy[k])
        line = (f"pass {name}: through {p['ridge']} at [{c[0]:.0f}, {c[1]:.0f}], saddle at {T.height(c):.0f} m, "
                f"{p['width']:.0f} m wide; the way: " + "; ".join(sides))
        if worst:
            line += f" FAIL: {100 * worst[0]:.0f}% at [{worst[1][0]:.0f}, {worst[1][1]:.0f}]"
        out.append(line)
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
        rw = getattr(T, "river_water", None)
        if rw is not None and rw.any():
            wet = rw.ravel()[_cells(T, R.xy)] & ~T.ford_mask.ravel()[_cells(T, R.xy)]
            atford = T.ford_mask.ravel()[_cells(T, R.xy)]
            if atford.any():
                out.append(f"    crosses at a ford: " + ", ".join(n for n, fd in T.fords.items()
                                                                   if np.hypot(*(R.xy - fd["xy"]).T).min() < fd["width"] * 1.5))
            if wet.any():
                lab, n = ndimage.label(wet)
                spots = [R.xy[lab == k].mean(0) for k in range(1, n + 1)]
                out.append(f"    crosses river water at " + ", ".join(f"[{x:.0f}, {y:.0f}]" for x, y in spots)
                           + ": needs a bridge (or add a ford there)")
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
        line = f"cover {name}: {_area(m.sum() * T.cell ** 2)} equivalent ({100 * m.mean():.0f}% of the frame)"
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
        rad = max(40 * T.k, 1.5 * T.cell)
        own = ((T.spec.get("peaks") or {}).get(ref) or {}).get("radius", 0.02 * T.size)
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
        own = dd[near] >= D - zone
        sil = max(ang[own].max() if own.any() else -np.inf, (top - e) / D)
        front = ang[~own].max() if (~own).any() else -np.inf
        k = int(np.argmax(np.where(~own, ang, -np.inf))) if (~own).any() else 0
        res = {"visible": (sil - front) * D, "block": p[k] if (~own).any() else None, "dist": D}
        top = e + sil * D
    else:
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
            lvls = []
            for L in (L for L in T.lines.values() if L.kind == "river"):
                dry = np.isnan(T.water.ravel()[_cells(T, L.xy)])  # a river's reach under a lake is the lake
                if dry.any():
                    q = cKDTree(L.xy[dry]).query(xy)
                    lvls.append((L.name, L.h[dry][q[1]], q[0]))
            for n, lk in T.lakes.items():
                wet = T.lake_id == lk["id"]
                if wet.any():
                    lvls.append((n, lk["level"], np.hypot(T.X[wet] - xy[0], T.Y[wet] - xy[1]).min()))
            if not lvls:
                out.append(f"intent {name}: no water to be above")
                continue
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
            eye = float(it.get("eye", 1.7))
            src = it["from"]
            spots = None
            if isinstance(src, str) and src in T.sites:  # a place, not a point: try the eye across it
                st = T.sites[src]
                c = np.array(st["xy"])
                spots = [("centre", c)] + [(_compass(a), c + 0.7 * st["radius"] * np.array([math.sin(a), math.cos(a)]))
                                           for a in np.radians(np.arange(0, 360, 45))]
            for tgt in it["see"]:
                want = it.get("min_visible", 0)
                if spots:
                    got = []
                    for label, xy in spots:
                        if isinstance(tgt, str) and tgt in T.lakes:
                            v = lake_seen(T, xy.tolist(), tgt, eye)
                            got.append((label, v, v > 0))
                        else:
                            v = sight(T, xy.tolist(), tgt, eye)["visible"]
                            got.append((label, v, v > want))
                    ok = [g for g in got if g[2]]
                    lake = isinstance(tgt, str) and tgt in T.lakes
                    summit = isinstance(tgt, str) and (tgt in T.points or tgt.startswith("highest"))
                    unit = "%" if lake else " m showing"
                    fmt = ((lambda v: f"{100 * v:.0f}%") if lake else (lambda v: f"{v:.0f} m showing") if summit else
                           (lambda v: f"clear by {v:.0f} m" if v > 0 else f"blocked, {-v:.0f} m short"))
                    best = max(got, key=lambda g: g[1])
                    line = (f"intent {name}: {tgt} from {src}: seen from {len(ok)} of {len(got)} spots across it "
                            f"(centre {fmt(got[0][1])}, best {best[0]} {fmt(best[1])}; eye {eye:g} m)" + ("" if ok else " FAIL"))
                    if it.get("skyline") and unit != "%":
                        sk = sight(T, spots[0][1].tolist(), tgt, eye).get("skyline")
                        line += "; on the skyline" if sk else "; NOT on the skyline (higher ground behind it) FAIL"
                    out.append(line)
                    continue
                if isinstance(tgt, str) and tgt in T.lakes:
                    f = lake_seen(T, src, tgt, eye)
                    out.append(f"intent {name}: {tgt}: {100 * f:.0f}% of its surface visible" + ("" if f > 0 else " FAIL"))
                    continue
                r = sight(T, src, tgt, eye)
                if r["visible"] > want:
                    s = (f"intent {name}: {tgt} visible, {r['visible']:.0f} m of it showing above what's in front "
                         f"({r['dist']:.0f} m away)") if "skyline" in r else (
                        f"intent {name}: {tgt} visible (the sight line clears the ground by {r['visible']:.0f} m; "
                        f"{r['dist']:.0f} m away)")
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
