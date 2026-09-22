"""Strokes: sculpting marks laid onto the body's actual surface, expanded into ordinary blobs.

spec["strokes"][name] = {"op": "clay" | "crease" | "flatten", "path": [point, ...], "width", "depth", ...}

Every path point is an address on the surface of the body without any strokes (so strokes don't chase
each other), seated by raycasting the field:
  {"bone": b, "t": 0..1, "side": [x,y,z], "around": deg}
      straight out from the point t along bone b toward `side` (a world direction; only its part across
      the bone counts; default up), turned `around` degrees about the bone (right hand, a -> b).
  {"at": joint | [x,y,z] | {"bone", "t"}, "offset": [x,y,z], "dir": [x,y,z]}
      where a ray through at+offset arriving along -dir first hits (dir default [0,-1,0]: seen from the front).
Keys a point leaves out are taken from the point before it (of the same kind), so
  [{"bone": "forearm.L", "t": 0.1, "side": [0, 1, 0]}, {"t": 0.9}]  runs down the back of the forearm.
Between control points the path is resampled and every sample re-seated, so it follows the surface
instead of cutting a chord.

  width:  half-width of the stroke across the surface (m); a number, or one per control point
  depth:  clay: how far it pushes the surface out. crease: how far in. flatten: how far below the path's
          points the plane sits. A number or one per control point (interpolated between).
  profile (clay/crease): the stroke's cross-section, i.e. how hard its edge is.
          "soft" (clay default): a bell, melts in.   "sharp" (crease default): a cusp along the path, crisp.
          "round": a dome with a visible rim.         "flat": a plateau, flat top with a soft rim (planes).
  soft, blend (flatten): width of the fade-out ring beyond `width` (0.8*width), rounding where the plane
          meets the surface (0.2*width).
  layer:  strokes apply after everything else in their layer (default 0), in the order given; later layers
          (the face kit's lids, lips, eyeballs) sit on top unaffected.
  repeat: {"count": n, "shift": {"t": dt, "around": deg, "offset": [x,y,z]}, "scale": f}
          n copies; copy i has every control point shifted by i*shift and width/depth scaled by f**i.

Strokes displace the surface rather than adding shapes: each moves the existing skin along its normal
by depth * profile(distance across the surface / width), so it follows curvature and never leaves flaps
or seams. Overlapping strokes add up, like clay. They don't reach through to the far side of a limb.

Ops:
  clay     push out along the path (a ridge, a muscle mass), or around one point (a dab).
  crease   push in along the path (a groove, a fold line), or at one point (a dimple).
  flatten  plane off the surface: one point makes a flat spot `width` across; two or more plane a strip
           from the first to the last (the plane follows their averaged normal, lowered by depth).
Each stroke becomes one blob named after it (<name>_r<i> for repeats; ".L" kept).
"""

from __future__ import annotations

import copy
import hashlib
import json
import math

import numpy as np

from .spec import SpecError

OPS = ("clay", "crease", "flatten")
_CACHE: dict[str, dict] = {}


def _unit(v) -> np.ndarray:
    v = np.asarray(v, float)
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-12)


def _r(v) -> list[float]:
    return [round(float(x), 5) for x in v]


def expand(spec: dict) -> dict:
    """Return a copy of spec (kits already expanded) with every stroke replaced by what it generates."""
    strokes = spec.get("strokes") or {}
    if not strokes:
        return spec
    out = copy.deepcopy(spec)
    out.pop("strokes")
    key = hashlib.sha1(json.dumps([out, strokes], sort_keys=True, default=float).encode()).hexdigest()
    if key not in _CACHE:
        if len(_CACHE) > 64:
            _CACHE.clear()
        _CACHE[key] = _generate(out, strokes)
    for kind, items in _CACHE[key].items():
        have = out.setdefault(kind, {})
        for n, v in items.items():
            if n in have:
                raise SpecError(f"stroke output {kind[:-1]} {n!r} already exists")
            have[n] = copy.deepcopy(v)
    return out


