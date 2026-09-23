"""Evaluate compiled primitives onto a voxel grid and mesh the zero level set."""

from __future__ import annotations

import hashlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np
from scipy import sparse
from skimage import measure

from .spec import Prim

FAR = 1.0  # field value where no primitive reaches; only its sign matters there


def smin(a, b, k):
    """Smooth union, cubic: curvature stays continuous where a blend starts (the quadratic form is only
    C1, which leaves a faint edge in the highlights along every fillet boundary)."""
    if k <= 0:
        return np.minimum(a, b)
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * h * k * (1.0 / 6.0)


def sd_cone(p: np.ndarray, pr: dict) -> np.ndarray:
    """Round cone along a bone, with an optionally elliptical cross-section."""
    q = (p - pr["a"]) @ pr["frame"].T  # columns: width, axis, height
    fw, fh = pr["flat"]
    bw, bh = pr.get("bow", (0.0, 0.0))
    if bw or bh:  # a bowed log: the cross-section's centre follows a parabola, 0 at the ends, `bow` mid-way
        t = np.clip(q[..., 1] / pr["len"], 0.0, 1.0)
        sag = 4.0 * t * (1.0 - t)
        q = np.stack([q[..., 0] - bw * sag, q[..., 1], q[..., 2] - bh * sag], -1)
    x, y, z = q[..., 0] / fw, q[..., 1], q[..., 2] / fh
    r1, r2, h = pr["ra"], pr["rb"], pr["len"]
    b = np.clip((r1 - r2) / h, -0.999, 0.999)
    a = np.sqrt(1.0 - b * b)
    qx = np.sqrt(x * x + z * z)
    k = -b * qx + a * y
    d = np.where(k < 0.0, np.sqrt(qx * qx + y * y) - r1,
                 np.where(k > a * h, np.sqrt(qx * qx + (y - h) ** 2) - r2, a * qx + b * y - r1))
    if pr.get("cut"):  # flat ends at the joints (sawn logs, beams, dowels), edges rounded by `cut`
        rc = pr["cut"]
        side = np.where(k < 0.0, qx - r1, np.where(k > a * h, qx - r2, d))  # the flank, continued past the ends
        cap = np.abs(y - 0.5 * h) - 0.5 * h
        e0, e1 = side + rc, cap + rc
        d = np.hypot(np.maximum(e0, 0.0), np.maximum(e1, 0.0)) + np.minimum(np.maximum(e0, e1), 0.0) - rc
    return d * min(fw, fh, 1.0)


def sd_ellipsoid(p: np.ndarray, pr: dict) -> np.ndarray:
    q = (p - pr["c"]) @ pr["rot"]  # world -> local
    r = pr["size"]
    k0 = np.linalg.norm(q / r, axis=-1)
    k1 = np.maximum(np.linalg.norm(q / (r * r), axis=-1), 1e-9)
    return k0 * (k0 - 1.0) / k1


def sd_lids(p: np.ndarray, pr: dict) -> np.ndarray:
    """Both eyelids of one eye: a solid ball around the eyeball (front part only) with an almond opening.
    The opening is a lens between two arcs meeting at the eye corners, measured by direction from the eye
    centre, so its walls are radial and meet the eyeball at right angles (a thin wedge there would alias).
    Local frame as for ellipsoids: the eye faces local -y, local +z is up."""
    q = (p - pr["c"]) @ pr["rot"]
    r, rho = pr["r"], pr["round"]
    dist = np.linalg.norm(q, axis=-1)
    ball = dist - pr["ro"]
    back = q[..., 1] - 0.3 * r
    if pr["closed"]:
        lid = ball
    else:
        s = r / np.maximum(dist, 1e-9)            # project onto the eyeball's sphere
        x, z = q[..., 0] * s, q[..., 2] * s
        up = np.hypot(x, z - pr["cu"]) - pr["Ru"]  # inside the upper arc's circle = below the upper margin
        lo = np.hypot(x, z - pr["cl"]) - pr["Rl"]
        lens = np.maximum(up, lo) * np.minimum(dist, pr["ro"]) / r
        lid = np.maximum(ball + rho, -lens + rho) - rho
    return np.maximum(lid + rho, back + rho) - rho


