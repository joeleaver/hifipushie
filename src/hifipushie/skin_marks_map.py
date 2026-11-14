"""The surface marks are placed on (the head's mesh, curvature, scatter) and the map they are drawn into (sphere, pixels, frames, draw). Part of the skin's drawn marks (skin_marks.py has the overview)."""
from __future__ import annotations

import hashlib
import json

import numpy as np

from . import skin_marks
from .skin_marks import _unit

# ---- the surface ---------------------------------------------------------------------------------------------------
def head_box(J: dict) -> tuple[np.ndarray, np.ndarray]:
    from .skin_zones import interocular
    io = interocular(J)
    jx = abs(J["lm_jaw_0.L"][0])
    lo = np.array([-jx - 0.45 * io, J["lm_nose_tip"][1] - 0.15 * io, J["lm_chin"][2] - 1.7 * io])
    hi = np.array([jx + 0.45 * io, J["lm_jaw_0.L"][1] + 1.0 * io, J["lm_brow_mid.L"][2] + 1.4 * io])
    return lo, hi


def head_mesh(spec: dict, part: str, J: dict, voxel: float = 0.0015):
    """The skin part's surface in the head's box: (V, N, F), area-weighted vertex normals; cached by the field."""
    from . import sdf, store
    from . import images_frame
    prims = images_frame.prims_on(spec, [part])
    lo, hi = head_box(J)
    key = hashlib.sha1(json.dumps([sorted(sdf.fingerprint(p) for p in prims), np.round(lo, 5).tolist(),
                                   np.round(hi, 5).tolist(), voxel, skin_marks.VERSION]).encode()).hexdigest()[:16]
    if key in skin_marks._MESH:
        return skin_marks._MESH[key]
    f = store.HOME / "_images" / f"mk_mesh_{key}.npz"
    if f.exists():
        z = np.load(f)
        out = (z["V"], z["N"], z["F"])
    else:
        res = int(np.ceil((hi - lo).max() / voxel))
        grid = sdf.evaluate(prims, resolution=res, box=(lo, hi), pad=4 * voxel)
        V, F = sdf.mesh(grid, smooth=2)
        glo = grid.origin
        ghi = grid.origin + (np.array(grid.field.shape) - 1) * grid.voxel
        wall = ((V < glo + 1.01 * grid.voxel) | (V > ghi - 1.01 * grid.voxel)).any(1)
        F = F[~wall[F].any(1)]
        used = np.unique(F)
        remap = np.full(len(V), -1)
        remap[used] = np.arange(len(used))
        V, F = V[used].astype(np.float64), remap[F].astype(np.int64)
        fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
        N = np.zeros_like(V)
        for k in range(3):
            np.add.at(N, F[:, k], fn)
        N = _unit(N)
        f.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(f, V=V.astype(np.float32), N=N.astype(np.float32), F=F.astype(np.int32))
        out = (V.astype(np.float32), N.astype(np.float32), F.astype(np.int32))
    if len(skin_marks._MESH) > 4:
        skin_marks._MESH.pop(next(iter(skin_marks._MESH)))
    skin_marks._MESH[key] = out
    return out


def head_curvature(spec: dict, part: str, J: dict, h: float = 0.01):
    """Per head-mesh vertex: the surface's mean curvature over ~h (the field's Laplacian / 2 by central differences
    h apart), in units of 1 / interocular (a ball one interocular round = 1): > 0 convex (the cheek's front, the
    nasolabial bulge, the chin), < 0 hollow (under the cheekbone, beside the nose). Cached with the mesh."""
    from . import sdf, store
    from . import images_frame
    from .skin_zones import interocular
    V, N, F = head_mesh(spec, part, J)
    prims = images_frame.prims_on(spec, [part])
    key = hashlib.sha1(json.dumps([sorted(sdf.fingerprint(p) for p in prims), len(V), np.asarray(V[:20]).round(5).tolist(), h,
                                   skin_marks.VERSION]).encode()).hexdigest()[:16]
    f = store.HOME / "_images" / f"mk_curv_{key}.npy"
    if f.exists():
        return np.load(f)
    P = V.astype(np.float64)
    lap = -6.0 * sdf.field_at(prims, P)
    for ax in range(3):
        e = np.zeros(3)
        e[ax] = h
        lap = lap + sdf.field_at(prims, P + e) + sdf.field_at(prims, P - e)
    k = (0.5 * lap / (h * h) * interocular(J)).astype(np.float32)
    np.save(f, k)
    return k


def curvature_at(spec: dict, part: str, J: dict):
    """A function P -> head_curvature at the nearest head-mesh vertex."""
    from scipy.spatial import cKDTree
    V, _, _ = head_mesh(spec, part, J)
    k = head_curvature(spec, part, J)
    tree = cKDTree(np.asarray(V, float))
    return lambda P: k[tree.query(np.asarray(P, float), k=1)[1]].astype(float)


