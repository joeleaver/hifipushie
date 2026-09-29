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

from . import noise, terrain_sharp

DEFAULTS = {
    "tile": 64.0,          # metres a side
    "voxel": 0.5,          # the meshing voxel (divides the tile); coarser LODs are LOD0 decimated
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
    "mode": "cliffs",      # "cliffs": heightmap ground tiles + 3D cliff meshes over steep ground and openings
                           # (terrain_cliffs); "full": the whole ground as 3D mesh tiles
    "sharp": True,         # creases on mesh edges (extended marching cubes, terrain_sharp)
    "cliff_slope": 42.0,   # (cliffs) degrees: steeper ground gets a 3D cliff mesh
    "cliff_margin": 4.0,   # (cliffs) m the region reaches past the steep ground and round openings
    "cave_wall": 3.0,      # (cliffs) m of rock kept round every void in a cliff shell
    "maps": True,          # baked maps per tile and LOD (terrain_bake): normal, ORM, base colour, height, weights
    "texel_density": [16.0, 6.0, 2.5],  # texels per metre per LOD (a tile's atlas is capped at texture_max)
    "texture_max": 2048,
    "ground_density": 4.0,  # (cliffs) the ground tiles' maps, texels per metre at LOD 0
    "micro": 1.0,          # bake-only fine rock relief (facets, cracks, laminae below the voxel); 0 = none
}

# ground materials: what each cover type lays on the ground (tree layers: the forest floor under them)
LAYER_OF = {"meadow": "grass", "grass": "grass", "orchard": "grass", "forest": "forest_floor",
            "conifer": "forest_floor", "deciduous": "forest_floor", "rock": "rock", "scree": "rock", "sand": "sand",
            "mud": "earth", "snow": "snow"}
LAYERS = {  # reference look (sRGB colour, roughness) and a triplanar tiling scale (m) for engines
    "grass": {"color": [0.36, 0.47, 0.20], "roughness": 0.95, "scale": 3.0},
    "forest_floor": {"color": [0.27, 0.22, 0.15], "roughness": 0.95, "scale": 3.0},
    "sand": {"color": [0.72, 0.65, 0.48], "roughness": 0.9, "scale": 2.0},
    "rock": {"color": [0.36, 0.34, 0.31], "roughness": 0.85, "scale": 6.0},  # (the heightfield views' rock)
    "wet_rock": {"color": [0.17, 0.16, 0.15], "roughness": 0.35, "scale": 6.0},
    "earth": {"color": [0.42, 0.34, 0.24], "roughness": 0.95, "scale": 2.5},
    "snow": {"color": [0.93, 0.94, 0.96], "roughness": 0.7, "scale": 4.0},
}


def smin(a, b, k):
    if np.isscalar(k) and k <= 0:
        return np.minimum(a, b)
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * h * k * (1.0 / 6.0)


def smax(a, b, k):
    return -smin(-a, -b, k)


def smoothstep(e0, e1, x):
    u = np.clip((x - e0) / (e1 - e0), 0, 1)
    return u * u * (3 - 2 * u)


# ---------------------------------------------------------------- volumes

NORMAL_H = 0.125  # the normals' stencil, voxels: exact on each side of a crease (split_normals splits at creases)
NEAR = 2.5  # how far from a volume's surface the rock character reaches (m)


class Tube:
    """A passage along a polyline of nodes: an elliptical cross-section (half width rw across, rh up) that varies
    node to node, rounded ends, optionally cut flat below `floor` (per node). One node is an ellipsoid (a chamber).
    Arches, sea caves and notches are all tubes; a cave engine would be a graph of them."""

    def __init__(self, name, nodes, rw, rh, floor=None, op="subtract", blend=1.0, rough=0.4, rough_scale=3.0, seed=0,
                 roof=None, beds=None, relief=1.0):
        self.name, self.op, self.blend = name, op, float(blend)
        self.nodes = np.atleast_2d(np.asarray(nodes, float))
        n = len(self.nodes)
        self.rw = np.broadcast_to(np.asarray(rw, float), (n,)).copy()
        self.rh = np.broadcast_to(np.asarray(rh, float), (n,)).copy()
        self.floor = None if floor is None else np.broadcast_to(np.asarray(floor, float), (n,)).copy()
        # a flat roof (per node: a bedding plane the passage spread along) and beds in the walls: {"bed": m thick,
        # "amp": m each bed stands out or back, "off": xy -> the beds' shift in height (the rock's own beds)}
        self.roof = None if roof is None else np.broadcast_to(np.asarray(roof, float), (n,)).copy()
        self.beds = beds
        self.relief = float(relief)  # how much of the rock character (facets) its walls take
        self.rough, self.rough_scale, self.seed = float(rough), float(rough_scale), int(seed)
        rough = self.rough + (1.6 * beds["amp"] if beds else 0.0)
        # the box reaches past everything the tube does to the field (its blend, and the rock character's reach,
        # NEAR): cut off inside that reach, the field jumped at the box's edge (shards). The ellipse's distance
        # under-reads along its long axis by the aspect ratio, hence the factor.
        aspect = float(np.max(np.maximum(self.rw / self.rh, self.rh / self.rw)))
        r = np.maximum(self.rw, self.rh).max() + (self.blend + rough + NEAR + 0.5) * aspect
        self.lo, self.hi = self.nodes.min(0) - r, self.nodes.max(0) + r
        if self.floor is not None:
            self.lo[2] = max(self.lo[2], float(self.floor.min()) - self.blend - rough - 0.5)

    def sd(self, p, detail=False):
        """Signed distance (roughly: the ellipse's is a bound). With detail: also each point's height above the floor
        of the nearest segment (inf with no floor) and that segment's smaller radius (for how much rock relief
        a passage's walls take)."""
        best = np.full(len(p), np.inf)
        above = np.full(len(p), np.inf)
        size = np.zeros(len(p))
        rough = self.rough * (2 * noise.fbm(p, self.rough_scale, 3, seed=self.seed) - 1) if self.rough > 0 else 0.0
        if self.beds:
            rough = rough + wall_beds(p, self.beds)
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
            # walls and roof rough, the floor flat (rough floors made a cave's floor a scramble of 1 m steps)
            dd = (np.sqrt((u / rw) ** 2 + (v / rh) ** 2 + (w / rw) ** 2) - 1) * np.minimum(rw, rh) + rough
            if self.roof is not None:  # flat along the bedding plane, rounding into the walls over ~a voxel
                rf = self.roof[i] + s * (self.roof[j] - self.roof[i])
                dd = smax(dd, p[:, 2] - rf, np.minimum(0.6, 0.3 * rh))
            ab = np.full(len(p), np.inf)
            if self.floor is not None:
                fl = self.floor[i] + s * (self.floor[j] - self.floor[i])
                # the floor meets the walls in a fillet about a voxel round, not a hard crease: a vertex on a
                # crease takes one side's normal from the field and the faces on the other side shade black
                dd = smax(dd, fl - p[:, 2], np.minimum(0.6, 0.3 * rh))
                ab = p[:, 2] - fl
            m = dd < best
            best = np.where(m, dd, best)
            above = np.where(m, ab, above)
            size = np.where(m, np.minimum(rw, rh), size)
        return (best, above, size) if detail else best

    def touches(self, lo, hi):
        return bool(np.all(self.hi >= lo) and np.all(self.lo <= hi))


class Mound:
    """A low cone of fallen blocks standing on a floor (breakdown under a skylight or in a collapse pit): `radius` at
    its foot, `height` at its top, rough. Added to the rock (op "add")."""

    def __init__(self, name, at, radius, height, blend=0.6, rough=0.25, rough_scale=1.5, seed=0):
        self.name, self.op, self.blend, self.relief = name, "add", float(blend), 0.0
        self.at, self.r, self.h = np.asarray(at, float), float(radius), float(height)
        self.rough, self.rough_scale, self.seed = float(rough), float(rough_scale), int(seed)
        m = self.r + self.blend + self.rough + NEAR + 1.0
        self.lo = self.at - np.array([m, m, 1.5 + self.blend + self.rough])
        self.hi = self.at + np.array([m, m, self.h + m])

    def sd(self, p, detail=False):
        q = p - self.at
        rxy = np.hypot(q[:, 0], q[:, 1])
        L = math.hypot(self.r, self.h)
        side = (rxy * self.h + q[:, 2] * self.r - self.h * self.r) / L  # the cone's flank
        d = smax(side, -q[:, 2] - 0.3, 0.3)  # (its foot sunk a little into the floor)
        if self.rough > 0:
            d = d + self.rough * (2 * noise.fbm(p, self.rough_scale, 3, seed=self.seed) - 1)
        if detail:
            return d, np.full(len(p), np.inf), np.full(len(p), self.r)
        return d

    def touches(self, lo, hi):
        return bool(np.all(self.hi >= lo) and np.all(self.lo <= hi))


def wall_beds(p, b):
    """Beds in a passage's walls, as an offset to its distance (+ rock stands out: a ledge; - it's set back): each
    bed `amp` proud or recessed on its own, a notch along every bedding plane. Continuous: each bed hands over to the
    next over >= 0.45 m either side (a step in the field meshed as shards, a sharper one as teeth)."""
    off = b["off"](p[:, :2]) if b.get("off") else 0.0
    z = (p[:, 2] + off) / b["bed"]
    kb = np.floor(z).astype(np.int64)
    f = z - kb
    edge = np.minimum(f, 1 - f)
    be = max(0.12, 0.45 / b["bed"])
    o = lambda k: 2 * noise._hash(k, k * 0 + 11, k * 0, int(b.get("seed", 0))) - 1
    lower = f < 0.5
    nb = np.where(lower, kb - 1, kb + 1)
    u = smoothstep(-be, be, np.where(lower, f, f - 1))
    stand = np.where(lower, o(nb) * (1 - u) + o(kb) * u, o(kb) * (1 - u) + o(nb) * u)
    return b["amp"] * (stand - 0.6 * (1 - smoothstep(0.0, 2 * be, edge)))


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
            floor = float(v.get("floor", (sea - 1.0) if sea is not None else T.height(at) - 6))
            roof_min = float(v.get("roof", 2.0))
            # where along the land near `at` the arch is shortest: real sea arches go through a thin neck, short and
            # tall (a fixed spot put a 38 m tunnel through a 30 m point)
            R = float(v.get("search", 30.0))
            g = np.arange(-R, R + 0.1, 3.0)
            cands = [at] + [at + np.array([dx, dy]) for dx in g for dy in g if 0 < dx * dx + dy * dy <= R * R]
            best = None
            for c in cands:
                top = T.height(c)
                height = float(v.get("height", 0.65 * (top - floor)))
                if top - floor - height < roof_min or height < 2:
                    continue
                ts = [_bearing(T, v["toward"], c)] if "toward" in v else [
                    np.array([math.sin(math.radians(b_)), math.cos(math.radians(b_))]) for b_ in range(0, 180, 10)]
                for t in ts:
                    s1 = _daylight(T, c, t, floor + 0.5 * height, reach=80)
                    s2 = _daylight(T, c, -t, floor + 0.5 * height, reach=80)
                    if s1 is None or s2 is None:
                        continue
                    # short for its height (length over height), near `at`
                    score = (s1 + s2) / height + 0.01 * float(np.linalg.norm(c - at))
                    if best is None or score < best[0]:
                        best = (score, c, t, s1, s2, top, height)
            if best is None:
                raise ValueError(f"volume {name!r}: no place within {R:.0f} m of {v['at']!r} where an arch fits (land "
                                 f"that comes out into the open both ways, {roof_min:g} m of roof over it)")
            _, c, t, s1, s2, top, height = best
            w = float(v.get("width", min(8.0, 0.8 * height)))
            # irregular: mouths flared and taller than the middle, the line bending a little
            side = np.array([-t[1], t[0]])
            u = np.linspace(-1, 1, 5)
            along = np.where(u < 0, u * (s2 + 0.5 * w), u * (s1 + 0.5 * w))
            bend = 0.12 * w * math.sin(seed) * (1 - u * u)
            xy = c + along[:, None] * t + bend[:, None] * side
            flare = 1 + 0.3 * u * u
            common["rough"] = v.get("rough", 0.25)
            out.append(Tube(name, np.c_[xy, np.full(5, floor)], w / 2 * flare, height * (1 + 0.12 * u * u), floor,
                            **common))
            notes.append(f"{name}: arch at [{c[0]:.0f}, {c[1]:.0f}] heading {math.degrees(math.atan2(t[0], t[1])) % 180:.0f}"
                         f" deg, {w:.1f} m wide, {height:.1f} m high over a floor at {floor:+.1f} m, {s1 + s2:.0f} m "
                         f"through the rock, roof {top - floor - height:.1f} m thick at its middle")
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
            # a flat floor in the water, the roof high enough to see from a boat, the back cut deep under the lip
            depth, h = float(v.get("depth", 5.0)), float(v.get("height", 3.5))
            L = float(v.get("length", 30.0))
            floor = float(v.get("floor", (sea - 0.5) if sea is not None else T.height(at)))
            # along the face: across the address's own direction into the rock (cliff_foot:<address>), else the slope
            inward = adir if adir is not None else -_downhill(T, at)
            along = _bearing(T, v["along"], at) if "along" in v else np.array([-inward[1], inward[0]])
            pts = []
            for s_ in np.linspace(-L / 2, L / 2, max(3, int(L / 5) + 1)):
                face = _face(T, at + s_ * along, floor + h / 2)
                if face is not None:
                    pts.append(face)
            if len(pts) < 2:
                raise ValueError(f"volume {name!r}: no cliff face near {v['at']!r} to undercut")
            pts = np.array(pts)
            f = np.abs(np.linspace(-1, 1, len(pts)))
            ease = 1 - 0.75 * f ** 3  # full depth along most of it, easing out at the ends
            common["rough"] = v.get("rough", 0.3)
            out.append(Tube(name, np.c_[pts, np.full(len(pts), floor)], depth * ease, h * (0.6 + 0.4 * ease), floor,
                            **common))
            lip = [float(T.height(p_ - _downhill(T, p_) * depth)) for p_ in pts]  # the ground over the notch's back
            notes.append(f"{name}: overhang notch {depth:.1f} m deep, {h:.1f} m high over a floor at {floor:+.1f} m, "
                         f"{L:.0f} m along the cliff; {min(lip) - floor - h:.1f}-{max(lip) - floor - h:.1f} m of rock "
                         f"over it")
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

