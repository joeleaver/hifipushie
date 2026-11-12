"""Silhouettes and measures: the silhouette, shape measures, outline IoU, branch angles, reference masks and
branch directions. Part of vegetation (vegetation.py has the overview)."""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from .vegetation_tree import _norm

# ---------------------------------------------------------------- silhouettes and measures
def silhouette(tree: dict, azimuth: float = 0.0, px_per_m: float = 20.0, leaves: bool = True, pad: float = 0.5):
    """An orthographic side view as a boolean mask (rows top to bottom) and its frame {x0, z1, px_per_m}: branches as
    lines of their own width, leaves as discs. Milliseconds: what measures and fits look at."""
    from PIL import Image, ImageDraw
    P, par, rad = tree["pos"], tree["parent"], tree["radius"]
    c, s_ = math.cos(math.radians(azimuth)), math.sin(math.radians(azimuth))
    x = P[:, 0] * c + P[:, 1] * s_
    z = P[:, 2]
    lx = lz = lr = np.zeros(0)
    if leaves:  # each twig as a disc of about its own size
        from . import veg_leaf
        tw = veg_leaf.place_live(tree)
        if len(tw["pos"]):
            tl = {**veg_leaf.TWIG, **(tree["spec"]["leaves"].get("twig") or {})}["length"]
            cen = tw["pos"] + tw["frame"][:, :, 1] * (0.5 * tl * tw["scale"])[:, None]
            lx, lz, lr = cen[:, 0] * c + cen[:, 1] * s_, cen[:, 2], 0.45 * tl * tw["scale"]
    x0 = min(x.min(), lx.min() if len(lx) else 0) - pad
    x1 = max(x.max(), lx.max() if len(lx) else 0) + pad
    z1 = max(z.max(), lz.max() if len(lz) else 0) + pad
    W, H = int((x1 - x0) * px_per_m) + 1, int(z1 * px_per_m) + 1
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    X, Y = (x - x0) * px_per_m, (z1 - z) * px_per_m
    wpx = np.maximum(1, np.round(2 * rad * px_per_m)).astype(int)
    for i in range(1, len(P)):
        p = par[i]
        d.line([X[p], Y[p], X[i], Y[i]], fill=255, width=int(wpx[i]))
    if len(lx):
        r = np.maximum(1.0, lr * px_per_m)
        LX, LY = (lx - x0) * px_per_m, (z1 - lz) * px_per_m
        for i in range(len(lx)):
            d.ellipse([LX[i] - r[i], LY[i] - r[i], LX[i] + r[i], LY[i] + r[i]], fill=255)
    return np.asarray(im) > 0, {"x0": x0, "z1": z1, "px_per_m": px_per_m}


def _rows(mask):
    """Per row: leftmost, rightmost filled column (or -1)."""
    any_ = mask.any(1)
    left = np.where(any_, mask.argmax(1), -1)
    right = np.where(any_, mask.shape[1] - 1 - mask[:, ::-1].argmax(1), -1)
    return any_, left, right