def scatter(V, N, F, density, per_m2: float, rng, chunk: int = 200000, keep_all: bool = False):
    """Points on the mesh at `per_m2` x density(points, normals) (0..1) per square metre: (P, Nrm, d)."""
    V, N, F = (np.asarray(a) for a in (V, N, F))
    dv = density(V.astype(np.float64), N.astype(np.float64))
    keep = dv[F].max(1) > 1e-4
    F = F[keep]
    if not len(F):
        return np.zeros((0, 3)), np.zeros((0, 3)), np.zeros(0)
    a, b, c = (V[F[:, k]].astype(np.float64) for k in range(3))
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    n = rng.poisson(area * per_m2)
    fi = np.repeat(np.arange(len(F)), n)
    r1, r2 = rng.random(len(fi)), rng.random(len(fi))
    s = np.sqrt(r1)
    w = np.stack([1 - s, s * (1 - r2), s * r2], 1)
    P = w[:, :1] * a[fi] + w[:, 1:2] * b[fi] + w[:, 2:] * c[fi]
    Nn = _unit(w[:, :1] * N[F[fi, 0]] + w[:, 1:2] * N[F[fi, 1]] + w[:, 2:] * N[F[fi, 2]])
    d = np.concatenate([density(P[i:i + chunk], Nn[i:i + chunk]) for i in range(0, len(P), chunk)]) if len(P) else np.zeros(0)
    if keep_all:
        return P, Nn, d
    m = rng.random(len(P)) < d
    return P[m], Nn[m], d[m]


# ---- the map --------------------------------------------------------------------------------------------------------
def sphere(J: dict, lat: tuple, lon: float, px_m: float) -> dict:
    """The wrap: centre inside the head at the mouth's height, latitude range `lat` (deg), `lon` deg round, pixels
    ~px_m at the surface. Returns {"img": the image dict's placement keys, "fr": images_project.wrap_coords' frame, W, H}."""
    from .skin_zones import interocular
    io = interocular(J)
    # (deep in the head, behind the mouth: a centre in the mouth itself mapped the tongue and teeth over the face)
    o = np.array([0.0, J["lm_jaw_1.L"][1] + 0.2 * io,
                  0.5 * (J["lm_mouth_corner.L"][2] + J["lm_nose_base"][2])])
    lat_c = np.radians(0.5 * (lat[0] + lat[1]))
    d = np.array([0.0, -np.cos(lat_c), np.sin(lat_c)])
    su, sv = np.radians(lon), np.radians(lat[1] - lat[0])
    r = 1.5 * io  # a typical radius from the centre to the face
    W = int(min(skin_marks.MAX_PX, np.ceil(su * r / px_m)))
    H = int(min(skin_marks.MAX_PX, np.ceil(sv * r / px_m)))
    k = np.array([0.0, 0.0, 1.0])
    e1 = np.array([0.0, -1.0, 0.0])
    fr = {"o": o, "k": k, "dir": e1, "right": np.cross(k, e1), "seam": np.pi, "dc": float(np.mod(-np.pi, 2 * np.pi)),
          "su": su, "sv": sv, "phic": float(lat_c), "wrap": "sphere", "r0": r, "flip": False}
    img = {"at": [round(float(x), 6) for x in o], "wrap": "sphere", "dir": [round(float(x), 6) for x in d],
           "span": [round(float(lon), 4), round(float(lat[1] - lat[0]), 4)], "depth": round(1.3 * io, 5), "facing": 0.0}
    return {"img": img, "fr": fr, "W": W, "H": H}


def pix(sp: dict, P: np.ndarray) -> np.ndarray:
    """Pixel coordinates (x right, y down; pixel centres at integers) of points."""
    from .images_project import wrap_coords
    u, v, _, _ = wrap_coords(sp["fr"], P)
    return np.stack([u * sp["W"] - 0.5, (1 - v) * sp["H"] - 0.5], 1)


