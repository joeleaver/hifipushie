"""Cards: a card's spec, a twig rasterized into its tile, the outline strip, the card's mesh. Part of the leaves, twigs and their cards (veg_leaf.py has the overview)."""
from __future__ import annotations

import math

import numpy as np
from numba import njit

from . import veg_leaf

# ---------------------------------------------------------------- atlases and cards
def _srgb(c):
    c = np.clip(np.asarray(c, float), 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def card_spec(leaves: dict) -> dict:
    """The leaves spec a card's picture is made from: the mesh twig's, with `leaves.card.twig` / `.leaf` over it (a
    picture can afford thousands of true-width needles and a three-year fan where a mesh twig can't)."""
    cd = {**veg_leaf.CARD, **(leaves.get("card") or {})}
    out = {**leaves, **cd["leaf"]}
    out["twig"] = {**(leaves.get("twig") or {}), **cd["twig"], "variants": cd["variants"]}
    return out


def _enclose(poly: np.ndarray, k: int) -> np.ndarray:
    """A convex polygon of at most k corners round a convex one: drop the edge whose neighbours meet nearest."""
    P = [np.asarray(q, float) for q in poly]
    while len(P) > k:
        n = len(P)
        best = None
        for i in range(n):
            a0, a1, b0, b1 = P[i - 1], P[i], P[(i + 1) % n], P[(i + 2) % n]
            d1, d2 = a1 - a0, b0 - b1
            den = d1[0] * d2[1] - d1[1] * d2[0]
            if abs(den) < 1e-12:
                continue
            t = ((b1[0] - a0[0]) * d2[1] - (b1[1] - a0[1]) * d2[0]) / den
            if t < 1:  # the neighbours diverge: this edge can't go
                continue
            X = a0 + t * d1
            area = 0.5 * abs((b0[0] - a1[0]) * (X[1] - a1[1]) - (b0[1] - a1[1]) * (X[0] - a1[0]))
            if best is None or area < best[0]:
                best = (area, i, X)
        if best is None:
            break
        _, i, X = best
        j = (i + 1) % n
        P[i] = X
        del P[j]
    return np.array(P)


@njit(cache=True)
def _face_ids(px, py, F, z, n):
    """Per pixel of an n x n picture: the highest face (by its own z) covering the pixel's centre, or within half a
    pixel of it (a needle thinner than a pixel still draws, as a line); -1 = none."""
    ids = np.full((n, n), -1, np.int64)
    zb = np.full((n, n), -1e30)
    for f in range(len(F)):
        x0, y0 = px[F[f, 0]], py[F[f, 0]]
        x1, y1 = px[F[f, 1]], py[F[f, 1]]
        x2, y2 = px[F[f, 2]], py[F[f, 2]]
        ix0 = max(int(math.floor(min(x0, x1, x2) - 1.0)), 0)
        ix1 = min(int(math.ceil(max(x0, x1, x2) + 1.0)), n - 1)
        iy0 = max(int(math.floor(min(y0, y1, y2) - 1.0)), 0)
        iy1 = min(int(math.ceil(max(y0, y1, y2) + 1.0)), n - 1)
        if ix1 < ix0 or iy1 < iy0:
            continue
        ar = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        sg = 1.0 if ar >= 0 else -1.0
        l0 = math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2) * 0.5
        l1 = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2) * 0.5
        l2 = math.sqrt((x0 - x2) ** 2 + (y0 - y2) ** 2) * 0.5
        zf = z[f]
        for iy in range(iy0, iy1 + 1):
            cy = iy + 0.5
            for ix in range(ix0, ix1 + 1):
                if zf < zb[iy, ix]:
                    continue
                cx = ix + 0.5
                if sg * ((x1 - x0) * (cy - y0) - (y1 - y0) * (cx - x0)) < -l0:
                    continue
                if sg * ((x2 - x1) * (cy - y1) - (y2 - y1) * (cx - x1)) < -l1:
                    continue
                if sg * ((x0 - x2) * (cy - y2) - (y0 - y2) * (cx - x2)) < -l2:
                    continue
                zb[iy, ix] = zf
                ids[iy, ix] = f
    return ids


