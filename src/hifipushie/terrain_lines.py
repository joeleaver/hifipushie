"""Linear features: hedgerows, stone walls, fences, earth banks, ditches, lines of trees. Anything a designer draws as a
line on the land that isn't a way to walk (routes) or water (rivers).

"lines": {name: {"type": "hedge" | "stone wall" | "fence" | "bank" | "ditch" | "trees",
                 one of: "along": [addresses], "follows": route | river, "around": zone, "network": {...},
                 "side"?: "left" | "right" | "both", "offset"?: m, "from"?/"to"?: 0..1 (follows),
                 "gaps"?: [addresses], "gates"?: m (a gap every so far), "width"?, "bank"?, "ditch"?, "height"?,
                 "shrubs"?: m, "trees"?: m | false}}

A type is a cross-section and what stands on it; any of its numbers can be given:
  hedge       a bank 0.4 m under a 2.5 m wide hedge (shrubs every 1.8 m, a tree standing out of it every ~25 m)
  stone wall  a dry-stone wall 1.2 m high, 0.7 m wide (below the grid: the export lists it, the views draw it)
  fence       posts and wire, 1.2 m (listed and drawn, no ground change)
  bank        an earth bank 1 m high, 4 m across
  ditch       a ditch 1 m deep, 3 m across
  trees       a line of trees (a shelterbelt, an avenue), one every 7 m, 8 m wide
"bank" and "ditch" on any type add them (a hedge with a ditch on its field side: "ditch": 0.8, "ditch_side": "right").

A line never crosses water, pads or routes: it stops at a route (a gateway) and at the water's edge. The views draw
walls and fences, and put the shrubs and trees; the export lists every line (meta.json "lines": points on the ground,
type, height, width), writes a mask per line, and the trees go in trees.csv.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from .terrain import smoothstep

TYPES = {
    "hedge": {"bank": 0.4, "width": 2.5, "shrubs": 1.8, "trees": 25.0, "cover": [0.10, 0.20, 0.08]},
    "stone wall": {"width": 0.7, "height": 1.2, "wall": True},
    "fence": {"width": 0.15, "height": 1.2, "fence": True},
    "bank": {"bank": 1.0, "width": 4.0},
    "ditch": {"ditch": 1.0, "width": 3.0},
    "trees": {"width": 8.0, "trees": 7.0, "cover": [0.12, 0.22, 0.08]},
}
ALIASES = {"hedgerow": "hedge", "hedges": "hedge", "wall": "stone wall", "drystone wall": "stone wall",
           "dry stone wall": "stone wall", "dyke": "stone wall", "stone dyke": "stone wall", "fences": "fence",
           "earth bank": "bank", "embankment": "bank", "drain": "ditch", "trench": "ditch", "tree line": "trees",
           "treeline": "trees", "shelterbelt": "trees", "avenue": "trees", "windbreak": "trees", "line of trees": "trees"}


def _type(name, f):
    t = str(f.get("type", "hedge")).lower().strip().replace("-", " ").replace("_", " ")
    t = ALIASES.get(t, t)
    if t not in TYPES:
        raise ValueError(f"line {name!r}: type {f.get('type')!r} isn't one this knows ({', '.join(TYPES)}; also "
                         f"{', '.join(sorted(ALIASES))})")
    return t, {**TYPES[t], **{k: v for k, v in f.items() if k in ("bank", "ditch", "width", "height", "shrubs", "trees",
                                                                     "ditch_side")}}


def _dense(pts, step):
    """A polyline resampled every `step` m (straight between its corners)."""
    pts = np.asarray(pts, float)
    out = [pts[:1]]
    for a, b in zip(pts[:-1], pts[1:]):
        n = max(1, int(math.ceil(np.linalg.norm(b - a) / step)))
        out.append(a + (b - a) * (np.arange(1, n + 1) / n)[:, None])
    return np.vstack(out)


def _offset(xy, off):
    """A polyline moved sideways (+ = left of its direction)."""
    t = np.gradient(xy, axis=0)
    t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
    return xy + np.stack([-t[:, 1], t[:, 0]], 1) * off


def _network(T, name, net):
    """Field boundaries over a zone: long lines `spacing` apart across it (at `angle`, or along the contours: fields
    laid across the slope), and between each pair short cross lines at irregular places (T-junctions, fields of uneven
    length), clipped to the zone."""
    from . import terrain_design as design
    zone = design.region(T, net.get("in", "everywhere")) > 0.5
    sp = net.get("spacing", 120.0)
    sx, sy = (float(sp[0]), float(sp[1])) if isinstance(sp, (list, tuple)) else (float(sp), 1.3 * float(sp))
    jit = float(net.get("jitter", 0.25))
    ang = net.get("angle", "contour")
    if ang == "contour":  # the long lines follow the slope's contours in the zone (fields across the slope)
        gy, gx = np.gradient(ndimage.gaussian_filter(T.H, max(1.0, 60.0 / T.cell)), T.cell)
        a = math.atan2(float(gy[zone].mean()), float(gx[zone].mean())) if zone.any() else 0.0
        ang_r = a + math.pi / 2
    else:
        ang_r = math.radians(90 - float(ang))  # a compass bearing for the long lines
    d = np.array([math.cos(ang_r), math.sin(ang_r)])  # along the long lines
    n = np.array([-d[1], d[0]])
    P = np.stack([T.X[zone], T.Y[zone]], 1)
    if not len(P):
        return []
    import zlib
    rng = np.random.default_rng(zlib.crc32(name.encode()))
    u, v = P @ d, P @ n
    lines = []
    vs = np.arange(v.min() - sx, v.max() + sx, sx)
    vs = vs + rng.uniform(-jit, jit, len(vs)) * sx
    for v0 in vs:
        lines.append(np.array([d * u.min() + n * v0, d * u.max() + n * v0]))
    for v0, v1 in zip(vs[:-1], vs[1:]):
        u0 = u.min() + rng.uniform(0, sy)
        while u0 < u.max():
            a = d * u0 + n * v0
            b = d * (u0 + rng.uniform(-jit, jit) * sy * 0.3) + n * v1
            lines.append(np.array([a, b]))
            u0 += sy * rng.uniform(1 - jit, 1 + jit)
    # clipped to the zone: dense samples kept inside, split where they leave it
    out = []
    for L in lines:
        xy = _dense(L, max(T.cell, 2.0))
        inside = T.sample(xy, zone.astype(float)) > 0.5
        out += _runs(xy, inside)
    return out


def _runs(xy, keep, min_len=6.0):
    """The pieces of a polyline where keep is True."""
    out, start = [], None
    for i, k in enumerate(np.r_[keep, False]):
        if k and start is None:
            start = i
        elif not k and start is not None:
            piece = xy[start:i]
            if len(piece) > 1 and np.linalg.norm(piece[-1] - piece[0]) >= min_len:
                out.append(piece)
            start = None
    return out


def _paths(T, name, f):
    """The feature's polylines (dense, in metres)."""
    step = max(T.cell / 2, 1.0)
    if "along" in f:
        pts = [T.address(a)[0] for a in f["along"]]
        return [_dense(pts, step)]
    if "follows" in f:
        ref = f["follows"]
        L = T.routes.get(ref) or T.lines.get(ref)
        if L is None:
            raise ValueError(f"line {name!r}: follows {ref!r}, which is no route, river or ridge")
        s0, s1 = float(f.get("from", 0.0)), float(f.get("to", 1.0))
        xy = L.xy[(L.s >= s0) & (L.s <= s1)]
        xy = _dense(xy, step)
        wr = float((T.spec.get("routes") or {}).get(ref, {}).get("width", 4.0)) if ref in T.routes else \
            float(L.props.get("floor", 6.0)) if L.kind == "river" else 4.0
        off = float(f.get("offset", wr / 2 + float(f.get("width", 2.5)) / 2 + 1.5))
        side = f.get("side", "both")
        sides = [1, -1] if side == "both" else [1 if side == "left" else -1]
        return [ndimage.gaussian_filter1d(_offset(xy, s * off), 2, axis=0) for s in sides]
    if "around" in f:
        from skimage import measure
        from . import terrain_design as design
        m = design.region(T, f["around"])
        cs = measure.find_contours(np.pad(m, 1), 0.5)
        out = []
        for c in cs:
            c = c - 1
            xy = np.stack([T.xs[0] + c[:, 1] * T.cell, T.ys[0] + c[:, 0] * T.cell], 1)
            if len(xy) > 4:
                out.append(_dense(ndimage.gaussian_filter1d(xy, 1.5, axis=0, mode="wrap"), step))
        return out
    if "network" in f:
        return _network(T, name, f["network"])
    raise ValueError(f"line {name!r}: give \"along\" (addresses), \"follows\" (a route or river), \"around\" (a zone) "
                     f"or \"network\" ({{\"in\": zone, \"spacing\": m}})")