def outward(sp: dict, P: np.ndarray, Nrm: np.ndarray, V=None, cell: int = 16, tol: float = 0.004) -> np.ndarray:
    """Points the wrap shows: skin facing out from the wrap's centre, inside the map, and (given the mesh's vertices V)
    the outermost skin along the ray from the centre: the nose's and mouth's insides lie along the same rays as the
    cheeks and lips, and their marks printed through as islands of shadow on the face."""
    o = np.asarray(sp["fr"]["o"], float)
    q = P - o
    R = np.linalg.norm(q, axis=1)
    f = (Nrm * q).sum(1) / np.maximum(R, 1e-9)
    x = pix(sp, P) if len(P) else np.zeros((0, 2))
    inside = np.isfinite(x).all(1) & (x[:, 0] >= 0) & (x[:, 1] >= 0) & (x[:, 0] <= sp["W"] - 1) & (x[:, 1] <= sp["H"] - 1)
    # (and not near the centre itself, which lies in the mouth: the tongue and teeth there map onto the whole picture
    # through a huge Jacobian, white discs of shadow all over the face)
    ok = (f > 0.05) & inside & (R > 0.3 * sp["fr"]["r0"])
    if V is not None and ok.any():
        V = np.asarray(V, float)
        xv = pix(sp, V)
        Rv = np.linalg.norm(V - o, axis=1)
        gw, gh = sp["W"] // cell + 1, sp["H"] // cell + 1
        iv = np.isfinite(xv).all(1) & (xv[:, 0] >= 0) & (xv[:, 1] >= 0) & (xv[:, 0] < sp["W"]) & (xv[:, 1] < sp["H"])
        top = np.zeros((gh, gw))
        cx, cy = (xv[iv] / cell).astype(int).T
        np.maximum.at(top, (cy, cx), Rv[iv])
        from scipy.ndimage import maximum_filter
        top = maximum_filter(top, 3)   # (a mesh vertex every ~1.5 mm: a cell may hold none)
        px_, py_ = (x[ok] / cell).astype(int).T
        t_ = top[py_, px_]
        ok[np.flatnonzero(ok)] = (t_ > 0) & (R[ok] > t_ - tol)
    return ok


def frames(Nrm: np.ndarray, along: np.ndarray):
    """Tangent frames: t1 = `along` projected onto the tangent plane, t2 = n x t1."""
    t1 = along - (along * Nrm).sum(1, keepdims=True) * Nrm
    bad = np.linalg.norm(t1, axis=1) < 1e-6
    t1[bad] = np.cross(Nrm[bad], [1.0, 0, 0])
    t1 = _unit(t1)
    return t1, np.cross(Nrm, t1)


def jacobians(sp, P, t1, t2, eps=2e-4):
    """d(pixel)/d(metres along t1, t2) per point: (n, 2, 2), columns t1, t2."""
    x0 = pix(sp, P)
    a = (pix(sp, P + eps * t1) - pix(sp, P - eps * t1)) / (2 * eps)
    b = (pix(sp, P + eps * t2) - pix(sp, P - eps * t2)) / (2 * eps)
    return x0, np.stack([a, b], 2)


def draw(img: np.ndarray, x0: np.ndarray, A: np.ndarray, reach: np.ndarray, shape, values: np.ndarray) -> None:
    """Draws marks into img (H, W) by "over" (1 - (1 - a)(1 - b)): mark i covers the pixels within reach[i] metres of
    its centre x0[i]; shape(i, s, t) gives its coverage 0..1 at tangent coordinates (s along t1, t along t2, m)."""
    H, W = img.shape
    for i in range(len(x0)):
        Ai = A[i]
        det = Ai[0, 0] * Ai[1, 1] - Ai[0, 1] * Ai[1, 0]
        if not np.isfinite(det) or abs(det) < 1e-9:
            continue
        ext = reach[i] * np.abs(Ai).sum(1)
        xa, xb = int(np.floor(x0[i, 0] - ext[0])), int(np.ceil(x0[i, 0] + ext[0]))
        ya, yb = int(np.floor(x0[i, 1] - ext[1])), int(np.ceil(x0[i, 1] + ext[1]))
        xa, ya, xb, yb = max(xa, 0), max(ya, 0), min(xb, W - 1), min(yb, H - 1)
        if xb < xa or yb < ya or (xb - xa) * (yb - ya) > 250000:
            continue
        gx, gy = np.meshgrid(np.arange(xa, xb + 1) - x0[i, 0], np.arange(ya, yb + 1) - x0[i, 1])
        inv = np.array([[Ai[1, 1], -Ai[0, 1]], [-Ai[1, 0], Ai[0, 0]]]) / det
        s = inv[0, 0] * gx + inv[0, 1] * gy
        t = inv[1, 0] * gx + inv[1, 1] * gy
        c = shape(i, s, t) * values[i]
        sub = img[ya:yb + 1, xa:xb + 1]
        sub[...] = 1 - (1 - sub) * (1 - np.clip(c, 0, 1))


def _px_m(A):
    """The size of a pixel in metres at each mark (the larger of its two axes)."""
    sv = np.linalg.svd(A, compute_uv=False)
    return 1.0 / np.maximum(sv[:, 1], 1e-9)


def _save(path, rgb: np.ndarray) -> None:
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    a = np.round(np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    a = np.dstack([a, np.full(a.shape[:2], 255, np.uint8)])  # opaque: the store bleeds colour under alpha 0
    tmp = path.with_suffix(".tmp.png")
    Image.fromarray(a, "RGBA").save(tmp)
    tmp.replace(path)
