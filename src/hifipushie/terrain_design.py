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
        if r in ("sea", "beach", "cliffs", "coast") and getattr(T, "sea", None):
            from .terrain_sea import regions
            return regions(T, r)
        if r in ("routes", "sites"):
            return T.masks.get(r, np.zeros(shape))
        if r == "cliff_foot":  # below every steep face: where talus and fallen blocks lie (scree cover)
            return getattr(T, "rock", {}).get("foot", np.zeros(shape, bool)).astype(float)
        if r in getattr(T, "vzones", {}):  # a volcano's crater, flows ("lava"), collapse scars, "debris"
            return T.vzones[r].astype(float)
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
        rad = r.get("radius", 200 * T.k)
        ln = T.lines.get(r["near"]) or T.routes.get(r["near"]) if isinstance(r["near"], str) else None
        lk = T.lakes.get(r["near"]) if isinstance(r["near"], str) else None
        wet = (T.lake_id == lk["id"]) if lk is not None and hasattr(T, "lake_id") else None
        if ln is not None:  # near a ridge, river or route: along its whole length
            dist = cKDTree(ln.xy).query(T.P)[0].reshape(T.X.shape)
        elif wet is not None and wet.any():  # near a lake or the sea: its water's edge (a point far out at sea found
            dist = ndimage.distance_transform_edt(~wet) * T.cell  # nothing on land)
        else:
            xy = T.address(r["near"])[0]
            dist = np.hypot(T.X - xy[0], T.Y - xy[1])
        meet(smoothstep(rad * 1.1, rad * 0.9, dist))
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
    # sites in dependency order: one that overlooks or falls toward another is built after it (key order mattered)
    todo = dict(T.spec.get("sites") or {})
    while todo:
        ready = [n for n, s in todo.items()
                 if not any(isinstance(s.get(k), str) and s.get(k) in todo and s.get(k) != n
                            for k in ("at", "overlooks", "toward"))]
        for n in ready or list(todo)[:1]:  # (a cycle: build in the given order)
            _site(T, n, todo.pop(n))
    for st in T.sites.values():  # props face an address (a basket its tee): compass bearing, 0 north, 90 east
        pr = st.get("prop")
        if pr and pr.get("facing"):
            f = T.address(pr.pop("facing"))[0] - np.array(st["xy"])
            pr["yaw"] = round(float(np.degrees(np.arctan2(f[0], f[1]))) % 360, 1)
        elif pr:
            pr.pop("facing", None)
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
        # erosion smoothed crags of a few metres away entirely ("rugged made no visible difference at any setting"):
        # the settle step after erosion keeps them, and the report measures them
        T.settle_mask = np.maximum(getattr(T, "settle_mask", np.zeros(T.X.shape)), (R > 0.05) * 1.0)
        T.rugged_zones = getattr(T, "rugged_zones", {}) | {name: (R > 0.1, sc)}


def _wall(T, name, w):
    """Just outside the zone the ground must rise at least min_slope for `height` metres; raised where it doesn't."""
    inside = region(T, w["around"]) > 0.5
    if not inside.any():
        raise ValueError(f"wall {name!r}: its zone is empty")
    s, (iy, ix) = ndimage.distance_transform_edt(~inside, return_indices=True)
    s *= T.cell
    edge = ndimage.gaussian_filter(T.H, 2)[iy, ix]  # the height at the zone's edge nearest each outside cell
    tan = math.tan(math.radians(min(w.get("min_slope", 50) + 5, 80)))  # a margin: smoothing and texture soften it
    height = float(w.get("height", 40))
    # the ground is triangles between grid points: the wall's lip and foot round off over about a cell, so it is built
    # taller by that much (a 25 m wall two cells wide measured only 15 m of it at 55 deg)
    built = height + 0.6 * T.cell * tan
    band = built / tan
    need = edge + np.minimum(s * tan, built)
    fade = smoothstep(band + 3 * T.cell + height, band + 3 * T.cell, s) * (s > 0)
    raise_by = np.clip(need - T.H, 0, None) * fade * _gaps(T, w)
    T.H = T.H + raise_by
    # the face is rock: erosion's slumping had knocked a 25 m, 55 deg wall down to 15 m of it
    face = (s > 0) & (s <= band + 2 * T.cell) & (_gaps(T, w) > 0.5)
    T.hard |= face
    T.hardness = np.where(face, np.minimum(T.hardness, 0.2), T.hardness)
    T.walls[name] = {"inside": inside, "band": band, "raised": float(raise_by.max()), "spec": w}


def _check_wall(T, name):
    """For each boundary point: the steepest ground just outside it. Below min_slope = climbable there."""
    W = T.walls[name]
    w, inside = W["spec"], W["inside"]
    boundary = inside & ~ndimage.binary_erosion(inside)
    boundary[[0, -1], :] = boundary[:, [0, -1]] = False
    gap = _gaps(T, w) < 0.5
    # along the outward ray from each boundary point: the tallest stretch at least min_slope steep must rise `height`
    # (checking only the steepest slope anywhere outside counted a 2 m step as unclimbable)
    tall, steepest = _steep_runs(T, inside, boundary, w.get("min_slope", 50), W["band"] + 3 * T.cell)
    ok = tall >= 0.8 * float(w.get("height", 40))
    W["tall"] = tall
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
                                   float(steepest[yy, xx].max()), float(np.median(tall[yy, xx]))))
    W["climbable"].sort(key=lambda c: -c[1])
    W["length"] = boundary.sum() * T.cell
    W["fraction"] = 1 - bad.sum() / max(boundary.sum(), 1)


def _steep_runs(T, inside, boundary, min_slope, reach):
    """For each boundary cell: the height gained by the tallest continuous stretch at least min_slope steep along the
    ray out of the zone (uphill away from it) within `reach` metres."""
    sd = ndimage.distance_transform_edt(~inside) - ndimage.distance_transform_edt(inside)
    sd = ndimage.gaussian_filter(sd, 2.0)
    gy, gx = np.gradient(sd)
    by, bx = np.nonzero(boundary)
    nrm = np.stack([gx[by, bx], gy[by, bx]], 1)
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-9
    step = T.cell / 2
    ds = np.arange(0, reach + step, step)
    p0 = np.stack([T.xs[bx], T.ys[by]], 1)
    pts = p0[:, None, :] + nrm[:, None, :] * ds[None, :, None]
    h = T.sample(pts.reshape(-1, 2)).reshape(len(p0), len(ds))
    rise = np.diff(h, axis=1)
    steep = rise >= step * math.tan(math.radians(min_slope - 2))  # (2 deg slack: the ray crosses cells obliquely)
    best = np.zeros(len(p0))
    run = np.zeros(len(p0))
    for k in range(rise.shape[1]):
        run = np.where(steep[:, k], run + rise[:, k], 0)
        best = np.maximum(best, run)
    out, top = np.zeros(inside.shape), np.zeros(inside.shape)
    out[by, bx] = best
    g = ndimage.uniform_filter1d(rise, 3, axis=1) / step  # the steepest along the ray, over ~1.5 cells
    top[by, bx] = np.degrees(np.arctan(g.max(axis=1))) if g.shape[1] else 0
    return out, top


