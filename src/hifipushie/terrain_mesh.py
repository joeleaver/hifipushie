"""3D terrain: a signed distance field over the heightfield plus 3D volumes (arches, sea caves, overhangs), meshed and
exported as a grid of seamless glTF tiles with LODs, skirts, collision and a manifest. Experimental.

The heightfield stays the design surface (terrain.py builds it); `spec["volumes"]` are shapes addressed on it and
subtracted from (or added to) the rock. The field is global and evaluated pointwise:
    F(p) = (z - h(x, y)) / sqrt(1 + |grad h|^2)          the ground as a solid (distance-corrected on slopes)
    F = smax(F, -d_volume, blend) | smin(F, d_volume, blend)   each volume in spec order
h reads the terrain grid as a cubic B-spline without prefiltering (approximating: C2, never overshoots a cliff).

Tiling rules (the design agreed 2026-09-28):
- A fixed world grid of tiles (i, j) from `origin`, `tile` metres a side. LOD k meshes at voxel * 2^k; every voxel
  divides the tile, so both neighbours put border vertices on the same lattice edges.
- Border vertices are decided once: per LOD, every lattice edge on a tile border that the surface crosses gets one
  canonical vertex (linear crossing, then Newton steps constrained to the border plane), its field normal and its
  material weights. Each tile's marching-cubes border vertices are replaced by these, and decimation keeps them
  (pyfqmr with preserve_border), so neighbours share bit-identical chains. A cave crossing a border is just more
  crossings on that plane: more loops in the chain.
- Normals and weights come from the global field/masks at each vertex: continuous across seams by construction.
- Skirts: each shared border's chain is extruded into the rock (in the border plane, against the surface normal) by
  as much as the neighbours' LOD chains differ there, clamped to the rock's thickness so a skirt never pokes into a
  cave. Mixed-LOD neighbours then show no cracks.
- The seam check reads the written GLBs back and fails loudly (see `seam_check`).

Only the ground near the surface is evaluated: each tile's grid spans its own height range (plus volumes), not the
world's.
"""

from __future__ import annotations

import json
import math
import struct
import time
import zlib
from pathlib import Path

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from . import noise

DEFAULTS = {
    "tile": 64.0,          # metres a side
    "voxel": 1.0,          # LOD0 meshing voxel; LOD k uses voxel * 2^k (all must divide the tile)
    "lods": 3,
    "origin": None,        # world grid origin [x, y]; default the extent's south-west corner
    "error": [0.04, 0.15, 0.5],     # decimation tolerance per LOD, metres
    "budget": [12000, 3000, 800],   # triangle cap per tile per LOD (the border chains are always kept)
    "skirt": 0.3,          # minimum skirt depth, metres
    "collision": 1,        # which LOD the collision mesh is made from
    "heightmap": 65,       # samples a side per tile heightmap (2^k + 1, edges shared with the neighbours); 0 = none
    "splat": 128,          # splat texels a side per tile (+ a margin into the neighbours); 0 = none
    "splat_margin": 2,
    "blend": 1.0,          # default volume blend (m): rounded edges where a cave meets the ground
}

# ground materials: what each cover type lays on the ground (tree layers: the forest floor under them)
LAYER_OF = {"meadow": "grass", "grass": "grass", "orchard": "grass", "forest": "forest_floor",
            "conifer": "forest_floor", "deciduous": "forest_floor", "rock": "rock", "scree": "rock", "sand": "sand",
            "mud": "earth", "snow": "snow"}
LAYERS = {  # reference look (sRGB colour, roughness) and a triplanar tiling scale (m) for engines
    "grass": {"color": [0.36, 0.47, 0.20], "roughness": 0.95, "scale": 3.0},
    "forest_floor": {"color": [0.27, 0.22, 0.15], "roughness": 0.95, "scale": 3.0},
    "sand": {"color": [0.72, 0.65, 0.48], "roughness": 0.9, "scale": 2.0},
    "rock": {"color": [0.44, 0.42, 0.39], "roughness": 0.85, "scale": 6.0},
    "earth": {"color": [0.42, 0.34, 0.24], "roughness": 0.95, "scale": 2.5},
    "snow": {"color": [0.93, 0.94, 0.96], "roughness": 0.7, "scale": 4.0},
}


def smin(a, b, k):
    if k <= 0:
        return np.minimum(a, b)
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * h * k * (1.0 / 6.0)


def smax(a, b, k):
    return -smin(-a, -b, k)


def smoothstep(e0, e1, x):
    u = np.clip((x - e0) / (e1 - e0), 0, 1)
    return u * u * (3 - 2 * u)


# ---------------------------------------------------------------- volumes

class Tube:
    """A passage along a polyline of nodes: an elliptical cross-section (half width rw across, rh up) that varies
    node to node, rounded ends, optionally cut flat below `floor` (per node). One node is an ellipsoid (a chamber).
    Arches, sea caves and notches are all tubes; a cave engine would be a graph of them."""

    def __init__(self, name, nodes, rw, rh, floor=None, op="subtract", blend=1.0, rough=0.4, rough_scale=3.0, seed=0):
        self.name, self.op, self.blend = name, op, float(blend)
        self.nodes = np.atleast_2d(np.asarray(nodes, float))
        n = len(self.nodes)
        self.rw = np.broadcast_to(np.asarray(rw, float), (n,)).copy()
        self.rh = np.broadcast_to(np.asarray(rh, float), (n,)).copy()
        self.floor = None if floor is None else np.broadcast_to(np.asarray(floor, float), (n,)).copy()
        self.rough, self.rough_scale, self.seed = float(rough), float(rough_scale), int(seed)
        r = np.maximum(self.rw, self.rh).max() + self.blend + self.rough + 0.5
        self.lo, self.hi = self.nodes.min(0) - r, self.nodes.max(0) + r
        if self.floor is not None:
            self.lo[2] = max(self.lo[2], float(self.floor.min()) - self.blend - self.rough - 0.5)

    def sd(self, p):
        best = np.full(len(p), np.inf)
        segs = [(0, 0)] if len(self.nodes) == 1 else [(i, i + 1) for i in range(len(self.nodes) - 1)]
        for i, j in segs:
            a, b = self.nodes[i], self.nodes[j]
            d = b - a
            L = float(np.linalg.norm(d))
            t = d / L if L > 1e-9 else np.array([1.0, 0.0, 0.0])
            s = np.clip(((p - a) @ t) / L, 0, 1) if L > 1e-9 else np.zeros(len(p))
            q = p - (a + s[:, None] * d)
            eu = np.cross(t, [0, 0, 1.0])
            eu = eu / np.linalg.norm(eu) if np.linalg.norm(eu) > 1e-6 else np.array([1.0, 0, 0])
            ev = np.cross(eu, t)
            u, v, w = q @ eu, q @ ev, q @ t
            rw = self.rw[i] + s * (self.rw[j] - self.rw[i])
            rh = self.rh[i] + s * (self.rh[j] - self.rh[i])
            dd = (np.sqrt((u / rw) ** 2 + (v / rh) ** 2 + (w / rw) ** 2) - 1) * np.minimum(rw, rh)
            if self.floor is not None:
                fl = self.floor[i] + s * (self.floor[j] - self.floor[i])
                dd = np.maximum(dd, fl - p[:, 2])
            best = np.minimum(best, dd)
        if self.rough > 0:
            best = best + self.rough * (2 * noise.fbm(p, self.rough_scale, 3, seed=self.seed) - 1)
        return best

    def touches(self, lo, hi):
        return bool(np.all(self.hi >= lo) and np.all(self.lo <= hi))


def _bearing(T, v, at_xy):
    """A direction in plan: a compass bearing (0 north, 90 east) or an address to head for."""
    if isinstance(v, (int, float)):
        b = math.radians(float(v))
        return np.array([math.sin(b), math.cos(b)])
    xy = T.address(v)[0]
    d = np.asarray(xy, float) - at_xy
    return d / max(np.linalg.norm(d), 1e-9)


def _daylight(T, xy, t, below, reach=300.0, start=0.0):
    """Distance along t from xy to the first ground lower than `below` (where a passage comes out into the open)."""
    s = np.arange(start, reach, T.cell / 2)
    h = T.sample(xy + s[:, None] * t)
    k = np.flatnonzero(h < below)
    return float(s[k[0]]) if len(k) else None


def _sea(T):
    return float(T.sea["level"]) if getattr(T, "sea", None) else None


