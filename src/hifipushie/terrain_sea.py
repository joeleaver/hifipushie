"""The sea and its coast: water below a level out to the frame's edge, and the shore forms where land meets it.

"sea": {"level": 0, "land": zone, "wander": 0.3, "depth": 30, "shelf": m,
        "shore": "rocky" | "beach" | "cliffs",
        "cliffs": {"height": m | [lo, hi], "except": [addresses or zones], "only": [...]},
        "beaches": {name: {"at": address, "length": m, "width": m}},
        "coves": {name: {"at": address | compass word, "width": m, "depth": m, "beach": true}}}

Where the sea is: everything outside the `land` zone (an island: {"near": [x, y], "radius": m}; a coast: "north"), or
without one, the ground below `level` connected to the frame's edge. The coastline wanders (`wander`, 0 for the zone's
own outline). Coves bite horseshoe bays into the land (a mouth narrower than the bay, headlands either side). Offshore,
the seabed shelves down to `depth` below the level over `shelf` metres.

Shore forms, per stretch of coast (the default `shore`, cliffs, and named beaches; coves with "beach" get one at their
head):
  rocky   the land as it is, dropping steeply into the water.
  beach   the land graded down to the water: sand a few metres wide at a few percent, the ground behind easing down to
          it (the sea's "beach" zone is for sand cover).
  cliffs  the land ends in a face at ~70 deg from its top down to the sea floor. Where the land at the coast is lower
          than the asked height, the land ramps up to the cliff top from inland (fading inland, never a rim with lower
          ground behind it); the report measures each stretch's height.

Everything downstream sees the sea as a lake named "sea": shore addresses ("sea.south_shore": the coast on the land's
south side), sight lines ("see": ["sea"]), sites on the shore, the export's water. Zones "sea", "beach", "cliffs"
and "coast" (a band either side of the shoreline) are available to cover and routes.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at terrain_sea.NAME: C422). terrain_sea_apply: `apply`: the sea cut into the terrain: land, cliffs, coves,
geos, stacks, beaches. terrain_sea_report: after the cut: `recut`, the cliff's feet, `fill`, regions, the report, the
seabed, a cove's shape.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from . import noise
from .terrain import compass, smoothstep
from . import moved

CLIFF = math.radians(70)
TALUS_SHARE, TALUS_BASE, TALUS_SLOPE = 0.08, 4.0, 36.0  # a sea cliff's rubble apron: m tall = share x the cliff + base
# (at most 0.3 x), its slope (deg) out from the foot
STACK_CORE = 0.45  # a stack's heightfield core: its radius x this, sheer (the solid stack in the 3D tiles is the form)


def _cliff_face(T, sd, top, level, cl):
    """A sea cliff's face as a profile seaward of its lip: risers with one or two ledges on a tall face (tiers: a face
    of one even slope from lip to water read as a draped curtain), each ledge at a height that wanders along the coast
    and pinching out in places. Returns the height below the lip at each cell and the face's run (lip to foot, m)."""
    hgt = np.maximum(top - level, 0)
    tiers = float(cl.get("tiers", 1.0))
    pts = np.c_[T.P, np.full(len(T.P), 61.0)]

    def nz(scale, seed):
        return noise.fbm(pts, scale, 2, seed=seed).reshape(T.X.shape)
    one = smoothstep(12, 18, hgt) * tiers
    two = smoothstep(28, 36, hgt) * tiers
    r = np.tan(CLIFF + math.radians(8) * one)  # risers steeper where ledges take up the run
    f1 = np.where(two > 0.5, 0.34, 0.5) + 0.14 * (nz(70.0, 301) - 0.5)
    f2 = 0.66 + 0.12 * (nz(80.0, 303) - 0.5)
    D1 = np.clip(0.15 * hgt, 2.5 * T.cell, 9.0) * smoothstep(0.36, 0.55, nz(55.0, 302)) * one
    D2 = np.clip(0.13 * hgt, 2.5 * T.cell, 8.0) * smoothstep(0.36, 0.55, nz(45.0, 304)) * two
    d = np.maximum(-sd, 0)
    z1, z2 = f1 * hgt, np.maximum(f2 * hgt, f1 * hgt + 2 * T.cell)
    d1 = z1 / r
    drop = r * d
    # a ledge falls outward a little (a dead-level shelf read as a road)
    drop = np.where(d > d1, z1 + 0.08 * np.minimum(d - d1, D1) + r * np.maximum(d - d1 - D1, 0), drop)
    d2 = d1 + D1 + (z2 - z1 - 0.08 * D1) / r
    drop = np.where((d > d2) & (two > 0.01), z2 + 0.08 * np.minimum(d - d2, D2) + r * np.maximum(d - d2 - D2, 0),
                    drop)
    run = hgt / r + D1 + np.where(two > 0.01, D2, 0) - 0.08 * (D1 + D2) / r
    return drop, np.maximum(run, 0)


