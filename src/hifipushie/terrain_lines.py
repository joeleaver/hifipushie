"""Linear features: hedgerows, stone walls, fences, earth banks, ditches, lines of trees. Anything a designer draws as a
line on the land that isn't a way to walk (routes) or water (rivers).

"lines": {name: {"type": "hedge" | "stone wall" | "fence" | "bank" | "ditch" | "trees",
                 one of: "along": [addresses], "follows": route | river, "around": zone, "network": {...},
                 "side"?: "left" | "right" | "both", "offset"?: m, "from"?/"to"?: 0..1 (follows),
                 "gaps"?: [addresses], "gates"?: m (a gap every so far), "width"?, "bank"?, "ditch"?, "height"?,
                 "shrubs"?: m, "trees"?: m | false}}

A type is a cross-section and what stands on it; any of its numbers can be given:
  hedge       a bank 0.4 m under a 2.5 m wide hedge (shrubs every 1.8 m, a tree standing out of it every ~25 m)
  stone wall  a dry-stone wall 1.2 m high, 0.7 m wide (below the grid: the export lists it, the views draw it)
  fence       posts and wire, 1.2 m (listed and drawn, no ground change)
  bank        an earth bank 1 m high, 4 m across
  ditch       a ditch 1 m deep, 3 m across
  trees       a line of trees (a shelterbelt, an avenue), one every 7 m, 8 m wide
"bank" and "ditch" on any type add them (a hedge with a ditch on its field side: "ditch": 0.8, "ditch_side": "right").

A line never crosses water, pads or routes: it stops at a route (a gateway) and at the water's edge. The views draw
walls and fences, and put the shrubs and trees; the export lists every line (meta.json "lines": points on the ground,
type, height, width), writes a mask per line, and the trees go in trees.csv.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from .terrain import smoothstep

TYPES = {
    "hedge": {"bank": 0.4, "width": 2.5, "shrubs": 1.8, "trees": 25.0, "cover": [0.10, 0.20, 0.08]},
    "stone wall": {"width": 0.7, "height": 1.2, "wall": True},
    "fence": {"width": 0.15, "height": 1.2, "fence": True},
    "bank": {"bank": 1.0, "width": 4.0},
    "ditch": {"ditch": 1.0, "width": 3.0},
    "trees": {"width": 8.0, "trees": 7.0, "cover": [0.12, 0.22, 0.08]},
}
ALIASES = {"hedgerow": "hedge", "hedges": "hedge", "wall": "stone wall", "drystone wall": "stone wall",
           "dry stone wall": "stone wall", "dyke": "stone wall", "stone dyke": "stone wall", "fences": "fence",
           "earth bank": "bank", "embankment": "bank", "drain": "ditch", "trench": "ditch", "tree line": "trees",
           "treeline": "trees", "shelterbelt": "trees", "avenue": "trees", "windbreak": "trees", "line of trees": "trees"}


def _type(name, f):
    t = str(f.get("type", "hedge")).lower().strip().replace("-", " ").replace("_", " ")
    t = ALIASES.get(t, t)
    if t not in TYPES:
        raise ValueError(f"line {name!r}: type {f.get('type')!r} isn't one this knows ({', '.join(TYPES)}; also "
                         f"{', '.join(sorted(ALIASES))})")
    return t, {**TYPES[t], **{k: v for k, v in f.items() if k in ("bank", "ditch", "width", "height", "shrubs", "trees",
                                                                     "ditch_side")}}


def _dense(pts, step):
    """A polyline resampled every `step` m (straight between its corners)."""
    pts = np.asarray(pts, float)
    out = [pts[:1]]
    for a, b in zip(pts[:-1], pts[1:]):
        n = max(1, int(math.ceil(np.linalg.norm(b - a) / step)))
        out.append(a + (b - a) * (np.arange(1, n + 1) / n)[:, None])
    return np.vstack(out)


def _offset(xy, off):
    """A polyline moved sideways (+ = left of its direction)."""
    t = np.gradient(xy, axis=0)
    t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
    return xy + np.stack([-t[:, 1], t[:, 0]], 1) * off


def _network(T, name, net):
    """Field boundaries over a zone: long lines `spacing` apart across it (at `angle`, or along the contours: fields
    laid across the slope), and between each pair short cross lines at irregular places (T-junctions, fields of uneven
    length), clipped to the zone."""
    from . import terrain_design as design
    zone = design.region(T, net.get("in", "everywhere")) > 0.5
    sp = net.get("spacing", 120.0)
    sx, sy = (float(sp[0]), float(sp[1])) if isinstance(sp, (list, tuple)) else (float(sp), 1.3 * float(sp))
    jit = float(net.get("jitter", 0.25))
    ang = net.get("angle", "contour")
    if ang == "contour":  # the long lines follow the slope's contours in the zone (fields across the slope)
        gy, gx = np.gradient(ndimage.gaussian_filter(T.H, max(1.0, 60.0 / T.cell)), T.cell)
        a = math.atan2(float(gy[zone].mean()), float(gx[zone].mean())) if zone.any() else 0.0
        ang_r = a + math.pi / 2
    else:
        ang_r = math.radians(90 - float(ang))  # a compass bearing for the long lines
    import zlib
    rng = np.random.default_rng(zlib.crc32(name.encode()))
    if not zone.any():
        return []
    step = max(T.cell, 2.0)
    Hs = ndimage.gaussian_filter(T.H, max(1.0, 0.3 * sx / T.cell))
    gy, gx = np.gradient(Hs, T.cell)
    grade = float(np.median(np.hypot(gx, gy)[zone]))
    lines = []
    pattern = net.get("pattern", "irregular")
    if pattern == "irregular":
        if ang == "contour":  # fields lie along the zone's mean contour
            ang_r = math.atan2(float(gy[zone].mean()), float(gx[zone].mean())) + math.pi / 2
        lines = _subdivided_fields(T, zone, sx, sy, jit, rng, ang_r)
        # and the zone's own edge (the fields' outer boundary), where it isn't the frame's edge
        from skimage import measure
        for c in measure.find_contours(np.pad(zone.astype(float), 1), 0.5):
            c = c - 1
            xy = np.stack([T.xs[0] + c[:, 1] * T.cell, T.ys[0] + c[:, 0] * T.cell], 1)
            if len(xy) > 4:
                lines.append(ndimage.gaussian_filter1d(xy, 2, axis=0))
    elif pattern == "cells":
        lines = _voronoi_fields(T, zone, sx, sy, jit, rng, gx, gy, step)
    elif ang == "contour" and grade > 0.015:
        # the long lines ARE contours of the ground (smoothed at field size), about `spacing` apart on the slope: the
        # fields lie across it wherever it turns (one straight bearing made a rigid grid)
        from skimage import measure
        dh = sx * grade
        lo, hi = float(Hs[zone].min()), float(Hs[zone].max())
        levels = np.arange(lo + dh * rng.uniform(0.3, 0.7), hi, dh)
        levels = levels + rng.uniform(-jit, jit, len(levels)) * dh
        longs = []
        for lv in levels:
            for c in measure.find_contours(Hs, lv):
                xy = np.stack([T.xs[0] + c[:, 1] * T.cell, T.ys[0] + c[:, 0] * T.cell], 1)
                if len(xy) > 3:
                    longs.append((lv, _dense(xy, step)))
        lines += [xy for _, xy in longs]
        # cross lines: from points along each contour straight down the slope to the one below (T-junctions), at
        # uneven intervals
        for lv, xy in longs:
            s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
            at = rng.uniform(0, sy)
            while at < s[-1]:
                p = np.array([np.interp(at, s, xy[:, 0]), np.interp(at, s, xy[:, 1])])
                path = [p]
                for _ in range(int(2.0 * sx / step)):
                    g = np.array([T.sample(path[-1][None], gx)[0], T.sample(path[-1][None], gy)[0]])
                    gn = np.linalg.norm(g)
                    if gn < 1e-4:
                        break
                    q = path[-1] - g / gn * step
                    path.append(q)
                    if T.sample(q[None], Hs)[0] <= lv - dh:
                        break
                if len(path) > 3:
                    lines.append(np.array(path))
                at += sy * rng.uniform(1 - jit, 1 + jit) * rng.choice([1.0, 1.0, 1.6])
    else:
        if ang == "contour":  # (flat ground: no contours to follow)
            ang_r = rng.uniform(0, math.pi)
        d = np.array([math.cos(ang_r), math.sin(ang_r)])  # along the long lines
        n = np.array([-d[1], d[0]])
        P = np.stack([T.X[zone], T.Y[zone]], 1)
        u, v = P @ d, P @ n
        vs = np.arange(v.min() - sx, v.max() + sx, sx)
        vs = vs + rng.uniform(-jit, jit, len(vs)) * sx
        for v0 in vs:
            lines.append(np.array([d * u.min() + n * v0, d * u.max() + n * v0]))
        for v0, v1 in zip(vs[:-1], vs[1:]):
            u0 = u.min() + rng.uniform(0, sy)
            while u0 < u.max():
                a = d * u0 + n * v0
                b = d * (u0 + rng.uniform(-jit, jit) * sy * 0.3) + n * v1
                lines.append(np.array([a, b]))
                u0 += sy * rng.uniform(1 - jit, 1 + jit)
    # every line wanders a little (boundaries were laid by hand, round old trees and wet ground), then is clipped to
    # the zone: dense samples kept inside, split where they leave it
    from . import noise
    out = []
    for k, L in enumerate(lines):
        xy = _dense(L, step)
        if len(xy) > 3:
            t = np.gradient(xy, axis=0)
            t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
            wob = noise.fbm(np.c_[xy, np.full(len(xy), 70.0 + k)], 0.7 * sx, 2, seed=331) - 0.5
            xy = xy + np.stack([-t[:, 1], t[:, 0]], 1) * (0.12 * sx * wob)[:, None]
        inside = T.sample(xy, ndimage.binary_dilation(zone, iterations=2).astype(float)) > 0.5
        out += _runs(xy, inside)
    return out


def _split_convex(poly, p, d):
    """A convex polygon cut by the line through p along d: (left part, right part, the cut segment) or None."""
    n = np.array([-d[1], d[0]])
    s = (poly - p) @ n
    a, b = [], []
    cut = []
    m = len(poly)
    for i in range(m):
        P, Q = poly[i], poly[(i + 1) % m]
        sp, sq = s[i], s[(i + 1) % m]
        (a if sp >= 0 else b).append(P)
        if (sp >= 0) != (sq >= 0):
            X = P + (Q - P) * (sp / (sp - sq))
            a.append(X)
            b.append(X)
            cut.append(X)
    if len(cut) != 2 or len(a) < 3 or len(b) < 3:
        return None
    return np.array(a), np.array(b), np.array(cut)


def _area_poly(poly):
    x, y = poly[:, 0], poly[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _subdivided_fields(T, zone, sx, sy, jit, rng, ang_r):
    """Irregular fields by repeated splitting: the zone's box (turned to the fields' lie) is cut across its longer side
    near its middle, a little off square, and each part again, until a field is about its target size (which varies
    0.5-2x by a slow noise: small crofts, big fields). Quads with T-junctions, like enclosure (a Voronoi of jittered
    seeds read as honeycomb, a grid as a ladder)."""
    from . import noise
    d0 = np.array([math.cos(ang_r), math.sin(ang_r)])
    n0 = np.array([-d0[1], d0[0]])
    P = np.stack([T.X[zone], T.Y[zone]], 1)
    u, v = P @ d0, P @ n0
    box = np.array([d0 * u.min() + n0 * v.min(), d0 * u.max() + n0 * v.min(),
                    d0 * u.max() + n0 * v.max(), d0 * u.min() + n0 * v.max()])
    box = box + (box - box.mean(0)) * 0.05
    target = sx * sy
    out = []
    stack = [box]
    while stack:
        poly = stack.pop()
        A = _area_poly(poly)
        c = poly.mean(0)
        size = target * (0.5 + 1.5 * float(noise.fbm(np.c_[c[None], [[4.0]]], 3 * math.sqrt(target), 2, seed=371)[0]))
        if A < size or len(out) > 4000:
            continue
        # cut across the longer side: the cut runs along the polygon's short axis (principal axes of its vertices)
        C = np.cov((poly - c).T)
        w_, V = np.linalg.eigh(C)
        long_ax = V[:, 1]
        th = rng.normal(0, 0.12 + 0.2 * min(jit, 1.5))
        dcut = np.array([-long_ax[1], long_ax[0]])
        dcut = np.array([dcut[0] * math.cos(th) - dcut[1] * math.sin(th), dcut[0] * math.sin(th) + dcut[1] * math.cos(th)])
        ext = float(np.sqrt(w_[1])) * 1.7
        p = c + long_ax * rng.uniform(-0.25, 0.25) * ext
        r = _split_convex(poly, p, dcut)
        if r is None:
            continue
        a, b, cut = r
        out.append(cut)
        stack += [a, b]
    return out


def _voronoi_fields(T, zone, sx, sy, jit, rng, gx, gy, step):
    """Irregular fields: the cells of jittered seeds (sizes varying by a slow noise, some fields twice the size of their
    neighbours), stretched along the local contour (fields lie across the slope), their shared edges as boundaries. A
    rigid grid of long lines and ticks read as a ladder."""
    from scipy.spatial import Voronoi
    from . import noise
    P = np.stack([T.X[zone], T.Y[zone]], 1)
    lo, hi = P.min(0) - sx, P.max(0) + sx
    a = math.sqrt(sx * sy)
    # seeds by dart throwing, the spacing varying 0.6-1.6x over a few fields (small crofts by the village, big fields
    # further out)
    cand = rng.uniform(lo, hi, (int(np.prod(hi - lo) / (0.15 * a * a)) + 50, 2))
    sc = 0.6 + 1.0 * noise.fbm(np.c_[cand, np.full(len(cand), 3.0)], 4 * a, 2, seed=361)
    seeds = []
    from scipy.spatial import cKDTree
    for p_, r_ in zip(cand, sc * a * (0.75 + 0.25 * (1 - min(jit, 1.0)))):
        if not seeds or cKDTree(np.array(seeds)).query(p_)[0] > r_:
            seeds.append(p_)
    seeds = np.array(seeds)
    # the local contour direction at each seed: cells stretched along it by sy/sx
    g = np.c_[T.sample(seeds, gx), T.sample(seeds, gy)]
    gn = np.linalg.norm(g, axis=1)
    ang = np.where(gn > 1e-3, np.arctan2(g[:, 1], g[:, 0]) + math.pi / 2, rng.uniform(0, math.pi, len(seeds)))
    ang0 = float(np.median(ang))
    R = np.array([[math.cos(-ang0), -math.sin(-ang0)], [math.sin(-ang0), math.cos(-ang0)]])
    S = np.diag([1.0, sy / sx]) if sy > sx else np.eye(2)
    M = np.linalg.inv(S) @ R  # into a space where the fields are round
    v = Voronoi(seeds @ M.T)
    Minv = np.linalg.inv(M)
    out = []
    for (i, j) in v.ridge_vertices:
        if i < 0 or j < 0:
            continue
        a_, b_ = v.vertices[i] @ Minv.T, v.vertices[j] @ Minv.T
        if np.any(np.abs(a_) > 1e7) or np.any(np.abs(b_) > 1e7):
            continue
        out.append(np.array([a_, b_]))
    return out


def _runs(xy, keep, min_len=6.0):
    """The pieces of a polyline where keep is True."""
    out, start = [], None
    for i, k in enumerate(np.r_[keep, False]):
        if k and start is None:
            start = i
        elif not k and start is not None:
            piece = xy[start:i]
            if len(piece) > 1 and np.linalg.norm(piece[-1] - piece[0]) >= min_len:
                out.append(piece)
            start = None
    return out


def _paths(T, name, f):
    """The feature's polylines (dense, in metres)."""
    step = max(T.cell / 2, 1.0)
    if "along" in f:
        pts = [T.address(a)[0] for a in f["along"]]
        return [_dense(pts, step)]
    if "follows" in f:
        ref = f["follows"]
        L = T.routes.get(ref) or T.lines.get(ref)
        if L is None:
            raise ValueError(f"line {name!r}: follows {ref!r}, which is no route, river or ridge")
        s0, s1 = float(f.get("from", 0.0)), float(f.get("to", 1.0))
        xy = L.xy[(L.s >= s0) & (L.s <= s1)]
        xy = _dense(xy, step)
        wr = float((T.spec.get("routes") or {}).get(ref, {}).get("width", 4.0)) if ref in T.routes else \
            float(L.props.get("floor", 6.0)) if L.kind == "river" else 4.0
        off = float(f.get("offset", wr / 2 + float(f.get("width", 2.5)) / 2 + 1.5))
        side = f.get("side", "both")
        sides = [1, -1] if side == "both" else [1 if side == "left" else -1]
        return [ndimage.gaussian_filter1d(_offset(xy, s * off), 2, axis=0) for s in sides]
    if "around" in f:
        from skimage import measure
        from . import terrain_design as design
        m = design.region(T, f["around"])
        cs = measure.find_contours(np.pad(m, 1), 0.5)
        out = []
        for c in cs:
            c = c - 1
            xy = np.stack([T.xs[0] + c[:, 1] * T.cell, T.ys[0] + c[:, 0] * T.cell], 1)
            if len(xy) > 4:
                out.append(_dense(ndimage.gaussian_filter1d(xy, 1.5, axis=0, mode="wrap"), step))
        return out
    if "network" in f:
        # (angle, jitter, pattern read at the line level too: a tester put them there and they did nothing)
        return _network(T, name, {**{k: f[k] for k in ("angle", "jitter", "pattern") if k in f}, **f["network"]})
    raise ValueError(f"line {name!r}: give \"along\" (addresses), \"follows\" (a route or river), \"around\" (a zone) "
                     f"or \"network\" ({{\"in\": zone, \"spacing\": m}})")


