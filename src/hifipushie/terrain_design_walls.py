"""Walls and passes: gaps, passes, rugged ground, a wall and its check, steep runs. Part of the terrain design layer (terrain_design.py has the overview)."""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from . import noise
from .terrain import smoothstep
from .terrain_design import region

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
        sea = getattr(T, "sea", None)
        if sea is not None:  # dry land only: it had crumpled the seabed, with a seam where the zone's edge crossed the water
            R *= smoothstep(0, 3 * T.cell, sea["sd"])
        R *= ndimage.gaussian_filter(np.isnan(T.water).astype(float), 1.0) ** 2  # (nor under a lake)
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
        lumps = 0.25 * sc * (crag.reshape(T.X.shape) - 0.5) + 0.06 * sc * (fine.reshape(T.X.shape) - 0.5)
        # crags are blocks with flat faces, not round knolls and bowls: the noise cut into planes (ridged noise left a
        # round pit between every pair of crests: a pocked, melted-cheese face)
        from .terrain_rock import facets
        blocky, _ = facets(T, lumps, max(0.7 * sc, 3 * T.cell), tilt=0.25, seed=64 + k, crease=0.06)
        T.H += R * blocky
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
    if W.get("mouth") is not None:  # a valley open to a side: past the horseshoe's ends is its mouth, not a wall
        cd, beyond = W["mouth"]
        gap |= (T.X * cd[0] + T.Y * cd[1]) > beyond
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
