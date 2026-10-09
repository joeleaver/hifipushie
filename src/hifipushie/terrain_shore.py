"""Shores of still water for the 3D tiles: lake margins and sea beaches, with the stream beds' machinery
(terrain_stream; pushieworld note 110's last line: "same question for the lake shore and the beach (driftwood,
pebbles, wrack line)").

- Lakes (not the sea): `still_waters` gives each lake's wet cells and level; terrain_stream.Streams adds them to its
  grids as still water (energy 0, no pools / riffles / bars / cut banks, no bed shape): the shallows' bed is gravel
  near the water's edge and silt further in, the shore's foot damp; clutter: reeds and sedge along the margin,
  cobble patches at the water line, a few rounded rocks, a little driftwood and litter.
- Sea beaches: `beach_clutter`: where the tiles paint sand above the water near the coast: `pebbles` (a patch of
  beach pebbles: on the shingle patches up the beach and thinly lower down), `wrack` (a strip of weed and drift lying
  along the high water mark, where terrain_ground.tint paints the wrack line), `driftwood` (logs above the wrack
  line, lying along the shore). Rows as terrain_stream.clutter's, place "shore"."""

from __future__ import annotations

import numpy as np
from scipy import ndimage

from . import noise

KINDS = {  # (added to terrain_stream.KINDS for the csv and the manifest)
    "pebbles": {"scale": [0.6, 1.6], "squash": [0.7, 1.2], "what": "a patch of beach pebbles and shell (flatter and "
                "smaller stones than `cobbles`)"},
    "wrack": {"scale": [1.0, 3.0], "squash": [1.0, 1.0], "what": "a strip of seaweed and drift at the high water mark; "
              "yaw = its long axis (0 = along world +x)"},
}
SPACING = {"pebbles": 1.1, "wrack": 1.6, "driftwood": 3.0}


def _ss(e0, e1, x):
    u = np.clip((x - e0) / (e1 - e0), 0, 1)
    return u * u * (3 - 2 * u)


def still_waters(T):
    """[(name, wet mask, level)] for every lake with water that is not the sea."""
    out = []
    lid = getattr(T, "lake_id", None)
    if lid is None:
        return out
    wet = ~np.isnan(T.water)
    for name, lk in (getattr(T, "lakes", None) or {}).items():
        if lk.get("sea") or not lk.get("area", 1) or "id" not in lk:
            continue
        m = wet & (lid == lk["id"])
        if m.sum() >= 4:
            out.append((name, m, float(lk["level"])))
    return out


def signed_distance(mask, cell, far):
    """Metres to a wet mask's edge on its own grid (negative inside), smoothed a little, capped at +-far."""
    if mask.all() or not mask.any():
        return np.full(mask.shape, -far if mask.all() else far)
    sd = np.where(mask, -(ndimage.distance_transform_edt(mask) - 0.5), ndimage.distance_transform_edt(~mask) - 0.5) * cell
    return np.clip(ndimage.gaussian_filter(sd, 0.8), -far, far)