def _site(T, name, s):
    """A flat pad. An address on a lake shore puts the pad inland of that point, clear of the water."""
    ref = s["at"]
    xy, _, d = T.address(ref)
    r = float(s.get("radius", 60))
    shore_lake = None
    sea = getattr(T, "sea", None)
    if isinstance(ref, str) and sea and ref in sea["coves"]:  # in a cove: at its head, just inland of its beach
        cv = sea["coves"][ref]
        xy = np.array(cv["head"]) + np.array(cv["inland"]) * (r + s.get("setback", 5))
        shore_lake, d = "sea", np.array(cv["inland"])
    elif isinstance(ref, str) and ref.endswith("_shore"):
        shore_lake = ref.rsplit(".", 1)[0]
        xy = _shore_pad(T, name, shore_lake, xy, d, r + s.get("setback", 5), r + max(20.0, 0.5 * r))
    rim = isinstance(ref, str) and "_rim" in ref.split("@")[0]
    if rim:  # d points into the canyon: back from the lip, on the plateau, looking in ("lip": its edge at the lip)
        xy = xy - d * ((0.35 * r if s.get("lip") else r) + s.get("setback", 0 if s.get("lip") else 3))
        s = {**s, "level": s.get("level", T.height(xy + -d * r))}
    dist = np.hypot(T.X - xy[0], T.Y - xy[1])
    inside = dist <= r
    # the water that could reach the pad: what's beside it, not a river's level 200 m upstream (that put a lakeside
    # village 198 m up on a mound)
    wet = ~np.isnan(T.water) & (dist < r + max(20.0, 0.5 * r))
    if "level" in s:
        level = float(s["level"])
    elif shore_lake is not None:  # a lakeside pad: just above its lake, cut into the bank behind
        level = T.lakes[shore_lake]["level"] + s.get("above_water", 3.0)
    else:
        level = float(np.median(T.H[inside]))
    if wet.any():  # above the water nearest the pad (a steep river beside it is higher upstream, lower downstream)
        k = np.argmin(np.where(wet, dist, np.inf))
        level = max(level, float(T.water.ravel()[k]) + s.get("above_water", 2.0))
    river = getattr(T, "river_water", np.zeros(T.X.shape, bool)) & inside
    if isinstance(ref, str) and ref.rsplit(".", 1)[-1] in ("source", "mouth"):  # a spring or a river's end: on purpose
        river[:] = False
    if river.any():
        T.warnings.append(f"site {name!r}: a river runs through the pad (at [{T.X[river].mean():.0f}, "
                          f"{T.Y[river].mean():.0f}]): move it, or it will be built over the water")
    shoulder = s.get("shoulder", max(20.0, 0.5 * r))
    # banks sized to how far the ground is from the pad (35 deg), at least `shoulder`
    bank = np.clip(np.abs(T.H - level) / math.tan(math.radians(35)), shoulder, shoulder + r)  # capped: beyond, a cliff
    w = smoothstep(r + bank, r, dist)
    before = T.H.copy()
    if rim:  # a lookout on a rim: cut to the plateau, never fill out over the lip (the fill mound hid the view)
        w = np.where(T.H >= level, w, 0)

    def surface(fall, dvec):  # a pad that falls gently toward dvec (real yards drain; a dead-level one blinds its middle)
        return level - fall * ((T.X - xy[0]) * dvec[0] + (T.Y - xy[1]) * dvec[1])

    fall, dvec, note = float(s.get("fall", 0.0)), np.array([0.0, 0.0]), ""
    if s.get("toward"):
        tw = s["toward"]
        dvec = {"north": (0, 1), "south": (0, -1), "east": (1, 0), "west": (-1, 0)}.get(tw) if isinstance(tw, str) else None
        dvec = np.array(dvec, float) if dvec is not None else T.address(tw)[0] - xy
        dvec = dvec / (np.linalg.norm(dvec) + 1e-12)
        fall = fall or 0.02
    if s.get("overlooks"):  # choose the gentlest fall toward the target that lets most of the pad see it
        tgt = s["overlooks"]
        dvec = T.address(tgt)[0] - xy
        dvec = dvec / (np.linalg.norm(dvec) + 1e-12)
        spots = [xy] + [xy + 0.7 * r * np.array([math.sin(a), math.cos(a)]) for a in np.radians(np.arange(0, 360, 45))]
        best = None
        keep_h = T.H
        asked = float(s.get("fall", 0.0))  # a fall the designer gave is the least it gets
        for f in [asked] + [f for f in (0.02, 0.04, 0.06, 0.08, 0.1) if f > asked]:
            T.H = keep_h * (1 - w) + surface(f, dvec) * w
            named = isinstance(tgt, str)  # (an [x, y] target is neither a cove nor a lake: it crashed the lookup)
            cove = named and getattr(T, "sea", None) and tgt in T.sea["coves"]
            seen = sum((lake_seen(T, p_.tolist(), "sea", mask=T.sea["coves"][tgt]["mask"]) > 0) if cove else
                       (lake_seen(T, p_.tolist(), tgt) > 0) if named and tgt in T.lakes else
                       (sight(T, p_.tolist(), tgt)["visible"] > 0) for p_ in spots)
            if best is None or seen > best[1]:
                best = (f, seen)
            if seen >= 6:
                break
        T.H = keep_h
        fall = best[0]
        note = f"; falls {100 * fall:.0f}% toward {tgt} so {best[1]} of 9 spots across it see it" + (
            f" (asked {100 * asked:.0f}%)" if abs(fall - asked) > 1e-6 and asked else "")
        if best[1] < 6:
            T.warnings.append(f"site {name!r} overlooks {tgt!r} from only {best[1]} of 9 spots even falling "
                              f"{100 * fall:.0f}%: raise it, move it nearer the edge, or move the target")
    if fall and not note:
        note = f"; falls {100 * fall:.0f}% toward " + (s["toward"] if isinstance(s.get("toward"), str) else "its low side")
    T.H = T.H * (1 - w) + surface(fall, dvec) * w
    _earthworks(T, w)
    T.sites[name] = {"xy": xy.tolist(), "level": level, "radius": r, "cut": float((before - T.H).max()),
                     "fill": float((T.H - before).max()), "note": note, "fall": fall, "toward": dvec.tolist()}
    if s.get("prop"):  # a prop the engine drops here (a basket, a bench): its name; which way it faces is resolved
        T.sites[name]["prop"] = {"name": s["prop"], "yaw": 0.0, "facing": s.get("facing")}  # once every site stands
    if max(T.sites[name]["cut"], T.sites[name]["fill"]) > 25:
        T.warnings.append(f"site {name!r} is dug {T.sites[name]['cut']:.0f} m into / built {T.sites[name]['fill']:.0f} m "
                          f"out of the slope: it stands against a cliff or on a mound; move it or give it a level")
    T.masks.setdefault("sites", np.zeros(T.X.shape))
    T.masks["sites"] = np.maximum(T.masks["sites"], smoothstep(r + 8, r, dist))
    T.pads = np.maximum(getattr(T, "pads", np.zeros(T.X.shape)), smoothstep(r, r - 2 * T.cell, dist))


