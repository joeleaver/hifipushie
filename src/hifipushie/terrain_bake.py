"""Baked maps for terrain tiles: the detail comes from textures, not triangles.

Each cliff (or full-mode) tile mesh gets its own UV atlas per LOD (`unwrap`: charts by the axis a face faces, as a
triplanar projection would pick, split where they'd overlap, packed on 4-texel blocks), and every texel goes onto
the exact rock field plus `micro_relief` (fine facets, cracks and laminae below the meshing voxel, bake-only: meshed
they would zigzag) to bake:
- normal (tangent space, glTF/OpenGL convention: +Y = up the texture), against MikkTSpace-style tangents (written as
  TANGENT; Blender and most engines recompute Mikk and ignore it, so the bake must match Mikk);
- height (16-bit, the exact surface's offset along the low-poly normal, range per tile in the manifest);
- AO (from the field: how far open the rock is along the normal and round it, the same in every engine);
- base colour (the terrain's own macro colour at the exact point: cover, strata, rock tone, wet band);
- roughness (from the layer weights) packed with AO as ORM;
- layer weights (RGBA per group of 4 layers, the manifest's order) for engines that blend tiling layers.
Gutters: texels round each chart are baked from the surface beyond its edge (the chart's triangles extrapolated),
so filtering and mips at a seam read the real neighbour (across tile borders too), then dilated.
Ground tiles use their planar UV (the tile's square) and bake colour, normal and ORM the same way."""

from __future__ import annotations

import io
import math

import numpy as np
from scipy import ndimage

from . import noise
from . import terrain_mesh as tm


def _unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


# ---------------------------------------------------------------- fine rock (bake only)

def micro_relief(r, amount=1.0, texel=0.1):
    """A function p -> field offset: rock detail finer than the meshing voxel (facets 1.2 m and 0.45 m across, thin
    cracks along a coarser facet net's zero lines, the bedding plane's notch, laminae every sixth of a bed).
    Centimetres deep: for normal and height maps only. Band-limited to the map's texel: a feature narrower than
    ~4 texels fades out (sampled anyway it aliased, and two tiles' texels at a shared border read different
    normals)."""
    seed = r["seed"] + 77
    keep = lambda width: float(np.clip((width / texel - 3.0) / 3.0, 0.0, 1.0))  # 0 below 3 texels, 1 from 6
    a1, a2, ac = keep(1.2), keep(0.45), keep(0.3)
    an, al = keep(0.6), keep(0.24)
    bed = r.get("bed")

    J = r.get("joints")

    def f(p):
        out = 0.06 * a1 * tm._pl_facets(p, 1.2, seed)
        if a2 > 0:
            out = out + 0.015 * a2 * tm._pl_facets(p, 0.45, seed + 1)
        if J and ac > 0:  # hairline cracks along the joint sets, on their candidate planes (most not meshed)
            for m, d in enumerate(J["dirs"][:2]):
                sp = J["spacing"][m]
                q = (p[:, :2] @ np.asarray(d)) / sp + 0.37 * tm._pl_facets(p, 2.0, seed + 9 + m)
                dist = np.abs(q - np.round(q)) * sp
                out = out + 0.03 * ac * np.clip(1 - dist / 0.12, 0, 1) ** 2
        if ac > 0:
            c = tm._pl_facets(p, 3.1, seed + 2)
            out = out + 0.06 * ac * np.clip(1 - np.abs(c) / 0.1, 0, 1) ** 2  # cracks where the net crosses zero
        if bed and (an > 0 or al > 0):
            zb = tm.bed_level(p, r)
            e = np.abs(zb - np.round(zb)) * bed  # m from the nearest bedding plane
            # the bedding plane's notch: a smooth trough (a cusp stair-stepped when a close view magnified its texels)
            u = np.clip(1 - e / 0.35, 0, 1)
            # (broken along its length: an unbroken dark line on every bed read as a seam)
            brk = np.clip((noise.fbm(p * np.array([1.0, 1.0, 0.2]), 6.0, 2, seed=seed + 5) - 0.35) * 3, 0, 1)
            out = out + 0.14 * an * u * u * (3 - 2 * u) * brk
            if al > 0:
                z = zb * 6.0
                fr = z - np.floor(z)
                out = out + 0.025 * al * np.clip(1 - np.minimum(fr, 1 - fr) * bed / 6.0 / 0.12, 0, 1)
        return amount * out
    return f