class Surface:
    """Raycasts against the (mirrored) body without strokes."""

    def __init__(self, base: dict):
        from .spec import compile_prims, expand_mirror
        self.spec = expand_mirror(base)
        self.prims = compile_prims(base)
        adds = [p for p in self.prims if p.op == "add"]
        self.span = float(np.linalg.norm(np.max([p.hi for p in adds], 0) - np.min([p.lo for p in adds], 0)))

    def f(self, pts: np.ndarray) -> np.ndarray:
        from . import sdf
        return sdf.field_at(self.prims, pts)

    def normals(self, pts: np.ndarray) -> np.ndarray:
        from . import sdf
        return _unit(sdf.gradient(self.prims, np.atleast_2d(pts), 1e-4))

    def _bisect(self, lo: np.ndarray, hi: np.ndarray, iters: int = 30) -> np.ndarray:
        """lo inside, hi outside (arrays of points): the crossing between them."""
        for _ in range(iters):
            mid = (lo + hi) / 2
            inside = self.f(mid) < 0
            lo = np.where(inside[:, None], mid, lo)
            hi = np.where(inside[:, None], hi, mid)
        return (lo + hi) / 2

    def exit(self, origin: np.ndarray, d: np.ndarray, what: str) -> np.ndarray:
        """Where a ray from inside the body, heading along d, first leaves it."""
        us = np.linspace(0.0, self.span, 800)
        f = self.f(origin + us[:, None] * d)
        if f[0] >= 0:
            raise SpecError(f"{what}: the bone axis at {_r(origin)} is outside the body")
        out = np.flatnonzero(f >= 0)
        if not len(out):
            raise SpecError(f"{what}: no surface along {_r(d)} from {_r(origin)}")
        k = out[0]
        return self._bisect(origin[None] + us[k - 1] * d, origin[None] + us[k] * d)[0]

    def entry(self, point: np.ndarray, facing: np.ndarray, what: str) -> np.ndarray:
        """First surface point hit by a ray arriving along -facing through `point`."""
        start = point + facing * self.span
        us = np.linspace(0.0, 2 * self.span, 1600)
        f = self.f(start - us[:, None] * facing)
        hit = np.flatnonzero(f < 0)
        if not len(hit) or hit[0] == 0:
            raise SpecError(f"{what}: no surface along {_r(-facing)} through {_r(point)}")
        k = hit[0]
        return self._bisect(start[None] - us[k] * facing, start[None] - us[k - 1] * facing)[0]

    def nearest_along(self, p: np.ndarray, n: np.ndarray, reach: np.ndarray, what: str) -> np.ndarray:
        """For each point p (m, 3), the inside-to-outside crossing along its line p + u n closest to u = 0,
        |u| <= reach. Used to drop resampled path points (on a chord, below the skin) back onto it."""
        us = np.linspace(-1.0, 1.0, 121)[None, :] * reach[:, None]      # (m, K)
        pts = p[:, None, :] + us[..., None] * n[:, None, :]
        f = self.f(pts)
        cross = (f[:, :-1] < 0) & (f[:, 1:] >= 0)
        if not cross.any(axis=1).all():
            bad = int(np.flatnonzero(~cross.any(axis=1))[0])
            raise SpecError(f"{what}: lost the surface near {_r(p[bad])} (path jumps across a gap?)")
        mid = 0.5 * (us[:, :-1] + us[:, 1:])
        k = np.argmin(np.where(cross, np.abs(mid), np.inf), axis=1)
        rows = np.arange(len(p))
        return self._bisect(pts[rows, k], pts[rows, k + 1])


def _rot_about(axis, deg: float) -> np.ndarray:
    from .kits import _rot_about as rot
    return rot(axis, deg)


def _euler(R: np.ndarray) -> list[float]:
    from .kits import _euler as eul
    return eul(R)


def _points(name: str, st: dict) -> list[dict]:
    """Control points with left-out keys inherited from the previous point of the same kind."""
    path = st.get("path")
    if not path:
        raise SpecError(f"stroke {name!r}: needs a non-empty \"path\"")
    pts = []
    for pt in path:
        if "bone" not in pt and "at" not in pt:
            if not pts:
                raise SpecError(f"stroke {name!r}: the first point needs \"bone\" or \"at\"")
            pt = {**pts[-1], **pt}
        pts.append(dict(pt))
    return pts


def _shift(pts: list[dict], shift: dict, i: int) -> list[dict]:
    out = []
    for pt in pts:
        q = dict(pt)
        if "t" in shift:
            q["t"] = float(q.get("t", 0.5)) + i * float(shift["t"])
        if "around" in shift:
            q["around"] = float(q.get("around", 0.0)) + i * float(shift["around"])
        if "offset" in shift:
            q["offset"] = [a + i * float(b) for a, b in zip(q.get("offset", [0, 0, 0]), shift["offset"])]
        out.append(q)
    return out


def _seat(surf: Surface, pt: dict, what: str) -> np.ndarray:
    from .spec import resolve_point
    if "bone" in pt:
        b = surf.spec["bones"].get(pt["bone"])
        if b is None:
            raise SpecError(f"{what}: unknown bone {pt['bone']!r}")
        a, bb = resolve_point(surf.spec, b["a"]), resolve_point(surf.spec, b["b"])
        axis = _unit(bb - a)
        side = np.asarray(pt.get("side", [0, 0, 1]), float)
        side = side - axis * (side @ axis)
        if np.linalg.norm(side) < 1e-6:
            raise SpecError(f"{what}: \"side\" is along the bone; give a direction across it")
        d = _rot_about(axis, float(pt.get("around", 0.0))) @ _unit(side)
        return surf.exit(a + (bb - a) * float(pt.get("t", 0.5)), d, what)
    p = resolve_point(surf.spec, pt["at"]) + np.asarray(pt.get("offset", [0, 0, 0]), float)
    return surf.entry(p, _unit(pt.get("dir", [0, -1, 0])), what)


