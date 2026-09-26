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
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy import ndimage, sparse
from scipy.sparse.linalg import splu
from scipy.spatial import cKDTree

from . import noise

PROFILES = {"V": 1.0, "U": 2.2, "gorge": 0.6, "open": 1.5, "straight": 1.0, "concave": 1.6, "convex": 0.7}
SIDE_GRADE = {"V": 0.45, "U": 0.6, "gorge": 0.8, "open": 0.12}  # how fast an automatic divide rises
CRESTS = {"arete": 0.0, "rounded": 1.0}
RELIEF_CAP = 600.0  # texture/lumpiness scale with relief up to this: beyond it they made pinnacles


UNITS = {"m": 1.0, "km": 1000.0, "cm": 0.01, "ft": 0.3048, "yd": 0.9144, "mi": 1609.344}
# every number in a spec is a length (converted with the units) unless its key is one of these
NOT_LENGTHS = {"slope", "min_slope", "sides", "max_grade", "grade", "amount", "density", "range", "fov", "lobes",
               "proud", "concavity", "strength", "age", "lumpy", "soften", "color", "size", "coarse", "wander", "k",
               "compression", "detail", "average", "talus", "dip", "dip_toward", "hard", "count", "down", "along"}
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
         "sites", "routes", "walls", "cover", "rugged", "intent")


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
            out[str(x.pop("name", None) or f"{sec.rstrip('s')}_{i}")] = x
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


# ---------------------------------------------------------------- the terrain

