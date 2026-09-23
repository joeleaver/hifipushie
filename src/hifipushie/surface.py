"""What paint (and the bake) can know about a point on the surface, computed lazily from the exact field.

Points holds a set of surface points (mesh vertices or baked texels): position, normal, part, and on demand
  ao          ambient occlusion 0..1 (1 = open), from all parts' fields (`ao`)
  curvature   mean curvature (1/m, 1/r on a sphere of radius r; convex > 0), from the part's own field
  thickness   how far (m) the part goes on behind the point, against the normal (`thickness`)
  sky         how open the point is to the sky above (1 = open, 0 = roofed over), reaching much further than
              AO: rain, sun and snow reach it or they don't (`sky`)
  hidden      1 where the point is buried inside another part
Each is computed once for the whole set and kept in `cache`, which the caller may prefill (the bake passes the
AO it already computed) or persist (store keeps a mesh's inputs next to it, so repainting doesn't redo AO).
"""

from __future__ import annotations

import numpy as np

from . import sdf

FIELD_INPUTS = ("ao", "curvature", "thickness", "sky")


def unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


class Points:
    def __init__(self, spec: dict, pos: np.ndarray, normal: np.ndarray, part: np.ndarray, part_names: list[str],
                 voxel: float, cache: dict | None = None, streams: dict | None = None):
        self.spec, self.part_names, self.voxel = spec, list(part_names), float(voxel)
        self.pos = np.asarray(pos, np.float64)
        self.normal = unit(np.asarray(normal, np.float64))
        self.part = np.asarray(part)
        self.cache = {} if cache is None else cache
        self._streams = streams
        self.footprint = self.voxel  # how far apart the points are (m): texel size in a bake, ~voxel on a mesh

    def __len__(self):
        return len(self.pos)

    @property
    def streams(self) -> dict:
        """The prims of each part, by part name."""
        if self._streams is None:
            from .spec import compile_prims
            self._streams = {ps[0].part: ps for ps in sdf.streams(compile_prims(self.spec))}
        return self._streams

    def get(self, key: str) -> np.ndarray:
        if key not in self.cache:
            if key == "ao":
                self.cache[key] = ao(list(self.streams.values()), self.pos, self.normal, self.voxel)
            elif key == "sky":
                self.cache[key] = sky(list(self.streams.values()), self.pos, self.normal, self.voxel)
            elif key == "hidden":
                self.cache[key] = hidden(self.streams, self.pos, self.part, self.part_names, self.voxel)
            else:
                out = np.zeros(len(self))
                for i, pn in enumerate(self.part_names):
                    sel = np.flatnonzero(self.part == i)
                    if not len(sel) or pn not in self.streams:
                        continue
                    ps = self.streams[pn]
                    if key == "curvature":
                        out[sel] = laplacian(ps, self.pos[sel], self.voxel) / 2
                    elif key == "thickness":
                        out[sel] = thickness(ps, self.pos[sel], self.normal[sel], self.voxel,
                                             model_size(self.streams.values()))
                    else:
                        raise KeyError(key)
                self.cache[key] = out
        return self.cache[key]

    def moved(self, pos: np.ndarray, keep_inputs: bool = False) -> "Points":
        """New points near these (same parts, same normals), dropped back onto their parts' surfaces along the
        normal with one field evaluation (enough for offsets small against the curvature). keep_inputs: the
        offsets are tiny (finite differences), so the field inputs computed so far carry over."""
        pos = pos.copy()
        for i, pn in enumerate(self.part_names):
            sel = np.flatnonzero(self.part == i)
            if len(sel) and pn in self.streams:
                f = sdf.field_at(self.streams[pn], pos[sel])
                pos[sel] -= np.clip(f, -2 * self.voxel, 2 * self.voxel)[:, None] * self.normal[sel]
        out = Points(self.spec, pos, self.normal, self.part, self.part_names, self.voxel,
                     cache=dict(self.cache) if keep_inputs else None, streams=self._streams)
        out.footprint = self.footprint
        return out


def hidden(streams: dict, X: np.ndarray, part: np.ndarray, part_names: list[str], voxel: float) -> np.ndarray:
    """1 where a point is buried inside another part (skin under a solid shell, the back of an eyeball)."""
    out = np.zeros(len(X))
    for i, pn in enumerate(part_names):
        sel = np.flatnonzero(part == i)
        others = [ps for o, ps in streams.items() if o != pn]
        if others and len(sel):
            f = sdf.field_at([p for ps in others for p in ps], X[sel])
            out[sel] = f < -0.5 * voxel
    return out


def model_size(streams) -> float:
    size = 0.0
    for ps in streams:
        adds = [p for p in ps if p.op == "add"]
        if adds:
            size = max(size, float(np.max(np.max([p.hi for p in adds], 0) - np.min([p.lo for p in adds], 0))))
    return size


def newton(prims, x: np.ndarray, h: float, voxel: float, iterations: int = 6):
    """Newton-step points onto the part's zero set (steps capped at 2 voxels); points stop once they move less
    than a thousandth of a voxel. Returns the points and the field gradient there."""
    x = x.copy()
    g = np.zeros_like(x)
    todo = np.arange(len(x))
    for _ in range(iterations):
        if not len(todo):
            break
        f, g[todo] = sdf.value_gradient(prims, x[todo], h)
        step = (f / np.maximum((g[todo] ** 2).sum(1), 1e-12))[:, None] * g[todo]
        n = np.linalg.norm(step, axis=1, keepdims=True)
        x[todo] -= step * np.minimum(1.0, 2 * voxel / np.maximum(n, 1e-12))
        todo = todo[n[:, 0] > 1e-3 * voxel]
    if len(todo):
        g[todo] = sdf.value_gradient(prims, x[todo], h)[1]
    return x, g