def _per_point(st: dict, key: str, n: int, default, name: str) -> np.ndarray:
    v = st.get(key, default)
    if v is None:
        return None
    v = np.asarray(v, float)
    if v.ndim == 0:
        return np.full(n, float(v))
    if len(v) != n:
        raise SpecError(f"stroke {name!r}: {key} has {len(v)} values for {n} control points")
    return v


def _generate(base: dict, strokes: dict) -> dict:
    surf = Surface(base)
    gen = {"blobs": {}}
    for name, st in strokes.items():
        op = st.get("op", "clay")
        if op not in OPS:
            raise SpecError(f"stroke {name!r}: unknown op {op!r} (have {', '.join(OPS)})")
        stem, sfx = (name[:-2], ".L") if name.endswith(".L") else (name, "")
        pts = _points(name, st)
        rep = st.get("repeat") or {}
        count = int(rep.get("count", 1))
        for i in range(count):
            scale = float(rep.get("scale", 1.0)) ** i
            prefix = f"{stem}_r{i}" if count > 1 else stem
            group = None
            _one(surf, gen, f"{name} copy {i}" if count > 1 else name, op, st,
                 _shift(pts, rep.get("shift", {}), i), scale, prefix, sfx, group)
    return gen


def _one(surf: Surface, gen: dict, what: str, op: str, st: dict, pts: list[dict], scale: float,
         prefix: str, sfx: str, group):
    n = len(pts)
    S = np.array([_seat(surf, pt, f"stroke {what} point {i}") for i, pt in enumerate(pts)])
    N = surf.normals(S)
    width = _per_point(st, "width", n, 0.01, what) * scale
    depth = _per_point(st, "depth", n, 0.004, what) * scale
    extra = {"layer": int(st["layer"])} if st.get("layer") else {}

    if op == "flatten":
        nrm = _unit(N.mean(0))
        P = S[[0, -1]] if n > 1 else S[:1]
        w = float(width.max())
        dep = float(depth.mean())
        gen["blobs"][f"{prefix}{sfx}"] = {
            "shape": "flatten", "at": [0, 0, 0], "pts": [_r(q - nrm * dep) for q in P], "nrm": [_r(nrm)],
            "width": round(w, 5), "soft": round(float(st.get("soft", 0.8 * w)), 5),
            "height": round(dep + 0.5 * w, 5), "blend": round(float(st.get("blend", 0.2 * w)), 5), **extra}
        return

    if n > 1:  # resample between control points and drop the samples back onto the surface
        # Positions follow a Catmull-Rom curve through the control points and width/depth ease in and out
        # of each one (smoothstep): linear interpolation would kink the surface across the stroke at every
        # control point, which reads as a crease line.
        step = 0.35 * float(width.min())
        ext = np.concatenate([2 * S[:1] - S[1:2], S, 2 * S[-1:] - S[-2:-1]])
        Ps, Ns, W, D = [S[0]], [N[0]], [width[0]], [depth[0]]
        for i in range(n - 1):
            p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
            m = max(1, math.ceil(np.linalg.norm(S[i + 1] - S[i]) / step))
            for j in range(1, m + 1):
                a = j / m
                Ps.append(0.5 * (2 * p1 + (p2 - p0) * a + (2 * p0 - 5 * p1 + 4 * p2 - p3) * a * a
                                 + (3 * p1 - p0 - 3 * p2 + p3) * a ** 3))
                e = a * a * (3 - 2 * a)
                Ns.append(_unit(N[i] + e * (N[i + 1] - N[i])))
                W.append(width[i] + e * (width[i + 1] - width[i]))
                D.append(depth[i] + e * (depth[i + 1] - depth[i]))
        S, N, width, depth = np.array(Ps), np.array(Ns), np.array(W), np.array(D)
        if len(S) > 2:  # the in-between samples lie on chords, below the skin
            inner = slice(1, -1)
            reach = np.full(len(S) - 2, step * 4 + float(np.linalg.norm(S[-1] - S[0])) * 0.25)
            S[inner] = surf.nearest_along(S[inner], N[inner], reach, f"stroke {what}")
            N[inner] = surf.normals(S[inner])
    sign = 1.0 if op == "clay" else -1.0
    gen["blobs"][f"{prefix}{sfx}"] = {
        "shape": "displace", "at": [0, 0, 0], "pts": [_r(q) for q in S], "nrm": [_r(v) for v in N],
        "width": _r(width), "depth": _r(sign * depth),
        "profile": st.get("profile", "soft" if op == "clay" else "sharp"), **extra}