def volumes(T) -> tuple[list[Tube], list[str]]:
    """The spec's volumes as tubes, and notes on what was chosen or doesn't fit (for the report)."""
    out, notes = [], []
    spec = T.spec.get("volumes") or {}
    if isinstance(spec, list):
        spec = {v.get("name", f"volume_{i}"): v for i, v in enumerate(spec, 1)}
    for k, (name, v) in enumerate(spec.items()):
        kind = v.get("type")
        seed = zlib.crc32(name.encode()) % 10000
        common = dict(op=v.get("op", "subtract"), blend=v.get("blend", DEFAULTS["blend"]), rough=v.get("rough", 0.4),
                      rough_scale=v.get("rough_scale", 3.0), seed=seed)
        at, _, adir = T.address(v["at"])  # an address's own direction (e.g. "cliff_foot:<address>": into the rock)
        at = np.asarray(at, float)
        adir = None if adir is None else np.asarray(adir, float)[:2] / max(np.linalg.norm(np.asarray(adir)[:2]), 1e-9)
        sea = _sea(T)
        if kind == "arch":
            t = _bearing(T, v["toward"], at) if "toward" in v else _narrowest(T, at)
            floor = float(v.get("floor", (sea - 1.0) if sea is not None else T.height(at) - 6))
            top = T.height(at)
            height = float(v.get("height", 0.55 * (top - floor)))
            w = float(v.get("width", 8.0))
            ends = []
            for sgn in (1, -1):
                s = _daylight(T, at, sgn * t, floor + 0.5 * height)
                if s is None:
                    raise ValueError(f"volume {name!r}: the arch never comes out of the rock heading "
                                     f"{'forward' if sgn > 0 else 'back'}")
                ends.append(at + sgn * t * (s + 0.5 * w))
            nodes = [[*ends[1], floor], [*ends[0], floor]]
            out.append(Tube(name, nodes, w / 2, height, floor, **common))
            roof = top - floor - height
            notes.append(f"{name}: arch {w:.0f} m wide, {height:.1f} m high over a floor at {floor:+.1f} m, "
                         f"{np.linalg.norm(ends[0] - ends[1]):.0f} m through the rock, roof {roof:.1f} m thick at its "
                         f"middle" + (" (thin: it may break through)" if roof < 2 else ""))
        elif kind in ("cave", "tunnel"):
            t = _bearing(T, v["toward"], at) if "toward" in v else adir if adir is not None else -_downhill(T, at)
            floor0 = float(v.get("floor", (sea - 0.5) if sea is not None else T.height(at)))
            w, h = float(v.get("width", 6.0)), float(v.get("height", 5.0))
            L = float(v.get("length", 30.0))
            rise = float(v.get("rise", 0.0))
            narrow = float(v.get("narrow", 0.7))
            # the mouth: where the rock starts along the way in (a cave addressed in the water or on the cliff top both
            # open at the cliff)
            if T.height(at) < floor0 + 0.5 * h:  # out in the open: ahead to the rock
                s = np.arange(0, 300, T.cell / 2)
                k = np.flatnonzero(T.sample(at + s[:, None] * t) >= floor0 + 0.5 * h)
                if not len(k):
                    raise ValueError(f"volume {name!r}: no rock ahead of {v['at']!r} to cut a cave into")
                mouth = at + t * s[k[0]]
            else:  # in the rock: back to where it comes out
                mouth = at - t * (_daylight(T, at, -t, floor0 + 0.5 * h, reach=200) or 0.0)
            start = mouth - t * 0.5 * w
            n = max(3, int(L / 6))
            s = np.linspace(0, L + 0.5 * w, n + 1)
            wander = float(v.get("wander", 0.08)) * L
            side = np.array([-t[1], t[0]])
            lat = wander * np.sin(np.pi * s / (L + 0.5 * w)) * math.sin(seed)  # one gentle bend
            xy = start + s[:, None] * t + lat[:, None] * side
            fl = floor0 + rise * np.clip(s / max(L, 1e-6), 0, 1)
            f = np.clip(s / (L + 0.5 * w), 0, 1)
            rw = w / 2 * (1 - (1 - narrow) * f)
            rh = h * (1 - (1 - narrow) * f)
            out.append(Tube(name, np.c_[xy, fl], rw, rh, fl, **common))
            ch = float(v.get("chamber", 0.0))
            if ch > 0:  # a domed chamber at the end, on the passage's floor
                out.append(Tube(name + ":chamber", [[*xy[-1], fl[-1]]], ch, 0.8 * ch, fl[-1], **common))
            ground = T.sample(xy)
            inside = ground > fl + rh  # (the part out in the open has no roof)
            roof = float(np.min((ground - (fl + rh))[inside])) if inside.any() else float("nan")
            notes.append(f"{name}: cave {w:.0f} x {h:.0f} m, mouth at [{mouth[0]:.0f}, {mouth[1]:.0f}] floor "
                         f"{floor0:+.1f} m, {L:.0f} m in" + (f", chamber r {ch:.0f} m" if ch else "")
                         + f"; thinnest roof {roof:.1f} m" + (" (it breaks through)" if roof < 1 else ""))
        elif kind == "overhang":  # a wave-cut notch along a cliff foot: the lip above overhangs it
            depth, h = float(v.get("depth", 4.0)), float(v.get("height", 3.0))
            L = float(v.get("length", 30.0))
            floor = float(v.get("floor", (sea + 0.3) if sea is not None else T.height(at)))
            along = _bearing(T, v["along"], at) if "along" in v else np.array([-_downhill(T, at)[1], _downhill(T, at)[0]])
            pts = []
            for s in np.linspace(-L / 2, L / 2, max(3, int(L / 5) + 1)):
                p = at + s * along
                face = _face(T, p, floor + h / 2)
                if face is not None:
                    pts.append(face)
            if len(pts) < 2:
                raise ValueError(f"volume {name!r}: no cliff face near {v['at']!r} to undercut")
            pts = np.array(pts)
            f = np.abs(np.linspace(-1, 1, len(pts)))
            rw = depth * (1 - 0.7 * f ** 2)
            out.append(Tube(name, np.c_[pts, np.full(len(pts), floor + h / 2)], rw, h / 2, floor, **common))
            notes.append(f"{name}: overhang notch {depth:.0f} m deep, {h:.0f} m high, {L:.0f} m along the cliff")
        else:
            raise ValueError(f"volume {name!r}: type {kind!r}: use arch, cave or overhang")
        if common["op"] not in ("subtract", "add"):
            raise ValueError(f"volume {name!r}: op {common['op']!r}: use subtract or add")
    return out, notes


def _downhill(T, xy):
    """Unit direction downhill at xy, the slope smoothed over a few cells."""
    e = 3 * T.cell
    gx = T.height(xy + [e, 0]) - T.height(xy - np.array([e, 0]))
    gy = T.height(xy + [0, e]) - T.height(xy - np.array([0, e]))
    g = -np.array([gx, gy])
    return g / max(np.linalg.norm(g), 1e-9)


def _narrowest(T, at):
    """The bearing along which the land at `at` is thinnest (an arch goes through a neck)."""
    best = None
    for b in range(0, 180, 5):
        t = np.array([math.sin(math.radians(b)), math.cos(math.radians(b))])
        s1 = _daylight(T, at, t, T.height(at) - 3)
        s2 = _daylight(T, at, -t, T.height(at) - 3)
        if s1 is not None and s2 is not None and (best is None or s1 + s2 < best[0]):
            best = (s1 + s2, t)
    if best is None:
        raise ValueError("an arch needs land that comes out into the open both ways")
    return best[1]


def _face(T, p, z):
    """Where the ground crosses height z nearest p, along the local slope (a cliff face's position)."""
    d = _downhill(T, p)
    s = np.arange(-40, 40, T.cell / 4)
    pts = p + s[:, None] * d
    h = T.sample(pts) - z
    k = np.flatnonzero(np.sign(h[:-1]) != np.sign(h[1:]))
    if not len(k):
        return None
    k = k[np.argmin(np.abs(s[k]))]
    f = h[k] / (h[k] - h[k + 1])
    return pts[k] + f * (pts[k + 1] - pts[k])


# ---------------------------------------------------------------- the field

class Field:
    def __init__(self, T, vols: list[Tube]):
        self.H = np.ascontiguousarray(T.H, float)
        self.x0, self.y0, self.c = float(T.xs[0]), float(T.ys[0]), float(T.cell)
        self.vols = vols

    def column(self, x, y):
        """Ground height h and the slope correction 1 / sqrt(1 + |grad h|^2) at columns."""
        r = (np.asarray(y, float) - self.y0) / self.c
        q = (np.asarray(x, float) - self.x0) / self.c
        e = 0.5
        rr = np.concatenate([r, r, r, r + e, r - e])
        qq = np.concatenate([q, q + e, q - e, q, q])
        v = ndimage.map_coordinates(self.H, [rr, qq], order=3, prefilter=False, mode="nearest").reshape(5, -1)
        gx = (v[1] - v[2]) / (2 * e * self.c)
        gy = (v[3] - v[4]) / (2 * e * self.c)
        return v[0], 1.0 / np.sqrt(1.0 + gx * gx + gy * gy)

    def ground(self, p):
        h, s = self.column(p[:, 0], p[:, 1])
        return (p[:, 2] - h) * s

    def volumes(self, p, F):
        for vol in self.vols:
            k = np.flatnonzero(np.all((p >= vol.lo) & (p <= vol.hi), axis=1))
            if not len(k):
                continue
            d = vol.sd(p[k])
            F[k] = smax(F[k], -d, vol.blend) if vol.op == "subtract" else smin(F[k], d, vol.blend)
        return F

    def value(self, p):
        p = np.asarray(p, float)
        return self.volumes(p, self.ground(p))

    def value_gradient(self, p, h):
        tet = np.array([[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]], float)
        f = self.value((p[:, None, :] + h * tet[None]).reshape(-1, 3)).reshape(-1, 4)
        return f.mean(1), (f @ tet) / (4 * h)