def rock_relief(p, r):
    """Solid rock character as a field offset (+ carves, - builds): planar facets meeting in crisp creases, and bedding
    (a V notch at each bedding plane, each bed standing proud or set back on its own, stepping over at its edge).
    Continuous everywhere with C0 creases, never jumps: a jump (the nearest cell's plane alone) meshed as steps whose
    normals pointed sideways (black shards), and blending the cells smoothly read as mush. The mesh shows the creases
    with split normals (`split_normals`). The heightfield's own rock (terrain_rock) moves the ground in plan only;
    this can overhang."""
    out = r["facets"] * (_pl_facets(p, r["size"], r["seed"]) + 0.4 * _pl_facets(p, 0.43 * r["size"], r["seed"] + 5))
    if r["bedding"] > 0:
        z = bed_level(p, r)
        kb = np.floor(z).astype(np.int64)
        f = z - kb
        edge = np.minimum(f, 1 - f)
        # each bed stands proud or set back on its own, stepping over to the next in a straight ramp `be` either side
        # of the bedding plane (creases at both ends: a crisp step, no jump)
        off = lambda k: 2 * noise._hash(k, k * 0 + 7, k * 0, r["seed"] + 20) - 1
        lower = f < 0.5
        nb = np.where(lower, kb - 1, kb + 1)
        be = r.get("bed_edge", 0.08)
        u = np.clip((np.where(lower, f, f - 1) + be) / (2 * be), 0, 1)  # 0..1 from the lower bed to the upper
        o = np.where(lower, off(nb) * (1 - u) + off(kb) * u, off(kb) * (1 - u) + off(nb) * u)
        out = out + r["bedding"] * (0.3 * np.clip(1 - edge / be, 0, 1) + 0.3 * o)
    return out


# a fixed rotation for the facet lattice, so its creases don't line up with the world's axes
_ROT = np.linalg.qr(np.array([[0.62, -0.51, 0.33], [0.27, 0.71, 0.58], [-0.49, -0.12, 0.74]]))[0]


def _pl_facets(p, size, seed):
    """Random heights at the corners of a rotated cubic lattice, interpolated linearly over each cube's six tetrahedra
    (the Freudenthal split: consistent across faces): a continuous, piecewise-planar field. Offsetting a surface by it
    breaks the surface into planar facets with crisp creases. -1..1."""
    q = (p @ _ROT.T) / size
    b = np.floor(q).astype(np.int64)
    f = q - b
    order = np.argsort(-f, axis=1)  # the tetrahedron: walk the axes from the largest fraction down
    fs = np.take_along_axis(f, order, 1)
    w = np.stack([1 - fs[:, 0], fs[:, 0] - fs[:, 1], fs[:, 1] - fs[:, 2], fs[:, 2]], 1)
    v = b.copy()
    out = w[:, 0] * (2 * noise._hash(v[:, 0], v[:, 1], v[:, 2], seed) - 1)
    rows = np.arange(len(p))
    for k in range(3):
        v[rows, order[:, k]] += 1
        out = out + w[:, k + 1] * (2 * noise._hash(v[:, 0], v[:, 1], v[:, 2], seed) - 1)
    return out


def bed_level(p, r):
    """Which bed a point is in, as a real number (bed k spans k..k+1): the heightfield rock's own beds
    (terrain_rock.bed_step / bed_offset, so sills on the heightfield's faces and the solid rock's beds line up) when
    it has them, else level beds `bed` thick."""
    off = r["bed_offset"](p[:, :2]) if r.get("bed_offset") else 0.0
    return (p[:, 2] + off) / r["bed"]


def rock_config(T, cfg):
    """The solid rock character's settings: spec "rock" (false turns it off; "facets", "bedding" 0..1 as for the
    heightfield; "facet_size", "bed" m) and export.tiles "rock" (a multiplier, 0 = none). Beds are the heightfield
    rock's own where terrain_rock exposes them."""
    from . import terrain_rock
    rc = T.spec.get("rock", {})
    mult = float(cfg.get("rock", 1.0))
    if rc is False or mult <= 0:
        return None
    rc = rc if isinstance(rc, dict) else {}
    # few large facets with crisp joints (5 m cells and 1.8 m beds at 1 m voxels read as crumpled paper); the
    # heightfield's own facets are larger (1.2 x crag): these sit inside them, the finer size
    size = float(rc.get("facet_size", np.clip(float(T.world.get("crag", 12.0)) / 2.5, 4.0, 10.0)))
    fac = mult * float(rc.get("facets", 1.0)) * 0.18 * size
    bd = mult * float(rc.get("bedding", 1.0))
    bed, off = float(rc.get("bed", 3.0)), None
    if hasattr(terrain_rock, "bed_step") and hasattr(terrain_rock, "bed_offset") and "bed" not in rc:
        bed = float(terrain_rock.bed_step(T))
        off = _gridded(lambda xy, T=T: terrain_rock.bed_offset(T, xy), T)
    # bed steps ramp over 2 voxels either side of their plane (0.8 voxel meshed as a sawtooth that cast jagged
    # shadows); the crisp notch at the bedding plane is in the maps (terrain_bake.micro_relief)
    vox = float(cfg.get("voxel", DEFAULTS["voxel"]))
    return {"size": size, "facets": fac, "bedding": bd, "bed": bed, "bed_offset": off, "seed": 4242,
            "reach": 1.4 * fac + 0.7 * bd + 1.0, "bed_edge": max(0.05, 2.0 * vox / bed)}


def _gridded(fn, T, spacing=2.0):
    """A smooth function of plan position (the beds' wander: fbm over ~150 m) read from a cubic spline on a grid over
    the frame instead of evaluated per point: it was a quarter of every field evaluation, and the bake evaluates the
    field tens of times per texel. Identical for meshing and baking (both use this)."""
    (x0, y0), (x1, y1) = T.spec["extent"]
    m = 4 * spacing
    xs = np.arange(x0 - m, x1 + m + spacing, spacing)
    ys = np.arange(y0 - m, y1 + m + spacing, spacing)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    coef = ndimage.spline_filter(fn(np.c_[X.ravel(), Y.ravel()]).reshape(X.shape), order=3)

    def f(xy):
        xy = np.atleast_2d(np.asarray(xy, float))
        return ndimage.map_coordinates(coef, [(xy[:, 0] - xs[0]) / spacing, (xy[:, 1] - ys[0]) / spacing], order=3,
                                       prefilter=False, mode="nearest")
    return f


def dig_doline(T, H, d):
    """A doline (a karst sinkhole) dug into the ground grid: a bowl `radius` m round and `depth` m deep relative to the
    ground around it (so on a hillside it's a hollow in the slope), gentle at the lip and steepest (2 x depth / run)
    at its throat, a flat floor `throat` m round where a shaft drops to the cave."""
    dx, dy = T.X - d["xy"][0], T.Y - d["xy"][1]
    r = np.hypot(dx, dy)
    # an uneven rim: the radius wanders +-20% round the bowl (a perfect circle read as a dish)
    u = np.c_[(dx / np.maximum(r, 1e-9)).ravel(), (dy / np.maximum(r, 1e-9)).ravel(), np.zeros(r.size)]
    wob = 1 + 0.4 * (noise.fbm(u * 3.0, 1.0, 2, seed=int(d.get("seed", 0))).reshape(r.shape) - 0.5)
    R = d["throat"] + (d["radius"] - d["throat"]) * wob
    s = np.clip((r - d["throat"]) / np.maximum(R - d["throat"], 1e-6), 0, 1)
    return H - d["depth"] * (1 - s) ** 2


class Field:
    def __init__(self, T, vols: list[Tube], rock=None, dolines=None):
        self.H = np.ascontiguousarray(T.H, float)
        self.x0, self.y0, self.c = float(T.xs[0]), float(T.ys[0]), float(T.cell)
        self.vols = vols
        self.rock = rock
        self.floor_guard = None
        self.micro = None  # fine rock relief evaluated only when baking maps (terrain_bake.micro_relief)
        for d in dolines or ():  # 2.5D ground edits (karst dolines: grassy funnels into a throat)
            self.H = dig_doline(T, self.H, d)
        if rock is not None:
            # where the rock character goes: steep ground (45-62 deg), as a smooth mask on the grid (~2 cells). From
            # each point's own column slope it switched on within 0.2 m at a cliff's lip (the B-spline's slope turns
            # fast there): the relief times that switch was a sub-voxel step in the field, meshed as black shards
            gy, gx = np.gradient(self.H, self.c)
            cs = 1.0 / np.sqrt(1.0 + gx * gx + gy * gy)
            # (dilated a cell first: a sheer cliff is a cell or two wide in plan and smoothing alone halved it)
            self.steep = ndimage.gaussian_filter(ndimage.maximum_filter(smoothstep(0.71, 0.47, cs), 3), 1.0)

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

    def _relief_cap(self, size):
        """How much of the rock character a passage's walls take: at most ~0.2 of its smaller radius (a 3 m tunnel
        doesn't take 2 m facets)."""
        amp = 1.4 * self.rock["facets"] if self.rock else 1.0
        return np.clip(0.2 * size / max(amp, 1e-6), 0.1, 1.0)

    def steep_at(self, x, y):
        r = (np.asarray(y, float) - self.y0) / self.c
        q = (np.asarray(x, float) - self.x0) / self.c
        return ndimage.map_coordinates(self.steep, [r, q], order=3, prefilter=False, mode="nearest")

    def ground(self, p):
        h, s = self.column(p[:, 0], p[:, 1])
        return (p[:, 2] - h) * s

    def volumes(self, p, F, near=None):
        """Each volume combined into F in order; `near` (if given) gets how close each point is to a volume, 0..1
        (rock character applies there)."""
        for vol in self.vols:
            k = np.flatnonzero(np.all((p >= vol.lo) & (p <= vol.hi), axis=1))
            if not len(k):
                continue
            d, above, size = vol.sd(p[k], detail=True)
            F[k] = smax(F[k], -d, vol.blend) if vol.op == "subtract" else smin(F[k], d, vol.blend)
            if near is not None:
                # rock relief on walls and roofs, scaled to the passage (a 1 m slot doesn't take 0.8 m facets), and
                # none on floors (a person walks there)
                w = smoothstep(NEAR, 0.0, d) * self._relief_cap(size) * smoothstep(0.3, 1.5, above)
                near[k] = np.maximum(near[k], w * vol.relief)
                if self.floor_guard is not None:
                    self.floor_guard[k] = np.minimum(self.floor_guard[k], np.where(np.isinf(above), 1.0,
                                                                                  smoothstep(0.3, 1.5, above)))
        return F

    def solid(self, p, F, s):
        """Volumes and rock character on top of the ground's distance F (s: the column's slope factor, cos slope)."""
        near = np.zeros(len(p))
        self.floor_guard = np.ones(len(p))
        F = self.volumes(p, F, near)
        guard, self.floor_guard = self.floor_guard, None
        if self.rock is not None:
            # steep ground (45-62 deg) and anything a volume shaped: faceted, jointed, bedded rock (not cave floors)
            w = np.maximum(self.steep_at(p[:, 0], p[:, 1]) * guard, near)
            k = np.flatnonzero((w > 0.01) & (np.abs(F) < self.rock["reach"]))
            if len(k):
                F[k] = F[k] + w[k] * rock_relief(p[k], self.rock)
                if self.micro is not None:  # (bake-only fine rock: below the meshing voxel, for the maps)
                    F[k] = F[k] + w[k] * self.micro(p[k])
        return F

    def value(self, p):
        p = np.asarray(p, float)
        h, s = self.column(p[:, 0], p[:, 1])
        return self.solid(p, (p[:, 2] - h) * s, s)

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
    _, g = field.value_gradient(P, NORMAL_H * v)
    N = g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12)
    return P, N


