"""Unique mark maps for the face: stubble hairs and freckles drawn on the head's OWN surface, once per model, the way a
character texture artist paints them into a unique map instead of tiling a swatch (a tiled freckle swatch showed its
6 cm repeat; tiled stubble dots read as a grey block with no beard line, no growth direction and no density zones).

How: the skin part's field is meshed in a box round the head (`head_mesh`, cached); marks are scattered on that
mesh by area x a density field built from the face's landmarks (so they follow edits of the head); each mark is drawn
into one image laid as a sphere wrap round a centre inside the head (`images` "wrap": "sphere": u, v from the
direction alone, per pixel in the shader, so the map holds on any head shape). A mark's footprint is drawn through
the wrap's local Jacobian, so it keeps its true size and shape in millimetres wherever it lands on the map.

Stubble (`stubble_map`): hairs as short cut strokes (blunt, ~0.1 mm wide) leaving the skin at an angle and lying
along the beard's growth direction (down on cheeks / jaw / chin, down and out from the philtrum on the moustache,
toward the throat under the chin), density by zone (moustache and chin full, the mouth-corner connector and the
cheeks thinner, fading to the cheek line), the cheek line and neckline crisp when trimmed and feathered when grown
out, patchiness by a low noise, salt and pepper by a share of white hairs. Channels: r = dark hairs, g = white
hairs, b = the shadow of the dark hair under and at the skin (the roots' local count, blurred ~1.5 mm: no roots, no
shadow, so patches, grey hairs and beard lines all carry into it).

Freckles (`freckle_map`): ephelides as irregular macules (lobed outlines, soft edges of their own), lognormal sizes,
clustered (a low noise to a power), on what faces the sun (nose bridge and dorsum, the malar cheeks, forehead,
upper lip less, nothing under the chin); a share darker; a few moles (rounder, sharper, darker, some raised).
Channels: r = light freckles, g = dark freckles, b = moles.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np

VERSION = 10
MAX_PX = 8192

# stubble styles: length (m) of the exposed hair, the shadow's weight, edge (0 natural .. 1 crisply trimmed), density
# scale, patchiness, how far the cheeks fill (0 thin .. 1 as the chin); hair grows ~0.4 mm a day
STUBBLE_STYLES = {
    "clean": {"length": 0.00005, "shadow": 0.4, "trim": 0.0, "density": 1.0, "patchy": 0.1, "cheeks": 0.55},
    "five_oclock": {"length": 0.0004, "shadow": 0.6, "trim": 0.0, "density": 1.0, "patchy": 0.15, "cheeks": 0.55},
    "short": {"length": 0.0014, "shadow": 1.0, "trim": 0.0, "density": 1.0, "patchy": 0.1, "cheeks": 0.6},
    "designer": {"length": 0.004, "shadow": 1.0, "trim": 1.0, "density": 1.0, "patchy": 0.15, "cheeks": 0.7},
    "heavy": {"length": 0.008, "shadow": 1.0, "trim": 0.25, "density": 1.0, "patchy": 0.2, "cheeks": 0.8},
    "patchy": {"length": 0.002, "shadow": 0.5, "trim": 0.0, "density": 0.8, "patchy": 0.75, "cheeks": 0.3},
}
HAIRS_PER_M2 = 6.0e5   # ~60 / cm2 where the beard is full (moustache, chin)

_MESH: dict = {}


def _ramp(x, a, b):
    """0 at a, 1 at b (either order), smoothstep."""
    den = np.asarray(b, float) - a
    t = np.clip((np.asarray(x, float) - a) / np.where(np.abs(den) > 1e-15, den, 1e-15), 0, 1)
    return t * t * (3 - 2 * t)


def _unit(v):
    v = np.asarray(v, float)
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


# ---- the surface ---------------------------------------------------------------------------------------------------

def head_box(J: dict) -> tuple[np.ndarray, np.ndarray]:
    from .skin import interocular
    io = interocular(J)
    jx = abs(J["lm_jaw_0.L"][0])
    lo = np.array([-jx - 0.45 * io, J["lm_nose_tip"][1] - 0.15 * io, J["lm_chin"][2] - 1.7 * io])
    hi = np.array([jx + 0.45 * io, J["lm_jaw_0.L"][1] + 1.0 * io, J["lm_brow_mid.L"][2] + 1.4 * io])
    return lo, hi


def head_mesh(spec: dict, part: str, J: dict, voxel: float = 0.0015):
    """The skin part's surface in the head's box: (V, N, F), area-weighted vertex normals; cached by the field."""
    from . import images, sdf, store
    prims = images.prims_on(spec, [part])
    lo, hi = head_box(J)
    key = hashlib.sha1(json.dumps([sorted(sdf.fingerprint(p) for p in prims), np.round(lo, 5).tolist(),
                                   np.round(hi, 5).tolist(), voxel, VERSION]).encode()).hexdigest()[:16]
    if key in _MESH:
        return _MESH[key]
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
    if len(_MESH) > 4:
        _MESH.pop(next(iter(_MESH)))
    _MESH[key] = out
    return out


def head_curvature(spec: dict, part: str, J: dict, h: float = 0.01):
    """Per head-mesh vertex: the surface's mean curvature over ~h (the field's Laplacian / 2 by central differences
    h apart), in units of 1 / interocular (a ball one interocular round = 1): > 0 convex (the cheek's front, the
    nasolabial bulge, the chin), < 0 hollow (under the cheekbone, beside the nose). Cached with the mesh."""
    from . import images, sdf, store
    from .skin import interocular
    V, N, F = head_mesh(spec, part, J)
    prims = images.prims_on(spec, [part])
    key = hashlib.sha1(json.dumps([sorted(sdf.fingerprint(p) for p in prims), len(V), np.asarray(V[:20]).round(5).tolist(), h,
                                   VERSION]).encode()).hexdigest()[:16]
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
    ~px_m at the surface. Returns {"img": the image dict's placement keys, "fr": images.wrap_coords' frame, W, H}."""
    from .skin import interocular
    io = interocular(J)
    # (deep in the head, behind the mouth: a centre in the mouth itself mapped the tongue and teeth over the face)
    o = np.array([0.0, J["lm_jaw_1.L"][1] + 0.2 * io,
                  0.5 * (J["lm_mouth_corner.L"][2] + J["lm_nose_base"][2])])
    lat_c = np.radians(0.5 * (lat[0] + lat[1]))
    d = np.array([0.0, -np.cos(lat_c), np.sin(lat_c)])
    su, sv = np.radians(lon), np.radians(lat[1] - lat[0])
    r = 1.5 * io  # a typical radius from the centre to the face
    W = int(min(MAX_PX, np.ceil(su * r / px_m)))
    H = int(min(MAX_PX, np.ceil(sv * r / px_m)))
    k = np.array([0.0, 0.0, 1.0])
    e1 = np.array([0.0, -1.0, 0.0])
    fr = {"o": o, "k": k, "dir": e1, "right": np.cross(k, e1), "seam": np.pi, "dc": float(np.mod(-np.pi, 2 * np.pi)),
          "su": su, "sv": sv, "phic": float(lat_c), "wrap": "sphere", "r0": r, "flip": False}
    img = {"at": [round(float(x), 6) for x in o], "wrap": "sphere", "dir": [round(float(x), 6) for x in d],
           "span": [round(float(lon), 4), round(float(lat[1] - lat[0]), 4)], "depth": round(1.3 * io, 5), "facing": 0.0}
    return {"img": img, "fr": fr, "W": W, "H": H}


