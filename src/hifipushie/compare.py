"""Compare model silhouettes against reference images: overlap score, diff image, edge table."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image
from scipy import ndimage, signal


def reference_mask(path: str, flip: bool = False, threshold: float = 40.0) -> np.ndarray:
    """Foreground mask from alpha if present, else by distance from the corner background colour."""
    im = Image.open(path)
    if im.mode in ("RGBA", "LA") or "transparency" in im.info:
        a = np.asarray(im.convert("RGBA"))[..., 3]
        mask = a > 127
    else:
        rgb = np.asarray(im.convert("RGB")).astype(float)
        corners = np.array([rgb[0, 0], rgb[0, -1], rgb[-1, 0], rgb[-1, -1]])
        bg = np.median(corners, axis=0)
        mask = np.linalg.norm(rgb - bg, axis=-1) > threshold
    if flip:
        mask = mask[:, ::-1]
    return mask


def _crop(mask: np.ndarray) -> np.ndarray:
    rows, cols = np.where(mask)
    if not len(rows):
        raise ValueError("empty mask")
    return mask[rows.min():rows.max() + 1, cols.min():cols.max() + 1]


def _resize(mask: np.ndarray, h: int, w: int) -> np.ndarray:
    im = Image.fromarray(mask.astype(np.uint8) * 255).resize((max(w, 1), max(h, 1)), Image.BILINEAR)
    return np.asarray(im) > 127


def _place(r: np.ndarray, s: float, cy: float, cx: float, shape) -> np.ndarray:
    """Scale mask r by s and paste it so its centroid lands at (cy, cx) on a canvas of shape."""
    rs = _resize(r, round(r.shape[0] * s), round(r.shape[1] * s))
    ry, rx = (c.mean() for c in np.where(rs))
    oy, ox = round(cy - ry), round(cx - rx)
    out = np.zeros(shape, bool)
    y0, x0 = max(oy, 0), max(ox, 0)
    y1, x1 = min(oy + rs.shape[0], shape[0]), min(ox + rs.shape[1], shape[1])
    if y1 > y0 and x1 > x0:
        out[y0:y1, x0:x1] = rs[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
    return out


def _iou(a, b) -> float:
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 0.0


def align(M: np.ndarray, r: np.ndarray, fit: str):
    """Where reference mask r goes on model canvas M, as (row0, col0, scale): r's pixel edge (0, 0) lands on
    canvas position (row0, col0) and each r pixel spans `scale` canvas pixels. fit="auto" searches scale and
    offset for the best overlap (compares shape only); "height"/"width" match that bounding-box dimension,
    bottom-aligned."""
    rows, cols = np.where(M)
    if fit in ("height", "width"):
        s = (np.ptp(rows) + 1) / r.shape[0] if fit == "height" else (np.ptp(cols) + 1) / r.shape[1]
        return rows.max() + 1 - r.shape[0] * s, (cols.min() + cols.max() + 1) / 2 - r.shape[1] * s / 2, s
    s0 = float(np.sqrt(M.sum() / r.sum()))
    cy, cx = rows.mean(), cols.mean()
    reach = max(M.shape) // 6

    def best_at(s):
        """Best integer shift at scale s: one FFT correlation gives the overlap for every shift at once."""
        R = _place(r, s, cy, cx, M.shape)
        inter = signal.fftconvolve(M.astype(float), R[::-1, ::-1].astype(float), mode="full")
        h, w = M.shape
        inter = np.rint(inter[h - 1 - reach:h + reach, w - 1 - reach:w + reach])
        iou = inter / (M.sum() + R.sum() - inter)
        dy, dx = np.unravel_index(iou.argmax(), iou.shape)
        return float(iou[dy, dx]), s, int(dy) - reach, int(dx) - reach

    best = max((best_at(s) for s in s0 * np.linspace(0.85, 1.15, 31)), key=lambda b: b[0])
    best = max((best_at(s) for s in best[1] * np.linspace(0.99, 1.01, 9)), key=lambda b: b[0])
    _, s, dy, dx = best
    rs = _resize(r, round(r.shape[0] * s), round(r.shape[1] * s))  # as _place pasted it
    ry, rx = (c.mean() for c in np.where(rs))
    return round(cy - ry) + dy, round(cx - rx) + dx, rs.shape[0] / r.shape[0]


@dataclass
class Placement:
    """A reference mask placed on a model's silhouette canvas. Canvas pixel (row, col) sits at world
    u = u0 + col*px, v = v1 - row*px; `ref` is the full-resolution reference (cropped to its bounding box),
    its pixel edge (0, 0) at canvas position (row0, col0), each of its pixels `scale` canvas pixels wide."""
    M: np.ndarray  # model silhouette on the canvas
    R: np.ndarray  # reference point-sampled at the canvas pixel centres
    u0: float
    v1: float
    px: float
    ref: np.ndarray
    row0: float
    col0: float
    scale: float

    def ref_px(self, uv: np.ndarray) -> np.ndarray:
        """World (u, v) points -> (row, col) coordinates in `ref`, for ndimage.map_coordinates."""
        row, col = (self.v1 - uv[..., 1]) / self.px, (uv[..., 0] - self.u0) / self.px
        return np.stack([(row + 0.5 - self.row0) / self.scale - 0.5, (col + 0.5 - self.col0) / self.scale - 0.5])


def place(model: dict, ref: np.ndarray, fit: str = "auto", world=None) -> Placement:
    """Put the reference on the model's silhouette canvas (padded by a third on each side).
    model: {"mask", "u": (u0,u1), "v": (v0,v1)} from sdf.silhouettes. world = (u0, v1, px): the reference
    already has world coordinates (a plan): its pixel (row, col) edge sits at u0 + col*px, v1 - row*px, and it
    is placed exactly there (fit is ignored)."""
    m = model["mask"]
    u0, u1 = model["u"]
    v0, v1 = model["v"]
    px = (u1 - u0) / (m.shape[1] - 1)
    pad = max(m.shape) // 3
    M = np.pad(m, pad)
    crop = _crop(ref)
    if world is not None:
        rr, cc = np.where(ref)
        U, V = world[0] + cc.min() * world[2], world[1] - rr.min() * world[2]
        cu0, cv1 = u0 - pad * px, v1 + pad * px
        p = Placement(M, M, cu0, cv1, px, crop, (cv1 - V) / px + 0.5, (U - cu0) / px + 0.5, world[2] / px)
        fit = "world"
    else:
        p = Placement(M, M, u0 - pad * px, v1 + pad * px, px, crop, *align(M, crop, fit))
    rows, cols = np.indices(M.shape)
    uv = np.stack([p.u0 + cols * px, p.v1 - rows * px], -1)
    img = crop.astype(np.uint8)

    def sample(row0, col0, scale):
        p.row0, p.col0, p.scale = row0, col0, scale
        return ndimage.map_coordinates(img, p.ref_px(uv), order=0, cval=0) > 0

    best = (_iou(M, sample(p.row0, p.col0, p.scale)), p.row0, p.col0, p.scale)
    if fit == "auto":
        # align() works in whole pixels; at typical resolutions half a pixel along the whole outline is worth
        # several points of IoU, so hill-climb in quarter pixels and 0.25% scale steps.
        for _ in range(40):
            _, r0, c0, s = best
            cands = [(r0 + 0.25, c0, s), (r0 - 0.25, c0, s), (r0, c0 + 0.25, s), (r0, c0 - 0.25, s),
                     (r0, c0, s * 1.0025), (r0, c0, s / 1.0025)]
            top = max(((_iou(M, sample(*c)), *c) for c in cands), key=lambda t: t[0])
            if top[0] <= best[0]:
                break
            best = top
    p.R = sample(*best[1:])
    return p


def diff_image(M: np.ndarray, R: np.ndarray, width: int = 480):
    """Grey = both, red = model only, blue = reference only; cropped to the union.
    Returns (image, crop box (row0, row1, col0, col1))."""
    rows, cols = np.where(M | R)
    y0, y1, x0, x1 = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
    Mc, Rc = M[y0:y1, x0:x1], R[y0:y1, x0:x1]
    img = np.full(Mc.shape + (3,), 30, np.uint8)
    img[Mc & Rc] = (170, 170, 175)
    img[Mc & ~Rc] = (230, 70, 60)   # model has extra
    img[~Mc & Rc] = (60, 130, 240)  # model is missing
    k = width / max(Mc.shape)
    im = Image.fromarray(img).resize((round(Mc.shape[1] * k), round(Mc.shape[0] * k)), Image.NEAREST)
    return im, (y0, y1, x0, x1)


def compare(model: dict, ref: np.ndarray, fit: str = "auto", bands: int = 12, world=None):
    """model: {"mask", "u": (u0,u1), "v": (v0,v1)} from sdf.silhouettes (world extents of the mask).
    Returns (iou, diff_image, report_text). Band errors are in world units."""
    p = place(model, ref, fit, world)
    fit = "world (exact)" if world is not None else fit
    M, R, u0, v1, px = p.M, p.R, p.u0, p.v1, p.px
    iou = _iou(M, R)
    diff, (y0, y1, x0, x1) = diff_image(M, R)
    Mc, Rc = M[y0:y1, x0:x1], R[y0:y1, x0:x1]

    wu = lambda c: u0 + (c + x0) * px  # noqa: E731
    wv = lambda r: v1 - (r + y0) * px  # noqa: E731
    ref_h = (np.ptp(np.where(R)[0]) + 1) * px

    def edges(a, axis):
        idx = np.where(a.any(axis=axis))[0]
        return (idx.min(), idx.max()) if len(idx) else None

    ch, cw = Mc.shape
    lines = [f"IoU {iou:.3f}  (grey match, red = model has extra, blue = model is missing)",
             f"alignment: fit={fit}; the reference, as placed, is {ref_h:.3f} tall in world units",
             "Horizontal bands (top→bottom): v range | model u-extent | ref u-extent | edge errors (+ = model sticks out)"]
    for i in range(bands):
        a, b = i * ch // bands, (i + 1) * ch // bands
        me, re = edges(Mc[a:b], 0), edges(Rc[a:b], 0)
        if not me and not re:
            continue
        fmt = lambda e: f"[{wu(e[0]):+.3f},{wu(e[1]):+.3f}]" if e else "     (none)     "  # noqa: E731
        err = f"lo {(re[0] - me[0]) * px:+.3f}  hi {(me[1] - re[1]) * px:+.3f}" if me and re else ""
        lines.append(f"  v {wv(b):.3f}..{wv(a):.3f} | {fmt(me)} | {fmt(re)} | {err}")
    lines.append("Vertical bands (left→right): u range | model v-extent | ref v-extent | edge errors (+ = model sticks out)")
    for i in range(bands):
        a, b = i * cw // bands, (i + 1) * cw // bands
        me, re = edges(Mc[:, a:b], 1), edges(Rc[:, a:b], 1)
        if not me and not re:
            continue
        fmt = lambda e: f"[{wv(e[1]):+.3f},{wv(e[0]):+.3f}]" if e else "     (none)     "  # noqa: E731
        err = f"bottom {(me[1] - re[1]) * px:+.3f}  top {(re[0] - me[0]) * px:+.3f}" if me and re else ""
        lines.append(f"  u {wu(a):+.3f}..{wu(b):+.3f} | {fmt(me)} | {fmt(re)} | {err}")
    return iou, diff, "\n".join(lines)