# ---------------------------------------------------------------- materials

def rock_colours(T):
    """sRGB per terrain cell: the colour the heightfield views paint on rock there (terrain_rock.colour when it
    exists, else the same rule as terrain.ground_colours: the kind's rock, sandstone for arid kinds, and every
    rock-type cover layer, e.g. black lava or a cliff's grey, over it where its mask is)."""
    from . import terrain_design as design
    from . import terrain_rock
    f = getattr(terrain_rock, "colour", None)
    if f is not None:
        return np.asarray(f(T), float)
    arid = T.world["kind"] in ("canyon", "dunes", "plateau")
    hn = (T.H - T.H.min()) / max(np.ptp(T.H), 1)
    base = np.array([0.58, 0.38, 0.26]) if arid else np.array(terrain_rock.params(T).get("rock_colour",
                                                                                       LAYERS["rock"]["color"]))
    c = base + 0.06 * hn[..., None]
    for name, m in T.cover.items():
        spec = design._spec_cover(T, name)
        if LAYER_OF.get(spec.get("type", name)) == "rock":
            a = np.clip(m, 0, 1)[..., None]
            c = c * (1 - a) + np.array(design.cover_colour(T, name)) * a
    tone = (getattr(T, "rock", None) or {}).get("tone") if isinstance(getattr(T, "rock", None), dict) else None
    if tone is not None and np.shape(tone) == T.H.shape:
        c = c * np.asarray(tone)[..., None]
    return c


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
        self.layers = list(dict.fromkeys(order + ["rock", "earth"] + (["sand", "wet_rock"] if self.sea is not None
                                                                      else [])))
        col = ground_colours(T, cover=True)
        wet = ~np.isnan(T.water)
        col[wet] = np.array(LAYERS["sand"]["color"]) * 0.8
        self.display = col
        self.rock_grid = rock_colours(T)
        steep = T._slope() > 45
        self.rock_ref = np.median(self.rock_grid[steep] if steep.any() else self.rock_grid.reshape(-1, 3), 0)
        self.routes = T.masks.get("routes")

    def layer_ref(self, name):
        """A layer's reference look for the manifest (rock: this terrain's own rock colour)."""
        ref = dict(LAYERS[name])
        if name == "rock":
            ref["color"] = [round(float(x), 3) for x in self.rock_ref]
        elif name == "wet_rock":
            ref["color"] = [round(float(x) * 0.45, 3) for x in self.rock_ref]
        return ref

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
        tide = np.zeros(n)
        if self.sea is not None:  # under water: sand, unless rock
            wet = smoothstep(0.2, 1.2, self.sea - P[:, 2])
            for key in W:
                W[key] *= 1 - wet
            W["sand"] += wet
            # the splash zone: rock dark and wet from the water up a couple of metres, higher inside caves and notches
            tide = smoothstep(self.sea + 2.2 + 1.5 * below, self.sea + 0.4, P[:, 2])
        for key in W:
            W[key] *= 1 - rock
        W["rock"] += rock * (1 - tide)
        if "wet_rock" in W:
            W["wet_rock"] += rock * tide
        Wm = np.stack([W[k] for k in self.layers], 1)
        Wm /= np.maximum(Wm.sum(1, keepdims=True), 1e-9)
        # display colour: the terrain's own preview colours (cover, roads, slope), rock over steep faces and caves
        c = np.stack([self._grid(self.display[..., i], xy) for i in range(3)], 1)
        if self.sea is not None:
            wet = smoothstep(0.2, 1.2, self.sea - P[:, 2])[:, None]
            c = c * (1 - wet) + np.array(LAYERS["sand"]["color"]) * 0.8 * wet
        # the rock's own colour where the heightfield views paint it (the kind's rock, strata bands, rock cover
        # layers such as black lava or a cliff's grey), not one grey for every terrain
        rc = np.stack([self._grid(self.rock_grid[..., i], xy) for i in range(3)], 1)
        if self.field.rock is not None:  # beds and facets differ in tone (a single grey read as plaster)
            r = self.field.rock
            zb = bed_level(P, r)
            kb = np.floor(zb).astype(np.int64)
            fr = zb - kb
            th = lambda k: 0.84 + 0.26 * noise._hash(k, k * 0 + 3, k * 0, r["seed"] + 30)
            # (each bed's tone eases into the next over ~0.2 m: a step aliased along every bedding plane in the maps)
            e = min(0.45, 0.2 / r["bed"])
            lo_, hi_ = smoothstep(-e, e, fr), smoothstep(-e, e, fr - 1)
            tone = th(kb - 1) * (1 - lo_) + th(kb) * (lo_ - hi_) + th(kb + 1) * hi_
            tone = tone * (0.92 + 0.12 * _pl_facets(P, r["size"], r["seed"] + 40))
            tone = tone * (0.93 + 0.14 * noise.fbm(P, 2.5 * r["size"], 2, seed=r["seed"] + 31))
            rc = rc * tone[:, None]
        # crevices, joints and the backs of overhangs darker (how open the field is half a metre out along the
        # normal: a cheap occlusion that needs no ray tracing, the same in every engine)
        d = 0.8
        open_ = np.clip(self.field.value(P + d * N) / d, 0, 1)
        rc = rc * (0.55 + 0.45 * open_)[:, None]
        c = c * (1 - rock[:, None]) + rc * (1 - 0.55 * tide[:, None]) * rock[:, None]  # wet: its own rock, darker
        return Wm.astype(np.float32), c


