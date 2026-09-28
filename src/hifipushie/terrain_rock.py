"""Rock character on steep ground, seen from 1-3 km: buttresses and couloirs, ledges, a boulder foot. Every cliff
(sea cliffs, basin walls, canyon walls, mesas, crater walls, scars) had come out as one smooth plaster sheet: the
builders make the right profile, nothing broke it up along its length.

"rock": {"buttresses": 0..1, "ledges": 0..1, "facets": 0..1, "boulders": 0..1, "scale": m} | false
  (defaults 1, 0.25, 1, the kind's crag size). Applied after erosion (it smeared this detail) to ground steeper than
  ~40 deg, never on routes, sites or water.

A height field can't overhang, and a 70 deg face on a 5 m grid is only a few cells across in plan, so what reads from
afar has to vary ALONG the face: buttresses and couloirs are the face moved horizontally in and out (the profile down
the fall line is kept, so a wall stays as steep and tall), which also notches its lip and its foot. Ledges are the
heights pulled toward a staircase (treads and risers) where the face is gentle enough for a tread to be a cell wide.
The boulder foot is lumpy ground below each face.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from . import noise
from .terrain import smoothstep


def _keep(T):
    keep = np.zeros(T.X.shape, bool)
    for k in ("routes", "sites"):
        if k in T.masks:
            keep |= T.masks[k] > 0.05
    for p in T.passes.values():
        keep |= p["corridor"]
    for pf in getattr(T, "peak_forms", {}).values():  # (a peak's arêtes stay clean edges: rock lumps made its skyline a saw)
        keep |= pf["crest"]
    return ndimage.binary_dilation(keep, iterations=2) | ~np.isnan(T.water)


def _chisel(u, v, seed):
    """0..1, piecewise linear in u (knots at the integers, alternating crest and trough, each its own height), the knots
    changing slowly with v (blended between two knot sets): straight flanks, sharp crests, V troughs."""
    def row(vk):
        k = np.floor(u)
        f = u - k
        ki = k.astype(np.int64)
        h0 = noise._hash(ki, vk, np.zeros_like(ki), seed)
        h1 = noise._hash(ki + 1, vk, np.zeros_like(ki), seed)
        par = (ki % 2 == 0)
        a = np.where(par, 0.55 + 0.45 * h0, 0.45 * h0)  # even knots crests, odd troughs
        b = np.where(par, 0.45 * h1, 0.55 + 0.45 * h1)
        return a + (b - a) * f
    vk = np.floor(v).astype(np.int64)
    t = v - np.floor(v)
    t = t * t * (3 - 2 * t)
    return row(vk) * (1 - t) + row(vk + 1) * t


def facets(T, H, size, tilt=0.12, seed=0, crease=0.18):
    """The ground broken into planar facets: jittered cells `size` across, each the plane fitted to the ground over it
    (least squares), tipped a little at random (`tilt`, as a slope), blended with its nearest neighbour's plane only in
    a narrow band at the border (`crease`, a share of the size): creases and small risers between planes. Keeps the
    large form (each plane is the ground's own) and replaces round lumps with flat faces and joints (noise lumps read
    as melted wax and bubbles on rock)."""
    from scipy.spatial import cKDTree
    rng = np.random.default_rng(seed)
    x0, y0 = T.xs[0] - size, T.ys[0] - size
    gx_, gy_ = np.meshgrid(np.arange(x0, T.xs[-1] + 2 * size, size), np.arange(y0, T.ys[-1] + 2 * size, size))
    seeds = np.c_[gx_.ravel(), gy_.ravel()] + rng.uniform(-0.45, 0.45, (gx_.size, 2)) * size
    # stretched cells: facets and joints have a grain (strike), not honeycomb
    ang = rng.uniform(0, np.pi)
    R = np.array([[math.cos(ang), -math.sin(ang)], [math.sin(ang), math.cos(ang)]]) @ np.diag([1.0, 0.6])
    tree = cKDTree(seeds @ R.T)
    d, idx = tree.query(T.P @ R.T, k=2)
    x, y, z = T.P[:, 0], T.P[:, 1], H.ravel()
    n = len(seeds)
    i1 = idx[:, 0]
    cx, cy = seeds[:, 0], seeds[:, 1]
    dx, dy = x - cx[i1], y - cy[i1]

    def s(v):
        return np.bincount(i1, v, minlength=n)
    S1, Sx, Sy, Sz = s(np.ones_like(x)), s(dx), s(dy), s(z)
    Sxx, Sxy, Syy, Sxz, Syz = s(dx * dx), s(dx * dy), s(dy * dy), s(dx * z), s(dy * z)
    A = np.stack([np.stack([Sxx, Sxy, Sx], -1), np.stack([Sxy, Syy, Sy], -1), np.stack([Sx, Sy, S1], -1)], -2)
    b = np.stack([Sxz, Syz, Sz], -1)
    ok = S1 >= 6
    A[~ok] = np.eye(3)
    b[~ok] = 0
    A = A + np.eye(3) * 1e-6 * size ** 2
    coef = np.linalg.solve(A, b[..., None])[..., 0]  # z = a dx + b dy + c, per cell
    fit = coef[i1, 0] * dx + coef[i1, 1] * dy + coef[i1, 2]  # (before the tip below)
    rms = np.sqrt(np.bincount(i1, (z - fit) ** 2, minlength=n) / np.maximum(S1, 1))
    coef[:, :2] += rng.normal(0, tilt, (n, 2))
    coef[:, 2] += rng.normal(0, 0.15 * tilt * size, n)

    def plane(i):
        return coef[i, 0] * (x - cx[i]) + coef[i, 1] * (y - cy[i]) + coef[i, 2]
    p1, p2 = plane(idx[:, 0]), plane(idx[:, 1])
    w2 = 0.5 * smoothstep(crease * size, 0, d[:, 1] - d[:, 0])
    good = ok[idx[:, 0]] & ok[idx[:, 1]]
    out = np.where(good, (1 - w2) * p1 + w2 * p2, z)
    # a cell that isn't near a plane (a small cliff with its top and foot in one cell) is left alone: its plane was the
    # average, a 50 deg ramp through a 70 deg face
    keep = np.exp(-(((1 - w2) * rms[idx[:, 0]] + w2 * rms[idx[:, 1]]) / (0.1 * size)) ** 2)
    return out.reshape(H.shape), keep.reshape(H.shape)


def walls_mask(T):
    """Designed unclimbable walls (a basin's, a "walls" edge): ledges would break their tall steep run."""
    m = np.zeros(T.X.shape, bool)
    for b in getattr(T, "basins", {}).values():
        m |= b["wall"]
    for w in T.walls.values():
        if w.get("basin"):
            continue
        out = ndimage.distance_transform_edt(~(w["inside"] > 0.5)) * T.cell
        m |= (out > 0) & (out < 1.5 * w["band"] + 3 * T.cell)
    return m


def apply(T):
    cfg = T.spec.get("rock", {})
    if cfg is False:
        return
    cfg = cfg or {}
    crag = float(cfg.get("scale", T.world["crag"]))
    H = T.H
    Hs = ndimage.gaussian_filter(H, 1.0)
    gy, gx = np.gradient(Hs, T.cell)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    keep = _keep(T)
    steep = smoothstep(36, 50, slope) * ~keep
    if steep.max() < 0.5:
        T.rock = {"cells": 0}
        return
    # the face's frame: downslope from heavily smoothed ground (coherent along a face, not cell to cell)
    Hb = ndimage.gaussian_filter(H, 3.0)
    by, bx = np.gradient(Hb, T.cell)
    g = np.hypot(bx, by) + 1e-9
    nx, ny = bx / g, by / g  # uphill
    s = T.X * -ny + T.Y * nx  # along the face (strike)
    q = T.X * nx + T.Y * ny  # up and down it
    # reaching the lip and the foot so they notch too, but not the flat top behind the lip (resampling it along the
    # fall line dug box-shaped pits into the clifftop grass)
    zone = np.maximum(ndimage.gaussian_filter(steep, 1.0), steep) * smoothstep(18, 32, slope) * ~keep

    b_amt = float(cfg.get("buttresses", 1.0))
    if b_amt > 0:
        L = max(1.5 * crag, 3.5 * T.cell)  # spacing of ribs along the face
        # ribs run the whole fall line (short blobs read as raindrops on a mountainside) and their spacing wanders
        # (evenly spaced flutes read as a comb)
        warp = noise.fbm(np.stack([s.ravel() / (3 * L), q.ravel() / (20 * L), np.full(s.size, 2.0)], 1), 1.0, 2,
                         seed=216).reshape(H.shape)
        sw = s + 1.6 * L * (warp - 0.5)
        # ribs and couloirs piecewise planar across the face: straight flanks between sharp crests and V-shaped couloirs
        # (smooth noise ribs read as melted wax dripping down every face)
        ridged = _chisel(sw / L, q / (10 * L), 211)
        # big bays and headlands of the face every few ribs
        pts2 = np.stack([s.ravel() / (5 * L), q.ravel() / (20 * L), np.full(s.size, 3.0)], 1)
        n2 = noise.fbm(pts2, 1.0, 2, seed=212).reshape(H.shape)
        # full strength on cliffs; a mountainside of 40-50 deg gets a third (it had raindrop dimples all over)
        # the shift is smooth across the whole face and a little past its lip and foot, and the ground is resampled, not
        # cross-faded: fading the shifted face into the unshifted by the local slope bevelled every lip and foot into a
        # 50 deg ramp (a 21 m sea cliff at 70 deg became 9 m of face under a 12 m drape)
        A0 = b_amt * max(0.4 * crag, 1.0 * T.cell)
        sig = max(1.0, 0.6 * A0 / T.cell)
        sb = ndimage.gaussian_filter(steep, sig)
        zone_s = np.clip(1.5 * sb, 0, 1) * ~keep
        cliffness = ndimage.gaussian_filter(steep * smoothstep(45, 65, slope), sig) / np.maximum(sb, 1e-6)
        amp = A0 * (0.35 + 0.65 * np.clip(cliffness, 0, 1))
        # (ribs vary in strength along the face: evenly fluted walls read as organ pipes)
        n3 = noise.fbm(np.stack([sw.ravel() / (2.5 * L), q.ravel() / (15 * L), np.full(s.size, 4.0)], 1), 1.0, 2,
                       seed=215).reshape(H.shape)
        delta = amp * ((0.2 + 1.8 * n3 ** 1.5) * (ridged - 0.5) + 1.6 * (n2 - 0.5))  # metres, + = face out
        # sample the ground a horizontal distance delta uphill (+: higher ground brought out: a buttress)
        yy = (T.Y - T.ys[0] + ny * delta * zone_s) / T.cell
        xx = (T.X - T.xs[0] + nx * delta * zone_s) / T.cell
        H = ndimage.map_coordinates(H, [yy, xx], order=1, mode="nearest")

    l_amt = float(cfg.get("ledges", 0.25))
    if l_amt > 0:
        # a tread needs a cell or two of run: only faces gentle enough get ledges; risers in between steepen
        step = max(0.6 * crag, 2.5 * T.cell)
        dip = (noise.fbm(np.c_[T.P, np.full(len(T.P), 5.0)], 20 * step, 2, seed=213).reshape(H.shape) - 0.5) * step
        z = (H + dip) / step
        k = np.floor(z)
        fr = z - k
        stair = (k + smoothstep(0.55, 1.0, fr)) * step - dip  # a level tread, then a riser
        can = smoothstep(62, 50, slope) * smoothstep(34, 42, slope)
        w = l_amt * 0.6 * can * zone * ~walls_mask(T)
        H = H * (1 - w) + stair * w

    f_amt = float(cfg.get("facets", 1.0))
    if f_amt > 0:
        # planar facets and joints over the faces (and rugged ground): the noise above left round pits and bubbles
        fsize = max(1.2 * crag, 3.5 * T.cell)
        w = zone.copy()
        for rz, (m, sc) in getattr(T, "rugged_zones", {}).items():
            w = np.maximum(w, ndimage.gaussian_filter(m.astype(float), 1.0) * smoothstep(12, 25, slope) * ~keep)
        w = np.clip(f_amt * w, 0, 1)
        if w.max() > 0.05:
            before = H
            fz, planar = facets(T, H, fsize, tilt=0.35, seed=217, crease=0.08)
            w = w * planar
            H = H * (1 - w) + fz * w
            # tipped planes meeting can close small hollows on a face (pits: 9 -> 56 per km2 on b2_alps' cliffs): fill
            # the ones the faceting made (a designed hollow was there before and stays)
            from skimage.morphology import reconstruction
            seed_ = H.copy()
            seed_[1:-1, 1:-1] = H.max()
            fill = reconstruction(seed_, H, method="erosion") - H
            seed_b = before.copy()
            seed_b[1:-1, 1:-1] = before.max()
            was = reconstruction(seed_b, before, method="erosion") - before
            H = H + np.where((w > 0.05) & (fill > was + 0.05) & (fill < 0.3 * fsize), fill - was, 0)

    bd = float(cfg.get("bedding", 1.0))
    if bd > 0:
        # bedding on cliffs: the face stepped into near-vertical risers and narrow sills a cell deep, a few metres apart,
        # level along the face (a 70 deg face with nothing across it read as a curtain draped down to the water). Needs
        # a riser of several cells' height, so only where the cell is small against the step
        step = max(2.0, 6.0 * T.cell)  # (a sill must be a couple of cells deep: 3 m beds on a 1 m grid were sub-cell)
        dip = (noise.fbm(np.c_[T.P, np.full(len(T.P), 6.0)], 25 * step, 2, seed=218).reshape(H.shape) - 0.5) * 0.8 * step
        th = noise.fbm(np.c_[T.P, np.full(len(T.P), 8.0)], 6 * step, 2, seed=219).reshape(H.shape)  # beds come and go
        z = (H + dip) / step
        k = np.floor(z)
        stair = (k + smoothstep(0.45, 1.0, z - k)) * step - dip
        w = bd * 0.9 * smoothstep(55, 68, slope) * zone * smoothstep(0.42, 0.52, th) * ~walls_mask(T)
        H = H * (1 - w) + stair * w

    bo = float(cfg.get("boulders", 1.0))
    foot_m = np.zeros(H.shape, bool)
    if bo > 0:
        # below each face: blocky lumps on the gentler ground within a few cells (talus and fallen blocks)
        cliff = steep > 0.5
        near = ndimage.distance_transform_edt(~cliff) * T.cell
        # (well below the face's top, not the ground on top of it: "below the max nearby" held on any slope, and a plateau
        # rim came out pockmarked)
        below = Hb < ndimage.maximum_filter(Hb, size=7) - max(0.5 * crag, 2 * T.cell)
        foot = smoothstep(6 * T.cell + 0.5 * crag, 1 * T.cell, near) * smoothstep(34, 26, slope) * below * ~keep
        lumps = noise.fbm(np.c_[T.P, np.full(len(T.P), 9.0)], 1.3 * T.cell, 2, seed=214).reshape(H.shape)
        H = H + bo * foot * np.clip(lumps - 0.45, 0, None) * min(0.25 * crag, 3.0) * 2
        foot_m = foot > 0.3
    T.H = H
    T.rock = {"cells": int((steep > 0.5).sum()), "foot": foot_m}


def measure(T):
    """How broken the faces are, as built: the share of face cells whose aspect differs from the face's mean by > 25 deg
    (buttress and couloir sides), and how many cells across (in plan) the cliffs over 60 deg are: a face 2-3 cells
    across can't carry detail of its own (it rendered as big flat triangles)."""
    slope = T._slope()
    face = (slope > 45) & np.isnan(T.water)
    if face.sum() < 20:
        return None
    gy, gx = np.gradient(T.H, T.cell)
    asp = np.arctan2(gy, gx)
    Hb = ndimage.gaussian_filter(T.H, 4.0)
    by, bx = np.gradient(Hb, T.cell)
    mean = np.arctan2(by, bx)
    d = np.abs((asp - mean + np.pi) % (2 * np.pi) - np.pi)
    cliff = (slope > 60) & np.isnan(T.water)
    across = float(np.median(2 * ndimage.distance_transform_edt(cliff)[cliff])) if cliff.sum() > 20 else None
    # closed hollows on the faces (round pits: water would pool on a cliff) and how rounded the faces are (median
    # |laplacian| x cell: planar facets with creases are low, noise lumps high)
    from skimage.morphology import reconstruction
    seed = T.H.copy()
    seed[1:-1, 1:-1] = T.H.max()
    pit = (reconstruction(seed, T.H, method="erosion") - T.H) > max(0.5, 0.1 * T.cell)  # (deeper than half a metre)
    _, n_pits = ndimage.label(pit & face)
    lap = np.abs(ndimage.laplace(T.H))[face] / T.cell
    return {"face_km2": face.sum() * T.cell ** 2 / 1e6, "turned": float((d[face] > math.radians(25)).mean()),
            "cliff_cells": across, "pits_km2": n_pits / max(face.sum() * T.cell ** 2 / 1e6, 1e-9),
            "rounded": float(np.median(lap))}