def _lattice_values(field, P, v):
    """Field values at lattice points, kept at least 1e-3 voxel from zero so every crossing lies strictly inside
    its lattice edge (both neighbours then agree which edges are crossed)."""
    F = field.value(P)
    eps = 1e-3 * v
    return np.where(np.abs(F) < eps, np.where(F < 0, -eps, eps), F)


def project(field, P, v, fixed=None, iterations=4):
    """Newton steps onto the zero set (capped at half a voxel), then unit normals from the field's gradient.
    `fixed`: (n, 3) bool, axes a vertex may not move along (border planes)."""
    P = P.astype(np.float64).copy()
    h = v / 8
    todo = np.arange(len(P))
    for _ in range(iterations):
        if not len(todo):
            break
        f, g = field.value_gradient(P[todo], h)
        if fixed is not None:
            g = np.where(fixed[todo], 0.0, g)
        step = (f / np.maximum((g * g).sum(1), 1e-12))[:, None] * g
        n = np.linalg.norm(step, axis=1, keepdims=True)
        step *= np.minimum(1.0, 0.5 * v / np.maximum(n, 1e-12))
        ok = np.isfinite(step).all(1)
        P[todo[ok]] -= step[ok]
        todo = todo[ok & (n[:, 0] > 1e-4 * v)]
    _, g = field.value_gradient(P, h)
    N = g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12)
    return P, N


# ---------------------------------------------------------------- materials

class Materials:
    """Per-vertex layer weights (for engines: world-space/triplanar tiling layers blended by weight) and a display
    colour (the reference material's vertex colour), both from the global masks at the vertex's position and the
    field's normal there: continuous across seams."""

    def __init__(self, T, field):
        from . import terrain_design as design
        from .terrain import ground_colours
        self.T, self.field = T, field
        self.sea = _sea(T)
        order = []
        self.cover = []
        for name, m in T.cover.items():
            c = design._spec_cover(T, name)
            layer = LAYER_OF.get(c.get("type", name), "grass")
            tree = bool(c.get("trees"))
            self.cover.append((name, layer, 0.6 if tree else 1.0))
            order.append(layer)
        self.layers = list(dict.fromkeys(order + ["rock", "earth"] + (["sand"] if self.sea is not None else [])))
        col = ground_colours(T, cover=True)
        wet = ~np.isnan(T.water)
        col[wet] = np.array(LAYERS["sand"]["color"]) * 0.8
        self.display = col
        self.routes = T.masks.get("routes")

    def _grid(self, a, xy):
        return self.T.sample(xy, a)

    def weights(self, P, N):
        xy = P[:, :2]
        n = len(P)
        W = {k: np.zeros(n) for k in self.layers}
        rest = np.ones(n)
        for name, layer, k in reversed(self.cover):  # painted in order: later layers over earlier
            d = np.clip(self._grid(self.T.cover[name].astype(float), xy), 0, 1) * k
            W[layer] += d * rest
            rest *= 1 - d
        W["earth"] += rest
        if self.routes is not None:
            r = np.clip(self._grid(self.routes.astype(float), xy), 0, 1) * 0.8
            for key in W:
                W[key] *= 1 - r
            W["earth"] += r
        # rock: steep or overhanging faces (from the field's normal), and anything below the heightfield's ground
        # (a cave's walls and roof, an arch's soffit)
        slope = np.degrees(np.arccos(np.clip(N[:, 2], -1, 1)))
        below = smoothstep(0.3, 1.2, -self.field.ground(P))
        rock = np.maximum(smoothstep(38, 58, slope), below)
        if self.sea is not None:  # under water: sand, unless rock
            wet = smoothstep(0.2, 1.2, self.sea - P[:, 2])
            for key in W:
                W[key] *= 1 - wet
            W["sand"] += wet
        for key in W:
            W[key] *= 1 - rock
        W["rock"] += rock
        Wm = np.stack([W[k] for k in self.layers], 1)
        Wm /= np.maximum(Wm.sum(1, keepdims=True), 1e-9)
        # display colour: the terrain's own preview colours (cover, roads, slope), rock over steep faces and caves
        c = np.stack([self._grid(self.display[..., i], xy) for i in range(3)], 1)
        rc = np.array(LAYERS["rock"]["color"])
        if self.sea is not None:
            wet = smoothstep(0.2, 1.2, self.sea - P[:, 2])[:, None]
            c = c * (1 - wet) + np.array(LAYERS["sand"]["color"]) * 0.8 * wet
        c = c * (1 - rock[:, None]) + rc * rock[:, None]
        return Wm.astype(np.float32), c


def _linear(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


# ---------------------------------------------------------------- glTF

def _pad4(b: bytes, fill=b"\0"):
    return b + fill * (-len(b) % 4)


def write_glb(path, name, prims, translation, material, extras=None):
    """One node (at `translation`, glTF axes) with one mesh of primitives: each {"attrs": {NAME: float array},
    "indices": uint array, "material": index or None, "extras": {}}. Materials: a list of glTF material dicts."""
    bin_ = bytearray()
    views, accs = [], []

    def add(arr, target, comp, typ, minmax=False):
        arr = np.ascontiguousarray(arr)
        off = len(bin_)
        bin_.extend(_pad4(arr.tobytes()))
        views.append({"buffer": 0, "byteOffset": off, "byteLength": arr.nbytes, "target": target})
        acc = {"bufferView": len(views) - 1, "componentType": comp, "count": int(arr.shape[0]), "type": typ}
        if minmax:
            acc["min"] = [float(x) for x in arr.min(0)]
            acc["max"] = [float(x) for x in arr.max(0)]
        accs.append(acc)
        return len(accs) - 1

    gprims = []
    for p in prims:
        attrs = {}
        for k, a in p["attrs"].items():
            a = np.asarray(a, np.float32)
            typ = {1: "SCALAR", 2: "VEC2", 3: "VEC3", 4: "VEC4"}[a.shape[1]]
            attrs[k] = add(a, 34962, 5126, typ, minmax=(k == "POSITION"))
        idx = np.asarray(p["indices"]).ravel()
        n = len(p["attrs"]["POSITION"])
        if n < 65535:
            ia = add(idx.astype(np.uint16), 34963, 5123, "SCALAR")
        else:
            ia = add(idx.astype(np.uint32), 34963, 5125, "SCALAR")
        gp = {"attributes": attrs, "indices": ia, "mode": 4}
        if p.get("material") is not None:
            gp["material"] = p["material"]
        if p.get("extras"):
            gp["extras"] = p["extras"]
        gprims.append(gp)
    doc = {"asset": {"version": "2.0", "generator": "hifipushie terrain_mesh"},
           "scene": 0, "scenes": [{"nodes": [0]}],
           "nodes": [{"name": name, "mesh": 0, "translation": [float(x) for x in translation]}],
           "meshes": [{"name": name, "primitives": gprims}],
           "accessors": accs, "bufferViews": views, "buffers": [{"byteLength": len(bin_)}]}
    if material:
        doc["materials"] = material
    if extras:
        doc["nodes"][0]["extras"] = extras
    js = _pad4(json.dumps(doc, separators=(",", ":")).encode(), b" ")
    total = 12 + 8 + len(js) + 8 + len(bin_)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))
        f.write(struct.pack("<II", len(js), 0x4E4F534A))
        f.write(js)
        f.write(struct.pack("<II", len(bin_), 0x004E4942))
        f.write(bytes(bin_))


def read_glb(path):
    """(translation, [primitive dicts {attr: array, "indices", "extras"}]) of a GLB written by write_glb."""
    b = Path(path).read_bytes()
    jl = struct.unpack_from("<I", b, 12)[0]
    doc = json.loads(b[20:20 + jl])
    bl = struct.unpack_from("<I", b, 20 + jl)[0]
    binb = b[28 + jl:28 + jl + bl]
    comp = {5126: np.float32, 5123: np.uint16, 5125: np.uint32}
    width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}

    def acc(i):
        a = doc["accessors"][i]
        v = doc["bufferViews"][a["bufferView"]]
        arr = np.frombuffer(binb, comp[a["componentType"]], a["count"] * width[a["type"]], v["byteOffset"])
        return arr.reshape(a["count"], width[a["type"]]) if width[a["type"]] > 1 else arr

    prims = []
    for p in doc["meshes"][0]["primitives"]:
        d = {k: acc(i) for k, i in p["attributes"].items()}
        d["indices"] = acc(p["indices"]).reshape(-1, 3).astype(np.int64)
        d["extras"] = p.get("extras", {})
        prims.append(d)
    return np.array(doc["nodes"][0].get("translation", [0, 0, 0]), float), prims


def _to_gltf(P):  # ours (x east, y north, z up) -> glTF (x, y up, z = -north)
    return np.c_[P[:, 0], P[:, 2], -P[:, 1]]


def _from_gltf(P):
    return np.c_[P[:, 0], -P[:, 2], P[:, 1]]


# ---------------------------------------------------------------- tiles