def _earthworks(T, w):
    """Banks cut or built for a pad or a road: erosion leaves them alone (gullies cut into a fill slope read as a
    sawtooth along its edge)."""
    T.masks["earthworks"] = np.maximum(T.masks.get("earthworks", np.zeros(T.X.shape)), w)


def _shore_pad(T, name, lake, xy, d, back, clearance=None):
    """Where a pad `back` metres inland of a lake's shore goes: at the asked side's shore point unless a river runs
    there, else the nearest shore point toward that side whose pad is clear of rivers (said in the report)."""
    rw = getattr(T, "river_water", None)
    want = xy + d * back
    if rw is None or not rw.any():
        return want

    def clear(p):
        return not (rw & (np.hypot(T.X - p[0], T.Y - p[1]) < (clearance or back))).any()

    if clear(want):
        return want
    wet = ~np.isnan(T.water) & (T.lake_id == T.lakes[lake]["id"])
    edge = wet & ~ndimage.binary_erosion(wet)
    pts = np.stack([T.X[edge], T.Y[edge]], 1)
    c = np.array([T.X[wet].mean(), T.Y[wet].mean()])
    out = pts - c
    out /= np.linalg.norm(out, axis=1, keepdims=True) + 1e-9
    for k in np.argsort(-(out @ d)):
        if out[k] @ d < 0:
            break
        p = pts[k] + out[k] * back
        if clear(p):
            T.warnings.append(f"site {name!r}: a river reaches {lake!r}'s shore where asked, so the pad moved along the "
                              f"shore to [{p[0]:.0f}, {p[1]:.0f}]")
            return p
    T.warnings.append(f"site {name!r}: every shore point on that side of {lake!r} has a river beside it")
    return want


_OFFS = [(0, 1), (1, 0), (1, 1), (1, -1), (1, 2), (2, 1), (2, -1), (1, -2),
         (1, 3), (3, 1), (3, -1), (1, -3), (2, 3), (3, 2), (3, -2), (2, -3)]  # 32 headings: steep slopes need near-contour ones


BUMP = 1.0


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
        # each step may be up to BUMP metres off the grade: the carve evens out bumps that size (planning on ground
        # smoothed over 30 m instead hid 45 deg risers, so plans went where no road could be built)
        g = np.maximum(np.abs(H.ravel()[B] - H.ravel()[A]) - BUMP, 0) / length
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


def _grid(T, r, cliffs=True, extra=None):
    """The search grid for a route: ground smoothed over ~30 m (the carve evens out smaller bumps anyway), except
    where earthworks already shaped it (a break's benches smoothed away are a cliff again), and what blocks it."""
    f = 2 if T.X.size > 400_000 else 1  # (at every other cell, one-cell cliff bands fell between samples)
    sm = ndimage.gaussian_filter(T.H, float(r.get("smooth", 6.0)) / T.cell / 2)  # nearly the real ground (see BUMP)
    ew = T.masks.get("earthworks", np.zeros(T.X.shape))
    H = np.where(ew > 0.5, T.H, sm)[::f, ::f]
    cell = T.cell * f
    lakes = getattr(T, "lake_id", np.zeros(T.X.shape, int)) > 0
    blocked = lakes[::f, ::f].copy()
    # true cliffs are walls to a road, however the smoothing sees them (a 70 deg canyon band smoothed read as 25%)
    if cliffs:
        cliff = (T._slope() > 50) & (ew <= 0.5)
        for a in [r["from"], *r.get("via", []), r["to"]]:  # a stop on a crest isn't walled in by its own steep sides
            xy = T.address(a)[0]
            cliff &= np.hypot(T.X - xy[0], T.Y - xy[1]) > 3 * T.cell * f + float(r.get("width", 5))
        blocked |= ndimage.maximum_filter(cliff, size=f)[::f, ::f] if f > 1 else cliff
    river = getattr(T, "river_water", np.zeros(T.X.shape, bool)) & ~getattr(T, "ford_mask", np.zeros(T.X.shape, bool))
    penalty = ndimage.binary_dilation(river, iterations=f)[::f, ::f] * 40.0 * cell  # wading/bridging costs: use fords
    for a in r.get("avoid", []):
        blocked |= region(T, a)[::f, ::f] > 0.5
    if r.get("stay_in"):
        blocked |= region(T, r["stay_in"])[::f, ::f] < 0.5
    if extra is not None:  # cells an earlier plan's legs crowded
        blocked |= ndimage.maximum_filter(extra, size=f)[::f, ::f] if f > 1 else extra
    return H, cell, blocked, penalty


def _cell_of(T, c, cell):
    return int(round((c[1] - T.ys[0]) / cell)), int(round((c[0] - T.xs[0]) / cell))


def _search(T, name, r, maxg, cliffs=True, extra=None):
    """The least-cost way through the stops at the asked grade, relaxing it if nothing connects. Returns (legs of
    [x, y] points, how much it was relaxed, where the asked grade ran out) or None when nothing connects at all."""
    stops = [r["from"], *r.get("via", []), r["to"]]
    H, cell, blocked, penalty = _grid(T, r, cliffs, extra)
    pts = []
    relaxed, strict_at = 1.0, None
    for a, b in zip(stops[:-1], stops[1:]):
        ca, cb = [T.address(x)[0] for x in (a, b)]
        ga, gb = _cell_of(T, ca, cell), _cell_of(T, cb, cell)
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
            if extra is not None:  # blocking crowded legs closed it off: the caller keeps its earlier plan
                return None
            if cliffs:  # the best it can do over the cliffs, drawn and judged as built (FAIL), rather than nothing
                found = _search(T, name, r, maxg, cliffs=False)
                if found is not None:
                    cove = getattr(T, "sea", None) and any(isinstance(x, str) and x in T.sea["coves"] or
                                                           (isinstance(x, str) and x in T.sites and
                                                            (T.spec.get("sites") or {}).get(x, {}).get("at") in T.sea["coves"])
                                                           for x in (a, b))
                    T.warnings.append(f"route {name!r}: cliffs over 50 deg close {a!r} off from {b!r} and no break "
                                      f"could be cut (max_break {r.get('max_break', 250):g} m): drawn over the cliff, "
                                      f"judged as built" + ("; a cove's scar walls in its apron: give the cove a "
                                                            "\"valley\" toward where the route goes" if cove else
                                                            "; move a stop or add a 'via' past the cliff"))
                return found
            T.warnings.append(f"route {name!r}: no way from {a!r} to {b!r} (water or avoided zones close it off)")
            return None
        if strict is not None and strict_at is None:
            reach, (gy, gx) = strict
            yy, xx = np.nonzero(reach)
            end = np.array([T.xs[0] + gx * cell, T.ys[0] + gy * cell])
            k = int(np.argmin(np.hypot(T.xs[0] + xx * cell - end[0], T.ys[0] + yy * cell - end[1])))
            strict_at = (np.array([T.xs[0] + xx[k] * cell, T.ys[0] + yy[k] * cell]), end)
        iy, ix = np.divmod(path, H.shape[1])
        leg = np.stack([T.xs[0] + ix * cell, T.ys[0] + iy * cell], 1)
        leg[0], leg[-1] = ca, cb
        pts.append(leg if not pts else leg[1:])
    return pts, relaxed, strict_at