def sd_box(p: np.ndarray, pr: dict) -> np.ndarray:
    """Box with half-extents `size` in its local frame (as for ellipsoids), edges rounded by `round`."""
    q = np.abs((p - pr["c"]) @ pr["rot"]) - (pr["size"] - pr["round"])
    out = np.linalg.norm(np.maximum(q, 0.0), axis=-1)
    return out + np.minimum(q.max(axis=-1), 0.0) - pr["round"]


PROFILES = {
    # cross-section of a stroke, x = distance from its path / width, 0..1 -> 1..0; and max |slope|
    "soft": (lambda x: (1 - x * x) ** 2, 1.54),       # a bell: melted-in clay
    "sharp": (lambda x: (1 - x) ** 2, 2.0),           # a cusp at the path: a crisp crease or ridge line
    "round": (lambda x: 1 - x * x, 2.0),              # a dome with a defined edge
    "flat": (lambda x: _smoothstep(np.clip((1 - x) / 0.35, 0, 1)), 4.3),  # a plateau: flat top, soft rim
}


def _smoothstep(s):
    return s * s * (3 - 2 * s)


def _path_closest(q: np.ndarray, P: np.ndarray):
    """For points q (m, 3), the closest point on polyline P (K, 3): segment index j, parameter t, point c."""
    if len(P) == 1:
        z = np.zeros(len(q), int)
        return z, np.zeros(len(q)), np.broadcast_to(P[0], q.shape)
    a, d = P[:-1], P[1:] - P[:-1]
    x = q[:, None, :] - a[None]
    t = np.clip((x * d).sum(-1) / np.maximum((d * d).sum(1), 1e-18), 0.0, 1.0)
    j = np.argmin(((x - t[..., None] * d) ** 2).sum(-1), axis=1)
    tj = t[np.arange(len(q)), j]
    return j, tj, a[j] + tj[:, None] * d[j]


def mod_displace(cur: np.ndarray, p: np.ndarray, pr: dict, chunk: int = 4096) -> np.ndarray:
    """A stroke: push the surface out (depth > 0, clay) or in (depth < 0, crease) along its normal.

    Like a sculpting brush, a stroke is a dense trail of dabs, summed: each sample i of the path adds
    depth_i * profile(distance across the surface / width_i), weighted by the arc length it stands for and
    normalised so a long straight stroke reaches `depth`. Distance is measured across the surface (each
    sample's normal component left out), so the bump follows curvature. A sum of smooth dabs is smooth
    everywhere (measuring from the nearest point of a polyline instead kinks the surface at every sample,
    which shows as stripes), and the trail tapers off naturally over about a width at each end.
    Each dab fades out past `reach` along its normal, so it doesn't print through to the far side of a limb."""
    P, N, W, D, ds = pr["pts"], pr["nrm"], pr["width"], pr["depth"], pr["ds"]
    prof = PROFILES[pr["profile"]][0]
    H = pr["reach"]
    gain = D * ds / (W * pr["norm"]) if len(P) > 1 else D  # a single point is one dab at full depth
    flat = p.reshape(-1, 3)
    c0 = cur.reshape(-1)
    out = c0.copy()
    # only dabs within reach matter: the K nearest samples (K covers a width's worth of path either side)
    K, R = pr["k"], pr["radius"]
    for s in range(0, len(flat), chunk):
        q = flat[s:s + chunk].astype(np.float64)
        dist, idx = pr["tree"].query(q, k=K, distance_upper_bound=R)
        idx = idx.reshape(len(q), K)
        ok = idx < len(P)
        if not ok.any():
            continue
        j = np.where(ok, idx, 0)
        r = q[:, None, :] - P[j]                                   # (m, K, 3)
        h = (r * N[j]).sum(-1)
        lat = np.sqrt(np.maximum((r * r).sum(-1) - h * h, 0.0)) / W[j]
        k = np.where(ok & (lat < 1.0), prof(np.minimum(lat, 1.0)), 0.0)
        k *= 1 - _smoothstep(np.clip((np.abs(h) - H) / H, 0, 1))
        out[s:s + chunk] = c0[s:s + chunk] - (k * gain[j]).sum(1)
    return out.reshape(cur.shape)


