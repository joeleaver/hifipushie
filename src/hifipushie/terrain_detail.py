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


# rolling ground by kind: (undulation m, its scale m, swale depth m, hummock height m)
GROUND = {"hills": (1.8, 110, 0.9, 0.25), "farmland": (1.1, 90, 0.6, 0.18), "moor": (1.4, 120, 0.8, 0.45),
          "coast": (1.0, 90, 0.6, 0.3), "alpine valley": (1.2, 110, 0.7, 0.4), "cirque": (1.0, 90, 0.6, 0.45),
          "canyon": (0.6, 90, 0.4, 0.2), "plateau": (0.9, 120, 0.5, 0.25), "crater": (1.0, 100, 0.6, 0.3),
          "dunes": (0.0, 100, 0.0, 0.0)}


def _swales(T, H, sc):
    """0..1: the hollows water gathers in on this ground, from a catchment of ~(0.3 sc)^2 up to full depth at ~(2 sc)^2,
    broadened to 20-40 m wide U-shaped troughs (on a coarser grid; D8 on the ground smoothed a little)."""
    from .terrain import _accumulate, _receivers, smoothstep
    f = max(1, int(round(4.0 / T.cell)))
    c = T.cell * f
    Hc = ndimage.gaussian_filter(H, max(1.0, 6.0 / T.cell))[::f, ::f]
    base = np.zeros(Hc.shape, bool)
    base[[0, -1], :] = base[:, [0, -1]] = True
    wet = ~np.isnan(T.water)[::f, ::f]
    rec, _, levels = _receivers(Hc, c, base | wet)
    area = _accumulate(rec, levels, c).reshape(Hc.shape)
    a0, a1 = (0.3 * sc) ** 2, (2.0 * sc) ** 2
    line = smoothstep(math.log(a0), math.log(a1), np.log(area))
    width = max(1.0, 8.0 / c)
    line = ndimage.grey_dilation(line, size=int(2 * width) | 1)
    line = ndimage.gaussian_filter(line, max(1.0, 7.0 / c))
    line = np.where(wet, 0, line)
    up = ndimage.zoom(line, (H.shape[0] / line.shape[0], H.shape[1] / line.shape[1]), order=1)
    out = np.zeros(H.shape)
    out[:up.shape[0], :up.shape[1]] = up[:H.shape[0], :H.shape[1]]
    return np.clip(out, 0, 1)


def _sightlines(T):
    """0..1 corridors (~8 m wide) along the intent's sight lines (from -> each target it must see): ground texture
    stays off them."""
    from scipy.spatial import cKDTree
    m = np.zeros(T.X.shape)
    for it in (T.spec.get("intent") or {}).values():
        if not isinstance(it, dict) or "from" not in it or "see" not in it:
            continue
        try:
            a = T.address(it["from"])[0]
            tg = [T.address(t["at"] if isinstance(t, dict) else t)[0] for t in it["see"]]
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
        for b in tg:
            n = max(2, int(np.linalg.norm(b - a) / max(T.cell, 1.0)))
            seg = a + (b - a) * np.linspace(0, 1, n)[:, None]
            d, _ = cKDTree(seg).query(T.P, distance_upper_bound=8.0)
            m = np.maximum(m, (np.isfinite(d) & (d < 4.0)).reshape(T.X.shape).astype(float))
    return m