class Terrain:
    def __init__(self, spec: dict):
        from . import terrain_design as design
        from .terrain_erode import erode
        self.source = spec
        spec = normalise(spec)
        self.spec = spec
        self.units = spec["_units"]
        (x0, y0), (x1, y1) = spec["extent"]
        self.size = max(x1 - x0, y1 - y0)
        self.k = self.size / REFERENCE_SIZE  # landscape defaults (noise, ribs, erosion scales) scale with the frame
        self.cell = c = float(spec.get("cell", self.size / 400))
        from . import terrain_world as world
        self.world = world.resolve(self)  # the kind of terrain, its compression, player-scale detail
        world.fill_heights(self)
        self.xs = np.arange(x0, x1 + c / 2, c)
        self.ys = np.arange(y0, y1 + c / 2, c)
        self.X, self.Y = np.meshgrid(self.xs, self.ys)  # [iy, ix]
        self.P = np.stack([self.X.ravel(), self.Y.ravel()], 1)
        self.warnings: list[str] = []
        self.points = {}
        for group in ("peaks", "cols"):
            for n, p in (spec.get(group) or {}).items():
                self.points[n] = (np.array(p["at"], float), float(p["h"]))
        self.zones = dict(spec.get("zones") or {})
        self.lines: dict[str, Line] = {}
        self.lakes: dict[str, dict] = {}
        self.sites: dict[str, dict] = {}
        self.routes: dict[str, Line] = {}
        self.walls: dict[str, dict] = {}
        self.passes: dict[str, dict] = {}
        self.canyons, self.mesas, self.fords = {}, {}, {}
        self.masks: dict[str, np.ndarray] = {}   # what each design element occupies (sites, routes, ...)
        self.water = np.full(self.X.shape, np.nan)
        self._ridges()
        self._rivers()
        self.H = self._base()
        from . import terrain_forms as forms
        forms.carve(self)  # canyons cut into the plateau, mesas stood on it
        for c in self.canyons.values():  # water ends in a canyon's river: base level for erosion
            m, _ = self._stamp(self.lines[c["river"]], c["floor"] / 2)
            self._fixed_river |= m
        self.H0 = self.H.copy()
        self._texture()
        from . import terrain_sea
        terrain_sea.apply(self)  # the sea and its coast: before lakes, sites and routes, which use its shores
        design.rugged(self)  # (after the sea: its zones, "cliffs" and "coast", are places to make rugged)
        self._landforms()
        self._fill_lakes()  # lake shores are addresses sites use
        design.apply(self)
        erode(self)  # after the design: its places are protected, and lakes are where water ends
        forms.settle(self)  # caprocks stay flat
        design.check(self)
        self._fill_lakes()
        self.cover = design.cover(self)

    # ------------------------------------------------ skeleton
    def _pt(self, ref):
        if isinstance(ref, str) and "@" in ref:  # a point on a line already built: "north_ridge@0.6"
            name, s = ref.split("@")
            xy, h, _ = self.lines[name].at(float(s))
            return np.array([*xy, h])
        if isinstance(ref, str):
            if ref not in self.points:
                raise ValueError(f"unknown point {ref!r}: ridges pass through peaks, cols, 'line@0.4' or [x, y, z]")
            xy, h = self.points[ref]
            return np.array([*xy, h])
        if len(ref) == 2 or ref[2] is None:  # a height left out: chosen from the kind, like a peak's
            z = self.world["base"] + 0.85 * self.world["relief"]
            self.filled.append(f"ridge point [{ref[0]:.0f}, {ref[1]:.0f}] h {z:.0f} m")
            return np.array([ref[0], ref[1], z], float)
        return np.array(ref, float)

    def _ridges(self):
        for name, r in (self.spec.get("ridges") or {}).items():
            through = list(r["through"])
            closed = bool(r.get("closed"))
            if len(through) > 2 and _same(through[0], through[-1]):
                through, closed = through[:-1], True
            ctrl = np.array([self._pt(p) for p in through])
            xy, ki = _catmull(ctrl[:, :2], self.cell / 2, closed)
            hs = np.r_[ctrl[:, 2], ctrl[:1, 2]] if closed else ctrl[:, 2]
            h = np.empty(len(xy))
            for j in range(len(ki) - 1):
                a, b = ki[j], ki[j + 1]
                u = np.linspace(0, 1, b - a + 1)
                h[a:b + 1] = hs[j] + (hs[j + 1] - hs[j]) * u * u * (3 - 2 * u)  # peaks and cols level off
            xy = self._wander(xy, ki, r.get("wander", 1.0), seed=len(self.lines))
            s, _ = _arclen(xy)
            self.lines[name] = Line(name, "ridge", xy, h, s, {"crest": CRESTS[r.get("crest", "arete")], "closed": closed})

    def _wander(self, xy, ki, amount, seed):
        """Real crests never run as smooth arcs between summits: bend each span sideways with low noise, most in its
        middle, none at the peaks and cols themselves (they stay where the designer put them)."""
        if not amount:
            return xy
        tan = np.gradient(xy, axis=0)
        tan /= np.linalg.norm(tan, axis=1, keepdims=True) + 1e-12
        nrm = np.stack([-tan[:, 1], tan[:, 0]], 1)
        d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
        n = noise.fbm(np.c_[d / 1.0, np.zeros((len(d), 2))], 350 * self.k, 3, seed=97 + seed) - 0.5
        env = np.zeros(len(xy))
        for a, b in zip(ki[:-1], ki[1:]):
            span = d[b] - d[a]
            env[a:b + 1] = np.sin(np.pi * np.linspace(0, 1, b - a + 1)) * min(0.07 * span, 150 * self.k)
        return xy + nrm * (2 * n * env * amount)[:, None]

    def _rivers(self):
        todo = dict(self.spec.get("rivers") or {})
        while todo:
            progressed = False
            for name, r in list(todo.items()):
                if r.get("into") and r["into"] not in self.lines:
                    continue
                src = np.array(r["source"], float)
                mid = [np.array(p, float) for p in r.get("through", [])]
                if r.get("into"):
                    parent = self.lines[r["into"]]
                    last = mid[-1][:2] if mid else src[:2]
                    j = int(cKDTree(parent.xy).query(last)[1])
                    j = min(j + int(100 / self.cell), len(parent.xy) - 1)  # joins a little downstream
                    mouth = np.array([*parent.xy[j], parent.h[j] + r.get("hanging", 0)])
                else:
                    mouth = np.array(r["mouth"], float)
                ctrl = np.vstack([src[:2], *[m[:2] for m in mid], mouth[:2]])
                xy, ki = _catmull(ctrl, self.cell / 2)
                s, length = _arclen(xy)
                k = r.get("concavity", 1.6)  # graded rivers: steep near the source, flattening downstream
                known = [(0, src[2])] + [(ki[i + 1], m[2]) for i, m in enumerate(mid) if len(m) > 2] + [(len(xy) - 1, mouth[2])]
                h = np.empty(len(xy))
                for (a, ha), (b, hb) in zip(known[:-1], known[1:]):
                    u = (s[a:b + 1] - s[a]) / max(s[b] - s[a], 1e-9)
                    h[a:b + 1] = hb + (ha - hb) * (1 - u) ** k
                v = r.get("valley") or {}
                prof = v.get("profile", "V")
                self.lines[name] = Line(name, "river", xy, h, s, {
                    "p": PROFILES[prof], "side": float(v.get("sides", SIDE_GRADE[prof])),
                    "floor": float(v.get("floor", 30 * self.k)), "length": length,
                    "into": r.get("into"), "hanging": r.get("hanging", 0)})
                del todo[name]
                progressed = True
            if not progressed:
                raise ValueError(f"rivers joining unknown rivers: {sorted(todo)}")

    # ------------------------------------------------ harmonic base
    def _solve(self, fixed: np.ndarray, rhs: list[np.ndarray]) -> list[np.ndarray]:
        ny, nx = self.X.shape
        n = nx * ny
        idx = np.arange(n).reshape(ny, nx)
        rows, cols = [], []
        deg = np.zeros(n)
        for a, b in ((idx[:, 1:].ravel(), idx[:, :-1].ravel()), (idx[1:, :].ravel(), idx[:-1, :].ravel())):
            for i, j in ((a, b), (b, a)):
                rows.append(i); cols.append(j)
                np.add.at(deg, i, 1)
        rows, cols = np.concatenate(rows), np.concatenate(cols)
        f = fixed.ravel()
        keep = ~f[rows]
        A = sparse.csc_matrix((np.r_[-np.ones(keep.sum()), np.where(f, 1.0, deg)],
                               (np.r_[rows[keep], np.arange(n)], np.r_[cols[keep], np.arange(n)])), shape=(n, n))
        lu = splu(A)
        return [lu.solve(np.where(f, r.ravel(), 0.0)).reshape(ny, nx) for r in rhs]

    def _stamp(self, line: Line, radius: float):
        """Cells within radius of a line, and for each cell its nearest sample index."""
        d, i = cKDTree(line.xy).query(self.P, distance_upper_bound=radius + self.cell)
        m = d <= max(radius, self.cell * 0.75)
        return m.reshape(self.X.shape), np.where(m, i, 0).reshape(self.X.shape)

    def _edges(self):
        """Fixed frame-edge cells and their heights. "border": a height, or per side {"n"|"s"|"e"|"w": height |
        "open"}; an open side has no height of its own (the ground carries on as it goes)."""
        b = self.spec.get("border", "open")
        sides = b if isinstance(b, dict) else {k: b for k in "nsew"}
        shape = self.X.shape
        fix, val = np.zeros(shape, bool), np.zeros(shape)
        for k, sl in (("s", (0, slice(None))), ("n", (-1, slice(None))), ("w", (slice(None), 0)), ("e", (slice(None), -1))):
            v = sides.get(k, "open")
            if v != "open":
                fix[sl] = True
                val[sl] = float(v)
        return fix, val

    def _base(self):
        shape = self.X.shape
        low_fix, low = self._edges()
        prof = np.full(shape, PROFILES["V"])
        high_fix, high, crest = np.zeros(shape, bool), np.zeros(shape), np.zeros(shape)
        self._fixed_river = np.zeros(shape, bool)
        river_id = np.zeros(shape, int)
        from .terrain_forms import canyon_rivers
        cut = canyon_rivers(self.spec)
        rivers = [L for L in self.lines.values() if L.kind == "river" and L.name not in cut]
        for k, L in enumerate(rivers, 1):
            m, i = self._stamp(L, L.props["floor"] / 2)
            if L.props["hanging"]:  # the lip: leave the last stretch free, so the step is steep, not a wall
                into = self.lines[L.props["into"]].props["floor"]
                m &= (1 - L.s[i]) * L.props["length"] > 3 * L.props["hanging"] + into / 2
            low_fix |= m; low[m] = L.h[i[m]]; prof[m] = L.props["p"]
            self._fixed_river |= m
            river_id[m] = k
        self.basins = {}
        for name, b in (self.spec.get("basins") or {}).items():
            F, floor_h, wall_p = self._basin(name, b)
            keep = F & ~self._fixed_river  # authored rivers inside a basin keep their own heights
            low_fix |= keep; low[keep] = floor_h[keep]; prof[keep] = wall_p
            prof[~low_fix & self.basins[name]["wall"]] = wall_p
        for L in self.lines.values():
            if L.kind == "ridge":
                m, i = self._stamp(L, 0)
                high_fix |= m; high[m] = L.h[i[m]]; crest[m] = L.props["crest"]
                low_fix &= ~m  # a ridge reaching the frame's edge stays a ridge
        # a peak no ridge passes through stands alone (a hill, a knoll): not a constraint (a fixed disk next to a fixed
        # floor makes a walled mesa) but a dome raised on whatever ground is there, after the base (_hills)
        on_ridge = {p for r in (self.spec.get("ridges") or {}).values() for p in r["through"] if isinstance(p, str)}
        self._lone = [n for n in self.points if n not in on_ridge]
        sea = self.spec.get("sea")
        if sea:  # the sea is low ground: the land falls to it (a ring of peaks with nothing low around it stood as a
            # plateau at its basin floor's height)
            lvl = float(sea.get("level", 0.0))
            if "land" in sea:
                from . import terrain_design as design
                try:
                    out = design.region(self, sea["land"]) < 0.5
                except (AttributeError, ValueError):  # a land zone made from the ground itself: not yet
                    out = None
                if out is not None:
                    out &= ~high_fix
                    low_fix |= out
                    low[out] = lvl - 0.5 * float(sea.get("depth", 30.0))
            elif not low_fix.any() and high_fix.any():  # ridges with nothing low: the frame's edges at the land's base
                # (a plain stays a plain at world.base with its tilt: pinning the edges at the sea floor had ignored the
                # base and put a coast's farmland at 0 m)
                for sl in ((0, slice(None)), (-1, slice(None)), (slice(None), 0), (slice(None), -1)):
                    low_fix[sl] = True
                    low[sl] = self.world["base"]
        plain = not low_fix.any() and not high_fix.any()  # a tile of open ground: a plain at the base height (+ tilt, hills)
        if not low_fix.any() and not plain:
            raise ValueError("nothing low: add a river or a basin, or give the frame's edge a height (\"border\")")

        def solve():
            if plain:
                base = self.world["base"]
                self.floor, self.prof = np.full(shape, base), prof
                self.crest, self.round, self.t = self.floor.copy(), np.zeros(shape), np.zeros(shape)
                return
            self.floor, self.prof = self._solve(low_fix, [low, prof])
            if high_fix.any():
                t, = self._solve(low_fix | high_fix, [np.where(high_fix, 1.0, 0.0)])
                self.crest, self.round = self._solve(high_fix, [high, crest])
                self.t = np.clip(t, 0, 1)
            else:  # no ridges at all (a tile of rolling ground, hills only): the low ground is the ground
                self.crest, self.round, self.t = self.floor.copy(), np.zeros(shape), np.zeros(shape)

        solve()
        self.divides = []
        extra = []
        if self.spec.get("divides", True) and len(rivers) > 1:
            add = self._divides(rivers, river_id, high_fix)
            if add is not None:
                extra.append(add)
        if self.spec.get("ribs", True) and high_fix.any():
            add = self._ribs(high_fix, low_fix)
            if add is not None:
                extra.append(add)
        if extra:
            for m, h in extra:
                m = m & ~low_fix
                high_fix |= m; high[m] = h[m]; crest[m] = 1.0
            solve()
        s = self.t ** self.prof
        s = (1 - self.round) * s + self.round * (1 - (1 - s) ** 2)
        self.hard = np.zeros(self.X.shape, bool)  # rock that resists erosion (cliff bands)
        self.hardness = np.ones(self.X.shape)  # erodibility factor: 1 soil ... ~0 rock that stands
        for b in self.basins.values():  # basin walls get a mountainside's profile, and a character
            prof = self._wall_profile(b)
            u = np.linspace(0, 1, len(prof))
            t = self.t
            if b["character"] in ("buttressed", "broken", "tiered"):
                # buttresses and couloirs: along the ring the face's profile shifts out and in, so rock ribs stand
                # proud between gullies (a smooth face read as drapery; ~900 m apart they read as lobes, not ribs)
                spacing = max(0.4 * b["width"], 80 * self.k)
                a1 = b["arc"] / spacing
                n1 = noise.fbm(np.c_[a1.ravel(), np.zeros((a1.size, 2))], 1.0, 3, seed=73).reshape(self.X.shape)
                amp = {"buttressed": 0.3, "broken": 0.45, "tiered": 0.15}[b["character"]]
                t = np.clip(t + amp * (2 * n1 - 1) * np.sin(np.pi * np.clip(t, 0, 1)), 0, 1)
            s = np.where(b["wall"], np.interp(t, u, prof), s)
            # the band(s) wander up and down the face (one even ring read as a built wall)
            pts = np.c_[self.P, np.zeros(len(self.P))]
            shift = 0.12 * (2 * noise.fbm(pts, 500 * self.k, 2, seed=71).reshape(self.X.shape) - 1)
            for at0 in b["_bands"]:
                at = at0 + shift  # (breaking a band made climbable gaps: "unclimbable" wins that one)
                band = b["wall"] & (t >= at - 0.03) & (t <= at + b["_ft"] + 0.03)
                self.hard |= band
                self.hardness = np.where(band, 0.2, self.hardness)  # (0 made a palisade: it stood, all else went)
        H = self.floor + np.maximum(self.crest - self.floor, 0) * s
        tilt = self.spec.get("tilt")  # the whole frame leans: {"down": "south" | bearing deg, "grade": 0.07}
        if tilt:
            down = tilt.get("down", "south")
            b = math.radians({"north": 0, "east": 90, "south": 180, "west": 270}.get(down, down if isinstance(down, (int, float)) else 180))
            (x0, y0), (x1, y1) = self.spec["extent"]
            along = (self.X - (x0 + x1) / 2) * math.sin(b) + (self.Y - (y0 + y1) / 2) * math.cos(b)
            H = H - float(tilt.get("grade", 0.05)) * along  # lower toward `down`
        return self._hills(H)

    def _wall_profile(self, b):
        """Height fraction s(t) across a basin wall, t from the floor's edge (0) to the crest (1): a concave scree foot,
        one cliff band at `band_at` (its height `band`, at min_slope + 14 deg), steady slopes above easing to the crest.
        Built as slope weights (the band's weight is its steepness), so the whole face averages its intended slope."""
        n = 512
        t = np.linspace(0, 1, n)
        rest = math.tan(math.radians(b["avg"]))
        wgt = rest * (0.45 + 0.75 * smoothstep(0.0, 0.3, t) - 0.35 * smoothstep(0.75, 1.0, t))
        steep = math.tan(math.radians(min(b["min_slope"] + 14, 80)))  # margin: erosion and the grid soften it
        # each band is `band` tall plus the grid's rounding at its lip and foot (the check measures the tallest steep
        # stretch: tiered bands sharing the height made "unclimbable" walls of 17 m steps)
        tall = b["band"] + 0.6 * self.cell * steep
        width = max(b["relief"] / math.tan(math.radians(b["avg"])), 1e-6)
        ft = min(0.4, (tall / steep) / width)  # one band's share of the width
        n_bands = b["bands"] or (3 if b["character"] == "tiered" else 1)
        ats = [b["band_at"]] if n_bands == 1 else list(np.linspace(0.2, 0.75, n_bands))
        if n_bands * ft > 0.6:  # no room for them all at full height: shorter bands (the wall check will say so)
            ft = 0.6 / n_bands
        for at in ats:
            wgt = np.where((t >= at) & (t < at + ft), steep, wgt)
        b["_ft"], b["_bands"] = ft, ats
        s = np.r_[0, np.cumsum((wgt[1:] + wgt[:-1]) / 2)]
        return s / s[-1]

    def _hills(self, H):
        """Lone peaks as domes on the ground beneath: a rounded top of `radius`, flanks falling at about `flanks`
        degrees (default 18) to the surrounding ground. Their footprint is protected from basin floors and such."""
        for n in self._lone:
            xy, h = self.points[n]
            p = (self.spec.get("peaks") or {}).get(n) or (self.spec.get("cols") or {}).get(n) or {}
            d = np.hypot(self.X - xy[0], self.Y - xy[1])
            under = self.height(xy, H)
            rise = h - under
            if rise <= 0:
                self.warnings.append(f"hill {n!r} ({h:.0f} m) is below the ground there ({under:.0f} m): it adds nothing")
                continue
            top = float(p.get("radius", max(0.02 * self.size, 1.5 * self.cell)))
            foot = top + rise / math.tan(math.radians(p.get("flanks", 18)))
            if p.get("base_radius"):  # its footprint, given directly: the flanks follow
                foot = max(float(p["base_radius"]), top + self.cell)
            u = np.clip((d - top) / (foot - top), 0, 1)
            H = H + rise * 0.5 * (1 + np.cos(np.pi * u)) * (d < foot)  # a smooth dome: level top, soft foot
        return H

    def _early_xy(self, ref):
        """An address resolved before any ground exists (for the skeleton): points, lines, landform centres."""
        if isinstance(ref, (list, tuple)):
            return np.array(ref[:2], float)
        if ref in self.points:
            return self.points[ref][0]
        lfs = self.spec.get("landforms") or {}
        if ref in lfs:
            return self._early_xy(lfs[ref].get("at") or lfs[ref].get("across"))
        if "@" in ref:
            name, s = ref.split("@")
            return self.lines[name].at(float(s))[0]
        if "." in ref:
            name, end = ref.rsplit(".", 1)
            return self.lines[name].at(0.0 if end == "source" else 1.0)[0]
        if ref in self.zones or ref.startswith("quadrant:"):
            from . import terrain_design as design
            try:
                return design.centroid(self, design.region(self, ref))
            except (AttributeError, ValueError):  # a zone defined by the ground (above/below/slope) isn't there yet
                pass
        raise ValueError(f"can't place {ref!r} before the ground exists: use a compass direction (\"north\"), a peak, "
                         f"col, landform, line, a zone drawn on the map, or [x, y]")

    def _basin(self, name, b):
        """A valley floor inside a closed ridge: a bowl from `floor` [low, high] that drains to `falls_to`, and between
        the floor's edge and the crest a wall as wide as its steepness allows (the wall is the mountainside itself)."""
        from skimage.draw import polygon
        L = self.lines.get(b["inside"])
        if L is None or not L.props.get("closed"):
            raise ValueError(f"basin {name!r}: 'inside' must name a closed ridge (one that ends where it starts)")
        inside = np.zeros(self.X.shape, bool)
        rr, cc = polygon((L.xy[:, 1] - self.ys[0]) / self.cell, (L.xy[:, 0] - self.xs[0]) / self.cell, self.X.shape)
        inside[rr, cc] = True
        lo, hi = b.get("floor", [None, None])
        crest_min = float(np.percentile(L.h, 5))  # passes will notch lower; they're exempt
        w = b.get("walls", {})
        # a real mountainside averages 25-40 deg: a scree foot, cliff band(s), easier upper slopes. "Unclimbable" needs
        # only one band steep and tall enough, not the whole face (that read as a draped curtain)
        slope = float(w.get("min_slope", 45))
        avg = float(w.get("average", 32))
        if avg > slope + 8:  # the cliff band (min_slope + 14) must stay steeper than the face around it
            asked = "average" in (((self.source.get("basins") or {}).get(name) or {}).get("walls") or {})
            self.warnings.append(f"basin {name!r}: " + ("walls.average" if asked else "the kind's face slope")
                                 + f" {avg:.0f} deg is steeper than its cliff band allows (min_slope {slope:.0f} + 8): "
                                 f"built at {slope + 8:.0f}; raise min_slope for steeper walls")
            avg = slope + 8
        # each stretch of wall is as wide as the crest behind it needs at that slope (a big peak has a big footprint;
        # one width from the lowest crest made the high stretches 58 deg)
        dist, near = cKDTree(L.xy).query(self.P)
        arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(L.xy, axis=0), axis=1))][near].reshape(self.X.shape)
        crest_here = ndimage.gaussian_filter(L.h[near].reshape(self.X.shape), 150 * self.k / self.cell)
        need = np.maximum(3 * self.cell, (crest_here - hi) / math.tan(math.radians(avg)))
        if "width" in w:
            need = np.full(self.X.shape, float(w["width"]))
        F = inside & (dist.reshape(self.X.shape) >= need)
        F = ndimage.binary_opening(F, iterations=2)
        if "width" not in w and F.any() and lo is not None and hi is not None and hi > lo:
            # the face starts at the floor's edge, which is lower than `hi` where the floor is low (by the drain, or on
            # the low side of a tilted floor): size those stretches for their real relief (sized from `hi`, a wall
            # asked at 45 deg came out 54)
            fl0 = self._floor_heights(b, F, lo, hi, name)
            _, (fy, fx_) = ndimage.distance_transform_edt(~F, return_indices=True)
            edge_h = fl0[fy, fx_]
            need = np.maximum(3 * self.cell, (crest_here - edge_h) / math.tan(math.radians(avg)))
            F = inside & (dist.reshape(self.X.shape) >= need)
            F = ndimage.binary_opening(F, iterations=2)
        width = float(np.median(need[inside & ~F])) if (inside & ~F).any() else float(need.mean())
        if not F.any():
            raise ValueError(f"basin {name!r}: walls {width:.0f} m wide leave no floor; lower the floor's high end "
                             f"or the crest, or widen the ring")
        fl, fx, sink = self._floor_heights(b, F, lo, hi, name, full=True)
        self._fixed_river |= sink  # water ends here: base level for erosion
        wall = inside & ~F
        band = float(w.get("height", max(30.0, 0.08 * (crest_min - hi))))  # the cliff band's height
        self.basins[name] = {"floor": F, "wall": wall, "inside": inside, "width": width, "lo": lo, "hi": hi,
                             "min_slope": slope, "falls": fx.tolist(), "band": band, "avg": avg,
                             "relief": float(np.median(L.h)) - hi, "band_at": float(w.get("band_at", 0.3)),
                             "arc": arc, "character": w.get("character", "tiered"), "bands": int(w.get("bands", 0))}
        return F, fl, PROFILES.get(w.get("profile", "straight"), 1.0)

    def _floor_heights(self, b, F, lo, hi, name, full=False):
        """A basin floor's heights over the grid (meaningful on F): from `lo` at the drain to `hi` at the floor's edge."""
        fx = self._early_xy(b["falls_to"]) if b.get("falls_to") else np.array(
            [self.X[F].mean(), self.Y[F].mean()])
        lfs = self.spec.get("landforms") or {}
        r = 0.5 * lfs[b["falls_to"]]["radius"] if isinstance(b.get("falls_to"), str) and b["falls_to"] in lfs else 60.0 * self.k
        sink = (np.hypot(self.X - fx[0], self.Y - fx[1]) < r) & F
        if not sink.any():
            fy, fxx = np.nonzero(F)
            c = [float(self.xs[fxx].mean()), float(self.ys[fy].mean())]
            dmin = float(np.hypot(self.X[F] - fx[0], self.Y[F] - fx[1]).min())
            raise ValueError(f"basin {name!r}: falls_to {b.get('falls_to')!r} at [{fx[0]:.0f}, {fx[1]:.0f}] isn't on the "
                             f"basin floor: the walls take the ground there. The floor spans x {self.xs[fxx].min():.0f}-"
                             f"{self.xs[fxx].max():.0f}, y {self.ys[fy].min():.0f}-{self.ys[fy].max():.0f} (centre "
                             f"[{c[0]:.0f}, {c[1]:.0f}]), {dmin:.0f} m from it: move it onto the floor, or lower the floor's "
                             f"high end / the crest so the walls take less room")
        # the floor ramps by relative distance, drain -> edge (harmonic from a small drain is logarithmic: a flat
        # plateau with the drain sunk in a funnel)
        d_sink = ndimage.distance_transform_edt(~sink) * self.cell
        d_edge = ndimage.distance_transform_edt(F) * self.cell
        u = ndimage.gaussian_filter(d_sink / np.maximum(d_sink + d_edge, 1e-6), 3)
        if b.get("rises_toward"):  # the floor tilts: mostly along the drain -> this address, a little toward every edge
            rt = b["rises_toward"]
            cd = compass(rt)
            if cd is not None:  # a direction: rising across the whole floor that way
                proj = (self.P - fx) @ cd
                ax = cd * max(float(proj[F.ravel()].max()), self.cell)
            else:
                ax = self._early_xy(rt) - fx
            along = np.clip(((self.P - fx) @ ax) / (ax @ ax), 0, 1).reshape(self.X.shape)
            u = 0.75 * along + 0.25 * u
        p = {"bowl": 1.0, "flat": 2.5, "open": 0.7}[b.get("shape", "bowl")]  # flat: level, tipping up at the edge
        fl = lo + (hi - lo) * np.clip(u, 0, 1) ** p
        return (fl, fx, sink) if full else fl

    def _ribs(self, high_fix, low_fix):
        """Spurs running down from every ridge at irregular spacing: they break long mountain walls into
        spur-and-gully, which harmonic slopes (smooth between crest and floor) never have. Each rib is traced
        downhill on the first solution and stands a little proud of it, fading out toward the valley."""
        cfg = self.spec.get("ribs") if isinstance(self.spec.get("ribs"), dict) else {}
        every, proud = cfg.get("every", 320.0 * self.k), cfg.get("proud", 0.07)
        s = self.t ** self.prof
        H = self.floor + np.maximum(self.crest - self.floor, 0) * s
        gy, gx = np.gradient(H, self.cell)
        rng = np.random.default_rng(5)
        m, hv = np.zeros(self.X.shape, bool), np.zeros(self.X.shape)
        count = 0
        for L in self.lines.values():
            if L.kind != "ridge":
                continue
            d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(L.xy, axis=0), axis=1))]
            pos = every * rng.uniform(0.3, 1.0)
            while pos < d[-1] - every * 0.3:
                i = int(np.searchsorted(d, pos))
                tan = L.xy[min(i + 1, len(L.xy) - 1)] - L.xy[max(i - 1, 0)]
                tan /= np.linalg.norm(tan) + 1e-12
                for side in (1, -1):
                    p = L.xy[i] + side * np.array([-tan[1], tan[0]]) * 3 * self.cell
                    path = [L.xy[i]]
                    for _ in range(int(900 * self.k / self.cell)):
                        iy, ix = int(round((p[1] - self.ys[0]) / self.cell)), int(round((p[0] - self.xs[0]) / self.cell))
                        if not (0 < iy < len(self.ys) - 1 and 0 < ix < len(self.xs) - 1) or low_fix[iy, ix] or self.t[iy, ix] < 0.35:
                            break
                        g = np.array([gx[iy, ix], gy[iy, ix]])
                        if np.linalg.norm(g) < 0.05:
                            break
                        path.append(p.copy())
                        p = p - g / np.linalg.norm(g) * self.cell
                    if len(path) < 8:
                        continue
                    path = np.array(path)
                    hs = self.sample(path, H)
                    relief = hs[0] - hs[-1]
                    u = np.linspace(0, 1, len(path))
                    hs = hs + proud * relief * np.sin(np.pi * np.clip(u * 1.3, 0, 1)) ** 0.7 * (1 - u)
                    ij = np.round((path[:, ::-1] - [self.ys[0], self.xs[0]]) / self.cell).astype(int)
                    ok = ~high_fix[ij[:, 0], ij[:, 1]]
                    ok[:3] = False  # leave the crest itself to the ridge
                    m[ij[ok, 0], ij[ok, 1]] = True
                    hv[ij[ok, 0], ij[ok, 1]] = hs[ok]
                    count += 1
                pos += every * rng.uniform(0.6, 1.4)
        self.rib_count = count
        return (m, hv) if count else None

    def _divides(self, rivers, river_id, high_fix):
        """Crests along the medial line between neighbouring rivers that no authored ridge separates."""
        dist, (iy, ix) = ndimage.distance_transform_edt(river_id == 0, return_indices=True)
        dist *= self.cell
        label = river_id[iy, ix]
        bnd = np.zeros(label.shape, bool)
        bnd[:, 1:] |= label[:, 1:] != label[:, :-1]
        bnd[1:, :] |= label[1:, :] != label[:-1, :]
        near_ridge = ndimage.distance_transform_edt(~high_fix) * self.cell < 3 * self.cell
        cand = bnd & (self.t < 0.5) & ~near_ridge & (dist > 2 * self.cell)
        cand[[0, -1], :] = cand[:, [0, -1]] = False
        if not cand.any():
            return None
        side = np.array([0.0] + [L.props["side"] for L in rivers])[label]
        side = ndimage.minimum_filter(side, 3)
        cap = self.crest.max()
        h = np.minimum(self.floor + dist * side, np.where(self.crest > self.floor + 20 * self.k, self.crest, cap))
        pairs = {}
        la, lb = label, ndimage.maximum_filter(label, 3)
        for a, b, hh in zip(la[cand], lb[cand], h[cand]):
            key = tuple(sorted((rivers[a - 1].name, rivers[max(b, 1) - 1].name)))
            if key[0] != key[1]:
                pairs.setdefault(key, []).append(hh)
        self.divides = [(k, len(v) * self.cell, max(v)) for k, v in pairs.items()]
        self._divide_mask = cand
        return cand, h

    # ------------------------------------------------ addresses
    def address(self, ref):
        """(xy, ground height there, direction or None). See terrain_guide.md for the forms."""
        from . import terrain_design as design
        if isinstance(ref, dict) and "from" in ref:
            xy, _, d = self.address(ref["from"])
            xy = xy + np.array(ref.get("offset", [0, 0]), float)
            return xy, self.height(xy), d
        if isinstance(ref, (list, tuple)):
            xy = np.array(ref[:2], float)
            return xy, self.height(xy), None
        if not isinstance(ref, str):
            raise ValueError(f"bad address {ref!r}")
        if ref in self.points:
            xy = self.points[ref][0]
            return xy, self.height(xy), None
        if ref.startswith("edge:"):  # "edge:w" (its middle) or "edge:w@0.3" (from the south / west end), just inside
            side, _, f = ref[5:].partition("@")
            f = float(f) if f else 0.5
            (x0, y0), (x1, y1) = self.spec["extent"]
            m = 2 * self.cell
            xy = {"w": (x0 + m, y0 + f * (y1 - y0)), "e": (x1 - m, y0 + f * (y1 - y0)),
                  "s": (x0 + f * (x1 - x0), y0 + m), "n": (x0 + f * (x1 - x0), y1 - m)}[side[0]]
            xy = np.array(xy, float)
            inward = {"w": (1, 0), "e": (-1, 0), "s": (0, 1), "n": (0, -1)}[side[0]]
            return xy, self.height(xy), np.array(inward, float)
        if ref == "highest" or ref.startswith("highest:"):
            m = design.region(self, ref.split(":", 1)[1]) > 0.5 if ":" in ref else np.ones(self.X.shape, bool)
            k = int(np.argmax(np.where(m, self.H, -np.inf)))
            xy = self.P[k]
            return xy, self.height(xy), None
        if "_rim" in ref.split("@")[0] and "." in ref and ref.split(".")[0] in getattr(self, "canyons", {}):
            from .terrain_forms import rim_address
            return rim_address(self, ref)
        if ref in getattr(self, "fords", {}):
            xy = np.array(self.fords[ref]["xy"])
            return xy, self.height(xy), None
        if ref in getattr(self, "mesas", {}):
            xy = np.array(self.mesas[ref]["xy"])
            return xy, self.height(xy), None
        if ref.endswith("_shore") and "." in ref:
            lake, side = ref.rsplit(".", 1)
            return self._shore(lake, side[:-len("_shore")])
        if ref in self.sites:
            xy = np.array(self.sites[ref]["xy"])
            return xy, self.height(xy), None
        if ref in self.passes:
            xy = np.array(self.passes[ref]["xy"])
            return xy, self.height(xy), None
        if ref in (self.spec.get("passes") or {}):  # before it's cut
            return self.address(self.spec["passes"][ref]["at"])
        if ref in self.lakes:
            xy = np.array(self.lakes[ref]["xy"])
            return xy, self.height(xy), None
        if "@" in ref:
            name, s = ref.split("@")
            line = self.lines.get(name) or self.routes.get(name)
            if line is None:
                raise ValueError(f"unknown line {name!r} in {ref!r}")
            xy, h, tan = line.at(float(s))
            return xy, self.height(xy), tan
        if "." in ref and ref.rsplit(".", 1)[0] in self.lines:
            name, end = ref.rsplit(".", 1)
            xy, h, tan = self.lines[name].at(0.0 if end == "source" else 1.0)
            return xy, self.height(xy), tan
        if getattr(self, "sea", None) and ref in self.sea.get("beach_at", {}):  # a named beach: its middle on the coast
            xy = np.array(self.sea["beach_at"][ref])
            return xy, self.height(xy), None
        if getattr(self, "sea", None) and ref in self.sea["coves"]:  # a cove: the middle of its bay
            xy = np.array(self.sea["coves"][ref]["xy"])
            return xy, self.height(xy), np.array(self.sea["coves"][ref]["inland"])
        if ref in self.lines or ref in self.routes:  # a line by name: its middle (the whole line for "near" zones)
            xy, h, tan = (self.lines.get(ref) or self.routes[ref]).at(0.5)
            return xy, self.height(xy), tan
        if ref in (self.spec.get("landforms") or {}):
            lf = self.spec["landforms"][ref]
            xy = np.array(lf["_centre"], float) if "_centre" in lf else self._early_xy(ref)  # not built yet
            return xy, self.height(xy), None
        if ref in self.zones or ":" in ref or ref in design.NAMED_REGIONS:
            xy = design.centroid(self, design.region(self, ref))
            return xy, self.height(xy), None
        raise ValueError(f"unknown address {ref!r}")

    def _shore(self, lake, side):
        """The point of a lake's shore furthest toward a compass side, and the direction out of the lake there."""
        dirs = {"north": (0, 1), "south": (0, -1), "east": (1, 0), "west": (-1, 0), "northeast": (1, 1),
                "northwest": (-1, 1), "southeast": (1, -1), "southwest": (-1, -1)}
        d = np.array(dirs[side], float)
        d /= np.linalg.norm(d)
        wet = ~np.isnan(self.water) & (self.lake_id == self.lakes[lake]["id"])
        if not wet.any():
            raise ValueError(f"lake {lake!r} holds no water, so it has no shore")
        if self.lakes[lake].get("sea"):  # the sea's north shore: the coast on the land's north side; inland from there
            land = self.sea["land"]
            coast = wet & ndimage.binary_dilation(~wet & land)
            pts = np.stack([self.X[coast], self.Y[coast]], 1)
            c = np.array([self.X[land].mean(), self.Y[land].mean()])
            k = int(np.argmax((pts - c) @ d))
            inland = c - pts[k]
            return pts[k], self.height(pts[k]), inland / (np.linalg.norm(inland) + 1e-9)
        edge = wet & ~ndimage.binary_erosion(wet)
        pts = np.stack([self.X[edge], self.Y[edge]], 1)
        c = np.array([self.X[wet].mean(), self.Y[wet].mean()])
        k = int(np.argmax((pts - c) @ d))
        return pts[k], self.height(pts[k]), d

    def summit(self, name):
        """A peak's built height: the highest ground within its own top (map, report and probes all use this)."""
        xy, _ = self.points[name]
        p = (self.spec.get("peaks") or {}).get(name) or (self.spec.get("cols") or {}).get(name) or {}
        # within half its top's radius (on a tilt, higher ground uphill inside the whole radius read as its summit)
        r = max(0.5 * float(p.get("radius", 0)), min(40 * self.k, 3 * self.cell), 1.5 * self.cell)
        return float(self.H[np.hypot(self.X - xy[0], self.Y - xy[1]) <= r].max())

    def height(self, xy, H=None):
        H = getattr(self, "H", None) if H is None else H
        if H is None:  # before the ground exists (zones for the base itself): no height yet
            return float("nan")
        return float(self.sample(np.atleast_2d(xy), H)[0])

    def sample(self, xy, H=None):
        H = self.H if H is None else H
        return ndimage.map_coordinates(H, [(xy[:, 1] - self.ys[0]) / self.cell, (xy[:, 0] - self.xs[0]) / self.cell],
                                       order=1, mode="nearest")

    # ------------------------------------------------ landforms
    def _smooth(self, a, r):
        return ndimage.gaussian_filter(a.astype(float), r / self.cell)

    def _landforms(self):
        lfs = self.spec.get("landforms") or {}
        prints = {}
        for name, lf in lfs.items():
            before = self.H.copy()
            getattr(self, "_lf_" + lf["type"])(name, lf)
            prints[name] = np.abs(self.H - before) > 0.5
        names = list(prints)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                both = (prints[a] & prints[b]).sum()
                if both > 0.1 * min(prints[a].sum(), prints[b].sum()) and both > 0:
                    self.warnings.append(f"landform {b!r} overlaps {a!r} ({both * self.cell ** 2 / 1e4:.1f} ha): "
                                         f"{b!r} is applied later and wins where they meet")
        self._prints = prints

    def _lf_lake(self, name, lf):
        """A basin carved to below a level, with a rim (rock bar or dam) up to the level where the ground is lower."""
        xy, _, _ = self.address(lf["at"])
        r = float(lf["radius"])
        # a lobed shoreline, not a circle: distance warped by noise that is smooth in space (warping by bearing
        # alone made radial star points)
        true_d = np.hypot(self.X - xy[0], self.Y - xy[1])
        lobe = noise.fbm(np.c_[self.P, np.full(len(self.P), 7.0)], 0.9 * r, 2, seed=int(xy[0] + xy[1]) % 1000)
        d = true_d + lf.get("lobes", 0.3) * r * 2 * (lobe.reshape(self.X.shape) - 0.5)
        drains = [b for b in self.basins.values() if np.allclose(b["falls"], xy)]
        level = float(lf["level"]) if "level" in lf else (drains[0]["lo"] if drains else self.height(xy))
        depth = float(lf.get("depth", 10))
        target = np.where(d < r, level - depth * np.clip(1 - (d / r) ** 2, 0, 1) ** 1.5 - 0.3,
                          level - 0.3 + 0.35 * (d - r))  # shore banks at ~19 deg rather than a step
        reach = smoothstep(1.6 * r, 1.1 * r, true_d)  # the bank only reshapes the shore, not the hills around it
        before = self.H
        self.H = self.H * (1 - reach) + np.minimum(self.H, self._smooth(target, 10 * self.k)) * reach
        dug = (before - self.H > 20) & (before > level + 20) & (d < r)
        if dug.sum() * self.cell ** 2 > 0.05 * math.pi * r * r:  # a lake is a dug-out disk: say when that ate land
            self.warnings.append(f"lake {name!r}: its disk ({r:.0f} m radius) dug out {_area(dug.sum() * self.cell ** 2)} "
                                 f"of ground standing over 20 m above its level (up to {float((before - self.H).max()):.0f} m "
                                 f"deep): a lake is a basin dug to its level everywhere inside its radius. Make it smaller "
                                 f"or move it off the high ground (for water around land use 'sea')")
        dam = lf.get("dam", True)
        if dam:
            # an embankment wherever the ground (before digging) was below the crest: its inner face rises from the
            # water's edge, a level top, an outer face at 1:2.5 down to the ground. On a slope that is a bank across the
            # downhill side only ("downhill": a farm pond); uphill the dug bank is the shore. (A ring raised on the dug
            # ground left an uphill rim; a separate berm below the pond left a trough and spilled at its ends)
            crest = level + float(lf.get("freeboard", 1.0 if dam == "downhill" else 1.5))
            top = float(lf.get("crest_width", max(3.0, 0.1 * r)))
            rise = crest - (level - 0.3)
            d_in = r + 2.0 * rise
            bank = np.where(d < r, -np.inf, np.where(d < d_in, level - 0.3 + (d - r) / 2.0,
                                                     np.where(d < d_in + top, crest, crest - (d - d_in - top) / 2.5)))
            low = self._smooth(before, 2 * self.cell) < crest
            fill = np.where(low & (true_d < 3 * r), np.minimum(bank, crest), -np.inf)
            self.H = np.maximum(self.H, fill)
        # dam false: a natural lake, holding only what the ground holds (the report says if it leaks)
        self.lakes[name] = {"xy": xy.tolist(), "level": level, "r": r, "id": len(self.lakes) + 1}
        lf["_centre"] = xy.tolist()

    def _lf_fan(self, name, lf):
        """A debris cone where a steep stream meets flatter ground: spreads downslope from the stream's mouth."""
        xy, _, tan = self.address(lf["at"])
        if tan is None:
            raise ValueError(f"fan {name!r}: 'at' must be on a river (e.g. 'burn.mouth') so it knows which way to spread")
        base = self.floor
        v = np.stack([self.X - xy[0], self.Y - xy[1]], -1)
        d = np.linalg.norm(v, axis=-1)
        ahead = (v @ tan) / (d + 1e-9)
        spread = np.clip((ahead + 0.3) / 0.6, 0, 1)
        cone = lf["height"] * np.clip(1 - d / lf["radius"], 0, 1) ** 1.3 * spread * (self.t < 0.5)
        self.H = np.where(cone > 0, np.maximum(self.H, self._smooth(base + cone, 20 * self.k)), self.H)
        lf["_centre"] = (xy + tan * lf["radius"] * 0.35).tolist()

    def _lf_moraine(self, name, lf):
        """A ridge of till across a valley where a glacier's snout stood, bowed downstream, breached by the river."""
        river = lf["across"].split("@")[0]
        xy, _, tan = self.address(lf["across"])
        nrm = np.array([-tan[1], tan[0]])
        v = np.stack([self.X - xy[0], self.Y - xy[1]], -1)
        u, w = v @ tan, v @ nrm
        L = self.lines[river]
        u = u + 0.0006 / self.k * w ** 2
        bump = lf["height"] * np.exp(-(u / lf["width"]) ** 2)
        breach = 1 - np.exp(-(w / (L.props["floor"] * 0.3)) ** 2)
        self.H += bump * breach * np.clip(1 - self.t / 0.45, 0, 1)
        lf["_centre"] = (xy + nrm * L.props["floor"]).tolist()

    def _lf_terrace(self, name, lf):
        """A flat bench on one bank at a height above the river: cuts the slope above, fills below."""
        L = self.lines[lf["along"]]
        side = 1 if lf.get("side", "left") == "left" else -1
        d, i = cKDTree(L.xy).query(self.P)
        d, i = d.reshape(self.X.shape), i.reshape(self.X.shape)
        tan = np.gradient(L.xy, axis=0)
        tan /= np.linalg.norm(tan, axis=1, keepdims=True)
        nrm = np.stack([-tan[:, 1], tan[:, 0]], 1) * side
        v = np.stack([self.X, self.Y], -1) - L.xy[i]
        on_side = (v * nrm[i]).sum(-1) > 0
        inner = L.props["floor"] / 2
        band = np.clip(np.minimum(d - inner, inner + lf["width"] - d) / (30 * self.k) + 0.5, 0, 1)
        along = np.clip(np.minimum(L.s[i] - lf["from"], lf["to"] - L.s[i]) * L.props["length"] / (60 * self.k) + 0.5, 0, 1)
        w = self._smooth(band * along * on_side, 15 * self.k)
        self.H = self.H * (1 - w) + (L.h[i] + lf["height"]) * w
        cxy, _, ctan = L.at((lf["from"] + lf["to"]) / 2)
        lf["_centre"] = (cxy + np.array([-ctan[1], ctan[0]]) * side * (inner + lf["width"] / 2)).tolist()

    def _fill_lakes(self):
        """Each lake fills the ground below its own level connected to its centre. Real water in an enclosed basin
        would rise to the basin's lowest rim; for a designed level that's rarely wanted, so a leak is reported and
        the water kept to the lake's own neighbourhood."""
        self.water[:] = np.nan
        self.lake_id = np.zeros(self.X.shape, int)
        self.warnings = [w for w in self.warnings if not w.startswith("lake ")]  # this runs twice
        for name, lk in self.lakes.items():
            if lk.get("sea"):
                from . import terrain_sea
                wet = terrain_sea.fill(self, lk) & np.isnan(self.water)
                self.water[wet] = lk["level"]
                self.lake_id[wet] = lk["id"]
                lk.update(area=wet.sum() * self.cell ** 2, depth=float((lk["level"] - self.H[wet]).max()) if wet.any() else 0)
                continue
            xy, level, r = np.array(lk["xy"]), lk["level"], lk["r"]
            d = np.hypot(self.X - xy[0], self.Y - xy[1])
            below = self.H < level
            lab, _ = ndimage.label(below)
            near = (d < max(r / 3, 2 * self.cell)) & below
            if not near.any():
                lk.update(area=0, depth=0)
                why = [o for o, p in self._prints.items() if o != name and (p & (d < r)).any()]
                self.warnings.append(f"lake {name!r} holds no water: the ground at its centre is above its level "
                                     f"{level:.0f} m" + (f" (raised by {', '.join(why)})" if why else ""))
                continue
            ids = np.unique(lab[near])
            wet = np.isin(lab, ids[ids > 0])
            def spills(w):
                return (w & (d > 2.5 * r)).any() or w[[0, -1], :].any() or w[:, [0, -1]].any()

            if spills(wet):
                # water finds its own level: the highest that stays in its basin (cropping it at a radius left water
                # standing over land at the crop)
                edge = wet & (d > 1.3 * r)
                k = np.argmin(np.where(edge, d, np.inf))
                lo_l, hi_l = float(self.H[near].min()), level
                for _ in range(14):
                    mid = (lo_l + hi_l) / 2
                    lab2, _ = ndimage.label(self.H < mid)
                    ids2 = np.unique(lab2[near & (self.H < mid)])
                    w2 = np.isin(lab2, ids2[ids2 > 0])
                    lo_l, hi_l = (mid, hi_l) if not spills(w2) else (lo_l, mid)
                self.warnings.append(f"lake {name!r} at {level:.0f} m would spill out near [{self.P[k, 0]:.0f}, "
                                     f"{self.P[k, 1]:.0f}]: its water stands at {lo_l:.1f} m, the most its basin holds; "
                                     f"dam it (\"dam\": true), move it, or lower the level")
                level = lk["level"] = lo_l
                below = self.H < level
                lab, _ = ndimage.label(below)
                near = (d < max(r / 3, 2 * self.cell)) & below
                if not near.any():
                    lk.update(area=0, depth=0)
                    continue
                ids = np.unique(lab[near])
                wet = np.isin(lab, ids[ids > 0])
            self.water[wet] = level
            self.lake_id[wet] = lk["id"]
            lk.update(area=wet.sum() * self.cell ** 2, depth=float((level - self.H[wet]).max()) if wet.any() else 0)
            shore = ndimage.binary_dilation(wet) & ~wet
            lk["freeboard"] = float(self.H[shore].min() - level) if shore.any() else 0
        from . import terrain_forms as forms
        forms.water(self)

    # ------------------------------------------------ processes
    def _texture(self):
        pts = np.c_[self.P, np.zeros(len(self.P))]
        relief = np.minimum(np.maximum(self.crest - self.floor, 0), RELIEF_CAP * self.k)
        steep = np.clip(self._slope() / 35, 0, 1)
        rough = (0.3 + 0.7 * steep) * np.clip(self.t, 0, 1) ** 0.7  # rock high and steep; floors stay smooth
        crestward = 1 - 0.7 * smoothstep(0.85, 1.0, self.t)  # lumps right on a crest read as pinnacles
        W = self.world
        if W["kind"]:
            # landform structure (spur-and-gully systems a few hundred metres apart): part of the proportions, so it
            # scales with the level; wide and moderate (deep narrow flutes were the problem, not structure)
            land = 1 - np.abs(2 * noise.fbm(pts, 0.06 * self.size, 3, seed=3) - 1)
            self.H += rough * crestward * 0.02 * relief * 2 * (land.reshape(self.X.shape) - 0.5)
            # player-scale roughness: metres, by the kind of terrain, never by the relief
            ridged = 1 - np.abs(2 * noise.fbm(pts, 3 * W["crag"], 3, seed=4) - 1)
            fine = noise.fbm(pts, 1.1 * W["crag"], 2, seed=5)
            self.H += rough * crestward * W["bumps"] * 2 * (ridged.reshape(self.X.shape) - 0.5)
            self.H += rough * 0.4 * W["bumps"] * 2 * (fine.reshape(self.X.shape) - 0.5)
            return
        ridged = 1 - np.abs(2 * noise.fbm(pts, 120 * self.k, 3, seed=3) - 1)
        gully = noise.fbm(pts, 45 * self.k, 2, seed=5)
        self.H += rough * 0.03 * relief * crestward * (ridged.reshape(self.X.shape) - 0.5)
        self.H += rough * 4 * self.k * (gully.reshape(self.X.shape) - 0.5)

    # ------------------------------------------------ measuring
    def _slope(self, H=None):
        H = self.H if H is None else H
        gy, gx = np.gradient(H, self.cell)
        return np.degrees(np.arctan(np.hypot(gx, gy)))

    def report(self) -> str:
        from . import terrain_design as design
        from . import terrain_world
        out = terrain_world.report(self) + ["peaks/cols (authored -> built):"]
        cols = self.spec.get("cols") or {}
        for n, (xy, h) in self.points.items():
            built = self.height(xy) if n in cols else self.summit(n)
            out.append(f"  {n}: {h:.0f} m -> {built:.0f} m" + (" (a pass notches it)" if any(
                np.hypot(*(np.array(p["xy"]) - xy)) < p["width"] + 3 * self.cell for p in self.passes.values()) else ""))
        for L in self.lines.values():
            if L.kind != "river":
                continue
            out.append(f"river {L.name}: {L.props['length']:.0f} m, {L.h[0]:.0f} -> {L.h[-1]:.0f} m, "
                       f"mean grade {100 * (L.h[0] - L.h[-1]) / L.props['length']:.1f}%")
            for s in (0.15, 0.5, 0.85):
                xy, h, tan = L.at(s)
                nrm = np.array([-tan[1], tan[0]])
                prof = []
                for side in (1, -1):
                    ds = np.arange(0, 1500 * self.k, self.cell)
                    hs = self.sample(xy + nrm * side * ds[:, None])
                    top = int(np.argmax(hs))
                    wall = hs[: top + 1]
                    lo = int(np.argmax(wall > h + 0.15 * (hs[top] - h)))
                    hi = int(np.argmax(wall > h + 0.85 * (hs[top] - h)))
                    if hi > lo:
                        slope = math.degrees(math.atan((wall[hi] - wall[lo]) / ((hi - lo) * self.cell)))
                    else:  # a short, steep bank: the whole rise over its whole run ("18 m over 10 m (0 deg)" before)
                        slope = math.degrees(math.atan((hs[top] - h) / max(ds[top], self.cell)))
                    prof.append(f"{hs[top] - h:.0f} m over {ds[top]:.0f} m ({slope:.0f} deg)")
                out.append(f"    @{s:.2f}: floor {L.h[np.searchsorted(L.s, s)]:.0f} m; left bank rises {prof[0]}, right {prof[1]}")
        if getattr(self, "rib_count", 0):
            out.append(f"ribs (automatic): {self.rib_count} spurs off the ridges")
        for (a, b), length, top in self.divides:
            out.append(f"divide (automatic) between {a} and {b}: {length:.0f} m of crest, up to {top:.0f} m")
        from . import terrain_sea
        out += terrain_sea.report(self)
        for name, lk in self.lakes.items():
            if lk.get("sea"):
                continue
            out.append(f"lake {name}: level {lk['level']:.0f} m, {lk.get('area', 0) / 1e4:.1f} ha, "
                       f"deepest {lk.get('depth', 0):.0f} m, lowest shore {lk.get('freeboard', 0):+.1f} m above the water")
        out += design.report(self)
        out += self._highest()
        out += self._drainage()
        out += design.intent(self)
        if self.warnings:
            out.append("WARNINGS:")
            out += [f"  {w}" for w in self.warnings]
        return self._in_units("\n".join(out))

    def _in_units(self, text):
        """The report is built in metres; say it in the spec's units (and say when the scale was assumed)."""
        u = self.units
        head = ""
        if u["assumed"]:
            why = f"a typical {self.world['kind'].replace('_', ' ')} level" if self.world["kind"] else "a default"
            head = (f"scale: no units given, so the frame was taken as {self.size:.0f} m across ({why}; "
                    f"1 unit = {u['mu']:.3g} m); set \"units\" or \"across\" to change it. Report in units.\n")
        if u["mu"] == 1.0 and not u["assumed"]:
            return text
        import re
        name, mu = u["name"], u["mu"]

        def num(v, area=False):
            x = float(v) / (mu * mu if area else mu)
            return f"{x:.3g}" if abs(x) < 10 else f"{x:.0f}"

        text = re.sub(r"\[(-?[\d.]+), (-?[\d.]+)\]", lambda m: f"[{num(m[1])}, {num(m[2])}]", text)
        text = re.sub(r"(-?[\d.]+) km2\b", lambda m: f"{num(float(m[1]) * 1e6, True)} sq {name}", text)
        text = re.sub(r"(-?[\d.]+) ha\b", lambda m: f"{num(float(m[1]) * 1e4, True)} sq {name}", text)
        text = re.sub(r"(-?[\d.]+) m2\b", lambda m: f"{num(float(m[1]), True)} sq {name}", text)
        text = re.sub(r"(-?[\d.]+) m\b", lambda m: f"{num(m[1])} {name}", text)
        return head + text

    def _highest(self):
        """The frame's highest ground, and whether it's something the designer placed (the export's height range showed
        an unauthored 134 m ridge in a coast of 70 m clifftops)."""
        k = int(np.argmax(self.H))
        xy, z = self.P[k], float(self.H.ravel()[k])
        line = f"highest ground: {z:.0f} m at [{xy[0]:.0f}, {xy[1]:.0f}]"
        pk = {**(self.spec.get("cols") or {}), **(self.spec.get("peaks") or {})}
        near = [n for n, (p, h) in self.points.items()
                if np.linalg.norm(p - xy) < max(1.5 * float(pk.get(n, {}).get("radius", 0)), 200 * self.k, 5 * self.cell)]
        near += [L.name for L in self.lines.values() if L.kind == "ridge"
                 and cKDTree(L.xy).query(xy)[0] < max(150 * self.k, 4 * self.cell)]
        top_authored = max([h for _, h in self.points.values()] + [float(L.h.max()) for L in self.lines.values()
                                                                   if L.kind == "ridge"] + [-np.inf])
        if near:
            return [line + f" ({', '.join(near[:2])})"]
        self.warnings.append(line + " is nothing you placed" + (f", {z - top_authored:.0f} m above your highest point"
                                                             if np.isfinite(top_authored) and z > top_authored else "")
                             + ": the tilt, a frame edge or automatic divides/ribs made it; probe it, or lower it with "
                               "\"border\" or the tilt")
        return [line + " (unauthored)"]

    def _drainage(self):
        """Pits (water can't leave, not a lake) and big unauthored streams (flow gathering away from the rivers)."""
        H = np.where(np.isnan(self.water), self.H, self.water)
        base = ~np.isnan(self.water)
        base[[0, -1], :] = base[:, [0, -1]] = True
        rec, dist, levels = _receivers(H, self.cell, base)
        import fastscapelib as fs  # its priority flood (skimage's reconstruction was pathologically slow on a tilt)
        grid = fs.RasterGrid(list(H.shape), [self.cell, self.cell], fs.NodeStatus.FIXED_VALUE)
        filled = fs.FlowGraph(grid, [fs.SingleFlowRouter(), fs.PFloodSinkResolver()]).update_routes(H.copy())
        depth = np.asarray(filled).reshape(H.shape) - H  # how deep water would stand (depression fill)
        hollows = (depth > 1.0) & np.isnan(self.water)
        hollows = ndimage.binary_opening(hollows)  # specks of a cell or two aren't worth a line
        lab_h, n_h = ndimage.label(hollows)
        area = _accumulate(rec, levels, self.cell).reshape(H.shape)
        near = np.zeros(H.shape, bool)
        for L in self.lines.values():
            if L.kind == "river":
                m, _ = self._stamp(L, L.props["floor"] / 2 + 80 * self.k)
                near |= m
        stray = (area > 250_000 * self.k ** 2) & ~near & np.isnan(self.water)
        for sn, st in self.sites.items():  # water running through a pad: it floods the village (unwarned before)
            pad = np.hypot(self.X - st["xy"][0], self.Y - st["xy"][1]) <= st["radius"]
            big = pad & (area > 100_000 * self.k ** 2) & np.isnan(self.water)
            if big.any():
                self.warnings.append(f"site {sn!r}: a stream draining {_area(float(area[big].max()))} runs through the pad: "
                                     f"move the site, give the stream a river, or accept a culvert")
        lab, n = ndimage.label(stray)
        out = [f"drainage: {n_h} hollows over 1 m deep outside lakes (would hold water)"]
        if n_h:
            big = ndimage.sum(np.ones(H.shape), lab_h, range(1, n_h + 1))
            said = set()
            for k in np.argsort(-big)[:3]:
                yy, xx = np.nonzero(lab_h == k + 1)
                closed = [n for n, b in self.basins.items() if b["floor"][yy, xx].mean() > 0.5]
                if closed and closed[0] in said:
                    continue
                said.add(closed[0]) if closed else None
                if closed:
                    top = float((H[yy, xx] + depth[yy, xx]).max())
                    out.append(f"  basin {closed[0]} is enclosed: real water would rise to {top:.0f} m and spill at its "
                               f"lowest rim point; the lake keeps its own level (fine for a designed level)")
                    continue
                out.append(f"  hollow {_area(big[k] * self.cell ** 2)}, {depth[yy, xx].max():.1f} m deep at "
                           f"[{self.xs[xx].mean():.0f}, {self.ys[yy].mean():.0f}]")
        if n:
            sizes = ndimage.maximum(area, lab, range(1, n + 1))
            said = []
            for k in np.argsort(-sizes):
                yy, xx = np.nonzero(lab == k + 1)
                j = np.argmax(area[yy, xx])
                p = np.array([self.xs[xx[j]], self.ys[yy[j]]])
                if any(np.linalg.norm(p - q) < 100 * self.k for q in said):  # one stream, not three reports of it
                    continue
                said.append(p)
                out.append(f"  unauthored stream draining {_area(area[yy[j], xx[j]])} at [{p[0]:.0f}, {p[1]:.0f}]")
                if len(said) == 3:
                    break
        return out

    def export(self, out_dir, size: int | None = None, engine: str | None = None):
        """For an engine, north-up: height (float32 .npy absolute, 16-bit PNG and a Unity .raw both offset to 0 with the
        range in meta.json), an 8-bit density mask per cover layer, water, roads, sites, playable and walls masks,
        splat weights for the ground layers (tree layers are instances, not ground textures), trees.csv, and meta.json
        with everything placed (sites with their planes, passes, routes, rivers with their water, fords, lakes).
        `size` resamples to an engine grid along the longer side (Unity 257/513/1025/2049: 2^n + 1; Unreal 505/1009/
        2017); `engine` "unity" picks the next 2^n + 1 when no size is given."""
        from PIL import Image
        from . import terrain_design as design
        out = Path(out_dir)
        (out / "masks").mkdir(parents=True, exist_ok=True)
        ny, nx = self.H.shape
        n = max(nx, ny)
        if not size and engine == "unity":
            size = 2 ** math.ceil(math.log2(max(n - 1, 32))) + 1
        k = (size - 1) / (n - 1) if size else 1.0
        # engines want square heightmaps (Unity 2^n+1): a non-square frame is padded on its short side with the edge
        # continued, and meta.json says which part is the level
        pad = (n - ny, n - nx) if size else (0, 0)
        shape = (size, size) if size else (ny, nx)

        def grid(a, order=1):
            a = a[::-1].astype(np.float32)
            if size and any(pad):
                a = np.pad(a, ((0, pad[0]), (0, pad[1])), mode="edge")
            if not size:
                return a
            yy, xx = np.meshgrid(np.linspace(0, n - 1, shape[0]), np.linspace(0, n - 1, shape[1]), indexing="ij")
            return ndimage.map_coordinates(a, [yy, xx], order=order, mode="nearest").astype(np.float32)

        H = grid(self.H, 3)
        lo, hi = float(H.min()), float(H.max())
        np.save(out / "height.npy", H)
        q = np.round((H - lo) / max(hi - lo, 1e-6) * 65535).astype(np.uint16)
        Image.fromarray(q).save(out / "height.png")
        # Unity's RAW import: 16-bit little-endian ("Windows" byte order), first row = the south edge (z = 0)
        q[::-1].astype("<u2").tofile(out / "height.raw")

        def mask(name, m):
            Image.fromarray((np.clip(grid(m), 0, 1) * 255).astype(np.uint8)).save(out / "masks" / f"{name}.png")

        for name, m in self.cover.items():
            mask(name, m)  # densities (for trees, detail), each 0..1 on its own
        # splat weights for the ground layers, painted in order, each over what's below; "ground" is what's left; they
        # sum to 1. Tree layers are instances (trees.csv) and stay out: a forest's weight had painted its ground green
        ground = [nm for nm in self.cover if not design.tree_kind(self, nm)]
        rest = np.ones(self.X.shape)
        weights = {}
        for name in reversed(ground):
            weights[name] = self.cover[name] * rest
            rest = rest * (1 - self.cover[name])
        weights["ground"] = rest
        order = ground + ["ground"]
        for i in range(0, len(order), 4):
            chans = [grid(weights[nm]) for nm in order[i:i + 4]]
            while len(chans) < 4:
                chans.append(np.zeros_like(chans[0]))
            rgba = (np.clip(np.stack(chans, -1), 0, 1) * 255).astype(np.uint8)
            Image.fromarray(rgba, "RGBA").save(out / f"splat{i // 4}.png")
        inst = design.trees(self)
        with open(out / "trees.csv", "w") as f:
            f.write("x,y,z,kind,layer\n")
            layers = getattr(self, "tree_layers", {})
            for x, y, z, li in inst:
                nm, kind = layers.get(int(li), ("", ""))
                f.write(f"{x:.2f},{y:.2f},{z:.2f},{kind},{nm}\n")
        dry = np.isnan(self.water)
        mask("water", ~dry)
        roads = self.masks.get("routes", np.zeros(self.X.shape))
        mask("roads", roads)
        mask("sites", self.masks.get("sites", np.zeros(self.X.shape)))
        walls, inside = np.zeros(self.X.shape), np.zeros(self.X.shape, bool)
        for W in self.walls.values():
            inside |= W["inside"]
            s = ndimage.distance_transform_edt(~W["inside"]) * self.cell
            walls = np.maximum(walls, (s > 0) & (s <= W["band"] + self.cell))
        gates = np.zeros(self.X.shape, bool)
        for p in self.passes.values():
            gates |= p["corridor"]
        ways = gates | (roads > 0.5)  # the way in is the road as built, not only the pass's straight notch
        walkable = dry & (self._slope() <= 45)
        # playable: inside the walls (and along the roads and passes that lead in); with no walls, walkable dry ground
        playable = (inside | ways) if self.walls else (walkable | ways)
        mask("playable", playable & (dry | ways))
        mask("walls", walls * ~ways)
        cell = self.cell / k
        (x0, y0), (x1, y1) = self.spec["extent"]
        span = (n - 1) * self.cell  # the square the grid covers (padded frames reach past the level)
        rivers = {}
        for nm, L in self.lines.items():
            if L.kind != "river":
                continue
            rw = getattr(self, "river_water_lines", {}).get(nm)
            pts = [[*map(float, xy), float(h)] for xy, h in zip(L.xy[::4], L.h[::4])]
            river = {"bed_xyz": [[round(v, 2) for v in p] for p in pts]}
            if rw is not None:
                river["water"] = [[round(float(x), 2), round(float(y), 2), round(float(z), 2), round(float(w), 2)]
                                  for (x, y), z, w in zip(rw["xy"][::4], rw["level"][::4], rw["width"][::4])]
            rivers[nm] = river
        meta = {"extent": self.spec["extent"], "cell": cell, "height_range": [lo, hi], "size": [H.shape[1], H.shape[0]],
                "north_up": True, "pixel_0_0": "north-west corner",
                "height_npy": "float32, absolute metres, north-up",
                "height_png": "16-bit, north-up, offset to 0: height = lo + value / 65535 * (hi - lo)",
                "unity": {"raw": "height.raw", "resolution": H.shape[0], "depth": 16, "byte_order": "Windows (little-endian)",
                          "flip_vertically": False, "rows": "first row is the south edge",
                          "terrain_size": [span, hi - lo, span], "position": [x0, lo, y1 - span],
                          "axes": "Unity x = east, z = north, y = up"},
                "level_pixels": [int(round((nx - 1) * k)) + 1, int(round((ny - 1) * k)) + 1],
                "padded": "the level is the top-left part; the rest continues its edges" if any(pad) else "",
                "splat": {f"splat{i // 4}.png": order[i:i + 4] for i in range(0, len(order), 4)},
                "masks": {"water": "open water", "roads": "road beds", "sites": "site pads", "walls": "wall faces",
                          "playable": "inside the walls and along the ways in" if self.walls else
                          "dry ground a person can walk (45 deg or less) and the roads",
                          **{nm: "density 0..1" for nm in self.cover}},
                "trees": "trees.csv (x, y, z, kind, layer), world metres; tree layers aren't in the splats",
                "rivers": rivers, "rivers_water": "per point [x, y, water surface z, water width m] (0 where it's dry "
                                                  "or in a lake)",
                "fords": {nm: {"at": f["xy"], "river": f["river"], "width": f["width"], "depth": f["depth"],
                               "bed": round(self.height(f["xy"]), 2)} for nm, f in getattr(self, "fords", {}).items()},
                "cover": {nm: (self.spec.get("cover") or {}).get(nm, {}).get("type", nm) for nm in self.cover},
                "lakes": {nm: {"level": lk["level"], "at": lk["xy"], **({"sea": True} if lk.get("sea") else {})}
                          for nm, lk in self.lakes.items()},
                "sites": {nm: {"at": st["xy"], "level": st["level"], "radius": st["radius"], "fall": st.get("fall", 0.0),
                               "falls_toward": st.get("toward", [0, 0]),
                               "plane": "z = level - fall * ((x - at.x) * falls_toward.x + (y - at.y) * falls_toward.y)"}
                          for nm, st in self.sites.items()},
                "passes": {nm: {"at": p["xy"], "saddle": round(self.height(np.array(p["xy"])), 2), "width": p["width"]}
                           for nm, p in self.passes.items()},
                "routes": {nm: {"width": L.props["width"], "points_xyz": np.c_[L.xy, L.h][::2].round(2).tolist()}
                           for nm, L in self.routes.items()}}
        (out / "meta.json").write_text(json.dumps(meta, indent=1))
        return out


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


