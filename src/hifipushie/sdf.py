"""Evaluate compiled primitives onto a voxel grid and mesh the zero level set.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at sdf.NAME: C422). sdf_shapes: the shapes: smooth minimum, one signed distance function per primitive kind
(`SDF`: the table of them) and the modifiers of a combined field (`MODS`).
"""
from __future__ import annotations

import hashlib
import os
import threading
import warnings
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np
from scipy import sparse
from skimage import measure

from .spec import Prim
from . import moved

FAR = 1.0  # field value where no primitive reaches; only its sign matters there

PROFILES = {
    # cross-section of a stroke, x = distance from its path / width, 0..1 -> 1..0; and max |slope|
    "soft": (lambda x: (1 - x * x) ** 2, 1.54),       # a bell: melted-in clay
    "sharp": (lambda x: (1 - x) ** 2, 2.0),           # a cusp at the path: a crisp crease or ridge line
    "round": (lambda x: 1 - x * x, 2.0),              # a dome with a defined edge
    "flat": (lambda x: _smoothstep(np.clip((1 - x) / 0.35, 0, 1)), 4.3),  # a plateau: flat top, soft rim
}


def _smoothstep(s):
    return s * s * (3 - 2 * s)


@dataclass
class Grid:
    field: np.ndarray  # (nx, ny, nz)
    origin: np.ndarray
    voxel: float


BLOCK = 8  # narrow-band block edge, in voxels


def units(prims: list[Prim]):
    """Primitives in combination order, with consecutive members of a group together: a group (e.g. the
    segments of a lip or a finger) is joined first, with its own small `join` blend (0 = hard min), and
    blended into the rest once, so its segments don't each add a full smooth-union bulge where they
    overlap."""
    i = 0
    while i < len(prims):
        j = i + 1
        if prims[i].group and prims[i].op != "modify":
            while j < len(prims) and prims[j].group == prims[i].group and prims[j].op == prims[i].op:
                j += 1
        yield prims[i:j]
        i = j


def _merge(hits: list[np.ndarray], ds: list[np.ndarray], tail: tuple, join: float, mul=None):
    """Union of a group's primitives (smooth by `join`, usually small or 0), each given on its own indices.
    mul(indices) -> how much of the join holds at each of those places (a fuse with sides); None = all of it."""
    from . import sdf_shapes
    if len(hits) == 1:
        return hits[0], ds[0]
    h = np.unique(np.concatenate(hits))
    d = np.full((len(h), *tail), FAR, dtype=ds[0].dtype)
    for i, (hit, v) in enumerate(zip(hits, ds)):  # (a fuse: each mass by its own join and sides; else one for all)
        k = np.searchsorted(h, hit)
        ji = join[i] if isinstance(join, list) else join
        mi = mul[i] if isinstance(mul, list) else mul
        d[k] = sdf_shapes.smin(d[k], v, ji) if mi is None else sdf_shapes.smin_var(d[k], v, ji * mi(hit)).astype(d.dtype)
    return h, d


def combine(cur: np.ndarray, d: np.ndarray, p: Prim) -> np.ndarray:
    from . import sdf_shapes
    if p.op == "add":
        return sdf_shapes.smin(cur, d, p.blend)
    if p.op == "intersect":  # keep only what's inside d (a clothing part's region)
        return -sdf_shapes.smin(-cur, -d, p.blend)
    return -sdf_shapes.smin(-cur, d, p.blend)


def streams(prims: list[Prim]) -> list[list[Prim]]:
    """Primitives split by part, in order. Each part is its own field; the model is their hard union."""
    out: dict[str, list[Prim]] = {}
    for p in prims:
        out.setdefault(p.part, []).append(p)
    return list(out.values())


def frame(prims: list[Prim], resolution: int = 160, pad: float = 0.02, box=None):
    """Grid placement (lo, voxel, shape) covering every part's additive primitives, optionally cut to box."""
    adds = [p for p in prims if p.op == "add"]
    if not adds:
        raise ValueError("nothing to build: no additive primitives")
    lo = np.min([p.lo for p in adds], axis=0) - pad
    hi = np.max([p.hi for p in adds], axis=0) + pad
    if box is not None:
        lo, hi = np.maximum(lo, box[0]), np.minimum(hi, box[1])
        if np.any(hi <= lo):
            raise ValueError("the close-up box doesn't touch the model")
    voxel = float((hi - lo).max() / resolution)
    return lo, voxel, np.ceil((hi - lo) / voxel).astype(int) + 1


