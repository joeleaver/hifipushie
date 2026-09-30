"""Rock character on steep ground, seen from 1-3 km: buttresses and couloirs, ledges, a boulder foot. Every cliff
(sea cliffs, basin walls, canyon walls, mesas, crater walls, scars) had come out as one smooth plaster sheet: the
builders make the right profile, nothing broke it up along its length.

"rock": {"buttresses": 0..1, "ledges": 0..1, "facets": 0..1, "bedding": 0..1, "boulders": 0..1, "aprons": 0..1,
         "scale": m} | false
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
    S = getattr(T, "sea", None)
    if S:  # stacks, talus and shore boulders are shaped already (faceting their slopes made spikes)
        keep |= S["st_mask"] | (S["rocks"] > 0.05)
    return ndimage.binary_dilation(keep, iterations=2) | ~np.isnan(T.water)


def _keep_shift(T):
    """What the faces' horizontal shift leaves alone: as _keep, but the sea's cells are shifted too (a buttress runs on
    into the water; kept, the cells at the waterline were pulled up into spires between untouched water cells)."""
    keep = _keep(T)
    lk = (getattr(T, "lakes", {}) or {}).get("sea")
    if lk is not None and hasattr(T, "lake_id"):
        sea = T.lake_id == lk["id"]
        S = getattr(T, "sea", None)
        design = np.zeros(T.X.shape, bool)
        if S:
            design |= S["st_mask"] | (S["rocks"] > 0.05)
        keep = keep & ~(sea & ~ndimage.binary_dilation(design, iterations=2))
    return keep


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


def bed_step(T):
    """Bedding's step height (m) on cliffs: six cells, so a sill is a cell or two deep (sub-cell beds were invisible)."""
    return max(2.0, 6.0 * T.cell)


def bed_offset(T, xy):
    """The beds' wander in height at points [n, 2] (m): bed k's base is at z = k * bed_step - bed_offset. Shared with
    3D rock so solid beds line up with the heightfield's sills."""
    step = bed_step(T)
    xy = np.atleast_2d(np.asarray(xy, float))
    return (noise.fbm(np.c_[xy, np.full(len(xy), 6.0)], 25 * step, 2, seed=218) - 0.5) * 0.8 * step


def params(T):
    """The rock pass's sizes for other modules (3D rock): facet size and tilt, bed step, crag size."""
    cfg = T.spec.get("rock", {}) or {}
    crag = float(cfg.get("scale", T.world["crag"])) if cfg is not False else T.world["crag"]
    return {"facet_size": max(1.2 * crag, 3.5 * T.cell), "facet_tilt": 0.35, "bed_step": bed_step(T), "crag": crag,
            "rib_spacing": max(1.5 * crag, 3.5 * T.cell), "rock_colour": [0.36, 0.34, 0.31]}


def base_colour(T, slope=None, hn=None):
    """sRGB rock before any cover: the kind's rock (sandstone in canyon/dunes/plateau country, grey elsewhere), the
    canyon's strata bands, faint level beds on cliffs."""
    slope = T._slope() if slope is None else slope
    hn = (T.H - T.H.min()) / max(np.ptp(T.H), 1) if hn is None else hn
    arid = T.world["kind"] in ("canyon", "dunes", "plateau")
    rock = (np.array([0.58, 0.38, 0.26]) if arid else np.array([0.36, 0.34, 0.31])) + 0.06 * hn[..., None]
    if arid and getattr(T, "canyons", None):
        cy = next(iter(T.canyons.values()))
        per = max(cy["depth"] / 7, 4.0)  # colour bands through the strata, level all along the canyon
        band = 0.5 + 0.5 * np.sin(2 * np.pi * T.H / per) + 0.25 * np.sin(2 * np.pi * T.H / (per * 0.37))
        rock = rock * (0.8 + 0.25 * band[..., None]) + np.array([0.08, 0.02, -0.02]) * (band[..., None] - 0.5)
    if not arid:  # beds in any cliff: faint level bands of lighter and darker rock (one grey read as a painted curtain)
        wob = noise.fbm(np.c_[T.P, np.full(len(T.P), 31.0)], 60.0, 2, seed=231).reshape(T.H.shape) - 0.5
        z = T.H + 6 * wob
        band = 0.6 * np.sin(2 * np.pi * z / 5.3) + 0.4 * np.sin(2 * np.pi * z / 2.1 + 1.0)
        rock = rock * (1 + 0.09 * band[..., None] * smoothstep(45, 60, slope)[..., None])
    return rock