def apply(T):
    """Build every line: cut its pieces where it meets water, pads and routes (and its gaps), shape the ground (bank,
    ditch), and record it for cover, trees, the export and the views."""
    spec = T.spec.get("lines") or {}
    T.features = {}
    if not spec:
        return
    wet = ~np.isnan(T.water)
    pads = T.masks["sites"] > 0.3 if "sites" in T.masks else np.zeros(T.X.shape, bool)
    roads = T.masks["routes"] > 0.3 if "routes" in T.masks else np.zeros(T.X.shape, bool)
    H = T.H
    for name, f in spec.items():
        t, p = _type(name, f)
        w = float(p["width"])
        pieces = []
        gaps = [T.address(g)[0] for g in f.get("gaps", [])]
        # (a line beside a route keeps to its side: only other things stop it)
        block = wet | pads | (roads if "follows" not in f or f["follows"] not in T.routes else False)
        for xy in _paths(T, name, f):
            ok = T.sample(xy, (~ndimage.binary_dilation(block, iterations=1)).astype(float)) > 0.5
            ok &= (xy[:, 0] > T.xs[0]) & (xy[:, 0] < T.xs[-1]) & (xy[:, 1] > T.ys[0]) & (xy[:, 1] < T.ys[-1])
            for g in gaps:
                ok &= np.hypot(*(xy - g).T) > float(f.get("gap_width", 4.0)) / 2 + w / 2
            if f.get("gates"):  # a gap every so far along it
                s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
                ok &= (s % float(f["gates"])) > float(f.get("gap_width", 4.0))
            pieces += _runs(xy, ok, min_len=max(3.0, 2 * w))
        if not pieces:
            T.warnings.append(f"line {name!r}: nothing left of it (it's all under water, pads or routes, or outside "
                              f"its zone)")
            T.features[name] = {"type": t, "pieces": [], "length": 0.0, **p}
            continue
        allp = np.vstack(pieces)
        dist = cKDTree(allp).query(T.P, distance_upper_bound=w / 2 + 4 * T.cell + 3.0)[0].reshape(T.X.shape)
        dist = np.where(np.isfinite(dist), dist, 1e9)
        core = smoothstep(w / 2 + T.cell, w / 2, dist)  # what stands on it (cover mask)
        if p.get("bank"):  # an earth bank under it: rounded, a little wider than what stands on it
            half = w / 2 + max(1.0, 0.6 * p["bank"] / 0.35)
            H = H + float(p["bank"]) * np.clip(1 - (dist / half) ** 2, 0, 1) ** 1.2 * (dist < half)
        if p.get("ditch"):  # a ditch: alone (type ditch), or beside it on one side
            depth = float(p["ditch"])
            if t == "ditch":
                dd = dist
                half = w / 2
            else:
                side = p.get("ditch_side", "right")
                sgn = {"left": 1, "right": -1, "both": 0}.get(side, -1)
                dd = np.full(T.X.shape, 1e9)
                for xy in pieces:
                    offs = [1, -1] if sgn == 0 else [sgn]
                    for s in offs:
                        q = _offset(xy, s * (w / 2 + 1.5))
                        dq = cKDTree(q).query(T.P, distance_upper_bound=6 + 4 * T.cell)[0].reshape(T.X.shape)
                        dd = np.minimum(dd, np.where(np.isfinite(dq), dq, 1e9))
                half = 1.2
            H = H - depth * np.clip(1 - (dd / half) ** 2, 0, 1) * (dd < half) * ~block
        T.features[name] = {"type": t, "pieces": pieces, "mask": core, "length":
                            float(sum(np.linalg.norm(np.diff(q, axis=0), axis=1).sum() for q in pieces)), **p}
    T.H = H