def rasterize(mesh: dict, leaf_color, wood_color, size: int = 384, ss: int = 2, rough=(0.5, 0.85)) -> dict:
    """A twig seen from above (its upper side toward the eye, running up the picture) as maps: color (sRGB, the
    colour bled past the alpha's edge), alpha, normal (tangent space of the card), mask (R = light comes through:
    leaf 1 / wood 0, thinner where leaves overlap; G = roughness; B = shade: lower leaves darker). `frame` = the
    picture's square in the twig's metres [x0, y0, side]."""
    from PIL import Image, ImageDraw
    from scipy import ndimage
    V, F = mesh["V"], mesh["F"]
    lo, hi = V[:, :2].min(0), V[:, :2].max(0)
    side = float(max(hi - lo)) * 1.06
    cx = 0.5 * (lo[0] + hi[0])
    x0, y0 = cx - side / 2, lo[1] - 0.03 * side
    n = size * ss
    px = (V[:, 0] - x0) / side * n
    py = (1 - (V[:, 1] - y0) / side) * n
    tri = V[F]
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-12)
    fn[fn[:, 2] < 0] *= -1
    zmean = tri[:, :, 2].mean(1)
    zr = (zmean - zmean.min()) / max(np.ptp(zmean), 1e-9)
    tone = mesh["col"][F].mean(1)
    leaf = mesh["mat"] == 1
    lc, wc = np.asarray(leaf_color, float), np.asarray(wood_color, float)  # (spec colours are sRGB already)
    # a leaf is not one flat green: each blade half catches the light by its own tilt, pale ones run yellow and dark
    # ones blue-green, lower ones sit in the upper ones' shade (flat per-leaf tones read as poster paint at 2 m)
    lit = 0.7 + 0.42 * np.clip(fn @ np.array([-0.38, 0.42, 0.82]), 0, 1)
    dev = np.clip((tone - np.median(tone[leaf]) if leaf.any() else tone * 0) * 2.2, -0.6, 0.6)
    hue = np.stack([1 + 0.22 * dev, 1 + 0.06 * dev, 1 - 0.35 * dev], 1)
    col = np.where(leaf[:, None], lc[None] * hue * (np.clip(tone, 0, 1.6) * lit)[:, None], wc[None] * np.clip(tone, 0.4, 1.6)[:, None]) * (0.72 + 0.28 * zr)[:, None]
    if "rgb" in mesh:  # parts with a colour of their own (petals, a flower's eye)
        own = mesh["rgb"][F].mean(1)
        has = ~np.isnan(own[:, 0])
        col[has] = own[has] * (np.clip(tone[has], 0, 1.6) * (0.85 + 0.15 * lit[has]))[:, None]
    # which face shows in each pixel: the upper faces over the lower (a painter's order, as a depth test on each
    # face's own height). One compiled pass: PIL polygons, four a face, took 20 min for a spruce's bough atlas
    ids = _face_ids(np.ascontiguousarray(px, np.float64), np.ascontiguousarray(py, np.float64),
                    np.ascontiguousarray(F, np.int64), np.ascontiguousarray(zmean, np.float64), n)
    hit = ids >= 0
    fi = np.where(hit, ids, 0)

    def paint(vals, empty):
        img = np.asarray(vals, np.float32)[fi]
        img[~hit] = empty
        return img.reshape(size, ss, size, ss, -1).mean((1, 3))  # (a box filter down to the picture's size)

    a = paint(np.ones((len(F), 1)), 0.0)[..., 0]
    c = paint(np.clip(col, 0, 1), 0.0)
    im_n = np.clip(fn * 0.5 + 0.5, 0, 1)
    im_m = np.stack([leaf.astype(float), np.where(leaf, rough[0], rough[1]), 0.55 + 0.45 * zr], 1)
    c = np.where(a[..., None] > 1e-3, c / np.maximum(a[..., None], 1e-3), 0)  # un-premultiply the box filter
    grain = ndimage.gaussian_filter(np.random.default_rng(3).random((size, size)), 1.2)
    c = c * (0.93 + 0.14 * (grain - grain.min()) / max(float(np.ptp(grain)), 1e-9))[..., None]
    solid = a > 0.02
    if solid.any():  # bleed the colour out past the edge (no dark fringe under filtering)
        idx = ndimage.distance_transform_edt(~solid, return_distances=False, return_indices=True)
        c = c[idx[0], idx[1]]
    nrm = paint(im_n, (128 / 255, 128 / 255, 1.0))
    m = paint(im_m, (0.0, 1.0, 1.0))
    return {"color": np.clip(c, 0, 1), "alpha": a, "normal": nrm, "mask": m, "frame": [x0, y0, side],
            "coverage": float((a > 0.5).mean())}


