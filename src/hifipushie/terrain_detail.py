"""Finer cells for the last stages of a build. A 70 deg face is only 2-3 cells across in plan at the default cell
(a sea cliff 10 m high on a 2 m grid is 2 cells), so it can't carry detail of its own: it rendered as a soft vertical
drape. The large-scale work (base, sea, sites, routes, erosion) runs at the spec's cell; then every grid on the terrain
is resampled `detail` times finer, the sea cliffs are re-cut on the fine grid from their continuous signed distance
(the face's plane and its lip), and rock character, the checks, lakes and cover run at the fine cell. The export and
the views get the fine grid.

"detail": "auto" (default: 2 where the frame has sea cliffs or rock faces under 3 cells across, while the fine grid
stays under ~1100 cells a side) | 1 (off) | 2 | 3 | 4.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

MAX_SIDE = 1100


def factor(T) -> int:
    want = T.spec.get("detail", "auto")
    side = max(len(T.xs), len(T.ys))
    if want != "auto":
        return max(1, int(want))
    if (side - 1) * 2 + 1 > MAX_SIDE:
        return 1
    S = getattr(T, "sea", None)
    if S and (S["wc"] > 0.5).any():
        return 2
    slope = T._slope()
    cliff = (slope > 60) & np.isnan(T.water)
    if cliff.sum() > 50 and np.median(2 * ndimage.distance_transform_edt(cliff)[cliff]) < 3:
        return 2
    return 1


def _walk(obj, fn, depth=0):
    """Apply fn to every grid-shaped array held (in dicts, lists, object attributes), in place where they're held."""
    if depth > 4:
        return obj
    if isinstance(obj, np.ndarray):
        return fn(obj)
    if isinstance(obj, dict):
        for k in list(obj):
            obj[k] = _walk(obj[k], fn, depth + 1)
        return obj
    if isinstance(obj, list):
        for i in range(len(obj)):
            obj[i] = _walk(obj[i], fn, depth + 1)
        return obj
    if isinstance(obj, tuple):
        return tuple(_walk(v, fn, depth + 1) for v in obj)
    return obj


def refine(T, f: int):
    """Resample every grid on T `f` times finer (heights cubic within their neighbours' range, fractions linear, masks
    and ids nearest, water nearest: the lakes are re-filled later), and move T to the fine grid."""
    if f <= 1:
        return
    shape = T.X.shape
    c = T.cell
    cf = c / f
    xs = np.arange(T.xs[0], T.xs[-1] + cf / 2, cf)
    ys = np.arange(T.ys[0], T.ys[-1] + cf / 2, cf)
    GY, GX = np.meshgrid((ys - T.ys[0]) / c, (xs - T.xs[0]) / c, indexing="ij")
    coords = [GY, GX]

    def up(a, cubic=False):
        if not isinstance(a, np.ndarray) or a.shape != shape:
            return a
        if a.dtype == bool:
            return ndimage.map_coordinates(a.astype(np.uint8), coords, order=0, mode="nearest").astype(bool)
        if not np.issubdtype(a.dtype, np.floating):
            return ndimage.map_coordinates(a, coords, order=0, mode="nearest").astype(a.dtype)
        if np.isnan(a).any():
            return ndimage.map_coordinates(a, coords, order=0, mode="nearest")
        if cubic:
            lo = ndimage.map_coordinates(ndimage.minimum_filter(a, size=2, origin=-1), [np.floor(GY), np.floor(GX)], order=0,
                                         mode="nearest")
            hi = ndimage.map_coordinates(ndimage.maximum_filter(a, size=2, origin=-1), [np.floor(GY), np.floor(GX)], order=0,
                                         mode="nearest")
            return np.clip(ndimage.map_coordinates(a, coords, order=3, mode="nearest"), lo, hi)
        return ndimage.map_coordinates(a, coords, order=1, mode="nearest")

    skip = {"X", "Y", "P", "xs", "ys", "source", "spec"}
    for k, v in list(vars(T).items()):
        if k in skip:
            continue
        if k in ("H", "H0"):
            setattr(T, k, up(v, cubic=True))
            continue
        setattr(T, k, _walk(v, up))
    T.xs, T.ys = xs, ys
    T.X, T.Y = np.meshgrid(xs, ys)
    T.P = np.stack([T.X.ravel(), T.Y.ravel()], 1)
    T.cell = cf
    T.detail = {"factor": f, "cell": c}
    from . import terrain_sea
    terrain_sea.recut(T)
