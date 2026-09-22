"""Evaluate compiled primitives onto a voxel grid and mesh the zero level set."""

from __future__ import annotations

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
    x, y, z = q[..., 0] / fw, q[..., 1], q[..., 2] / fh
    r1, r2, h = pr["ra"], pr["rb"], pr["len"]
    b = np.clip((r1 - r2) / h, -0.999, 0.999)
    a = np.sqrt(1.0 - b * b)
    qx = np.sqrt(x * x + z * z)
    k = -b * qx + a * y
    d = np.where(k < 0.0, np.sqrt(qx * qx + y * y) - r1,
                 np.where(k > a * h, np.sqrt(qx * qx + (y - h) ** 2) - r2, a * qx + b * y - r1))
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
    R = np.maximum(W, 2 * H)
    for s in range(0, len(flat), chunk):
        q = flat[s:s + chunk].astype(np.float64)
        lo, hi = q.min(0), q.max(0)
        near = np.flatnonzero(np.all((P > lo - R[:, None]) & (P < hi + R[:, None]), axis=1))
        if not len(near):
            continue
        r = q[:, None, :] - P[near][None]                        # (m, k, 3)
        h = (r * N[near][None]).sum(-1)
        lat = np.sqrt(np.maximum((r * r).sum(-1) - h * h, 0.0)) / W[near]
        k = np.where(lat < 1.0, prof(np.minimum(lat, 1.0)), 0.0)
        k *= 1 - _smoothstep(np.clip((np.abs(h) - H) / H, 0, 1))
        out[s:s + chunk] = c0[s:s + chunk] - k @ gain[near]
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


SDF = {"cone": sd_cone, "ellipsoid": sd_ellipsoid, "lids": sd_lids, "box": sd_box}
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
    return smin(cur, d, p.blend) if p.op == "add" else -smin(-cur, d, p.blend)


def evaluate(prims: list[Prim], resolution: int = 160, pad: float = 0.02, box=None) -> Grid:
    """Sample the field on a grid, exactly only in blocks the surface can pass through.

    The field is (close to) 1-Lipschitz, so a block whose centre value exceeds its half-diagonal holds
    no surface; those blocks just take the centre value, which is all marching cubes needs (the sign).
    box=(lo, hi) limits the grid to that region (for close-ups); the cut is capped where it crosses the body."""
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
    shape = np.ceil((hi - lo) / voxel).astype(int) + 1
    nb = -(-shape // BLOCK)

    B = BLOCK
    corner = lo + voxel * B * np.stack(np.meshgrid(*[np.arange(n) for n in nb], indexing="ij"), -1)
    half_diag = voxel * (B - 1) * np.sqrt(3) / 2
    centre_val = field_at(prims, corner + voxel * (B - 1) / 2, margin=2 * half_diag)
    blocks = np.broadcast_to(centre_val[..., None, None, None], (*nb, B, B, B)).astype(np.float32)

    # modifiers make the field steeper than 1 (by up to lip), so the surface can be further from a centre
    lip = max([p.lip for p in prims] + [1.0])
    active = np.argwhere(np.abs(centre_val) <= lip * 1.5 * half_diag + voxel)
    if len(active):
        a_lo = lo + voxel * B * active
        a_hi = a_lo + voxel * (B - 1)
        local = voxel * np.stack(np.meshgrid(*[np.arange(B)] * 3, indexing="ij"), -1)
        vals = np.full((len(active), B, B, B), FAR, np.float32)
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
            if not hits:
                continue
            h, d = _merge(hits, ds, (B, B, B), unit[0].join)
            vals[h] = combine(vals[h], d, unit[-1])
        blocks[tuple(active.T)] = vals

    field = blocks.transpose(0, 3, 1, 4, 2, 5).reshape(nb * B)
    field = np.ascontiguousarray(field[:shape[0], :shape[1], :shape[2]])
    return Grid(field, lo, voxel)


def field_at(prims: list[Prim], pts: np.ndarray, clip: bool = True, margin: float = 0.0) -> np.ndarray:
    """Exact combined field at arbitrary points (..., 3), combined in the same order as evaluate().
    clip=False evaluates every primitive everywhere, so far from the shape the value is a real distance
    rather than FAR (slower; the fitter needs it to pull toward parts the model is missing).
    margin widens the clipping, so values within `margin` of the surface are real distances too."""
    flat = pts.reshape(-1, 3)
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
        if not hits:
            continue
        h, d = _merge(hits, ds, (), unit[0].join)
        out[h] = combine(out[h], d, unit[-1])
    return out.reshape(pts.shape[:-1])


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


def vertex_normals(verts: np.ndarray, faces: np.ndarray) -> np.ndarray:
    v = verts.astype(np.float64)
    fn = np.cross(v[faces[:, 1]] - v[faces[:, 0]], v[faces[:, 2]] - v[faces[:, 0]])
    vn = np.zeros_like(v)
    for k in range(3):
        np.add.at(vn, faces[:, k], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-20)


def project(prims: list[Prim], verts: np.ndarray, faces: np.ndarray, voxel: float, iterations: int = 3):
    """Newton-step mesh vertices onto the exact zero set, and return unit normals from the field gradient.

    Marching cubes (and smoothing) leave vertices up to a fraction of a voxel off the surface, and
    faceted normals show the grid wherever the surface bends within a voxel. Steps are capped at half
    a voxel so a vertex can't jump across a thin gap to another sheet. Where the mesh can't represent
    the surface at this resolution (gaps thinner than a voxel), projecting folds it; there the vertex
    stays put and keeps the mesh normal."""
    v0 = verts.astype(np.float64)
    v = v0.copy()
    h = voxel * 0.25
    for _ in range(iterations):
        f = field_at(prims, v)
        g = gradient(prims, v, h)
        step = (f / np.maximum((g * g).sum(1), 1e-12))[:, None] * g
        n = np.linalg.norm(step, axis=1, keepdims=True)
        v -= step * np.minimum(1.0, 0.5 * voxel / np.maximum(n, 1e-12))
    g = gradient(prims, v, h)
    normals = g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12)
    bad = (vertex_normals(v, faces) * normals).sum(1) < 0.5
    v[bad] = v0[bad]
    normals[bad] = vertex_normals(v, faces)[bad]
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