def _breaks(T, name, r, maxg, width, tries=8):
    """Where nothing connects a route's stops at its grade, the barrier is the gap between what each end can reach
    (a cliff band, a cove's scar). Break it where it's thinnest: switchback legs at the route's grade cut across the
    step, the ground shaped into benches with rock cut between them. Then look again (a canyon has several bands)."""
    stops = [r["from"], *r.get("via", []), r["to"]]
    cuts = []
    keep_H, keep_ew = T.H.copy(), T.masks.get("earthworks", np.zeros(T.X.shape)).copy()
    opened = False
    for _ in range(tries):
        H, cell, blocked, penalty = _grid(T, r)
        opened = True
        pair = None
        for a, b in zip(stops[:-1], stops[1:]):
            ga, gb = _cell_of(T, T.address(a)[0], cell), _cell_of(T, T.address(b)[0], cell)
            ra = _path(T, H, cell, ga, gb, maxg * 0.95, blocked, reach_only=True, penalty=penalty)
            if ra is None:
                continue
            opened = False
            rb = _path(T, H, cell, gb, ga, maxg * 0.95, blocked, reach_only=True, penalty=penalty)
            if rb is None:
                continue
            ea = ra[0] & ~ndimage.binary_erosion(ra[0], border_value=1)  # (the frame's own edge isn't a barrier)
            eb = rb[0] & ~ndimage.binary_erosion(rb[0], border_value=1)
            if not ea.any() or not eb.any():
                continue
            pa = np.stack(np.nonzero(ea), 1)
            pb = np.stack(np.nonzero(eb), 1)
            kq = min(25, len(pb))  # several candidates each: the nearest far side may be the tallest
            d, j = cKDTree(pb).query(pa, k=kq)
            d, j = np.atleast_2d(d.T).T.reshape(len(pa), -1), np.atleast_2d(j.T).T.reshape(len(pa), -1)
            ia = np.repeat(np.arange(len(pa)), d.shape[1])
            d, j = d.ravel(), j.ravel()
            to_xy = lambda q: np.stack([T.xs[0] + q[:, 1] * cell, T.ys[0] + q[:, 0] * cell], 1)
            xa, xb = to_xy(pa[ia]), to_xy(pb[j])
            za, zb = T.sample(xa), T.sample(xb)
            drop = np.abs(za - zb)
            goal = T.address(b)[0]
            zg = T.height(goal)
            toward = np.abs(zb - zg) < np.abs(za - zg) - 2  # a break has to bring the route nearer its goal's height
            # the lowest and thinnest place in the barrier (the thinnest alone broke a cove's scar where it was 193 m
            # tall, when its sides come down toward the headlands), heading for the goal; never taller than max_break
            # near the route's own line between its stops: the thinnest place anywhere was the canyon's end at the
            # frame's edge, a kilometre off the way
            st = T.address(a)[0]
            ax = goal - st
            tt = np.clip(((xa + xb) / 2 - st) @ ax / max(ax @ ax, 1e-9), 0, 1)
            off = np.linalg.norm((xa + xb) / 2 - (st + tt[:, None] * ax), axis=1)
            cost = np.where((drop <= float(r.get("max_break", 250.0))) & (drop >= 5) & toward & (d > 0),
                            d + 2.0 * drop + 1.0 * off, np.inf)
            order = np.argsort(cost)
            pair = [(xa[i], xb[i]) for i in order[:12] if np.isfinite(cost[i])]  # the best few, tried in turn
            if pair:
                break
        if pair is None:  # every stretch connects at its grade now, or nothing can be broken
            break
        cut = None
        for A, B in pair:
            if T.height(A) < T.height(B):
                A, B = B, A
            zm = (T.height(A) + T.height(B)) / 2
            if any(np.hypot(*((A + B) / 2 - np.array(c["at"]))) < 50 and abs(zm - c["z"]) < 10 for c in cuts):
                continue  # broke there already (the same step, not the next band down)
            cut = _cut_break(T, name, A, B, maxg, width, r)  # None: no dry room beside that cliff; the next one
            if cut is not None:
                break
        if cut is None:
            break
        cuts.append(cut)
    if cuts and not opened:  # breaks that didn't open the way come out again: earthworks for nothing
        T.H, T.masks["earthworks"] = keep_H, keep_ew
        T.warnings.append(f"route {name!r}: breaks through its cliffs didn't open a way at its grade; none were kept")
        return []
    return cuts