def _linear(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


# ---------------------------------------------------------------- glTF

def _pad4(b: bytes, fill=b"\0"):
    return b + fill * (-len(b) % 4)


def write_glb(path, name, prims, translation, material, extras=None, images=None):
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
        if not len(p["indices"]):
            continue
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
    if images:  # [(bytes, mime type)]: embedded, texture i = image i, one sampler (trilinear, repeat)
        doc["images"] = []
        for data, mime in images:
            off = len(bin_)
            bin_.extend(_pad4(data))
            views.append({"buffer": 0, "byteOffset": off, "byteLength": len(data)})
            doc["images"].append({"bufferView": len(views) - 1, "mimeType": mime})
        doc["samplers"] = [{"magFilter": 9729, "minFilter": 9987}]
        doc["textures"] = [{"source": i, "sampler": 0} for i in range(len(images))]
        doc["buffers"][0]["byteLength"] = len(bin_)
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

# the lattice's z planes sit this fraction of a voxel off round heights: flat floors at round heights (sea level, a
# cave floor at 5.5 m) lay exactly on lattice planes, every corner there was a zero, and marching cubes left
# non-manifold slivers (the seam check caught them). x and y stay on the tile borders.
ZOFF = 0.137

class Grid:
    """The world's tile grid and the meshing lattice per LOD."""

    def __init__(self, T, cfg):
        (x0, y0), (x1, y1) = T.spec["extent"]
        self.origin = np.array(cfg.get("origin") or [x0, y0], float)
        self.tile = float(cfg["tile"])
        self.voxel = float(cfg["voxel"])
        self.lods = int(cfg["lods"])
        vmax = self.voxel
        if abs(self.tile / vmax - round(self.tile / vmax)) > 1e-9:
            raise ValueError(f"tile {self.tile} m isn't a whole number of voxels ({vmax} m)")
        # the meshed world: the extent from the origin, trimmed to whole voxels
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
    h, sce = field.column(XE.ravel(), YE.ravel())
    zlo, zhi = float(np.min(h - getattr(field, "zpad", 0.0) / np.maximum(sce, 0.15))), h.max()
    lo = np.array([X.min() - v, Y.min() - v, -1e9])
    hi = np.array([X.max() + v, Y.max() + v, 1e9])
    for vol in vols:
        if vol.touches(lo, hi):
            zlo, zhi = min(zlo, vol.lo[2] - getattr(field, "vol_pad", 0.0)), max(zhi, vol.hi[2])
    pad = 2 + int(math.ceil((field.rock["reach"] if field.rock else 0.0) / v))  # (rock relief moves the surface)
    c0, c1 = int(math.floor(zlo / v)) - pad, int(math.ceil(zhi / v)) + pad
    ic = np.arange(c0, c1 + 1)
    hcol, scol = field.column(X.ravel(), Y.ravel())
    Z = (ic + ZOFF) * v
    F = (Z[None, :] - hcol[:, None]) * scol[:, None]
    P = np.stack(np.broadcast_arrays(X.ravel()[:, None], Y.ravel()[:, None], Z[None, :]), -1).reshape(-1, 3)
    F = F.ravel()
    F = field.solid(P, F, np.repeat(scol, len(ic)))
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
    to_w = lambda a: np.c_[G.origin[0] + a[:, 0] * v, G.origin[1] + a[:, 1] * v, (a[:, 2] + ZOFF) * v]
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
    n_open = len(_boundary_edges(faces))

    def valid(f):  # manifold, and no new holes (dropping a fin's twin faces can open one)
        return _manifold(f) and len(_boundary_edges(f)) == n_open

    def run(n, base=None):
        # pyfqmr sometimes folds a thin part (a cave mouth, an arch's soffit) whatever the count: other settings of
        # its aggressiveness usually don't
        Pb, Fb = base if base is not None else (P, faces)
        out = None
        for agg in (7, 5, 9, 6, 8):
            s = pyfqmr.Simplify()
            s.setMesh(Pb, Fb)
            s.simplify_mesh(target_count=int(n), aggressiveness=agg, max_iterations=300, preserve_border=True,
                            verbose=False)
            v, f, _ = s.getMesh()
            out = _drop_twins(np.asarray(v, float), np.asarray(f, np.int64))
            if valid(out[1]) and len(out[1]) <= 1.15 * n + 64:  # (a low aggressiveness can stall far above n)
                return out
        return out


    def error(v, f):
        if not valid(f):  # pyfqmr can fold a thin part into a fin (two faces on one directed edge)
            return np.inf
        c = np.r_[v[f].mean(1), (v[f[:, 0]] + v[f[:, 1]]) / 2]
        return float(np.percentile(np.abs(field.value(c)), 99))

    tol = err + error(P, faces)
    if len(faces) <= budget:
        best, hi = (P, faces), len(faces)
    else:
        # the budget caps it: the first unfolded result at or under it (a fold at the budget itself used to hand back
        # the undecimated mesh: LOD2 came out bigger than LOD1)
        n = int(budget)
        best = None
        while n >= 16:
            cand = run(n)
            if valid(cand[1]) and len(cand[1]) <= budget:
                best = cand
                break
            n = int(n * 0.8)
        if best is None:  # in one pass every count folded something: in steps, each from the last good mesh
            cur = (P, faces)
            while len(cur[1]) > budget:
                cand = run(max(int(len(cur[1]) / 1.6), int(budget)), cur)
                if not valid(cand[1]) or len(cand[1]) >= len(cur[1]):
                    break
                cur = cand
            return cur
        hi = n
        if error(*best) > tol:
            return best
    # down from the best mesh so far, each step from the last one that held (a log search over the dense mesh ran
    # pyfqmr on all of it 7 times a tile: most of the export's CPU time); a step that breaks the tolerance is retried
    # at a gentler ratio before stopping
    for ratio in (0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5):
        n = int(len(best[1]) * ratio)
        if n < 16:
            break
        cand = run(n, best)
        if len(cand[1]) < len(best[1]) and error(*cand) <= tol:
            best = cand
            continue
        for gentler in (0.75, 0.88):
            cand = run(int(len(best[1]) * gentler), best)
            if len(cand[1]) < len(best[1]) and error(*cand) <= tol:
                best = cand
                break
        break
    return best


def _drop_twins(v, f):
    """pyfqmr sometimes folds a thin part into a fin: the same triangle twice, back to back. Both go (the faces round
    them close up), and vertices left unused are dropped."""
    key = np.sort(f, axis=1)
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    keep = cnt[inv.ravel()] == 1
    if keep.all():
        return v, f
    f = f[keep]
    used = np.unique(f)
    remap = np.full(len(v), -1, np.int64)
    remap[used] = np.arange(len(used))
    return v[used], remap[f]


def _manifold(f):
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    n = int(f.max()) + 1
    if len(np.unique(e[:, 0] * n + e[:, 1])) < len(e):
        return False
    und = np.minimum(e[:, 0], e[:, 1]) * n + np.maximum(e[:, 0], e[:, 1])
    return bool(np.unique(und, return_counts=True)[1].max() <= 2)


def _polylines(edges):
    """The ordered vertex lists an undirected edge set makes: open chains (from a vertex that isn't degree 2) and
    closed loops (first vertex repeated at the end). Deterministic: walks start at the lowest row."""
    adj = {}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    done = set()

    def walk(s):
        line, cur = [s], s
        while True:
            nxt = sorted(x for x in adj[cur] if (min(cur, x), max(cur, x)) not in done)
            if not nxt:
                return line
            x = nxt[0]
            done.add((min(cur, x), max(cur, x)))
            line.append(x)
            cur = x
            if cur == s:
                return line

    out = []
    for s in sorted(v for v, n in adj.items() if len(n) != 2):
        while any((min(s, x), max(s, x)) not in done for x in adj[s]):
            out.append((walk(s), False))
    for s in sorted(adj):
        if any((min(s, x), max(s, x)) not in done for x in adj[s]):
            out.append((walk(s), True))
    return out


def _simplify(P, line, closed, tol, always):
    """Douglas-Peucker on a chain of rows (in 3D, within its border plane): the rows kept, in order. Ends, and rows
    in `always` (tile corners), are kept; a loop keeps at least 3 (it must not close up)."""
    pts = [r for r in line if r in always] if closed else []
    keep = {line[0], line[-1], *[r for r in line if r in always]}

    def dp(a, b):
        stack = [(a, b)]
        while stack:
            a, b = stack.pop()
            if b <= a + 1:
                continue
            A, B = P[line[a]], P[line[b]]
            Q = P[line[a + 1:b]]
            d = B - A
            L2 = max(float(d @ d), 1e-18)
            t = np.clip((Q - A) @ d / L2, 0, 1)
            e = np.linalg.norm(Q - (A + t[:, None] * d), axis=1)
            k = int(np.argmax(e))
            if e[k] > tol:
                keep.add(line[a + 1 + k])
                stack += [(a, a + 1 + k), (a + 1 + k, b)]

    if closed:
        body = line[:-1]
        far = int(np.argmax(np.linalg.norm(P[body] - P[body[0]], axis=1)))
        keep.add(body[far])
        dp(0, far)
        dp(far, len(line) - 1)
        if len(keep) < 3:  # a thin loop: the vertex furthest from its chord too
            A, B = P[body[0]], P[body[far]]
            d = np.linalg.norm(np.cross(P[body] - A, B - A), axis=1)
            keep.add(body[int(np.argmax(d))])
    else:
        # the anchors split the chain; each piece simplified on its own
        anchors = [i for i, r in enumerate(line) if r in keep]
        for a, b in zip(anchors, anchors[1:]):
            dp(a, b)
    del pts
    return [r for r in line if r in keep]


def _needs(lines, keep, CP, lods):
    """Per LOD, per canonical row on a kept chain: how far it is from the same plane's chains at the other LODs
    (what a skirt there has to cover)."""
    segs = {}
    for pl, L in lines.items():
        for k in range(lods):
            s = []
            for ln, closed in L:
                kept = [r for r in ln if r in keep[k]]
                s += list(zip(kept, kept[1:]))
            segs[pl, k] = np.array([[CP[x], CP[y]] for x, y in s]).reshape(-1, 2, 3)
    need = [np.zeros(len(CP)) for _ in range(lods)]
    for (pl, k), sg in segs.items():
        rows = np.unique(np.array(list(_plane_rows(lines[pl], keep[k])), np.int64))
        if not len(rows):
            continue
        for j2 in range(lods):
            if j2 != k and len(segs[pl, j2]):
                need[k][rows] = np.maximum(need[k][rows], _chain_dist(CP[rows], segs[pl, j2]))
    return need


def _plane_rows(L, keep):
    for ln, _ in L:
        for r in ln:
            if r in keep:
                yield r


def _cross3(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    return (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)


def _collapse_border(P, F, drop, min_dot=0.2):
    """Collapse each border vertex in `drop` into a neighbour along the border (half-edge collapse onto the
    neighbour's position). Returns the faces left and the vertices that couldn't go without turning a face over or
    joining the mesh badly (the link condition)."""
    F = F.copy()
    Pl = P.tolist()
    alive = np.ones(len(F), bool)
    bn = {}
    for a, b in _boundary_edges(F):
        bn.setdefault(int(a), set()).add(int(b))
        bn.setdefault(int(b), set()).add(int(a))
    # faces are only looked up round border vertices (a collapse moves a border vertex onto a border vertex)
    isb = np.zeros(int(F.max()) + 1, bool)
    isb[list(bn)] = True
    vf = {}
    for f in np.flatnonzero(isb[F].any(1)):
        for v in F[f]:
            if isb[v]:
                vf.setdefault(int(v), set()).add(int(f))
    dropping = set(int(u) for u in drop)

    def nbrs(v):
        return {int(x) for f in vf.get(v, ()) for x in F[f]} - {v}

    def attempt(u, w):
        fu = vf.get(u, set())
        shared = [f for f in fu if w in F[f]]
        if len(shared) != 1 or len(fu) < 2:  # (u's only face gone would leave w and the third vertex stranded)
            return False
        third = [int(x) for x in F[shared[0]] if x != u and x != w]
        if len(vf.get(w, ())) < 2 or (third[0] in vf and len(vf[third[0]]) < 2):
            return False
        if nbrs(u) & nbrs(w) != set(third):
            return False
        for f in fu:
            if f == shared[0]:
                continue
            tri = F[f]
            n0 = _cross3(Pl[tri[0]], Pl[tri[1]], Pl[tri[2]])
            t2 = [w if x == u else x for x in tri]
            n1 = _cross3(Pl[t2[0]], Pl[t2[1]], Pl[t2[2]])
            l0 = math.sqrt(n0[0] ** 2 + n0[1] ** 2 + n0[2] ** 2)
            l1 = math.sqrt(n1[0] ** 2 + n1[1] ** 2 + n1[2] ** 2)
            if l1 < 1e-9 or n0[0] * n1[0] + n0[1] * n1[1] + n0[2] * n1[2] <= min_dot * l0 * l1:
                return False
        f0 = shared[0]
        alive[f0] = False
        for x in F[f0]:
            vf.get(int(x), set()).discard(f0)
        for f in list(vf[u]):
            F[f][F[f] == u] = w
            vf.setdefault(w, set()).add(f)
        vf[u] = set()
        for x in bn.pop(u, set()):
            bn[x].discard(u)
            if x != w:
                bn[x].add(w)
                bn[w].add(x)
        return True

    pending = sorted(dropping)
    for _ in range(4):
        left = []
        for u in pending:
            # into a neighbour that stays if there is one (fewer moves), else one that goes later
            cands = sorted(bn.get(u, ()), key=lambda x: (x in dropping, x))
            if not any(attempt(u, w) for w in cands):
                left.append(u)
            else:
                dropping.discard(u)
        if len(left) == len(pending):
            break
        pending = left
    return F[alive], set(pending)


def _chain_dist(A, segs_b):
    """Distance from points A (n, 3) to the nearest of the segments (m, 2, 3)."""
    if not len(segs_b):
        return np.full(len(A), np.inf)
    P0, D = segs_b[:, 0], segs_b[:, 1] - segs_b[:, 0]
    L2 = np.maximum((D * D).sum(1), 1e-18)
    out = np.empty(len(A))
    for s0 in range(0, len(A), 256):
        Q = A[s0:s0 + 256, None, :] - P0[None]
        t = np.clip((Q * D[None]).sum(2) / L2[None], 0, 1)
        out[s0:s0 + 256] = np.linalg.norm(Q - t[..., None] * D[None], axis=2).min(1)
    return out


_CTX: dict = {}  # what the export's worker processes read (forked: shared, not pickled)


WORKER_GB = 2.5  # a tile worker's peak (measured 1.2-2.2 GB on pebble/lava at 0.5 m)


def _pool():
    """A fork pool sized by free memory (`resources.workers`), guarded: 16 fixed workers x ~2 GB plus other jobs
    OOM-killed the user's desktop twice."""
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor
    from . import resources
    n = resources.workers(_CTX.get("worker_gb", WORKER_GB), cap=16)
    ex = ProcessPoolExecutor(max_workers=n, mp_context=multiprocessing.get_context("fork"))
    return resources.guarded(ex, "terrain tiles")


def _job_maps(args):
    """A tile's heightmap (2^k + 1 samples, edges shared with the neighbours) and splat PNGs (runs in a worker)."""
    from PIL import Image
    i, j, lo = args
    c = _CTX
    G, field, mats, cfg, out, hrange = c["G"], c["base"], c["mats"], c["cfg"], c["out"], c["hrange"]
    lo = np.array(lo)
    extra = {}
    hm = int(cfg["heightmap"]) if cfg["mode"] == "full" else 0  # (cliffs: the ground tiles wrote theirs)
    if hm:
        s = np.linspace(0, G.tile, hm)
        X, Y = np.meshgrid(lo[0] + s, lo[1] + s)
        h, _ = field.column(X.ravel(), Y.ravel())
        h = h.reshape(hm, hm)[::-1].astype(np.float32)  # north-up rows
        np.save(out / "heightmaps" / f"height_{i}_{j}.npy", h)
        q = np.round((h - hrange[0]) / (hrange[1] - hrange[0]) * 65535).clip(0, 65535).astype(np.uint16)
        Image.fromarray(q).save(out / "heightmaps" / f"height_{i}_{j}.png")
        extra["heightmap"] = f"heightmaps/height_{i}_{j}.npy"
    sp = int(cfg["splat"])
    if sp:
        mg = int(cfg["splat_margin"])
        Nn = sp + 2 * mg
        d = G.tile / sp
        cc = lo[0] + (np.arange(Nn) - mg + 0.5) * d
        r = lo[1] + (np.arange(Nn) - mg + 0.5) * d
        X, Y = np.meshgrid(cc, r[::-1])  # row 0 = north
        h, _ = field.column(X.ravel(), Y.ravel())
        P = np.c_[X.ravel(), Y.ravel(), h]
        _, g = field.value_gradient(P, 0.125)
        Nm = g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12)
        W, _ = mats.weights(P, Nm)
        files = []
        for g4 in range(0, len(mats.layers), 4):
            ch = W[:, g4:g4 + 4]
            ch = np.c_[ch, np.zeros((len(ch), 4 - ch.shape[1]))]
            img = (np.clip(ch, 0, 1) * 255 + 0.5).astype(np.uint8).reshape(Nn, Nn, 4)
            fn = f"splats/splat{g4 // 4}_{i}_{j}.png"
            Image.fromarray(img, "RGBA").save(out / fn)
            files.append(fn)
        extra["splats"] = files
    return extra


def _job_ground(ij):
    from . import terrain_cliffs
    c = _CTX
    i, j = ij
    lo, _ = c["G"].bounds(i, j)
    return terrain_cliffs.ground_tile(c["region"], c["mats"], i, j, lo, int(c["cfg"]["heightmap"]) or 65,
                                      c["G"].lods, c["out"], c["cfg"])


def _job_mc(ij):
    """A tile's marching cubes and its border vertices' lattice-edge keys (runs in a worker)."""
    c = _CTX
    i, j = ij
    if hasattr(c["field"], "empty") and c["field"].empty(*c["G"].bounds(i, j)):
        return None
    r = _tile_mc(c["field"], c["G"], i, j, 0, c["vols"])
    if r is None:
        return None
    idx, faces, rng = r
    (_, _), (_, _), n, (NX, NY) = c["G"].cells(i, j, 0)
    return idx, faces, rng, _border_keys(idx, rng, n, NX, NY)


def _job_dense(ij):
    """A tile's LOD0 mesh: marching cubes on the lattice, interior projected, border vertices the canonical ones."""
    c = _CTX
    G, v0, field, reg, CP = c["G"], c["v0"], c["field"], c["reg"], c["CP"]
    idx, faces, rng, kk = c["mc"][ij]
    P = np.c_[G.origin[0] + idx[:, 0] * v0, G.origin[1] + idx[:, 1] * v0, (idx[:, 2] + ZOFF) * v0]
    border = np.array(sorted(kk), np.int64)
    rows = np.array([reg[kk[q]] for q in border], np.int64)
    inner = np.setdiff1d(np.arange(len(P)), border)
    N = np.zeros_like(P)
    P[inner], N[inner] = project(field, P[inner], v0)
    P[border], N[border] = CP[rows], c["CN"][rows]
    mov = np.ones(len(P), bool)
    mov[border] = False
    if c["cfg"].get("sharp", True):  # creases on mesh edges (extended marching cubes), not a sawtooth
        n0 = len(P)
        to_world = lambda q: np.array([G.origin[0] + q[0] * v0, G.origin[1] + q[1] * v0, (q[2] + ZOFF) * v0])
        P, faces, N, _ = terrain_sharp.feature_points(P, faces, idx, N, field, to_world, v0, mov, bounds=G.bounds(*ij))
        mov = np.r_[mov, np.ones(len(P) - n0, bool)]
    else:
        P = snap_creases(P, faces, field, v0, mov)
    vrow = np.full(len(P), -1, np.int64)
    vrow[border] = rows
    return P, faces, vrow


def _job_collapse(args):
    ij, keep_rows = args
    P, faces, vrow = _CTX["dense"][ij]
    drop = np.flatnonzero((vrow >= 0) & ~np.isin(vrow, keep_rows))
    Fk, bad = _collapse_border(P, faces, drop)
    return Fk, {int(vrow[u]) for u in bad}


def build_field(T, cfg=None):
    """The 3D field of a terrain: (field, volume pieces, notes, caves)."""
    from . import terrain_caves
    cfg = {**DEFAULTS, **((T.spec.get("export") or {}).get("tiles") or {}), **(cfg or {})}
    vols, notes = volumes(T)
    rock = rock_config(T, cfg)
    caves = terrain_caves.build(T, rock)
    for cv in caves:
        vols = vols + cv.tubes
        notes = notes + cv.notes
    return Field(T, vols, rock, dolines=[d for cv in caves for d in cv.dolines]), vols, notes, caves


def export_tiles(T, out_dir, cfg: dict | None = None, log=print) -> dict:
    """See `_export_tiles`; holds the machine's heavy-job slot (`resources.heavy`) so exports don't stack up."""
    from . import resources
    with resources.heavy("terrain tiles", log=log):
        return _export_tiles(T, out_dir, cfg, log)


def _export_tiles(T, out_dir, cfg: dict | None = None, log=print) -> dict:
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
    field, vols, notes, caves = build_field(T, cfg)
    base = field  # the whole rock (materials, trees, caves' walk, splats); `field` is what's meshed
    mats = Materials(T, base)
    G = Grid(T, cfg)
    region = None
    if cfg["mode"] == "cliffs":
        from . import terrain_cliffs
        region = terrain_cliffs.Region(T, base, G, cfg)
        field = terrain_cliffs.CliffField(base, region)
    elif cfg["mode"] != "full":
        raise ValueError(f"export.tiles mode {cfg['mode']!r}: use cliffs or full")
    timing["setup"] = time.time() - t0
    tiles = [(i, j) for j in range(G.nj) for i in range(G.ni)]
    if cfg.get("only"):  # a block of tiles [[i0, j0], [i1, j1]] (inclusive), for trying things
        (i0, j0), (i1, j1) = cfg["only"]
        tiles = [(i, j) for (i, j) in tiles if i0 <= i <= i1 and j0 <= j <= j1]
    log(f"{len(tiles)} tiles ({G.ni} x {G.nj}) of {G.tile:g} m, voxel {G.voxel:g} m, LOD errors "
        f"{cfg['error'][:G.lods]} m, {len(vols)} volume pieces")

    # ---- 1. marching cubes per tile, and the canonical border vertices (decided once)
    t0 = time.time()
    v0 = G.voxel
    mc = {}
    reg = {}
    _CTX.update(field=field, G=G, vols=vols, base=base)
    with _pool() as ex:  # (in parallel: serial it was a third of the export)
        for (i, j), r in zip(tiles, ex.map(_job_mc, tiles)):
            mc[i, j] = r
    for (i, j) in tiles:  # canonical border keys numbered in tile order (deterministic)
        if mc[i, j] is not None:
            for key in mc[i, j][3].values():
                reg.setdefault(key, len(reg))
    keys = sorted(reg, key=reg.get) or [(0, 0, 0, 0)]  # (a placeholder when no tile has a mesh)
    a, b, fixed = _key_geometry(keys, G, 0)
    Fa, Fb = _lattice_values(field, a, v0), _lattice_values(field, b, v0)
    tt = Fa / (Fa - Fb)
    CP, CN = project(field, a + tt[:, None] * (b - a), v0, fixed=fixed)
    CW, CC = mats.weights(CP, CN)
    pos = {tuple(p): r for r, p in enumerate(CP)}
    timing["marching cubes + border vertices"] = time.time() - t0

    # ---- 2. border chains per shared plane, simplified once per LOD (nested: each LOD keeps a subset of the last)
    t0 = time.time()
    plane_edges = {}
    for (i, j), r in mc.items():
        if r is None:
            continue
        idx, faces, rng, kk = r
        for (p, q) in _boundary_edges(faces):
            if p in kk and q in kk:
                for plane in _planes(kk[p], kk[q], G, 0):
                    plane_edges.setdefault(plane, set()).add(tuple(sorted((reg[kk[p]], reg[kk[q]]))))
    corner = fixed[:, 0] & fixed[:, 1]
    lines = {pl: _polylines(e) for pl, e in plane_edges.items()}
    keep = []
    prev = {pl: [(ln, closed) for ln, closed in L] for pl, L in lines.items()}
    for k in range(G.lods):
        ks = set(np.flatnonzero(corner).tolist())
        cur = {}
        for pl, L in prev.items():
            simp = []
            for ln, closed in L:
                kept = _simplify(CP, ln, closed, cfg["error"][k], ks)
                simp.append((kept, closed))
                ks.update(kept)
            cur[pl] = simp
        keep.append(ks)
        prev = cur
    timing["border chains"] = time.time() - t0

    # ---- 3. per tile: LOD0 projected; each LOD = border chains collapsed to its kept vertices, then decimated
    t0 = time.time()
    _CTX.update(field=field, G=G, v0=v0, mc=mc, reg=reg, CP=CP, CN=CN, cfg=cfg)
    work = [ij for ij, r in mc.items() if r is not None]
    with _pool() as ex:
        dense = dict(zip(work, ex.map(_job_dense, work)))
    _CTX["dense"] = dense
    # skirts go into the rock, in the border plane, against the surface normal; never out through the other side
    # (a skirt under a cave roof would hang into the cave)
    dirn = -CN.copy()
    dirn[fixed] = 0.0
    ln_ = np.linalg.norm(dirn, axis=1, keepdims=True)
    dirn = np.where(ln_ > 0.2, dirn / np.maximum(ln_, 1e-9), np.array([0, 0, -1.0]))
    thick = _thickness(field, CP, dirn, np.full(len(CP), 3.0), v0)
    pbr = {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.0, "roughnessFactor": 0.92}
    mat = [{"name": "terrain_reference", "pbrMetallicRoughness": pbr},
           {"name": "terrain_skirt", "doubleSided": True, "pbrMetallicRoughness": pbr}]
    rounds = 0
    while True:
        collapsed = {}
        with _pool() as ex:
            for rnd in range(8):
                # where the rock is too thin for the skirt a gap needs, every LOD keeps that vertex (the gap closes)
                need = _needs(lines, keep, CP, G.lods)
                thin = set()
                for k in range(G.lods):
                    d = np.maximum(need[k] * 1.25 + 0.05, cfg["skirt"])
                    thin |= set(np.flatnonzero((need[k] > 1e-6) & (d > thick + 1e-6)).tolist())
                if thin:
                    for kk in keep:
                        kk |= thin
                    continue
                # a vertex a tile can't drop without folding is kept by both its tiles (at every LOD: chains nested)
                failed = set()
                for k in range(G.lods):
                    kr = np.array(sorted(keep[k]), np.int64)
                    for ij, (Fk, bad) in zip(work, ex.map(_job_collapse, [(ij, kr) for ij in work])):
                        collapsed[ij[0], ij[1], k] = Fk
                        failed |= bad
                if not failed:
                    break
                for kk in keep:
                    kk |= failed
            else:
                raise RuntimeError("border chains didn't settle (vertices that can't be collapsed, or rock too "
                                   "thin for a skirt)")
        depth = [np.minimum(np.maximum(need[k] * 1.25 + 0.05, cfg["skirt"]), thick) for k in range(G.lods)]
        timing["border collapse + skirts"] = time.time() - t0

        t0 = time.time()
        manifest_tiles = []
        _CTX.update(mats=mats, cfg=cfg, out=out, vols=vols, collapsed=collapsed, pos=pos, depth=depth, dirn=dirn,
                    CN=CN, CW=CW, CC=CC, mat=mat, keep=[np.array(sorted(kk), np.int64) for kk in keep])
        if cfg.get("maps"):  # the field the maps are baked from: the rock with its bake-only fine relief
            import copy
            from . import terrain_bake
            bfs = []
            for k in range(G.lods):  # (per LOD: the fine relief band-limited to its texel)
                bf = copy.copy(base)
                if base.rock is not None and float(cfg["micro"]) > 0:
                    dens = cfg["texel_density"][min(k, len(cfg["texel_density"]) - 1)]
                    bf.micro = terrain_bake.micro_relief(base.rock, float(cfg["micro"]), 1.0 / dens)
                if region is not None:  # (a cliff's visible face: the rock, its ground sunk toward the region's edge)
                    bf = terrain_cliffs.CliffField(bf, region).front_field()
                bfs.append(bf)
            _CTX.update(bakefield=bfs, layer_rough=np.array([LAYERS[nm]["roughness"] for nm in mats.layers]))
        stats, t_dec = [], 0.0
        with _pool() as ex:
            wanted = set()
            for entry, st, td, wt in ex.map(_job_tile, tiles):
                manifest_tiles.append(entry)
                stats += st
                t_dec += td
                wanted |= wt
        # a vertex a coarse LOD couldn't lose without folding (the dense mesh folded at every count, and an
        # earlier LOD's mesh couldn't drop it either): every LOD keeps it and the tiles are written again
        if not wanted or rounds >= 2:
            break
        rounds += 1
        for kk in keep:
            kk |= wanted
        log(f"{len(wanted)} border vertices kept for coarse LODs that folded; tiles written again")
    timing["tiles (decimate, project, write)"] = time.time() - t0
    timing["of which decimation"] = t_dec

    # ---- 4. heightmap and splat tiles on the same grid (in parallel)
    t0 = time.time()
    hrange = [float(np.nanmin(T.H)), float(np.nanmax(T.H))]
    hm, sp = int(cfg["heightmap"]), int(cfg["splat"])
    for sub in ("heightmaps", "splats"):
        (out / sub).mkdir(exist_ok=True)
    _CTX.update(hrange=hrange)
    ground = []
    if region is not None:
        # the ground: pushed heightmaps, holes, grid meshes; splats as before (on the heightmap's own tiles)
        pbr = {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.0, "roughnessFactor": 0.92}
        cfg["_hrange"] = hrange
        cfg["_layer_rough"] = np.array([LAYERS[nm]["roughness"] for nm in mats.layers])
        cfg["_ground_mat"] = [{"name": "terrain_reference", "pbrMetallicRoughness": pbr},
                              {"name": "terrain_skirt", "doubleSided": True, "pbrMetallicRoughness": pbr}]
        _CTX.update(region=region, mats=mats, cfg=cfg, out=out)
        with _pool() as ex:
            ground = list(ex.map(_job_ground, tiles))
        cfg.pop("_hrange"), cfg.pop("_ground_mat"), cfg.pop("_layer_rough")
        manifest_tiles = [e for e in manifest_tiles if any(e["lods"])]
        timing["ground tiles"] = time.time() - t0
        t0 = time.time()
    with _pool() as ex:
        for e, extra in zip(ground or manifest_tiles,
                            ex.map(_job_maps, [(e["i"], e["j"], e["min"]) for e in (ground or manifest_tiles)])):
            e.update(extra)
    timing["heightmaps + splats"] = time.time() - t0

    # ---- 5. trees and the manifest
    from . import terrain_design as design
    inst = design.trees(T)
    with open(out / "trees.csv", "w") as f:
        f.write("x,y,z,kind,layer\n")
        layers = getattr(T, "tree_layers", {})
        zs = np.zeros(0) if not len(inst) else region.height(inst[:, 0], inst[:, 1]) if region is not None \
            else base.column(inst[:, 0], inst[:, 1])[0]
        # a tree stands only where the solid ground is under it: not over an arch's mouth or a notch the volumes cut
        # away (a cypress stood in the water at the arch), nor on a face the rock relief moved
        if len(inst):
            below = base.value(np.c_[inst[:, :2], zs - 0.3])
            ok = below < 0
            n_drop = int((~ok).sum())
            inst, zs = inst[ok], zs[ok]
            if n_drop:
                notes.append(f"{n_drop} trees dropped: no solid ground under them")
        for (x, y, _, li), z in zip(inst, zs):
            nm, kind = layers.get(int(li), ("", ""))
            f.write(f"{x:.2f},{y:.2f},{z:.2f},{kind},{nm}\n")
    groups = [mats.layers[g:g + 4] for g in range(0, len(mats.layers), 4)]
    layer_tex = {}
    if cfg.get("maps"):
        from . import terrain_bake
        layer_tex = terrain_bake.layer_textures(out, {nm: mats.layer_ref(nm) for nm in mats.layers})
    manifest = {
        "format": "hifipushie terrain tiles 1",
        "units": "m",
        "axes": {"world": "x east, y north, z up", "gltf": "glTF x = east, y = up, z = -north (node translation = "
                                                          "the tile's south-west corner; vertices local to it)"},
        "origin": G.origin.tolist(), "tile_size": G.tile, "grid": [G.ni, G.nj],
        "world_min": G.lo.tolist(), "world_max": G.hi.tolist(),
        "trimmed": "the extent was trimmed to whole coarsest voxels" if G.trimmed else "",
        "voxel": G.voxel,
        "lods": [{"lod": k, "error_m": cfg["error"][k], "budget_triangles": cfg["budget"][k],
                  "made": "LOD0's mesh with the border chains simplified (Douglas-Peucker at error_m, each LOD's chain "
                          "a subset of the one before) and decimated to error_m"} for k in range(G.lods)],
        "skirts": "primitive 1 of each tile (extras.role = skirt, double-sided material): each shared border's chain "
                  "extruded into the rock by how far the neighbours' LOD chains differ there (chains are nested "
                  "subsets, so that's at most their tolerances)",
        "collision": f"collision_<i>_<j>.glb: LOD {cfg['collision']} surface, no skirts, positions only",
        "sea_level": _sea(T),
        "materials": {
            "layers": [{"name": nm, **mats.layer_ref(nm), "weights": f"_WEIGHTS{g}", "channel": c,
                        **({"textures": layer_tex[nm]} if nm in layer_tex else {}),
                        "triplanar": nm in ("rock", "wet_rock")}
                       for g, grp in enumerate(groups) for c, nm in enumerate(grp)],
            "engine_recipe": "per pixel: weights w_i from the weights texture (cliff tiles: maps/<tile>_weights<g>.png "
                             "on TEXCOORD_0) or the splat (ground: TEXCOORD_1) or _WEIGHTS<g> per vertex. Each layer's "
                             "tiling textures (materials/<layer>_albedo/_normal/_height.png) at world position / "
                             "scale: planar (x, -y) on the ground, triplanar (blend by |n|^4 on the world axes) where "
                             "`triplanar` is true or the face is steeper than ~35 deg and in caves. Albedo = baked base "
                             "colour x (sum w_i albedo_i / colour_i) (the layers modulate the tile's macro colour); "
                             "normal = the baked normal with sum w_i detail normal_i blended on top (RNM or whiteout); "
                             "occlusion (ORM R) on indirect light only; roughness ORM G. Height blending (w_i x "
                             "height_i, sharpened) gives crisper layer edges than linear weights.",
            "blend": "layer weights per vertex (_WEIGHTS0, _WEIGHTS1 ... vec4, sum 1) and per tile splat PNGs "
                     "(RGBA = the same layers in the same groups of 4); layers are world-space/triplanar tiling "
                     "textures at `scale` metres",
            "reference": ("the baked material (terrain_baked: base colour, ORM = occlusion/roughness/metallic, "
                          "tangent-space normal, all from the exact field at TEXCOORD_0) shows each tile as authored "
                          "in any glTF viewer; skirts and buried faces use a plain matte material with COLOR_0")
                         if cfg.get("maps") else
                         "COLOR_0 is a display colour (linear) with a plain matte material, so tiles look right in "
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
        "mode": cfg["mode"],
        "config": {k: v for k, v in cfg.items() if not k.startswith("_") and k != "only"},
        "maps": {
            "per tile LOD": "each tile's GLB embeds base colour (JPEG, sRGB), ORM (PNG: R occlusion, G roughness, "
                            "B metallic 0) and normal (PNG, tangent space, OpenGL/glTF: +Y up the texture, against "
                            "the TANGENT attribute) on TEXCOORD_0, its own atlas; lods[].maps gives the size, "
                            "texels/m, fill and how many texels fell back to the low poly",
            "beside": "maps/<tile>_height.png (16-bit, 0.5 = on the low poly, +-height_range_m along its normal: "
                      "for parallax/tessellation) and maps/<tile>_weights<g>.png (the layer weights, RGBA per "
                      "group of 4 in the manifest's layer order, on the same atlas)",
            "detail": "normals come from the exact rock plus bake-only fine relief (facets 0.45-1.2 m, cracks, the "
                      "bedding notch): detail below the meshing voxel lives in the maps, not in triangles",
            "seams": "gutters are baked from the surface past each chart's edge (across tile borders too), so "
                     "filtering and mips read the real neighbour; the seam check compares decoded normals along "
                     "shared borders",
        } if cfg.get("maps") else None,
        "tiles": manifest_tiles,
    }
    if region is not None:
        manifest["cliffs"] = {
            "what": "the ground is the heightmap (ground tiles); `tiles` are 3D cliff meshes laid over it wherever the "
                    f"ground is steeper than {cfg['cliff_slope']:g} deg or a volume opens (cave mouths, arches, "
                    "notches, shafts). Each cliff mesh is a closed shell of rock that pinches out buried under the "
                    "heightmap at its edges: nothing to stitch.",
            "heightmap": f"pushed {region.push:.2f} m into the rock under the cliffs (eroded in plan), so the cliff "
                         "face covers it; holes only where a void opens through it (hole PNG per ground tile: 255 = "
                         "hole, one per heightmap cell, row 0 north)",
            "shell": {"sink_m": round(region.sink, 2), "thick_m": round(region.thick, 2),
                      "cave_wall_m": region.wall, "margin_m": cfg["cliff_margin"]},
            "hole_cells": int(region.holes.sum()),
        }
        manifest["ground"] = ground
        manifest["heightmaps"] = {"samples": int(cfg["heightmap"]), "spacing": region.d,
                                  "format": "float32 .npy absolute metres, north-up; .png 16-bit over the range",
                                  "range": hrange, "note": "pushed under the cliff meshes; edges shared with "
                                  "neighbours; ground_<i>_<j>_lod<k>.glb are the same samples as grid meshes (stride "
                                  "2^k, hole cells left out, vertical skirts on shared borders)"}
    if caves:  # a person walked through every passage
        t0 = time.time()
        from . import terrain_caves
        manifest["caves"] = terrain_caves.check(caves, base, sea=_sea(T))
        timing["cave walk"] = time.time() - t0
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    timing["total before check"] = time.time() - t_all
    t0 = time.time()
    check = seam_check(out) if manifest_tiles else {"summary": {"failures": 0}, "failures": []}
    if region is not None:
        from . import terrain_cliffs
        gc = terrain_cliffs.ground_check(out, manifest, region)
        check["summary"]["ground"] = gc["summary"]
        check["failures"] += gc["failures"]
        check["summary"]["failures"] = len(check["failures"])
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
    what = "cliff mesh tiles" if M.get("mode") == "cliffs" else "3D tiles"
    lines = [f"{what} in {r['out']}: {M['grid'][0]} x {M['grid'][1]} tiles of {M['tile_size']:g} m"
             + (f", {len(M['tiles'])} with cliffs" if M.get("mode") == "cliffs" else "")]
    for k, L in enumerate(M["lods"]):
        tris = [t["lods"][k]["triangles"] for t in M["tiles"] if t["lods"][k]]
        size = sum(t["lods"][k]["bytes"] for t in M["tiles"] if t["lods"][k])
        if tris:
            lines.append(f"LOD {k} (error {L['error_m']:g} m): {sum(tris)} triangles, per tile {min(tris)}-{max(tris)} "
                         f"(median {int(np.median(tris))}), {size / 1e6:.1f} MB")
    if M.get("ground"):
        for k in range(len(M["ground"][0]["lods"])):
            tris = [g["lods"][k]["triangles"] for g in M["ground"]]
            size = sum(g["lods"][k]["bytes"] for g in M["ground"])
            lines.append(f"ground LOD {k}: {sum(tris)} triangles ({min(tris)}-{max(tris)} a tile), {size / 1e6:.1f} MB")
        c = M["cliffs"]
        lines.append(f"heightmap pushed {c['heightmap'].split(' m ')[0].split()[-1]} m under the cliffs; "
                     f"{c['hole_cells']} hole cells")
    lines += [f"volume {n}" for n in M["volumes"]]
    lines += [f"walk: {n}" for n in M.get("caves", [])]
    sc = M["seam_check"]
    if "shared_edges" in sc:
        lines.append(f"seam check: {sc['failures']} failures; shared edges {sc['shared_edges']}, border normals within "
                     f"{sc['border_normal_max_deg']} deg, LOD gaps up to {sc['lod_pairs_max_gap_m']} m all under "
                     f"skirts")
    else:
        lines.append(f"seam check: {sc['failures']} failures")
    if "ground" in sc:
        lines.append("ground check: " + ", ".join(f"{k} {v}" for k, v in sc["ground"].items()))
    sh = [f"LOD {k} {sc[f'lod{k}_shards']['area_pct']}%" for k in range(len(M["lods"])) if f"lod{k}_shards" in sc]
    if sh:
        lines.append("shards (corner normals against their face, share of the area): " + ", ".join(sh))
    lines.append("timing (s): " + ", ".join(f"{k} {v}" for k, v in M["timing_s"].items()))
    return "\n".join(lines)


def _job_tile(ij):
    """Write one tile's LODs and collision (runs in a worker: everything it reads is in _CTX)."""
    i, j = ij
    c = _CTX
    G, v0, field, mats, cfg, out, vols = c["G"], c["v0"], c["field"], c["mats"], c["cfg"], c["out"], c["vols"]
    dense, collapsed, pos, depth, dirn = c["dense"], c["collapsed"], c["pos"], c["depth"], c["dirn"]
    CN, CW, CC, mat = c["CN"], c["CW"], c["CC"], c["mat"]
    stats, t_dec, wanted = [], 0.0, set()
    lo, hi = G.bounds(i, j)
    trans = _to_gltf(np.array([[lo[0], lo[1], 0.0]]))[0]
    entry = {"i": i, "j": j, "min": [float(lo[0]), float(lo[1])], "max": [float(hi[0]), float(hi[1])], "lods": []}
    zmin, zmax = np.inf, -np.inf
    prevs = []
    for k in range(G.lods):
        if (i, j) not in dense:
            entry["lods"].append(None)
            continue
        P, faces0, _ = dense[i, j]
        Fk = collapsed[i, j, k]
        used = np.unique(Fk)
        remap = np.full(len(P), -1, np.int64)
        remap[used] = np.arange(len(used))
        Pk, Fk = P[used], remap[Fk]
        n_mc = len(faces0)
        td = time.time()
        Pd = Fd = None
        if k > 0 and prevs:
            # from the last LOD's mesh (a fifth of the dense one's faces: the count search was most of the export's
            # time), its border collapsed to this LOD's chain; the dense mesh only if that can't be done
            Pp, Fp = prevs[-1]
            rp = np.array([pos.get(tuple(q), -1) for q in Pp])
            Fc, bad = _collapse_border(Pp, Fp, np.flatnonzero((rp >= 0) & ~np.isin(rp, c["keep"][k])), min_dot=0.0)
            if not bad:
                used = np.unique(Fc)
                remap = np.full(len(Pp), -1, np.int64)
                remap[used] = np.arange(len(used))
                Pd, Fd = _decimate(Pp[used], remap[Fc], cfg["error"][k], cfg["budget"][k], field)
                if len(Fd) > 1.15 * cfg["budget"][k] + 64:
                    Pd = Fd = None
        if Pd is None:
            Pd, Fd = _decimate(Pk, Fk, cfg["error"][k], cfg["budget"][k], field)
        if k > 0 and prevs and len(Fd) > max(cfg["budget"][k], len(prevs[-1][1])):
            # this LOD from the dense mesh folded at every count: from an earlier LOD's mesh instead (the last one
            # first), its border collapsed to this LOD's chain (the same chain either way: neighbours still agree)
            for Pp, Fp in reversed(prevs):
                rp = np.array([pos.get(tuple(q), -1) for q in Pp])
                drop = np.flatnonzero((rp >= 0) & ~np.isin(rp, c["keep"][k]))
                Fc, bad = _collapse_border(Pp, Fp, drop, min_dot=0.0)
                if bad:
                    if len(Fd) > 1.2 * cfg["budget"][k]:
                        wanted |= {int(rp[u]) for u in bad}
                    continue
                used = np.unique(Fc)
                remap = np.full(len(Pp), -1, np.int64)
                remap[used] = np.arange(len(used))
                P2, F2 = _decimate(Pp[used], remap[Fc], cfg["error"][k], cfg["budget"][k], field)
                if len(F2) < len(Fd):
                    Pd, Fd = P2, F2
                    break
        t_dec += time.time() - td
        # border vertices must have come through untouched, and be this LOD's chain
        rowd = np.array([pos.get(tuple(p), -1) for p in Pd])
        on = _on_border(Pd, lo, hi)
        if np.any(on & (rowd < 0)):
            raise RuntimeError(f"tile {i},{j} LOD {k}: {int(np.sum(on & (rowd < 0)))} border vertices moved in "
                               f"decimation")
        bd = rowd >= 0
        N = np.zeros_like(Pd)
        before = Pd.copy()
        Pd[~bd], N[~bd] = project(field, Pd[~bd], v0)
        # where projecting a coarse vertex folds its faces, it stays where decimation put it
        fold = ~bd & ((_vertex_normals(Pd, Fd) * N).sum(1) < 0.3)
        if fold.any():
            Pd[fold] = before[fold]
            N[fold] = _vertex_normals(Pd, Fd)[fold]
        N[bd] = CN[rowd[bd]]
        prevs.append((Pd.copy(), Fd.copy()))
        W = np.zeros((len(Pd), len(mats.layers)), np.float32)
        C = np.zeros((len(Pd), 3))
        W[bd], C[bd] = CW[rowd[bd]], CC[rowd[bd]]
        W[~bd], C[~bd] = mats.weights(Pd[~bd], N[~bd])
        # skirts along shared borders (not the world's edge)
        be = _boundary_edges(Fd)
        shared = np.array([_shared(Pd[a_], Pd[b_], lo, hi, G) for a_, b_ in be], bool) if len(be) else np.zeros(0, bool)
        be = be[shared] if len(be) else be
        sv = np.unique(be.ravel()) if len(be) else np.zeros(0, np.int64)
        top = Pd[sv]
        bot = top + dirn[rowd[sv]] * depth[k][rowd[sv]][:, None]
        m = {int(x): r_ for r_, x in enumerate(sv)}
        SP = np.empty((2 * len(sv), 3))
        SP[0::2], SP[1::2] = top, bot
        SN = np.repeat(N[sv], 2, 0)
        SC = np.repeat(C[sv], 2, 0)
        SW = np.repeat(W[sv], 2, 0)
        sf = []
        for a_, b_ in be:  # the face has a -> b; the skirt hangs below it, facing the same way
            ta, tb = 2 * m[int(a_)], 2 * m[int(b_)]
            sf += [(tb, ta, ta + 1), (tb, ta + 1, tb + 1)]
        sf = np.array(sf, np.int64).reshape(-1, 3)
        origin = np.array([lo[0], lo[1], 0.0])
        Ps, Fs, Ns, src = split_normals(Pd, Fd, N, field, bd, NORMAL_H * v0)
        bur = np.zeros(len(Fs), bool)
        if hasattr(field, "front"):
            # a cliff shell: faces off the visible rock (its back, buried under the heightmap) go in their own
            # primitive, so an engine or a bake can skip them
            bur = np.abs(field.front(Ps[Fs].mean(1))) > max(0.3, 2 * cfg["error"][k])
        stem = f"tile_{i}_{j}_lod{k}"
        images, binfo = None, None
        if cfg.get("maps") and (~bur).any():
            Pv, Nv, Cv, Wv, Fv = _compact(Ps, Ns, C[src], W[src], Fs[~bur])
            prim, images, binfo = _textured(Pv, Nv, Wv, Fv, k, origin, lo, stem)
            prims = [prim]
        else:
            prims = [_prim(*_compact(Ps - origin, Ns, C[src], W[src], Fs[~bur]), 0, {"role": "surface"}, mats, lo, cfg)]
        if bur.any():
            prims.append(_prim(*_compact(Ps - origin, Ns, C[src], W[src], Fs[bur]), 1, {"role": "buried"}, mats,
                               lo, cfg))
        if len(sf):
            prims.append(_prim(SP - origin, SN, SC, SW, sf, 1, {"role": "skirt"}, mats, lo, cfg))
        fn = f"{stem}.glb"
        from . import terrain_bake
        write_glb(out / fn, stem, prims, trans, mat + ([terrain_bake.material("terrain_baked")] if images else []),
                  extras={"tile": [i, j], "lod": k, "error_m": cfg["error"][k]}, images=images)
        if k == int(cfg["collision"]):
            cf = f"collision_{i}_{j}.glb"
            write_glb(out / cf, f"collision_{i}_{j}", [{"attrs": {"POSITION": _to_gltf(Pd - origin)},
                                                        "indices": Fd}], trans, None,
                      extras={"tile": [i, j], "collision": True, "from_lod": k})
            entry["collision"] = cf
        zmin, zmax = min(zmin, float(Pd[:, 2].min())), max(zmax, float(Pd[:, 2].max()))
        entry["lods"].append({"file": fn, "triangles": int(len(Fd)), "skirt_triangles": int(len(sf)),
                              "visible_triangles": int((~bur).sum()),
                              "marching_cubes_triangles": int(n_mc), "bytes": (out / fn).stat().st_size})
        if binfo:
            entry["lods"][-1]["maps"] = binfo
        stats.append((i, j, k, len(Fd), len(sf), n_mc, (out / fn).stat().st_size))
    entry["zmin"], entry["zmax"] = zmin, zmax
    entry["volumes"] = sorted({vol.name.split(":")[0] for vol in vols
                               if vol.touches(np.array([lo[0], lo[1], -1e9]), np.array([hi[0], hi[1], 1e9]))})
    return entry, stats, t_dec, wanted


def _corner_normals(P, F, field, h):
    """Each face corner's normal read from the field just inside its face (so on its face's side of a crease), and
    that sample point stepped onto the surface. Samples reading across a crease from their face take its normal."""
    fn = _face_normals(P, F)
    Q = (0.75 * P[F] + 0.25 * P[F].mean(1)[:, None, :]).reshape(-1, 3)
    f, g = field.value_gradient(Q, h)
    gl = np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12)
    Nc = (g / gl).reshape(-1, 3, 3)
    Qs = (Q - (f / gl[:, 0])[:, None] * (g / gl)).reshape(-1, 3, 3)
    off = (Nc * fn[:, None, :]).sum(2) < 0.3
    Nc = np.where(off[..., None], fn[:, None, :], Nc)
    return fn, Nc, Qs


def snap_creases(P, F, field, v, movable, angle=25.0, rounds=2):
    """Vertices beside a crease moved onto it (the point nearest them on the tangent planes their faces see, as dual
    contouring places vertices): marching cubes can't put vertices on a crease that runs across its cells, and the
    crease came out as a row of teeth. Only vertices whose faces turn by more than `angle` are tried; a move is kept
    if it stays within half a voxel, on the surface, and turns no face over."""
    P = P.copy()
    h = NORMAL_H * v
    cosa = math.cos(math.radians(angle))
    for _ in range(rounds):
        fn = _face_normals(P, F)
        vn = _vertex_normals(P, F)
        # candidates: a vertex whose faces disagree with their mean
        worst = np.ones(len(P))
        for c in range(3):
            np.minimum.at(worst, F[:, c], (fn * vn[F[:, c]]).sum(1))
        cand = movable & (worst < cosa)
        if not cand.any():
            break
        # the tangent planes of the candidate and its ring (vertices on the surface, each with the exact normal of
        # its own side): their quadric's minimum is the crease point nearest it, regularised toward where it is
        e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]], F[:, [1, 0]], F[:, [2, 1]], F[:, [0, 2]]])
        e = np.unique(e[cand[e[:, 0]]], axis=0)
        e = np.r_[e, np.repeat(np.flatnonzero(cand), 2).reshape(-1, 2)]
        near = np.unique(e[:, 1])
        _, g = field.value_gradient(P[near], h)
        Nn = np.zeros_like(P)
        Nn[near] = g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-12)
        A = np.zeros((len(P), 3, 3))
        b = np.zeros((len(P), 3))
        n = Nn[e[:, 1]]
        nn = n[:, :, None] * n[:, None, :]
        np.add.at(A, e[:, 0], nn)
        np.add.at(b, e[:, 0], (nn @ P[e[:, 1]][:, :, None])[:, :, 0])
        idx = np.flatnonzero(cand)
        eps = 0.05
        Ai = A[idx] + eps * np.eye(3)[None]
        bi = b[idx] + eps * P[idx]
        x = np.linalg.solve(Ai, bi[:, :, None])[:, :, 0]
        mv = np.linalg.norm(x - P[idx], axis=1)
        ok = (mv < 0.6 * v) & (np.abs(field.value(x)) < 0.1 * v)
        idx, x = idx[ok], x[ok]
        old = P[idx].copy()
        P[idx] = x
        # undo moves that turn a face over
        fn2 = _face_normals(P, F)
        flip = (fn2 * fn).sum(1) < 0.2
        if flip.any():
            bad = np.zeros(len(P), bool)
            bad[F[flip].ravel()] = True
            back = bad[idx]
            P[idx[back]] = old[back]
    return P