def trees(T):
    """Shrubs along hedges and trees standing out of them / lining a treeline: (x, y, kind) rows."""
    out = []
    rng = np.random.default_rng(23)
    for name, F in getattr(T, "features", {}).items():
        for xy in F["pieces"]:
            s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
            if s[-1] < 1:
                continue
            for key, kind in (("shrubs", "shrub"), ("trees", "broadleaf")):
                sp = F.get(key)
                if not sp:
                    continue
                at = np.arange(rng.uniform(0, sp), s[-1], float(sp))
                at = at + rng.uniform(-0.3, 0.3, len(at)) * sp * (0.3 if kind == "shrub" else 1.0)
                at = np.clip(at, 0, s[-1])
                px = np.interp(at, s, xy[:, 0])
                py = np.interp(at, s, xy[:, 1])
                jit = rng.normal(0, 0.15 * F["width"], (len(at), 2)) if kind == "shrub" else np.zeros((len(at), 2))
                for (x, y) in np.c_[px, py] + jit:
                    out.append((x, y, kind, name))
    return out


def meta(T):
    """The lines for the export: per piece its points on the ground, and what it is."""
    out = {}
    for name, F in getattr(T, "features", {}).items():
        pcs = []
        for xy in F["pieces"]:
            q = xy[:: max(1, int(round(4.0 / max(np.linalg.norm(xy[1] - xy[0]), 0.1))))] if len(xy) > 2 else xy
            if len(q) and not np.allclose(q[-1], xy[-1]):
                q = np.vstack([q, xy[-1:]])
            z = T.sample(q)
            pcs.append([[round(float(x), 2), round(float(y), 2), round(float(h), 2)] for (x, y), h in zip(q, z)])
        out[name] = {"type": F["type"], "width": F["width"], "height": F.get("height"), "bank": F.get("bank"),
                     "ditch": F.get("ditch"), "pieces": pcs}
    return out


def report(T):
    out = []
    lt = trees(T)
    for name, F in getattr(T, "features", {}).items():
        if not F["pieces"]:
            continue
        txt = f"line {name} ({F['type']}): {F['length']:.0f} m in {len(F['pieces'])} piece(s)"
        m = F["mask"] > 0.5
        if (F.get("bank") or F.get("ditch")) and m.any():  # as built: the bank's crest over the ground either side
            ring = ndimage.binary_dilation(m, iterations=max(2, int(4.0 / T.cell))) & ~ndimage.binary_dilation(m)
            if ring.any():
                rel = float(np.median(T.H[m]) - np.median(T.H[ring]))
                txt += f", stands {rel:+.1f} m over the ground beside it"
        n = sum(1 for tr in lt if tr[3] == name)
        if n:
            txt += f", {n} shrubs/trees"
        out.append(txt)
    return out
