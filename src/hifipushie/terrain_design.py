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

Where the code is (split by responsibility, as C424): this module is the family's base: EVERY constant, `region`,
`centroid`. terrain_design_walls: passes, rugged ground, walls. terrain_design_sites: sites, earthworks.
terrain_design_routes: `apply` and routes. terrain_design_cover: cover and trees. terrain_design_sight: cells, the
eye, `sight`. terrain_design_report: realism, `report`, `intent`.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from .terrain import smoothstep
from . import moved

NAMED_REGIONS = ("everywhere", "centre", "north", "south", "east", "west")

COVER_TYPES = {
    "forest":    {"slope": [0, 40], "avoid": ["water", "routes", "sites"], "breakup": {"scale": 150, "amount": 0.3},
                  "color": [0.12, 0.25, 0.11], "trees": "conifer"},
    "conifer":   {"slope": [0, 42], "avoid": ["water", "routes", "sites"], "breakup": {"scale": 150, "amount": 0.3},
                  "color": [0.10, 0.22, 0.12], "trees": "conifer"},
    "deciduous": {"slope": [0, 36], "avoid": ["water", "routes", "sites"], "breakup": {"scale": 150, "amount": 0.3},
                  "color": [0.24, 0.34, 0.12], "trees": "broadleaf"},
    "rock":      {"slope": [40, 90], "breakup": {"scale": 60, "amount": 0.3}, "color": [0.39, 0.37, 0.34]},
    "scree":     {"slope": [32, 42], "density": 0.7, "breakup": {"scale": 60, "amount": 0.6}, "color": [0.58, 0.54, 0.47]},
    "grass":     {"slope": [0, 42], "avoid": ["water"], "color": [0.45, 0.56, 0.26]},
    "meadow":    {"slope": [0, 25], "avoid": ["water", "routes"], "breakup": {"scale": 80, "amount": 0.3},
                  "color": [0.55, 0.62, 0.30]},
    # grass by how it's kept (terrain_ground: each reads differently in the 3D tiles' maps)
    # (albedos as measured off photos of real turf under sun: mown ~h 98 s 0.65 v 0.43, darker than they look)
    "mown":      {"slope": [0, 42], "avoid": ["water"], "color": [0.20, 0.40, 0.13]},   # fairways, greens, lawns
    "rough":     {"slope": [0, 40], "avoid": ["water"], "breakup": {"scale": 60, "amount": 0.2},
                  "color": [0.30, 0.43, 0.17]},                                         # long grass, tussocks
    "scrub":     {"slope": [0, 50], "avoid": ["water", "routes"], "breakup": {"scale": 40, "amount": 0.5},
                  "color": [0.30, 0.34, 0.21]},                                         # low bushes, heath
    "bunker":    {"slope": [0, 25], "avoid": ["water", "routes", "sites"], "color": [0.86, 0.80, 0.64],
                  "depth": 0.6},                                                        # sand traps, dug in (tiles)
    "snow":      {"slope": [0, 45], "color": [0.94, 0.95, 0.97]},
    "sand":      {"slope": [0, 15], "color": [0.70, 0.62, 0.45]},
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
        if r in ("sea", "beach", "cliffs", "coast", "rocks") and getattr(T, "sea", None):
            from .terrain_sea import regions
            return regions(T, r)
        if r in ("routes", "sites"):
            return T.masks.get(r, np.zeros(shape))
        if r == "cliff_foot":  # below every steep face: where talus and fallen blocks lie (scree cover)
            m = getattr(T, "rock", {}).get("foot", np.zeros(shape, bool)).astype(float)  # (soft: hard-edged patches read
            return np.clip(ndimage.gaussian_filter(m, 2.0) * 1.5, 0, 1)  # as pale sugar cubes along a wall's foot)
        if r in getattr(T, "vzones", {}):  # a volcano's crater, flows ("lava"), collapse scars, "debris"
            return T.vzones[r].astype(float)
        if r in T.lakes and hasattr(T, "lake_id"):
            return (T.lake_id == T.lakes[r]["id"]).astype(float)
        if r.startswith("zone:"):
            return region(T, T.zones[r[5:]])
        if r in T.sites:  # a site: its pad
            st = T.sites[r]
            return smoothstep(1.1 * st["radius"], 0.9 * st["radius"],
                              np.hypot(T.X - st["xy"][0], T.Y - st["xy"][1]))
        if r in getattr(T, "features", {}):  # a line feature (a hedge, a wall): the ground it stands on
            m = T.features[r].get("mask")
            return m if m is not None else np.zeros(shape)
        bn, _, band = r.rpartition(".")
        if bn in getattr(T, "basins", {}) and band:  # a band of a basin wall's profile ("valley.scree"), or its walls
            b = T.basins[bn]
            if band in ("wall", "walls"):
                return b["wall"].astype(float)
            if band == "floor":
                return b["floor"].astype(float)
            z = (b.get("zones") or {})
            if band in z:
                return np.clip(ndimage.gaussian_filter(z[band].astype(float), 1.0) * 1.3, 0, 1)
            raise ValueError(f"basin {bn!r} has no {band!r} (its zones: wall, floor"
                             + "".join(", " + k for k in z) + (": give walls.from_top for bands" if not z else "") + ")")
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
        opened = [b for n, b in getattr(T, "basins", {}).items()
                  if (T.spec.get("basins") or {}).get(n, {}).get("inside") == r["inside"]]
        if not L.props.get("closed") and opened:  # a horseshoe opening to a side: its basin's inside
            meet(opened[0]["inside"].astype(float))
        elif not L.props.get("closed"):
            raise ValueError(f"region inside {r['inside']!r}: that ridge isn't closed (end it where it starts), and no "
                             f"basin opens it to a side")
        else:
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


_OFFS = [(0, 1), (1, 0), (1, 1), (1, -1), (1, 2), (2, 1), (2, -1), (1, -2),
         (1, 3), (3, 1), (3, -1), (1, -3), (2, 3), (3, 2), (3, -2), (2, -3)]  # 32 headings: steep slopes need near-contour ones


BUMP = 1.0

PROFILE_COVER = {"cliffs": {"type": "rock"}, "crags": {"type": "rock"}, "slabs": {"type": "rock", "slope": [30, 90]},
                 "scree": {"type": "scree", "slope": [0, 50], "density": 0.9},
                 "forest": {"type": "conifer", "slope": [0, 45], "density": 0.85},
                 "meadow": {"type": "meadow", "slope": [0, 40]}}

TREES_PER_M2 = 0.02  # the preview's (and a reasonable engine's) density at mask 1: one tree per 50 m2

# ---------------------------------------------------------------- report and intent

# what real landscapes look like, for the realism check: share of ground steeper than 30 / 45 / 60 deg in rugged
# mountain terrain (alpine DEMs), and the slope real mountainsides average
REAL = {"over_30": 0.35, "over_45": 0.12, "over_60": 0.03, "face": (25, 40)}


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("terrain_design_walls", "terrain_design_sites", "terrain_design_routes", "terrain_design_cover",
           "terrain_design_sight", "terrain_design_report")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C427)