def _cut_break(T, name, A, B, maxg, width, r):
    zA, zB = T.height(A), T.height(B)
    drop = zA - zB
    if drop < 3:
        return None
    g = 0.9 * maxg
    w_half = max(width / 2 + 2, 1.5 * T.cell * (2 if T.X.size > 400_000 else 1))
    # across the cliff is its own downhill direction at the crossing, not the line between the two points found either
    # side of it (they can lie diagonally along a canyon: the legs then dug a quarry into the plateau)
    gy, gx = np.gradient(ndimage.gaussian_filter(T.H, max(2.0, 0.25 * drop / T.cell)), T.cell)
    iy, ix = _ij(T, (A + B) / 2)
    dirv = -np.array([gx[iy, ix], gy[iy, ix]])
    if np.linalg.norm(dirv) < 1e-6:
        dirv = B - A
    dirv = dirv / (np.linalg.norm(dirv) + 1e-9)
    dl = max(float((B - A) @ dirv), 0.0)  # its distance across (the bottom leg ends on the same foot as B)
    tv = np.array([-dirv[1], dirv[0]])
    # the legs are as long as the cliff runs on beside the crossing: both its top and its foot staying near their
    # heights, on dry land (fixed 30 m legs made a 209 m canyon wall into 31 legs stacked in a 1 km trench; long fixed
    # legs ran into the sides of a cove's bowl)
    wet = ~np.isnan(T.water)
    tol = max(3.0, 0.15 * drop)

    def room(sg):
        s_ = np.arange(T.cell, float(r.get("leg", 300.0)), T.cell)
        top, foot = A + sg * tv * s_[:, None], B + sg * tv * s_[:, None]
        ok = ((np.abs(T.sample(top) - zA) < tol) & (np.abs(T.sample(foot) - zB) < tol)
              & ~wet.ravel()[_cells(T, top)] & ~wet.ravel()[_cells(T, foot)])
        bad = np.nonzero(~ok)[0]
        return float(s_[bad[0] - 1]) if len(bad) and bad[0] > 0 else (float(s_[-1]) if not len(bad) else 0.0)

    rooms = [room(1), room(-1)]
    if max(rooms) < max(20.0, 3 * width):  # no room beside this cliff for switchbacks
        return None
    if rooms[1] > rooms[0]:
        tv = -tv
    nlegs = max(1, int(math.ceil(drop / (g * max(rooms)))))
    leg = drop / (g * nlegs)
    # rock cut between the benches at up to 55 deg, the stack centred on the cliff
    sep = max(2 * w_half + 2 * T.cell, (g * leg) / math.tan(math.radians(55)))
    # the top leg starts at the step's top and the bottom one ends at its foot: spread across the step when it's wide
    # enough (centred on a wide canyon wall, the top leg began in mid-wall, joined to nothing), centred on the cliff
    # (cut into the land either side) when it's narrower than the stack
    if nlegs > 1 and dl >= (nlegs - 1) * sep:
        us = np.linspace(0, dl, nlegs)
    else:
        us = np.array([dl / 2 + (kk - (nlegs - 1) / 2) * sep for kk in range(nlegs)])
    V = np.stack([T.X - A[0], T.Y - A[1]], -1)
    uu, vv = V @ dirv, V @ tv
    vc = np.clip(vv, 0, leg)
    zleg = np.array([zA - g * (leg * kk + (vc if kk % 2 == 0 else leg - vc)) for kk in range(nlegs)])
    kf = np.clip(np.interp(uu, us, np.arange(nlegs)) if nlegs > 1 else np.zeros_like(uu), 0, nlegs - 1)
    k0 = np.floor(kf).astype(int)
    k1 = np.minimum(k0 + 1, nlegs - 1)
    t = kf - k0
    bench = min(0.45, w_half / max(sep, 1e-6))  # flat benches around each leg, rock cut between
    t = np.clip((t - bench) / max(1 - 2 * bench, 1e-6), 0, 1)
    S = np.take_along_axis(zleg, k0[None], 0)[0] * (1 - t) + np.take_along_axis(zleg, k1[None], 0)[0] * t
    # the top leg starts on the upper ground and the bottom one ends on the lower: extend the benches' ends there
    bank = max(15.0, 2 * T.cell)
    wgt = (smoothstep(-w_half - bank, -w_half, vv) * smoothstep(leg + w_half + bank, leg + w_half, vv)
           * smoothstep(us[0] - w_half - bank, us[0] - w_half, uu) * smoothstep(us[-1] + w_half + bank, us[-1] + w_half, uu))
    # no deeper than the step itself (plus a margin): along a curving scar on a cone the legs ran into rising ground and
    # cut 169 m
    lim = drop + 10.0
    wgt = wgt * smoothstep(lim + 10, lim, np.abs(S - T.H))
    before = T.H.copy()
    T.H = T.H * (1 - wgt) + S * wgt
    _earthworks(T, wgt)
    return {"route": name, "at": ((A + B) / 2).tolist(), "z": (zA + zB) / 2, "drop": drop, "legs": nlegs,
            "cut": float((before - T.H).max()), "fill": float((T.H - before).max())}


def _profile(T, pts, maxg, relax=1.0):
    """The planned way as dense points and its road height: the grid path's staircase smoothed, resampled evenly,
    graded to 0.92 of the limit both ways and pulled back toward the ground."""
    xy = np.vstack(pts)
    # (not smoothed: every way of smoothing the grid's staircase that was tried moved the road onto ground the search
    # hadn't checked, over cliff lips and down risers, and failed more roads as built)
    s, length = _arclen(xy)
    n = max(2, int(length / (T.cell / 2)))
    u = np.linspace(0, 1, n)
    xy = np.stack([np.interp(u, s, xy[:, 0]), np.interp(u, s, xy[:, 1])], 1)
    step = np.linalg.norm(np.diff(xy, axis=0), axis=1)  # true steps: shorter than length/(n-1) at corners
    ds = length / (n - 1)
    ground = T.sample(xy)
    h = ndimage.gaussian_filter1d(ground, 30 / ds, mode="nearest")
    gp = 0.85 * maxg  # planned with slack under the limit: the grid leaves about a metre of wiggle (24% on 20 at 0.92)
    for _ in range(30):  # grade limit both ways, pulled back toward the ground
        for i in range(1, n):
            h[i] = np.clip(h[i], h[i - 1] - gp * step[i - 1], h[i - 1] + gp * step[i - 1])
        for i in range(n - 2, -1, -1):
            h[i] = np.clip(h[i], h[i + 1] - gp * step[i], h[i + 1] + gp * step[i])
        h = 0.8 * h + 0.2 * ndimage.gaussian_filter1d(ground, 10 / ds, mode="nearest")
    for i in range(1, n):
        h[i] = np.clip(h[i], h[i - 1] - gp * step[i - 1], h[i - 1] + gp * step[i - 1])
    return xy, h, n


def _crowded(xy, h, width):
    """Points of later legs that pass too close to an earlier leg for both beds and a bank of at most 45 deg between."""
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
    reach = width + 4 + 40
    pairs = cKDTree(xy).query_pairs(reach, output_type="ndarray")
    if not len(pairs):
        return np.zeros(0, int)
    i, j = pairs[:, 0], pairs[:, 1]
    d = np.linalg.norm(xy[i] - xy[j], axis=1)
    along = np.abs(s[j] - s[i])
    need = width + 4 + np.abs(h[i] - h[j])  # beds apart by their width, and the bank between no steeper than 45 deg
    bad = (d < need) & (along > 3 * need + 2 * width)
    return np.unique(np.maximum(i[bad], j[bad]))