def split_normals(P, F, N, field, keep, h, angle=75.0):
    """Hard edges where the rock creases: each face corner reads the field's normal just inside its face; corners that
    disagree with their vertex's normal by more than `angle` (the other side of a crease, or a vertex whose normal
    faces away from the face: a black shard) get a copy of the vertex with their side's normal, copies shared by
    corners that agree. Vertices in `keep` (tile borders: both tiles must match) never split.
    Returns positions, faces, normals and each new vertex's source vertex."""
    fn, Nc, _ = _corner_normals(P, F, field, h)
    cos = math.cos(math.radians(angle))
    Nv = N[F]
    ok = ((Nc * Nv).sum(2) >= cos) & ((Nv * fn[:, None, :]).sum(2) > 0.1)
    ok |= keep[F]
    if ok.all():
        return P, F, N, np.arange(len(P))
    F2 = F.copy()
    newP, newN, src = [], [], []
    groups = {}
    nxt = len(P)
    for f, c in zip(*np.nonzero(~ok)):
        v = int(F[f, c])
        n = Nc[f, c]
        gl = groups.setdefault(v, [])
        for gi, (s, idx) in enumerate(gl):
            m = s / np.linalg.norm(s)
            if m @ n >= cos:
                gl[gi] = (s + n, idx)
                F2[f, c] = idx
                break
        else:
            gl.append((n.copy(), nxt))
            F2[f, c] = nxt
            src.append(v)
            nxt += 1
    for v, gl in groups.items():
        for s, idx in gl:
            newN.append(s / np.linalg.norm(s))
    order = np.argsort([idx for gl in groups.values() for _, idx in gl])
    newN = np.array(newN)[order]
    src = np.array(src, np.int64)
    return np.vstack([P, P[src]]), F2, np.vstack([N, newN]), np.r_[np.arange(len(P)), src]


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