def apply(T):
    """Build every line: cut its pieces where it meets water, pads and routes (and its gaps), shape the ground (bank,
    ditch), and record it for cover, trees, the export and the views."""
    spec = T.spec.get("lines") or {}
    T.features = {}
    if not spec:
        return
    wet = ~np.isnan(T.water)
    slope = T._slope(ndimage.gaussian_filter(T.H, 1.0))
    pads = T.masks["sites"] > 0.3 if "sites" in T.masks else np.zeros(T.X.shape, bool)
    roads = T.masks["routes"] > 0.3 if "routes" in T.masks else np.zeros(T.X.shape, bool)
    H = T.H
    for name, f in spec.items():
        t, p = _type(name, f)
        w = float(p["width"])
        pieces = []
        import zlib
        rng = np.random.default_rng(zlib.crc32(("gates" + name).encode()))
        gaps = [T.address(g)[0] for g in f.get("gaps", [])]
        # (a line beside a route keeps to its side: only other things stop it)
        # (a line beside a route keeps to its side; one round a yard runs along the pad's edge, not stopped by it; none
        # runs over cliffs or steep faces: a wall across a valley side stood as a billboard over the drop)
        block = wet | (pads if "around" not in f else False) | \
            (roads if "follows" not in f or f["follows"] not in T.routes else False) | \
            (slope > float(f.get("max_slope", 38)))
        for xy in _paths(T, name, f):
            ok = T.sample(xy, (~ndimage.binary_dilation(block, iterations=1)).astype(float)) > 0.5
            ok &= (xy[:, 0] > T.xs[0]) & (xy[:, 0] < T.xs[-1]) & (xy[:, 1] > T.ys[0]) & (xy[:, 1] < T.ys[-1])
            for g in gaps:
                ok &= np.hypot(*(xy - g).T) > float(f.get("gap_width", 4.0)) / 2 + w / 2
            gates = f.get("gates", 110.0 if "network" in f else None)
            if gates:  # a gate every so far along it (field boundaries have them at uneven places)
                s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
                g_at = np.cumsum(float(gates) * rng.uniform(0.5, 1.5, int(s[-1] / (0.5 * float(gates))) + 2))
                gw = float(f.get("gap_width", 4.0))
                for ga in g_at[g_at < s[-1] - gw]:
                    ok &= ~((s > ga) & (s < ga + gw))
            pieces += _runs(xy, ok, min_len=max(12.0 if "network" in f else 3.0, 2 * w))
        if not pieces:
            T.warnings.append(f"line {name!r}: nothing left of it (it's all under water, pads or routes, or outside "
                              f"its zone)")
            T.features[name] = {"type": t, "pieces": [], "length": 0.0, **p}
            continue
        allp = np.vstack(pieces)
        dist = cKDTree(allp).query(T.P, distance_upper_bound=w / 2 + 4 * T.cell + 3.0)[0].reshape(T.X.shape)
        dist = np.where(np.isfinite(dist), dist, 1e9)
        core = smoothstep(w / 2 + T.cell, w / 2, dist)  # what stands on it (cover mask)
        # the ground it shapes: never a route's bed or a pad (a bank beside a lane had cut into the road and broken its
        # grade), never the water
        guard = np.clip(ndimage.gaussian_filter((roads | pads | wet).astype(float), 1.0) * 2, 0, 1)
        free = 1 - guard
        if p.get("bank"):  # an earth bank under it: rounded, a little wider than what stands on it, at least 3 cells
            half = max(w / 2 + max(1.0, 0.6 * p["bank"] / 0.35), 1.5 * T.cell)
            H = H + float(p["bank"]) * np.clip(1 - (dist / half) ** 2, 0, 1) ** 1.2 * (dist < half) * free
        if p.get("ditch"):  # a ditch: alone (type ditch), or beside it on one side
            depth = float(p["ditch"])
            if t == "ditch":
                dd = dist
                half = max(w / 2, 1.5 * T.cell)  # (a 3 m ditch on a 2 m grid was under a cell: it didn't show)
            else:
                side = p.get("ditch_side", "right")
                sgn = {"left": 1, "right": -1, "both": 0}.get(side, -1)
                half = max(1.2, 1.5 * T.cell)
                dd = np.full(T.X.shape, 1e9)
                for xy in pieces:
                    offs = [1, -1] if sgn == 0 else [sgn]
                    for s_ in offs:
                        q = _offset(xy, s_ * (w / 2 + half + 0.3))
                        dq = cKDTree(q).query(T.P, distance_upper_bound=6 + 4 * T.cell)[0].reshape(T.X.shape)
                        dd = np.minimum(dd, np.where(np.isfinite(dq), dq, 1e9))
            p["ditch_mask"] = dd < half
            H = H - depth * np.clip(1 - (dd / half) ** 2, 0, 1) ** 0.7 * (dd < half) * free
        T.features[name] = {"type": t, "pieces": pieces, "mask": core, "length":
                            float(sum(np.linalg.norm(np.diff(q, axis=0), axis=1).sum() for q in pieces)), **p}
    T.H = H