def pix(sp: dict, P: np.ndarray) -> np.ndarray:
    """Pixel coordinates (x right, y down; pixel centres at integers) of points."""
    from .images import wrap_coords
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


# ---- the beard -------------------------------------------------------------------------------------------------------

class _Poly:
    """A closed 2D outline: contains_points(q, radius) = inside, or within radius of it (radius > 0)."""

    def __init__(self, pts):
        self.a = np.asarray(pts, float)
        self.b = np.roll(self.a, -1, 0)

    def contains_points(self, q, radius=0.0):
        q = np.asarray(q, float)
        inside = np.zeros(len(q), bool)
        dmin = np.full(len(q), np.inf)
        for a, b in zip(self.a, self.b):
            cross = ((a[1] > q[:, 1]) != (b[1] > q[:, 1]))
            xi = a[0] + (q[:, 1] - a[1]) * (b[0] - a[0]) / ((b[1] - a[1]) if b[1] != a[1] else 1e-12)
            inside ^= cross & (q[:, 0] < xi)
            if radius > 0:
                ab = b - a
                t = np.clip(((q - a) @ ab) / max(ab @ ab, 1e-18), 0, 1)
                dmin = np.minimum(dmin, np.linalg.norm(q - (a + t[:, None] * ab), axis=1))
        return inside | (dmin < radius) if radius > 0 else inside