def _textured(P, N, W, F, k, origin, lo, stem):
    """A tile's visible surface with its own UV atlas and baked maps (terrain_bake): the primitive (material 2, the
    baked reference material), the embedded images (base colour, ORM, normal) and a report. Height and layer-weight
    maps go beside the GLB in maps/."""
    from PIL import Image
    from . import terrain_bake
    c = _CTX
    cfg, mats, out, v0 = c["cfg"], c["mats"], c["out"], c["v0"]
    t0 = time.time()
    dens = cfg["texel_density"][min(k, len(cfg["texel_density"]) - 1)]
    uvc, size, d, _ = terrain_bake.unwrap(P, F, dens, int(cfg["texture_max"]))
    sp = terrain_bake.split_corners(P, _unit_rows(N), F, uvc, extra={"W": W})
    T4 = terrain_bake.tangents(sp["P"], sp["N"], sp["uv"], sp["F"])
    reach = max(0.6, 4 * cfg["error"][k] + 0.5)
    bf = c["bakefield"][k]
    surface = lambda Pl, Nl: terrain_bake._surface(bf, Pl, Nl, v0, reach)
    maps, info = terrain_bake.bake(surface, c["base"], mats, sp["P"], sp["N"], T4, sp["uv"], sp["F"], size,
                                   c["layer_rough"], field=bf)
    info["seconds"] = round(time.time() - t0, 1)
    if k == 0:  # how well the triangles follow the rock's creases (terrain_sharp.crease_error)
        fn_ = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
        rock = fn_[:, 2] / np.maximum(np.linalg.norm(fn_, axis=1), 1e-12) < math.cos(math.radians(40))
        if rock.sum() > 16:
            info["crease"] = terrain_sharp.crease_error(P, F, c["field"], max(0.01, v0 / 32), rock=rock)
    (out / "maps").mkdir(exist_ok=True)
    Image.fromarray(maps["height"], "I;16").save(out / "maps" / f"{stem}_height.png")
    wfiles = []
    for g, w in enumerate(maps["weights"]):
        fn = f"maps/{stem}_weights{g}.png"
        Image.fromarray(w, "RGBA").save(out / fn)
        wfiles.append(fn)
    images = [(terrain_bake.jpeg(maps["basecolor"]), "image/jpeg"), (terrain_bake.png(maps["orm"], "RGB"), "image/png"),
              (terrain_bake.png(maps["normal"], "RGB"), "image/png")]
    attrs = {"POSITION": _to_gltf(sp["P"] - origin), "NORMAL": _to_gltf(sp["N"]),
             "TANGENT": np.c_[_to_gltf(T4[:, :3]), T4[:, 3]], "TEXCOORD_0": sp["uv"]}
    sq = int(cfg["splat"])
    if sq:
        mg = int(cfg["splat_margin"])
        Nn = sq + 2 * mg
        Q = sp["P"] - origin
        attrs["TEXCOORD_1"] = np.c_[(Q[:, 0] / cfg["tile"] * sq + mg) / Nn, 1 - (Q[:, 1] / cfg["tile"] * sq + mg) / Nn]
    Wv = sp["W"]
    for g in range(0, Wv.shape[1], 4):
        w = Wv[:, g:g + 4]
        attrs[f"_WEIGHTS{g // 4}"] = np.c_[w, np.zeros((len(w), 4 - w.shape[1]))]
    info.update(size=[int(size[0]), int(size[1])], texels_per_m=round(float(d), 2), height=f"maps/{stem}_height.png",
                weights=wfiles)
    return {"attrs": attrs, "indices": sp["F"], "material": 2, "extras": {"role": "surface"}}, images, info


