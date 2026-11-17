"""Texture repaint: GRAPHICS (signs, numbers, labels, logos) are not painted by region: the splat texture smears them
into half-letters and warped shapes, so a texture artist REDRAWS them as a clean decal and lays it on the face.

  face(tx, surf, part)          the part's flat face: plane by PCA of its texels, the side facing the viewer (-y),
                                axes up (world z projected) / right; the face outline's corners
  rectify(...)                  what the generated texture shows on that face, front-on (the hallucination, to judge)
  redraw(concept, src_pts, dst_pts, canvas, k)
                                the concept's graphic warped onto the face canvas (affine from 3 corners or a
                                homography from 4), then REDRAWN: posterised to its k flat colours (k-means), each
                                colour's shape smoothed at the canvas resolution (no jaggies, no specks)
  apply(...)                    the decal onto the map's texels on that face (soft edge, inset from the rim)
The graphic can also come from an image model (oxidegen's edit / generate, given the concept crop): pass it as an
RGBA png in canvas space and only apply() runs."""
from __future__ import annotations

import numpy as np
from PIL import Image
from scipy import ndimage

from .texrepaint_concept import kmeans, lab


def face(tx, surf, part: str, toward=(0, -1, 0)):
    names = surf.meta["objects"]
    objs = [i for i, n in enumerate(names) if part.lower() in n.lower() and "lod" not in n.lower()]
    if not objs:
        raise ValueError(f"part {part!r}: no object with that name; objects: {sorted(set(names))}")
    sel = np.isin(tx.obj, objs)
    p = tx.pos[sel]; c = p.mean(0); _, _, Vt = np.linalg.svd(p - c, full_matrices=False)
    n = Vt[2] * np.sign(Vt[2] @ np.array(toward, np.float32) or 1)
    up = np.array([0, 0, 1.0]) - n * n[2]; up /= np.linalg.norm(up); right = np.cross(up, n)
    # the face toward the viewer by POSITION (front half of the plate) and |normal . n| (fused-mesh parts can carry
    # flipped normals: selecting by normal alone found only the rim on Scraps' kart sign)
    front = sel & ((tx.pos - c) @ n > 0) & (np.abs(tx.nrm @ n) > 0.5)
    return {"centre": c, "n": n, "up": up, "right": -right, "front": front, "objects": objs}


def canvas_coords(F, pos, px_per_m, box):
    d = pos - F["centre"]; u = d @ F["right"]; v = d @ F["up"]
    x0, y1 = box[0], box[3]
    return (u - x0) * px_per_m, (y1 - v) * px_per_m


def face_box(F, tx, margin=0.01):
    d = tx.pos[F["front"]] - F["centre"]; u = d @ F["right"]; v = d @ F["up"]
    return (u.min() - margin, v.min() - margin, u.max() + margin, v.max() + margin)


def rectify(F, tx, tex_rgb, size=1024):
    """the generated texture on the face, front-on: (image, px_per_m, box, outline mask)"""
    box = face_box(F, tx); ppm = size / max(box[2] - box[0], box[3] - box[1])
    W, H = int((box[2] - box[0]) * ppm) + 1, int((box[3] - box[1]) * ppm) + 1
    x, y = canvas_coords(F, tx.pos[F["front"]], ppm, box)
    img = np.zeros((H, W, 3), np.float32); cnt = np.zeros((H, W), np.float32)
    xi, yi = np.clip(x.astype(int), 0, W - 1), np.clip(y.astype(int), 0, H - 1)
    np.add.at(img, (yi, xi), tex_rgb[F["front"]]); np.add.at(cnt, (yi, xi), 1)
    m = cnt > 0; img[m] /= cnt[m, None]
    m2 = ndimage.binary_closing(m, iterations=3)
    img = _fill(img, m)
    img[~m2] = 0
    return img.astype(np.uint8), ppm, box, ndimage.binary_fill_holes(m2)


def _fill(img, m):
    idx = ndimage.distance_transform_edt(~m, return_distances=False, return_indices=True)
    return img[idx[0], idx[1]]


def corners(mask, n=3):
    """the outline's n corners (largest-area polygon on the convex hull), ordered: top first, then clockwise"""
    from scipy.spatial import ConvexHull
    ys, xs = np.nonzero(mask); pts = np.stack([xs, ys], 1).astype(np.float64)
    h = pts[ConvexHull(pts).vertices]
    if len(h) > 60:
        h = h[np.linspace(0, len(h) - 1, 60).astype(int)]
    best, sel = -1, None
    import itertools
    for comb in itertools.combinations(range(len(h)), n):
        P = h[list(comb)]; a = 0.5 * abs(np.dot(P[:, 0], np.roll(P[:, 1], 1)) - np.dot(P[:, 1], np.roll(P[:, 0], 1)))
        if a > best:
            best, sel = a, P
    c = sel.mean(0); ang = np.arctan2(sel[:, 1] - c[1], sel[:, 0] - c[0])
    sel = sel[np.argsort(ang)]                     # image coords: increasing angle = clockwise on screen
    top = np.argmin(sel[:, 1])
    return np.roll(sel, -top, 0)


def _affine(src, dst):
    """matrix M (2x3) with dst = M @ [src, 1]"""
    A = np.hstack([src, np.ones((len(src), 1))])
    M, *_ = np.linalg.lstsq(A, dst, rcond=None)
    return M.T