# ---------------------------------------------------------------- views

def _font(size):
    from PIL import ImageFont
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def ground_colours(T: Terrain, cover: bool = True) -> np.ndarray:
    """sRGB per cell: bare ground by slope and height, then each cover layer over it (its preview colour x
    density), water on top."""
    from . import terrain_design as design
    slope = T._slope()
    hn = (T.H - T.H.min()) / max(np.ptp(T.H), 1)
    arid = T.world["kind"] in ("canyon", "dunes", "plateau")
    bare = np.array([0.66, 0.52, 0.36]) if arid else np.array([0.40, 0.47, 0.26])  # bare ground: sandstone or grass
    grass = bare * (1 - 0.3 * hn[..., None]) + np.array([0.10, 0.07, 0.02]) * hn[..., None]
    rock = (np.array([0.58, 0.38, 0.26]) if arid else np.array([0.36, 0.34, 0.31])) + 0.06 * hn[..., None]
    if arid and getattr(T, "canyons", None):
        cy = next(iter(T.canyons.values()))
        per = max(cy["depth"] / 7, 4.0)  # colour bands through the strata, level all along the canyon
        band = 0.5 + 0.5 * np.sin(2 * np.pi * T.H / per) + 0.25 * np.sin(2 * np.pi * T.H / (per * 0.37))
        rock = rock * (0.8 + 0.25 * band[..., None]) + np.array([0.08, 0.02, -0.02]) * (band[..., None] - 0.5)
    w = smoothstep(28, 40, slope)[..., None]
    c = grass * (1 - w) + rock * w
    if cover:
        for name, m in T.cover.items():
            col = np.array(design.cover_colour(T, name))
            a = np.clip(m, 0, 1)[..., None]  # density 1 covers the ground (at 85% black sand showed as grass)
            c = c * (1 - a) + col * a
    c[~np.isnan(T.water)] = [0.16, 0.28, 0.38]
    return c