def _route(T, name, r):
    maxg = float(r.get("max_grade", 0.12))
    width = float(r.get("width", 5))
    stops = [r["from"], *r.get("via", []), r["to"]]
    cuts = _breaks(T, name, r, maxg, width) if r.get("breaks", True) else []
    T.breaks = getattr(T, "breaks", []) + cuts
    found = _search(T, name, r, maxg)
    if found is not None and found[1] > 1:  # walled off by cliffs it winds far and steep: over them may be better
        alt = _search(T, name, r, maxg, cliffs=False)
        if alt is not None and alt[1] <= found[1]:  # (a tie: as before cliffs were walls)
            found = alt
    if found is None:
        return
    pts, relaxed, strict_at = found
    if relaxed > 1:
        msg = (f"route {name!r}: nothing within {100 * maxg:.0f}% connects its stops; searched at "
               f"{100 * maxg * relaxed:.0f}% (the carve then eases what it can)")
        if strict_at is not None:  # say where the asked grade runs out and what's in the way
            near, end = strict_at
            dz = T.height(end) - T.height(near)
            dd = max(float(np.linalg.norm(end - near)), 1.0)
            msg += (f". At {100 * maxg:.0f}% it gets as far as [{near[0]:.0f}, {near[1]:.0f}], {dd:.0f} m short; from "
                    f"there the ground {'rises' if dz > 0 else 'falls'} {abs(dz):.0f} m to the stop ({100 * abs(dz) / dd:.0f}% "
                    f"straight): lower/raise the stop, add a 'via' where it can wind, or allow a steeper grade")
        T.warnings.append(msg)
    xy, h, n = _profile(T, pts, maxg, relaxed)
    # switchback legs need room between them for their beds and a bank of at most 45 deg: where the plan crowds them,
    # the later leg's cells are closed and it plans again, wider (built crowded, one leg's carve broke the other's
    # bed: a descent planned at 25% measured 167% as built)
    extra = np.zeros(T.X.shape, bool)
    for _ in range(int(r.get("uncrowd", 5))):
        bad = _crowded(xy, h, width)
        if not len(bad):
            break
        for p in xy[bad]:
            extra |= np.hypot(T.X - p[0], T.Y - p[1]) < width / 2 + T.cell
        again = _search(T, name, r, maxg, extra=extra)
        if again is None or again[1] > relaxed:
            T.warnings.append(f"route {name!r}: switchback legs crowd each other near [{xy[bad[0], 0]:.0f}, "
                              f"{xy[bad[0], 1]:.0f}] (too little room between them for a bank); the ground there may "
                              f"not hold both")
            break
        pts = again[0]
        xy, h, n = _profile(T, pts, maxg, relaxed)
    length = _arclen(xy)[1]
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
        # earthworks have a limit: past ~25 m of cut or fill a road is a bridge or a tunnel, not a causeway (a 65 m fill
        # built a tongue out over a canyon); left as it is, and the report says where
        # cut up to 25 m (a cutting); fill at the way's own scale: a 2 m mule trail doesn't stand on a 25 m bank (it
        # made knife-edge fins)
        deep = float(r.get("max_earthworks", 25.0))
        tall = float(r.get("max_fill", deep))  # (a 6-12 m default made trails fail down gullies: fins are the lesser evil)
        w *= np.where(hr > T.H, smoothstep(tall + 3, tall, hr - T.H), smoothstep(deep + 5, deep, T.H - hr))
        if hasattr(T, "pads"):  # a road arrives at a site; it doesn't bury or trench the pad (its bank it grades through:
            w *= 1 - T.pads  # left alone, the bank stood as a step where every road met its pad)
        before = T.H.copy()
        T.H = T.H * (1 - w) + hr * w
        _earthworks(T, w)
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
                                                   "cut": cut, "fill": fill, "relaxed": relaxed})


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
    # slope of the ground smoothed over a cell, its thresholds shifted by noise a few cells across: cut on the raw
    # slope, rock and snow speckled cell by cell and every boundary was a hard pasted line along one contour of slope
    pts = np.c_[T.P, np.zeros(len(T.P))]
    jit = 2 * noise.fbm(pts, max(3 * T.cell, 25.0), 3, seed=47).reshape(T.X.shape) - 1
    slope = T._slope(ndimage.gaussian_filter(T.H, 1.0)) + 6.0 * jit
    elev_j = jit * max(4 * T.cell, 20.0)
    layers = list(T.spec.get("cover") or {})
    # painted in key order, or by each layer's "order" (a patch can't reorder keys: scree had to be deleted and re-added
    # to paint after rock)
    pos = {n: i for i, n in enumerate(layers)}
    layers.sort(key=lambda n: (float((T.spec["cover"][n] or {}).get("order", pos[n])), pos[n]))
    for k, name in enumerate(layers):
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
            Hj = T.H + elev_j * min(1.0, fade / 40)
            m *= smoothstep(lo - fade, lo + fade, Hj) * smoothstep(hi + fade, hi - fade, Hj)
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
        across = 2 * math.sqrt(b["inside"].sum() / math.pi) * T.cell  # the ring's rough diameter
        floor_share = b["floor"].sum() / max(b["inside"].sum(), 1)
        out.append(f"realism: basin {name}: from the floor's edge up to the crest at {b['avg']:.0f} deg takes a median "
                   f"{b['width']:.0f} m of mountainside; the ring is ~{across:.0f} m across, leaving "
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
        wall = b["wall"] & np.isnan(T.water)
        built = float(np.degrees(np.arctan(np.tan(np.radians(T._slope()[wall])).mean()))) if wall.any() else 0.0
        out.append(f"basin {name}: floor {b['floor'].sum() * T.cell ** 2 / 1e6:.2f} km2 from {fl.min():.0f} to "
                   f"{np.percentile(fl, 98):.0f} m, drains to [{b['falls'][0]:.0f}, {b['falls'][1]:.0f}]; "
                   f"walls {b['width']:.0f} m wide, averaging {built:.0f} deg as built (asked {b['avg']:.0f}) with "
                   f"{b['bands'] or ('3' if b['character'] == 'tiered' else '1')} cliff band(s) {b['band']:.0f} m tall")
    from .terrain_forms import measure_canyon, measure_mesa
    for name, c in getattr(T, "canyons", {}).items():
        m = measure_canyon(T, name)
        w = f"{m['width'][0]:.0f}-{m['width'][1]:.0f} m rim to rim" if m["width"] else "rim to rim not measurable"
        (cs, cf), (ls, lf) = m["cliff"], m["ledge"]
        strata = (f"cliff strata median {cs:.0f} deg ({100 * cf:.0f}% over 60), ledges median {ls:.0f} deg"
                  if np.isfinite(cs) and np.isfinite(ls) else "no strata could be built (too narrow or too shallow for "
                  "its bands: its walls are talus slopes)")
        out.append(f"canyon {name} (measured): {m['depth'] or 0:.0f} m deep at its deepest, {w} (asked "
                   f"{2 * c['half']:.0f}); {strata}, talus at the foot")
        if np.isfinite(cs) and cs < 50:
            T.warnings.append(f"canyon {name!r}: its cliff strata stand at only {cs:.0f} deg as built (the grid and "
                              f"erosion soften them): they read as steep slopes, not cliffs; a finer cell sharpens them")
        if np.isfinite(ls) and ls > 40:
            T.warnings.append(f"canyon {name!r}: its ledges are {ls:.0f} deg as built, too steep to read as ledges: the "
                              f"canyon is too narrow for its depth and bands; widen it or use fewer bands")
    for name, m in getattr(T, "mesas", {}).items():
        mm = measure_mesa(T, name)
        out.append(f"mesa {name} (measured): top {mm['top']:.0f} m (asked {m['top']:.0f}), flat within 2 m over "
                   f"{mm['across']:.0f} m across, cliff median {mm['cliff']:.0f} deg, {mm['rise']:.0f} m above the ground "
                   f"around it")
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
        line = (f"pass {name}: through {p['ridge']} at [{c[0]:.0f}, {c[1]:.0f}], saddle at {T.height(c):.0f} m as built"
                + (f" (planned {p['floor']:.0f})" if abs(T.height(c) - p["floor"]) > 3 else "") + ", "
                f"{p['width']:.0f} m wide; the way: " + "; ".join(sides))
        if worst:
            line += f" FAIL: {100 * worst[0]:.0f}% at [{worst[1][0]:.0f}, {worst[1][1]:.0f}]"
        out.append(line)
    for name, (zone, sc) in getattr(T, "rugged_zones", {}).items():
        if zone.sum() < 5:
            out.append(f"rugged {name}: its zone is empty")
            continue
        detail = T.H - ndimage.gaussian_filter(T.H, max(sc, 2 * T.cell) / T.cell)
        rough_in = float(np.std(detail[zone]))
        rough_out = float(np.std(detail[~zone])) if (~zone).sum() > 5 else float("nan")
        out.append(f"rugged {name}: {zone.sum() * T.cell ** 2 / 1e4:.1f} ha; the ground's detail at its {sc:.0f} m scale "
                   f"stands +-{rough_in:.1f} m there (+-{rough_out:.1f} m elsewhere)")
    for name, s in T.sites.items():
        wet = ~np.isnan(T.water)
        dw = (np.hypot(T.X - s["xy"][0], T.Y - s["xy"][1])[wet].min() - s["radius"]) if wet.any() else None
        sea = getattr(T, "sea", None)
        if sea is not None:
            iy = int(np.clip(round((s["xy"][1] - T.ys[0]) / T.cell), 0, len(T.ys) - 1))
            ix = int(np.clip(round((s["xy"][0] - T.xs[0]) / T.cell), 0, len(T.xs) - 1))
            if sea["sd"][iy, ix] < 0:  # (a pad built out into the sea on a fill mound had read "edge 8 m from water")
                T.warnings.append(f"site {name!r}: its centre is {-sea['sd'][iy, ix]:.0f} m out to sea of the coastline: the "
                                  f"pad stands on {s['fill']:.0f} m of fill in the water. Move it inland, or put the "
                                  f"cove/beach where it should stand")
        out.append(f"site {name}: pad {2 * s['radius']:.0f} m across at {s['level']:.0f} m, centre "
                   f"[{s['xy'][0]:.0f}, {s['xy'][1]:.0f}]; cut {s['cut']:.0f} m, fill {s['fill']:.0f} m{s.get('note', '')}"
                   + (f"; edge {dw:.0f} m from water" if dw is not None else ""))
    for name, R in T.routes.items():
        # the road as built: the ground under its centre line after every carve, not its own planned profile (that
        # always met the limit, so the line said OK where the warnings said nothing connects at that grade)
        g = _grades(T, R.xy)
        ok = g.max() <= R.props["max_grade"] + 0.01
        turns = _switchbacks(R.xy)
        worst = int(np.argmax(g))
        verdict = "OK" if ok else f"FAIL at [{R.xy[worst, 0]:.0f}, {R.xy[worst, 1]:.0f}]"
        if not ok:  # (a FAIL had no warning at all)
            T.warnings.append(f"route {name!r} FAILS its grade as built: {100 * g.max():.0f}% at [{R.xy[worst, 0]:.0f}, "
                              f"{R.xy[worst, 1]:.0f}] (limit {100 * R.props['max_grade']:.0f}%)")
        if R.props.get("relaxed", 1) > 1:
            verdict += (f" (no way at {100 * R.props['max_grade']:.0f}% exists on the ground: it was found at "
                        f"{100 * R.props['max_grade'] * R.props['relaxed']:.0f}% and graded by cutting and filling)")
        out.append(f"route {name}: {R.props['length']:.0f} m, climbs {np.abs(np.diff(R.h)).sum():.0f} m, "
                   f"{turns} switchbacks, steepest 20 m as built {100 * g.max():.0f}% (limit "
                   f"{100 * R.props['max_grade']:.0f}%) {verdict}; cut up to {R.props['cut']:.0f} m, fill "
                   f"{R.props['fill']:.0f} m")
        for bk in getattr(T, "breaks", []):
            if bk["route"] == name:
                out.append(f"    breaks through a {bk['drop']:.0f} m step at [{bk['at'][0]:.0f}, {bk['at'][1]:.0f}]: "
                           f"{bk['legs']} switchback leg(s) cut into it (cut up to {bk['cut']:.0f} m, fill "
                           f"{bk['fill']:.0f} m); \"breaks\": false to forbid")
        for end, k in (("start", 0), ("end", -1)):
            gap = float(R.h[k] - T.sample(R.xy[k:k + 1] if k == 0 else R.xy[-1:])[0])
            if abs(gap) > 3:
                out.append(f"    its graded bed {'ends' if k else 'starts'} {abs(gap):.0f} m {'above' if gap > 0 else 'below'} "
                           f"the ground at its {end}: the last stretch there is a drop no road at its grade could make "
                           f"(a cliff band in the way: move the stop, or allow a steeper grade)")
        rw = getattr(T, "river_water", None)
        if rw is not None and rw.any():
            # each stretch of the road in river water is one crossing; it's a ford crossing if any of it is in a ford
            # (a road starting on a ford leaves it through the same water: that isn't a second crossing)
            cells = _cells(T, R.xy)
            wet = rw.ravel()[cells] | T.ford_mask.ravel()[cells]
            lab, n = ndimage.label(wet)
            fords, bridges = set(), []
            for k in range(1, n + 1):
                run = lab == k
                if T.ford_mask.ravel()[cells][run].any():
                    fords.update(nm for nm, fd in T.fords.items()
                                 if np.hypot(*(R.xy[run] - fd["xy"]).T).min() < fd["width"] * 1.5)
                else:
                    bridges.append(R.xy[run].mean(0))
            if fords:
                out.append("    crosses at a ford: " + ", ".join(sorted(fords)))
            if bridges:
                out.append(f"    crosses river water at " + ", ".join(f"[{x:.0f}, {y:.0f}]" for x, y in bridges)
                           + ": needs a bridge (or add a ford there)")
        off = np.abs(T.sample(R.xy) - R.h) > 1.0  # the ground under the road isn't the road: legs crowd each other
        if off.any():
            lab, n = ndimage.label(off)
            spots = sorted(((lab == k).sum(), k) for k in range(1, n + 1))[::-1][:3]
            out.append(f"    ground and road disagree by over 1 m along {off.sum() * R.props['length'] / len(R.xy):.0f} m "
                       f"(over 25 m of cut or fill is left for a bridge or tunnel; or legs pass close, or a later carve "
                       f"changed the ground): " + ", ".join(
                           f"[{R.xy[lab == k][:, 0].mean():.0f}, {R.xy[lab == k][:, 1].mean():.0f}]" for _, k in spots))
    for name, W in T.walls.items():
        out.append(f"wall {name} (measured): {W['length'] / 1000:.1f} km of edge, {100 * W['fraction']:.0f}% at least "
                   f"{W['spec'].get('min_slope', 50)} deg for {W['spec'].get('height', 40)} m "
                   f"(raised up to {W['raised']:.0f} m)")
        for xy, length, steep, tall in W["climbable"][:5]:
            out.append(f"    climbable: {length:.0f} m near [{xy[0]:.0f}, {xy[1]:.0f}] (steepest {steep:.0f} deg, its tallest "
                       f"steep stretch {tall:.0f} m)")
    for name, m in T.cover.items():
        line = f"cover {name}: {_area(m.sum() * T.cell ** 2)} equivalent ({100 * m.mean():.0f}% of the frame)"
        zs = [z for z in T.zones][:4]
        if zs:
            line += "; " + ", ".join(f"{z} {100 * (m * region(T, z)).sum() / max(region(T, z).sum(), 1):.0f}%" for z in zs)
        out.append(line)
    for a in (T.spec.get("probe") or []):  # the finished ground: after sites, roads and erosion
        xy, h, _ = T.address(a)
        out.append(f"probe {a}: [{xy[0]:.0f}, {xy[1]:.0f}] ground as built {h:.0f} m, slope {T._slope()[_ij(T, xy)]:.0f} deg")
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
            out += _see(T, name, it)
        if "hide" in it:  # the other way round: must NOT be seen from there (a hidden beach, a secret path)
            out += _see(T, name, {**it, "see": it["hide"]}, hide=True)
    return out


def _see(T, name, it, hide=False):
    """intent "see": from a place (a site: the eye at its centre and eight spots across it) to each target: whether the
    sight line clears the ground; for a summit or mesa how many metres of it show above what's in front and how far it
    stands above the skyline beside and behind it ("min_prominence"); for a lake the share of its surface seen."""
    out = []
    eye = float(it.get("eye", 1.7))
    src = it["from"]
    spots = [("centre", src)]
    if isinstance(src, str) and src in T.sites:
        st = T.sites[src]
        c = np.array(st["xy"])
        spots = [("centre", c.tolist())] + [(_compass(a), (c + 0.7 * st["radius"] * np.array([math.sin(a), math.cos(a)])).tolist())
                                            for a in np.radians(np.arange(0, 360, 45))]
        # only spots on the pad: one over a lip's drop would be an eye in the air
        spots = [sp for sp in spots if T.height(np.array(sp[1])) > st["level"] - 3] or spots[:1]
    want = it.get("min_visible", 0)
    prom = it.get("min_prominence")
    for tgt in it["see"]:
        cove = isinstance(tgt, str) and getattr(T, "sea", None) is not None and tgt in T.sea["coves"]
        lake = isinstance(tgt, str) and (tgt in T.lakes or cove)
        got = []
        for label, xy in spots:
            if lake:  # (a cove is the sea's water in its bay)
                v, tall, dip = (lake_seen(T, xy, "sea", eye, angles=True, mask=T.sea["coves"][tgt]["mask"]) if cove
                                else lake_seen(T, xy, tgt, eye, angles=True))
                got.append((label, v, v > 0, None, tall, dip))
            else:
                r = sight(T, xy, tgt, eye)
                got.append((label, r["visible"], r["visible"] > want, r, 0, 0))
        ok = [g for g in got if g[2]]
        if hide:
            line = (f"intent {name}: {_label(tgt)} hidden from {src}: " + ("seen from none of the spots OK" if not ok else
                    f"FAIL: seen from {len(ok)} of {len(got)} spots (" + ", ".join(g[0] for g in ok[:4]) + ")"))
            out.append(line)
            continue
        summit = not lake and "standout" in got[0][3]
        fmt = ((lambda v: f"{100 * v:.0f}% of its surface") if lake else
               (lambda v: f"{v:.0f} m of it showing" if v > 0 else "hidden") if summit
               else (lambda v: f"clear by {v:.0f} m" if v > 0 else f"blocked, {-v:.0f} m short"))
        best = max(got, key=lambda g: g[1])
        where = f"from {src}" + (f": seen from {len(ok)} of {len(got)} spots across it (centre {fmt(got[0][1])}, best "
                                 f"{best[0]} {fmt(best[1])})" if len(spots) > 1 else f": {fmt(got[0][1])}")
        line = f"intent {name}: {_label(tgt)} {where}; eye {eye:g} m" + ("" if ok else " FAIL")
        if lake and ok:
            b = max(got, key=lambda g: g[4])
            line += (f"; the water seen stands {got[0][4]:.1f} deg tall in the view from the centre ({b[4]:.1f} at best, "
                     f"{b[0]}), its far edge {b[5]:.1f} deg below the horizon")
            if b[4] < 1.0:
                line += " (a thin strip at eye level: lower the water relative to the eye, or bring it closer)"
        r = got[0][3]
        if not ok and r is not None and r.get("block") is not None:
            b = r["block"]
            line += f" (the ground at [{b[0]:.0f}, {b[1]:.0f}] is in the way)"
        if r is not None:
            if summit:
                so = max(g[3]["standout"] for g in got)
                line += f"; its top stands {so:.0f} m above the skyline beside/behind it" if so > 0 else \
                    f"; its top is {-so:.0f} m below the skyline beside/behind it (it doesn't stand out)"
                if prom is not None and so < prom:
                    line += f" FAIL (want >= {prom:g} m)"
            sk = any(g[3]["skyline"] for g in got)
            line += "; on the skyline" if sk else "; against higher ground behind it"
            if it.get("skyline") and not sk:
                line += " FAIL (wanted on the skyline)"
        out.append(line)
    return out