def laplacian(prims, pts: np.ndarray, voxel: float) -> np.ndarray:
    """Laplacian of the exact field at pts (= 2/r on a sphere of radius r), one 7-point stencil evaluation."""
    h = 0.75 * voxel
    st = np.array([[0, 0, 0], [h, 0, 0], [-h, 0, 0], [0, h, 0], [0, -h, 0], [0, 0, h], [0, 0, -h]])
    f = sdf.field_at(prims, pts[:, None, :] + st[None])
    return (f[:, 1:].sum(1) - 6 * f[:, 0]) / (h * h)


def _frame(N):
    ref = np.where(np.abs(N[:, 2:3]) < 0.9, [[0.0, 0.0, 1.0]], [[1.0, 0.0, 0.0]])
    U = unit(np.cross(N, ref))
    return U, np.cross(N, U)


def _cone(N, tilt_deg: float, ring: int):
    """The axis N plus `ring` directions tilted from it, with cosine weights."""
    U, V = _frame(N)
    t = np.radians(tilt_deg)
    return [(N, 1.0)] + [(np.cos(t) * N + np.sin(t) * (np.cos(a) * U + np.sin(a) * V), np.cos(t))
                         for a in np.linspace(0, 2 * np.pi, ring, endpoint=False) + 0.3]


def ao(streams: list, X: np.ndarray, N: np.ndarray, voxel: float, samples: int = 3, ring: int = 6) -> np.ndarray:
    """SDF ambient occlusion over the hemisphere: along the normal and a ring of directions tilted 50 deg from it,
    how open each is (the narrowest field / distance ratio of a few steps out, like a cone's soft shadow),
    cosine-weighted. Every part occludes every other: a sleeve darkens the arm under it."""
    step = 0.008 * model_size(streams)
    dirs = _cone(N, 50, ring)
    prims = [p for ps in streams for p in ps]
    q, den = [], []
    for D, w in dirs:
        for i in range(1, samples + 1):
            d = i * step
            q.append(X + D * d + N * (0.25 * voxel))
            den.append(d * w)
    f = sdf.field_at(prims, np.stack(q, 1))  # (n, dirs * samples): one call, so it all goes on the pool
    vis = np.clip(f / np.array(den)[None], 0, 1).reshape(len(X), len(dirs), samples).min(2)
    w = np.array([w for _, w in dirs])
    return np.clip(vis @ w / w.sum(), 0, 1)


def sky(streams: list, X: np.ndarray, N: np.ndarray, voxel: float, samples: int = 6, ring: int = 6) -> np.ndarray:
    """Openness to the sky: rays up (straight and a ring 35 deg off vertical) marched out to 0.3 x the model
    size (a roof, an eave, a table top over the point all count), each scored like an AO cone (field over
    distance), cosine-weighted. Points on down-facing skin still look up, from just outside themselves."""
    size = model_size(streams)
    reach = 0.3 * size
    depths = reach * (np.arange(1, samples + 1) / samples) ** 1.6
    up = np.broadcast_to(np.array([0.0, 0.0, 1.0]), X.shape)
    dirs = _cone(up, 35, ring)
    prims = [p for ps in streams for p in ps]
    start = X + N * (1.5 * voxel)
    q = np.stack([start + D * d for D, _ in dirs for d in depths], 1)
    f = sdf.field_at(prims, q).reshape(len(X), len(dirs), samples)
    vis = np.clip(f / (0.35 * depths[None, None]), 0, 1).min(2)
    w = np.array([w for _, w in dirs])
    return vis @ w / w.sum()


def thickness(prims, X: np.ndarray, N: np.ndarray, voxel: float, size: float, samples: int = 10,
              ring: int = 4) -> np.ndarray:
    """How far the part goes on behind each point (m): along -normal and a ring 25 deg off it, the depth where
    the ray leaves the part (between the last inside and first outside sample), cosine-weighted. Rays that don't
    leave within 0.08 * the model size count as that deep, so thick bodies all read the same."""
    dmax = 0.08 * size
    depths = dmax * (np.arange(1, samples + 1) / samples) ** 1.5  # finer near the skin: thin parts
    dirs = _cone(-N, 25, ring)
    q = np.stack([X + D * d for D, _ in dirs for d in depths], 1) - N[:, None] * (0.25 * voxel)
    f = sdf.field_at(prims, q).reshape(len(X), len(dirs), samples)
    outside = f >= 0
    k = np.argmax(outside, axis=2)  # the first sample outside (0 when none is)
    exits = outside.any(2)
    fk = np.take_along_axis(f, k[..., None], 2)[..., 0]
    fp = np.take_along_axis(f, np.maximum(k - 1, 0)[..., None], 2)[..., 0]
    dk, dp = depths[k], np.where(k > 0, depths[np.maximum(k - 1, 0)], 0.0)
    fp = np.where(k > 0, fp, -0.25 * voxel)
    t = np.clip(-fp / np.maximum(fk - fp, 1e-12), 0, 1)
    out = np.where(exits, dp + t * (dk - dp), dmax)
    w = np.array([w for _, w in dirs])
    return out @ w / w.sum()