def _lips_path(J):
    from .skin import OUTLINES, OUTLINES_DENSE
    names = OUTLINES_DENSE["lips"] if "verm_u00" in J else OUTLINES["lips"]
    return _Poly([[J[n][0], J[n][2]] for n in names if n in J])


def beard_density(J: dict, o: dict, curv=None):
    """density(P, N) -> 0..1: where the beard grows and how thickly, from the face's landmarks (interocular units) and,
    given `curv` (a function P -> head_curvature at those points), the surface's own forms. o = the stubble's options
    (cheek_line, neckline, trim, cheeks, patchy, density, seed).

    Untrimmed growth has no edge: the density tapers over 2-3 cm into sparse single hairs (Joe, 2026-10-09: "the edges
    are too hard, and don't follow the face shapes the way that stubble does"), with a few stragglers past it; only
    `trim` makes a line. The upper boundary runs under the cheekbone (a curve from the sideburn, sagging to the
    nostril's level mid-cheek, up to the moustache's corner), the neckline follows the jaw's underside and fades down
    the neck, the cheek's rounded front and the nasolabial bulge are thinner (convex), the moustache, chin and jaw
    full, the lower lip's corners sparse beside a denser soul patch."""
    from .skin import interocular
    from .paint import noise
    io = interocular(J)
    L = lambda n: np.asarray(J[n], float)  # noqa: E731
    trim = float(o["trim"])
    soft = io * (0.015 + 0.3 * (1 - trim))        # the boundaries' half-width: ~2.2 cm across untrimmed, ~2 mm trimmed
    cl, nl = float(o["cheek_line"]), float(o["neckline"])
    nose_b, nos, mc = L("lm_nose_base"), L("lm_nostril.L"), L("lm_mouth_corner.L")
    j1 = L("lm_jaw_1.L")
    y_ax = j1[1] + 0.3 * io                       # a vertical axis inside the head: angle round it from the front

    def theta(q):
        return np.degrees(np.arctan2(q[:, 0], -(q[:, 1] - y_ax)))
    # the upper boundary as a height over that angle: sideburn front, mid-cheek under the zygoma, moustache corner
    S = j1 + io * np.array([-0.04, -0.28, 0.05 + cl])
    M = mc + io * np.array([0.3, -0.02, 0.45 + 0.6 * cl])
    Cm = 0.5 * (S + M)
    Cm[2] = nos[2] - 0.02 * io + 0.8 * cl * io      # (a straight S-M line cut across the cheekbone's front)
    tS, tM, tC = (float(theta(p[None])[0]) for p in (S, M, Cm))
    tC = 0.5 * (tS + tM)

    def z_top(t):
        t = np.clip(t, tM, tS)
        return (S[2] * (t - tM) * (t - tC) / ((tS - tM) * (tS - tC)) + M[2] * (t - tS) * (t - tC) / ((tM - tS) * (tM - tC)) +
                Cm[2] * (t - tS) * (t - tM) / ((tC - tS) * (tC - tM)))
    # the jaw's edge (its landmark chain, mirrored to the chin) as a height over |x|: the neckline hangs below it
    chain = [L(f"lm_jaw_{k}.L") for k in range(2, 8)] + [L("lm_chin")]
    jx = np.array([abs(p[0]) for p in chain])[::-1]
    jz = np.array([p[2] for p in chain])[::-1]
    lips = _lips_path(J)
    y_ear = j1[1]
    ztop_sb = L("lm_jaw_0.L")[2] - 0.05 * io
    cheeks, patchy, seed = float(o["cheeks"]), float(o["patchy"]), int(o.get("seed", 0))

    def region(q, P, grow):
        """1 inside the beard's area, its boundaries feathered by `soft` and moved out by `grow` (m)."""
        t = theta(q)
        lat = _ramp(q[:, 0], M[0] - 0.12 * io, M[0] + 0.02 * io)
        top_c = _ramp(q[:, 2] - grow, z_top(t) + soft, z_top(t) - soft)
        top_m = _ramp(q[:, 2] - grow, nos[2] + 0.02 * io + soft, nos[2] + 0.02 * io - soft)
        d = lat * top_c + (1 - lat) * top_m
        drop = np.interp(q[:, 0], jx, jz) - q[:, 2]           # how far below the jaw's edge
        d *= _ramp(drop - grow, (0.55 + nl) * io + soft, (0.55 + nl) * io - soft)
        d *= _ramp(q[:, 2] - grow, ztop_sb + 0.1 * io, ztop_sb - 0.1 * io)
        back = y_ear + io * (0.04 + 0.35 * _ramp(q[:, 2], L("lm_jaw_3.L")[2], L("lm_jaw_4.L")[2] - 0.2 * io))
        d *= _ramp(q[:, 1] - 0.5 * grow, back + 0.06 * io, back - 0.06 * io)
        return d

    def dens(P, Nrm):
        q = P.copy()
        q[:, 0] = np.abs(q[:, 0])
        d = region(q, P, 0.0)
        if trim < 0.5:   # stragglers: a few single hairs out past the fade
            d = np.maximum(d, 0.06 * (1 - 2 * trim) * region(q, P, 1.4 * soft))
        nose = _ramp(q[:, 2], nose_b[2] - 0.005 * io, nose_b[2] + 0.04 * io) * _ramp(q[:, 0], nos[0] + 0.2 * io, nos[0] + 0.06 * io)
        d *= 1 - nose
        front = q[:, 1] < mc[1] + 0.25 * io
        d[front & lips.contains_points(P[:, [0, 2]], radius=0.0004)] = 0
        # zones: the cheek (out beside the mouth, above the jaw) thinner; the neck a little thinner
        jaw = _ramp(q[:, 2], mc[2] - 0.1 * io, mc[2] + 0.35 * io)
        side = _ramp(q[:, 0], mc[0] + 0.05 * io, mc[0] + 0.35 * io)
        cheek = jaw * side
        w = 1 - (1 - cheeks) * cheek
        if curv is not None:   # rounded forms carry less: the cheek's front, the nasolabial bulge
            k = curv(P)
            w *= 1 - 0.45 * _ramp(k, 0.6, 1.8) * np.maximum(cheek, _ramp(q[:, 0], mc[0] - 0.05 * io, mc[0] + 0.1 * io) * jaw)
        # round the mouth: sparse at the lower lip's corners and the connector beside them, a denser soul patch
        g = lambda cx, cz, rx, rz: np.exp(-(((q[:, 0] - cx) / rx) ** 2 + ((q[:, 2] - cz) / rz) ** 2))  # noqa: E731
        w *= 1 - (0.3 + 0.4 * patchy) * g(mc[0] + 0.14 * io, mc[2] - 0.2 * io, 0.12 * io, 0.14 * io)
        w *= 1 - 0.35 * g(mc[0] - 0.05 * io, mc[2] - 0.22 * io, 0.1 * io, 0.1 * io)
        w = np.minimum(w * (1 + 0.15 * g(0.0, L("lm_lip_lower")[2] - 0.2 * io, 0.12 * io, 0.12 * io)), 1.0)
        w *= 1 - 0.2 * np.exp(-(q[:, 0] / (0.045 * io)) ** 2) * _ramp(q[:, 2], mc[2], mc[2] + 0.1 * io)   # the philtrum
        w *= 1 - 0.2 * _ramp(np.interp(q[:, 0], jx, jz) - q[:, 2], 0.15 * io, 0.6 * io)                  # the neck
        if patchy > 0:
            nz = noise(P, {"scale": 0.014, "octaves": 2, "seed": 300 + seed})
            w *= (1 - patchy) + patchy * _ramp(nz, 0.32 + 0.12 * patchy, 0.6)
        return np.clip(d * w * float(o["density"]), 0, 1)
    return dens