def shape_measures(mask: np.ndarray, levels: int = 20) -> dict:
    """What a silhouette says about the tree's form, in units of its height: crown width, the bole (height where the
    crown starts: the lowest level at least a quarter as wide as the widest), the height of the widest point, the
    width profile bottom to top, how lopsided it is about the trunk's foot, and porosity (sky inside the outline)."""
    any_, left, right = _rows(mask)
    rows = np.flatnonzero(any_)
    top, bot = rows[0], rows[-1]
    H = bot - top + 1
    foot = slice(bot - max(2, H // 50), bot + 1)
    cx = 0.5 * (left[foot][any_[foot]].mean() + right[foot][any_[foot]].mean())
    width = np.where(any_, right - left + 1, 0)[top: bot + 1][::-1].astype(float)  # bottom to top
    lft = np.where(any_, cx - left, 0)[top: bot + 1][::-1]
    rgt = np.where(any_, right - cx, 0)[top: bot + 1][::-1]
    k = max(3, H // 40)
    sm = ndimage.uniform_filter1d(width, k)
    wmax = sm.max()
    crown0 = int(np.argmax(sm >= 0.25 * wmax))
    filled = sum(int(r - l + 1) for a, l, r in zip(any_, left, right) if a)
    t = (np.arange(levels) + 0.5) / levels
    hh = np.arange(H) / H
    return {"width_over_height": round(float(wmax / H), 3), "bole": round(float(crown0 / H), 3),
            "widest_at": round(float(np.argmax(sm) / H), 3),
            "crown_aspect": round(float(wmax / max(H - crown0, 1)), 3),
            "lopsided": round(float((ndimage.uniform_filter1d(rgt, k).max() - ndimage.uniform_filter1d(lft, k).max()) / max(wmax, 1)), 3),
            "porosity": round(float(1 - mask.sum() / max(filled, 1)), 3),
            "profile": [round(float(v), 3) for v in np.interp(t, hh, sm) / H],
            "_cx": float(cx), "_top": int(top), "_bot": int(bot)}


def _outline(mask, size=256):
    """The row-filled outline, scaled to `size` rows tall, the trunk's foot at the centre column."""
    from PIL import Image
    m = shape_measures(mask, 4)
    any_, left, right = _rows(mask)
    f = np.zeros_like(mask)
    for i in np.flatnonzero(any_):
        f[i, left[i]: right[i] + 1] = True
    f = f[m["_top"]: m["_bot"] + 1]
    sc = size / f.shape[0]
    w = max(1, int(round(f.shape[1] * sc)))
    g = np.asarray(Image.fromarray(f.astype(np.uint8) * 255).resize((w, size), Image.BILINEAR)) > 127
    out = np.zeros((size, 3 * size), bool)
    x0 = int(round(1.5 * size - m["_cx"] * sc))
    a, b = max(x0, 0), min(x0 + w, 3 * size)
    out[:, a:b] = g[:, a - x0: b - x0]
    return out


def outline_iou(mask_a, mask_b, flip: bool = True) -> float:
    """IoU of two silhouettes' row-filled outlines at equal height, feet together (the better of both mirrorings)."""
    A, B = _outline(mask_a), _outline(mask_b)
    best = 0.0
    for Bm in ([B, B[:, ::-1]] if flip else [B]):
        best = max(best, float((A & Bm).sum() / max((A | Bm).sum(), 1)))
    return round(best, 3)


def branch_angles(tree: dict, order: int = 1) -> dict:
    """Angles of the axes of one order: where they leave their parent (insertion, degrees off the parent's
    direction) and how their far half lies (elevation above the horizontal)."""
    P, par, ax = tree["pos"], tree["parent"], tree["axis"]
    ins, elev = [], []
    for a in tree["axes"]:
        if a["order"] != order or "node" not in a:
            continue
        n0 = a["node"]
        if n0 >= len(P) or tree["order"][n0] != order:
            continue
        nodes = np.flatnonzero(ax == ax[n0])
        if len(nodes) < 2:
            continue
        p = par[n0]
        d_par = _norm(P[p] - P[par[p]]) if p > 0 else np.array([0, 0, 1.0])
        ins.append(math.degrees(math.acos(float(np.clip(_norm(P[n0] - P[p]) @ d_par, -1, 1)))))
        tip = nodes[-1]
        mid = nodes[len(nodes) // 2]
        d = _norm(P[tip] - P[mid]) if tip != mid else _norm(P[tip] - P[p])
        elev.append(math.degrees(math.asin(float(np.clip(d[2], -1, 1)))))
    q = lambda v: [round(float(x), 1) for x in np.percentile(v, [10, 50, 90])] if len(v) else []
    return {"n": len(ins), "insertion_p10_50_90": q(ins), "elevation_p10_50_90": q(elev)}


def traced_mask(polygon, size=None) -> np.ndarray:
    """A silhouette from an outline traced on the photo by eye (image px, closed): what to use when the tree fills
    the frame or stands against other trees."""
    from PIL import Image, ImageDraw
    P = np.asarray(polygon, float)
    lo = np.floor(P.min(0)).astype(int)
    w, h = (np.ceil(P.max(0)).astype(int) - lo + 1)
    im = Image.new("L", (int(w), int(h)), 0)
    ImageDraw.Draw(im).polygon([tuple(q) for q in (P - lo)], fill=255)
    return np.asarray(im) > 0


def reference_mask(image, crop=None, foot=None, tol=30.0, horizon=None, trunk=40, exclude=(), close=1, edge=0.03,
                   polygon=None) -> np.ndarray:
    """A tree's silhouette from a photo of it against the sky. A pixel is tree when its colour is more than `tol`
    from its row's background, read at the left and right edges of `crop` [x0, y0, x1, y1] (which must be sky there;
    the crop ends at the trunk's foot, x = `foot`). Below `horizon` (image y: where ground or far trees start) only
    +-`trunk` px round the foot count, against that band's own edges. `exclude` rectangles (image px) are dropped;
    the biggest piece is kept. Look at the mask before trusting its numbers."""
    from PIL import Image
    if polygon is not None:
        return traced_mask(polygon)
    im = np.asarray(Image.open(image).convert("RGB")).astype(np.float64)
    x0, y0, x1, y1 = crop
    reg = im[y0:y1, x0:x1]
    H, W = reg.shape[:2]

    def differs(a):
        k = max(2, int(edge * a.shape[1]))
        L, R = np.median(a[:, :k], axis=1), np.median(a[:, -k:], axis=1)
        L, R = ndimage.uniform_filter1d(L, 9, axis=0), ndimage.uniform_filter1d(R, 9, axis=0)
        t = np.linspace(0, 1, a.shape[1])[None, :, None]
        return np.linalg.norm(a - (L[:, None] * (1 - t) + R[:, None] * t), axis=2) > tol

    m = differs(reg)
    if horizon is not None and horizon < y1:
        h = max(int(horizon) - y0, 0)
        m[h:] = False
        c = int(foot) - x0
        a, b = max(c - 2 * trunk, 0), min(c + 2 * trunk, W)
        m[h:, a:b] = differs(reg[h:, a:b])
    for ex0, ey0, ex1, ey1 in exclude:
        m[max(ey0 - y0, 0): max(ey1 - y0, 0), max(ex0 - x0, 0): max(ex1 - x0, 0)] = False
    if close:
        m = ndimage.binary_closing(m, iterations=int(close))
    lab, n = ndimage.label(m, structure=np.ones((3, 3)))
    if n:
        sizes = np.bincount(lab.ravel())
        sizes[0] = 0
        m = lab == int(np.argmax(sizes))
    return m


def line_directions(gray: np.ndarray, region: np.ndarray, sigma: float = 1.5, rho: float = 5.0) -> dict:
    """Which way the lines in an image run (branches against the sky, or our own silhouette), as angles from the
    vertical (0 = upright, 90 = level): structure tensor, weighted by how line-like and how strong each pixel is,
    inside `region`. Returns p25/p50/p75 and the share steeper than 30 deg / flatter than 60 deg. The same measure
    on a winter photo and on a bare silhouette at the same pixel scale compares branch angles without tracing."""
    g = np.asarray(gray, float)
    gx = ndimage.gaussian_filter(g, sigma, order=(0, 1))
    gy = ndimage.gaussian_filter(g, sigma, order=(1, 0))
    jxx, jyy, jxy = (ndimage.gaussian_filter(v, rho) for v in (gx * gx, gy * gy, gx * gy))
    tr = jxx + jyy
    coh = np.sqrt((jxx - jyy) ** 2 + 4 * jxy ** 2) / np.maximum(tr, 1e-12)
    th = 0.5 * np.arctan2(2 * jxy, jxx - jyy)  # the gradient's direction; the line runs across it
    ang = np.degrees(np.abs(np.arctan2(np.sin(th), np.cos(th))))  # gradient from the x axis
    ang = np.where(ang > 90, 180 - ang, ang)  # gradient level (0) = an upright line: already "from the vertical"
    w = (coh * tr)[region]
    a = ang[region]
    if w.sum() <= 0:
        return {"p25": 0.0, "p50": 0.0, "p75": 0.0, "upright": 0.0, "level": 0.0}
    o = np.argsort(a)
    cw = np.cumsum(w[o]) / w.sum()
    q = lambda f: float(a[o][min(np.searchsorted(cw, f), len(a) - 1)])
    return {"p25": round(q(0.25), 1), "p50": round(q(0.5), 1), "p75": round(q(0.75), 1),
            "upright": round(float(w[a < 30].sum() / w.sum()), 3), "level": round(float(w[a > 60].sum() / w.sum()), 3)}


def _filled(mask):
    any_, left, right = _rows(mask)
    f = np.zeros_like(mask)
    for i in np.flatnonzero(any_):
        f[i, left[i]: right[i] + 1] = True
    return f


def photo_branch_directions(image, mask_args: dict, crown_from: float = 0.3) -> dict:
    """line_directions of a winter photo inside the tree's outline, above `crown_from` of its height (off the trunk)."""
    from PIL import Image
    R = reference_mask(image, **mask_args)
    im = np.asarray(Image.open(image).convert("L")).astype(float)
    if mask_args.get("polygon") is not None:
        P = np.asarray(mask_args["polygon"])
        x0, y0 = int(np.floor(P[:, 0].min())), int(np.floor(P[:, 1].min()))
    else:
        x0, y0 = mask_args["crop"][0], mask_args["crop"][1]
    g = im[y0: y0 + R.shape[0], x0: x0 + R.shape[1]]
    reg = _filled(R)[: g.shape[0], : g.shape[1]]
    rows = np.flatnonzero(reg.any(1))
    reg[int(rows[-1] - crown_from * (rows[-1] - rows[0])):] = False
    out = line_directions(g, reg)
    out["height_px"] = int(rows[-1] - rows[0])
    return out


def tree_branch_directions(tree: dict, azimuth: float, height_px: int, crown_from: float = 0.3) -> dict:
    """The same measure on our bare silhouette, drawn as tall in pixels as the photo's tree."""
    m, _ = silhouette(tree, azimuth, height_px / max(tree["height"], 1e-6), leaves=False)
    reg = _filled(m)
    rows = np.flatnonzero(reg.any(1))
    reg[int(rows[-1] - crown_from * (rows[-1] - rows[0])):] = False
    return line_directions(255.0 * (~m), reg)