def evaluate(prims: list[Prim], resolution: int = 160, pad: float = 0.02, box=None, at=None) -> Grid:
    """Sample the field on a grid, exactly only in blocks the surface can pass through.

    The field is (close to) 1-Lipschitz, so a block whose centre value exceeds its half-diagonal holds
    no surface; those blocks just take the centre value, which is all marching cubes needs (the sign).
    box=(lo, hi) limits the grid to that region (for close-ups); the cut is capped where it crosses the body.
    at=(lo, voxel, shape) from frame() puts the grid exactly there (to mesh parts on one shared grid).
    Several parts: each is evaluated on its own and the results hard-unioned."""
    lo, voxel, shape = at if at is not None else frame(prims, resolution, pad, box)
    fields = [_evaluate_part(ps, lo, voxel, shape) for ps in streams(prims)]
    return Grid(fields[0] if len(fields) == 1 else np.minimum.reduce(fields), lo, voxel)


def _evaluate_part(prims: list[Prim], lo: np.ndarray, voxel: float, shape) -> np.ndarray:
    return PartGrid().update(prims, (lo, voxel, shape))[0]


def fingerprint(p: Prim, cuts: bool = True) -> str:
    """Content hash of a primitive: equal fingerprints give equal field contributions. A shell's base part
    is left out (the shell part inherits its base's changed regions instead). cuts=False: without the targeted
    cuts folded into it (the same shape before cutting)."""
    h = hashlib.sha1(repr((p.name, p.kind, p.op, p.blend, p.layer, p.group, p.join, p.part, p.lip)
                          + ((p.sides,) if p.sides else ())).encode())
    for k in sorted(p.params):
        v = p.params[k]
        if k in ("prims", "tree") or (k == "cuts" and not cuts):
            continue
        h.update(k.encode())
        h.update(np.ascontiguousarray(v).tobytes() if isinstance(v, np.ndarray) else repr(v).encode())
    return h.hexdigest()