def beard_direction(J: dict, P: np.ndarray, Nrm: np.ndarray) -> np.ndarray:
    """The way hair grows (a world vector; projected on the skin later): down, out from the philtrum on the moustache,
    toward the throat under the chin."""
    from .skin import interocular
    io = interocular(J)
    mc = np.asarray(J["lm_mouth_corner.L"], float)
    nb = np.asarray(J["lm_nose_base"], float)
    g = np.tile(np.array([0.0, 0.35, -1.0]), (len(P), 1))
    must = _ramp(P[:, 2], mc[2] - 0.05 * io, mc[2] + 0.1 * io) * _ramp(np.abs(P[:, 0]), mc[0] + 0.5 * io, mc[0]) * \
        _ramp(P[:, 2], nb[2] + 0.05 * io, nb[2] - 0.05 * io)
    g[:, 0] += 0.9 * np.sign(P[:, 0]) * _ramp(np.abs(P[:, 0]), 0.0, 0.25 * io) * must
    g[:, 1] += 0.8 * np.clip(-Nrm[:, 2], 0, 1)    # under the chin: toward the throat
    # cheeks: a little forward, toward the chin
    g[:, 1] -= 0.3 * _ramp(np.abs(P[:, 0]), mc[0], mc[0] + 0.5 * io) * (1 - must)
    return g