def colour(T):
    """sRGB (ny, nx, 3): what the heightfield views paint on rock, for 3D rock to match: the base colour, then every
    rock-type cover layer where its mask is (in paint order), then the rock's tone (pale buttresses, dark gullies)."""
    from . import terrain_design as design
    c = base_colour(T)
    for name, m in (getattr(T, "cover", None) or {}).items():
        sc = design._spec_cover(T, name)
        if sc.get("type", name) in ("rock", "scree") or "rock" in name:
            a = np.clip(m, 0, 1)[..., None]
            c = c * (1 - a) + np.array(design.cover_colour(T, name)) * a
    tone = (getattr(T, "rock", None) or {}).get("tone")
    if tone is not None:
        c = c * tone[..., None]
    return np.clip(c, 0, 1)


def face_height(T, H, face):
    """Metres of relief the faces around each cell span (the visible ground: water counts at its level), averaged over
    the steep ground nearby; and the local top and foot (max/min over about one face height)."""
    vis = np.where(np.isnan(T.water), H, np.maximum(H, np.nan_to_num(T.water, nan=-1e9)))
    vb = ndimage.gaussian_filter(vis, 1.0)
    w = int(np.clip(min(250.0, 0.25 * T.size) / T.cell, 5, 151)) | 1
    rel = ndimage.maximum_filter(vb, w) - ndimage.minimum_filter(vb, w)
    f = face.astype(float)
    sig = max(2.0, w / 4)
    Hf = ndimage.gaussian_filter(rel * f, sig) / np.maximum(ndimage.gaussian_filter(f, sig), 1e-3)
    Hf = np.where(ndimage.gaussian_filter(f, sig) > 1e-3, Hf, 0.0)
    med = float(np.median(Hf[face])) if face.any() else 0.0
    wl = int(np.clip(1.6 * med / T.cell, 7, 151)) | 1  # (one face's top and foot: the wide window saw the hills behind)
    return Hf, ndimage.maximum_filter(vb, wl), ndimage.minimum_filter(vb, wl), med


def _structure(T, H, s, q, zone_s, face, Hf, amt):
    """The faces' big structure, before any detail: buttresses with flat fronts and V gullies a face-height or so apart
    (spacing and depth scale with the face: 20-40 m on a sea cliff, ~300 m on an alpine wall), strong in some stretches
    and slabby in others (an even texture everywhere read as crumpled paper). Returns the horizontal shift (m, + = face
    brought out) and how strongly each stretch is structured (0..1)."""
    lo = max(8 * T.cell, 20.0)
    Lb = np.clip(0.9 * Hf, lo, 320.0)
    Ab = amt * np.clip(0.17 * Hf, 1.5 * T.cell, 45.0)
    lg = np.log2(Lb / lo)
    big = np.zeros(H.shape)
    for k in range(int(math.ceil(math.log2(320.0 / lo))) + 1):
        wk = np.clip(1 - np.abs(lg - k), 0, 1) * zone_s
        if wk.max() < 1e-3:
            continue
        Lk = lo * 2 ** k
        warp = noise.fbm(np.stack([s.ravel() / (3 * Lk), q.ravel() / (12 * Lk), np.full(s.size, 7.0 + k)], 1), 1.0, 2,
                         seed=231 + k).reshape(H.shape)
        r = _chisel((s + 1.3 * Lk * (warp - 0.5)) / Lk, q / (5 * Lk), 241 + k)
        # buttress fronts are flat (the face itself, brought out), gullies V-shaped and narrower than the buttresses
        p = (np.minimum(r, 0.68) - 0.36) / 0.32
        big += wk * p
    med = float(np.median(Lb[face])) if face.any() else lo
    st = noise.fbm(np.stack([s.ravel() / (2.5 * med), q.ravel() / (6 * med), np.full(s.size, 9.0)], 1), 1.0, 2,
                   seed=251).reshape(H.shape)
    strength = 0.25 + 0.75 * smoothstep(0.35, 0.62, st)
    return Ab * strength * big, strength


