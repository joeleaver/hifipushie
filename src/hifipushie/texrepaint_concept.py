"""Texture repaint: the CONCEPT ART as the authority. A turnaround sheet (front | side | back panels, side = the
character's left, facing left) is split into its panels, each panel is registered to the model's own orthographic
silhouette (scale + offset searched for the best overlap, reported as IoU), and every texel the panel's view sees
(depth test, facing, away from the silhouette edge) gets the concept's colour there with a weight (facing cos^2).
That gives, per texel: what the art says it should be, and how sure (how squarely a view sees it)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from .texrepaint_surface import Surface, Texels, View


def load_rgb(path) -> np.ndarray:
    from PIL import Image
    return np.array(Image.open(path).convert("RGB"))


def lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB 0-255 (..,3) -> CIELab (L 0-100)"""
    from skimage.color import rgb2lab
    a = np.clip(np.asarray(rgb, np.float32).reshape(-1, 1, 3) / 255.0, 0, 1)
    return rgb2lab(a).astype(np.float32).reshape(np.shape(rgb))


def foreground(img: np.ndarray, thr: float = 14.0) -> np.ndarray:
    """the subject against a plain studio background (colour taken from the border)"""
    L = lab(img); b = np.concatenate([L[:4].reshape(-1, 3), L[-4:].reshape(-1, 3), L[:, :4].reshape(-1, 3),
                                      L[:, -4:].reshape(-1, 3)])
    bg = np.median(b, 0); d = np.linalg.norm((L - bg) * [0.5, 1, 1], axis=-1)
    m = ndimage.binary_opening(d > thr, np.ones((3, 3)))
    lab_, n = ndimage.label(m)
    area = np.bincount(lab_.ravel(), minlength=n + 1)
    keep = area > 0.002 * m.size; keep[0] = False
    return ndimage.binary_fill_holes(keep[lab_])


def split_panels(img: np.ndarray, n: int = 3) -> list[tuple[int, int, int, int]]:
    """the n subjects of a turnaround sheet, left to right: (x0, y0, x1, y1) boxes"""
    fg = foreground(img); cols = fg.any(0)
    segs, x = [], 0
    while x < len(cols):
        if cols[x]:
            s = x
            while x < len(cols) and cols[x]:
                x += 1
            segs.append([s, x])
        x += 1
    gap = 0.01 * img.shape[1]; merged = []
    for s in segs:
        if merged and s[0] - merged[-1][1] < gap:
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    merged = sorted(sorted(merged, key=lambda s: s[1] - s[0])[-n:])
    out = []
    for s, e in merged:
        rows = np.nonzero(fg[:, s:e].any(1))[0]
        out.append((int(s), int(rows[0]), int(e), int(rows[-1]) + 1))
    return out


@dataclass
class Panel:
    view: str
    img: np.ndarray        # the whole sheet
    box: tuple             # (x0, y0, x1, y1) of this panel
    k: float = 1.0         # concept px per view px
    t: tuple = (0.0, 0.0)  # concept px = k * view px + t
    iou: float = 0.0
    sil: np.ndarray | None = None