def stubble_map(spec: dict, part: str, J: dict, o: dict) -> tuple[str, dict, dict]:
    """The stubble map's file, the image dict's placement keys, and stats. o: the resolved options (length m, density,
    grey, patchy, trim, cheeks, cheek_line, neckline, size, seed)."""
    from . import store
    from scipy.ndimage import gaussian_filter
    sp = sphere(J, (-80.0, 52.0), 230.0, 0.00006 if o["length"] < 0.003 else 0.00008)
    V, N, F = head_mesh(spec, part, J)
    key = hashlib.sha1(json.dumps([o, np.asarray(V[:50]).round(5).tolist(), len(V), sp["img"], VERSION],
                                  sort_keys=True, default=str).encode()).hexdigest()[:16]
    path = store.HOME / "_images" / f"mk_stubble_{key}.png"
    stats_f = path.with_suffix(".json")
    if path.exists() and stats_f.exists():
        return str(path), sp["img"], json.loads(stats_f.read_text())
    rng = np.random.default_rng(900 + int(o.get("seed", 0)))
    dens = beard_density(J, o, curvature_at(spec, part, J))
    P, Nrm, d = scatter(V, N, F, dens, HAIRS_PER_M2, rng)
    keep = outward(sp, P, Nrm, V)   # (no hairs on skin facing in: the mouth's inside, a lip's inner roll)
    P, Nrm, d = P[keep], Nrm[keep], d[keep]
    n = len(P)
    W, H = sp["W"], sp["H"]
    R = np.zeros((H, W), np.float32)
    G = np.zeros((H, W), np.float32)
    if n:
        g = beard_direction(J, P, Nrm)
        ang = rng.normal(0, np.radians(18), n)              # each hair its own way, a little
        t1, t2 = frames(Nrm, g)
        x0, A = jacobians(sp, P, t1, t2)
        # where the beard thins out (its fading edges, stragglers) the hairs are finer, shorter and lighter: terminal
        # beard hair gives way to vellus
        fine = np.clip(d / 0.6, 0, 1) ** 0.5
        Lh = float(o["length"]) * rng.lognormal(0, 0.22, n) * (0.55 + 0.45 * fine)  # grown since the shave, unevenly
        elev = np.radians(np.clip(42 - 3.2 * Lh * 1000, 14, 42))                 # longer hairs lie flatter
        proj = Lh * np.cos(elev)
        wid = 0.000105 * float(o["size"]) * rng.uniform(0.8, 1.2, n) * (0.5 + 0.5 * fine)
        curl = rng.normal(0, 1, n) * np.clip(Lh / 0.006, 0, 1.2) * 0.25          # bend (rad over the hair's length)
        ca, sa = np.cos(ang), np.sin(ang)
        pxm = _px_m(A)
        white = rng.random(n) < float(o["grey"])
        tone = np.where(white, rng.uniform(0.75, 1.0, n), rng.uniform(0.0, 0.15, n))  # 0 dark .. 1 white
        reach = proj + wid + 2 * pxm

        def shape(i, s, t):
            a = ca[i] * s + sa[i] * t           # along the hair
            b = -sa[i] * s + ca[i] * t          # across
            l = max(proj[i], 0.5 * wid[i])
            b = b - curl[i] * a * a / max(l, 1e-6) * 0.5
            aa = 0.5 * pxm[i]
            hw = 0.5 * wid[i]
            across = _ramp(np.abs(b), hw + aa, max(hw - aa, 0.0))
            ends = _ramp(a, -aa - 0.25 * wid[i], aa - 0.25 * wid[i] + 1e-9) * _ramp(a, l + aa, l - aa)
            cov = across * ends
            if proj[i] < wid[i]:            # a cut stub: a round dot
                r = np.hypot(s, t)
                cov = _ramp(r, hw + aa, max(hw - aa, 0.0))
            return cov * min(1.0, (wid[i] / max(pxm[i], 1e-9)) ** 0.5 + 0.35)  # sub-pixel hairs read fainter
        draw(R, x0, A, reach, shape, (1 - tone) * 0.95 * (0.35 + 0.65 * fine))
        draw(G, x0, A, reach, shape, tone * 0.95 * (0.35 + 0.65 * fine))
        # the shadow: the EXPECTED density of dark roots (hair in the skin), from a dense sample of the density field
        # (not the drawn roots' count: blurred enough to hide its Poisson noise, ~3 mm, it fell off 3 mm short of every
        # edge and left a pale band over the lip), each sample weighted by 1 / its pixel's area on the skin
        K = 12
        Pc, Nc, dc = scatter(V, N, F, dens, K * HAIRS_PER_M2, np.random.default_rng(950 + int(o.get("seed", 0))), keep_all=True)
        keep = outward(sp, Pc, Nc, V)
        Pc, Nc, dc = Pc[keep], Nc[keep], dc[keep]
        _, Ac = jacobians(sp, Pc, *frames(Nc, np.tile([1.0, 0, 0], (len(Pc), 1))))
        xi = np.round(pix(sp, Pc)).astype(int)
        area = np.abs(Ac[:, 0, 0] * Ac[:, 1, 1] - Ac[:, 0, 1] * Ac[:, 1, 0])
        Bd = np.zeros((H, W), np.float32)
        Ba = np.zeros((H, W), np.float32)
        np.add.at(Bd, (xi[:, 1], xi[:, 0]), (dc * (1 - float(o["grey"])) * area).astype(np.float32))
        np.add.at(Ba, (xi[:, 1], xi[:, 0]), area.astype(np.float32))
        pm = float(np.median(pxm))
        Bd, Ba = gaussian_filter(Bd, 0.0012 / pm), gaussian_filter(Ba, 0.0012 / pm)
        # the average density over the samples (two skins over one pixel, a lip's inner roll over its outer, count
        # once: a head whose mesh doubled there summed to a full shadow over its whole face), where there is skin
        avg = Bd / np.maximum(Ba, 1e-6)
        support = np.clip(Ba / (0.5 * K * HAIRS_PER_M2), 0, 1)
        Bs = np.clip(avg * support / 0.7, 0, 1) ** 1.2   # full at ~70% of a full dark beard; thin edges fade faster
    else:
        Bs = np.zeros((H, W), np.float32)
        pm = 0.0
    _save(path, np.dstack([R, G, Bs]))
    stats = {"hairs": int(n), "px_mm": round(pm * 1000, 4), "size": [W, H], "white": round(float(np.mean(white)) if n else 0.0, 3)}
    stats_f.write_text(json.dumps(stats))
    return str(path), sp["img"], stats