def ground(T):
    """Player-scale texture on gentle ground, after erosion (which smoothed any): field-scale undulation (1-2 m over
    ~100 m), swales (shallow hollows a few tens of metres wide running down the slope, where water gathers) and hummocks
    in patches. Hill country had read as plaster-smooth tilted planes. Never on sites, routes, passes, water or their
    shoulders; hollows it makes deeper than ~0.6 m are filled back (it mustn't make ponds).
    "ground": {"undulation": 0..2, "swales": 0..2, "hummocks": 0..2, "scale": m} | false (defaults 1, by the kind)."""
    from . import noise
    from .terrain import smoothstep
    cfg = T.spec.get("ground", {})
    if cfg is False:
        T.ground_rms = None
        return
    cfg = cfg or {}
    kind = T.world.get("kind") or "hills"
    base = next((v for k, v in GROUND.items() if k in str(kind)), GROUND["hills"])
    und, sc, sw, hu = base
    sc = float(cfg.get("scale", sc))
    und *= float(cfg.get("undulation", 1.0))
    sw *= float(cfg.get("swales", 1.0))
    hu *= float(cfg.get("hummocks", 1.0))
    H = T.H
    before = H.copy()
    Hs = ndimage.gaussian_filter(H, max(1.0, 8.0 / T.cell))
    gy, gx = np.gradient(Hs, T.cell)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    keep = np.zeros(H.shape)
    for k in ("routes", "sites", "earthworks"):
        if k in T.masks:
            keep = np.maximum(keep, np.clip(T.masks[k], 0, 1))
    for p in T.passes.values():
        keep = np.maximum(keep, p["corridor"].astype(float))
    wet = ~np.isnan(T.water)
    keep = np.maximum(keep, wet.astype(float))
    keep = np.maximum(keep, _sightlines(T))  # (a 1 m hummock blocked a disc golf line the designer had checked)
    reach = max(2.0, 12.0 / T.cell)
    keep = np.clip(ndimage.maximum_filter(keep, size=int(2 * reach) | 1), 0, 1)
    keep = ndimage.gaussian_filter(keep, reach / 2)
    w = smoothstep(24, 12, slope) * (1 - np.clip(1.5 * keep, 0, 1))
    if w.max() < 0.05 or und + sw + hu <= 0:
        T.ground_rms = None
        return
    P = T.P
    z = np.zeros(len(P))
    # a size spectrum, big first: a few broad swells, field-scale undulation, then little (an even mid-size dimpling read
    # as orange peel from the air)
    n0 = noise.fbm(np.c_[P, z + 30.0], 2.5 * sc, 2, seed=300)
    n1 = noise.fbm(np.c_[P, z + 31.0], sc, 2, seed=301)
    n2 = noise.fbm(np.c_[P, z + 32.0], 0.4 * sc, 2, seed=302)
    add = und * (1.3 * 2 * (n0 - 0.5) + 0.8 * 2 * (n1 - 0.5) + 0.25 * 2 * (n2 - 0.5))
    add = add.reshape(H.shape)
    swl = np.zeros(H.shape)
    if sw > 0:  # swales: broad shallow hollows where the water gathers, from the drainage of the undulating ground
        # (noise stretched along the fall line seamed along every divide and valley bottom: grooves like contours)
        swl = _swales(T, H + w * add, sc)
        add = add - sw * swl
    # hummocks: small rounded lumps in a few patches, on the drier gentle ground (not in the swales, not on slopes)
    patch = smoothstep(0.55, 0.7, noise.fbm(np.c_[P, z + 34.0], 1.2 * sc, 2, seed=304)).reshape(H.shape)
    hm = noise.fbm(np.c_[P, z + 35.0], max(7.0, 3 * T.cell), 2, seed=305).reshape(H.shape)
    add = add + hu * patch * (1 - swl) * smoothstep(12, 4, slope) * 2 * np.clip(hm - 0.45, 0, None) * 2
    H = H + w * add
    # hollows the texture made (deeper than what was there, by over 0.6 m): filled back to 0.6 m
    from skimage.morphology import reconstruction
    def depth(A):
        s = A.copy()
        s[1:-1, 1:-1] = A.max()
        return reconstruction(s, A, method="erosion") - A
    extra = depth(H) - depth(before)
    H = H + np.clip(extra - 0.6, 0, None) * (w > 0.02)
    T.H = H
    # measured: the gentle ground's relief about its ~200 m trend (plaster-smooth ground is ~0.1-0.2 m)
    m = (w > 0.5) & ~wet
    trend = ndimage.gaussian_filter(H, 25.0 / T.cell)
    T.ground_rms = float(np.sqrt(np.mean((H - trend)[m] ** 2))) if m.sum() > 50 else None
    T.ground_before = float(np.sqrt(np.mean((before - ndimage.gaussian_filter(before, 25.0 / T.cell))[m] ** 2))) \
        if m.sum() > 50 else None


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