def register(panel: Panel, v: View, ref=None, search: bool = True, k_fix: float | None = None,
             ground: float | None = None) -> Panel:
    """fit concept = k * view + t. With ref (rows, cols, rgb of the model rendered with its OWN generated texture,
    View.textured) the fit maximises COLOUR agreement with the panel (robust to patterned backdrops: no matte
    needed); without it, silhouette IoU against the border-colour foreground. Coarse grid, then a fine one."""
    sil = v.silhouette(); ys, xs = np.nonzero(sil); x0, y0, x1, y1 = panel.box
    H, W = panel.img.shape[:2]; mh = ys.max() - ys.min() + 1; mw = xs.max() - xs.min() + 1
    if ref is not None:
        r, c, rgb = ref
        sel = np.random.default_rng(0).choice(len(r), min(len(r), 4000), replace=False)
        r, c = r[sel].astype(np.float32), c[sel].astype(np.float32); want = lab(rgb[sel]) * [0.5, 1, 1]
        L = lab(panel.img) * [0.5, 1, 1]

        def score(k, tx, ty):
            cy = np.clip((k * r + ty).astype(int), 0, H - 1); cx = np.clip((k * c + tx).astype(int), 0, W - 1)
            return -np.minimum(np.linalg.norm(L[cy, cx] - want, axis=1), 40).mean()
    else:
        fg = foreground(panel.img); S = sil[::2, ::2]

        def score(k, tx, ty):
            w = ndimage.affine_transform(fg.astype(np.float32), [k * 2, k * 2], offset=[ty, tx], output_shape=S.shape,
                                         order=0) > 0.5
            return (w & S).sum() / max((w | S).sum(), 1)
    # coarse: the subject is 55-100 % of the sheet height, centred anywhere in its panel's columns
    kmax = H / mh; best = (-1e9, kmax, 0, 0)
    grid = [(k, (x0 + x1) / 2 - k * (xs.min() + xs.max()) / 2 + dx, ty)
            for k in (kmax * np.linspace(0.55, 1.0, 13) if k_fix is None else k_fix * np.linspace(0.97, 1.03, 3))
            for dx in np.linspace(-0.12, 0.12, 9) * (x1 - x0)
            for ty in np.linspace(-0.05 * H, H - k * mh * 0.95, 11) - k * ys.min()]
    if k_fix is not None and ground is not None:   # same sheet: same scale, same ground line; slide sideways only
        ty = ground - k_fix * ys.max()
        txc = (x0 + x1) / 2 - k_fix * (xs.min() + xs.max()) / 2       # centred in its panel, then a local refine
        grid = [(k_fix, txc + dx, ty) for dx in np.linspace(-0.06, 0.06, 25) * (x1 - x0)]
    for k, tx, ty in (grid if search else grid[:1]):
        sc = score(k, tx, ty)
        if sc > best[0]:
            best = (sc, k, tx, ty)
    for it in range(3 if search and ground is None else 0):  # fine: shrink around the best
        _, k0, tx0, ty0 = best; f = 0.4 ** (it + 1)
        for k in k0 * (1 + np.linspace(-0.1, 0.1, 7) * f * (0.3 if k_fix else 1)):
            for tx in tx0 + np.linspace(-0.08, 0.08, 9) * f * mw * k:
                for ty in ty0 + np.linspace(-0.08, 0.08, 9) * f * mh * k:
                    sc = score(k, tx, ty)
                    if sc > best[0]:
                        best = (sc, k, tx, ty)
    panel.iou, panel.k, panel.t = float(best[0]), float(best[1]), (float(best[2]), float(best[3]))
    return panel


def project(panels: list[Panel], surf: Surface, tx: Texels, ppm: float, edge_px: int = 3, keep=None,
            image_index: int | None = None, tex: np.ndarray | None = None):
    """per texel: the concept colour (weighted mean over the views that see it), the total weight, and per view
    the weight (for the report). keep: triangle mask of what occludes (LODs excluded)."""
    n = len(tx.idx); acc = np.zeros((n, 3), np.float32); wsum = np.zeros(n, np.float32); per = {}; regs = []
    occ = surf if keep is None else _sub(surf, keep); k_fix = ground = None
    for p in sorted(panels, key=lambda p: p.view != "front"):   # the front fixes the sheet's scale
        v = View(p.view, occ, ppm, *surf.bounds())
        p = register(Panel(p.view, p.img, p.box), v, None if tex is None else v.textured(image_index, tex),
                     k_fix=k_fix, ground=ground)
        if k_fix is None:
            k_fix, ground = p.k, p.k * np.nonzero(v.silhouette())[0].max() + p.t[1]
        p.sil = v.silhouette(); regs.append(p)
        vis, cos, xy = v.visible(tx.pos, tx.nrm)
        inner = ndimage.distance_transform_edt(v.silhouette()) > edge_px
        xi = np.clip(xy[:, 0].astype(int), 0, v.W - 1); yi = np.clip(xy[:, 1].astype(int), 0, v.H - 1)
        ok = vis & inner[yi, xi]
        cx = p.k * xy[:, 0] + p.t[0]; cy = p.k * xy[:, 1] + p.t[1]
        H, W = p.img.shape[:2]
        ok &= (cx >= 0) & (cy >= 0) & (cx < W - 1) & (cy < H - 1)
        col = np.stack([ndimage.map_coordinates(p.img[..., c].astype(np.float32), [cy[ok], cx[ok]], order=1)
                        for c in range(3)], 1)
        w = np.zeros(n, np.float32); w[ok] = np.clip(cos[ok], 0, 1) ** 2
        acc[ok] += col * w[ok, None]; wsum += w; per[p.view] = (w, p.iou, p.k)
    colour = acc / np.maximum(wsum, 1e-6)[:, None]
    return colour, wsum, per, regs