# ---- freckles --------------------------------------------------------------------------------------------------------

def freckle_density(J: dict, o: dict):
    """Where freckles gather: what faces the sun (above and in front) on the nose, the malar cheeks, the forehead,
    less on the upper lip and chin; clusters from a low noise."""
    from .skin import interocular
    from .paint import noise
    io = interocular(J)
    L = lambda n: np.asarray(J[n], float)  # noqa: E731
    sun = _unit(np.array([0.0, -0.55, 0.83]))
    nb, br, lid = L("lm_nose_bridge"), L("lm_nose_base"), L("lm_lid_lower.L")
    zones = o["zones"]
    seed = int(o.get("seed", 0))
    clump = float(o["clump"])

    def g(P, c, r):
        return np.exp(-(((P - c) / r) ** 2).sum(1))

    def dens(P, Nrm):
        q = P.copy()
        q[:, 0] = np.abs(q[:, 0])
        face = g(q, np.array([0.0, nb[1] + 0.4 * io, 0.5 * (nb[2] + br[2])]), np.array([1.25, 1.2, 1.25]) * io)
        w = zones["face"] * face
        w = np.maximum(w, zones["nose"] * g(q, np.array([0.0, nb[1] - 0.15 * io, 0.5 * (nb[2] + br[2]) + 0.05 * io]), np.array([0.28, 0.4, 0.5]) * io))
        w = np.maximum(w, zones["cheeks"] * g(q, lid + io * np.array([0.1, 0.05, -0.42]), np.array([0.45, 0.5, 0.33]) * io))
        w = np.maximum(w, zones["forehead"] * g(q, np.array([0.0, nb[1] + 0.2 * io, nb[2] + 0.75 * io]), np.array([0.9, 0.6, 0.45]) * io))
        w = np.maximum(w, zones["upper_lip"] * g(q, np.array([0.0, br[1] + 0.05 * io, br[2] - 0.2 * io]), np.array([0.4, 0.4, 0.15]) * io))
        w = np.maximum(w, zones["chin"] * g(q, L("lm_chin") + np.array([0.0, 0.0, 0.25 * io]), np.array([0.35, 0.35, 0.3]) * io))
        lit = _ramp(Nrm @ sun, 0.05, 0.6)
        nz = noise(P, {"scale": 0.018, "octaves": 2, "seed": 500 + seed})
        cl = (1 - clump) + clump * _ramp(nz, 0.3, 0.75) ** 1.5
        lips = _lips_path(J)
        inl = lips.contains_points(P[:, [0, 2]], radius=0.001) & (P[:, 1] < L("lm_mouth_corner.L")[1] + 0.25 * io)
        d = np.clip(w * lit * cl, 0, 1)
        d[inl] = 0
        # not on the lids' margins and eyes (the eye area keeps a few)
        eye = np.maximum(g(q, L("lm_lid_upper.L") + np.array([0, 0.03 * io, -0.02 * io]), np.array([0.28, 0.4, 0.13]) * io), 0)
        return d * (1 - 0.85 * eye)
    return dens