class Grid:
    """The world's tile grid and the meshing lattice per LOD."""

    def __init__(self, T, cfg):
        (x0, y0), (x1, y1) = T.spec["extent"]
        self.origin = np.array(cfg.get("origin") or [x0, y0], float)
        self.tile = float(cfg["tile"])
        self.voxel = float(cfg["voxel"])
        self.lods = int(cfg["lods"])
        vmax = self.voxel * 2 ** (self.lods - 1)
        if abs(self.tile / vmax - round(self.tile / vmax)) > 1e-9:
            raise ValueError(f"tile {self.tile} m isn't a whole number of the coarsest voxel {vmax} m")
        # the meshed world: the extent from the origin, trimmed to whole coarsest voxels
        self.lo = self.origin
        span = np.array([x1, y1]) - self.origin
        self.span = np.floor(span / vmax + 1e-9) * vmax
        self.hi = self.origin + self.span
        self.trimmed = bool(np.any(np.abs(self.span - span) > 1e-6))
        self.ni, self.nj = int(math.ceil(self.span[0] / self.tile - 1e-9)), int(math.ceil(self.span[1] / self.tile - 1e-9))

    def v(self, k):
        return self.voxel * 2 ** k

    def cells(self, i, j, k):
        """Global lattice index range [a0, a1] x [b0, b1] (inclusive) of tile (i, j) at LOD k."""
        v = self.v(k)
        n = int(round(self.tile / v))
        NX, NY = int(round(self.span[0] / v)), int(round(self.span[1] / v))
        return (i * n, min((i + 1) * n, NX)), (j * n, min((j + 1) * n, NY)), n, (NX, NY)

    def bounds(self, i, j):
        lo = self.origin + np.array([i, j]) * self.tile
        return lo, np.minimum(lo + self.tile, self.hi)


def _tile_mc(field, G: Grid, i, j, k, vols):
    """Marching cubes of one tile at LOD k on the global lattice. Returns global lattice-index vertex coordinates
    (float64), faces, and the tile's lattice ranges."""
    from skimage import measure
    v = G.v(k)
    (a0, a1), (b0, b1), n, (NX, NY) = G.cells(i, j, k)
    ia = np.arange(a0, a1 + 1)
    ib = np.arange(b0, b1 + 1)
    X, Y = np.meshgrid(G.origin[0] + ia * v, G.origin[1] + ib * v, indexing="ij")
    # the tile's height range: its columns and one column round it, plus the volumes reaching it
    m = 1
    xe = G.origin[0] + np.arange(max(a0 - m, 0), min(a1 + m, NX) + 1) * v
    ye = G.origin[1] + np.arange(max(b0 - m, 0), min(b1 + m, NY) + 1) * v
    XE, YE = np.meshgrid(xe, ye, indexing="ij")
    h, _ = field.column(XE.ravel(), YE.ravel())
    zlo, zhi = h.min(), h.max()
    lo = np.array([X.min() - v, Y.min() - v, -1e9])
    hi = np.array([X.max() + v, Y.max() + v, 1e9])
    for vol in vols:
        if vol.touches(lo, hi):
            zlo, zhi = min(zlo, vol.lo[2]), max(zhi, vol.hi[2])
    c0, c1 = int(math.floor(zlo / v)) - 2, int(math.ceil(zhi / v)) + 2
    ic = np.arange(c0, c1 + 1)
    hcol, scol = field.column(X.ravel(), Y.ravel())
    Z = ic * v
    F = (Z[None, :] - hcol[:, None]) * scol[:, None]
    P = np.stack(np.broadcast_arrays(X.ravel()[:, None], Y.ravel()[:, None], Z[None, :]), -1).reshape(-1, 3)
    F = F.ravel()
    F = field.volumes(P, F)
    eps = 1e-3 * v
    F = np.where(np.abs(F) < eps, np.where(F < 0, -eps, eps), F)
    F = F.reshape(len(ia), len(ib), len(ic))
    if F.min() > 0 or F.max() < 0:
        return None
    verts, faces, _, _ = measure.marching_cubes(F, 0.0, spacing=(1.0, 1.0, 1.0), method="lewiner",
                                                allow_degenerate=False, gradient_direction="ascent")
    faces = faces[:, ::-1].astype(np.int64)  # outward for our inside-negative field
    idx = verts.astype(np.float64) + np.array([a0, b0, c0], float)
    return idx, faces, (a0, a1, b0, b1)


def _border_keys(idx, rng, n_tile, NX, NY):
    """For vertices on the tile's border planes: a key naming their lattice edge (axis, lower corner), and which
    axes are fixed (on a tile border or the world's edge)."""
    a0, a1, b0, b1 = rng
    onx = (idx[:, 0] == a0) | (idx[:, 0] == a1)
    ony = (idx[:, 1] == b0) | (idx[:, 1] == b1)
    on = onx | ony
    keys = {}
    for vi in np.flatnonzero(on):
        c = idx[vi]
        frac = np.abs(c - np.round(c)) > 1e-6
        if frac.sum() != 1:
            raise RuntimeError(f"border vertex {c} isn't on one lattice edge")
        ax = int(np.flatnonzero(frac)[0])
        lower = np.round(c).astype(np.int64)
        lower[ax] = int(math.floor(c[ax]))
        keys[vi] = (ax, int(lower[0]), int(lower[1]), int(lower[2]))
    return keys


def _key_geometry(keys, G, k):
    """Lattice edge endpoints (world) and fixed axes for canonical border vertices."""
    v = G.v(k)
    K = np.array(keys, np.int64)
    ax = K[:, 0]
    lo = K[:, 1:].astype(float)
    hi = lo.copy()
    hi[np.arange(len(K)), ax] += 1
    to_w = lambda a: np.c_[G.origin[0] + a[:, 0] * v, G.origin[1] + a[:, 1] * v, a[:, 2] * v]
    n = int(round(G.tile / v))
    NX, NY = int(round(G.span[0] / v)), int(round(G.span[1] / v))
    fixed = np.zeros((len(K), 3), bool)
    fixed[:, 0] = (ax != 0) & ((K[:, 1] % n == 0) | (K[:, 1] == NX))
    fixed[:, 1] = (ax != 1) & ((K[:, 2] % n == 0) | (K[:, 2] == NY))
    return to_w(lo), to_w(hi), fixed


def _boundary_edges(faces):
    """Directed edges used by one face only (a mesh's open border), as (a, b) in face order."""
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    key = np.minimum(e[:, 0], e[:, 1]) * (int(e.max()) + 1) + np.maximum(e[:, 0], e[:, 1])
    u, inv, cnt = np.unique(key, return_inverse=True, return_counts=True)
    return e[cnt[inv] == 1]


def _decimate(P, faces, err, budget, field):
    """Fewest triangles (pyfqmr, open borders locked) whose surface stays within `err` of the field (99th percentile
    at face centres and edge midpoints, over what the undecimated mesh already misses), capped at `budget`.
    (pyfqmr's own lossless mode barely removed anything with the border locked.)"""
    import pyfqmr

    def run(n):
        s = pyfqmr.Simplify()
        s.setMesh(P, faces)
        s.simplify_mesh(target_count=int(n), aggressiveness=7, preserve_border=True, verbose=False)
        v, f, _ = s.getMesh()
        return np.asarray(v, float), np.asarray(f, np.int64)

    def error(v, f):
        if not _manifold(f):  # pyfqmr can fold a thin part into a fin (two faces on one directed edge)
            return np.inf
        c = np.r_[v[f].mean(1), (v[f[:, 0]] + v[f[:, 1]]) / 2]
        return float(np.percentile(np.abs(field.value(c)), 99))

    tol = err + error(P, faces)
    if len(faces) <= budget:
        best, hi = (P, faces), len(faces)
    else:
        hi = int(budget)
        best = run(hi)
        if error(*best) > tol:
            if not _manifold(best[1]):  # over budget and folded: the budget gives way
                return P, faces
            return best
    lo = 64
    for _ in range(7):  # search the count on a log scale
        if hi / lo < 1.15:
            break
        mid = int(math.sqrt(lo * hi))
        cand = run(mid)
        if error(*cand) <= tol:
            best, hi = cand, mid
        else:
            lo = mid
    return best


def _manifold(f):
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    n = int(f.max()) + 1
    if len(np.unique(e[:, 0] * n + e[:, 1])) < len(e):
        return False
    und = np.minimum(e[:, 0], e[:, 1]) * n + np.maximum(e[:, 0], e[:, 1])
    return bool(np.unique(und, return_counts=True)[1].max() <= 2)


def _chain_dist(A, segs_b):
    """Distance from points A to a set of segments (m, 2, 3), via dense samples along the segments."""
    if not len(segs_b):
        return np.full(len(A), np.inf)
    L = np.linalg.norm(segs_b[:, 1] - segs_b[:, 0], axis=1)
    pts = []
    for (p, q), l in zip(segs_b, L):
        m = max(2, int(l / 0.02) + 1)
        pts.append(p + np.linspace(0, 1, m)[:, None] * (q - p))
    d, _ = cKDTree(np.vstack(pts)).query(A)
    return d


