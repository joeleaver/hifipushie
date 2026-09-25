"""What paint (and the bake) can know about a point on the surface, computed lazily from the exact field.

Points holds a set of surface points (mesh vertices or baked texels): position, normal, part, and on demand
  ao, sky     ambient occlusion and openness to the sky (0..1): measured by Cycles in the Blender scene
              (scene.raytraced) and passed in through `cache`; asking for them otherwise is an error
  curvature   mean curvature (1/m, 1/r on a sphere of radius r; convex > 0), from the part's own field
  thickness   how far (m) the part goes on behind the point, against the normal (`thickness`)
  hidden      1 where the point is buried inside another part
  grain       the long axis of the element the point belongs to (sign arbitrary, length = how much its ends
              read as end grain: 1 on logs and legs, 0 on slabs and boards): wood grain,
              brushed metal, per board and log (`grain`); grain_seed: 0..1 per element, so parallel boards
              don't share one continuous pattern
Each is computed once for the whole set and kept in `cache`, which the caller may prefill.
"""

from __future__ import annotations

import numpy as np

from . import sdf

FIELD_INPUTS = ("ao", "curvature", "thickness", "sky")
INPUTS_VERSION = 4  # bump when how any input is measured changes: the scene's cached inputs are redone


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
            if key in ("ao", "sky"):
                raise KeyError(f"{key} is measured by Cycles in the Blender scene (scene.raytraced) and passed in "
                               f"(Points(cache=...)); there's no SDF estimate of it any more")
            elif key == "hidden":
                self.cache[key] = hidden(self.streams, self.pos, self.part, self.part_names, self.voxel)
            elif key in ("grain", "grain_seed", "radial"):
                self.cache["grain"], self.cache["grain_seed"], self.cache["radial"] = grain(
                    self.streams, self.pos, self.part, self.part_names, self.voxel)  # radial: (n, 3) offsets
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
    # exact values out to the stencil (clipped evaluation is only exact within a primitive's blend reach: a
    # sample h off a thin board with a small blend came back as the "far away" value, curvature ~1/mm on flat tops)
    f = sdf.field_at(prims, pts[:, None, :] + st[None], margin=2 * h)
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


def element_axis(p) -> np.ndarray:
    """A primitive's long axis (world, unit): a bone's axis, a box's or ellipsoid's longest side, a cylinder's
    axis if it's taller than wide, else across it (a round table top's grain runs across the disc)."""
    pr, kind = (p.params["p"], p.params["kind"]) if p.kind == "csg" else (p.params, p.kind)
    if kind == "cone":
        return np.asarray(pr["frame"][1], float)
    if kind in ("box", "ellipsoid", "lids"):
        return np.asarray(pr["rot"], float)[:, int(np.argmax(pr["size"]))]
    if kind == "cylinder":
        rx, ry, hz = pr["size"]
        return np.asarray(pr["rot"], float)[:, 2 if hz >= max(rx, ry) else (0 if rx >= ry else 1)]
    if kind == "blade":  # along its length (a leaf's midrib, a feather's shaft)
        return np.asarray(pr["rot"], float)[:, 1]
    return np.array([0.0, 0.0, 1.0])


PANEL = 0.25  # m: a box face wider than this both ways is a panel (a cabinet's side), not a piece's end grain


def end_weight(p) -> float:
    """How much a primitive's ends read as end grain, by how chunky its cross-section is (least / other side
    across the grain): 1 for logs, legs, beams (ratio >= 0.5), 0 for slabs and boards (<= 0.25): a table
    top's or a board's edge is finished wood, not a sawn, checked log end."""
    pr, kind = (p.params["p"], p.params["kind"]) if p.kind == "csg" else (p.params, p.kind)
    if kind == "cone":
        fw, fh = pr["flat"]
        r = min(fw, fh) / max(fw, fh)
    elif kind == "cylinder":
        rx, ry, hz = pr["size"]
        r = min(rx, ry) / max(rx, ry) if hz >= max(rx, ry) else hz / min(rx, ry)
    elif kind in ("box", "ellipsoid", "lids"):
        a, b, _ = np.sort(np.asarray(pr["size"], float))
        r = a / b
    elif kind == "blade":  # a sheet: no end grain
        return 0.0
    else:
        return 1.0
    t = float(np.clip((r - 0.25) / 0.25, 0.0, 1.0))
    return t * t * (3 - 2 * t)


def grain(streams: dict, X: np.ndarray, part: np.ndarray, names: list, voxel: float):
    """Each point's element (the additive primitive of its own part whose surface is nearest) and that
    element's long axis, a 0..1 seed hashed from its name, and the offset from its axis line (growth rings: its
    length is the radius): ((n, 3), (n,), (n, 3)). The axis's length is the
    element's `end_weight` (at least 1e-3): facing "element" reads |n . grain|, stretch only its direction. On a box face wider than PANEL
    both ways the grain runs along the face's longer side instead (a cabinet built of panels)."""
    import zlib
    g = np.tile(np.array([0.0, 0.0, 1.0]), (len(X), 1))
    seed = np.zeros(len(X))
    radial = np.zeros((len(X), 3))  # offset from the element's own axis line (linear in position, so it
    # interpolates exactly across a triangle; its length is the ring radius): growth rings on cut ends
    for i, pn in enumerate(names):
        sel = np.flatnonzero(part == i)
        if not len(sel) or pn not in streams:
            continue
        P = X[sel]
        best = np.full(len(sel), np.inf)
        for p in streams[pn]:
            if p.op != "add" or p.kind in ("shell", "displace", "flatten"):
                continue
            pad = 3 * voxel + float(np.max(p.reach)) if np.ndim(p.reach) else 3 * voxel + float(p.reach)
            near = np.flatnonzero(np.all((P >= p.lo - pad) & (P <= p.hi + pad), 1))
            if not len(near):
                continue
            pr, kind = (p.params["p"], p.params["kind"]) if p.kind == "csg" else (p.params, p.kind)
            Pn = P[near]
            wp = p.params.get("warp") if p.kind == "csg" else None
            if wp is not None:  # a deformed model: the element's own shape is where the point was before bending
                from .deform import undeform
                Pn = undeform(wp[0], Pn)
            d = np.abs(sdf.SDF[kind](Pn, pr))  # the element's own shape: cuts and noise don't move its axis
            win = d < best[near]
            if not win.any():
                continue
            k = near[win]
            best[k] = d[win]
            ax = element_axis(p)
            g[sel[k]] = ax * max(end_weight(p), 1e-3)
            c0 = np.asarray(pr["a"] if kind == "cone" else pr.get("c", Pn[win].mean(0)), float)
            q = Pn[win] - c0
            radial[sel[k]] = q - np.outer(q @ ax, ax)
            if kind == "box":  # a face too big to be a piece of wood's end is a panel: grain along its longer side
                rot, size = np.asarray(pr["rot"], float), np.asarray(pr["size"], float)
                q = (Pn[win] - pr["c"]) @ rot
                face = np.argmax(np.abs(q) / size, 1)
                ext = np.stack([np.delete(2 * size, f) for f in range(3)])  # each face's two extents
                idx = np.stack([np.delete(np.arange(3), f) for f in range(3)])
                big = (ext.min(1) > PANEL)[face]
                if big.any():
                    along = idx[face, np.argmax(ext[face], 1)]
                    g[sel[k[big]]] = rot[:, along[big]].T * max(end_weight(p), 1e-3)
            seed[sel[k]] = (zlib.crc32(p.name.encode()) % 10007) / 10007
    return g, seed, radial


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