def noise_thin(xy, s, at, sp):
    """0..1 chance a hedge shrub is missing here: thin places a few tens of metres apart."""
    from . import noise
    px, py = np.interp(at, s, xy[:, 0]), np.interp(at, s, xy[:, 1])
    n = noise.fbm(np.c_[px, py, np.full(len(at), 9.0)], 25.0, 2, seed=343)
    return np.clip(2.5 * (0.42 - n), 0, 0.9)


def trees(T):
    """Shrubs along hedges and trees standing out of them / lining a treeline: (x, y, kind) rows."""
    out = []
    rng = np.random.default_rng(23)
    for name, F in getattr(T, "features", {}).items():
        for xy in F["pieces"]:
            s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
            if s[-1] < 1:
                continue
            for key, kind in (("shrubs", "shrub"), ("trees", "broadleaf")):
                sp = F.get(key)
                if not sp:
                    continue
                at = np.arange(rng.uniform(0, sp), s[-1], float(sp))
                at = at + rng.uniform(-0.3, 0.3, len(at)) * sp * (0.3 if kind == "shrub" else 1.0)
                at = np.clip(at, 0, s[-1])
                if kind == "broadleaf" and F["type"] == "hedge":
                    # standards stand out of a hedge unevenly: in clumps along some stretches, none along others
                    cand = np.arange(rng.uniform(0, sp / 3), s[-1], sp / 3)
                    from . import noise
                    px0 = np.interp(cand, s, xy[:, 0])
                    py0 = np.interp(cand, s, xy[:, 1])
                    dens = noise.fbm(np.c_[px0, py0, np.full(len(cand), 5.0)], 2.5 * sp, 2, seed=341)
                    keep = rng.random(len(cand)) < np.clip(1.8 * (dens - 0.45), 0, 1) * 0.8
                    at = cand[keep]
                elif kind == "shrub":  # a hedge has thin places and small gaps
                    thin = noise_thin(xy, s, at, sp)
                    at = at[rng.random(len(at)) > thin]
                px = np.interp(at, s, xy[:, 0])
                py = np.interp(at, s, xy[:, 1])
                jit = rng.normal(0, 0.15 * F["width"], (len(at), 2)) if kind == "shrub" else np.zeros((len(at), 2))
                for (x, y) in np.c_[px, py] + jit:
                    out.append((x, y, kind, name))
    return out