class PartGrid:
    """One part's field on a fixed grid, kept between builds. update() re-evaluates only the blocks that the
    primitives added, removed or changed since the last call can reach (plus any extra boxes, e.g. where a
    shell's base part changed), and returns the field and those boxes."""

    def __init__(self):
        self.at_key = None
        self.fps: dict[str, tuple] = {}

    def update(self, prims: list[Prim], at, extra=()):
        lo, voxel, shape = at
        B = BLOCK
        nb = -(-np.asarray(shape) // B)
        half_diag = voxel * (B - 1) * np.sqrt(3) / 2
        at_key = (tuple(np.round(lo, 9)), round(voxel, 12), tuple(int(x) for x in shape))
        # where each primitive can change anything, block centre values included
        grow = 2 * half_diag + 2 * voxel
        fps = {}
        for q in prims:
            m = grow + (0.0 if q.op == "modify" else float(np.max(q.reach)))
            fps[fingerprint(q)] = (q.lo - m, q.hi + m)
        if at_key != self.at_key:
            self.blocks = np.empty((*nb, B, B, B), np.float32)
            redo = np.ones(tuple(nb), bool)
            boxes = [(lo, lo + voxel * (np.asarray(shape) - 1))]
        else:
            changed = set(fps) ^ set(self.fps)
            boxes = [fps[f] if f in fps else self.fps[f] for f in changed] + list(extra)
            b_lo = lo + voxel * B * np.stack(np.meshgrid(*[np.arange(n) for n in nb], indexing="ij"), -1)
            b_hi = b_lo + voxel * (B - 1)
            redo = np.zeros(tuple(nb), bool)
            for blo, bhi in boxes:
                redo |= np.all((b_hi >= blo) & (b_lo <= bhi), axis=-1)
        # The grid only claims to match (at_key, fps) once its blocks are filled: an update cut short (an
        # exception, a cancelled tool call) must not leave the next one trusting unwritten memory, whose random
        # signs mesh into millions of vertices and whose NaNs Taubin smoothing spreads.
        self.at_key = None
        if redo.any():
            self._redo(prims, lo, voxel, np.argwhere(redo), half_diag)
        self.at_key, self.fps = at_key, fps
        field = self.blocks.transpose(0, 3, 1, 4, 2, 5).reshape(nb * B)
        return np.ascontiguousarray(field[:shape[0], :shape[1], :shape[2]]), boxes

    def _redo(self, prims, lo, voxel, idx, half_diag):
        B = BLOCK
        b_lo = lo + voxel * B * idx
        centre = field_at(prims, b_lo + voxel * (B - 1) / 2, margin=2 * half_diag)
        # modifiers and grabs make the field steeper than 1 (by up to lip), so the surface can be further from a
        # centre: only in the blocks such a primitive can reach (over the whole part, one grabbed hoof made every
        # block of a figure's band 3x wider and a 2 s build 17 s)
        cpts = b_lo + voxel * (B - 1) / 2
        lip = np.ones(len(idx))
        for p in prims:
            if p.lip > 1.0:
                m = (0.0 if p.op == "modify" else float(np.max(p.reach))) + 2 * half_diag + 2 * voxel
                near = np.all((cpts >= p.lo - m) & (cpts <= p.hi + m), axis=1)
                lip[near] = np.maximum(lip[near], p.lip)
        act = np.abs(centre) <= lip * 1.5 * half_diag + voxel
        self.blocks[tuple(idx[~act].T)] = centre[~act, None, None, None]
        a_idx, a_lo = idx[act], b_lo[act]
        if not len(a_idx):
            return
        a_hi = a_lo + voxel * (B - 1)
        local = voxel * np.stack(np.meshgrid(*[np.arange(B)] * 3, indexing="ij"), -1)
        vals = np.empty((len(a_idx), B, B, B), np.float32)

        def work(ix):
            ps = _cull(prims, a_lo[ix].min(0), a_hi[ix].max(0), voxel + 1.5 * half_diag)
            vals[ix] = _block_values(ps, a_lo[ix], a_hi[ix], local, voxel, half_diag)

        _run(work, _chunks(a_lo, 256))
        self.blocks[tuple(a_idx.T)] = vals


class _Undeformed:
    """Points undeformed once per deformation (deform.py) and shared by every deformed primitive evaluated on
    them: undoing the bend per primitive made a deformed cabin build ~9x slower."""

    def __init__(self, pts):
        self.pts, self.cache = pts, {}

    def of(self, p: Prim, idx):
        wp = p.params.get("warp") if p.kind == "csg" else None
        if wp is None or (wp[0] and "bend" in wp[0][-1]):  # (a bend is two pieces: sd_csg undoes it itself)
            return None
        k = id(wp[0])
        if k not in self.cache:
            from .deform import undeform
            sh = self.pts.shape
            self.cache[k] = undeform(wp[0], self.pts.reshape(-1, 3)).reshape(sh)
        return self.cache[k][idx]


def _sd(p: Prim, pts, und: "_Undeformed", idx):
    from . import sdf_shapes
    pre = und.of(p, idx)
    return sdf_shapes.SDF[p.kind](pts, p.params) if pre is None else sdf_shapes.sd_csg(pts, p.params, pre)


def _block_values(prims: list[Prim], a_lo, a_hi, local, voxel: float, half_diag: float) -> np.ndarray:
    """Field values in a set of blocks (their low corners a_lo), all of one part's primitives in order."""
    from . import sdf_shapes
    B = BLOCK
    vals = np.full((len(a_lo), B, B, B), FAR, np.float32)
    und = _Undeformed(a_lo[:, None, None, None, :] + local)
    for unit in units(prims):
        if unit[0].op == "modify":
            p = unit[0]
            hit = np.flatnonzero(np.all((a_hi >= p.lo - voxel) & (a_lo <= p.hi + voxel), axis=1))
            if len(hit):
                vals[hit] = sdf_shapes.MODS[p.kind](vals[hit], a_lo[hit, None, None, None, :] + local, p.params)
            continue
        hits, ds, joins, muls = [], [], [], []
        for p in unit:
            margin = p.reach + voxel
            hit = np.flatnonzero(np.all((a_hi >= p.lo - margin) & (a_lo <= p.hi + margin), axis=1))
            # AABBs of slanted bones are loose: also drop blocks this primitive can't reach
            # (a grabbed primitive's field is up to p.lip steeper than a distance: allow for it)
            hit = hit[sdf_shapes.SDF[p.kind](a_lo[hit] + voxel * (B - 1) / 2, p.params) <= p.inert + p.lip * 1.5 * half_diag]
            if len(hit):
                hits.append(hit)
                ds.append(_sd(p, a_lo[hit, None, None, None, :] + local, und, hit).astype(np.float32))
                joins.append(p.join)
                muls.append((lambda hh, s=p.sides: sdf_shapes.sides_mul(s, a_lo[hh, None, None, None, :] + local)) if p.sides else None)
        if unit[-1].op == "intersect":  # outside every region primitive's reach is outside the region
            d = np.full((len(a_lo), B, B, B), FAR, np.float32)
            if hits:
                h, dh = _merge(hits, ds, (B, B, B), unit[0].join)
                d[h] = dh
            vals = combine(vals, d, unit[-1])
            continue
        if not hits:
            continue
        fused = (unit[0].group or "").startswith("fuse:")
        h, d = _merge(hits, ds, (B, B, B), joins if fused else unit[0].join, muls if fused else None)
        vals[h] = combine(vals[h], d, unit[-1])
    return vals


# ---------------------------------------------------------------- spatial chunking and threads
# Every primitive tests every point against its box, so cost is primitives x points. Sorting points into
# compact chunks (Morton order) and culling the primitive list per chunk makes each chunk see only the few
# primitives near it; chunks run on a thread pool (numpy releases the GIL in its loops).
_POOL: ThreadPoolExecutor | None = None
_LOCAL = threading.local()


def _run(fn, chunks):
    """fn(chunk) for every chunk: on the pool from the top level, inline when already inside a worker (a
    shell part's field is evaluated from within its own evaluation) or for a single chunk."""
    global _POOL
    if len(chunks) <= 1 or getattr(_LOCAL, "busy", False):
        for c in chunks:
            fn(c)
        return
    if _POOL is None:
        _POOL = ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 1))

    def job(c):
        _LOCAL.busy = True
        try:
            fn(c)
        finally:
            _LOCAL.busy = False
    list(_POOL.map(job, chunks))