def _nice(x):
    """1, 2 or 5 times a power of ten, near x."""
    e = 10 ** math.floor(math.log10(x))
    return min((1, 2, 5, 10), key=lambda m: abs(m * e - x)) * e


def map_image(T: Terrain, px: int = 1100, contour: float | None = None, labels: bool = True):
    """A plan view to reason on: hillshade over ground/cover colour, contours (index every 5th), rivers, ridges,
    divides, routes, sites, walls (red where climbable), names and a cover legend."""
    from PIL import Image, ImageDraw
    from skimage import measure
    from . import terrain_design as design
    H = T.H
    contour = contour or _nice(max(np.ptp(H), 1) / 20)
    gy, gx = np.gradient(H, T.cell)
    az, el = math.radians(315), math.radians(40)
    L = np.array([math.cos(el) * math.sin(az), math.cos(el) * math.cos(az), math.sin(el)])
    n = np.stack([-gx, -gy, np.ones_like(H)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    shade = np.clip(n @ L, 0, 1)
    rgb = ground_colours(T) * (0.45 + 0.7 * shade[..., None])
    img = Image.fromarray((np.clip(rgb[::-1], 0, 1) * 255).astype(np.uint8))
    sc = px / img.width
    img = img.resize((px, int(img.height * sc)), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    ny = H.shape[0]

    def to_px(x, y):
        return ((x - T.xs[0]) / T.cell * sc, (ny - 1 - (y - T.ys[0]) / T.cell) * sc)

    flat = T._slope() < 1.5  # a contour wandering over dead-flat ground (a mesa's caprock, a pad) is noise: a false ring
    for m in getattr(T, "mesas", {}).values():
        flat |= ndimage.binary_dilation(m["topmask"], iterations=1)
    for lev in np.arange(math.ceil(H.min() / contour) * contour, H.max(), contour):
        index = int(round(lev / contour)) % 5 == 0
        for cnt in measure.find_contours(H, lev):
            cnt = cnt[::2]
            on = ~flat[np.clip(np.round(cnt[:, 0]).astype(int), 0, ny - 1),
                       np.clip(np.round(cnt[:, 1]).astype(int), 0, H.shape[1] - 1)]
            lab, n = ndimage.label(on)
            for k in range(1, n + 1):
                pts = [(c[1] * sc, (ny - 1 - c[0]) * sc) for c in cnt[lab == k]]
                if len(pts) > 1:
                    d.line(pts, fill=(60, 40, 20) if index else (95, 75, 50), width=2 if index else 1)
    for Lr in T.lines.values():
        pts = [to_px(*p) for p in Lr.xy[::2]]
        if Lr.kind == "river":
            d.line(pts, fill=(40, 110, 200), width=3)
        else:
            for a in range(0, len(pts) - 1, 4):
                d.line(pts[a:a + 3], fill=(120, 30, 30), width=2)
    if getattr(T, "_divide_mask", None) is not None:
        yy, xx = np.nonzero(T._divide_mask[::2, ::2])
        for y, x in zip(yy, xx):
            px_, py_ = to_px(T.xs[2 * x], T.ys[2 * y])
            d.point((px_, py_), fill=(150, 60, 60))
    for name, w in T.walls.items():
        for (x, y), ok in zip(w["boundary"], w["ok"]):
            px_, py_ = to_px(x, y)
            col = (70, 20, 20) if ok else (255, 40, 40)
            d.ellipse([px_ - 1.5, py_ - 1.5, px_ + 1.5, py_ + 1.5], fill=col)
    for name, R in T.routes.items():
        d.line([to_px(*p) for p in R.xy[::2]], fill=(235, 140, 20), width=3)
    f, fb = _font(15), _font(17)

    def label(xy, text, col=(0, 0, 0)):
        x, y = to_px(*xy)
        d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=col)
        d.text((x + 6, y - 9), text, fill=col, font=f, stroke_width=2, stroke_fill=(255, 255, 255))

    if labels:
        for name, s in T.sites.items():
            x, y = to_px(*s["xy"])
            r = s["radius"] / T.cell * sc
            d.ellipse([x - r, y - r, x + r, y + r], outline=(160, 40, 160), width=2)
            label(s["xy"], f"{name} {s['level']:.0f}", (110, 20, 110))
        cols = T.spec.get("cols") or {}
        for name, (xy, h) in T.points.items():  # a col is labelled with the ground at it, a peak with its top
            label(xy, f"{name} {(T.height(xy) if name in cols else T.summit(name)):.0f}")
        for name, p in T.passes.items():
            label(p["xy"], f"{name} {T.height(np.array(p['xy'])):.0f}", (150, 70, 0))
        for name, m in getattr(T, "mesas", {}).items():
            label(m["xy"], f"{name} {float(np.median(T.H[m['topmask']])):.0f}")
        for Lr in T.lines.values():
            if Lr.kind == "river":
                label(Lr.at(0.5)[0], Lr.name, (20, 60, 150))
        for name, lf in (T.spec.get("landforms") or {}).items():
            if "_centre" in lf and name not in T.lakes:
                label(lf["_centre"], name, (90, 20, 90))
        for name, lk in T.lakes.items():
            label(lk["xy"], f"{name} {lk['level']:.0f}", (10, 50, 110))
        for name, R in T.routes.items():
            label(R.at(0.5)[0], name, (150, 70, 0))
        for name, it in (T.spec.get("intent") or {}).items():
            if "path" in it:
                d.line([to_px(*T.address(a)[0]) for a in it["path"]], fill=(235, 140, 20), width=1)
        W = img.width
        mu, un = T.units["mu"], T.units["name"]
        blen = _nice(T.size / mu / 4)  # in the spec's units
        bar = blen * mu * sc / T.cell
        d.rectangle([20, img.height - 30, 20 + bar, img.height - 22], fill=(0, 0, 0))
        d.text((24 + bar, img.height - 36), f"{blen:g} {un}", fill=(0, 0, 0), font=fb, stroke_width=2,
               stroke_fill=(255, 255, 255))
        d.text((W - 40, 12), "N", fill=(0, 0, 0), font=fb, stroke_width=2, stroke_fill=(255, 255, 255))
        d.polygon([(W - 34, 34), (W - 40, 50), (W - 28, 50)], fill=(0, 0, 0))
        d.text((20, 12), f"contours {contour / T.units['mu']:g} {T.units['name']}", fill=(0, 0, 0), font=f,
               stroke_width=2, stroke_fill=(255, 255, 255))
        y0 = 36
        for name in T.cover:
            col = tuple(int(255 * v) for v in design.cover_colour(T, name))
            d.rectangle([20, y0, 36, y0 + 14], fill=col, outline=(0, 0, 0))
            d.text((42, y0 - 2), name, fill=(0, 0, 0), font=f, stroke_width=2, stroke_fill=(255, 255, 255))
            y0 += 20
    return img


def mask_sheet(T: Terrain, px: int = 360):
    """Every cover mask as a greyscale tile (white = 1) over faint hillshade, labelled: to judge each on its own."""
    from PIL import Image, ImageDraw
    gy, gx = np.gradient(T.H, T.cell)
    shade = np.clip(0.6 + 0.4 * (-gx + gy) / (np.hypot(gx, gy) + 0.3), 0, 1)
    tiles = []
    for name, m in T.cover.items():
        v = (0.25 * shade + 0.75 * np.clip(m, 0, 1))[::-1]
        im = Image.fromarray((v * 255).astype(np.uint8)).convert("RGB")
        im = im.resize((px, int(im.height * px / im.width)), Image.LANCZOS)
        from . import terrain_design as design
        c = (T.spec.get("cover") or {}).get(name, {})
        lab = (f"{name} (~{c['count']} trees; each dot is one)" if c.get("count") and design.tree_kind(T, name)
               else f"{name} ({100 * m.mean():.0f}%)")
        if c.get("count") and design.tree_kind(T, name):  # a few trees' density is too faint to see: draw the mask full
            v = (0.25 * shade + 0.75 * np.clip(m / max(m.max(), 1e-6), 0, 1))[::-1]
            im = Image.fromarray((v * 255).astype(np.uint8)).convert("RGB")
            im = im.resize((px, int(im.height * px / im.width)), Image.LANCZOS)
        ImageDraw.Draw(im).text((8, 6), lab, fill=(255, 60, 60), font=_font(16),
                                stroke_width=2, stroke_fill=(0, 0, 0))
        tiles.append(im)
    if not tiles:
        return None
    cols = min(3, len(tiles))
    rows = math.ceil(len(tiles) / cols)
    sheet = Image.new("RGB", (cols * px, rows * tiles[0].height), (30, 30, 30))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * px, (i // cols) * tiles[0].height))
    return sheet


def write_mesh(T: Terrain, path, step: int = 1):
    """Grid mesh npz: verts, faces, linear colours, per-vertex tree densities; a water mesh for lakes."""
    from . import terrain_design as design
    H = T.H[::step, ::step]
    X, Y = T.X[::step, ::step], T.Y[::step, ::step]
    ny, nx = H.shape
    verts = np.stack([X.ravel(), Y.ravel(), H.ravel()], 1)
    i = np.arange(ny * nx).reshape(ny, nx)
    a, b, c, e = i[:-1, :-1].ravel(), i[:-1, 1:].ravel(), i[1:, 1:].ravel(), i[1:, :-1].ravel()
    faces = np.concatenate([np.stack([a, b, c], 1), np.stack([a, c, e], 1)])
    col = ground_colours(T)[::step, ::step].reshape(-1, 3)
    col = np.where(col <= 0.04045, col / 12.92, ((col + 0.055) / 1.055) ** 2.4)
    inst = design.trees(T)  # the same instances the export writes
    Wt = T.water[::step, ::step]
    wet = ~np.isnan(Wt)
    wv = verts.copy()
    if wet.any():
        _, (iy, ix) = ndimage.distance_transform_edt(~wet, return_indices=True)  # levels differ along a river
        wv[:, 2] = Wt[iy, ix].ravel()
    q = (wet[:-1, :-1] | wet[:-1, 1:] | wet[1:, 1:] | wet[1:, :-1]).ravel()
    wf = np.concatenate([np.stack([a, b, c], 1)[q], np.stack([a, c, e], 1)[q]])
    np.savez(path, verts=verts.astype(np.float32), faces=faces.astype(np.int32), colors=col.astype(np.float32),
             wverts=wv.astype(np.float32), wfaces=wf.astype(np.int32),
             tree_xyz=inst[:, :3].astype(np.float32),
             tree_kind=np.array([getattr(T, "tree_layers", {}).get(int(i), ("", "broadleaf"))[1] for i in inst[:, 3]]),
             span=np.float32(max(np.ptp(T.X), np.ptp(T.Y))), base=np.float32(T.H.min()),
             sea=np.float32(T.sea["level"] if getattr(T, "sea", None) else np.nan))


def render(T: Terrain, out_dir, views: list[dict], size=(1200, 700), samples=24):
    """Perspective Cycles renders: views are {"name", "eye": address | [x, y, z], "lift": m, "look": address, "fov"}."""
    import subprocess
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mesh = out_dir / "terrain_mesh.npz"
    write_mesh(T, mesh)
    jobs = []
    T.view_notes = []
    for v in views:
        exy, eh, _ = T.address(v["eye"])
        if isinstance(v["eye"], list) and len(v["eye"]) == 3:
            eh = v["eye"][2]
        wl = T.water.ravel()[int(np.clip(round((exy[1] - T.ys[0]) / T.cell), 0, len(T.ys) - 1)) * len(T.xs)
                                           + int(np.clip(round((exy[0] - T.xs[0]) / T.cell), 0, len(T.xs) - 1))]
        if np.isfinite(wl) and not (isinstance(v["eye"], list) and len(v["eye"]) == 3):
            eh = max(eh, float(wl))  # over water the eye stands on its surface, not on the bed (it rendered underwater)
        ez = eh + v.get("lift", 2)
        # never inside the ground: at least a person's eye above the highest ground within a few cells (on a slope the
        # ground beside the eye is higher than under it, and the near plane cut through it)
        near = np.hypot(T.X - exy[0], T.Y - exy[1]) <= 2.5 * T.cell
        floor = float(T.H[near].max()) if near.any() else T.height(exy)
        if ez < floor + 1.0:
            T.view_notes.append(f"view {v['name']!r}: the eye was {floor - ez:+.1f} m against the ground there: raised "
                                f"to {floor + 1.7:.0f} m")
            ez = floor + 1.7
        txy, th, _ = T.address(v["look"])
        # and not facing a wall: the first stretch toward what it looks at must clear the ground (an eye clear of the
        # ground under it but a few metres from a cliff rendered black)
        dvec = np.array(txy) - np.array(exy)
        dist = float(np.linalg.norm(dvec))
        if dist > 1:
            ds = np.arange(T.cell, min(60.0, 0.3 * dist), T.cell / 2)
            if len(ds):
                pts = np.array(exy) + dvec / dist * ds[:, None]
                ray = ez + (th - ez) * ds / dist
                need = float((T.sample(pts) + 1.0 - ray).max())
                if need > 0:
                    T.view_notes.append(f"view {v['name']!r}: the ground just ahead toward {v['look']!r} was in the way: "
                                        f"the eye was raised {need:.0f} m to see past it")
                    ez += need
        jobs.append({"eye": [*exy, ez], "look": [*txy, th], "fov": v.get("fov", 60),
                     "out": str(out_dir / f"{v['name']}.png")})
    job = out_dir / "job.json"
    job.write_text(json.dumps({"mesh": str(mesh), "views": jobs, "size": size, "samples": samples}))
    script = Path(__file__).with_name("blender_terrain.py")
    r = subprocess.run(["blender", "-b", "--factory-startup", "--python", str(script), "--", str(job)],
                       capture_output=True, text=True)
    if r.returncode or "Traceback" in r.stdout + r.stderr:  # Blender exits 0 after a Python error
        raise RuntimeError(r.stderr[-2000:] + r.stdout[-3000:])
    return [j["out"] for j in jobs]


def load(path) -> Terrain:
    return Terrain(json.loads(Path(path).read_text()))