FRECKLE_ZONES = {"face": 0.35, "nose": 1.0, "cheeks": 1.0, "forehead": 0.55, "upper_lip": 0.35, "chin": 0.3}


def freckle_map(spec: dict, part: str, J: dict, o: dict) -> tuple[str, dict, dict]:
    """The freckle map's file, placement and stats. o: amount (density), size (median diameter m), clump, dark (share
    of darker ones), moles (count on the face), zones, seed."""
    from . import store
    sp = sphere(J, (-62.0, 72.0), 220.0, 0.00012)
    V, N, F = head_mesh(spec, part, J)
    key = hashlib.sha1(json.dumps([o, np.asarray(V[:50]).round(5).tolist(), len(V), sp["img"], VERSION],
                                  sort_keys=True, default=str).encode()).hexdigest()[:16]
    path = store.HOME / "_images" / f"mk_freckles_{key}.png"
    stats_f = path.with_suffix(".json")
    if path.exists() and stats_f.exists():
        return str(path), sp["img"], json.loads(stats_f.read_text())
    rng = np.random.default_rng(1300 + int(o.get("seed", 0)))
    W, H = sp["W"], sp["H"]
    R = np.zeros((H, W), np.float32)
    G = np.zeros((H, W), np.float32)
    B = np.zeros((H, W), np.float32)
    per_m2 = 1.2e5 * float(o["amount"])          # ~12 / cm2 where densest at amount 1 (densely freckled noses: 10-30)
    dens = freckle_density(J, o)
    P, Nrm, d = scatter(V, N, F, dens, per_m2, rng)
    keep = outward(sp, P, Nrm, V)
    P, Nrm, d = P[keep], Nrm[keep], d[keep]
    n = len(P)
    if n:
        t1, t2 = frames(Nrm, np.tile([1.0, 0, 0], (n, 1)))
        x0, A = jacobians(sp, P, t1, t2)
        pxm = _px_m(A)
        rad = 0.5 * float(o["size"]) * rng.lognormal(0, 0.35, n) * (0.75 + 0.4 * d)      # denser: bigger, darker
        rad = np.clip(rad, 0.00025, 0.0025)
        soft = rng.uniform(0.2, 0.65, n)
        lobes = rng.normal(0, 1, (n, 4)) * np.array([0.0, 0.16, 0.1, 0.07])
        ph = rng.uniform(0, 2 * np.pi, (n, 4))
        aspect = rng.uniform(0.75, 1.0, n)
        rot = rng.uniform(0, np.pi, n)
        inten = np.clip(rng.uniform(0.25, 0.7, n) * (0.75 + 0.45 * d), 0, 1)   # most are faint
        dark = rng.random(n) < float(o["dark"])

        def shape(i, s, t):
            c, sn = np.cos(rot[i]), np.sin(rot[i])
            a = c * s + sn * t
            b = (-sn * s + c * t) / aspect[i]
            r = np.hypot(a, b)
            th = np.arctan2(b, a)
            edge = rad[i] * (1 + sum(lobes[i, k] * np.cos((k + 1) * th + ph[i, k]) for k in range(1, 4)))
            aa = pxm[i]
            return _ramp(r, edge * (1 + 0.5 * soft[i]) + aa, edge * (1 - soft[i]))
        reach = rad * 1.9 + 2 * pxm
        inten = np.where(dark, rng.uniform(0.8, 1.0, n), inten)
        draw(R, x0, A, reach, shape, inten)                  # every freckle, its darkness in its value
        draw(G, x0, A, reach, shape, np.where(dark, 1.0, 0.0))  # the darker ones alone
    # moles: a few, anywhere on the face, rounder, sharper, darker
    nm = int(o["moles"])
    if nm:
        fd = freckle_density(J, {**o, "zones": {k: 1.0 for k in FRECKLE_ZONES}, "clump": 0.0})
        Pm, Nm, _ = scatter(V, N, F, lambda P_, N_: np.clip(fd(P_, N_) * 3, 0, 1), 4e4, np.random.default_rng(1700 + int(o.get("seed", 0))))
        if len(Pm):
            pick = np.random.default_rng(1800 + int(o.get("seed", 0))).choice(len(Pm), min(nm, len(Pm)), replace=False)
            Pm, Nm = Pm[pick], Nm[pick]
            t1, t2 = frames(Nm, np.tile([1.0, 0, 0], (len(Pm), 1)))
            x0, A = jacobians(sp, Pm, t1, t2)
            pxm = _px_m(A)
            radm = np.random.default_rng(1900).uniform(0.0007, 0.0018, len(Pm))

            def mshape(i, s, t):
                return _ramp(np.hypot(s, t), radm[i] + pxm[i], radm[i] * 0.75)
            draw(B, x0, A, radm + 2 * pxm, mshape, np.ones(len(Pm)))
    _save(path, np.dstack([R, G, B]))
    stats = {"freckles": int(n), "moles": nm, "size": [W, H]}
    stats_f.write_text(json.dumps(stats))
    return str(path), sp["img"], stats
