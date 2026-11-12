"""Terrain from a vocabulary: a skeleton of named ridges and rivers, landforms addressed on it, and a design layer
(zones, cover masks, sites, routes, walls, views) compiled on top. Experimental. Metres; x east, y north, z up.
The spec is documented for users in terrain_guide.md; this docstring is about how it is built.

Pipeline (oldest first, like a history):
 1. skeleton: ridges (open or closed) and rivers (heights at source/through/mouth, concave long profiles).
 2. base: three harmonic fields (Laplace, Dirichlet on the skeleton): t, 0 on valley floors (and fixed frame
    edges) and 1 on crests; the floor height extended from the rivers; the crest height extended from the ridges.
    Height = floor + (crest - floor) * profile(t). Harmonic interpolation has no seams where the nearest feature
    switches. Then "divides": where two rivers have no ridge between them, the medial line between them becomes a
    rounded crest rising from their floors at their valleys' side grade (else the ground between is a ramp), and
    the fields are solved again.
 3. texture (capped so big relief doesn't grow pinnacles) and rugged ground.
 4. landforms (lake basins carve to a level and dam it, fans, moraines, terraces); overlaps are reported.
 5. design (terrain_design): passes, walls, sites, routes: they reshape the ground, in that order.
 6. erosion (terrain_erode: fastscapelib stream power, strata, thermal), with designed places protected and the
    authored large-scale heights restored; then walls are checked.
 7. lakes fill to their own level (not a global depression fill: an enclosed valley isn't one big lake).
 8. cover masks from the final ground.

Where the code is (split by responsibility, C424): this module is the family's base: EVERY constant, the spec's terms
and `normalise`, the curves (Line), flow receivers and accumulation. It imports none of the others. terrain_model:
class Terrain (init, addresses, texture) and `load`; its other methods are in mixins: terrain_skeleton (ridges,
rivers), terrain_harmonic (the solve, `_base`), terrain_features (basins, hills, ribs, divides), terrain_landforms
(lakes, dams, fans, moraines, terraces), terrain_measure (report, drainage, export). terrain_views: the map, the mask
sheet, the mesh, the render.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from . import moved

PROFILES = {"V": 1.0, "U": 2.2, "gorge": 0.6, "open": 1.5, "straight": 1.0, "concave": 1.6, "convex": 0.7}
RIVER_KEYS = {"source", "through", "mouth", "into", "hanging", "concavity", "valley", "water", "bed", "falls"}
CUT_GAP, CUT_SHARE = 5.0, 0.15  # a river over this much volcano / lone hill (m, x its fall) cuts its own valley
SIDE_GRADE = {"V": 0.45, "U": 0.6, "gorge": 0.8, "open": 0.12}  # how fast an automatic divide rises
CRESTS = {"arete": 0.0, "rounded": 1.0}
RELIEF_CAP = 600.0  # texture/lumpiness scale with relief up to this: beyond it they made pinnacles


UNITS = {"m": 1.0, "km": 1000.0, "cm": 0.01, "ft": 0.3048, "yd": 0.9144, "mi": 1609.344}
# every number in a spec is a length (converted with the units) unless its key is one of these
NOT_LENGTHS = {"slope", "min_slope", "sides", "max_grade", "grade", "amount", "density", "range", "fov", "lobes",
               "proud", "concavity", "strength", "age", "lumpy", "soften", "color", "size", "coarse", "wander", "k",
               "compression", "detail", "average", "talus", "dip", "dip_toward", "hard", "count", "down", "along",
               "gullies", "head", "reach", "top_slope", "walls", "front", "toward", "breach", "stacks", "faces", "hollow",
               "arete", "buttresses", "ledges", "boulders", "order", "bevel", "geos", "narrow"}
HEIGHT_KEYS = {"h", "level", "floor", "elevation", "above", "below", "border", "height", "depth", "freeboard",
               "above_water", "hanging", "relief"}
REFERENCE_SIZE = 4000.0  # landscape defaults were tuned on 4 km scenes; they scale with the frame (Terrain.k)


def normalise(spec: dict) -> dict:
    """The spec in metres. "units": m (default) | km | ft | ... | "none" (the numbers only mean proportions: the frame is
    taken as `across` metres wide, default 2000, and the report says so). Any length may be "30%": of the frame's
    width/height for positions ([x, y] lists), of the frame's longer side for other lengths, of `relief` (default a
    quarter of the frame) for heights."""
    import copy
    spec = _named(copy.deepcopy(spec))
    (x0, y0), (x1, y1) = [[_pct(v, None) if not isinstance(v, str) else 0 for v in p] for p in spec["extent"]]
    size = max(x1 - x0, y1 - y0)
    unit = spec.get("units", "m")
    if unit == "none":
        from .terrain_world import game_across
        mu = float(spec.get("across") or game_across(spec) or 2000.0) / size
    elif unit in UNITS:
        mu = UNITS[unit]
    else:
        raise ValueError(f"units {unit!r}: use one of {sorted(UNITS)} or 'none'")
    relief = spec.get("relief", 0.25 * size)

    def conv(v, key, axis=None):
        if isinstance(v, str) and v.endswith("%") and _number(v[:-1]):  # free text ending in "%" stays text
            f = float(v[:-1]) / 100
            if key in HEIGHT_KEYS:
                v = f * relief
            elif axis is not None:
                v = (x0, y0)[axis] + f * ((x1 - x0), (y1 - y0))[axis]
            else:
                v = f * size
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return v if key in NOT_LENGTHS else v * mu
        return walk(v, key)

    def walk(v, key=None):
        if isinstance(v, dict):
            return {k: conv(x, k) for k, x in v.items()}
        if isinstance(v, list):
            pos = len(v) in (2, 3) and all(isinstance(x, (int, float, str)) for x in v) and key not in NOT_LENGTHS
            out = []
            for i, x in enumerate(v):
                if pos and i < 2 and key not in HEIGHT_KEYS:
                    out.append(conv(x, key, axis=i))
                elif pos and i == 2:
                    out.append(conv(x, "h"))
                else:
                    out.append(conv(x, key))
            return out
        return v

    text = {k: spec[k] for k in TEXT_KEYS if k in spec}  # prose: never converted
    out = walk({k: v for k, v in spec.items() if k not in ("units", "across", "relief", "export", *TEXT_KEYS)})
    out.update(text)
    out["export"] = spec.get("export", {})
    out["_units"] = {"name": unit if unit != "none" else "units", "mu": mu, "assumed": unit == "none"}
    return out


def _pct(v, _):
    return v


def _number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


TEXT_KEYS = ("name", "story", "notes", "wishes", "brief")
NAMED = ("peaks", "cols", "ridges", "rivers", "basins", "passes", "canyons", "mesas", "fords", "landforms", "zones",
         "sites", "routes", "walls", "cover", "rugged", "intent", "volcanoes", "lines")


def _named(spec):
    """Sections of named things are dicts; a list is accepted (items named by their "name" key, else "<section>_1"...).
    Anything else is an error that says what was expected."""
    for sec in NAMED:
        v = spec.get(sec)
        if v is None or isinstance(v, dict):
            continue
        if not isinstance(v, list) or not all(isinstance(x, dict) for x in v):
            raise ValueError(f"{sec!r} must be an object of named entries ({{\"name\": {{...}}}}), not {type(v).__name__}")
        out = {}
        for i, x in enumerate(v, 1):
            x = dict(x)
            nm = x.pop("name", None)
            if not nm and sec == "cover" and isinstance(x.get("type"), str):
                # (by its type: "cover_1".."cover_6" in the report and the map's legend didn't say which is the meadow)
                nm = x["type"] if x["type"] not in out else f"{x['type']}_{i}"
            out[str(nm or f"{sec.rstrip('s')}_{i}")] = x
        spec[sec] = out
    return spec


def _area(a):
    """An area in words at any scale (the report's unit conversion understands m2, ha and km2)."""
    return f"{a / 1e6:.2f} km2" if a >= 1e6 else f"{a / 1e4:.1f} ha" if a >= 1e4 else f"{a:.0f} m2"


COMPASS = {"north": 0, "north-east": 45, "east": 90, "south-east": 135, "south": 180, "south-west": 225, "west": 270,
           "north-west": 315}


def compass(word):
    """A unit [x, y] vector for a compass word ("north", "ne", "south-west", "southwest"), else None."""
    if not isinstance(word, str):
        return None
    w = word.lower().replace("_", "-").replace(" ", "-")
    short = {"n": "north", "s": "south", "e": "east", "w": "west", "ne": "north-east", "nw": "north-west",
             "se": "south-east", "sw": "south-west"}
    w = short.get(w, w)
    for k, deg in COMPASS.items():
        if w in (k, k.replace("-", "")):
            a = math.radians(deg)
            return np.array([math.sin(a), math.cos(a)])
    return None


def smoothstep(e0, e1, x):
    u = np.clip((x - e0) / (e1 - e0), 0, 1)
    return u * u * (3 - 2 * u)


# ---------------------------------------------------------------- curves
WALL_BANDS = {"cliffs": "cliffs", "cliff": "cliffs", "crags": "crags", "rock": "crags", "broken rock": "crags",
              "slabs": "slabs", "scree": "scree", "talus": "scree", "forest": "forest", "woods": "forest",
              "trees": "forest", "woodland": "forest", "meadow": "meadow", "grass": "meadow", "pasture": "meadow",
              "alp": "meadow"}
BAND_SLOPE = {"crags": 50, "slabs": 42, "scree": 35, "forest": 28, "meadow": 20}
BAND_SHARE = {"cliffs": 0.4, "crags": 0.3, "slabs": 0.3, "scree": 0.25, "forest": 0.35, "meadow": 0.25}


def _from_top(ft, min_slope, name):
    """A wall described from the crest down: ["cliffs", "scree", "forest"], or with shares of the height
    [["cliffs", 0.4], ...] / [{"cliffs": 0.4}, ...] / {"cliffs": 0.4, ...}. Returns [(kind, share, slope deg)]."""
    if not ft:
        return None
    items = list(ft.items()) if isinstance(ft, dict) else ft
    out = []
    for it in items:
        if isinstance(it, str):
            k, sh = it, None
        elif isinstance(it, dict):
            (k, sh), = it.items()
        else:
            k, sh = it[0], (it[1] if len(it) > 1 else None)
        kind = WALL_BANDS.get(str(k).lower().strip())
        if kind is None:
            raise ValueError(f"basin {name!r}: walls.from_top {k!r} isn't a band this knows ({sorted(set(WALL_BANDS))})")
        sl = min(max(min_slope + 14, 62), 80) if kind == "cliffs" else BAND_SLOPE[kind]
        out.append([kind, sh, sl])
    given = sum(sh for _, sh, _ in out if sh is not None)
    free = [o for o in out if o[1] is None]
    if free:
        dflt = sum(BAND_SHARE[o[0]] for o in free)
        for o in free:
            o[1] = BAND_SHARE[o[0]] / dflt * max(1.0 - given, 0.1 * len(free))
    tot = sum(o[1] for o in out)
    return [(k, sh / tot, sl) for k, sh, sl in out]


def _catmull(pts: np.ndarray, step: float, closed: bool = False):
    """A Catmull-Rom curve through pts (n, 2), resampled every ~step metres. Returns (samples, index of each
    control point in samples); a closed curve ends on its first point again (index n)."""
    n = len(pts)
    if closed:
        P = np.vstack([pts[-1], pts, pts[0], pts[1]])
        segs = n
    else:
        P = np.vstack([2 * pts[0] - pts[1], pts, 2 * pts[-1] - pts[-2]])
        segs = n - 1
    out, idx, count = [], [], 0
    for i in range(segs):
        a, b, c, d = P[i], P[i + 1], P[i + 2], P[i + 3]
        m = max(2, int(np.linalg.norm(c - b) / step) + 1)
        u = np.linspace(0, 1, m, endpoint=False)[:, None]
        out.append(0.5 * (2 * b + (c - a) * u + (2 * a - 5 * b + 4 * c - d) * u ** 2 + (3 * b - 3 * c + d - a) * u ** 3))
        idx.append(count)
        count += m
    out.append((pts[0] if closed else pts[-1])[None])
    idx.append(count)
    return np.vstack(out), np.array(idx)


@dataclass
class Line:
    """A resampled line: xy samples, height per sample, arc-length fraction per sample."""
    name: str
    kind: str                 # "ridge" | "river" | "divide" | "route"
    xy: np.ndarray
    h: np.ndarray
    s: np.ndarray
    props: dict = field(default_factory=dict)

    def at(self, s: float):
        i = int(np.clip(np.searchsorted(self.s, s), 1, len(self.s) - 1))
        f = (s - self.s[i - 1]) / max(self.s[i] - self.s[i - 1], 1e-9)
        xy = self.xy[i - 1] + f * (self.xy[i] - self.xy[i - 1])
        t = self.xy[i] - self.xy[i - 1]
        return xy, float(self.h[i - 1] + f * (self.h[i] - self.h[i - 1])), t / (np.linalg.norm(t) + 1e-12)


def _arclen(xy):
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
    return d / max(d[-1], 1e-9), d[-1]


def _same(a, b):
    return a == b if isinstance(a, str) or isinstance(b, str) else list(a[:2]) == list(b[:2])


# ---------------------------------------------------------------- processes
_NB = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def _receivers(H: np.ndarray, cell: float, base: np.ndarray):
    """Steepest-descent (D8) receiver per cell (itself for base cells and cells with no lower neighbour),
    the distance to it, and the cells grouped by flow depth from the base (tree levels, for vectorised sweeps)."""
    ny, nx = H.shape
    pad = np.pad(H, 1, constant_values=np.inf)
    best, bi = np.zeros(H.shape), np.full(H.shape, -1)
    for k, (dy, dx) in enumerate(_NB):
        s = (H - pad[1 + dy:1 + dy + ny, 1 + dx:1 + dx + nx]) / (cell * math.hypot(dy, dx))
        up = s > best
        best[up], bi[up] = s[up], k
    idx = np.arange(H.size)
    iy, ix = np.divmod(idx, nx)
    dy = np.array([d[0] for d in _NB] + [0])[bi.ravel()]
    dx = np.array([d[1] for d in _NB] + [0])[bi.ravel()]
    rec = np.where(base.ravel() | (bi.ravel() < 0), idx, (iy + dy) * nx + ix + dx)
    dist = cell * np.hypot(dy, dx)
    depth = np.where(rec == idx, 0, -1)
    for k in range(1, H.size):
        new = (depth < 0) & (depth[rec] == k - 1)
        if not new.any():
            break
        depth[new] = k
    stuck = depth < 0  # cells in a receiver cycle: treat as roots
    rec[stuck] = idx[stuck]
    depth[stuck] = 0
    order = np.argsort(depth, kind="stable")
    bounds = np.searchsorted(depth[order], np.arange(depth.max() + 2))
    levels = [order[bounds[k]:bounds[k + 1]] for k in range(depth.max() + 1)]
    return rec, dist, levels


def _accumulate(rec, levels, cell):
    acc = np.full(len(rec), cell * cell)
    for lv in reversed(levels[1:]):
        np.add.at(acc, rec[lv], acc[lv])
    return acc


# The modules this one was split into (C424). Its constants stay HERE (C422): tests/test_constants_address.py. The terrain cache hashes the code of all of them (terrain_cache).
MODULES = ("terrain_model", "terrain_views", "terrain_skeleton", "terrain_harmonic", "terrain_features",
           "terrain_landforms", "terrain_measure")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