def _sub(surf: Surface, keep):
    return Surface(surf.P[keep], surf.N[keep], surf.UV[keep], surf.img[keep], surf.obj[keep], surf.meta)


def panels_from(sheet_path, views=("front", "side", "back")) -> list[Panel]:
    img = load_rgb(sheet_path); boxes = split_panels(img, len(views))
    if len(boxes) != len(views):   # subjects (or their backdrop halos) touch: equal columns, as sheets are laid out
        W = img.shape[1]; n = len(views); fg = foreground(img)
        boxes = []
        for i in range(n):
            a, b = i * W // n, (i + 1) * W // n; rows = np.nonzero(fg[:, a:b].any(1))[0]
            boxes.append((a, int(rows[0]) if len(rows) else 0, b, int(rows[-1]) + 1 if len(rows) else img.shape[0]))
    return [Panel(v, img, b) for v, b in zip(views, boxes)]


def palette(colours: np.ndarray, k: int = 6, seed: int = 0) -> list[dict]:
    """k-means (Lab, lightness half-weighted so shading doesn't split a colour) of foreground pixels: the colours a
    painter would mix, biggest first, with their share"""
    L = lab(colours.reshape(-1, 3).astype(np.float32)) * [0.5, 1, 1]
    rng = np.random.default_rng(seed); sel = L[rng.choice(len(L), min(len(L), 40000), replace=False)]
    cen = kmeans(sel, k, rng)
    rgbs = colours.reshape(-1, 3)
    out = []
    d = np.linalg.norm(L[:, None] - cen[None], axis=-1).argmin(1)
    for j in range(k):
        m = d == j
        if not m.any():
            continue
        out.append({"colour": [int(x) for x in np.median(rgbs[m], 0)], "share": round(float(m.mean()), 3)})
    return sorted(out, key=lambda e: -e["share"])


def kmeans(X: np.ndarray, k: int, rng, iters: int = 30) -> np.ndarray:
    """plain k-means++ (no OpenCV / sklearn in the environment)"""
    cen = [X[rng.integers(len(X))]]
    for _ in range(1, k):
        d = np.min(np.linalg.norm(X[:, None] - np.array(cen)[None], axis=-1), 1) ** 2
        cen.append(X[rng.choice(len(X), p=d / d.sum())])
    cen = np.array(cen)
    for _ in range(iters):
        a = np.linalg.norm(X[:, None] - cen[None], axis=-1).argmin(1)
        new = np.array([X[a == j].mean(0) if (a == j).any() else cen[j] for j in range(k)])
        if np.allclose(new, cen, atol=0.05):
            break
        cen = new
    return cen


def overlay(panels: list[Panel]) -> np.ndarray:
    """the sheet with each registered model silhouette outlined in red: check the registration by eye"""
    img = panels[0].img.copy(); H, W = img.shape[:2]
    for p in panels:
        if p.sil is None:
            continue
        edge = p.sil & ~ndimage.binary_erosion(p.sil, iterations=2)
        r, c = np.nonzero(edge)
        y = np.clip((p.k * r + p.t[1]).astype(int), 0, H - 1); x = np.clip((p.k * c + p.t[0]).astype(int), 0, W - 1)
        img[y, x] = (255, 0, 0)
    return img