# ---------------------------------------------------------------- unwrap

_DIRS = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]], float)
# (u, v) axes per direction, u x v = the direction (faces keep their winding in uv)
_UV = {0: ([0, 1, 0], [0, 0, 1]), 1: ([0, -1, 0], [0, 0, 1]), 2: ([-1, 0, 0], [0, 0, 1]), 3: ([1, 0, 0], [0, 0, 1]),
       4: ([1, 0, 0], [0, 1, 0]), 5: ([1, 0, 0], [0, -1, 0])}


def _adjacency(P, F):
    """Face pairs sharing an edge (vertices welded by position)."""
    _, wid = np.unique(np.round(P, 6), axis=0, return_inverse=True)
    wid = wid.ravel()
    W = wid[F]
    e = np.concatenate([W[:, [0, 1]], W[:, [1, 2]], W[:, [2, 0]]])
    f = np.tile(np.arange(len(F)), 3)
    key = np.minimum(e[:, 0], e[:, 1]) * (wid.max() + 1) + np.maximum(e[:, 0], e[:, 1])
    o = np.argsort(key, kind="stable")
    same = key[o][1:] == key[o][:-1]
    return f[o][:-1][same], f[o][1:][same]


def _components(n, a, b):
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    g = coo_matrix((np.ones(len(a)), (a, b)), shape=(n, n))
    return connected_components(g, directed=False)[1]


def _raster(tris, W, H):
    """Triangle id per texel (-1 none) for texel-space triangles (m, 3, 2): x right, y down."""
    from PIL import Image, ImageDraw
    img = Image.new("I", (W, H), -1)
    d = ImageDraw.Draw(img)
    for t, q in enumerate(tris):
        d.polygon([(float(x), float(y)) for x, y in q], fill=int(t))
    return np.asarray(img, np.int64)


def unwrap(P, F, density, max_size, margin=3):
    """Charts and a packed atlas for one mesh. Returns (corner uv (m, 3, 2) in 0..1, glTF convention: v down),
    the atlas size, the density used (texels/m) and the chart id per face."""
    fn = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    area = np.linalg.norm(fn, axis=1) / 2
    fn = _unit(fn)
    score = fn @ _DIRS.T
    lab = np.argmax(score, 1)
    a, b = _adjacency(P, F)
    for _ in range(3):  # fewer ragged charts: a face joins the label most of its neighbours have, if it faces it
        cnt = np.zeros((len(F), 6))
        np.add.at(cnt, (a, lab[b]), 1)
        np.add.at(cnt, (b, lab[a]), 1)
        best = np.argmax(cnt, 1)
        ok = (cnt[np.arange(len(F)), best] >= 2) & (score[np.arange(len(F)), best] > 0.35)
        lab = np.where(ok, best, lab)
    same = lab[a] == lab[b]
    comp = _components(len(F), a[same], b[same])
    # 2D coordinates per corner (metres) in each chart's own projection
    U = np.array([_UV[k][0] for k in range(6)], float)
    V = np.array([_UV[k][1] for k in range(6)], float)
    C = P[F]  # (m, 3, 3)
    uv = np.stack([(C * U[lab][:, None, :]).sum(2), (C * V[lab][:, None, :]).sum(2)], -1)
    charts = []
    for cid in range(comp.max() + 1):
        fs = np.flatnonzero(comp == cid)
        charts += _split(fs, uv, P, F)
    # a chart longer than about half the atlas it needs is cut in two (a 64 m cliff in one piece forced an atlas
    # twice the size, 10-20% filled)
    side = math.sqrt(max(area.sum(), 1e-6) * density ** 2 / 0.6)
    lim = max(64.0, 0.5 * min(2 ** math.ceil(math.log2(max(side, 1.0))), max_size)) / density
    out, todo = [], list(charts)
    while todo:
        fs = todo.pop()
        q = uv[fs].reshape(-1, 2)
        if len(fs) > 1 and float(np.max(np.ptp(q, 0))) > lim:
            c = P[F[fs]].mean(1)
            ax = int(np.argmax(np.ptp(c, 0)))
            m = np.median(c[:, ax])
            a_, b_ = fs[c[:, ax] <= m], fs[c[:, ax] > m]
            if len(a_) and len(b_):
                todo += [a_, b_]
                continue
        out.append(fs)
    return _pack(out, uv, area, density, max_size, margin)