def mod_flatten(cur: np.ndarray, p: np.ndarray, pr: dict) -> np.ndarray:
    """Plane off whatever stands above a plane (through pts, a point or a segment, normal nrm), fully
    within `width` of pts and fading out over `soft` beyond; only material up to `height` above the plane
    is touched, so a hand hanging in front of a thigh isn't shaved. The plane meets the surface in a
    smooth edge of radius `blend`."""
    P, n = pr["pts"], pr["nrm"][0]
    q = p.reshape(-1, 3)
    _, _, c = _path_closest(q, P)
    r = q - c
    h = r @ n
    lat = np.linalg.norm(r - h[:, None] * n, axis=1)
    wgt = 1 - _smoothstep(np.clip((lat - pr["width"]) / pr["soft"], 0, 1))
    wgt *= 1 - _smoothstep(np.clip((h - pr["height"]) / pr["height"], 0, 1))
    c0 = cur.reshape(-1)
    hp = (q - P[0]) @ n
    shaved = -smin(-c0, -hp, pr["blend"])  # smooth max(cur, height above the plane)
    return (c0 + wgt * (shaved - c0)).reshape(cur.shape)


def sd_cylinder(p: np.ndarray, pr: dict) -> np.ndarray:
    """Cylinder along its local z: radii size[0], size[1] (elliptical if they differ: then a lower bound),
    half-height size[2], edges rounded by `round`."""
    q = (p - pr["c"]) @ pr["rot"]
    rx, ry, hz = pr["size"]
    rnd = pr["round"]
    r = min(rx, ry)
    radial = np.hypot(q[..., 0] * (r / rx), q[..., 1] * (r / ry)) - (r - rnd)
    axial = np.abs(q[..., 2]) - (hz - rnd)
    out = np.hypot(np.maximum(radial, 0.0), np.maximum(axial, 0.0))
    return out + np.minimum(np.maximum(radial, axial), 0.0) - rnd


def sd_csg(p: np.ndarray, pr: dict) -> np.ndarray:
    """An element with its own solid ops (spec._csg): optionally hollowed to a wall, then its targeted cuts."""
    d = SDF[pr["kind"]](p, pr["p"])
    if pr.get("lumpy"):  # knots, axe marks, an uneven stone: noise on the surface itself (amount << scale)
        from .noise import fbm
        amt, sc, seed, octv = pr["lumpy"]
        d = d + amt * (2.0 * fbm(p.reshape(-1, 3), sc, octv, seed).reshape(d.shape) - 1.0)
    if pr["hollow"]:
        d = np.maximum(d, -d - pr["hollow"])
    for op, kind, params, k in pr["cuts"]:
        c = SDF[kind](p, params)
        d = -smin(-d, c, k) if op == "subtract" else -smin(-d, -c, k)
    return d


def sd_shell(p: np.ndarray, pr: dict) -> np.ndarray:
    """Another part's surface pushed out by `offset` (clothing). Solid by default: the inside is hidden in
    the part below, and a thin sheet a voxel or two thick would alias. With `thickness`, only the layer from
    offset - thickness to offset. Its own region primitives are intersected with it afterwards."""
    fb = field_at(pr["prims"], p, margin=pr["offset"] + 0.01)
    out = fb - pr["offset"]
    return out if not pr["thickness"] else np.maximum(out, pr["offset"] - pr["thickness"] - fb)


SDF = {"cone": sd_cone, "ellipsoid": sd_ellipsoid, "lids": sd_lids, "box": sd_box, "cylinder": sd_cylinder,
       "csg": sd_csg, "shell": sd_shell}
MODS = {"displace": mod_displace, "flatten": mod_flatten}  # op "modify": reshape what's been combined so far


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


def _merge(hits: list[np.ndarray], ds: list[np.ndarray], tail: tuple, join: float):
    """Union of a group's primitives (smooth by `join`, usually small or 0), each given on its own indices."""
    if len(hits) == 1:
        return hits[0], ds[0]
    h = np.unique(np.concatenate(hits))
    d = np.full((len(h), *tail), FAR, dtype=ds[0].dtype)
    for hit, v in zip(hits, ds):
        k = np.searchsorted(h, hit)
        d[k] = smin(d[k], v, join)
    return h, d