def export_tiles(T, out_dir, cfg: dict | None = None, log=print) -> dict:
    """Mesh the terrain's field (heightfield + volumes) into seamless tiles; write GLBs per tile per LOD, collision
    GLBs, heightmap and splat tiles, trees.csv and manifest.json; run the seam check (raises if it fails)."""
    from PIL import Image
    t_all = time.time()
    cfg = {**DEFAULTS, **((T.spec.get("export") or {}).get("tiles") or {}), **(cfg or {})}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.glb"):
        f.unlink()
    timing = {}
    t0 = time.time()
    vols, notes = volumes(T)
    field = Field(T, vols)
    mats = Materials(T, field)
    G = Grid(T, cfg)
    timing["setup"] = time.time() - t0
    tiles = [(i, j) for j in range(G.nj) for i in range(G.ni)]
    if cfg.get("only"):  # a block of tiles [[i0, j0], [i1, j1]] (inclusive), for trying things
        (i0, j0), (i1, j1) = cfg["only"]
        tiles = [(i, j) for (i, j) in tiles if i0 <= i <= i1 and j0 <= j <= j1]
    log(f"{len(tiles)} tiles ({G.ni} x {G.nj}) of {G.tile:g} m, LOD voxels {[G.v(k) for k in range(G.lods)]}, "
        f"{len(vols)} volume pieces")

    # ---- 1. marching cubes per tile per LOD, and the canonical border vertices (decided once)
    t0 = time.time()
    mc = {}
    canon = []  # per LOD: key -> row; arrays of positions/normals/weights
    for k in range(G.lods):
        reg = {}
        for (i, j) in tiles:
            r = _tile_mc(field, G, i, j, k, vols)
            if r is None:
                mc[i, j, k] = None
                continue
            idx, faces, rng = r
            (_, _), (_, _), n, (NX, NY) = G.cells(i, j, k)
            keys = _border_keys(idx, rng, n, NX, NY)
            for key in keys.values():
                reg.setdefault(key, len(reg))
            mc[i, j, k] = (idx, faces, rng, keys)
        keys = sorted(reg, key=reg.get)
        a, b, fixed = _key_geometry(keys, G, k)
        v = G.v(k)
        Fa, Fb = _lattice_values(field, a, v), _lattice_values(field, b, v)
        tt = Fa / (Fa - Fb)
        P0 = a + tt[:, None] * (b - a)
        P, N = project(field, P0, v, fixed=fixed)
        W, C = mats.weights(P, N)
        canon.append({"reg": reg, "P": P, "N": N, "W": W, "C": C, "fixed": fixed,
                      "pos": {tuple(p): r for r, p in enumerate(P)}})
    timing["marching cubes + border chains"] = time.time() - t0

    # ---- 2. skirts: how far each border vertex's chain strays from its neighbours' chains at other LODs
    t0 = time.time()
    chains = {}  # (plane key, k) -> segments (m, 2, 3) and vertex rows
    for (i, j, k), r in mc.items():
        if r is None:
            continue
        idx, faces, rng, keys = r
        be = _boundary_edges(faces)
        for (p, q) in be:
            if p not in keys or q not in keys:
                continue
            for plane in _planes(keys[p], keys[q], G, k):
                rows = (canon[k]["reg"][keys[p]], canon[k]["reg"][keys[q]])
                chains.setdefault((plane, k), set()).add(rows)
    need = [np.zeros(len(c["P"])) for c in canon]
    for (plane, k), rows in chains.items():
        segs = {kk: np.array([[canon[kk]["P"][a], canon[kk]["P"][b]] for a, b in chains[(plane, kk)]])
                for kk in range(G.lods) if (plane, kk) in chains and kk != k}
        vs = np.array(sorted({x for ab in rows for x in ab}))
        for kk, sg in segs.items():
            d = _chain_dist(canon[k]["P"][vs], sg)
            need[k][vs] = np.maximum(need[k][vs], d)
    depth = []
    for k, c in enumerate(canon):
        d = np.maximum(need[k] * 1.25 + 0.05, cfg["skirt"])
        # into the rock, in the border plane: against the surface normal with the plane's normal taken out
        dirn = -c["N"].copy()
        dirn[c["fixed"]] = 0.0
        ln = np.linalg.norm(dirn, axis=1, keepdims=True)
        dirn = np.where(ln > 0.2, dirn / np.maximum(ln, 1e-9), np.array([0, 0, -1.0]))
        # never out through the other side of the rock (a skirt under a cave roof would hang into the cave)
        thick = _thickness(field, c["P"], dirn, d, G.v(k))
        depth.append((np.minimum(d, thick), dirn, d > thick + 1e-6))
    timing["skirts"] = time.time() - t0

    # ---- 3. per tile: borders from the registry, project, decimate, re-project, weights, write
    t0 = time.time()
    t_dec = 0.0
    manifest_tiles = []
    mat = [{"name": "terrain_reference", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.0,
                                                                   "roughnessFactor": 0.92}},
           {"name": "terrain_skirt", "doubleSided": True,
            "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.0, "roughnessFactor": 0.92}}]
    stats = []
    for (i, j) in tiles:
        lo, hi = G.bounds(i, j)
        trans = _to_gltf(np.array([[lo[0], lo[1], 0.0]]))[0]
        entry = {"i": i, "j": j, "min": [float(lo[0]), float(lo[1])], "max": [float(hi[0]), float(hi[1])], "lods": []}
        zmin, zmax = np.inf, -np.inf
        for k in range(G.lods):
            r = mc[i, j, k]
            if r is None:
                entry["lods"].append(None)
                continue
            idx, faces, rng, keys = r
            v = G.v(k)
            c = canon[k]
            P = np.c_[G.origin[0] + idx[:, 0] * v, G.origin[1] + idx[:, 1] * v, idx[:, 2] * v]
            border = np.array(sorted(keys), np.int64)
            rows = np.array([c["reg"][keys[b]] for b in border], np.int64)
            inner = np.setdiff1d(np.arange(len(P)), border)
            P[inner], _ = project(field, P[inner], v)
            P[border] = c["P"][rows]
            n_mc = len(faces)
            td = time.time()
            Pd, Fd = _decimate(P, faces, cfg["error"][k], cfg["budget"][k], field)
            t_dec += time.time() - td
            # border vertices must have come through untouched
            rowd = np.array([c["pos"].get(tuple(p), -1) for p in Pd])
            on = _on_border(Pd, lo, hi)
            if np.any(on & (rowd < 0)):
                raise RuntimeError(f"tile {i},{j} LOD {k}: {int(np.sum(on & (rowd < 0)))} border vertices moved in "
                                   f"decimation")
            bd = rowd >= 0
            N = np.zeros_like(Pd)
            before = Pd.copy()
            Pd[~bd], N[~bd] = project(field, Pd[~bd], v)
            # where projecting a coarse vertex folds its faces, it stays where decimation put it
            fold = ~bd & ((_vertex_normals(Pd, Fd) * N).sum(1) < 0.3)
            if fold.any():
                Pd[fold] = before[fold]
                N[fold] = _vertex_normals(Pd, Fd)[fold]
            N[bd] = c["N"][rowd[bd]]
            W = np.zeros((len(Pd), len(mats.layers)), np.float32)
            C = np.zeros((len(Pd), 3))
            W[bd], C[bd] = c["W"][rowd[bd]], c["C"][rowd[bd]]
            W[~bd], C[~bd] = mats.weights(Pd[~bd], N[~bd])
            # skirts along shared borders (not the world's edge)
            be = _boundary_edges(Fd)
            shared = np.array([_shared(Pd[a], Pd[b], lo, hi, G) for a, b in be], bool) if len(be) else np.zeros(0, bool)
            be = be[shared] if len(be) else be
            sv = np.unique(be.ravel()) if len(be) else np.zeros(0, np.int64)
            dep, dirn, _ = depth[k]
            top = Pd[sv]
            bot = top + dirn[rowd[sv]] * dep[rowd[sv]][:, None]
            m = {int(x): r_ for r_, x in enumerate(sv)}
            SP = np.empty((2 * len(sv), 3))
            SP[0::2], SP[1::2] = top, bot
            SN = np.repeat(N[sv], 2, 0)
            SC = np.repeat(C[sv], 2, 0)
            SW = np.repeat(W[sv], 2, 0)
            sf = []
            for a, b in be:  # the face has a -> b; the skirt hangs below it, facing the same way
                ta, tb = 2 * m[int(a)], 2 * m[int(b)]
                sf += [(tb, ta, ta + 1), (tb, ta + 1, tb + 1)]
            sf = np.array(sf, np.int64).reshape(-1, 3)
            origin = np.array([lo[0], lo[1], 0.0])
            prims = [_prim(Pd - origin, N, C, W, Fd, 0, {"role": "surface"}, mats, lo, cfg)]
            if len(sf):
                prims.append(_prim(SP - origin, SN, SC, SW, sf, 1, {"role": "skirt"}, mats, lo, cfg))
            fn = f"tile_{i}_{j}_lod{k}.glb"
            write_glb(out / fn, f"tile_{i}_{j}_lod{k}", prims, trans, mat,
                      extras={"tile": [i, j], "lod": k, "voxel": v})
            if k == int(cfg["collision"]):
                cf = f"collision_{i}_{j}.glb"
                write_glb(out / cf, f"collision_{i}_{j}", [{"attrs": {"POSITION": _to_gltf(Pd - origin)},
                                                            "indices": Fd}], trans, None,
                          extras={"tile": [i, j], "collision": True, "from_lod": k})
                entry["collision"] = cf
            zmin, zmax = min(zmin, float(Pd[:, 2].min())), max(zmax, float(Pd[:, 2].max()))
            entry["lods"].append({"file": fn, "voxel": v, "triangles": int(len(Fd)), "skirt_triangles": int(len(sf)),
                                  "marching_cubes_triangles": int(n_mc), "bytes": (out / fn).stat().st_size})
            stats.append((i, j, k, len(Fd), len(sf), n_mc, (out / fn).stat().st_size))
        entry["zmin"], entry["zmax"] = zmin, zmax
        entry["volumes"] = sorted({vol.name.split(":")[0] for vol in vols
                                   if vol.touches(np.array([lo[0], lo[1], -1e9]), np.array([hi[0], hi[1], 1e9]))})
        manifest_tiles.append(entry)
    timing["tiles (project, decimate, write)"] = time.time() - t0
    timing["of which decimation"] = t_dec

    # ---- 4. heightmap and splat tiles on the same grid
    t0 = time.time()
    hm = int(cfg["heightmap"])
    hrange = [float(np.nanmin(T.H)), float(np.nanmax(T.H))]
    if hm:
        (out / "heightmaps").mkdir(exist_ok=True)
        for e in manifest_tiles:
            lo = np.array(e["min"])
            s = np.linspace(0, G.tile, hm)
            X, Y = np.meshgrid(lo[0] + s, lo[1] + s)
            h, _ = field.column(X.ravel(), Y.ravel())
            h = h.reshape(hm, hm)[::-1].astype(np.float32)  # north-up rows
            np.save(out / "heightmaps" / f"height_{e['i']}_{e['j']}.npy", h)
            q = np.round((h - hrange[0]) / (hrange[1] - hrange[0]) * 65535).clip(0, 65535).astype(np.uint16)
            Image.fromarray(q).save(out / "heightmaps" / f"height_{e['i']}_{e['j']}.png")
            e["heightmap"] = f"heightmaps/height_{e['i']}_{e['j']}.npy"
    sp = int(cfg["splat"])
    if sp:
        (out / "splats").mkdir(exist_ok=True)
        mg = int(cfg["splat_margin"])
        Nn = sp + 2 * mg
        d = G.tile / sp
        for e in manifest_tiles:
            lo = np.array(e["min"])
            c = lo[0] + (np.arange(Nn) - mg + 0.5) * d
            r = lo[1] + (np.arange(Nn) - mg + 0.5) * d
            X, Y = np.meshgrid(c, r[::-1])  # row 0 = north
            h, s = field.column(X.ravel(), Y.ravel())
            P = np.c_[X.ravel(), Y.ravel(), h]
            _, g = field.value_gradient(P, 0.125)
            Nm = g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12)
            W, _ = mats.weights(P, Nm)
            files = []
            for g4 in range(0, len(mats.layers), 4):
                ch = W[:, g4:g4 + 4]
                ch = np.c_[ch, np.zeros((len(ch), 4 - ch.shape[1]))]
                img = (np.clip(ch, 0, 1) * 255 + 0.5).astype(np.uint8).reshape(Nn, Nn, 4)
                fn = f"splats/splat{g4 // 4}_{e['i']}_{e['j']}.png"
                Image.fromarray(img, "RGBA").save(out / fn)
                files.append(fn)
            e["splats"] = files
    timing["heightmaps + splats"] = time.time() - t0

    # ---- 5. trees and the manifest
    from . import terrain_design as design
    inst = design.trees(T)
    with open(out / "trees.csv", "w") as f:
        f.write("x,y,z,kind,layer\n")
        layers = getattr(T, "tree_layers", {})
        zs = field.column(inst[:, 0], inst[:, 1])[0] if len(inst) else []
        for (x, y, _, li), z in zip(inst, zs):
            nm, kind = layers.get(int(li), ("", ""))
            f.write(f"{x:.2f},{y:.2f},{z:.2f},{kind},{nm}\n")
    groups = [mats.layers[g:g + 4] for g in range(0, len(mats.layers), 4)]
    manifest = {
        "format": "hifipushie terrain tiles 1",
        "units": "m",
        "axes": {"world": "x east, y north, z up", "gltf": "glTF x = east, y = up, z = -north (node translation = "
                                                          "the tile's south-west corner; vertices local to it)"},
        "origin": G.origin.tolist(), "tile_size": G.tile, "grid": [G.ni, G.nj],
        "world_min": G.lo.tolist(), "world_max": G.hi.tolist(),
        "trimmed": "the extent was trimmed to whole coarsest voxels" if G.trimmed else "",
        "lods": [{"lod": k, "voxel": G.v(k), "error_m": cfg["error"][k], "budget_triangles": cfg["budget"][k]}
                 for k in range(G.lods)],
        "skirts": "primitive 1 of each tile (extras.role = skirt, double-sided material): each shared border's chain "
                  "extruded into the rock by at least how far the neighbours' LOD chains differ there",
        "collision": f"collision_<i>_<j>.glb: LOD {cfg['collision']} surface, no skirts, positions only",
        "sea_level": _sea(T),
        "materials": {
            "layers": [{"name": nm, **LAYERS[nm], "weights": f"_WEIGHTS{g}", "channel": c}
                       for g, grp in enumerate(groups) for c, nm in enumerate(grp)],
            "blend": "layer weights per vertex (_WEIGHTS0, _WEIGHTS1 ... vec4, sum 1) and per tile splat PNGs "
                     "(RGBA = the same layers in the same groups of 4); layers are world-space/triplanar tiling "
                     "textures at `scale` metres",
            "reference": "COLOR_0 is a display colour (linear) with a plain matte material, so tiles look right in "
                         "any glTF viewer",
            "splat_uv": f"splats cover the tile plus {cfg['splat_margin']} texels into the neighbours each side, "
                        f"row 0 north; texel centre (c, r) at x = min.x + (c - {cfg['splat_margin']} + 0.5) * "
                        f"tile / {sp}, y = max.y - (r - {cfg['splat_margin']} + 0.5) * tile / {sp}" if sp else "",
        },
        "heightmaps": {"samples": hm, "spacing": G.tile / max(hm - 1, 1), "format": "float32 .npy absolute metres, "
                       "north-up; .png 16-bit over the range", "range": hrange,
                       "note": "the 2.5D ground only (volumes aren't in heightmaps); edges shared with neighbours"}
        if hm else None,
        "trees": "trees.csv (x, y, z, kind, layer), world metres",
        "volumes": notes,
        "tiles": manifest_tiles,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    timing["total before check"] = time.time() - t_all
    t0 = time.time()
    check = seam_check(out)
    timing["seam check"] = time.time() - t0
    manifest["seam_check"] = check["summary"]
    manifest["timing_s"] = {k: round(v, 2) for k, v in timing.items()}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    if check["failures"]:
        raise RuntimeError("seam check FAILED:\n" + "\n".join(check["failures"][:30]))
    return {"out": str(out), "manifest": manifest, "stats": stats, "timing": timing, "check": check}


def summary(r) -> str:
    """A short text report of an export_tiles result."""
    M = r["manifest"]
    lines = [f"3D tiles in {r['out']}: {M['grid'][0]} x {M['grid'][1]} tiles of {M['tile_size']:g} m"]
    for k, L in enumerate(M["lods"]):
        tris = [t["lods"][k]["triangles"] for t in M["tiles"] if t["lods"][k]]
        size = sum(t["lods"][k]["bytes"] for t in M["tiles"] if t["lods"][k])
        lines.append(f"LOD {k} (voxel {L['voxel']:g} m): {sum(tris)} triangles, per tile {min(tris)}-{max(tris)} "
                     f"(median {int(np.median(tris))}), {size / 1e6:.1f} MB")
    lines += [f"volume {n}" for n in M["volumes"]]
    sc = M["seam_check"]
    lines.append(f"seam check: {sc['failures']} failures; shared edges {sc['shared_edges']}, border normals within "
                 f"{sc['border_normal_max_deg']} deg, LOD gaps up to {sc['lod_pairs_max_gap_m']} m all under skirts")
    lines.append("timing (s): " + ", ".join(f"{k} {v}" for k, v in M["timing_s"].items()))
    return "\n".join(lines)


def _prim(P, N, C, W, F, material, extras, mats, lo, cfg):
    attrs = {"POSITION": _to_gltf(P), "NORMAL": _to_gltf(N), "COLOR_0": _linear(C)}
    for g in range(0, W.shape[1], 4):
        w = W[:, g:g + 4]
        attrs[f"_WEIGHTS{g // 4}"] = np.c_[w, np.zeros((len(w), 4 - w.shape[1]))]
    sp = int(cfg["splat"])
    if sp:  # splat UVs: the tile's texture, its margin into the neighbours
        mg = int(cfg["splat_margin"])
        Nn = sp + 2 * mg
        u = (P[:, 0] / cfg["tile"] * sp + mg) / Nn
        vv = 1 - (P[:, 1] / cfg["tile"] * sp + mg) / Nn
        attrs["TEXCOORD_0"] = np.c_[u, vv]
    return {"attrs": attrs, "indices": F, "material": material, "extras": extras}


def _vertex_normals(P, F):
    fn = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    vn = np.zeros_like(P)
    for c in range(3):
        np.add.at(vn, F[:, c], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-20)


def _on_border(P, lo, hi):
    return (P[:, 0] == lo[0]) | (P[:, 0] == hi[0]) | (P[:, 1] == lo[1]) | (P[:, 1] == hi[1])


def _shared(a, b, lo, hi, G):
    """Is edge a-b on a border this tile shares with a neighbour (not the world's edge)?"""
    for ax, lim in ((0, lo[0]), (0, hi[0]), (1, lo[1]), (1, hi[1])):
        if a[ax] == lim and b[ax] == lim:
            return G.lo[ax] < lim < G.hi[ax]
    return False


def _planes(ka, kb, G, k):
    """The border planes (axis, lattice index, tile span index) both endpoints of a border edge lie on."""
    v = G.v(k)
    n = int(round(G.tile / v))
    NX, NY = int(round(G.span[0] / v)), int(round(G.span[1] / v))
    out = []
    for ax, lim in ((0, NX), (1, NY)):
        ca, cb = ka[1 + ax], kb[1 + ax]
        if ka[0] != ax and kb[0] != ax and ca == cb and (ca % n == 0 or ca == lim):
            other = 1 - ax
            span = min(ka[1 + other], kb[1 + other]) // n
            out.append((ax, round(ca * v, 6), span))  # world position of the plane, in metres from the origin
    return out


def _thickness(field, P, d, want, v):
    """How far each point can go along d before it leaves the rock (capped at `want`), minus a margin."""
    out = want.copy()
    step = v / 2
    s = step
    alive = np.ones(len(P), bool)
    while alive.any() and s <= want.max() + step:
        k = np.flatnonzero(alive & (s <= want + step))
        if not len(k):
            break
        f = field.value(P[k] + d[k] * s)
        leave = f > 0
        out[k[leave]] = np.minimum(out[k[leave]], max(s - step, 0.0) + 0.25 * step)
        alive[k[leave]] = False
        s += step
    return out


# ---------------------------------------------------------------- the seam check

def seam_check(out_dir, normal_deg=1.0) -> dict:
    """Read the written tiles back and check: (1) border vertices identical across every shared edge, per LOD;
    (2) each LOD's tiles joined are watertight and consistently oriented except at the world's edge; (3) matched
    border vertices carry the same normal (under `normal_deg`), and the crease across seams is no worse than inside
    tiles; (4) every neighbouring LOD pair: chains' gaps covered by the skirts; (5) heightmap edges identical."""
    out = Path(out_dir)
    M = json.loads((out / "manifest.json").read_text())
    T = M["tile_size"]
    lods = len(M["lods"])
    # the edge of what was exported (the world's edge, or a block's when only some tiles were written)
    wlo = np.min([e["min"] for e in M["tiles"]], 0)
    whi = np.max([e["max"] for e in M["tiles"]], 0)
    failures, summary = [], {}
    tiles = {(e["i"], e["j"]): e for e in M["tiles"]}
    data = {}
    for (i, j), e in tiles.items():
        for k, L in enumerate(e["lods"]):
            if L is None:
                continue
            tr, prims = read_glb(out / L["file"])
            origin = _from_gltf(tr[None])[0]
            d = {}
            for p in prims:
                P = _from_gltf(p["POSITION"].astype(np.float64)) + origin
                d[p["extras"].get("role", "surface")] = (P, _from_gltf(p["NORMAL"].astype(np.float64)), p["indices"])
            data[i, j, k] = d
    # (2) watertight per LOD
    for k in range(lods):
        allP, allF, off = [], [], 0
        for (i, j) in tiles:
            if (i, j, k) not in data:
                continue
            P, _, F = data[i, j, k]["surface"]
            allP.append(P)
            allF.append(F + off)
            off += len(P)
        P = np.vstack(allP)
        F = np.vstack(allF)
        _, uid = np.unique(P, axis=0, return_inverse=True)
        F = uid.ravel()[F]
        F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])]
        e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
        nmax = int(F.max()) + 1
        fwd = e[:, 0] * nmax + e[:, 1]
        rev = e[:, 1] * nmax + e[:, 0]
        und = np.minimum(fwd, rev)
        u, cnt = np.unique(und, return_counts=True)
        fu, fcnt = np.unique(fwd, return_counts=True)
        dup_dir = int(np.sum(fcnt > 1))  # the same directed edge twice: flipped or overlapping faces
        Pu = np.zeros((nmax, 3))
        Pu[uid.ravel()] = np.vstack(allP)
        single = u[cnt == 1]
        a, b = single // nmax, single % nmax
        at_edge = (_at_world_edge(Pu[a], wlo, whi) & _at_world_edge(Pu[b], wlo, whi))
        open_inside = int(np.sum(~at_edge))
        nonman = int(np.sum(cnt > 2))
        summary[f"lod{k}_watertight"] = {"vertices": int(nmax), "triangles": int(len(F)), "open_edges_inside": open_inside,
                                          "open_edges_world_edge": int(np.sum(at_edge)), "non_manifold_edges": nonman,
                                          "same_direction_edges": dup_dir}
        if open_inside or nonman or dup_dir:
            bad = np.r_[a[~at_edge], u[cnt > 2] // nmax, fu[fcnt > 1] // nmax]
            ex = Pu[bad[:3]].round(2).tolist()
            failures.append(f"LOD {k}: {open_inside} open edges inside the world, {nonman} non-manifold, "
                            f"{dup_dir} doubled directed edges (e.g. at {ex})")
    # (1, 3, 4) shared edges
    worst_n, worst_gap, n_edges, uncovered = 0.0, 0.0, 0, 0
    crease_seam, crease_in = [], []
    for (i, j) in tiles:
        for (di, dj, ax) in ((1, 0, 0), (0, 1, 1)):
            if (i + di, j + dj) not in tiles:
                continue
            lim = np.array(tiles[i, j]["max"])[ax]
            n_edges += 1
            for k in range(lods):
                A, B = data.get((i, j, k)), data.get((i + di, j + dj, k))
                if A is None or B is None:
                    if (A is None) != (B is None):
                        failures.append(f"tiles {i},{j} / {i + di},{j + dj} LOD {k}: one side has no mesh")
                    continue
                ca, na = _on_plane(A["surface"], ax, lim)
                cb, nb = _on_plane(B["surface"], ax, lim)
                sa = {tuple(p): r for r, p in enumerate(ca)}
                sb = {tuple(p): r for r, p in enumerate(cb)}
                if set(sa) != set(sb):
                    failures.append(f"tiles {i},{j} / {i + di},{j + dj} LOD {k}: border vertices differ "
                                    f"({len(set(sa) - set(sb))} / {len(set(sb) - set(sa))} unmatched)")
                    continue
                ea, eb = _plane_edges(A["surface"], ax, lim), _plane_edges(B["surface"], ax, lim)
                if ea != eb:
                    failures.append(f"tiles {i},{j} / {i + di},{j + dj} LOD {k}: border edges differ")
                common = list(sa)
                if common:
                    va = na[[sa[p] for p in common]]
                    vb = nb[[sb[p] for p in common]]
                    ang = np.degrees(np.arccos(np.clip((va * vb).sum(1), -1, 1))).max()
                    worst_n = max(worst_n, float(ang))
                    if ang > normal_deg:
                        failures.append(f"tiles {i},{j} / {i + di},{j + dj} LOD {k}: normals differ by {ang:.2f} deg")
                    if k == 0:
                        crease_seam.append(_crease(A["surface"], B["surface"], ax, lim))
            # (4) LOD pairs: the gap between chains must be covered by a skirt
            for ka in range(lods):
                for kb in range(lods):
                    if ka == kb:
                        continue
                    A, B = data.get((i, j, ka)), data.get((i + di, j + dj, kb))
                    if A is None or B is None:
                        continue
                    segA, segB = _plane_segs(A["surface"], ax, lim), _plane_segs(B["surface"], ax, lim)
                    if not len(segA) or not len(segB):
                        if len(segA) != len(segB):
                            failures.append(f"tiles {i},{j} LOD {ka} / {i + di},{j + dj} LOD {kb}: a chain on one "
                                            f"side only")
                        continue
                    ptsA = np.unique(segA.reshape(-1, 3), axis=0)
                    gap = _chain_dist(ptsA, segB)
                    depA = _skirt_depth(A, ptsA)
                    ptsB = np.unique(segB.reshape(-1, 3), axis=0)
                    depB = _skirt_depth(B, ptsB)
                    _, near = cKDTree(ptsB).query(ptsA)
                    cover = np.maximum(depA, depB[near])
                    bad = gap > cover + 1e-3
                    worst_gap = max(worst_gap, float(gap.max()))
                    if bad.any():
                        uncovered += int(bad.sum())
                        failures.append(f"tiles {i},{j} LOD {ka} / {i + di},{j + dj} LOD {kb}: {int(bad.sum())} chain "
                                        f"points with a gap ({gap[bad].max():.2f} m) deeper than the skirts "
                                        f"({cover[bad].min():.2f} m)")
    for (i, j) in tiles:
        if (i, j, 0) in data:
            crease_in.append(_crease_inside(data[i, j, 0]["surface"]))
    summary["shared_edges"] = n_edges
    summary["border_normal_max_deg"] = round(worst_n, 4)
    cs = np.concatenate([c for c in crease_seam if len(c)]) if crease_seam else np.zeros(0)
    ci = np.concatenate([c for c in crease_in if len(c)]) if crease_in else np.zeros(0)
    summary["lod0_face_crease_deg"] = {"across_seams_p50_p99": [round(float(np.percentile(cs, q)), 2) for q in (50, 99)]
                                       if len(cs) else None,
                                       "inside_tiles_p50_p99": [round(float(np.percentile(ci, q)), 2) for q in (50, 99)]
                                       if len(ci) else None}
    summary["lod_pairs_max_gap_m"] = round(worst_gap, 3)
    summary["lod_pairs_uncovered_points"] = uncovered
    # (5) heightmaps
    hm_bad = 0
    for (i, j), e in tiles.items():
        if not e.get("heightmap"):
            continue
        h = np.load(out / e["heightmap"])
        if (i + 1, j) in tiles:
            h2 = np.load(out / tiles[i + 1, j]["heightmap"])
            hm_bad += int(np.any(h[:, -1] != h2[:, 0]))
        if (i, j + 1) in tiles:
            h2 = np.load(out / tiles[i, j + 1]["heightmap"])
            hm_bad += int(np.any(h[0, :] != h2[-1, :]))  # rows north-up: this tile's north row = the next's south
    summary["heightmap_edges_differing"] = hm_bad
    if hm_bad:
        failures.append(f"{hm_bad} heightmap tile edges differ from their neighbours'")
    summary["failures"] = len(failures)
    (out / "seam_check.json").write_text(json.dumps({"summary": summary, "failures": failures}, indent=1))
    return {"summary": summary, "failures": failures}


def _at_world_edge(P, lo, hi):
    return (P[:, 0] == lo[0]) | (P[:, 0] == hi[0]) | (P[:, 1] == lo[1]) | (P[:, 1] == hi[1])


def _on_plane(surf, ax, lim):
    P, N, _ = surf
    k = P[:, ax] == lim
    return P[k], N[k]


def _plane_edges(surf, ax, lim):
    P, _, F = surf
    be = _boundary_edges(F)
    on = (P[be[:, 0], ax] == lim) & (P[be[:, 1], ax] == lim)
    return {frozenset((tuple(P[a]), tuple(P[b]))) for a, b in be[on]}


def _plane_segs(surf, ax, lim):
    P, _, F = surf
    be = _boundary_edges(F)
    on = (P[be[:, 0], ax] == lim) & (P[be[:, 1], ax] == lim)
    return np.stack([P[be[on, 0]], P[be[on, 1]]], 1) if on.any() else np.zeros((0, 2, 3))


def _skirt_depth(tile, pts):
    if "skirt" not in tile:
        return np.zeros(len(pts))
    SP = tile["skirt"][0]
    top, bot = SP[0::2], SP[1::2]
    dep = np.linalg.norm(bot - top, axis=1)
    d, k = cKDTree(top).query(pts)
    return np.where(d < 1e-6, dep[k], 0.0)


def _face_normals(P, F):
    n = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-20)