def _split(fs, uv, P, F, depth=0):
    """A chart as face lists that don't overlap in their projection (split in two along its longest 3D axis while
    the triangles' summed area exceeds their union's)."""
    q = uv[fs].reshape(-1, 2)
    lo, hi = q.min(0), q.max(0)
    ext = float(max(hi - lo))
    if len(fs) < 3 or depth > 8 or ext <= 0:
        return [fs]
    s = 256.0 / ext
    t = (uv[fs] - lo) * s
    e1, e2 = t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]
    A = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]).sum() / 2
    ids = _raster(t, int(math.ceil((hi - lo)[0] * s)) + 2, int(math.ceil((hi - lo)[1] * s)) + 2)
    union = float((ids >= 0).sum())
    if union >= 0.93 * A - 2 * len(fs):  # (edge texels: thin triangles cover less than their area)
        return [fs]
    c = P[F[fs]].mean(1)
    ax = int(np.argmax(np.ptp(c, 0)))
    m = np.median(c[:, ax])
    left, right = fs[c[:, ax] <= m], fs[c[:, ax] > m]
    if not len(left) or not len(right):
        return [fs]
    return _split(left, uv, P, F, depth + 1) + _split(right, uv, P, F, depth + 1)


def _pack(charts, uv, area, density, max_size, margin):
    """Shelf packing of the charts' boxes (each turned to its smallest box) into a power-of-two square atlas."""
    boxes = []
    for fs in charts:
        q = uv[fs].reshape(-1, 2)
        c = q.mean(0)
        # the chart's principal axes: its smallest box
        cov = np.cov((q - c).T) if len(q) > 2 else np.eye(2)
        w, E = np.linalg.eigh(cov)
        R = E[:, ::-1]
        if np.linalg.det(R) < 0:
            R[:, 1] *= -1  # (a rotation, not a mirror: faces keep their winding)
        r = (q - c) @ R
        boxes.append((fs, c, R, r.min(0), r.max(0)))
    d = float(density)
    grow = 1.0
    B = 4  # packing on 4-texel blocks
    for _ in range(40):
        masks = [_chart_mask(uv[fs], c, R, lo, hi, d, margin, B) for fs, c, R, lo, hi in boxes]
        need = sum(float(m.sum()) for m in masks) * B * B * grow
        size = 2 ** max(6, int(math.ceil(math.log2(math.sqrt(need)))))
        if size > max_size:  # the density the cap allows
            d *= min(0.97, math.sqrt(max_size ** 2 / need))
            continue
        place = _raster_pack(masks, size // B)
        if place is not None:
            place = [(x * B, y * B) for x, y in place]
            break
        if size == max_size:
            d *= 0.93
        else:
            grow *= 1.3
    else:
        raise RuntimeError("uv packing failed")
    # as tall as the charts reach (to 128 texels): a half-empty square atlas wasted half its texels
    used = max(y + m.shape[0] * B for (x, y), m in zip(place, masks))
    H = min(size, max(64, 128 * int(math.ceil(used / 128))))
    out = np.zeros(uv.shape)
    cid = np.zeros(len(uv), np.int64)
    for k, ((fs, c, R, lo, hi), (x, y)) in enumerate(zip(boxes, place)):
        r = ((uv[fs] - c) @ R - lo) * d + margin + np.array([x, y])
        out[fs] = r / np.array([size, H])
        cid[fs] = k
    # our v runs up the chart (up the image); glTF's v runs down the image
    out[..., 1] = 1.0 - out[..., 1]
    return out, (size, H), d, cid


def _chart_mask(uvf, c, R, lo, hi, d, margin, B):
    """A chart's footprint on B-texel blocks (x, y = u, v), grown by `margin` texels for its gutter."""
    t = ((uvf - c) @ R - lo) * d + margin
    w, h = int(math.ceil((hi - lo)[0] * d + 2 * margin)), int(math.ceil((hi - lo)[1] * d + 2 * margin))
    ids = _raster(t, max(w, 1), max(h, 1)) >= 0
    ids |= ndimage.binary_dilation(ids, iterations=margin)
    nb = (-(-h // B), -(-w // B))
    m = np.zeros((nb[0] * B, nb[1] * B), bool)
    m[:h, :w] = ids
    m = m.reshape(nb[0], B, nb[1], B).any((1, 3))
    return m


def _raster_pack(masks, n):
    """Bottom-left placement of block masks (rows = v) on an n x n grid, largest first: the first free spot found by
    correlating each mask with what's taken. Returns [(x, y)] or None if they don't fit."""
    from scipy.signal import fftconvolve
    occ = np.zeros((n, n), np.float32)
    order = sorted(range(len(masks)), key=lambda k: -masks[k].sum())
    place = [None] * len(masks)
    for k in order:
        m = masks[k]
        h, w = m.shape
        if h > n or w > n:
            return None
        if occ.any():
            ov = fftconvolve(occ, m[::-1, ::-1].astype(np.float32), mode="valid")
            free = np.argwhere(ov < 0.5)
        else:
            free = np.array([[0, 0]])
        if not len(free):
            return None
        y, x = free[np.lexsort((free[:, 1], free[:, 0]))[0]]
        occ[y:y + h, x:x + w] += m
        place[k] = (int(x), int(y))
    return place


def split_corners(P, N, F, uvc, extra=None):
    """New vertices per (vertex, uv) pair: glTF wants one uv per vertex. extra: per-vertex arrays carried along."""
    key = np.c_[F.reshape(-1), np.round(uvc.reshape(-1, 2) * 2 ** 22).astype(np.int64)]
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.ravel()
    src = F.reshape(-1)[first]
    out = {"P": P[src], "N": N[src], "uv": uvc.reshape(-1, 2)[first], "F": inv.reshape(-1, 3), "src": src}
    for k, v in (extra or {}).items():
        out[k] = v[src]
    return out


def tangents(P, N, uv, F):
    """Per-vertex TANGENT (xyz, w) for glTF: xyz along +u, bitangent = cross(N, T) * w along -v (up the image)."""
    p0, p1, p2 = P[F[:, 0]], P[F[:, 1]], P[F[:, 2]]
    t0, t1, t2 = uv[F[:, 0]], uv[F[:, 1]], uv[F[:, 2]]
    e1, e2 = p1 - p0, p2 - p0
    d1, d2 = t1 - t0, t2 - t0
    det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    det = np.where(np.abs(det) < 1e-20, 1e-20, det)
    Tf = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) / det[:, None]   # dP/du
    Bf = -(e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) / det[:, None]  # -dP/dv
    # as MikkTSpace does it (Blender, Unity and Unreal recompute tangents that way and ignore ours): per corner the
    # face's tangent projected off the vertex normal and normalised, weighted by the corner's angle. Baking against
    # any other frame decodes wrong in those engines (lines along chart and tile borders, where frames differ most)
    Tv, Bv = np.zeros_like(P), np.zeros_like(P)
    C = P[F]
    for c in range(3):
        a_, b_ = C[:, (c + 1) % 3] - C[:, c], C[:, (c + 2) % 3] - C[:, c]
        ang = np.arccos(np.clip((_unit(a_) * _unit(b_)).sum(1), -1, 1))
        n = N[F[:, c]]
        tc = _unit(Tf - n * (Tf * n).sum(1, keepdims=True))
        np.add.at(Tv, F[:, c], tc * ang[:, None])
        np.add.at(Bv, F[:, c], _unit(Bf) * ang[:, None])
    T = _unit(Tv - N * (Tv * N).sum(1, keepdims=True))
    bad = np.linalg.norm(T, axis=1) < 0.5
    if bad.any():  # (a degenerate corner: any direction across the normal)
        alt = _unit(np.cross(N[bad], np.where(np.abs(N[bad, 2:3]) < 0.9, [[0, 0, 1.0]], [[1.0, 0, 0]])))
        T[bad] = alt
    w = np.where((np.cross(N, T) * Bv).sum(1) < 0, -1.0, 1.0)
    return np.c_[T, w]


# ---------------------------------------------------------------- baking

def _surface(field, X, N0, v, reach):
    """Newton steps from X onto the field's surface (each capped at half a voxel; a texel that strays further than
    `reach` from where it started keeps its low-poly point), then the field's normal there."""
    X0 = X.copy()
    X = X.copy()
    h = max(0.01, v / 16)
    todo = np.arange(len(X))
    f = np.full(len(X), np.inf)
    g = np.zeros_like(X)
    for it in range(7):
        if not len(todo):
            break
        ft, gt = field.value_gradient(X[todo], h)
        f[todo], g[todo] = ft, gt
        if it == 6:
            break
        st = (ft / np.maximum((gt * gt).sum(1), 1e-12))[:, None] * gt
        n = np.linalg.norm(st, axis=1, keepdims=True)
        st *= np.minimum(1.0, 0.5 * v / np.maximum(n, 1e-12))
        # a step under 2 mm is the last: the gradient just taken is the normal there (a separate normal pass
        # was a sixth of the bake)
        last = n[:, 0] <= 2e-3
        X[todo[~last]] -= st[~last]
        todo = todo[~last]
    moved = np.linalg.norm(X - X0, axis=1)
    G = _unit(g)
    # (strayed, turned away, or never reached the surface: steps capped at half a voxel ran out)
    bad = (moved > reach) | ((G * N0).sum(1) < -0.2) | ~np.isfinite(G).all(1) | (np.abs(f) > 0.05 + 0.1 * v)
    X[bad], G[bad] = X0[bad], N0[bad]
    return X, G, bad


def _grain(X):
    """0..1 value noise over ~1 m (roughness variation)."""
    from . import noise
    return noise.fbm(X, 1.3, 3, seed=91)


def ambient(field, X, G):
    """Occlusion from the field (0 closed .. 1 open): how much rock stands within 0.3-6.4 m of each point along its
    normal and four directions tipped 50 deg from it (a crevice, a cave's back, the foot of a wall read dark)."""
    T = _unit(np.cross(G, np.where(np.abs(G[:, 2:3]) < 0.9, [[0, 0, 1.0]], [[1.0, 0, 0]])))
    B = np.cross(G, T)
    dirs = [G] + [_unit(G * math.cos(0.87) + math.sin(0.87) * (math.cos(a) * T + math.sin(a) * B))
                  for a in (0.3, 1.87, 3.44, 5.01)]
    occ = np.zeros(len(X))
    wsum = 0.0
    for dvec in dirs:
        for i, d in enumerate((0.3, 0.8, 1.6, 3.2, 6.4)):
            w = 0.5 ** i
            f = field.value(X + dvec * d)
            occ += w * np.clip((d - f) / d, 0, 1)
            wsum += w
    return np.clip(1.0 - 1.6 * occ / wsum, 0.0, 1.0)


CHUNK = 200_000  # texels per field call: whole atlases at once (2.6M texels x 4-point stencils x fbm temporaries)
# made each bake worker 2+ GB


def _chunked(fn, *arrays):
    """fn over the rows of `arrays` in CHUNK-sized pieces, outputs concatenated (a tuple or a single array)."""
    n = len(arrays[0])
    if n <= CHUNK:
        return fn(*arrays)
    parts = [fn(*(a[i:i + CHUNK] for a in arrays)) for i in range(0, n, CHUNK)]
    if isinstance(parts[0], tuple):
        return tuple(np.concatenate([p[j] for p in parts]) for j in range(len(parts[0])))
    return np.concatenate(parts)


def bake(surface, ao_field, mats, P, N, T4, uv, F, size, layers_rough, field=None):
    """Every map of one mesh's atlas (size = (width, height)): {"normal": uint8 (h, w, 3), "orm", "basecolor",
    "weights": [RGBA...], "height": uint16}, plus the height range and how many texels fell back to the low poly."""
    Wd, Hd = (size, size) if np.isscalar(size) else size
    tris = uv[F] * np.array([Wd, Hd], float)  # texel space, x right, y down
    ids = _raster(tris, Wd, Hd)
    covered = ids >= 0
    # gutters: texels within a few of a chart take its nearest covered texel's triangle, extrapolated
    dist, (iy, ix) = ndimage.distance_transform_edt(~covered, return_indices=True)
    gut = (~covered) & (dist <= 3.5)
    ys, xs = np.nonzero(covered | gut)
    t = np.where(covered[ys, xs], ids[ys, xs], ids[iy[ys, xs], ix[ys, xs]])
    q = np.stack([xs + 0.5, ys + 0.5], -1)
    a_, b_, c_ = tris[t, 0], tris[t, 1], tris[t, 2]
    v0, v1, v2 = b_ - a_, c_ - a_, q - a_
    den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
    den = np.where(np.abs(den) < 1e-12, 1e-12, den)
    w1 = (v2[:, 0] * v1[:, 1] - v1[:, 0] * v2[:, 1]) / den
    w2 = (v0[:, 0] * v2[:, 1] - v2[:, 0] * v0[:, 1]) / den
    bary = np.stack([1 - w1 - w2, w1, w2], -1)
    bary = np.clip(bary, -1.0, 2.0)  # (gutters extrapolate a little past the edge; never far)
    corner = lambda A: np.einsum("nk,nkc->nc", bary, A[F[t]])
    Pl = corner(P)
    Nl = _unit(corner(N))
    Tl = corner(T4[:, :3])
    Tl = _unit(Tl - Nl * (Tl * Nl).sum(1, keepdims=True))
    Bl = np.cross(Nl, Tl) * np.sign(T4[F[t, 0], 3])[:, None]
    X, G, bad = _chunked(surface, Pl, Nl)
    height = ((X - Pl) * Nl).sum(1)
    tn = np.stack([(G * Tl).sum(1), (G * Bl).sum(1), (G * Nl).sum(1)], -1)
    tn[:, 2] = np.maximum(tn[:, 2], 0.02)
    tn = _unit(tn)
    # layer weights and colour from the normal over ~half a metre (the fine relief's own normal flipped rock/grass
    # texel by texel, and two tiles sampling a border a texel apart disagreed). Every value is taken per texel from
    # its own world point, or interpolated from its own triangle's vertices: never filtered across the atlas image,
    # where neighbouring texels belong to unrelated charts (a sparse grid + blur there bled one chart into the next
    # and drew lines along every tile border)
    Gs = G
    if field is not None:
        Gs = _unit(_chunked(lambda q: field.value_gradient(q, 0.4)[1], X))
        Gs = np.where(bad[:, None], G, Gs)
    Wt, col = _chunked(mats.weights, X, Gs)
    # roughness varies over a metre or so (one value per layer read as plastic, the wet band most of all)
    rgh = np.clip((Wt @ layers_rough) * (0.85 + 0.35 * _grain(X)), 0.05, 1.0)
    # AO at the mesh's vertices (identical on both sides of a tile border), interpolated over each triangle: it's
    # broad over metres
    if ao_field is not None:
        ao_v = _chunked(lambda a, b: ambient(ao_field, a, b), P, _unit(N))
        ao = np.clip(np.einsum("nk,nk->n", np.clip(bary, 0, 1) / np.clip(bary, 0, 1).sum(1, keepdims=True),
                               ao_v[F[t]]), 0, 1)
    else:
        ao = np.ones(len(X))
    filled = np.zeros((Hd, Wd), bool)
    filled[ys, xs] = True
    _, (fy, fx) = ndimage.distance_transform_edt(~filled, return_indices=True)

    def img(vals, fill):
        out = np.full((Hd, Wd) + vals.shape[1:], fill, np.float64)
        out[ys, xs] = vals
        return out[fy, fx]  # (dilated into the empty space)
    maps = {}
    maps["normal"] = np.round(img(tn * 0.5 + 0.5, 0.5) * 255).clip(0, 255).astype(np.uint8)
    srgb = np.clip(col, 0, 1)
    maps["basecolor"] = np.round(img(srgb, 0.5) * 255).clip(0, 255).astype(np.uint8)
    orm = np.stack([ao, np.clip(rgh, 0.02, 1), np.zeros(len(ao))], -1)
    maps["orm"] = np.round(img(orm, 0.5) * 255).clip(0, 255).astype(np.uint8)
    hr = float(max(np.abs(height).max(), 1e-3))
    maps["height"] = np.round(img((height / hr * 0.5 + 0.5)[:, None], 0.5)[..., 0] * 65535).astype(np.uint16)
    maps["weights"] = []
    for g in range(0, Wt.shape[1], 4):
        w = Wt[:, g:g + 4]
        w = np.c_[w, np.zeros((len(w), 4 - w.shape[1]))]
        maps["weights"].append(np.round(img(w, 0.0) * 255).clip(0, 255).astype(np.uint8))
    inside = covered[ys, xs]
    extra = {}
    if field is not None and inside.any():  # texel error: how far the baked points sit off the exact surface
        k = np.flatnonzero(inside & ~bad)[::7]
        r = np.abs(field.value(X[k])) if len(k) else np.zeros(1)
        extra["texel_error_mm_p50_p99"] = [round(1000 * float(np.percentile(r, q)), 2) for q in (50, 99)]
    return maps, {**extra, "height_range_m": round(hr, 4), "texels": int(inside.sum()),
                  "fallback_pct": round(100 * float(bad[inside].mean()), 3) if inside.any() else 0.0,
                  "fill_pct": round(100 * float(covered.mean()), 1),
                  "height_abs_p99_m": round(float(np.percentile(np.abs(height[inside]), 99)), 4) if inside.any()
                  else 0.0}


# ---------------------------------------------------------------- tiling layers

# per layer: the detail pattern (a tileable height field) and how strongly it shows. Patterns are spectra (periodic by
# construction): "grit" = rock grain and lumps, "grain" = fine grit, "ripples" = sand ripples, "clods" = soil lumps,
# "blades" = grass (streaky fine noise), "litter" = leaf litter blobs, "soft" = snow.
LAYER_DETAIL = {
    "rock": ("grit", 0.35), "wet_rock": ("grit", 0.25), "grass": ("blades", 0.5), "forest_floor": ("litter", 0.6),
    "sand": ("ripples", 0.4), "earth": ("clods", 0.6), "snow": ("soft", 0.25),
}


def _spectral(n, beta, seed, stretch=(1.0, 1.0)):
    """Tileable noise (n x n): random phases with a 1 / f^beta spectrum, zero mean, unit range."""
    rng = np.random.default_rng(seed)
    fx = np.fft.fftfreq(n)[None, :] * stretch[0]
    fy = np.fft.fftfreq(n)[:, None] * stretch[1]
    f = np.sqrt(fx * fx + fy * fy)
    f[0, 0] = 1.0
    amp = f ** -beta
    amp[0, 0] = 0.0
    z = np.real(np.fft.ifft2(amp * np.exp(2j * np.pi * rng.random((n, n)))))
    z -= z.min()
    return z / max(z.max(), 1e-12)


def layer_height(name, n=512):
    kind, _ = LAYER_DETAIL.get(name, ("grain", 0.3))
    s = zlib_seed(name)
    if kind == "grit":
        # grit and lumps only: any Voronoi crack net, even broken up, tiled into honeycomb paving across a cliff (the
        # cracks are the rock's own, in the baked maps)
        h = 0.35 * _spectral(n, 1.6, s + 1) + 0.35 * _spectral(n, 1.0, s + 2) + 0.3 * _spectral(n, 0.6, s + 4)
    elif kind == "ripples":
        h = 0.6 * _spectral(n, 2.2, s, stretch=(0.15, 1.0)) + 0.4 * _spectral(n, 0.8, s + 1)
    elif kind == "blades":
        h = 0.5 * _spectral(n, 0.6, s, stretch=(1.0, 0.25)) + 0.5 * _spectral(n, 1.4, s + 1)
    elif kind == "litter":
        h = 0.6 * (_spectral(n, 2.0, s) > 0.55) + 0.4 * _spectral(n, 1.0, s + 1)
    elif kind == "clods":
        h = 0.7 * _spectral(n, 1.8, s) + 0.3 * _spectral(n, 0.9, s + 1)
    elif kind == "soft":
        h = _spectral(n, 2.4, s)
    else:
        h = _spectral(n, 1.0, s)
    lo, hi = np.percentile(h, [1, 99])  # (full contrast: a few extremes had squeezed the rest into a grey)
    return np.clip((h - lo) / max(hi - lo, 1e-12), 0, 1)


def zlib_seed(name):
    import zlib
    return zlib.crc32(name.encode()) % 100000


def layer_textures(out_dir, layers: dict) -> dict:
    """Tileable textures per layer in out_dir/materials: <layer>_albedo.png (the layer's reference colour varied by
    its pattern, mean = the colour), <layer>_normal.png (glTF convention) and <layer>_height.png. {layer: files}."""
    from PIL import Image
    d = out_dir / "materials"
    d.mkdir(exist_ok=True)
    res = {}
    for name, ref in layers.items():
        h = layer_height(name)
        _, strength = LAYER_DETAIL.get(name, ("grain", 0.3))
        col = np.array(ref["color"], float)
        mod = 1.0 + 0.8 * strength * (h - h.mean())
        alb = np.clip(col[None, None, :] * mod[..., None], 0, 1)
        n = h.shape[0]
        texel = float(ref.get("scale", 3.0)) / n
        depth = 0.02 * strength * float(ref.get("scale", 3.0))  # (pattern relief: a few cm per metre of tile)
        gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * depth / (2 * texel)
        gy = (np.roll(h, 1, 0) - np.roll(h, -1, 0)) * depth / (2 * texel)  # (+y = up the image)
        nm = _unit(np.stack([-gx, -gy, np.ones_like(gx)], -1))
        files = {}
        for key, img in (("albedo", (alb * 255).round().astype(np.uint8)),
                         ("normal", ((nm * 0.5 + 0.5) * 255).round().astype(np.uint8)),
                         ("height", (h * 255).round().astype(np.uint8))):
            fn = f"materials/{name}_{key}.png"
            Image.fromarray(img).save(out_dir / fn)
            files[key] = fn
        res[name] = {**files, "detail_strength": strength}
    return res


def png(a, mode=None):
    from PIL import Image
    b = io.BytesIO()
    if a.dtype == np.uint16:
        Image.fromarray(a, "I;16").save(b, format="PNG")
    else:
        Image.fromarray(a, mode).save(b, format="PNG", optimize=False, compress_level=6)
    return b.getvalue()


def jpeg(a, q=90):
    from PIL import Image
    b = io.BytesIO()
    Image.fromarray(a, "RGB").save(b, format="JPEG", quality=q)
    return b.getvalue()


def material(name, rough=1.0):
    """The reference glTF material over the baked maps: base colour (texture 0), ORM (texture 1: occlusion R,
    roughness G, metallic B = 0), normal (texture 2). Shows the terrain as authored in any glTF viewer."""
    return {"name": name, "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "metallicFactor": 0.0,
                                                   "roughnessFactor": rough,
                                                   "metallicRoughnessTexture": {"index": 1}},
            "normalTexture": {"index": 2}, "occlusionTexture": {"index": 1}}