def _strip_outline(alpha: np.ndarray, strips: int):
    """A ladder round a long thin picture: per band along the twig the alpha's own left and right, as uv rows
    (bottom to top) of [left, right, v]."""
    n = alpha.shape[0]
    m = alpha > 0.08
    rows = np.flatnonzero(m.any(1))
    r0, r1 = rows[0], rows[-1] + 1
    edges = np.linspace(r0, r1, strips + 1)
    left = np.where(m.any(1), m.argmax(1), n).astype(float)
    right = np.where(m.any(1), n - m[:, ::-1].argmax(1), 0).astype(float)
    out = []
    for j, e in enumerate(edges):  # each rung spans the bands it borders
        a = int(np.floor(edges[max(j - 1, 0)]))
        b = int(np.ceil(edges[min(j + 1, strips)]))
        out.append([left[a:b].min() / n, right[a:b].max() / n, 1 - e / n])
    return np.array(out[::-1])


def card_mesh(alpha: np.ndarray, frame, verts: int = 7, cup: float = 0.1, cross: int = 1, droop: float = 0.0,
              length: float = 0.3, strips: int = 0, centre: bool = True) -> dict:
    """A card cut tight round a twig's picture: a convex polygon of at most `verts` corners round the alpha, as a
    fan from its middle (cupped, drooping like the twig), in the twig's own frame; uv = 0..1 in the picture.
    cross 2 adds the same card turned a quarter round the twig (tufts). `strips` n cuts a long thin twig as a
    ladder of n quads following its own width instead (a hanging birch or willow twig fills a fifth of one polygon)."""
    from scipy.spatial import ConvexHull
    n = alpha.shape[0]
    ys, xs = np.nonzero(alpha > 0.08)
    if len(xs) < 3:
        raise ValueError("an empty twig picture")
    x0, y0, side = frame
    if strips and strips > 1:
        lad = _strip_outline(alpha, int(strips))
        UV = np.vstack([np.c_[lad[:, 0], lad[:, 2]], np.c_[lad[:, 1], lad[:, 2]]])
        m_ = len(lad)
        F = np.array([t for i in range(m_ - 1) for t in ([i, m_ + i, m_ + i + 1], [i, m_ + i + 1, i + 1])])
    else:
        pts = np.c_[np.r_[xs, xs + 1, xs, xs + 1], np.r_[ys, ys, ys + 1, ys + 1]].astype(float)
        hull = pts[ConvexHull(pts).vertices]
        poly = _enclose(hull, verts)
        uv = np.clip(np.c_[poly[:, 0] / n, 1 - poly[:, 1] / n], -0.05, 1.05)
        k = len(poly)
        if centre:
            UV = np.vstack([uv.mean(0), uv])
            F = np.array([[0, 1 + i, 1 + (i + 1) % k] for i in range(k)])
        else:  # a fan from one corner: k - 2 triangles (no middle vertex: cheaper cards, more of them)
            UV = uv
            F = np.array([[0, i, i + 1] for i in range(1, k - 1)])
    X = x0 + UV[:, 0] * side
    Y = y0 + UV[:, 1] * side
    hw = max(np.abs(X).max(), 1e-6)
    Z = cup * hw * (np.abs(X) / hw) ** 2 - droop * length * np.clip(Y / max(length, 1e-6), 0, 1.5) ** 2
    V = np.c_[X, Y, Z]
    if np.cross(V[F[0, 1]] - V[F[0, 0]], V[F[0, 2]] - V[F[0, 0]])[2] < 0:
        F = F[:, ::-1]
    if cross > 1:
        V2 = np.c_[-V[:, 2], V[:, 1], V[:, 0]]
        V, F, UV = np.vstack([V, V2]), np.vstack([F, F + len(V)]), np.vstack([UV, UV])
    area = 0.5 * np.abs(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])).sum(-1 if V.shape[1] == 2 else None) if False else \
        float(0.5 * np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1).sum())
    return {"V": V, "F": F, "uv": UV, "area": area}