def _unit_rows(N):
    return N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)


def _compact(P, N, C, W, F):
    """The vertices faces F use, renumbered."""
    used = np.unique(F)
    remap = np.full(len(P), -1, np.int64)
    remap[used] = np.arange(len(used))
    return P[used], N[used], C[used], W[used], remap[F]


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
            if "buried" in d:  # (a cliff shell's back: part of the mesh's structure, not of what is seen)
                empty = (np.zeros((0, 3)), np.zeros((0, 3)), np.zeros((0, 3), np.int64))
                d["visible"] = d.get("surface", empty)
                (P1, N1, F1), (P2, N2, F2) = d["visible"], d.pop("buried")
                d["surface"] = (np.vstack([P1, P2]), np.vstack([N1, N2]), np.vstack([F1, F2 + len(P1)]))
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
        # shading: a face whose corner normals point away from it renders as a black shard (a jump in the field
        # under it, or a fold decimation left)
        sh = _shards([data[i, j, k].get("visible", data[i, j, k]["surface"]) for (i, j) in tiles if (i, j, k) in data])
        summary[f"lod{k}_shards"] = sh
        if sh["area_pct"] > SHARD_LIMIT[min(k, len(SHARD_LIMIT) - 1)]:
            failures.append(f"LOD {k}: {sh['faces']} faces ({sh['area_pct']}% of the area) with corner normals "
                            f"against the face: black shards (e.g. at {sh['at'][:3]})")
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
    if M.get("maps"):  # (6) baked maps agree across borders
        ms = map_seams(out, M["tiles"], lods)
        summary["map_seams"] = ms
        for key, r in ms.items():
            if not r["ok"]:
                failures.append(f"{key}: baked maps differ across tile borders (normals p50/p95/p99/max "
                                f"{r['normal_deg_p50_p95_p99_max']} deg, colour p50/p95 {r['colour_diff_p50_p95']})")
    summary["failures"] = len(failures)
    (out / "seam_check.json").write_text(json.dumps({"summary": summary, "failures": failures}, indent=1))
    return {"summary": summary, "failures": failures}


