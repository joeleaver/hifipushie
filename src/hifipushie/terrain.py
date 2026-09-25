"""Terrain from a vocabulary: a skeleton of named ridges and rivers, landforms addressed on it, intent checks.

Experimental (spike). Coordinates: metres, x east, y north, z up. A terrain spec:

    {"extent": [[x0, y0], [x1, y1]], "cell": 10, "border": 150,     # the frame's edge falls to this height
     "peaks": {name: {"at": [x, y], "h": z}}, "cols": {...same},
     "ridges": {name: {"through": [peak/col name | [x, y, z]...], "crest": "arete" | "rounded"}},
     "rivers": {name: {"source": [x, y, z], "through": [[x, y]...], "mouth": [x, y, z] | "into": river,
                       "hanging": m, "valley": {"profile": "U" | "V" | "gorge" | "open", "floor": m}}},
     "landforms": {name: {"type": "lake" | "fan" | "moraine" | "terrace", ...}},
     "intent": {name: {"at"/"path"/"from": addresses, "above_flood" | "max_grade" | "see": ...}}}

Addresses: a peak/col/landform name, "river.source", "river.mouth", "river@0.4" (fraction of its length).
Banks: "left"/"right" looking downstream.

How heights come from the skeleton: three harmonic fields (Laplace, Dirichlet on the skeleton): t, 0 on
valley floors (and the frame's edge) and 1 on ridge crests; the floor height extended from the rivers; the crest
height extended from the ridges. Height = floor + (crest - floor) * profile(t). Harmonic interpolation has no
seams where the nearest feature switches (distance-based blends crease there); the profile exponent (U vs V)
and crest rounding are themselves extended harmonically from the valleys/ridges that own them.
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
CRESTS = {"arete": 0.0, "rounded": 1.0}


# ---------------------------------------------------------------- curves

def _catmull(pts: np.ndarray, step: float) -> np.ndarray:
    """A Catmull-Rom curve through pts (n, d), resampled every ~step metres of xy length."""
    if len(pts) == 2:
        n = max(2, int(np.linalg.norm(pts[1, :2] - pts[0, :2]) / step) + 1)
        return pts[0] + (pts[1] - pts[0]) * np.linspace(0, 1, n)[:, None]
    p = np.vstack([2 * pts[0] - pts[1], pts, 2 * pts[-1] - pts[-2]])
    out = []
    for i in range(1, len(p) - 2):
        a, b, c, d = p[i - 1], p[i], p[i + 1], p[i + 2]
        n = max(2, int(np.linalg.norm(c[:2] - b[:2]) / step) + 1)
        u = np.linspace(0, 1, n, endpoint=i == len(p) - 3)[:, None]
        out.append(0.5 * (2 * b + (c - a) * u + (2 * a - 5 * b + 4 * c - d) * u ** 2
                          + (3 * b - 3 * c + d - a) * u ** 3))
    return np.vstack(out)


@dataclass
class Line:
    """A resampled skeleton line: xy samples, height per sample, arc-length fraction per sample."""
    name: str
    kind: str                 # "ridge" | "river"
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


# ---------------------------------------------------------------- the terrain

class Terrain:
    def __init__(self, spec: dict):
        self.spec = spec
        (x0, y0), (x1, y1) = spec["extent"]
        self.cell = c = float(spec.get("cell", 10))
        self.xs = np.arange(x0, x1 + c / 2, c)
        self.ys = np.arange(y0, y1 + c / 2, c)
        self.X, self.Y = np.meshgrid(self.xs, self.ys)  # [iy, ix]
        self.P = np.stack([self.X.ravel(), self.Y.ravel()], 1)
        self.points = {}
        for group in ("peaks", "cols"):
            for n, p in (spec.get(group) or {}).items():
                self.points[n] = (np.array(p["at"], float), float(p["h"]))
        self.lines: dict[str, Line] = {}
        self.water = np.full(self.X.shape, np.nan)  # lake surface heights
        self.log: list[str] = []
        self._ridges()
        self._rivers()
        self.H = self._base()
        self.H0 = self.H.copy()
        # the history, oldest first: the skeleton's shape, rough ground, streams cutting it, then young landforms
        self._texture()
        self._dissect()
        for name, lf in (spec.get("landforms") or {}).items():
            getattr(self, "_lf_" + lf["type"])(name, lf)
        self._fill_lakes()

    # ------------------------------------------------ skeleton
    def _pt(self, ref):
        if isinstance(ref, str) and "@" in ref:  # a point on a line already built: "north_ridge@0.6"
            name, s = ref.split("@")
            xy, h, _ = self.lines[name].at(float(s))
            return np.array([*xy, h])
        if isinstance(ref, str):
            xy, h = self.points[ref]
            return np.array([*xy, h])
        return np.array(ref, float)

    def _ridges(self):
        for name, r in (self.spec.get("ridges") or {}).items():
            ctrl = np.array([self._pt(p) for p in r["through"]])
            xy = _catmull(ctrl[:, :2], self.cell / 2)
            # heights: smoothstep between control points (peaks and cols are the extremes, level on top)
            ks, _ = _arclen(ctrl[:, :2])
            s, _ = _arclen(xy)
            # arc fraction of each control point on the resampled curve
            kxy = cKDTree(xy)
            ki = np.sort(kxy.query(ctrl[:, :2])[1])
            h = np.empty(len(xy))
            for a, b, ha, hb in zip(ki[:-1], ki[1:], ctrl[:-1, 2], ctrl[1:, 2]):
                u = np.linspace(0, 1, b - a + 1)
                h[a:b + 1] = ha + (hb - ha) * u * u * (3 - 2 * u)
            self.lines[name] = Line(name, "ridge", xy, h, s, {"crest": CRESTS[r.get("crest", "arete")]})

    def _rivers(self):
        todo = dict(self.spec.get("rivers") or {})
        while todo:
            for name, r in list(todo.items()):
                if r.get("into") and r["into"] not in self.lines:
                    continue
                src = np.array(r["source"], float)
                mid = [np.array(p, float)[:2] for p in r.get("through", [])]
                if r.get("into"):
                    parent = self.lines[r["into"]]
                    last = mid[-1] if mid else src[:2]
                    j = int(cKDTree(parent.xy).query(last)[1])
                    j = min(j + int(100 / self.cell), len(parent.xy) - 1)  # joins a little downstream
                    mouth = np.array([*parent.xy[j], parent.h[j] + r.get("hanging", 0)])
                    r["_join"] = (r["into"], float(parent.s[j]))
                else:
                    mouth = np.array(r["mouth"], float)
                ctrl = np.vstack([src[:2], *mid, mouth[:2]])
                xy = _catmull(ctrl, self.cell / 2)
                s, length = _arclen(xy)
                k = r.get("concavity", 1.6)  # graded rivers: steep near the source, gentle near the mouth
                h = mouth[2] + (src[2] - mouth[2]) * (1 - s) ** k
                v = r.get("valley") or {}
                self.lines[name] = Line(name, "river", xy, h, s, {
                    "p": PROFILES[v.get("profile", "V")], "floor": float(v.get("floor", 30)), "length": length,
                    "into": r.get("into"), "hanging": r.get("hanging", 0)})
                del todo[name]

    # ------------------------------------------------ harmonic base
    def _solve(self, fixed: np.ndarray, rhs: list[np.ndarray]) -> list[np.ndarray]:
        ny, nx = self.X.shape
        n = nx * ny
        idx = np.arange(n).reshape(ny, nx)
        rows, cols, vals = [], [], []
        deg = np.zeros(n)
        for sl_a, sl_b in (((slice(None), slice(1, None)), (slice(None), slice(None, -1))),
                           ((slice(1, None), slice(None)), (slice(None, -1), slice(None)))):
            a, b = idx[sl_a].ravel(), idx[sl_b].ravel()
            for i, j in ((a, b), (b, a)):
                rows.append(i); cols.append(j); vals.append(-np.ones(len(i)))
                np.add.at(deg, i, 1)
        rows, cols, vals = np.concatenate(rows), np.concatenate(cols), np.concatenate(vals)
        f = fixed.ravel()
        keep = ~f[rows]
        A = sparse.csc_matrix((np.r_[vals[keep], np.where(f, 1.0, deg)],
                               (np.r_[rows[keep], np.arange(n)], np.r_[cols[keep], np.arange(n)])), shape=(n, n))
        lu = splu(A)
        return [lu.solve(np.where(f, r.ravel(), 0.0)).reshape(ny, nx) for r in rhs]

    def _stamp(self, line: Line, radius: float):
        """Cells within radius of a line, and for each cell its nearest sample index."""
        d, i = cKDTree(line.xy).query(self.P, distance_upper_bound=radius + self.cell)
        m = d <= max(radius, self.cell * 0.75)
        return m.reshape(self.X.shape), np.where(m, i, 0).reshape(self.X.shape)

    def _floor_of(self, river):
        return self.lines[river].props["floor"] if river else 0

    def _base(self):
        shape = self.X.shape
        border = np.zeros(shape, bool)
        border[0, :] = border[-1, :] = border[:, 0] = border[:, -1] = True
        b = float(self.spec.get("border", 0))
        low_fix, low, prof = border.copy(), np.full(shape, b), np.full(shape, PROFILES["V"])
        high_fix, high, crest = np.zeros(shape, bool), np.zeros(shape), np.zeros(shape)
        for L in self.lines.values():
            if L.kind == "river":
                m, i = self._stamp(L, L.props["floor"] / 2)
                if L.props["hanging"]:  # the lip: leave the last stretch free, so the step is steep, not a wall
                    m &= (1 - L.s[i]) * L.props["length"] > 3 * L.props["hanging"] + self._floor_of(L.props["into"]) / 2
                low_fix |= m; low[m] = L.h[i[m]]; prof[m] = L.props["p"]
                self._fixed_river = getattr(self, "_fixed_river", np.zeros(shape, bool)) | m
        for L in self.lines.values():
            if L.kind == "ridge":
                m, i = self._stamp(L, 0)
                high_fix |= m; high[m] = L.h[i[m]]; crest[m] = L.props["crest"]
                low_fix &= ~m  # a ridge reaching the frame's edge stays a ridge
        t_fix = low_fix | high_fix
        t, = self._solve(t_fix, [np.where(high_fix, 1.0, 0.0)])
        self.floor, self.prof = self._solve(low_fix, [low, prof])
        self.crest, self.round = self._solve(high_fix, [high, crest])
        self.t = np.clip(t, 0, 1)
        s = self.t ** self.prof
        s = (1 - self.round) * s + self.round * (1 - (1 - s) ** 2)
        return self.floor + np.maximum(self.crest - self.floor, 0) * s

    # ------------------------------------------------ addresses
    def address(self, ref):
        """(xy, height of the ground there, tangent or None)."""
        if isinstance(ref, (list, tuple)):
            xy = np.array(ref[:2], float)
            return xy, self.height(xy), None
        if ref in self.points:
            xy = self.points[ref][0]
            return xy, self.height(xy), None
        if "@" in ref:
            name, s = ref.split("@")
            xy, h, tan = self.lines[name].at(float(s))
            return xy, h, tan
        if "." in ref:
            name, end = ref.rsplit(".", 1)
            L = self.lines[name]
            xy, h, tan = L.at(0.0 if end == "source" else 1.0)
            return xy, h, tan
        lf = self.spec["landforms"][ref]
        xy = np.array(lf["_centre"], float)
        return xy, self.height(xy), None

    def height(self, xy, H=None):
        H = self.H if H is None else H
        return float(ndimage.map_coordinates(H, [[(xy[1] - self.ys[0]) / self.cell], [(xy[0] - self.xs[0]) / self.cell]],
                                             order=1, mode="nearest")[0])

    # ------------------------------------------------ landforms
    def _smooth(self, a, r):
        return ndimage.gaussian_filter(a.astype(float), r / self.cell)

    def _lf_lake(self, name, lf):
        xy, _, _ = self.address(lf["at"])
        r = lf["radius"]
        d = np.hypot(self.X - xy[0], self.Y - xy[1])
        level = self.height(xy)
        bowl = np.clip(1 - (d / r) ** 2, 0, None) ** 1.5 * lf.get("depth", 10)
        self.H -= bowl  # a basin scoured by the ice; water fills it to its spill level (_fill_lakes)
        # what holds it: a rock bar (or moraine) round the rim, up to the level plus a little freeboard
        rim = np.exp(-((d - r) / (0.25 * r)) ** 2)
        self.H += rim * np.clip(level + lf.get("freeboard", 1.5) - self.H, 0, None)
        self._lakes = getattr(self, "_lakes", []) + [xy]
        lf["_centre"] = xy.tolist()

    def _lf_fan(self, name, lf):
        """A debris cone where a steep stream meets flatter ground: spreads downslope from the stream's mouth."""
        xy, _, tan = self.address(lf["at"])
        base = self.floor  # the valley floor it spreads on
        v = np.stack([self.X - xy[0], self.Y - xy[1]], -1)
        d = np.linalg.norm(v, axis=-1)
        ahead = (v @ tan) / (d + 1e-9)  # the fan opens in the stream's direction
        spread = np.clip((ahead + 0.3) / 0.6, 0, 1)
        cone = lf["height"] * np.clip(1 - d / lf["radius"], 0, 1) ** 1.3 * spread * (self.t < 0.5)
        self.H = np.maximum(self.H, self._smooth(base + cone, 20) * (cone > 0) + self.H * (cone <= 0))
        lf["_centre"] = (xy + tan * lf["radius"] * 0.35).tolist()

    def _lf_moraine(self, name, lf):
        """A ridge of till across a valley where a glacier's snout stood, bowed downstream, breached by the river."""
        river = lf["across"].split("@")[0]
        xy, _, tan = self.address(lf["across"])
        nrm = np.array([-tan[1], tan[0]])
        v = np.stack([self.X - xy[0], self.Y - xy[1]], -1)
        u, w = v @ tan, v @ nrm
        L = self.lines[river]
        u = u - 0.0006 * w ** 2 * -1  # bowed downstream at the centre
        bump = lf["height"] * np.exp(-(u / lf["width"]) ** 2)
        breach = 1 - np.exp(-(w / (L.props["floor"] * 0.3)) ** 2)
        valley = np.clip(1 - self.t / 0.45, 0, 1)
        self.H += bump * breach * valley
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
        target = L.h[i] + lf["height"]
        self.H = self.H * (1 - w) + target * w
        mid = (lf["from"] + lf["to"]) / 2
        cxy, _, ctan = L.at(mid)
        lf["_centre"] = (cxy + np.array([-ctan[1], ctan[0]]) * side * (inner + lf["width"] / 2)).tolist()

    def _fill_lakes(self):
        """Authored lakes fill to where they spill; every other depression is a pit (reported, not filled)."""
        F = priority_fill(self.H)
        deep = F - self.H > 0.05
        lab, _ = ndimage.label(deep)
        for xy in getattr(self, "_lakes", []):
            iy, ix = int(round((xy[1] - self.ys[0]) / self.cell)), int(round((xy[0] - self.xs[0]) / self.cell))
            if lab[iy, ix]:
                wet = lab == lab[iy, ix]
                self.water[wet] = F[wet]
        self.filled = F

    def _dissect(self):
        """Side streams cutting the slopes between the authored rivers (which stay put: they are base level).
        Stream power runs on a coarser grid (D8 on the fine grid scratches one-cell, eight-direction rills) and its
        erosion is upsampled smoothly onto the fine surface; a relief-scaled lumpiness first gives flow somewhere
        to converge (harmonic slopes are nearly planar: flow on them runs in parallel)."""
        d = self.spec.get("dissection", {"strength": 1.0})
        if not d or not d.get("strength"):
            return
        f = int(d.get("coarse", 4))
        relief = np.maximum(self.crest - self.floor, 0)
        pts = np.c_[self.P, np.zeros(len(self.P))]
        pert = sum(a * (noise.fbm(pts, sc, 3, seed=s) - 0.5) for a, sc, s in [(1, 500, 11), (0.5, 180, 12)])
        H = self.H + d.get("lumpy", 0.08) * relief * pert.reshape(self.X.shape) * np.clip(self.t * 3, 0, 1)
        Hc = H[::f, ::f]
        base = self._fixed_river[::f, ::f].copy()
        base[0, :] = base[-1, :] = base[:, 0] = base[:, -1] = True
        E, _ = stream_power(Hc, self.cell * f, base, steps=int(d.get("age", 40)), k=0.006 * d["strength"],
                            diffuse=d.get("soften", 0.02))
        delta = ndimage.zoom(E - Hc, f, order=3)[:H.shape[0], :H.shape[1]]
        delta = np.pad(delta, ((0, H.shape[0] - delta.shape[0]), (0, H.shape[1] - delta.shape[1])), mode="edge")
        self.H = H + delta

    # ------------------------------------------------ texture: process-flavoured detail, not free octaves
    def _texture(self):
        tx = self.spec.get("texture") or {}
        pts = np.c_[self.P, np.zeros(len(self.P))]
        relief = np.maximum(self.crest - self.floor, 0)
        steep = np.clip(self._slope() / 35, 0, 1)
        # rock breaks out on steep ground and high up; floors stay smooth (sediment)
        rough = (0.3 + 0.7 * steep) * np.clip(self.t, 0, 1) ** 0.7
        ridged = 1 - np.abs(2 * noise.fbm(pts, 120, 3, seed=3) - 1)
        gully = noise.fbm(pts, 45, 2, seed=5)
        self.H += rough * 0.02 * relief * (ridged.reshape(self.X.shape) - 0.5)
        self.H += rough * 4 * (gully.reshape(self.X.shape) - 0.5)

    # ------------------------------------------------ measuring
    def _slope(self, H=None):
        H = self.H if H is None else H
        gy, gx = np.gradient(H, self.cell)
        return np.degrees(np.arctan(np.hypot(gx, gy)))

    def report(self) -> str:
        out = []
        out.append("peaks/cols (authored -> built):")
        for n, (xy, h) in self.points.items():
            out.append(f"  {n}: {h:.0f} -> {self.height(xy):.0f} m")
        for L in self.lines.values():
            if L.kind != "river":
                continue
            out.append(f"river {L.name}: {L.props['length']:.0f} m, {L.h[0]:.0f} -> {L.h[-1]:.0f} m, "
                       f"mean grade {100 * (L.h[0] - L.h[-1]) / L.props['length']:.1f}%")
            rows = []
            for s in (0.15, 0.35, 0.55, 0.75, 0.9):
                xy, h, tan = L.at(s)
                nrm = np.array([-tan[1], tan[0]])
                prof = []
                for side in (1, -1):
                    ds = np.arange(0, 1500, self.cell)
                    hs = np.array([self.height(xy + nrm * side * d) for d in ds])
                    top = int(np.argmax(hs))
                    wall = hs[: top + 1]
                    lo = int(np.argmax(wall > h + 0.15 * (hs[top] - h)))
                    hi = int(np.argmax(wall > h + 0.85 * (hs[top] - h)))
                    slope = math.degrees(math.atan((wall[hi] - wall[lo]) / max((hi - lo) * self.cell, 1)))
                    prof.append((hs[top] - h, ds[top], slope))
                rows.append(f"    @{s:.2f}: floor {h:.0f} m; left bank rises {prof[0][0]:.0f} m over {prof[0][1]:.0f} m"
                            f" (wall {prof[0][2]:.0f} deg), right {prof[1][0]:.0f} m over {prof[1][1]:.0f} m"
                            f" (wall {prof[1][2]:.0f} deg)")
            out += rows
        out += self._drainage()
        out += self._intent()
        return "\n".join(out)

    def _drainage(self):
        """Pits (water can't leave, not a lake) and big unauthored streams (flow gathering away from the rivers)."""
        H = np.where(np.isnan(self.water), self.H, self.water)
        ny, nx = H.shape
        pad = np.pad(H, 1, constant_values=-1e9)
        nb = [(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx]
        drops = np.stack([(H - pad[1 + dy:1 + dy + ny, 1 + dx:1 + dx + nx]) / math.hypot(dy, dx) for dy, dx in nb])
        best = np.argmax(drops, 0)
        pit = (drops.max(0) <= 0) & np.isnan(self.water)
        pits = ndimage.label(pit)[1]
        # flow accumulation, highest cell first
        order = np.argsort(-H.ravel())
        acc = np.ones(H.size)
        dy = np.array([d[0] for d in nb])[best.ravel()]
        dx = np.array([d[1] for d in nb])[best.ravel()]
        iy, ix = np.divmod(np.arange(H.size), nx)
        ty, tx = iy + dy, ix + dx
        ok = (ty >= 0) & (ty < ny) & (tx >= 0) & (tx < nx) & ~pit.ravel()
        tgt = ty * nx + tx
        for k in order:
            if ok[k]:
                acc[tgt[k]] += acc[k]
        self.acc = acc.reshape(H.shape)
        area = self.acc * self.cell ** 2
        near = np.zeros(H.shape, bool)
        for L in self.lines.values():
            if L.kind == "river":
                m, _ = self._stamp(L, L.props["floor"] / 2 + 80)
                near |= m
        stray = (area > 250_000) & ~near & np.isnan(self.water)
        lab, n = ndimage.label(stray)
        out = [f"drainage: {pits} pits (water trapped outside lakes)"]
        if n:
            sizes = ndimage.sum(area, lab, range(1, n + 1))
            for k in np.argsort(-sizes)[:4]:
                yy, xx = np.nonzero(lab == k + 1)
                j = np.argmax(self.acc[yy, xx])
                out.append(f"  unauthored stream draining {area[yy[j], xx[j]] / 1e6:.2f} km2 at "
                           f"[{self.xs[xx[j]]:.0f}, {self.ys[yy[j]]:.0f}]")
        return out

    def _intent(self):
        out = []
        for name, it in (self.spec.get("intent") or {}).items():
            if "above_flood" in it:
                xy, h, _ = self.address(it["at"])
                river = min((L for L in self.lines.values() if L.kind == "river"),
                            key=lambda L: cKDTree(L.xy).query(xy)[0])
                rh = river.h[cKDTree(river.xy).query(xy)[1]]
                ok = h - rh >= it["above_flood"]
                out.append(f"intent {name}: {h - rh:.0f} m above {river.name} (want >= {it['above_flood']}) "
                           f"{'OK' if ok else 'FAIL'}")
            if "path" in it:
                pts = [self.address(a)[0] for a in it["path"]]
                xy = np.vstack([np.linspace(a, b, int(np.linalg.norm(b - a) / self.cell)) for a, b in zip(pts, pts[1:])])
                hs = ndimage.map_coordinates(self.H, [(xy[:, 1] - self.ys[0]) / self.cell, (xy[:, 0] - self.xs[0]) / self.cell], order=1)
                dist = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
                w = max(1, int(50 / self.cell))
                grade = np.abs(hs[w:] - hs[:-w]) / (dist[w:] - dist[:-w])
                climb = np.abs(np.diff(hs)).sum()
                need = climb / it["max_grade"]
                out.append(f"intent {name}: straight line {dist[-1]:.0f} m, climbs {climb:.0f} m, steepest 50 m "
                           f"{100 * grade.max():.0f}% (want <= {100 * it['max_grade']:.0f}%): "
                           f"{'OK' if grade.max() <= it['max_grade'] else f'needs a route >= {need:.0f} m (switchbacks)'}")
            if "see" in it:
                xy, h, _ = self.address(it["from"])
                for tgt in it["see"]:
                    txy, th, _ = self.address(tgt)
                    n = int(np.linalg.norm(txy - xy) / (self.cell / 2))
                    u = np.linspace(0, 1, n)[1:-1]
                    p = xy + (txy - xy) * u[:, None]
                    ground = ndimage.map_coordinates(self.H, [(p[:, 1] - self.ys[0]) / self.cell, (p[:, 0] - self.xs[0]) / self.cell], order=1)
                    sight = (h + 1.7) + (th + 2 - h - 1.7) * u
                    blocked = ground > sight
                    if blocked.any():
                        k = int(np.argmax(ground - sight))
                        out.append(f"intent {name}: {tgt} hidden (ground {ground[k] - sight[k]:.0f} m above the sight "
                                   f"line at [{p[k, 0]:.0f}, {p[k, 1]:.0f}])")
                    else:
                        out.append(f"intent {name}: {tgt} visible")
        return out


def load(path) -> Terrain:
    return Terrain(json.loads(Path(path).read_text()))


# ---------------------------------------------------------------- views

def _font(size):
    from PIL import ImageFont
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def ground_colours(T: Terrain) -> np.ndarray:
    """sRGB per cell: grass on gentle ground, scree/rock on steep, lighter rock high up, water in lakes."""
    slope = T._slope()
    hn = (T.H - T.H.min()) / max(np.ptp(T.H), 1)
    grass = np.array([0.36, 0.45, 0.22]) * (1 - 0.35 * hn[..., None]) + np.array([0.12, 0.08, 0.02]) * hn[..., None]
    rock = np.array([0.30, 0.29, 0.27]) + 0.08 * hn[..., None]
    w = np.clip((slope - 28) / 12, 0, 1)[..., None]
    c = grass * (1 - w) + rock * w
    wet = ~np.isnan(T.water)
    c[wet] = [0.18, 0.30, 0.40]
    return c


def map_image(T: Terrain, px: int = 1100, contour: float = 50, labels: bool = True):
    """A plan view to reason on: hillshade over colour, contours (index every 5th), rivers and ridges, names."""
    from PIL import Image, ImageDraw
    from skimage import measure
    H = T.H
    gy, gx = np.gradient(H, T.cell)
    az, el = math.radians(315), math.radians(40)  # light from the north-west
    L = np.array([math.cos(el) * math.sin(az), math.cos(el) * math.cos(az), math.sin(el)])
    n = np.stack([-gx, -gy, np.ones_like(H)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    shade = np.clip(n @ L, 0, 1)
    rgb = ground_colours(T) * (0.35 + 0.8 * shade[..., None])
    img = Image.fromarray((np.clip(rgb[::-1], 0, 1) * 255).astype(np.uint8))  # north up
    sc = px / img.width
    img = img.resize((px, int(img.height * sc)), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    ny = H.shape[0]

    def to_px(x, y):
        return ((x - T.xs[0]) / T.cell * sc, (ny - 1 - (y - T.ys[0]) / T.cell) * sc)

    for lev in np.arange(math.ceil(H.min() / contour) * contour, H.max(), contour):
        index = int(round(lev / contour)) % 5 == 0
        for cnt in measure.find_contours(H, lev):
            pts = [((c[1]) * sc, (ny - 1 - c[0]) * sc) for c in cnt[::2]]
            if len(pts) > 1:
                d.line(pts, fill=(60, 40, 20) if index else (95, 75, 50), width=2 if index else 1)
    for Lr in T.lines.values():
        pts = [to_px(*p) for p in Lr.xy[::2]]
        if Lr.kind == "river":
            d.line(pts, fill=(40, 110, 200), width=3)
        else:
            for a in range(0, len(pts) - 1, 4):
                d.line(pts[a:a + 3], fill=(120, 30, 30), width=2)
    if labels:
        f, fb = _font(15), _font(17)

        def label(xy, text, col=(0, 0, 0)):
            x, y = to_px(*xy)
            d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=col)
            d.text((x + 6, y - 9), text, fill=col, font=f, stroke_width=2, stroke_fill=(255, 255, 255))

        for name, (xy, h) in T.points.items():
            label(xy, f"{name} {T.height(xy):.0f}")
        for Lr in T.lines.values():
            if Lr.kind == "river":
                xy, h, _ = Lr.at(0.5)
                label(xy, Lr.name, (20, 60, 150))
        for name, lf in (T.spec.get("landforms") or {}).items():
            if "_centre" in lf:
                label(lf["_centre"], name, (90, 20, 90))
        for name, it in (T.spec.get("intent") or {}).items():
            if "path" in it:
                d.line([to_px(*T.address(a)[0]) for a in it["path"]], fill=(220, 120, 0), width=2)
        # scale bar and north
        W = img.width
        bar = 1000 * sc / T.cell
        d.rectangle([20, img.height - 30, 20 + bar, img.height - 22], fill=(0, 0, 0))
        d.text((24 + bar, img.height - 36), "1 km", fill=(0, 0, 0), font=fb, stroke_width=2, stroke_fill=(255, 255, 255))
        d.text((W - 40, 12), "N", fill=(0, 0, 0), font=fb, stroke_width=2, stroke_fill=(255, 255, 255))
        d.polygon([(W - 34, 34), (W - 40, 50), (W - 28, 50)], fill=(0, 0, 0))
        d.text((20, 12), f"contours {contour:.0f} m", fill=(0, 0, 0), font=f, stroke_width=2, stroke_fill=(255, 255, 255))
    return img


def write_mesh(T: Terrain, path, step: int = 1):
    """Grid mesh npz (verts, faces, colors linear) plus a water mesh for lakes."""
    H = T.H[::step, ::step]
    X, Y = T.X[::step, ::step], T.Y[::step, ::step]
    ny, nx = H.shape
    verts = np.stack([X.ravel(), Y.ravel(), H.ravel()], 1)
    i = np.arange(ny * nx).reshape(ny, nx)
    a, b, c, e = i[:-1, :-1].ravel(), i[:-1, 1:].ravel(), i[1:, 1:].ravel(), i[1:, :-1].ravel()
    faces = np.concatenate([np.stack([a, b, c], 1), np.stack([a, c, e], 1)])
    col = ground_colours(T)[::step, ::step].reshape(-1, 3)
    col = np.where(col <= 0.04045, col / 12.92, ((col + 0.055) / 1.055) ** 2.4)
    Wt = T.water[::step, ::step]
    wv = np.stack([X.ravel(), Y.ravel(), np.nan_to_num(Wt, nan=-1e4).ravel()], 1)
    wet = ~np.isnan(Wt)
    # a water quad where any corner is wet, at the lake level
    q = wet[:-1, :-1] | wet[:-1, 1:] | wet[1:, 1:] | wet[1:, :-1]
    lvl = np.nanmax(np.where(wet, Wt, np.nan)) if wet.any() else 0
    wv[:, 2] = np.where(wet.ravel(), wv[:, 2], lvl)
    wf = np.concatenate([np.stack([a, b, c], 1)[q.ravel()], np.stack([a, c, e], 1)[q.ravel()]])
    np.savez(path, verts=verts.astype(np.float32), faces=faces.astype(np.int32), colors=col.astype(np.float32),
             wverts=wv.astype(np.float32), wfaces=wf.astype(np.int32))


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
    if r.returncode:
        raise RuntimeError(r.stderr[-2000:] + r.stdout[-2000:])
    return [j["out"] for j in jobs]


# ---------------------------------------------------------------- processes

_NB = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def _receivers(H: np.ndarray, cell: float, base: np.ndarray):
    """Steepest-descent (D8) receiver per cell (itself for base cells and cells with no lower neighbour),
    the distance to it, and the cells ordered base-first by flow depth (tree levels, for vectorised sweeps)."""
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
    # simple, robust level assignment: iterate until settled (a few hundred cheap passes at most)
    depth = np.where(rec == idx, 0, -1)
    for k in range(1, H.size):
        new = (depth < 0) & (depth[rec] == k - 1)
        if not new.any():
            break
        depth[new] = k
    stuck = depth < 0
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
    for _ in range(steps):
        rec, dist, levels = _receivers(H.reshape(shape), cell, base)
        A = _accumulate(rec, levels, cell)
        F = k * A ** m / np.maximum(dist, 1e-9)
        for lv in levels[1:]:
            lv = lv[~fixed[lv]]
            H[lv] = (H[lv] + F[lv] * H[rec[lv]]) / (1 + F[lv])
        if diffuse:
            G = H.reshape(shape)
            lap = ndimage.laplace(G, mode="nearest")
            H = np.where(fixed, H, (G + diffuse * lap).ravel())
    return H.reshape(shape), A.reshape(shape)


def priority_fill(H: np.ndarray, eps: float = 0.0) -> np.ndarray:
    """Fill every depression to its spill level (Barnes' priority flood from the frame's edge)."""
    import heapq
    ny, nx = H.shape
    F = H.copy()
    done = np.zeros(H.shape, bool)
    heap = []
    for y in range(ny):
        for x in (0, nx - 1):
            heap.append((F[y, x], y, x)); done[y, x] = True
    for x in range(1, nx - 1):
        for y in (0, ny - 1):
            heap.append((F[y, x], y, x)); done[y, x] = True
    heapq.heapify(heap)
    while heap:
        h, y, x = heapq.heappop(heap)
        for dy, dx in _NB:
            yy, xx = y + dy, x + dx
            if 0 <= yy < ny and 0 <= xx < nx and not done[yy, xx]:
                done[yy, xx] = True
                if F[yy, xx] < h + eps:
                    F[yy, xx] = h + eps
                heapq.heappush(heap, (F[yy, xx], yy, xx))
    return F