def combine(cur: np.ndarray, d: np.ndarray, p: Prim) -> np.ndarray:
    if p.op == "add":
        return smin(cur, d, p.blend)
    if p.op == "intersect":  # keep only what's inside d (a clothing part's region)
        return -smin(-cur, -d, p.blend)
    return -smin(-cur, d, p.blend)


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


def fingerprint(p: Prim) -> str:
    """Content hash of a primitive: equal fingerprints give equal field contributions. A shell's base part
    is left out (the shell part inherits its base's changed regions instead)."""
    h = hashlib.sha1(repr((p.name, p.kind, p.op, p.blend, p.layer, p.group, p.join, p.part, p.lip)).encode())
    for k in sorted(p.params):
        v = p.params[k]
        if k in ("prims", "tree"):
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
            self.at_key = at_key
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
        self.fps = fps
        if redo.any():
            self._redo(prims, lo, voxel, np.argwhere(redo), half_diag)
        field = self.blocks.transpose(0, 3, 1, 4, 2, 5).reshape(nb * B)
        return np.ascontiguousarray(field[:shape[0], :shape[1], :shape[2]]), boxes

    def _redo(self, prims, lo, voxel, idx, half_diag):
        B = BLOCK
        b_lo = lo + voxel * B * idx
        centre = field_at(prims, b_lo + voxel * (B - 1) / 2, margin=2 * half_diag)
        # modifiers make the field steeper than 1 (by up to lip), so the surface can be further from a centre
        lip = max([p.lip for p in prims] + [1.0])
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


def _block_values(prims: list[Prim], a_lo, a_hi, local, voxel: float, half_diag: float) -> np.ndarray:
    """Field values in a set of blocks (their low corners a_lo), all of one part's primitives in order."""
    B = BLOCK
    vals = np.full((len(a_lo), B, B, B), FAR, np.float32)
    for unit in units(prims):
        if unit[0].op == "modify":
            p = unit[0]
            hit = np.flatnonzero(np.all((a_hi >= p.lo - voxel) & (a_lo <= p.hi + voxel), axis=1))
            if len(hit):
                vals[hit] = MODS[p.kind](vals[hit], a_lo[hit, None, None, None, :] + local, p.params)
            continue
        hits, ds = [], []
        for p in unit:
            margin = p.reach + voxel
            hit = np.flatnonzero(np.all((a_hi >= p.lo - margin) & (a_lo <= p.hi + margin), axis=1))
            # AABBs of slanted bones are loose: also drop blocks this primitive can't reach
            hit = hit[SDF[p.kind](a_lo[hit] + voxel * (B - 1) / 2, p.params) <= p.inert + 1.5 * half_diag]
            if len(hit):
                hits.append(hit)
                ds.append(SDF[p.kind](a_lo[hit, None, None, None, :] + local, p.params).astype(np.float32))
        if unit[-1].op == "intersect":  # outside every region primitive's reach is outside the region
            d = np.full((len(a_lo), B, B, B), FAR, np.float32)
            if hits:
                h, dh = _merge(hits, ds, (B, B, B), unit[0].join)
                d[h] = dh
            vals = combine(vals, d, unit[-1])
            continue
        if not hits:
            continue
        h, d = _merge(hits, ds, (B, B, B), unit[0].join)
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
    out = np.full(len(flat), FAR if clip else np.inf)
    for unit in units(prims):
        if unit[0].op == "modify":
            p = unit[0]
            near = np.flatnonzero(np.all((flat >= p.lo) & (flat <= p.hi), axis=1))
            if len(near):
                out[near] = MODS[p.kind](out[near], flat[near], p.params)
            continue
        hits, ds = [], []
        for p in unit:
            if clip:
                near = np.flatnonzero(np.all((flat >= p.lo - p.reach - margin) &
                                             (flat <= p.hi + p.reach + margin), axis=1))
            else:
                near = np.arange(len(flat))
            if len(near):
                hits.append(near)
                ds.append(SDF[p.kind](flat[near], p.params))
        if unit[-1].op == "intersect":
            d = np.full(len(flat), FAR)
            if hits:
                h, dh = _merge(hits, ds, (), unit[0].join)
                d[h] = dh
            out = combine(out, d, unit[-1])
            continue
        if not hits:
            continue
        h, d = _merge(hits, ds, (), unit[0].join)
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
    bad = (vertex_normals(v, faces) * normals).sum(1) < 0.5
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