def meta(T):
    """The lines for the export: per piece its points on the ground, and what it is."""
    out = {}
    for name, F in getattr(T, "features", {}).items():
        pcs = []
        for xy in F["pieces"]:
            q = xy[:: max(1, int(round(4.0 / max(np.linalg.norm(xy[1] - xy[0]), 0.1))))] if len(xy) > 2 else xy
            if len(q) and not np.allclose(q[-1], xy[-1]):
                q = np.vstack([q, xy[-1:]])
            z = T.sample(q)
            pcs.append([[round(float(x), 2), round(float(y), 2), round(float(h), 2)] for (x, y), h in zip(q, z)])
        out[name] = {"type": F["type"], "width": F["width"], "height": F.get("height"), "bank": F.get("bank"),
                     "ditch": F.get("ditch"), "pieces": pcs}
    return out


def report(T):
    out = []
    lt = trees(T)
    for name, F in getattr(T, "features", {}).items():
        if not F["pieces"]:
            continue
        txt = f"line {name} ({F['type']}): {F['length']:.0f} m in {len(F['pieces'])} piece(s)"
        m = F["mask"] > 0.5
        for key, mm, word in (("bank", m, "its bank's crest stands"), ("ditch", F.get("ditch_mask"), "its ditch is")):
            if not F.get(key) or mm is None or not mm.any():
                continue
            # as built: the feature's own ground against the ground a few metres out either side (asked in brackets)
            ring = ndimage.binary_dilation(mm, iterations=max(2, int(4.0 / T.cell))) & \
                ~ndimage.binary_dilation(mm | m, iterations=1)
            if ring.any():  # each cell against the ring's local mean (the whole line's median mixed hill and valley)
                sg = max(1.5, 5.0 / T.cell)
                rm = ndimage.gaussian_filter(T.H * ring, sg) / np.maximum(ndimage.gaussian_filter(ring.astype(float),
                                                                                                    sg), 1e-6)
                ok = mm & (ndimage.gaussian_filter(ring.astype(float), sg) > 0.02)
                if not ok.any():
                    continue
                diff = (T.H - rm)[ok]
                rel = float(np.median(np.sort(diff)[-max(1, len(diff) // 3):]) if key == "bank" else
                            np.median(np.sort(diff)[:max(1, len(diff) // 3)]))
                txt += f", {word} {rel:+.1f} m against the ground beside it (asked {'+' if key == 'bank' else '-'}" \
                       f"{float(F[key]):.1f})"
        ns = sum(1 for tr in lt if tr[3] == name and tr[2] == "shrub")
        nt = sum(1 for tr in lt if tr[3] == name and tr[2] != "shrub")
        if ns or nt:
            txt += f", {nt} trees" + (f" and {ns} shrubs" if ns else "")
        out.append(txt)
    return out