def _homography(src, dst):
    A = []
    for (x, y), (u, v) in zip(src, dst):
        A += [[-x, -y, -1, 0, 0, 0, u * x, u * y, u], [0, 0, 0, -x, -y, -1, v * x, v * y, v]]
    _, _, Vt = np.linalg.svd(np.array(A)); Hm = Vt[-1].reshape(3, 3)
    return Hm / Hm[2, 2]


def redraw(concept: np.ndarray, src_pts, dst_pts, shape, k=4, smooth=None, colours=None, inside=None):
    """warp the concept graphic onto the canvas (dst = canvas px of the same corners), then redraw it as k flat
    colours with smooth shapes. Returns (RGB image, label image, palette)."""
    H, W = shape; src = np.asarray(src_pts, np.float64); dst = np.asarray(dst_pts, np.float64)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    if len(src) == 3:   # canvas -> concept
        M = _affine(dst, src); cx = M[0, 0] * xx + M[0, 1] * yy + M[0, 2]; cy = M[1, 0] * xx + M[1, 1] * yy + M[1, 2]
        scale = np.sqrt(abs(np.linalg.det(M[:, :2])))
    else:
        Hm = _homography(dst, src); w = Hm[2, 0] * xx + Hm[2, 1] * yy + Hm[2, 2]
        cx = (Hm[0, 0] * xx + Hm[0, 1] * yy + Hm[0, 2]) / w; cy = (Hm[1, 0] * xx + Hm[1, 1] * yy + Hm[1, 2]) / w
        scale = np.sqrt(abs(np.linalg.det(Hm[:2, :2])))
    warped = np.stack([ndimage.map_coordinates(concept[..., c].astype(np.float32), [cy, cx], order=3, mode="nearest")
                       for c in range(3)], -1).clip(0, 255)
    inside = np.ones((H, W), bool) if inside is None else inside
    L = lab(warped) * [0.7, 1, 1]
    if colours is None:
        rng = np.random.default_rng(0); X = L[inside]
        cen = kmeans(X[rng.choice(len(X), min(len(X), 20000), replace=False)], k, rng)
    else:
        cen = lab(np.array(colours, np.float32)) * [0.7, 1, 1]
    d = np.linalg.norm(L[..., None, :] - cen[None, None], axis=-1)
    # shapes: each colour's soft membership smoothed over ~1 concept pixel, then the max (clean, anti-aliased later)
    s = smooth or max(1.0 / max(scale, 1e-6) * 0.9, 1.0)
    memb = np.exp(-(d - d.min(-1, keepdims=True)) / 6.0)
    memb = np.stack([ndimage.gaussian_filter(memb[..., j], s) for j in range(len(cen))], -1)
    lab_ = memb.argmax(-1)
    # remove specks smaller than a few concept pixels
    min_px = int((3.0 / max(scale, 1e-6)) ** 2)
    for j in range(len(cen)):
        comp, n = ndimage.label(lab_ == j)
        if n:
            sizes = np.bincount(comp.ravel())
            small = sizes < min_px; small[0] = False
            if small.any():
                bad = small[comp]
                memb[bad, j] = 0
    lab_ = memb.argmax(-1)
    # halos: a colour that only exists as a thin band along another boundary is the concept's anti-aliasing, not
    # paint (a brown rim round black on yellow): open each colour by ~1 concept pixel, give what goes to the next best
    r = max(int(round(1.0 / max(scale, 1e-6))), 1); st = ndimage.generate_binary_structure(2, 1)
    for j in range(len(cen)):
        m = lab_ == j
        thin = m & ~ndimage.binary_opening(m, st, iterations=r)
        memb[thin, j] = -1
    lab_ = memb.argmax(-1)
    pal = np.array([np.median(warped[inside & (lab_ == j)], 0) if (inside & (lab_ == j)).any() else [0, 0, 0]
                    for j in range(len(cen))]) if colours is None else np.array(colours, np.float32)
    # anti-aliased edges: supersampled label -> colour, then a light blur at the edge only
    rgb = pal[lab_].astype(np.float32)
    edge = ndimage.morphological_gradient(lab_, size=3) > 0
    rgb[edge] = ndimage.uniform_filter(rgb, (3, 3, 1))[edge]
    return rgb.clip(0, 255).astype(np.uint8), lab_, pal.astype(int).tolist()


def apply(colour: np.ndarray, F, tx, decal: np.ndarray, alpha: np.ndarray, ppm, box):
    """the decal (canvas RGB + alpha) onto the map (res x res x 3, the map tx was rasterised at)"""
    sel = F["front"]; x, y = canvas_coords(F, tx.pos[sel], ppm, box)
    H, W = decal.shape[:2]
    ok = (x >= 0) & (y >= 0) & (x < W - 1) & (y < H - 1)
    a = ndimage.map_coordinates(alpha.astype(np.float32), [y[ok], x[ok]], order=1)
    rgb = np.stack([ndimage.map_coordinates(decal[..., c].astype(np.float32), [y[ok], x[ok]], order=1)
                    for c in range(3)], 1)
    flat = colour.reshape(-1, 3).astype(np.float32); ids = tx.idx[sel][ok]
    flat[ids] = flat[ids] * (1 - a[:, None]) + rgb * a[:, None]
    return flat.reshape(colour.shape).clip(0, 255).astype(np.uint8), int(ok.sum())
