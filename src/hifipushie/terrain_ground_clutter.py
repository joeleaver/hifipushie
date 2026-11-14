"""Ground clutter: placeholder instances and the strips they stand in. Part of the terrain's ground (terrain_ground.py has the overview)."""
from __future__ import annotations

import numpy as np

from . import terrain_ground
from . import noise
from .terrain_ground import _ss

def clutter(T, mats, field, kinds=("bush", "boulder"), box=None, near=None, seed=7):
    """Ground clutter as instances [[x, y, z, kind index, scale, yaw, squash]] (kind index into `kinds`; squash: the
    height's share of the scale), from the same masks the maps paint: bushes on the scrub's clumps (kept back from
    cliff lips, low and wind-shorn near them), tussocks in rough grass, tall grass filling in round the eye (near
    only), boulders in clusters on rock (the splash zone, rock breaking through near lips; never on sand, sunk a
    little). Engines would scatter these from the layer weights with their own detail system; this is the placement
    and the reference density. box: [[x0, y0], [x1, y1]]; near: (points (n, 2+), radius) keeps only samples within
    radius of any point (render views). Steep ground, water, routes and sites are left bare."""
    if mats.ground is None:
        return np.zeros((0, 7))
    (x0, y0), (x1, y1) = box or T.spec["extent"]
    out = []
    for ki, kind in enumerate(kinds):
        sp = terrain_ground.CLUTTER[kind]
        if kind in terrain_ground.CLUTTER_NEAR:  # (each eye's own small box)
            if near is None:
                continue
            r = min(float(near[1]), terrain_ground.CLUTTER_NEAR[kind])
            for ei, e in enumerate(np.asarray(near[0], float)):
                bx0, by0 = max(x0, e[0] - r), max(y0, e[1] - r)
                bx1, by1 = min(x1, e[0] + r), min(y1, e[1] + r)
                if bx1 <= bx0 or by1 <= by0:
                    continue
                C = _clutter_strip(T, mats, field, kind, ki, np.arange(bx0, bx1, sp), np.arange(by0, by1, sp), sp,
                                   (e[None], r), np.random.default_rng([seed, ki, ei]))
                if len(C):
                    out.append(C)
            continue
        ys = np.arange(y0, y1, sp)
        rows = max(1, int(1_000_000 // max(1, len(np.arange(x0, x1, sp)))))  # (in strips: a big map is 10^7 samples)
        for r0 in range(0, len(ys), rows):
            C = _clutter_strip(T, mats, field, kind, ki, np.arange(x0, x1, sp), ys[r0:r0 + rows], sp, near,
                               np.random.default_rng([seed, ki, r0]))
            if len(C):
                out.append(C)
    return np.concatenate(out) if out else np.zeros((0, 7))


def _clutter_strip(T, mats, field, kind, ki, xs, ys, sp, near, rng):
    gx, gy = np.meshgrid(xs, ys)
    xy = np.c_[gx.ravel(), gy.ravel()]
    xy = xy + rng.uniform(-0.45, 0.45, xy.shape) * sp
    dn = None
    if near is not None:
        from scipy.spatial import cKDTree
        dn, _ = cKDTree(np.asarray(near[0], float)[:, :2]).query(xy)
        xy, dn = xy[dn < near[1]], dn[dn < near[1]]
    if not len(xy):
        return np.zeros((0, 7))
    h, cs = field.column(xy[:, 0], xy[:, 1])
    P = np.c_[xy, h]
    ok = cs > 0.82  # (under ~35 deg)
    if mats.sea is not None:
        ok &= h > mats.sea - 0.2
    if not np.isnan(T.water).all():
        wet = mats._grid((~np.isnan(T.water)).astype(float), xy) > 0.3
        if mats.sea is None:
            ok &= ~wet
    for m in ("routes", "sites"):
        if m in T.masks:
            ok &= mats._grid(np.asarray(T.masks[m], float), xy) < 0.2
    P = P[ok]
    if dn is not None:
        dn = dn[ok]
    if not len(P):
        return np.zeros((0, 7))
    n = len(P)
    N = np.tile([0.0, 0.0, 1.0], (n, 1))
    kd = mats.kinds(P)
    Wl, _ = mats.weights(P, N)
    lw = lambda *names: sum((Wl[:, mats.layers.index(k)] for k in names if k in mats.layers), np.zeros(n))
    green = np.clip(lw("grass", "scrub") * 1.25, 0, 1)  # (where the maps paint grass: not on sand or rock)
    u = rng.random(n)
    scale = rng.uniform(0.6, 1.4, n)
    squash = np.ones(n)
    one = lambda k: np.clip(np.zeros(n) + kd.get(k, 0.0), 0, 1)
    # how far into the top from the turf's edge (cliff lips): bushes and grass keep back from the bare lip
    bare, d, edge, top = mats.ground.edits.bare(P)
    into = np.where(top > 0.3, d - edge, 1e3)
    if kind == "bush":
        sc, clump = mats.ground.scrub(mats, P, one("scrub"), np.clip(one("rough") + one("scrub"), 0, 1))
        L = terrain_ground.CLUTTER_LIP
        p = sc * clump * 0.9 * _ss(L["keep"], L["keep"] + 1.0, into) * green
        hug = _ss(L["keep"] + 0.5, L["hug"], into)  # 0 at the edge .. 1 well back
        squash = L["squash"] + (1 - L["squash"]) * hug
        scale = scale * (1 + 0.35 * (1 - hug))  # (broader where it hugs the ground)
    elif kind in ("tussock", "tallgrass"):
        sc, _ = mats.ground.scrub(mats, P, one("scrub"), one("rough"))
        p = one("rough") * (1 - sc) * (1 - bare) * _ss(0.2, 0.8, into) * green
        if kind == "tussock":
            p = p * 0.6
            if dn is not None:  # (past the tall grass round the eye: fewer, bigger clumps keep the rough's cover, as an
                # engine's grass draws bigger clumps further out; at 0.45 m they thinned to a few dots from 30 m)
                far = _ss(terrain_ground.CLUTTER_MID[0], terrain_ground.CLUTTER_MID[1], dn)
                p = np.clip(p * (1 + terrain_ground.CLUTTER_MID[2] * far), 0, 1)
                scale = scale * (1 + terrain_ground.CLUTTER_MID[3] * far)
        else:  # (dense by the eye, thinning out to the radius: an engine's grass draw distance)
            r = terrain_ground.CLUTTER_NEAR["tallgrass"]
            p = p * 0.9 * (_ss(r, 0.45 * r, dn) if dn is not None else 1.0)
            scale = rng.uniform(0.7, 1.3, n)
    else:  # (on the ground the maps make rock: never on a beach's sand), in clusters
        rock, _, shore, _ = mats.ground.rock(mats, P, N)
        wr = lw("rock", "wet_rock")
        clus = _ss(0.42, 0.62, noise.fbm(np.c_[P[:, :2], np.zeros(n)], 7.0, 2, seed=671))
        p = _ss(0.55, 0.8, wr) * (shore * 0.6 + np.clip(rock - shore, 0, 1) * 0.2) * clus
        scale = scale * (0.6 + 0.8 * clus)  # (bigger in the thick of a cluster)
        P[:, 2] -= 0.12 * scale  # (sunk: a boulder sits in the ground, it isn't set on it)
    keep = u < p
    k = int(keep.sum())
    if not k:
        return np.zeros((0, 7))
    return np.c_[P[keep], np.full(k, ki), scale[keep], rng.uniform(0, 360, n)[keep], squash[keep]]
