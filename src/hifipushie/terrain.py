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
 3. texture and dissection (coarse-grid stream power, upsampled), capped so big relief doesn't grow pinnacles.
 4. landforms (lake basins carve to a level and dam it, fans, moraines, terraces); overlaps are reported.
 5. design (terrain_design): walls, sites, routes: they reshape the ground, in that order.
 6. lakes fill to their own level (not a global depression fill: an enclosed valley isn't one big lake).
 7. cover masks from the final ground.
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

PROFILES = {"V": 1.0, "U": 2.2, "gorge": 0.6, "open": 1.5}
SIDE_GRADE = {"V": 0.45, "U": 0.6, "gorge": 0.8, "open": 0.12}  # how fast an automatic divide rises
CRESTS = {"arete": 0.0, "rounded": 1.0}
RELIEF_CAP = 600.0  # texture/lumpiness scale with relief up to this: beyond it they made pinnacles


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
        self.spec = spec
        (x0, y0), (x1, y1) = spec["extent"]
        self.cell = c = float(spec.get("cell", 10))
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
        self.masks: dict[str, np.ndarray] = {}   # what each design element occupies (sites, routes, ...)
        self.water = np.full(self.X.shape, np.nan)
        self._ridges()
        self._rivers()
        self.H = self._base()
        self.H0 = self.H.copy()
        self._texture()
        self._dissect()
        self._landforms()
        self._fill_lakes()  # lake shores are addresses sites use
        design.apply(self)
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
        if len(ref) != 3:
            raise ValueError(f"a ridge point needs a height: [x, y, z], got {ref}")
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
        n = noise.fbm(np.c_[d / 1.0, np.zeros((len(d), 2))], 350, 3, seed=97 + seed) - 0.5
        env = np.zeros(len(xy))
        for a, b in zip(ki[:-1], ki[1:]):
            span = d[b] - d[a]
            env[a:b + 1] = np.sin(np.pi * np.linspace(0, 1, b - a + 1)) * min(0.07 * span, 150)
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
                    "floor": float(v.get("floor", 30)), "length": length,
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
        rivers = [L for L in self.lines.values() if L.kind == "river"]
        for k, L in enumerate(rivers, 1):
            m, i = self._stamp(L, L.props["floor"] / 2)
            if L.props["hanging"]:  # the lip: leave the last stretch free, so the step is steep, not a wall
                into = self.lines[L.props["into"]].props["floor"]
                m &= (1 - L.s[i]) * L.props["length"] > 3 * L.props["hanging"] + into / 2
            low_fix |= m; low[m] = L.h[i[m]]; prof[m] = L.props["p"]
            self._fixed_river |= m
            river_id[m] = k
        for L in self.lines.values():
            if L.kind == "ridge":
                m, i = self._stamp(L, 0)
                high_fix |= m; high[m] = L.h[i[m]]; crest[m] = L.props["crest"]
                low_fix &= ~m  # a ridge reaching the frame's edge stays a ridge
        if not high_fix.any():
            raise ValueError("no ridges: the ground rises from rivers to ridge crests, so at least one ridge is needed")

        def solve():
            t, = self._solve(low_fix | high_fix, [np.where(high_fix, 1.0, 0.0)])
            self.floor, self.prof = self._solve(low_fix, [low, prof]) if low_fix.any() else (
                np.full(shape, low[low_fix].min() if low_fix.any() else 0.0), prof)
            self.crest, self.round = self._solve(high_fix, [high, crest])
            self.t = np.clip(t, 0, 1)

        if not low_fix.any():
            raise ValueError("nothing low: add a river or give the frame's edge a height (\"border\")")
        solve()
        self.divides = []
        extra = []
        if self.spec.get("divides", True) and len(rivers) > 1:
            add = self._divides(rivers, river_id, high_fix)
            if add is not None:
                extra.append(add)
        if self.spec.get("ribs", True):
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
        return self.floor + np.maximum(self.crest - self.floor, 0) * s

    def _ribs(self, high_fix, low_fix):
        """Spurs running down from every ridge at irregular spacing: they break long mountain walls into
        spur-and-gully, which harmonic slopes (smooth between crest and floor) never have. Each rib is traced
        downhill on the first solution and stands a little proud of it, fading out toward the valley."""
        cfg = self.spec.get("ribs") if isinstance(self.spec.get("ribs"), dict) else {}
        every, proud = cfg.get("every", 320.0), cfg.get("proud", 0.07)
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
                    for _ in range(int(900 / self.cell)):
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
        h = np.minimum(self.floor + dist * side, np.where(self.crest > self.floor + 20, self.crest, cap))
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
        if ref == "highest" or ref.startswith("highest:"):
            m = design.region(self, ref.split(":", 1)[1]) > 0.5 if ":" in ref else np.ones(self.X.shape, bool)
            k = int(np.argmax(np.where(m, self.H, -np.inf)))
            xy = self.P[k]
            return xy, self.height(xy), None
        if ref.endswith("_shore") and "." in ref:
            lake, side = ref.rsplit(".", 1)
            return self._shore(lake, side[:-len("_shore")])
        if ref in self.sites:
            xy = np.array(self.sites[ref]["xy"])
            return xy, self.height(xy), None
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
        if ref in (self.spec.get("landforms") or {}):
            xy = np.array(self.spec["landforms"][ref]["_centre"], float)
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
        edge = wet & ~ndimage.binary_erosion(wet)
        pts = np.stack([self.X[edge], self.Y[edge]], 1)
        c = np.array([self.X[wet].mean(), self.Y[wet].mean()])
        k = int(np.argmax((pts - c) @ d))
        return pts[k], self.height(pts[k]), d

    def height(self, xy, H=None):
        H = self.H if H is None else H
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
        # a lobed shoreline, not a circle: the radius wanders with the bearing
        ang = np.arctan2(self.Y - xy[1], self.X - xy[0])
        lobe = noise.fbm(np.stack([np.cos(ang).ravel() * 3, np.sin(ang).ravel() * 3, np.zeros(ang.size)], 1), 1.0, 3,
                         seed=int(xy[0] + xy[1]) % 1000).reshape(ang.shape)
        d = np.hypot(self.X - xy[0], self.Y - xy[1]) / (1 + lf.get("lobes", 0.35) * 2 * (lobe - 0.5))
        level = float(lf["level"]) if "level" in lf else self.height(xy)
        depth = float(lf.get("depth", 10))
        target = np.where(d < r, level - depth * np.clip(1 - (d / r) ** 2, 0, 1) ** 1.5 - 0.3,
                          level - 0.3 + 0.35 * (d - r))  # shore banks at ~19 deg rather than a step
        reach = smoothstep(1.6 * r, 1.1 * r, d)  # the bank only reshapes the shore, not the hills around it
        self.H = self.H * (1 - reach) + np.minimum(self.H, self._smooth(target, 10)) * reach
        if lf.get("dam", True):
            rim = smoothstep(0.45 * r, 0.12 * r, np.abs(d - 1.2 * r))  # a solid band: a one-cell crest leaks
            self.H += rim * np.clip(level + lf.get("freeboard", 1.5) - self.H, 0, None)
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
        self.H = np.where(cone > 0, np.maximum(self.H, self._smooth(base + cone, 20)), self.H)
        lf["_centre"] = (xy + tan * lf["radius"] * 0.35).tolist()

    def _lf_moraine(self, name, lf):
        """A ridge of till across a valley where a glacier's snout stood, bowed downstream, breached by the river."""
        river = lf["across"].split("@")[0]
        xy, _, tan = self.address(lf["across"])
        nrm = np.array([-tan[1], tan[0]])
        v = np.stack([self.X - xy[0], self.Y - xy[1]], -1)
        u, w = v @ tan, v @ nrm
        L = self.lines[river]
        u = u + 0.0006 * w ** 2
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
        band = np.clip(np.minimum(d - inner, inner + lf["width"] - d) / 30 + 0.5, 0, 1)
        along = np.clip(np.minimum(L.s[i] - lf["from"], lf["to"] - L.s[i]) * L.props["length"] / 60 + 0.5, 0, 1)
        w = self._smooth(band * along * on_side, 15)
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
            if (wet & (d > 2.5 * r)).any() or wet[[0, -1], :].any() or wet[:, [0, -1]].any():
                edge = wet & (d > 1.3 * r)
                k = np.argmin(np.where(edge, d, np.inf))
                self.warnings.append(f"lake {name!r} at {level:.0f} m would spill out near "
                                     f"[{self.P[k, 0]:.0f}, {self.P[k, 1]:.0f}]: kept within {1.3 * r:.0f} m; "
                                     f"raise the ground there or lower the level")
                wet &= d <= 1.3 * r
                wet = ndimage.binary_opening(wet)
            self.water[wet] = level
            self.lake_id[wet] = lk["id"]
            lk.update(area=wet.sum() * self.cell ** 2, depth=float((level - self.H[wet]).max()) if wet.any() else 0)
            shore = ndimage.binary_dilation(wet) & ~wet
            lk["freeboard"] = float(self.H[shore].min() - level) if shore.any() else 0

    # ------------------------------------------------ processes
    def _texture(self):
        pts = np.c_[self.P, np.zeros(len(self.P))]
        relief = np.minimum(np.maximum(self.crest - self.floor, 0), RELIEF_CAP)
        steep = np.clip(self._slope() / 35, 0, 1)
        rough = (0.3 + 0.7 * steep) * np.clip(self.t, 0, 1) ** 0.7  # rock high and steep; floors stay smooth
        ridged = 1 - np.abs(2 * noise.fbm(pts, 120, 3, seed=3) - 1)
        gully = noise.fbm(pts, 45, 2, seed=5)
        crestward = 1 - 0.7 * smoothstep(0.85, 1.0, self.t)  # lumps right on a crest read as pinnacles
        self.H += rough * 0.03 * relief * crestward * (ridged.reshape(self.X.shape) - 0.5)
        self.H += rough * 4 * (gully.reshape(self.X.shape) - 0.5)

    def _dissect(self):
        """Side streams cutting the slopes between the authored rivers (which stay put: they are base level).
        Stream power runs on a coarser grid (D8 on the fine grid scratches one-cell, eight-direction rills) and its
        erosion is upsampled smoothly; a lumpiness first gives flow somewhere to converge (on planar slopes it runs
        in parallel stripes)."""
        d = self.spec.get("dissection", {"strength": 1.0})
        if not d or not d.get("strength"):
            return
        f = int(d.get("coarse", 4))
        relief = np.minimum(np.maximum(self.crest - self.floor, 0), RELIEF_CAP)
        pts = np.c_[self.P, np.zeros(len(self.P))]
        pert = sum(a * (noise.fbm(pts, sc, 3, seed=s) - 0.5) for a, sc, s in [(1, 500, 11), (0.5, 180, 12)])
        amp = d.get("lumpy", 0.08) * relief * np.clip(self.t * 3, 0, 1) * (1 - 0.7 * smoothstep(0.85, 1.0, self.t)) + 3.0
        H = self.H + amp * pert.reshape(self.X.shape) * ~self._fixed_river
        Hc = H[::f, ::f]
        base = self._fixed_river[::f, ::f].copy()
        base[0, :] = base[-1, :] = base[:, 0] = base[:, -1] = True
        E, _ = stream_power(Hc, self.cell * f, base, steps=int(d.get("age", 40)), k=0.006 * d["strength"],
                            diffuse=d.get("soften", 0.02))
        delta = ndimage.zoom(E - Hc, f, order=3)[:H.shape[0], :H.shape[1]]
        delta = np.pad(delta, ((0, H.shape[0] - delta.shape[0]), (0, H.shape[1] - delta.shape[1])), mode="edge")
        self.H = H + delta

    # ------------------------------------------------ measuring
    def _slope(self, H=None):
        H = self.H if H is None else H
        gy, gx = np.gradient(H, self.cell)
        return np.degrees(np.arctan(np.hypot(gx, gy)))

    def report(self) -> str:
        from . import terrain_design as design
        out = ["peaks/cols (authored -> built):"]
        for n, (xy, h) in self.points.items():
            top = self.H[np.hypot(self.X - xy[0], self.Y - xy[1]) < 40].max()
            out.append(f"  {n}: {h:.0f} -> {top:.0f} m")
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
                    ds = np.arange(0, 1500, self.cell)
                    hs = self.sample(xy + nrm * side * ds[:, None])
                    top = int(np.argmax(hs))
                    wall = hs[: top + 1]
                    lo = int(np.argmax(wall > h + 0.15 * (hs[top] - h)))
                    hi = int(np.argmax(wall > h + 0.85 * (hs[top] - h)))
                    slope = math.degrees(math.atan((wall[hi] - wall[lo]) / max((hi - lo) * self.cell, 1)))
                    prof.append(f"{hs[top] - h:.0f} m over {ds[top]:.0f} m ({slope:.0f} deg)")
                out.append(f"    @{s:.2f}: floor {L.h[np.searchsorted(L.s, s)]:.0f} m; left bank rises {prof[0]}, right {prof[1]}")
        if getattr(self, "rib_count", 0):
            out.append(f"ribs (automatic): {self.rib_count} spurs off the ridges")
        for (a, b), length, top in self.divides:
            out.append(f"divide (automatic) between {a} and {b}: {length:.0f} m of crest, up to {top:.0f} m")
        for name, lk in self.lakes.items():
            out.append(f"lake {name}: level {lk['level']:.0f} m, {lk.get('area', 0) / 1e4:.1f} ha, "
                       f"deepest {lk.get('depth', 0):.0f} m, lowest shore {lk.get('freeboard', 0):+.1f} m above the water")
        out += design.report(self)
        out += self._drainage()
        out += design.intent(self)
        if self.warnings:
            out.append("WARNINGS:")
            out += [f"  {w}" for w in self.warnings]
        return "\n".join(out)

    def _drainage(self):
        """Pits (water can't leave, not a lake) and big unauthored streams (flow gathering away from the rivers)."""
        H = np.where(np.isnan(self.water), self.H, self.water)
        base = ~np.isnan(self.water)
        base[[0, -1], :] = base[:, [0, -1]] = True
        rec, dist, levels = _receivers(H, self.cell, base)
        pit = (rec == np.arange(H.size)).reshape(H.shape) & ~base
        pits = ndimage.label(pit)[1]
        area = _accumulate(rec, levels, self.cell).reshape(H.shape)
        near = np.zeros(H.shape, bool)
        for L in self.lines.values():
            if L.kind == "river":
                m, _ = self._stamp(L, L.props["floor"] / 2 + 80)
                near |= m
        stray = (area > 250_000) & ~near & np.isnan(self.water)
        lab, n = ndimage.label(stray)
        out = [f"drainage: {pits} pits (water trapped outside lakes)"]
        if n:
            sizes = ndimage.maximum(area, lab, range(1, n + 1))
            for k in np.argsort(-sizes)[:3]:
                yy, xx = np.nonzero(lab == k + 1)
                j = np.argmax(area[yy, xx])
                out.append(f"  unauthored stream draining {area[yy[j], xx[j]] / 1e6:.2f} km2 at "
                           f"[{self.xs[xx[j]]:.0f}, {self.ys[yy[j]]:.0f}]")
        return out

    def export(self, out_dir):
        """For an engine: height (float32 .npy, and 16-bit PNG with its range in meta.json), one 8-bit PNG
        density/weight mask per cover layer, water surface, all north-up at one pixel per cell."""
        from PIL import Image
        out = Path(out_dir)
        (out / "masks").mkdir(parents=True, exist_ok=True)
        lo, hi = float(self.H.min()), float(self.H.max())
        np.save(out / "height.npy", self.H[::-1].astype(np.float32))
        Image.fromarray(((self.H[::-1] - lo) / (hi - lo) * 65535).astype(np.uint16)).save(out / "height.png")
        for name, m in self.cover.items():
            Image.fromarray((np.clip(m[::-1], 0, 1) * 255).astype(np.uint8)).save(out / "masks" / f"{name}.png")
        Image.fromarray((~np.isnan(self.water[::-1]) * 255).astype(np.uint8)).save(out / "masks" / "water.png")
        meta = {"extent": self.spec["extent"], "cell": self.cell, "height_range": [lo, hi],
                "size": [len(self.xs), len(self.ys)], "north_up": True,
                "cover": {n: (self.spec.get("cover") or {}).get(n, {}).get("type", n) for n in self.cover},
                "lakes": {n: {"level": lk["level"], "at": lk["xy"]} for n, lk in self.lakes.items()},
                "sites": {n: {"at": s["xy"], "level": s["level"], "radius": s["radius"]} for n, s in self.sites.items()},
                "routes": {n: L.xy.round(1).tolist() for n, L in self.routes.items()}}
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


def stream_power(H, cell, base, steps=40, k=0.004, m=0.5, diffuse=0.15):
    """Fluvial dissection: implicit stream-power incision (Braun & Willett 2013, n = 1) toward fixed base-level
    cells, plus a little hillslope diffusion. Returns the eroded surface and the final drainage area."""
    H = H.copy().ravel()
    fixed = base.ravel()
    shape = base.shape
    A = np.zeros(H.size)
    for _ in range(steps):
        rec, dist, levels = _receivers(H.reshape(shape), cell, base)
        A = _accumulate(rec, levels, cell)
        F = k * A ** m / np.maximum(dist, 1e-9)
        for lv in levels[1:]:
            lv = lv[~fixed[lv]]
            H[lv] = (H[lv] + F[lv] * H[rec[lv]]) / (1 + F[lv])
        if diffuse:
            G = H.reshape(shape)
            H = np.where(fixed, H, (G + diffuse * ndimage.laplace(G, mode="nearest")).ravel())
    return H.reshape(shape), A.reshape(shape)


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
    grass = np.array([0.40, 0.47, 0.26]) * (1 - 0.3 * hn[..., None]) + np.array([0.10, 0.07, 0.02]) * hn[..., None]
    rock = np.array([0.36, 0.34, 0.31]) + 0.06 * hn[..., None]
    w = smoothstep(28, 40, slope)[..., None]
    c = grass * (1 - w) + rock * w
    if cover:
        for name, m in T.cover.items():
            col = np.array(design.cover_colour(T, name))
            a = 0.85 * np.clip(m, 0, 1)[..., None]
            c = c * (1 - a) + col * a
    c[~np.isnan(T.water)] = [0.16, 0.28, 0.38]
    return c


def map_image(T: Terrain, px: int = 1100, contour: float = 50, labels: bool = True):
    """A plan view to reason on: hillshade over ground/cover colour, contours (index every 5th), rivers, ridges,
    divides, routes, sites, walls (red where climbable), names and a cover legend."""
    from PIL import Image, ImageDraw
    from skimage import measure
    from . import terrain_design as design
    H = T.H
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

    for lev in np.arange(math.ceil(H.min() / contour) * contour, H.max(), contour):
        index = int(round(lev / contour)) % 5 == 0
        for cnt in measure.find_contours(H, lev):
            pts = [(c[1] * sc, (ny - 1 - c[0]) * sc) for c in cnt[::2]]
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
            d.rectangle([x - r, y - r, x + r, y + r], outline=(160, 40, 160), width=2)
            label(s["xy"], f"{name} {s['level']:.0f}", (110, 20, 110))
        for name, (xy, h) in T.points.items():
            top = T.H[np.hypot(T.X - xy[0], T.Y - xy[1]) < 40].max()
            label(xy, f"{name} {top:.0f}")
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
        bar = 1000 * sc / T.cell
        d.rectangle([20, img.height - 30, 20 + bar, img.height - 22], fill=(0, 0, 0))
        d.text((24 + bar, img.height - 36), "1 km", fill=(0, 0, 0), font=fb, stroke_width=2, stroke_fill=(255, 255, 255))
        d.text((W - 40, 12), "N", fill=(0, 0, 0), font=fb, stroke_width=2, stroke_fill=(255, 255, 255))
        d.polygon([(W - 34, 34), (W - 40, 50), (W - 28, 50)], fill=(0, 0, 0))
        d.text((20, 12), f"contours {contour:.0f} m", fill=(0, 0, 0), font=f, stroke_width=2, stroke_fill=(255, 255, 255))
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
        ImageDraw.Draw(im).text((8, 6), f"{name} ({100 * m.mean():.0f}%)", fill=(255, 60, 60), font=_font(16),
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
    trees = {}
    for name, m in T.cover.items():
        kind = design.tree_kind(T, name)
        if kind:
            trees[kind] = np.maximum(trees.get(kind, 0), m[::step, ::step].ravel())
    Wt = T.water[::step, ::step]
    wet = ~np.isnan(Wt)
    wv = verts.copy()
    wv[:, 2] = np.where(wet.ravel(), Wt.ravel(), np.nanmax(np.where(wet, Wt, np.nan)) if wet.any() else 0)
    q = (wet[:-1, :-1] | wet[:-1, 1:] | wet[1:, 1:] | wet[1:, :-1]).ravel()
    wf = np.concatenate([np.stack([a, b, c], 1)[q], np.stack([a, c, e], 1)[q]])
    np.savez(path, verts=verts.astype(np.float32), faces=faces.astype(np.int32), colors=col.astype(np.float32),
             wverts=wv.astype(np.float32), wfaces=wf.astype(np.int32),
             **{f"trees_{k}": v.astype(np.float32) for k, v in trees.items()})


def render(T: Terrain, out_dir, views: list[dict], size=(1200, 700), samples=24):
    """Perspective Cycles renders: views are {"name", "eye": address | [x, y, z], "lift": m, "look": address, "fov"}."""
    import subprocess
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mesh = out_dir / "terrain_mesh.npz"
    write_mesh(T, mesh)
    jobs = []
    for v in views:
        exy, eh, _ = T.address(v["eye"])
        if isinstance(v["eye"], list) and len(v["eye"]) == 3:
            eh = v["eye"][2]
        txy, th, _ = T.address(v["look"])
        jobs.append({"eye": [*exy, eh + v.get("lift", 2)], "look": [*txy, th], "fov": v.get("fov", 60),
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
