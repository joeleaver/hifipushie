"""Cover: the spec's cover, colours, tree kinds, the profile's zones, `cover`, `trees`. Part of the terrain design layer (terrain_design.py has the overview)."""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from . import terrain_design
from . import noise
from .terrain import smoothstep
from .terrain_design import region

# ---------------------------------------------------------------- cover
def _spec_cover(T, name):
    c = (T.spec.get("cover") or {})[name]
    base = terrain_design.COVER_TYPES.get(c.get("type", name), {})
    return {**base, **c}


def cover_colour(T, name):
    c = _spec_cover(T, name)
    col = c.get("color", [0.5, 0.5, 0.5])
    if isinstance(col, str):
        col = [int(col[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return col


def tree_kind(T, name):
    return _spec_cover(T, name).get("trees")


def _profile_zones(T):
    """A profiled wall's bands re-cut on the ground as built: the vegetated bands' edges follow the ground's form (scree
    runs down the gullies and its fans below the cliffs, forest climbs the ribs between them), not a level line round
    the wall (bands cut on the profile alone were ruled stripes)."""
    for b in getattr(T, "basins", {}).values():
        tp, zt = b.get("t_prof"), b.get("_zones_t")
        if tp is None or not zt:
            continue
        # the ground's form across the slope at a gully's size: + in hollows, - on ribs
        sig = max(1.0, 25.0 / T.cell)
        lap = ndimage.gaussian_laplace(T.H, sig) * sig ** 2
        form = np.clip(lap / max(float(np.percentile(np.abs(lap[b["wall"]]), 90)), 1e-6), -1, 1) if b["wall"].any() \
            else np.zeros(T.X.shape)
        rag = noise.fbm(np.c_[T.P, np.full(len(T.P), 44.0)], max(40.0 * T.k, 6 * T.cell), 2, seed=351).reshape(T.X.shape)
        t = np.nan_to_num(tp, nan=-1.0)
        tz = t + (0.09 * form + 0.04 * (2 * rag - 1)) * np.sin(np.pi * np.clip(t, 0, 1))
        rocky = {"cliffs", "crags", "slabs"}
        hard = np.zeros(T.X.shape, bool)
        for kind, (t0, t1) in zt.items():
            if kind in rocky:
                hard |= (t >= t0) & (t < t1 + (1 if t1 >= 1 else 0))
        z = {}
        for kind, (t0, t1) in zt.items():
            top = t1 + (1 if t1 >= 1 else 0)
            z[kind] = b["wall"] & ((t >= t0) & (t < top) if kind in rocky else (tz >= t0) & (tz < top) & ~hard)
        # the scree fans below the cliffs (the rock pass's aprons) are scree whichever band they lie in
        ap = (getattr(T, "rock", None) or {}).get("aprons")
        if "scree" in z and ap is not None and ap.shape == T.X.shape:
            fan = ndimage.binary_dilation(ap, iterations=2) & b["wall"] & ~hard
            for kind in z:
                if kind not in rocky and kind != "scree":
                    z[kind] &= ~fan
            z["scree"] |= fan
        b["zones"] = z


def _profile_cover(T):
    """Basin walls described from the top down ("cliffs, scree, forest") get that cover in each band, unless the spec
    already covers the band (a layer "in" it): layers "<basin>_<band>", painted after the broad layers (before snow).
    Returns the bare bands' mask (cliffs, crags, slabs, scree), where the spec's own tree layers don't grow."""
    bare, add = None, {}
    _profile_zones(T)
    cover = T.spec.setdefault("cover", {}) if isinstance(T.spec.get("cover", {}), dict) else T.spec["cover"]
    used = {str(c.get("in")) for c in cover.values() if isinstance(c, dict)}
    for bn, b in getattr(T, "basins", {}).items():
        for kind, z in (b.get("zones") or {}).items():
            if kind in ("cliffs", "crags", "slabs", "scree"):
                zz = np.clip(ndimage.gaussian_filter(z.astype(float), 1.0) * 1.3, 0, 1)
                bare = zz if bare is None else np.maximum(bare, zz)
            key = f"{bn}_{kind}"
            if f"{bn}.{kind}" not in used and key not in cover:
                add[key] = {**terrain_design.PROFILE_COVER[kind], "in": f"{bn}.{kind}", "_auto": True}
    for fn, F in getattr(T, "features", {}).items():  # hedges and lines of trees: their green on the ground
        if F.get("cover") and F.get("pieces") and fn not in cover:
            add[fn] = {"type": "hedge", "in": fn, "slope": [0, 90], "color": F["cover"], "_auto": True, "_line": True}
    if add:
        names = list(cover)
        snow = [i for i, n in enumerate(names) if (cover[n] or {}).get("type", n) == "snow"]
        at = (snow[0] - 0.5) if snow else len(names)
        for i, (k, v) in enumerate(add.items()):
            cover[k] = {**v, "order": (len(names) + 1 if v.get("_line") else at) + 0.01 * i}
        T.auto_cover = list(add)
    return bare


def cover(T) -> dict:
    out = {}
    # slope of the ground smoothed over a cell, its thresholds shifted by noise a few cells across: cut on the raw
    # slope, rock and snow speckled cell by cell and every boundary was a hard pasted line along one contour of slope
    pts = np.c_[T.P, np.zeros(len(T.P))]
    jit = 2 * noise.fbm(pts, max(3 * T.cell, 25.0), 3, seed=47).reshape(T.X.shape) - 1
    slope = T._slope(ndimage.gaussian_filter(T.H, 1.0)) + 6.0 * jit
    ledges = (getattr(T, "rock", None) or {}).get("ledges")
    if ledges is not None and ledges.any():  # a ledge a few cells wide between risers is flat ground: grass holds on it
        slope = np.where(ledges, np.minimum(slope, T._slope() + 4.0 * jit), slope)  # (smoothed, it read as the face)
    elev_j = jit * max(4 * T.cell, 20.0)
    bare = _profile_cover(T)
    layers = list(T.spec.get("cover") or {})
    # painted in key order, or by each layer's "order" (a patch can't reorder keys: scree had to be deleted and re-added
    # to paint after rock)
    pos = {n: i for i, n in enumerate(layers)}
    layers.sort(key=lambda n: (float((T.spec["cover"][n] or {}).get("order", pos[n])), pos[n]))
    for k, name in enumerate(layers):
        c = _spec_cover(T, name)
        m = np.full(T.X.shape, float(c.get("density", 1.0)))
        if "in" in c:
            m *= region(T, c["in"])
        lo, hi = c.get("slope", [0, 90])
        m *= smoothstep(lo - 4, lo + 4, slope) if lo > 0 else 1
        m *= smoothstep(hi + 4, hi - 4, slope) if hi < 90 else 1
        if "elevation" in c:
            lo, hi = c["elevation"]
            fade = c.get("fade", 40)
            Hj = T.H + elev_j * min(1.0, fade / 40)
            m *= smoothstep(lo - fade, lo + fade, Hj) * smoothstep(hi + fade, hi - fade, Hj)
        if "gradient" in c:
            g = c["gradient"]
            a, b = T.address(g["from"])[0], T.address(g["to"])[0]
            ax = b - a
            u = np.clip(((T.P - a) @ ax) / (ax @ ax), 0, 1).reshape(T.X.shape)
            v0, v1 = g.get("range", [0, 1])
            m *= v0 + (v1 - v0) * u
        if "near" in c:
            what, within = c["near"]["what"], c["near"].get("within", 50)
            if what == "water":
                d = ndimage.distance_transform_edt(np.isnan(T.water)) * T.cell
            else:
                xy = T.address(what)[0]
                d = np.hypot(T.X - xy[0], T.Y - xy[1])
            m *= smoothstep(within, within * 0.6, d)
        if c.get("rows"):  # an orchard or plantation: trees in rows `rows` metres apart, along contours or an axis
            along = c.get("along", "contour")
            if along == "contour":
                u = T.H / max(float(np.mean(np.hypot(*np.gradient(T.H, T.cell)))) + 1e-3, 1e-3)  # ~distance across the slope
            else:
                ang = math.radians({"east": 90, "west": 90, "north": 0, "south": 0}.get(along, float(along) if
                                   isinstance(along, (int, float)) else 0))
                u = T.X * math.cos(ang) - T.Y * math.sin(ang)
            m *= smoothstep(0.55, 0.85, 0.5 + 0.5 * np.cos(2 * np.pi * u / float(c["rows"])))
        br = c.get("breakup")
        if br and br.get("amount"):
            user = ((T.spec.get("cover") or {})[name].get("breakup") or {}).get("scale")
            sc = user if user else br.get("scale", 100) * T.k  # the type defaults are landscape-scale
            n = noise.fbm(pts, sc, 3, seed=41 + k).reshape(T.X.shape)
            m *= np.clip(1 + br["amount"] * 4 * (n - 0.5), 0, 1)
        if not c.get("under_water") and "water" not in c.get("avoid", []):
            m *= np.isnan(T.water)  # nothing grows under water unless asked ("under_water": true)
        for a in c.get("avoid", []):
            if a == "water":
                wet = ~np.isnan(T.water)
                m *= smoothstep(0, 3 * T.cell, ndimage.distance_transform_edt(~wet) * T.cell) if wet.any() else 1
            elif a in ("routes", "sites"):
                if a in T.masks:
                    m *= 1 - T.masks[a]
            else:
                m *= 1 - region(T, a)
        if bare is not None and c.get("trees") and not c.get("_auto"):  # a wall profiled "cliffs, scree, forest":
            m *= 1 - bare  # trees only in its forest band
        m = np.clip(m, 0, 1)
        if c.get("count") and c.get("trees"):  # "a few trees": scale the density so about this many stand
            expect = m.sum() * T.cell ** 2 * terrain_design.TREES_PER_M2
            if expect > 0:
                m = np.clip(m * c["count"] / expect, 0, 1)
        out[name] = m
    return out


def trees(T, limit=250_000):
    """Tree instances (x, y, z, kind, layer) for every tree layer: a jittered grid a tree apart, each point kept with
    the mask's probability; an orchard's points sit on its rows (so rows read as rows, in the preview and the engine)."""
    rng = np.random.default_rng(11)
    out = []
    (x0, y0), (x1, y1) = T.spec["extent"]
    for li, (name, m) in enumerate(T.cover.items()):
        c = _spec_cover(T, name)
        kind = c.get("trees")
        if not kind or m.max() <= 0:
            continue
        if c.get("rows"):
            step = float(c.get("spacing", c["rows"]))
            gx, gy = np.meshgrid(np.arange(x0, x1, step / 2), np.arange(y0, y1, step / 2))
            pts = np.stack([gx.ravel(), gy.ravel()], 1) + rng.normal(0, 0.15, (gx.size, 2))
            keep = T.sample(pts, m) > 0.75  # on the rows' centres only
        else:
            step = 1 / math.sqrt(terrain_design.TREES_PER_M2)
            gx, gy = np.meshgrid(np.arange(x0, x1, step), np.arange(y0, y1, step))
            pts = np.stack([gx.ravel(), gy.ravel()], 1) + rng.uniform(-0.45, 0.45, (gx.size, 2)) * step
            keep = rng.random(len(pts)) < T.sample(pts, m)
        pts = pts[keep]
        out.append(np.c_[pts, T.sample(pts), np.full(len(pts), li)])
        T.tree_layers = getattr(T, "tree_layers", {}) | {li: (name, kind)}
    lt = []
    if getattr(T, "features", None):  # shrubs along hedges, trees standing out of them and lining treelines
        from .terrain_lines import trees as line_trees
        lt = line_trees(T)
        T._line_trees = lt
        base = len(T.cover) + 1
        for j, kind in enumerate(("shrub", "broadleaf")):
            pts = np.array([[x, y] for x, y, k, _ in lt if k == kind]).reshape(-1, 2)
            if len(pts):
                out.append(np.c_[pts, T.sample(pts), np.full(len(pts), base + j)])
                T.tree_layers = getattr(T, "tree_layers", {}) | {base + j: ("lines", kind)}
    if not out:
        return np.zeros((0, 4))
    allp = np.vstack(out)
    if len(lt) and len(allp) > limit:  # (the lines' own trees are few and placed: keep them all)
        keep_n = limit - len(lt)
        own = allp[:, 3] >= len(T.cover) + 1
        rest = allp[~own]
        allp = np.vstack([rest[rng.choice(len(rest), max(keep_n, 0), replace=False)], allp[own]]) \
            if len(rest) > keep_n else allp
        return allp
    if len(allp) > limit:
        allp = allp[rng.choice(len(allp), limit, replace=False)]
    return allp