def _crease(A, B, ax, lim):
    """Angle between the faces either side of each seam edge (LOD0)."""
    out = []
    PA, _, FA = A
    PB, _, FB = B
    nA, nB = _face_normals(PA, FA), _face_normals(PB, FB)

    def edge_faces(P, F, n):
        m = {}
        near = np.flatnonzero((P[F, ax] == lim).sum(1) >= 2)
        for f in near:
            tri = F[f]
            for a, b in ((0, 1), (1, 2), (2, 0)):
                pa, pb = P[tri[a]], P[tri[b]]
                if pa[ax] == lim and pb[ax] == lim:
                    m[frozenset((tuple(pa), tuple(pb)))] = n[f]
        return m

    ma, mb = edge_faces(PA, FA, nA), edge_faces(PB, FB, nB)
    for e, na in ma.items():
        if e in mb:
            out.append(np.degrees(np.arccos(np.clip(na @ mb[e], -1, 1))))
    return np.array(out)


def _crease_inside(surf):
    P, _, F = surf
    n = _face_normals(P, F)
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    fid = np.tile(np.arange(len(F)), 3)
    key = np.minimum(e[:, 0], e[:, 1]) * (len(P) + 1) + np.maximum(e[:, 0], e[:, 1])
    o = np.argsort(key, kind="stable")
    ks, fs = key[o], fid[o]
    same = ks[1:] == ks[:-1]
    a, b = fs[:-1][same], fs[1:][same]
    return np.degrees(np.arccos(np.clip((n[a] * n[b]).sum(1), -1, 1)))


