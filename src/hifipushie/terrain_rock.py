"""Rock character on steep ground, seen from 1-3 km: buttresses and couloirs, ledges, a boulder foot. Every cliff
(sea cliffs, basin walls, canyon walls, mesas, crater walls, scars) had come out as one smooth plaster sheet: the
builders make the right profile, nothing broke it up along its length.

"rock": {"buttresses": 0..1, "ledges": 0..1, "boulders": 0..1, "scale": m} | false
  (defaults 1, 0.6, 1, the kind's crag size). Applied after erosion (it smeared this detail) to ground steeper than
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
    return ndimage.binary_dilation(keep, iterations=2) | ~np.isnan(T.water)


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
    zone = ndimage.gaussian_filter(steep, 1.5)  # (reaching the lip and the foot, so they notch too)
    zone = np.maximum(zone, steep) * ~keep

    b_amt = float(cfg.get("buttresses", 1.0))
    if b_amt > 0:
        L = max(1.5 * crag, 3.5 * T.cell)  # spacing of ribs along the face
        pts = np.stack([s.ravel() / L, q.ravel() / (4 * L), np.full(s.size, 7.0)], 1)
        n1 = noise.fbm(pts, 1.0, 3, seed=211).reshape(H.shape)
        ridged = 1 - np.sqrt((2 * n1 - 1) ** 2 + 0.03)  # crests: buttresses (softened: sharp ones faceted); lows: couloirs
        # big bays and headlands of the face every few ribs
        pts2 = np.stack([s.ravel() / (5 * L), q.ravel() / (8 * L), np.full(s.size, 3.0)], 1)
        n2 = noise.fbm(pts2, 1.0, 2, seed=212).reshape(H.shape)
        amp = b_amt * max(0.4 * crag, 1.0 * T.cell)
        # (ribs vary in strength along the face: evenly fluted walls read as organ pipes)
        n3 = noise.fbm(np.stack([s.ravel() / (2.5 * L), q.ravel() / (6 * L), np.full(s.size, 4.0)], 1), 1.0, 2,
                       seed=215).reshape(H.shape)
        delta = amp * ((0.4 + 1.6 * n3) * (ridged - 0.5) + 1.6 * (n2 - 0.5))  # metres, + = face out (a buttress)
        # sample the ground a horizontal distance delta uphill (+: higher ground brought out: a buttress)
        yy = (T.Y - T.ys[0] + ny * delta * zone) / T.cell
        xx = (T.X - T.xs[0] + nx * delta * zone) / T.cell
        shifted = ndimage.map_coordinates(H, [yy, xx], order=1, mode="nearest")
        H = H * (1 - zone) + shifted * zone

    l_amt = float(cfg.get("ledges", 0.6))
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

    bo = float(cfg.get("boulders", 1.0))
    foot_m = np.zeros(H.shape, bool)
    if bo > 0:
        # below each face: blocky lumps on the gentler ground within a few cells (talus and fallen blocks)
        cliff = steep > 0.5
        near = ndimage.distance_transform_edt(~cliff) * T.cell
        below = Hb < ndimage.maximum_filter(Hb, size=5)  # (not the ground on top of the face)
        foot = smoothstep(6 * T.cell + 0.5 * crag, 1 * T.cell, near) * (slope < 40) * below * ~keep
        lumps = noise.fbm(np.c_[T.P, np.full(len(T.P), 9.0)], 1.3 * T.cell, 2, seed=214).reshape(H.shape)
        H = H + bo * foot * np.clip(lumps - 0.45, 0, None) * min(0.25 * crag, 3.0) * 2
        foot_m = foot > 0.3
    T.H = H
    T.rock = {"cells": int((steep > 0.5).sum()), "foot": foot_m}


def measure(T):
    """How broken the faces are, as built: along each face, how far its lip wanders in and out (the spread of the
    lip line across the fall line), and the share of face cells whose aspect differs from the face's mean by > 25 deg
    (buttress and couloir sides)."""
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
    return {"face_km2": face.sum() * T.cell ** 2 / 1e6, "turned": float((d[face] > math.radians(25)).mean())}