def _chunks(pts: np.ndarray, size: int) -> list[np.ndarray]:
    """Indices of pts split into spatially compact chunks of about `size` (Morton order on a 1024^3 grid)."""
    n = len(pts)
    if n <= size:
        return [np.arange(n)]
    lo = pts.min(0)
    span = max(float(np.ptp(pts, axis=0).max()), 1e-12)
    c = np.minimum((pts - lo) / span * 1024, 1023).astype(np.uint64)
    key = np.zeros(n, np.uint64)
    for bit in range(10):
        for axis in range(3):
            key |= ((c[:, axis] >> np.uint64(bit)) & np.uint64(1)) << np.uint64(3 * bit + axis)
    return np.array_split(np.argsort(key, kind="stable"), -(-n // size))


def _cull(prims: list[Prim], lo: np.ndarray, hi: np.ndarray, margin: float) -> list[Prim]:
    """The primitives that can affect anything in the box [lo, hi] (grown by margin), in order. Region
    (intersect) primitives always stay: missing them means outside the region, not 'no change'."""
    out = []
    for p in prims:
        r = (0.0 if p.op == "modify" else p.reach) + margin
        if p.op == "intersect" or (np.all(p.hi + r >= lo) and np.all(p.lo - r <= hi)):
            out.append(p)
    return out


def field_at(prims: list[Prim], pts: np.ndarray, clip: bool = True, margin: float = 0.0) -> np.ndarray:
    """Exact combined field at arbitrary points (..., 3), combined in the same order as evaluate().
    clip=False evaluates every primitive everywhere, so far from the shape the value is a real distance
    rather than FAR (slower; the fitter needs it to pull toward parts the model is missing).
    margin widens the clipping, so values within `margin` of the surface are real distances too.
    Several parts: the hard union of each part's field."""
    if pts.size == 0:  # e.g. a shell's base evaluated for a close-up block holding none of its points
        return np.full(pts.shape[:-1], FAR if clip else np.inf)
    parts = streams(prims)
    flat = pts.reshape(-1, 3)
    if not clip:
        if len(parts) > 1:
            return np.minimum.reduce([field_at(ps, pts, clip, margin) for ps in parts])
        return _field_serial(prims, flat, clip, margin).reshape(pts.shape[:-1])
    out = np.empty(len(flat))

    def work(idx):  # points sorted and chunked once; each part culled and evaluated per chunk
        q = flat[idx]
        lo, hi = q.min(0), q.max(0)
        v = None
        for ps in parts:
            culled = _cull(ps, lo, hi, margin)
            if not culled:
                continue
            f = _field_serial(culled, q, clip, margin)
            v = f if v is None else np.minimum(v, f)
        out[idx] = FAR if v is None else v

    _run(work, _chunks(flat, 4096))
    return out.reshape(pts.shape[:-1])


def _field_serial(prims: list[Prim], flat: np.ndarray, clip: bool, margin: float) -> np.ndarray:
    from . import sdf_shapes
    out = np.full(len(flat), FAR if clip else np.inf)
    und = _Undeformed(flat)
    for unit in units(prims):
        if unit[0].op == "modify":
            p = unit[0]
            near = np.flatnonzero(np.all((flat >= p.lo) & (flat <= p.hi), axis=1))
            if len(near):
                out[near] = sdf_shapes.MODS[p.kind](out[near], flat[near], p.params)
            continue
        hits, ds, joins, muls = [], [], [], []
        for p in unit:
            if clip:
                near = np.flatnonzero(np.all((flat >= p.lo - p.reach - margin) &
                                             (flat <= p.hi + p.reach + margin), axis=1))
            else:
                near = np.arange(len(flat))
            if len(near):
                hits.append(near)
                ds.append(_sd(p, flat[near], und, near))
                joins.append(p.join)
                muls.append((lambda hh, s=p.sides: sdf_shapes.sides_mul(s, flat[hh])) if p.sides else None)
        if unit[-1].op == "intersect":
            d = np.full(len(flat), FAR)
            if hits:
                h, dh = _merge(hits, ds, (), unit[0].join)
                d[h] = dh
            out = combine(out, d, unit[-1])
            continue
        if not hits:
            continue
        fused = (unit[0].group or "").startswith("fuse:")
        h, d = _merge(hits, ds, (), joins if fused else unit[0].join, muls if fused else None)
        out[h] = combine(out[h], d, unit[-1])
    return out


def taubin(verts: np.ndarray, faces: np.ndarray, iterations: int = 6, lam: float = 0.5,
           mu: float = -0.53) -> np.ndarray:
    """Volume-preserving smoothing; removes voxel stair-stepping along sharp blend creases."""
    n = len(verts)
    i = np.concatenate([faces[:, 0], faces[:, 1], faces[:, 2], faces[:, 1], faces[:, 2], faces[:, 0]])
    j = np.concatenate([faces[:, 1], faces[:, 2], faces[:, 0], faces[:, 0], faces[:, 1], faces[:, 2]])
    A = sparse.csr_matrix((np.ones(len(i)), (i, j)), shape=(n, n))
    A.data[:] = 1.0
    deg = np.asarray(A.sum(axis=1)).ravel()
    W = sparse.diags(1.0 / np.maximum(deg, 1)) @ A
    v = verts.astype(np.float64)
    for _ in range(iterations):
        v = v + lam * (W @ v - v)
        v = v + mu * (W @ v - v)
    return v.astype(np.float32)


def mesh(grid: Grid, smooth: int = 6):
    f = grid.field
    if not np.isfinite(f).all():  # a bug upstream; one NaN here becomes thousands of NaN vertices after Taubin
        warnings.warn(f"{np.count_nonzero(~np.isfinite(f))} non-finite field values meshed as outside")
        f = np.where(np.isfinite(f), f, FAR)
    if f.min() >= 0:
        raise ValueError("field has no interior: the shape is empty")
    # Pad with outside values so the surface is always closed.
    f = np.pad(f, 1, constant_values=FAR)
    verts, faces, _, _ = measure.marching_cubes(f, 0.0, spacing=(grid.voxel,) * 3,
                                                gradient_direction="ascent")
    verts += grid.origin - grid.voxel
    faces = faces[:, ::-1].astype(np.int32)  # skimage winds these inward for our inside-negative field
    if smooth:
        verts = taubin(verts, faces, smooth)
    return verts.astype(np.float32), faces


def gradient(prims: list[Prim], pts: np.ndarray, h: float) -> np.ndarray:
    """Central-difference gradient of the exact field at (n, 3) points."""
    g = np.empty_like(pts)
    for k in range(3):
        e = np.zeros(3)
        e[k] = h
        g[:, k] = (field_at(prims, pts + e) - field_at(prims, pts - e)) / (2 * h)
    return g


_TETRA = np.array([[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]], float)


def value_gradient(prims: list[Prim], pts: np.ndarray, h: float):
    """Field value and gradient at (n, 3) points from 4 evaluations on a tetrahedron around each (central
    differences would take 7). Both are second-order accurate; the value is off by ~h^2/2 * curvature."""
    f = field_at(prims, pts[:, None, :] + h * _TETRA[None])  # (n, 4)
    return f.mean(1), (f @ _TETRA) / (4 * h)


def vertex_normals(verts: np.ndarray, faces: np.ndarray) -> np.ndarray:
    v = verts.astype(np.float64)
    fn = np.cross(v[faces[:, 1]] - v[faces[:, 0]], v[faces[:, 2]] - v[faces[:, 0]])
    vn = np.zeros_like(v)
    for k in range(3):
        np.add.at(vn, faces[:, k], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-20)


def project(prims: list[Prim], verts: np.ndarray, faces: np.ndarray, voxel: float, iterations: int = 3,
            reuse=None, keep: bool = False):
    """Newton-step mesh vertices onto the exact zero set, and return unit normals from the field gradient.

    Marching cubes (and smoothing) leave vertices up to a fraction of a voxel off the surface, and
    faceted normals show the grid wherever the surface bends within a voxel. Steps are capped at half
    a voxel so a vertex can't jump across a thin gap to another sheet. Where the mesh can't represent
    the surface at this resolution (gaps thinner than a voxel), projecting folds it; there the vertex
    stays put and keeps the mesh normal."""
    v0 = verts.astype(np.float64)
    v = v0.copy()
    h = voxel * 0.125
    g = np.zeros_like(v)
    todo = np.arange(len(v))  # vertices still moving; the rest keep the gradient from their last step
    if reuse is not None:  # (mask, positions, gradients) of vertices already projected in an earlier build
        mask, rv, rg = reuse
        v[mask], g[mask] = rv, rg
        todo = np.flatnonzero(~mask)
    for _ in range(iterations):
        if not len(todo):
            break
        f, g[todo] = value_gradient(prims, v[todo], h)
        step = (f / np.maximum((g[todo] ** 2).sum(1), 1e-12))[:, None] * g[todo]
        n = np.linalg.norm(step, axis=1, keepdims=True)
        v[todo] -= step * np.minimum(1.0, 0.5 * voxel / np.maximum(n, 1e-12))
        todo = todo[n[:, 0] > 1e-3 * voxel]
    if len(todo):
        g[todo] = value_gradient(prims, v[todo], h)[1]
    raw = (v.copy(), g.copy()) if keep else None  # what a later build can reuse (before the fix-up below)
    normals = g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12)
    # (a NaN compares False, so non-finite projections are caught explicitly and keep their mesh position)
    bad = ~((vertex_normals(v, faces) * normals).sum(1) >= 0.5) | ~np.isfinite(v).all(1)
    v[bad] = v0[bad]
    normals[bad] = vertex_normals(v, faces)[bad]
    if keep:
        return v.astype(np.float32), normals.astype(np.float32), raw
    return v.astype(np.float32), normals.astype(np.float32)


def silhouettes(grid: Grid) -> dict:
    """Orthographic silhouette masks as images (row 0 = top), with world extents.

    front: camera at -Y looking +Y, image right = +X
    side:  camera at +X looking -X, image right = +Y (creature faces left)
    top:   camera at +Z looking down, image right = +X, image up = +Y
    """
    inside = grid.field < 0
    o, v = grid.origin, grid.voxel
    n = np.array(inside.shape)
    ext = lambda d: (float(o[d]), float(o[d] + v * (n[d] - 1)))  # noqa: E731
    return {
        "front": {"mask": inside.any(axis=1).T[::-1], "u": ext(0), "v": ext(2)},
        "side": {"mask": inside.any(axis=0).T[::-1], "u": ext(1), "v": ext(2)},
        "top": {"mask": inside.any(axis=2).T[::-1], "u": ext(0), "v": ext(1)},
    }


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("sdf_shapes",)
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