def _tiers(T, H, face_w, Hf, top, foot, nx, ny, s, amt):
    """Tall cliffs step back in tiers: a ledge (grass and shrubs hold on it) and the face above set back behind it, at
    a height that wanders along the face, pinching out in places. The ground above each ledge is resampled from a
    ledge's width downhill, so the upper face and its clifftop move back whole (no bevel)."""
    ledges = np.zeros(H.shape, bool)
    rel = top - foot
    tall = smoothstep(max(10.0, 8 * T.cell), max(18.0, 14 * T.cell), Hf)
    w = ndimage.gaussian_filter(face_w * tall, 1.5)
    if w.max() < 0.3:
        return H, ledges
    fr = [0.5] if float(np.median(Hf[face_w > 0.5])) < 30 else [0.36, 0.66]
    for i, f0 in enumerate(fr):
        wan = noise.fbm(np.stack([s.ravel() / 60.0, np.full(s.size, 3.0 + i), np.zeros(s.size)], 1), 1.0, 2,
                        seed=261 + i).reshape(H.shape)
        pinch = smoothstep(0.38, 0.55, noise.fbm(np.stack([s.ravel() / 45.0, np.full(s.size, 5.0 + i),
                                                           np.zeros(s.size)], 1), 1.0, 2, seed=271 + i).reshape(H.shape))
        z_t = foot + (f0 + 0.16 * (wan - 0.5)) * rel
        D = amt * np.clip(0.12 * Hf, 2.5 * T.cell, 14.0) * pinch * w
        if D.max() < T.cell:
            continue
        yy = (T.Y - T.ys[0] - ny * D) / T.cell
        xx = (T.X - T.xs[0] - nx * D) / T.cell
        Hs = ndimage.map_coordinates(H, [yy, xx], order=1, mode="nearest")
        on = (H >= z_t) & (Hs < z_t) & (D > T.cell)
        # the ledge falls outward a little and its lip rolls (a dead-level shelf read as a road)
        new = np.where(H < z_t, H, np.where(Hs < z_t, z_t - 0.25 * (z_t - np.maximum(Hs, z_t - 0.2 * D)), Hs))
        H = np.where(D > 0.05, new, H)
        ledges |= on
    return H, ledges


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
    face = steep > 0.5
    Hf, top, foot, med_h = face_height(T, H, face)
    gullies = np.zeros(H.shape, bool)
    strength = np.ones(H.shape)
    if b_amt > 0:
        # big structure first (buttresses and gullies at the face's own scale), then ribs inside it
        Ab_med = float(np.clip(0.17 * med_h, 1.5 * T.cell, 45.0))
        sig_b = max(1.0, 0.6 * Ab_med / T.cell)
        keep_s = _keep_shift(T)
        zone_b = np.clip(1.5 * ndimage.gaussian_filter(steep, sig_b), 0, 1) * ~keep_s
        # the big structure's own frame, from ground smoothed at its scale (on the ribs' frame it turned sharply round
        # every spur and packed blades into the corner)
        sgb = float(np.clip(0.15 * np.clip(0.9 * med_h, 20, 320) / T.cell, 3, 30))
        Hbb = ndimage.gaussian_filter(H, sgb)
        byb, bxb = np.gradient(Hbb, T.cell)
        gbb = np.hypot(bxb, byb) + 1e-9
        nxb, nyb = bxb / gbb, byb / gbb
        big, strength = _structure(T, H, T.X * -nyb + T.Y * nxb, T.X * nxb + T.Y * nyb, zone_b, face, Hf, b_amt)
        # shifted along the big frame's fall line: express as the ribs' frame's shift (their directions are close)
        big = big * np.clip(nxb * nx + nyb * ny, 0, 1)
        L = max(min(1.5 * crag, 0.35 * float(np.clip(0.9 * med_h, 20, 320))), 3.5 * T.cell)  # spacing of ribs
        # ribs run the whole fall line (short blobs read as raindrops on a mountainside) and their spacing wanders
        # (evenly spaced flutes read as a comb)
        warp = noise.fbm(np.stack([s.ravel() / (3 * L), q.ravel() / (20 * L), np.full(s.size, 2.0)], 1), 1.0, 2,
                         seed=216).reshape(H.shape)
        sw = s + 1.6 * L * (warp - 0.5)
        # ribs and couloirs piecewise planar across the face: straight flanks between sharp crests and V-shaped couloirs
        # (smooth noise ribs read as melted wax dripping down every face)
        ridged = _chisel(sw / L, q / (3.5 * L), 211)
        # full strength on cliffs; a mountainside of 40-50 deg gets a third (it had raindrop dimples all over)
        # the shift is smooth across the whole face and a little past its lip and foot, and the ground is resampled, not
        # cross-faded: fading the shifted face into the unshifted by the local slope bevelled every lip and foot into a
        # 50 deg ramp (a 21 m sea cliff at 70 deg became 9 m of face under a 12 m drape)
        A0 = b_amt * max(min(0.15 * crag, 0.035 * med_h), 1.0 * T.cell)  # (detail inside the big structure)
        sig = max(1.0, 0.6 * A0 / T.cell)
        sb = ndimage.gaussian_filter(steep, sig)
        zone_s = np.clip(1.5 * sb, 0, 1) * ~keep_s
        cliffness = ndimage.gaussian_filter(steep * smoothstep(45, 65, slope), sig) / np.maximum(sb, 1e-6)
        amp = A0 * (0.35 + 0.65 * np.clip(cliffness, 0, 1))
        # (ribs vary in strength along the face: evenly fluted walls read as organ pipes)
        n3 = noise.fbm(np.stack([sw.ravel() / (2.5 * L), q.ravel() / (15 * L), np.full(s.size, 4.0)], 1), 1.0, 2,
                       seed=215).reshape(H.shape)
        delta = amp * (0.2 + 1.8 * n3 ** 1.5) * (ridged - 0.5) * (0.5 + 0.5 * strength) * zone_s  # metres, + = out
        delta = delta + big * np.maximum(zone_b, 0)
        # never sample past the crest above or the foot below: brought out past a narrow ridge's top, the ground on its far
        # side came back as saw teeth along the skyline
        gb = np.maximum(g, 0.2)
        up_room = np.maximum(top - Hb, 0) / gb
        down_room = np.maximum(Hb - foot, 0) / gb
        delta = np.clip(delta, -0.8 * down_room - T.cell, 0.7 * up_room)
        # a crest at least a couple of cells wide (a chisel knot is a point: at a cliff's foot it stood as a thin spire)
        delta = ndimage.gaussian_filter(delta, 1.2)
        gullies = (big < -0.35 * Ab_med) & face
        # sample the ground a horizontal distance delta uphill (+: higher ground brought out: a buttress)
        yy = (T.Y - T.ys[0] + ny * delta) / T.cell
        xx = (T.X - T.xs[0] + nx * delta) / T.cell
        H = ndimage.map_coordinates(H, [yy, xx], order=1, mode="nearest")

    t_amt = float(cfg.get("tiers", 1.0))
    ledge_m = np.zeros(H.shape, bool)
    if t_amt > 0:
        cl = smoothstep(52, 62, slope) * ~keep * ~walls_mask(T)
        S = getattr(T, "sea", None)
        if S:  # (sea cliffs have their tiers in their own profile: terrain_sea._cliff_face)
            cl = cl * ~((S["wc"] > 0.5) & (np.abs(S["sd"]) < 80))
        cl = ndimage.binary_dilation(cl > 0.5, iterations=2).astype(float) * ~keep
        H, ledge_m = _tiers(T, H, cl, Hf, top, foot, nx, ny, s, t_amt)

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
    facet_delta = np.zeros_like(H)  # (what the faceting moved: 3D rock takes it back out and facets in its own way)
    if f_amt > 0:
        # planar facets and joints over the faces (and rugged ground): the noise above left round pits and bubbles
        fsize = max(1.2 * crag, 3.5 * T.cell)
        w = zone.copy()
        # (rugged zones are faceted at their own scale in design.rugged: faceting them again here at the crag size,
        # tipped planes over gentle ground made 5-15 m spires on a coast's grass)
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
            facet_delta = H - before

    bd = float(cfg.get("bedding", 1.0))
    if bd > 0:
        # bedding on cliffs: the face stepped into near-vertical risers and narrow sills a cell deep, a few metres apart,
        # level along the face (a 70 deg face with nothing across it read as a curtain draped down to the water). Needs
        # a riser of several cells' height, so only where the cell is small against the step
        step = bed_step(T)  # (a sill must be a couple of cells deep: 3 m beds on a 1 m grid were sub-cell)
        dip = bed_offset(T, T.P).reshape(H.shape)
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

    ap = float(cfg.get("aprons", 1.0))
    apron_m = np.zeros(H.shape, bool)
    if ap > 0:
        # scree cones below the cliffs: fans at ~33 deg leaning on each face's foot, fed from its couloirs (in patches,
        # not a ruled ring), sized to the face above them. A face running straight down to the floor had no room below it
        # for scree or trees
        cliff = smoothstep(52, 62, slope) * ~keep > 0.5
        if cliff.sum() > 10:
            dist, (iy, ix) = ndimage.distance_transform_edt(~cliff, return_indices=True)
            dist = dist * T.cell
            reach = max(8 * crag, 60 * T.cell)
            top = ndimage.maximum_filter(Hb, size=int(2 * min(reach, 400.0) / T.cell) | 1)
            foot_h = H[iy, ix]  # the ground at the nearest cliff cell (its foot, from below)
            face_h = np.clip(top - foot_h, 0, 600)
            feed = smoothstep(0.4, 0.62, noise.fbm(np.c_[T.P, np.full(len(T.P), 12.0)], max(1.5 * crag, 6 * T.cell),
                                                   2, seed=220).reshape(H.shape))
            # fed mostly from the gullies above (cones at a couloir's foot, not a ruled ring)
            if gullies.any():
                gf = np.clip(ndimage.gaussian_filter(gullies.astype(float), 2.0) * 4, 0, 1)
                feed = np.maximum(0.5 * feed, gf)
            # concave: steepest at the apex, easing out over its toe (a straight 33 deg cone read as a pale tent)
            hc = np.minimum(0.16 * face_h, 28.0) * feed[iy, ix]
            run_c = np.maximum(hc, 1e-6) / math.tan(math.radians(33))
            u = np.clip(dist / (1.35 * run_c), 0, 1)
            cone = np.where(u < 1, foot_h + hc * (1 - u) ** 1.6 - 0.02 * dist, -np.inf)  # (past its toe: nothing)
            lower = (H < foot_h + 0.5) & ~cliff & ~keep & (slope < 40) & np.isnan(T.water) & ~walls_mask(T)
            add = np.where(lower, np.clip(cone - H, 0, None), 0) * ap
            add = ndimage.gaussian_filter(add, 2.5)  # (at 1 cell the patches' edges stood as sugar-cube blocks)
            H = H + add
            apron_m = add > 0.5
    T.H = H
    # ledges: flat ground a few cells wide among the cliffs (tiers, sea cliffs' ledges, benches) as built
    gy2, gx2 = np.gradient(H, T.cell)
    sl = np.degrees(np.arctan(np.hypot(gx2, gy2)))
    cliffy = ndimage.binary_dilation(sl > 60, iterations=3)
    ledge_m = (ledge_m | ((sl < 32) & cliffy & ndimage.binary_erosion(ndimage.binary_dilation(sl > 60, iterations=6),
                                                                       iterations=2))) & ~keep
    # the rock's tone (views and the map): buttress fronts pale, gullies dark and streaked down the fall line, big
    # patches of lighter and darker rock (one even grey on every face read as a plaster drape)
    patch = noise.fbm(np.c_[T.P, np.full(len(T.P), 14.0)], max(3 * crag, 12 * T.cell), 2, seed=281).reshape(H.shape)
    streak = _chisel(s / max(2.5 * T.cell, 0.12 * crag), q / max(40 * T.cell, 3 * crag), 283)
    gsoft = np.clip(ndimage.gaussian_filter(gullies.astype(float), 2.0) * 3, 0, 1)
    tone = (0.72 + 0.5 * smoothstep(0.3, 0.7, patch)) * (1 - 0.35 * gsoft) * (0.84 + 0.22 * streak)
    T.H = H
    T.rock = {"cells": int((steep > 0.5).sum()), "foot": foot_m | apron_m, "aprons": apron_m, "ledges": ledge_m,
              "gullies": gullies, "face_height": med_h, "tone": tone, "facet_delta": facet_delta}


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
    # (across the whole face: beds and sills under 60 deg cut the cliff mask into strips 2 cells wide at any cell)
    cl = ndimage.binary_closing(cliff, iterations=3) & np.isnan(T.water)
    across = float(np.median(2 * ndimage.distance_transform_edt(cl)[cl])) if cl.sum() > 20 else None
    # closed hollows on the faces (round pits: water would pool on a cliff) and how rounded the faces are (median
    # |laplacian| x cell: planar facets with creases are low, noise lumps high)
    from skimage.morphology import reconstruction
    seed = T.H.copy()
    seed[1:-1, 1:-1] = T.H.max()
    pit = (reconstruction(seed, T.H, method="erosion") - T.H) > max(0.5, 0.1 * T.cell)  # (deeper than half a metre)
    S = getattr(T, "sea", None)
    rubble = (S["st_mask"] | (S["rocks"] > 0.05)) if S else np.zeros(T.X.shape, bool)  # (gaps between blocks aren't pits)
    _, n_pits = ndimage.label(pit & face & ~rubble)
    lap = np.abs(ndimage.laplace(T.H))[face] / T.cell
    return {"face_km2": face.sum() * T.cell ** 2 / 1e6, "turned": float((d[face] > math.radians(25)).mean()),
            "cliff_cells": across, "pits_km2": n_pits / max(face.sum() * T.cell ** 2 / 1e6, 1e-9),
            "rounded": float(np.median(lap)),
            "aprons": ((getattr(T, "rock", {}) or {}).get("aprons", np.zeros(1, bool)).sum() * T.cell ** 2 / 1e4)}