def read_glb_images(path):
    """The images embedded in a GLB, decoded (float arrays 0..1, rows top first), in texture order."""
    import io
    from PIL import Image
    b = Path(path).read_bytes()
    jl = struct.unpack_from("<I", b, 12)[0]
    doc = json.loads(b[20:20 + jl])
    binb = b[28 + jl:]
    out = []
    for im in doc.get("images", []):
        v = doc["bufferViews"][im["bufferView"]]
        a = np.asarray(Image.open(io.BytesIO(binb[v["byteOffset"]:v["byteOffset"] + v["byteLength"]])), float)
        out.append(a / 255.0)
    return out


def _bilinear(img, uv):
    H, W = img.shape[:2]
    x = np.clip(uv[:, 0] * W - 0.5, 0, W - 1.001)
    y = np.clip(uv[:, 1] * H - 0.5, 0, H - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x0 + 1] * fx * (1 - fy) + img[y0 + 1, x0] * (1 - fx) * fy
            + img[y0 + 1, x0 + 1] * fx * fy)


def _map_side(path, origin_fn, ax, lim):
    """Along a tile's border plane: sample points on its border edges with the baked normal (decoded to world axes,
    through the tile's own TANGENT/NORMAL) and base colour there. {edge key: (world normals (3, 3), colours)}."""
    tr, prims = read_glb(path)
    imgs = read_glb_images(path)
    p = prims[0]
    if "TEXCOORD_0" not in p or len(imgs) < 3:
        return {}
    origin = _from_gltf(tr[None])[0]
    P = _from_gltf(p["POSITION"].astype(np.float64)) + origin
    N = _from_gltf(p["NORMAL"].astype(np.float64))
    T = _from_gltf(p["TANGENT"][:, :3].astype(np.float64))
    w = p["TANGENT"][:, 3].astype(np.float64)
    uv = p["TEXCOORD_0"].astype(np.float64)
    F = p["indices"]
    be = _boundary_edges(F)
    on = (P[be[:, 0], ax] == lim) & (P[be[:, 1], ax] == lim)
    out = {}
    t = np.array([0.25, 0.5, 0.75])[:, None]
    for a, b in be[on]:
        key = frozenset((tuple(P[a]), tuple(P[b])))
        # (the edge's end in a canonical order, so both tiles sample the same points)
        a_, b_ = (a, b) if tuple(P[a]) < tuple(P[b]) else (b, a)
        Nl = _unit_rows(N[a_] * (1 - t) + N[b_] * t)
        Tl = T[a_] * (1 - t) + T[b_] * t
        Tl = _unit_rows(Tl - Nl * (Tl * Nl).sum(1, keepdims=True))
        Bl = np.cross(Nl, Tl) * np.sign(w[a_])
        q = uv[a_] * (1 - t) + uv[b_] * t
        tn = _bilinear(imgs[2], q)[:, :3] * 2 - 1
        g = _unit_rows(tn[:, :1] * Tl + tn[:, 1:2] * Bl + tn[:, 2:3] * Nl)
        out[key] = (g, _bilinear(imgs[0], q)[:, :3])
    return out


def map_seams(out, tiles, lods, kind="tiles"):
    """Baked maps across shared tile borders: the decoded normal and base colour at the same border points from
    both tiles. Returns {angle p50/p99/max deg, colour difference p99} per LOD and the worst places."""
    res = {}
    by = {(e["i"], e["j"]): e for e in tiles}
    for k in range(lods):
        ang, dcol = [], []
        for (i, j), e in by.items():
            for di, dj, ax in ((1, 0, 0), (0, 1, 1)):
                o = by.get((i + di, j + dj))
                if o is None or not e["lods"][k] or not o["lods"][k]:
                    continue
                lim = e["max"][ax]
                A = _map_side(out / e["lods"][k]["file"], None, ax, lim)
                B = _map_side(out / o["lods"][k]["file"], None, ax, lim)
                for key in set(A) & set(B):
                    ang.append(np.degrees(np.arccos(np.clip((A[key][0] * B[key][0]).sum(1), -1, 1))))
                    dcol.append(np.abs(A[key][1] - B[key][1]).max(1))
        if ang:
            a, c = np.concatenate(ang), np.concatenate(dcol)
            lim = MAP_SEAM[min(k, len(MAP_SEAM) - 1)]
            pa = [round(float(np.percentile(a, q)), 2) for q in (50, 95, 99)] + [round(float(a.max()), 2)]
            pc = [round(float(np.percentile(c, q)), 3) for q in (50, 95)]
            res[f"lod{k}"] = {"points": int(len(a)), "normal_deg_p50_p95_p99_max": pa, "colour_diff_p50_p95": pc,
                              "ok": bool(pa[0] <= lim[0] and pa[1] <= lim[1] and pc[1] <= lim[2])}
    return res


SHARD_LIMIT = [0.01, 0.05, 0.5]  # % of a LOD's area allowed to have corner normals against its faces
# the same border point decoded from both tiles' maps (each samples its own texels, 8-bit, bilinear): normals p50 and
# p95 (deg) and colour p95 (0..1) allowed, per LOD. A seam would shift the median; a few aliased texels at sharp
# detail don't. LOD 2 (0.4 m texels on a mesh 0.5 m off the rock) is looser: where its triangles stray far from the
# rock's normal the map can't bend past its surface (z >= 0.02) and the two sides clamp differently
MAP_SEAM = [(3.0, 15.0, 0.08), (3.0, 15.0, 0.08), (6.0, 50.0, 0.2)]


def _shards(surfs):
    """Faces with a corner normal against the face (dot < 0): count, area share, worst places."""
    n = a_bad = a_all = 0
    at = []
    for P, N, F in surfs:
        fn = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
        A = np.linalg.norm(fn, axis=1) / 2
        fn /= np.maximum(2 * A, 1e-20)[:, None]
        m = np.einsum("fcj,fj->fc", N[F], fn).min(1)
        b = m < 0
        n += int(b.sum())
        a_bad += float(A[b].sum())
        a_all += float(A.sum())
        at += [(float(A[f]), P[F[f]].mean(0).round(1).tolist()) for f in np.flatnonzero(b)]
    at = [p for _, p in sorted(at, reverse=True)[:5]]
    return {"faces": n, "area_m2": round(a_bad, 2), "area_pct": round(100 * a_bad / max(a_all, 1e-9), 4), "at": at}


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


def render_tiles(T, out_dir, views, lod=0, size=(1400, 800), samples=48, trees=True, box=None, skirt_color=None,
                 parts="all", textured=True):
    """Cycles renders of the written tiles, imported by Blender's glTF importer. views: {"name", "eye": address |
    [x, y] | [x, y, z], "lift" (m above the ground or the sea), "look": address | [x, y, z], "fov", "sun": [bearing,
    height], "borders": bool, "lamp": watts (a headlamp at the eye, for inside caves), "out"}. box: [[x0, y0],
    [x1, y1]]: only tiles (and trees) inside. lod: a level, or
    "checker" (LOD 0 and the coarsest alternating, to see the skirts at work). parts (cliffs mode): "all", "ground"
    (the heightmap alone: what a game shows without the overlay) or "cliffs". textured: True (the baked material),
    "layered" (the engine recipe: tiling layers over the baked maps) or False (vertex colour)."""
    import subprocess
    out = Path(out_dir)
    M = json.loads((out / "manifest.json").read_text())
    glbs = []
    for e in M["tiles"] * (parts != "ground") + M.get("ground", []) * (parts != "cliffs"):
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
                     "lamp": v.get("lamp", 0.0), "exposure": v.get("exposure", 0.0), "fill": v.get("fill", 0.4),
                     "fill_at": v.get("fill_at", 8.0),
                     "borders": v.get("borders", False), "out": str(Path(v["out"]).resolve())})
    job = {"glbs": glbs, "sea": sea, "size": list(size), "samples": samples, "views": jobs,
           "trees": str(out / "trees.csv") if trees else None, "tree_box": box, "skirt_color": skirt_color,
           "textured": bool(textured)}
    if textured == "layered":  # the engine recipe: tiling layers over the baked maps
        job["layers"] = [{"path": str((out / L["textures"]["height"]).resolve()), "scale": L["scale"],
                          "strength": L["textures"]["detail_strength"], "attr": L["weights"], "channel": L["channel"]}
                         for L in M["materials"]["layers"] if "textures" in L]
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