# ---------------------------------------------------------------- views

def border_segments(out_dir, lod=0):
    """The shared tile borders as the meshes have them: every surface edge on a border between two tiles."""
    out = Path(out_dir)
    M = json.loads((out / "manifest.json").read_text())
    wlo = np.min([e["min"] for e in M["tiles"]], 0)
    whi = np.max([e["max"] for e in M["tiles"]], 0)
    segs = []
    for e in M["tiles"]:
        L = e["lods"][lod]
        if L is None:
            continue
        tr, prims = read_glb(out / L["file"])
        P = _from_gltf(prims[0]["POSITION"].astype(np.float64)) + _from_gltf(tr[None])[0]
        be = _boundary_edges(prims[0]["indices"])
        a, b = P[be[:, 0]], P[be[:, 1]]
        keep = np.zeros(len(be), bool)
        for ax, lim in ((0, e["min"][0]), (0, e["max"][0]), (1, e["min"][1]), (1, e["max"][1])):
            if wlo[ax] < lim < whi[ax]:
                keep |= (a[:, ax] == lim) & (b[:, ax] == lim)
        segs.append(np.stack([a[keep], b[keep]], 1))
    return np.concatenate(segs) if segs else np.zeros((0, 2, 3))


def render_tiles(T, out_dir, views, lod=0, size=(1400, 800), samples=48, trees=True, box=None):
    """Cycles renders of the written tiles, imported by Blender's glTF importer. views: {"name", "eye": address |
    [x, y] | [x, y, z], "lift" (m above the ground or the sea), "look": address | [x, y, z], "fov", "sun": [bearing,
    height], "borders": bool, "out"}. box: [[x0, y0], [x1, y1]]: only tiles (and trees) inside. lod: a level, or
    "checker" (LOD 0 and the coarsest alternating, to see the skirts at work)."""
    import subprocess
    out = Path(out_dir)
    M = json.loads((out / "manifest.json").read_text())
    glbs = []
    for e in M["tiles"]:
        if box and (e["max"][0] < box[0][0] or e["min"][0] > box[1][0] or e["max"][1] < box[0][1]
                    or e["min"][1] > box[1][1]):
            continue
        k = (len(M["lods"]) - 1) * ((e["i"] + e["j"]) % 2) if lod == "checker" else lod  # mixed LODs: seams show
        if e["lods"][k]:
            glbs.append(str(out / e["lods"][k]["file"]))
    jobs = []
    sea = M.get("sea_level")
    for v in views:
        if isinstance(v["eye"], list) and len(v["eye"]) == 3:
            eye = list(map(float, v["eye"]))
        else:
            xy, h, _ = T.address(v["eye"])
            if sea is not None:
                h = max(h, sea)
            eye = [float(xy[0]), float(xy[1]), h + v.get("lift", 1.7)]
        if isinstance(v["look"], list) and len(v["look"]) == 3:
            look = list(map(float, v["look"]))
        else:
            xy, h, _ = T.address(v["look"])
            look = [float(xy[0]), float(xy[1]), h]
        jobs.append({"eye": eye, "look": look, "fov": v.get("fov", 55), "sun": v.get("sun", [225, 30]),
                     "borders": v.get("borders", False), "out": str(Path(v["out"]).resolve())})
    job = {"glbs": glbs, "sea": sea, "size": list(size), "samples": samples, "views": jobs,
           "trees": str(out / "trees.csv") if trees else None, "tree_box": box}
    if any(v.get("borders") for v in views):
        np.savez(out / "borders.npz", segs=border_segments(out, 0 if lod == "checker" else lod))
        job["borders"] = str(out / "borders.npz")
    (out / "render_job.json").write_text(json.dumps(job))
    script = Path(__file__).with_name("blender_tiles.py")
    r = subprocess.run(["blender", "-b", "--factory-startup", "--python", str(script), "--",
                        str(out / "render_job.json")], capture_output=True, text=True)
    if r.returncode or "Traceback" in r.stdout + r.stderr:
        raise RuntimeError(r.stderr[-2000:] + r.stdout[-3000:])
    return [j["out"] for j in jobs]