def _headland_sides(T, hl, p, inl, left, w):
    """Which side(s) of a cove get a headland: +1 = left looking inland from the mouth. "auto": the side where the land
    stands higher; "left"/"right", "both", "none", a compass side or an address."""
    if hl in ("auto", None, True):
        hi_left = T.height(p + left * 0.7 * w + inl * 0.1 * w) >= T.height(p - left * 0.7 * w + inl * 0.1 * w)
        return [1.0 if hi_left else -1.0]
    if hl in ("none", False):
        return []
    if hl == "both":
        return [1.0, -1.0]
    if hl in ("left", "right"):
        return [1.0 if hl == "left" else -1.0]
    cd = compass(hl)
    if cd is None:
        cd = T.address(hl)[0] - p
    return [1.0 if float(np.dot(cd, left)) >= 0 else -1.0]


def _coast_point(T, land, ref):
    """A point on the coastline: toward a compass direction from the land's middle, or the coast nearest an address.
    Returns (xy, inland unit vector)."""
    edge = land & ndimage.binary_dilation(~land)
    pts = np.stack([T.X[edge], T.Y[edge]], 1)
    c = np.array([T.X[land].mean(), T.Y[land].mean()])
    cd = compass(ref)
    if cd is not None:
        k = int(np.argmax((pts - c) @ cd))
    else:
        xy = T.address(ref)[0]
        k = int(np.argmin(np.linalg.norm(pts - xy, axis=1)))
    p = pts[k]
    # inland: down the gradient of the distance to the sea, smoothed, at that point
    sd = ndimage.gaussian_filter(ndimage.distance_transform_edt(land), 3)
    gy, gx = np.gradient(sd)
    iy, ix = int(round((p[1] - T.ys[0]) / T.cell)), int(round((p[0] - T.xs[0]) / T.cell))
    n = np.array([gx[iy, ix], gy[iy, ix]])
    if np.linalg.norm(n) < 1e-6:
        n = c - p
    return p, n / (np.linalg.norm(n) + 1e-9)


def _signed(land, cell):
    """Signed distance to the coastline in metres: positive on land."""
    return (ndimage.distance_transform_edt(land) - ndimage.distance_transform_edt(~land)) * cell


def _near(T, refs, reach, coves=None, sd=None):
    """A 0..1 mask within `reach` of each address or inside each zone (a cove: its whole bay and mouth). An address
    inland reaches the coast nearest it: its distance to the coast plus `reach` (a headland's peak is well back from
    its own cliffs)."""
    from . import terrain_design as design
    m = np.zeros(T.X.shape)
    for a in refs or []:
        if isinstance(a, str) and coves and a in coves:
            grow = ndimage.distance_transform_edt(~coves[a]["mask"]) * T.cell
            m = np.maximum(m, smoothstep(1.3 * reach, 0.7 * reach, grow))
            continue
        if isinstance(a, str) and (a in T.zones or a.startswith("quadrant:") or a in getattr(T, "vzones", {})) \
                or isinstance(a, dict):
            m = np.maximum(m, design.region(T, a))
            continue
        xy = T.address(a)[0]
        r = reach
        if sd is not None:
            iy = int(np.clip(round((xy[1] - T.ys[0]) / T.cell), 0, len(T.ys) - 1))
            ix = int(np.clip(round((xy[0] - T.xs[0]) / T.cell), 0, len(T.xs) - 1))
            r = reach + abs(float(sd[iy, ix]))
        m = np.maximum(m, smoothstep(1.3 * r, 0.7 * r, np.hypot(T.X - xy[0], T.Y - xy[1])))
    return m


SHELF = {"flat": 0.004, "area": 4000.0, "step": 1.0, "run": 60.0, "straight": 1.5}


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("terrain_sea_apply", "terrain_sea_report")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