def beach_clutter(T, mats, field, kinds, box=None, seed=17, density=1.0):
    """Sea beach clutter rows [x, y, z, kind index (into `kinds`, a list of names), scale, yaw, squash, place index,
    river index -1]: pebbles, wrack, driftwood where the maps paint sand above the sea near the coast. place =
    PLACES.index("shore") is filled by the caller's `place` value 5."""
    empty = np.zeros((0, 9))
    g = getattr(mats, "ground", None)
    if mats.sea is None or g is None or g.sea_d is None or "sand" not in mats.layers or density <= 0:
        return empty
    sea = float(mats.sea)
    c = float(T.cell)
    H = field.H if hasattr(field, "H") else T.H
    cand = (np.asarray(g.sea_d) < 90.0) & (np.asarray(g.sea_d) > -5.0) & (H > sea - 0.3) & (H < sea + 4.5)
    if not cand.any():
        return empty
    cand = ndimage.binary_dilation(cand, iterations=1)
    x0, y0 = float(T.xs[0]), float(T.ys[0])
    iy, ix = np.nonzero(cand)
    bx0, bx1, by0, by1 = x0 + ix.min() * c, x0 + ix.max() * c, y0 + iy.min() * c, y0 + iy.max() * c
    if box is not None:
        (a0, b0), (a1, b1) = box
        bx0, bx1, by0, by1 = max(bx0, a0), min(bx1, a1), max(by0, b0), min(by1, b1)
    if bx1 <= bx0 or by1 <= by0:
        return empty
    out = []
    isand = mats.layers.index("sand")
    for kind in ("pebbles", "wrack", "driftwood"):
        ki = kinds.index(kind)
        sp = SPACING[kind]
        xs = np.arange(np.floor(bx0 / sp) - 1, np.ceil(bx1 / sp) + 2) * sp
        for r0 in range(0, len(np.arange(np.floor(by0 / sp) - 1, np.ceil(by1 / sp) + 2)), 400):  # (in strips)
            ys = (np.arange(np.floor(by0 / sp) - 1, np.ceil(by1 / sp) + 2) * sp)[r0:r0 + 400]
            gx, gy = np.meshgrid(xs, ys)
            xy = np.c_[gx.ravel(), gy.ravel()]
            jj = np.clip(np.rint((xy[:, 1] - y0) / c).astype(int), 0, cand.shape[0] - 1)
            ii = np.clip(np.rint((xy[:, 0] - x0) / c).astype(int), 0, cand.shape[1] - 1)
            xy = xy[cand[jj, ii]]
            if not len(xy):
                continue
            h3 = lambda a, q=xy: noise._hash(np.rint(q[:, 0] / sp).astype(np.int64), np.rint(q[:, 1] / sp).astype(np.int64),
                                             np.full(len(q), a, np.int64), seed + 7 * ki)
            u_keep, u_a, u_b, u_c = h3(3), h3(4), h3(5), h3(6)
            xy = xy + (np.c_[h3(1), h3(2)] - 0.5) * 0.9 * sp
            ok = (xy[:, 0] >= bx0) & (xy[:, 0] < bx1) & (xy[:, 1] >= by0) & (xy[:, 1] < by1)
            xy, u_keep, u_a, u_b, u_c = xy[ok], u_keep[ok], u_a[ok], u_b[ok], u_c[ok]
            if not len(xy):
                continue
            h, cs = field.column(np.ascontiguousarray(xy[:, 0]), np.ascontiguousarray(xy[:, 1]))
            P = np.c_[xy, h]
            n = len(P)
            W, _ = mats.weights(P, np.tile([0.0, 0.0, 1.0], (n, 1)))
            sand = np.asarray(W[:, isand], float) * (cs > 0.85)
            for m_ in ("routes", "sites"):
                if m_ in T.masks:
                    sand = sand * (mats._grid(np.asarray(T.masks[m_], float), xy) < 0.2)
            Pf = np.c_[xy, np.zeros(n)]
            z = h - sea
            wv = 0.35 * (noise.fbm(Pf, 7.0, 2, seed=641) - 0.5)  # (terrain_ground.tint's own wander of the tide lines)
            # the shore's direction: along the contours of the distance to the sea
            e = 1.5
            dx = mats._grid(g.sea_d, xy + [e, 0]) - mats._grid(g.sea_d, xy - [e, 0])
            dy = mats._grid(g.sea_d, xy + [0, e]) - mats._grid(g.sea_d, xy - [0, e])
            along = np.degrees(np.arctan2(dx, -dy))
            lo, hi = (KINDS[kind] if kind in KINDS else {"scale": [0.8, 4.5]})["scale"]
            squash = np.ones(n)
            if kind == "pebbles":
                shg = _ss(0.55, 0.72, noise.fbm(Pf, 4.0, 3, seed=645)) * _ss(1.4, 2.4, z)  # (tint's shingle patches)
                p = sand * (0.5 * shg + 0.05 * _ss(0.3, 0.9, z)) * (z > 0.15)
                scale = lo + (hi - lo) * u_a ** 1.5
                yaw = 360 * u_b
                squash = 0.7 + 0.5 * u_c
            elif kind == "wrack":
                p = sand * 0.55 * np.exp(-((z - 1.25 - 1.5 * wv) / 0.16) ** 2) * \
                    _ss(0.4, 0.62, noise.fbm(Pf, 1.6, 3, seed=642))
                scale = lo + (hi - lo) * u_a
                yaw = along + 30 * (u_b - 0.5)
            else:
                p = sand * 0.05 * _ss(1.2, 1.7, z + 1.5 * wv) * _ss(3.4, 2.4, z) * \
                    (0.3 + 1.4 * _ss(0.5, 0.7, noise.fbm(Pf, 14.0, 2, seed=646)))
                scale = np.clip(1.8 * np.exp(0.5 * (4.91 * (np.clip(u_a, 1e-4, 1 - 1e-4) ** 0.14 -
                                                          (1 - np.clip(u_a, 1e-4, 1 - 1e-4)) ** 0.14))), 0.8, 4.5)
                yaw = along + 50 * (u_b - 0.5)
                squash = 0.8 + 0.6 * u_c
            keep = u_keep < np.clip(p * density, 0, 1)
            if keep.any():
                k = int(keep.sum())
                out.append(np.c_[P[keep], np.full(k, ki), scale[keep], np.mod(yaw[keep], 360.0), squash[keep],
                                 np.full(k, 5), np.full(k, -1)])
    return np.concatenate(out) if out else empty
