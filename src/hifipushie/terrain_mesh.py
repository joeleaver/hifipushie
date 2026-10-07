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
import os
import math
import struct
import time
import zlib
from pathlib import Path

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from . import fieldjit, noise, profiling, terrain_sharp
from .profiling import span as _span


def _f64(a):
    """A 1D contiguous float64 array (what the compiled kernels take)."""
    return np.ascontiguousarray(np.asarray(a, dtype=np.float64).ravel())

DEFAULTS = {
    "tile": 64.0,          # metres a side
    "voxel": 0.5,          # the meshing voxel (divides the tile); coarser LODs are LOD0 decimated
    "lods": 3,
    "origin": None,        # world grid origin [x, y]; default the extent's south-west corner
    "error": [0.04, 0.15, 0.5],     # decimation tolerance per LOD, metres
    "budget": [12000, 3000, 800],   # triangle cap per tile per LOD (the border chains are always kept)
    "skirt": 0.3,          # minimum skirt depth, metres
    "collision": 1,        # which LOD the collision mesh is made from
    "collision_budget": None,  # triangles a tile's collision mesh may have (default 2 x that LOD's budget): a LOD
                           # that came out heavier is decimated further for collision alone (no seam guarantees)
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
    "texel_density": [8.0, 4.0, 2.0],  # texels per metre per LOD (a tile's atlas is capped at texture_max): the macro
                           # maps; below ~0.5 m the tiling detail draws the rock (`detail`). Unique maps alone
                           # wanted 16/m at LOD 0 and were still mush at 10 m (renders m01)
    "texture_max": 2048,
    "ground_density": 4.0,  # (cliffs) the ground tiles' maps, texels per metre at LOD 0
    "micro": 1.0,          # bake-only fine rock relief (facets, cracks, laminae below the voxel); 0 = none
    "detail": True,        # the tiling rock detail (terrain_swatch): swatches in materials/ and, on cliff tiles, a
                           # strike-binned UV set (TEXCOORD_n, metres) + _DETAIL (strike x, y, side share, bed v)
    "detail_source": "procedural",  # the swatch: "procedural" (terrain_swatch.swatch) or "scan:<set>" (a CC0
                           # photoscan from the rock_scans asset pack: terrain_swatch.scan_swatch)
    "checks": True,        # the seam/ground/pattern checks after writing (off for previews)
}

DENSITY_FILL = 0.55  # the share of an atlas the packer fills (for choosing one texel density that fits every tile)

# ground materials: what each cover type lays on the ground (tree layers: the forest floor under them)
LAYER_OF = {"meadow": "grass", "grass": "grass", "orchard": "grass", "mown": "turf", "lawn": "turf", "fairway": "turf",
            "green": "turf", "rough": "grass",
            "scrub": "scrub", "heath": "scrub", "bunker": "sand", "forest": "forest_floor",
            "conifer": "forest_floor", "deciduous": "forest_floor", "rock": "rock", "scree": "rock", "sand": "sand",
            "mud": "earth", "snow": "snow"}
LAYERS = {  # reference look (sRGB colour, roughness) and a triplanar tiling scale (m) for engines
    "grass": {"color": [0.36, 0.47, 0.20], "roughness": 0.95, "scale": 3.0},
    "turf": {"color": [0.30, 0.50, 0.17], "roughness": 0.9, "scale": 2.0},  # (mown grass: fairways, greens, lawns)
    "forest_floor": {"color": [0.27, 0.22, 0.15], "roughness": 0.95, "scale": 3.0},
    "scrub": {"color": [0.30, 0.33, 0.21], "roughness": 0.95, "scale": 2.0},
    "sand": {"color": [0.72, 0.65, 0.48], "roughness": 0.9, "scale": 2.0},
    "rock": {"color": [0.36, 0.34, 0.31], "roughness": 0.85, "scale": 6.0},  # (the heightfield views' rock)
    "wet_rock": {"color": [0.17, 0.16, 0.15], "roughness": 0.55, "scale": 6.0},
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



STACK = {"radius": 0.75, "bed": 1.6, "beds": 0.4, "notch": 0.7, "ramp": 1.0, "lean": 10.0, "lobes": 0.55,
         "twist": 6.0}
# a solid sea stack: its radius x the sea's stack radius, bed thickness m, how far beds stand out / sit back (x r,
# +-half), the outline's lobes (x r) and how fast they change up the stack (m), its sides' lean (deg),
# the waterline notch (x min(0.3 r, 1.6 m)), each bed handing over to the next across `ramp` m (2 voxels: shards)


class Stack:
    """A sea stack as solid rock (op "add" over the heightfield's own stack): a lobed, grooved prism whose sides lean in
    ~6 deg, a flat top tilted a little and notched, edges bevelled ~0.35 m. The heightfield can't hold a 70-80 deg
    side on 1-2 m cells: its stacks came out as rounded loaves (the user's p05/L01 views)."""

    def __init__(self, name, xy, base, top, r, seed, blend=0.4, clip=None):
        self.name, self.op, self.blend, self.relief = name, "add", float(blend), 1.0
        # the heightfield's own stack (a slim core) taken away within `clip` m of the centre above the plinth, so the
        # solid stack alone is the form: two steep surfaces crossing inside its notch and lobes meshed as shards
        self.clip = None if clip is None else (float(clip), float(base) + 0.5)
        self.xy, self.base, self.top, self.r, self.seed = np.asarray(xy, float), float(base), float(top), float(r), \
            int(seed)
        rng = np.random.default_rng(self.seed)
        self.k_g = int(rng.integers(5, 9))
        self.ph = rng.uniform(0, 6.3, 2)
        self.tilt = rng.uniform(0.12, 0.35) * (top - base) / max(r, 1e-6)
        self.tdir = rng.uniform(0, 2 * math.pi)
        self.lean = math.tan(math.radians(STACK["lean"]))
        m = max(self.r * (1.6 + STACK["beds"]) + (top - base) * self.lean, self.clip[0] if self.clip else 0.0) + \
            self.blend + NEAR + 1.0
        self.lo = np.r_[self.xy - m, self.base - 1.0 - NEAR]
        self.hi = np.r_[self.xy + m, self.top + 1.0 + NEAR]

    def sd(self, p, detail=False):
        q = p[:, :2] - self.xy
        d = np.hypot(q[:, 0], q[:, 1])
        th = np.arctan2(q[:, 1], q[:, 0])
        u = np.c_[np.cos(th), np.sin(th), np.zeros(len(p))]
        # (the outline's lobes change up the stack, ~6 m: the same polygon all the way up read as a crate)
        lob = noise.fbm(u * 1.3 + np.c_[np.full(len(p), float(self.seed % 97)), np.zeros(len(p)),
                                         (p[:, 2] - self.base) / STACK["twist"]], 1.0, 3, seed=self.seed + 17)
        grooves = 0.06 * np.cos(self.k_g * th + self.ph[0]) + 0.03 * np.cos((self.k_g + 3) * th + self.ph[1])
        z = p[:, 2]
        # layered: each bed stands out or sits back on its own (and by a different amount round the stack), handing
        # over to the next across ~0.6 m (a step: shards); the sea's notch undercuts it at the waterline (a stack
        # standing on a fat skirt read as a bulky prism)
        b = STACK["bed"]
        zb = (z - self.base) / b
        kb = np.floor(zb)
        f = zb - kb
        bo = lambda k: (noise._hash(k.astype(np.int64), np.zeros_like(k, dtype=np.int64),
                                    np.zeros_like(k, dtype=np.int64), self.seed + 91) - 0.5)
        lo, hi = bo(kb), bo(kb + 1)
        e = STACK["ramp"] / b
        t = smoothstep(1 - e, 1.0, f)
        bed = (lo * (1 - t) + hi * t) * (1 + 0.6 * (lob - 0.5)) * smoothstep(0.8, 2.5, self.top - z)
        sea = self.base + 2.0
        notch = STACK["notch"] * min(self.r * 0.3, 1.6) * np.exp(-((z - sea - 0.9) / 1.2) ** 2)
        R = self.r * (1 + STACK["lobes"] * (lob - 0.5) + grooves + STACK["beds"] * bed) + (self.top - z) * self.lean \
            - notch
        side = (d - R) * 0.92
        along = q[:, 0] * math.cos(self.tdir) + q[:, 1] * math.sin(self.tdir)
        topz = self.top - self.tilt * np.clip(along + self.r, 0, 2 * self.r) * 0.5 \
            - 0.22 * (self.top - self.base) * np.clip(lob - 0.55, 0, None) / 0.45
        f = smax(side, p[:, 2] - topz, 0.35)
        f = smax(f, (self.base - 1.0) - p[:, 2], 0.3)
        if detail:
            return f, np.full(len(p), np.inf), np.full(len(p), self.r)
        return f

    def touches(self, lo, hi):
        return bool(np.all(self.hi >= lo) and np.all(self.lo <= hi))


def stacks(T):
    """The sea's stacks (terrain_sea) as solid prisms for the 3D tiles, and a note. Off with export.tiles "stacks":
    false."""
    st = (getattr(T, "sea", None) or {}).get("stacks") or []
    sea = _sea(T)
    out = []
    for i, a in enumerate(st):
        xy = np.asarray(a["xy"], float)
        top = sea + float(a["height"])
        from .terrain_sea import STACK_CORE
        rc = STACK_CORE * float(a["radius"]) + 0.11 * float(a["height"]) + 0.8  # (the core, spread at 84 deg, + margin)
        out.append(Stack(f"stack{i}", xy, sea - 2.0, top, STACK["radius"] * float(a["radius"]), 3000 + i, clip=rc))
    note = (f"stacks: {len(out)} as solid rock prisms (sides ~84 deg, flat tilted tops), "
            f"{min(a['height'] for a in st):.0f}-{max(a['height'] for a in st):.0f} m out of the water") if out else None
    return out, note


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


def _daylight_back(T, xy, t, above, reach):
    """Distance along t from xy to the first ground higher than `above` (land standing in a line of sight), or None."""
    st = np.arange(0.0, reach, T.cell / 2)
    k = np.flatnonzero(T.sample(xy + st[:, None] * t) > above)
    return float(st[k[0]]) if len(k) else None


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
                height, w, roof = _arch_size(v, top - floor, roof_min)
                if height is None:
                    continue
                ts = [_bearing(T, v["toward"], c)] if "toward" in v else [
                    np.array([math.sin(math.radians(b_)), math.cos(math.radians(b_))]) for b_ in range(0, 180, 10)]
                for t in ts:
                    s1 = _daylight(T, c, t, floor + 0.5 * height, reach=80)
                    s2 = _daylight(T, c, -t, floor + 0.5 * height, reach=80)
                    if s1 is None or s2 is None:
                        continue
                    # short for its height (length over height), near `at`, and daylight through it: land standing
                    # in its line just past a mouth fills the opening with rock (pebble's first neck framed a rock
                    # 9 m off)
                    zc = floor + 0.75 * height  # (rocks awash in front of a mouth don't close it)
                    blocked = sum(_daylight_back(T, c + t * sg * (s_ + 2.0), t * sg, zc, 60.0) is not None
                                  for sg, s_ in ((1, s1), (-1, s2)))
                    # (and big enough to read: 6 m / height; daylight through it weighs more than its length, since
                    # the neck cut makes a long one a fin anyway)
                    score = (s1 + s2) / height + 0.01 * float(np.linalg.norm(c - at)) + 3.0 * blocked + 6.0 / height
                    if best is None or score < best[0]:
                        best = (score, c, t, s1, s2, top, height, w)
            if best is None:
                raise ValueError(f"volume {name!r}: no place within {R:.0f} m of {v['at']!r} where an arch fits (land "
                                 f"that comes out into the open both ways, {roof_min:g} m of roof over it, at least "
                                 f"half its span)")
            _, c, t, s1, s2, top, height, w = best
            # irregular: mouths flared and taller than the middle, the line bending a little
            side = np.array([-t[1], t[0]])
            u = np.linspace(-1, 1, 5)
            along = np.where(u < 0, u * (s2 + 0.5 * w), u * (s1 + 0.5 * w))
            bend = 0.12 * w * math.sin(seed) * (1 - u * u)
            xy = c + along[:, None] * t + bend[:, None] * side
            flare = 1 + 0.3 * u * u
            common["rough"] = v.get("rough", 0.25)
            tube = Tube(name, np.c_[xy, np.full(5, floor)], w / 2 * flare, height * (1 + 0.12 * u * u), floor,
                        **common)
            # the neck: a sea arch goes through a fin of rock about as thick as the arch is tall (Durdle Door, the
            # Green Bridge of Wales). Through a wider headland the arch read as a tunnel with a turf lid ("a cave with
            # a cover over it", the user on pebble's 38 m arch): the sea's bays cut in on both sides until the rock
            # left round the arch is `through` metres thick, over `neck` metres either side of it
            through = float(v.get("through", max(4.0, 0.9 * height)))
            land = s1 + s2
            tube.kind = "arch"
            tube.arch = {"c": c, "t": t, "s1": s1, "s2": s2, "w": w, "height": height, "floor": floor,
                         "bend": 0.12 * w * math.sin(seed), "through": min(through, land)}
            if land > 1.25 * through:
                neck = float(v.get("neck", max(6.0, 1.2 * w)))
                tube.cut = {"kind": "neck", "c": c.tolist(), "t": t.tolist(), "a1": s1 + 0.5 * w, "a2": s2 + 0.5 * w,
                            "hw": 0.5 * w, "neck": neck, "through": through, "floor": floor,
                            "bend": 0.12 * w * math.sin(seed)}
            out.append(tube)
            shape = (f"through a neck {through:.0f} m thick (bays cut in from {land:.0f} m of land)"
                     if land > 1.25 * through else f"{land:.0f} m through the rock")
            notes.append(f"{name}: arch at [{c[0]:.0f}, {c[1]:.0f}] heading {math.degrees(math.atan2(t[0], t[1])) % 180:.0f}"
                         f" deg, {w:.1f} m wide, {height:.1f} m high over a floor at {floor:+.1f} m, {shape}, roof "
                         f"{top - floor - height:.1f} m thick at its middle")
        elif kind in ("cave", "tunnel"):
            t = _bearing(T, v["toward"], at) if "toward" in v else adir if adir is not None else -_downhill(T, at)
            floor0 = float(v.get("floor", (sea - 0.5) if sea is not None else T.height(at)))
            w, h = float(v.get("width", 4.5)), float(v.get("height", 6.0))  # (taller than wide: sea caves follow joints)
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
            # a roof of at least ROOF_SPAN x the span (and 1.5 m) over every node under the ground: the passage
            # lowers where the rock over it thins, and ends where even a 1.8 m passage wouldn't keep it (a 0.7 m roof
            # broke through; a turf skin over a hole read as a lid)
            ground = T.sample(xy)
            rmin = np.maximum(1.5, ROOF_SPAN * 2 * rw)
            room = ground - fl - rmin
            under = ground > fl + 0.5 * rh  # (the part out in the open has no roof)
            fix = []
            if v.get("roof_rule", True):
                lowered = under & (room < rh)
                keep = ~(under & (room < 1.8))
                stop = int(np.argmin(keep)) if not keep.all() else len(keep)
                if stop < len(keep):
                    fix.append(f"ends after {s[max(stop - 1, 0)]:.0f} m (the rock over it thins under "
                               f"{float(rmin[stop]) + 1.8:.1f} m)")
                    xy, fl, rw, rh, ground, rmin, under = (a[:max(stop, 2)] for a in (xy, fl, rw, rh, ground, rmin,
                                                                                       under))
                lowered = lowered[:len(rh)]
                if lowered.any():
                    rh = np.where(lowered, np.maximum(1.8, np.minimum(rh, ground - fl - rmin)), rh)
                    fix.append(f"lowered to {float(rh[lowered].min()):.1f} m where the rock thins")
            out.append(Tube(name, np.c_[xy, fl], rw, rh, fl, **common))
            ch = float(v.get("chamber", 0.0))
            if ch > 0 and len(xy) == n + 1:  # a domed chamber at the end, on the passage's floor
                g_end = float(T.sample(xy[-1:])[0])
                ch_fit = min(ch, (g_end - fl[-1]) / (0.8 + 2 * ROOF_SPAN), (g_end - fl[-1] - 1.5) / 0.8) \
                    if v.get("roof_rule", True) else ch
                if ch_fit < ch:
                    fix.append(f"chamber r {ch:.0f} -> {max(ch_fit, 0):.1f} m (its roof)")
                    ch = ch_fit
                if ch >= 1.5:
                    out.append(Tube(name + ":chamber", [[*xy[-1], fl[-1]]], ch, 0.8 * ch, fl[-1], **common))
            inside = ground > fl + rh
            roof = float(np.min((ground - (fl + rh))[inside])) if inside.any() else float("nan")
            shape = " (wider than tall: sea caves follow joints, mostly taller than wide)" if w > 1.15 * h else ""
            notes.append(f"{name}: cave {w:g} x {h:g} m{shape}, mouth at [{mouth[0]:.0f}, {mouth[1]:.0f}] floor "
                         f"{floor0:+.1f} m, {L:.0f} m in" + (f", chamber r {ch:.0f} m" if ch else "")
                         + f"; thinnest roof {roof:.1f} m" + (" (it breaks through)" if roof < 1 else "")
                         + ("; " + ", ".join(fix) if fix else ""))
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
            # the rock over the notch: where the ground behind the face is too low to roof it (1.5 m and ROOF_SPAN x
            # its height), the notch is shallower there (it broke through behind a low stretch of cliff)
            hh = h * (0.6 + 0.4 * ease)
            if v.get("roof_rule", True):
                for i, p_ in enumerate(pts):
                    dn = _downhill(T, p_)
                    for fr in (1.0, 0.8, 0.6, 0.45, 0.3, 0.2):
                        if T.height(p_ - dn * depth * ease[i] * fr) - floor - hh[i] >= max(1.5, ROOF_SPAN * hh[i]):
                            break
                    else:  # (a low stretch of cliff: the notch dies out to a nick)
                        fr = 0.15
                        hh[i] = max(0.5, min(hh[i], T.height(p_) - floor - 1.5))
                    ease[i] *= fr
            out.append(Tube(name, np.c_[pts, np.full(len(pts), floor)], depth * ease, hh, floor, **common))
            lip = np.array([float(T.height(p_ - _downhill(T, p_) * depth * e_)) for p_, e_ in zip(pts, ease)]) \
                - floor - hh
            notes.append(f"{name}: overhang notch {depth:.1f} m deep, {h:.1f} m high over a floor at {floor:+.1f} m, "
                         f"{L:.0f} m along the cliff; {lip.min():.1f}-{lip.max():.1f} m of rock over it")
        else:
            raise ValueError(f"volume {name!r}: type {kind!r}: use arch, cave or overhang")
        if common["op"] not in ("subtract", "add"):
            raise ValueError(f"volume {name!r}: op {common['op']!r}: use subtract or add")
    return out, notes


ROOF_SPAN = 0.5  # the rock over an opening: at least this share of its span (thinner read as a lid on a hole)


def _arch_size(v, avail, roof_min):
    """An arch's height, span and roof from the rock standing over its floor (avail): 0.65 of it high unless given,
    0.8 of that wide (capped at 8 m; arches are taller than wide), and a roof of at least `roof_min` and ROOF_SPAN x
    the span. (None, ...) where it doesn't fit."""
    h = float(v.get("height", 0.65 * avail))
    w = float(v.get("width", min(8.0, 0.8 * h)))
    for _ in range(4):
        roof = max(roof_min, ROOF_SPAN * w)
        if avail - h >= roof - 1e-6:
            break
        h = avail - roof
        if "width" not in v:
            w = min(8.0, 0.8 * h)
    roof = max(roof_min, ROOF_SPAN * w)
    if h < 2 or avail - h < roof - 1e-6:
        return None, None, None
    return h, w, roof


def cut_neck(T, H, c):
    """A sea arch's neck dug into the ground grid: on each side of the arch the ground down to its floor where the
    land along the arch's line is more than `through`/2 from its middle, over `hw` + `neck` metres across (the
    bays narrowing to nothing at the neck's ends), so the rock round the arch is a fin `through` m thick."""
    t = np.asarray(c["t"], float)
    n = np.array([-t[1], t[0]])
    dx, dy = T.X - c["c"][0], T.Y - c["c"][1]
    a = dx * t[0] + dy * t[1]
    A = np.where(a >= 0, c["a1"], c["a2"])
    u = np.clip(np.where(a >= 0, a / c["a1"], a / c["a2"]), -1, 1)
    b = dx * n[0] + dy * n[1] - c["bend"] * (1 - u * u)
    hw, B, th = c["hw"], c["neck"], 0.5 * c["through"]
    # the neck's half thickness: `through`/2 at the arch, opening out to the whole land at the bays' far sides
    half = th + (A - th) * smoothstep(hw, hw + B, np.abs(b))
    wgt = smoothstep(half, half + 1.0, np.abs(a)) * smoothstep(A + c["hw"] + 4.0, A + c["hw"], np.abs(a)) \
        * smoothstep(hw + B + 1.0, hw + B, np.abs(b))
    return H - wgt * np.maximum(H - c["floor"], 0.0)


def through_view(field, tube, reach=300.0):
    """Does an arch show daylight? Rays parallel to its line through a grid over its opening (above the water), marched
    through the rock: the share that come out the far side clear is the see-through share. Beyond each mouth the
    centre ray runs on `reach` m: what it meets (sea/sky, or land at what distance) is what the opening frames."""
    A = tube.arch
    t = np.r_[np.asarray(A["t"], float), 0.0]
    n = np.array([-t[1], t[0], 0.0])
    c = np.r_[np.asarray(A["c"], float), 0.0]
    sea = A["floor"] + 1.0
    lo = max(A["floor"], sea) + 0.3
    hw = 0.5 * A["w"]
    us = np.linspace(-0.9, 0.9, 9) * hw
    zs = np.linspace(lo, A["floor"] + 0.95 * A["height"], 7)
    U, Z = np.meshgrid(us, zs)
    inside = (U / hw) ** 2 + ((Z - A["floor"]) / A["height"]) ** 2 <= 1.0  # (the ellipse over its floor)
    U, Z = U[inside], Z[inside]
    s = np.arange(-(A["s2"] + hw + 2.0), A["s1"] + hw + 2.0, 0.25)
    P = (c + U[:, None, None] * n + Z[:, None, None] * np.array([0, 0, 1.0]) + s[None, :, None] * t
         ).reshape(-1, 3)
    P[:, :2] += 0  # (the bend: under 1 m, inside the 0.9 x half width margin)
    F = field.value(P).reshape(len(U), len(s))
    clear = float((F > 0).all(1).mean()) if len(U) else 0.0
    zc = A["floor"] + 0.75 * A["height"]  # (land standing over most of the opening; rocks awash don't count)
    beyond = {}
    for sign, key in ((1, "ahead"), (-1, "behind")):
        d = np.arange(0, reach, 1.0)
        start = c + t * sign * ((A["s1"] if sign > 0 else A["s2"]) + 2.0)
        Q = start[None] + sign * d[:, None] * t
        h, _ = field.column(Q[:, 0], Q[:, 1])
        k = np.flatnonzero(h > zc)
        beyond[key] = None if not len(k) else float(d[k[0]])
    b = math.degrees(math.atan2(t[0], t[1])) % 360
    say = lambda d, bb: (f"open sea/sky toward {bb:.0f} deg" if d is None else f"land {d:.0f} m off toward {bb:.0f} deg")
    note = (f"{tube.name}: see-through {100 * clear:.0f}% of the opening (rays along it, above the water); beyond: "
            f"{say(beyond['ahead'], b)}, {say(beyond['behind'], (b + 180) % 360)}"
            + (" -- WARNING: the arch barely shows daylight" if clear < 0.5 else ""))
    return {"clear": round(clear, 3), "ahead_land_m": beyond["ahead"], "behind_land_m": beyond["behind"], "note": note}


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

def rock_relief(p, r, g=None, jw=None, fd=None, u=None, blk=None, thin=None):
    """Solid rock character as a field offset (+ carves, - builds): planar facets meeting in crisp creases, and bedding
    (a V notch at each bedding plane, each bed standing proud or set back on its own, stepping over at its edge).
    Continuous everywhere with C0 creases, never jumps: a jump (the nearest cell's plane alone) meshed as steps whose
    normals pointed sideways (black shards), and blending the cells smoothly read as mush. The mesh shows the creases
    with split normals (`split_normals`). The heightfield's own rock (terrain_rock) moves the ground in plan only;
    this can overhang. fd: the ground's gradient per point (the face's orientation: facets on irregular triangles laid
    on the face, `facet`); u: 0..1 how much of the point's relief comes from a volume (a cave's walls and roof, which
    the ground's gradient says nothing about: facets in 3D there); thin: 0..1 per point, thin rock (Field.thin_at),
    where the soft beds are picked out (`strata`: fins and stacks are where the sea does that)."""
    fac = lambda size, seed: facet(p, size, seed, fd, u)
    uvol = u  # (the volumes' share; `u` is reused below)
    profiling.count("facets pts", len(p))
    if g is None:
        out = r["facets"] * (fac(r["size"], r["seed"]) + 0.4 * fac(0.43 * r["size"], r["seed"] + 5))
    else:
        # facet size follows the face's structure (g: 0 on buttresses and open faces, 1 in gullies and near the
        # top): big planes where the rock stands out, small broken facets where it's cut up; one facet size
        # everywhere read as evenly crumpled paper (the alps walls)
        out = np.zeros(len(p))
        kc, kf = np.flatnonzero(g < 1), np.flatnonzero(g > 0)
        # (with jointed blocks the finer facet octaves go: the blocks are the medium scale, and facets inside blocks
        # read as crumpled soft slabs)
        # (on volumes' walls (u) as before: the blocks don't go there)
        fine = np.ones(len(p)) if not r.get("blocks") else (np.zeros(len(p)) if u is None else np.asarray(u, float))
        if len(kc):
            sub = lambda size, seed: facet(p[kc], size, seed, None if fd is None else fd[kc], None if u is None else u[kc])
            big = sub(1.5 * r["size"], r["seed"])
            fk = fine[kc]
            sm = np.flatnonzero(fk > 0)
            add = np.zeros(len(kc))
            if len(sm):
                add[sm] = fk[sm] * 0.3 * facet(p[kc][sm], 0.6 * r["size"], r["seed"] + 5,
                                               None if fd is None else fd[kc][sm], None if u is None else u[kc][sm])
            out[kc] += (1 - g[kc]) * 1.1 * (big + add)
        if len(kf):
            sub = lambda size, seed: facet(p[kf], size, seed, None if fd is None else fd[kf], None if u is None else u[kf])
            mid = 0.55 * sub(0.45 * r["size"], r["seed"] + 11)
            fk = fine[kf]
            sm = np.flatnonzero(fk > 0)
            add = np.zeros(len(kf))
            if len(sm):
                add[sm] = fk[sm] * 0.35 * facet(p[kf][sm], 0.2 * r["size"], r["seed"] + 12,
                                                None if fd is None else fd[kf][sm], None if u is None else u[kf][sm])
            out[kf] += g[kf] * ((1.3 - 0.3 * fk) * mid + add)
        out = r["facets"] * out
    if r["bedding"] > 0:
        B = bed_planes(p, r, g)
        kb, f, lower, xy = B["kb"], B["f"], B["lower"], p[:, :2]
        edge = np.minimum(f, 1 - f)
        # each bed stands proud or set back, by an amount that changes along the strike (one offset per bed made the
        # step a ruler-straight line across the whole wall: "reads like a seam"), stepping over to the next in a
        # straight ramp either side of the bedding plane (creases at both ends: a crisp step, no jump). Where the plane
        # is absent (`pres` low: patches along the strike, gullies) the ramp widens to metres: the beds merge
        off = lambda k, i=slice(None): 2 * _bed_noise(xy[i], k, 28.0, r["seed"] + 20) - 1
        nb = np.where(lower, kb - 1, kb + 1)
        be = B["width"]
        u = np.clip((np.where(lower, f, f - 1) + be) / (2 * be), 0, 1)  # 0..1 from the lower bed to the upper
        t = np.where(lower, 1 - u, u)  # the neighbouring bed's share
        o = off(kb)
        i = np.flatnonzero(t > 0)
        o[i] += t[i] * (off(nb[i], i) - o[i])
        # (with jointed blocks the big beds step less: their planes ran the whole cliff as ruled ledges)
        # (in full on the volumes' walls: karst passages' ledges are these beds)
        bf = 1.0 if not r.get("blocks") else (0.4 if uvol is None else 0.4 + 0.6 * uvol)
        out = out + r["bedding"] * bf * (
            0.3 * B["pres"] * np.clip(1 - edge / B["sharp"], 0, 1) + 0.3 * o)
    if r.get("blocks"):
        # jointed blocks (terrain_blocks): courses and joint families bound blocks 1-10 m that stand proud or sit back
        # (a few missing): the medium scale. Not on volumes' walls (u) nor deep in the rock (jw)
        from . import terrain_blocks
        # ((1 - u)^3: at a cave mouth, half volume and half face, the face's blocks stepped the cave's walls and roof)
        wb = (1.0 if jw is None else jw) * (1.0 if uvol is None else (1.0 - uvol) ** 3)
        kb = np.flatnonzero(np.asarray(wb) * np.ones(len(p)) > 1e-3)
        if len(kb) and fd is not None:
            with _span("field.blocks", leaf=True):
                if blk is None:  # (blk: the offsets at every point, computed by the caller with the maps' ids)
                    zoff = r["bed_offset"](p[kb, :2]) if r.get("bed_offset") else 0.0
                    ob = terrain_blocks.offsets(p[kb], r["blocks"], fd[kb], zoff)
                else:
                    ob = blk[kb]
                out = out + 0.0
                out[kb] += (np.ones(len(p)) * wb)[kb] * ob
    if thin is not None and THIN_STRATA["depth"] > 0:
        kt = np.flatnonzero(np.asarray(thin, float) > 1e-3)
        if len(kt):
            out = out + 0.0
            zoff = r["bed_offset"](p[kt, :2]) if r.get("bed_offset") else 0.0
            # (sqrt: a fin's faces are only partly "thin" by the grid's measure, and the beds should run on across it;
            # not on the volumes' walls)
            wv = 1.0 if uvol is None else (1.0 - np.asarray(uvol, float)[kt]) ** 2
            out[kt] += np.sqrt(np.asarray(thin, float)[kt]) * wv * strata(p[kt], zoff, r["seed"])
    if r.get("joints") and r["joints"]["depth"] > 0:
        # (jw: 1 at the open ground, 0 a few metres in: joints on cave walls deep in the rock made black shards)
        with _span("field.joints", leaf=True):
            out = out + _joints(p, r, fd) * (1.0 if jw is None else jw)
    return out


def _bed_hash(k, seed):
    """0..1 per integer bed index (and seed)."""
    x = np.sin(np.asarray(k, float) * 12.9898 + seed * 78.233) * 43758.5453
    return x - np.floor(x)


def strata(p, zoff, seed, tone=False):
    """Thin rock's strata (+ carves): beds 1-3 m thick (THIN_STRATA spacing x (1 +- 2 jitter)) in the bed coordinate
    z + zoff, each with its own hardness: soft beds sit back up to `depth`, hard ones stand flush, how far changing
    along the strike (~12 m, the bed index a noise coordinate) so no bed is a ruled line. Beds hand over across +-ramp
    (>= 2 voxels in all: finer meshed as sawtooth). Durdle Door's fin reads by these, not by its facets.
    tone=True: each point's bed softness instead (0..1, eased across the planes the same way: the colour's banding)."""
    S, J, ramp, depth = (THIN_STRATA[k] for k in ("spacing", "jitter", "ramp", "depth"))
    zb = p[:, 2] + zoff
    i0 = np.floor(zb / S).astype(np.int64)
    bnd = lambda i: (i + J * (2 * _bed_hash(i, seed + 31) - 1)) * S  # (bed i spans bnd(i) .. bnd(i + 1))
    k = np.where(zb < bnd(i0), i0 - 1, np.where(zb >= bnd(i0 + 1), i0 + 1, i0))
    xy = p[:, :2]

    def rec(i, q):  # how far bed i sits back at points q: soft beds the most, wandering along the strike
        # (interbedded: about half the beds soft, 0.55-1, the rest hard and flush, as limestone and shale)
        hsh = _bed_hash(i, seed + 37)
        soft = np.where(hsh < 0.5, 0.55 + 0.9 * hsh, 0.0)
        if tone:
            return soft
        along = noise.fbm(np.c_[q, i * 13.7], 12.0, 2, seed=seed + 41)
        return depth * soft * np.clip(0.2 + 1.4 * along, 0, 1)
    v0 = rec(k, xy)
    v = v0.copy()
    # (each plane: half way between the two beds' values on it, eased over +-ramp; beds are >= 2 ramps thick)
    for side, d in ((-1, zb - bnd(k)), (1, bnd(k + 1) - zb)):
        t = smoothstep(ramp, -ramp, d)
        j = np.flatnonzero(t > 0)
        if len(j):
            v[j] += t[j] * (rec(k[j] + side, xy[j]) - v0[j])
    return v


def _joints(p, r, fd=None):
    """Joint sets: a few families of long, straight, vertical fracture planes (2-3 directions), irregularly spaced
    (each candidate plane on a fine spacing is present or not, jittered: many small blocks and a few big ones), strong
    in some bands of the face and absent in others. Each joint is a V groove between flat faces (a smooth profile
    pillowed every block: from 150 m the face read as hammered metal). ~2 voxels wide: geometry carries the medium
    structure, the maps the fine grain.
    fd: the face's horizontal normal per point (plan; its length the slope). A family whose planes run nearly along the face shows no
    groove there (a cliff breaks off along such a joint: it IS the face); crossing the face it cuts steep traces.
    Every family everywhere crossed as a lattice of long diagonal grooves: from 150 m a crosshatch of diamonds."""
    J = r["joints"]
    ed = J["edge"]
    out = np.zeros(len(p))
    h = lambda k, m, c: noise._hash(k, k * 0 + m, k * 0 + c, r["seed"] + 60)
    for m, d in enumerate(J["dirs"]):
        sp = J["spacing"][m]
        q = (p[:, :2] @ np.asarray(d)) / sp
        k0 = np.floor(q).astype(np.int64)
        best = np.zeros(len(p))
        for dk in (-1, 0, 1):
            k = k0 + dk
            pos = k + 0.8 * (h(k, m, 1) - 0.5)
            amp = (h(k, m, 2) < J["prob"][m]) * (0.6 + 0.4 * h(k, m, 3))
            t = np.clip(1 - np.abs(q - pos) * sp / ed, 0, 1)
            # (crisp shoulders, a rounded floor: a V-bottom crease on cave walls shaded as black shards)
            best = np.maximum(best, amp * t * (2 - t))
        if fd is not None:  # (|cos| of the joint plane's normal with the face's: 1 = the plane lies along the face;
            # the slope in the denominator keeps it continuous where the ground flattens and the direction is lost)
            cs = np.abs(fd @ np.asarray(d)) / np.sqrt((fd * fd).sum(1) + 0.04)
            best = best * smoothstep(0.8, 0.45, cs)
        # (the bands' noise only where there's a groove to scale: it was a sixth of every bake's time)
        kb = np.flatnonzero(best > 0)
        if len(kb):
            band = smoothstep(0.35, 0.6, noise.fbm(p[kb] * np.array([1.0, 1.0, 0.5]), J["band"], 2,
                                                   seed=r["seed"] + 70 + m))
            out[kb] = out[kb] + J["depth"] * best[kb] * band
    return out


# a fixed rotation for the facet lattice, so its creases don't line up with the world's axes
_ROT = np.linalg.qr(np.array([[0.62, -0.51, 0.33], [0.27, 0.71, 0.58], [-0.49, -0.12, 0.74]]))[0]


# a second rotation, for the lattice that warps the facet lattice (see _pl_facets)
_ROT_W = np.linalg.qr(np.array([[0.3, 0.8, -0.2], [-0.7, 0.1, 0.6], [0.5, -0.4, 0.7]]))[0]


def _hash3(ix, iy, iz, seed):
    """Three pseudo-random values -1..1 per lattice point from one 64-bit hash (16 bits each)."""
    h = ((ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791) ^ (seed * 2654435761)).astype(np.uint64)
    for m in (np.uint64(0xBF58476D1CE4E5B9), np.uint64(0x94D049BB133111EB)):  # (splitmix64's finaliser)
        h ^= h >> np.uint64(31)
        h *= m
    h ^= h >> np.uint64(29)
    return np.stack([((h >> np.uint64(16 * c)) & np.uint64(0xFFFF)).astype(np.float64) / 32767.5 - 1.0
                     for c in range(3)], 1)


def _pl_walk(q, seed, vec=False):
    """Random values (-1..1) at the corners of the unit cubic lattice, interpolated linearly over each cube's six
    tetrahedra (the Freudenthal split: consistent across faces). (n,), or (n, 3) with vec."""
    if fieldjit.ON:
        r = fieldjit.pl_walk(np.ascontiguousarray(q, dtype=np.float64), int(seed), bool(vec))
        return r if vec else r[:, 0]
    b = np.floor(q).astype(np.int64)
    f = q - b
    order = np.argsort(-f, axis=1)  # the tetrahedron: walk the axes from the largest fraction down
    fs = np.take_along_axis(f, order, 1)
    w = np.stack([1 - fs[:, 0], fs[:, 0] - fs[:, 1], fs[:, 1] - fs[:, 2], fs[:, 2]], 1)
    val = (lambda v: _hash3(v[:, 0], v[:, 1], v[:, 2], seed)) if vec else \
        (lambda v: 2 * noise._hash(v[:, 0], v[:, 1], v[:, 2], seed) - 1)
    v = b.copy()
    out = (w[:, :1] if vec else w[:, 0]) * val(v)
    rows = np.arange(len(q))
    for k in range(3):
        v[rows, order[:, k]] += 1
        out = out + (w[:, k + 1:k + 2] if vec else w[:, k + 1]) * val(v)
    return out


def _pl_facets(p, size, seed, warp=0.45):
    """A continuous, piecewise-planar field (-1..1): random heights at the corners of a rotated cubic lattice,
    interpolated linearly over each cube's six tetrahedra. Offsetting a surface by it breaks the surface into planar
    facets with crisp creases.
    The lattice is warped by a second piecewise-linear field on another rotated lattice 1.7x coarser (a composition of
    piecewise-linear maps is still piecewise linear: facets stay planar, creases stay C0). Unwarped, every crease lay
    on the lattice's planes and diagonals: a face showed a few fixed crease directions at a fixed spacing, a quilt of
    rhombs and rectangles (the user's "squares in the rocks")."""
    q = (p @ _ROT.T) / size
    if warp:
        q = q + warp * _pl_walk((p @ _ROT_W.T) / (1.7 * size), seed + 1001, vec=True)
    return _pl_walk(q, seed)


def facet(p, size, seed, fd=None, u=None):
    """Planar facets about `size` across (-1..1): on irregular triangles laid on the face where the ground's gradient
    fd says which way it faces (terrain_facets), on the warped lattice (`_pl_facets`) where a volume shapes the rock
    (share u) or no gradient is given."""
    if fd is None:
        return _pl_facets(p, size, seed)
    from . import terrain_facets
    with _span("field.facets", leaf=True):
        return _facet(p, size, seed, fd, u, terrain_facets)


def _facet(p, size, seed, fd, u, terrain_facets):
    u = np.zeros(len(p)) if u is None else u
    out = np.zeros(len(p))
    a, b = np.flatnonzero(u < 0.999), np.flatnonzero(u > 1e-3)
    if len(a):
        out[a] += (1 - u[a]) * terrain_facets.facets(p[a], size, seed, fd[a])
    if len(b):
        out[b] += u[b] * _pl_facets(p[b], size, seed)
    return out


def bed_level(p, r):
    """Which bed a point is in, as a real number (bed k spans k..k+1): the heightfield rock's own beds
    (terrain_rock.bed_step / bed_offset, so sills on the heightfield's faces and the solid rock's beds line up) when
    it has them, else level beds `bed` thick."""
    off = r["bed_offset"](p[:, :2]) if r.get("bed_offset") else 0.0
    return (p[:, 2] + off) / r["bed"]


def _bed_noise(xy, k, scale, seed, octaves=2):
    """0..1 per point, smooth along the strike (plan position, features ~`scale` m), independent per bed k (the bed
    index is the lattice's third coordinate, sampled on its nodes). Two octaves on rotated lattices."""
    k = np.asarray(k, float) * np.ones(len(xy))
    out = np.zeros(len(xy))
    for o, (a, w) in enumerate(((0.61, 0.65), (2.13, 0.35))[:octaves]):
        c, s, m = math.cos(a), math.sin(a), (2 ** o) / scale
        q = np.c_[(xy[:, 0] * c - xy[:, 1] * s) * m, (xy[:, 0] * s + xy[:, 1] * c) * m, k]
        out += w * noise._value_noise(q, seed + 101 * o)
    out = out / (0.65 if octaves == 1 else 1.0)
    return np.clip(0.5 + (out - 0.5) * (1.6 if octaves > 1 else 1.0), 0, 1)


def bed_planes(p, r, g=None):
    """The beds at points: bed level z (bed k spans k..k+1), kb, f, lower (nearer the plane under than over), and for
    the nearest bedding plane: `pres` 0..1 (how much the plane shows: it comes and goes along the strike in patches of
    ~20 m and breaks in gullies, g), `sharp` (its crisp half-width in bed units, varying along the strike: 1-2.5x
    `bed_edge`) and `width` (the step's ramp: sharp where present, metres wide where absent, so the beds merge).
    One offset, one sharpness and one tone per bed, uniform along the whole wall, read as a ruler line: a seam."""
    z = bed_level(p, r)
    kb = np.floor(z).astype(np.int64)
    f = z - kb
    lower = f < 0.5
    m = np.where(lower, kb, kb + 1)  # the nearest plane: between beds m - 1 and m
    be = r.get("bed_edge", 0.08)
    wide = min(0.42, 6.0 / r["bed"])
    pres, sharp = np.ones(len(z)), np.full(len(z), min(be, 0.45))
    # (only points near a plane need them: the step, the notch and the tone's ease reach at most `reach` from it)
    reach = max(wide, min(0.45, 4.2 / r["bed"]), 2.5 * be)
    k = np.flatnonzero(np.minimum(f, 1 - f) < reach)
    if len(k):
        xy = p[k, :2]
        pres[k] = smoothstep(0.3, 0.62, _bed_noise(xy, m[k], 22.0, r["seed"] + 23))
        if g is not None:
            pres[k] *= 1 - 0.8 * np.clip(g[k], 0, 1)
        sharp[k] = np.minimum(0.45, be * (1 + 1.5 * _bed_noise(xy, m[k], 15.0, r["seed"] + 24, octaves=1)))
    width = sharp + (1 - pres) * np.maximum(0.0, wide - sharp)
    return {"z": z, "kb": kb, "f": f, "lower": lower, "m": m, "pres": pres, "sharp": sharp, "width": width}


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
    bed, base = float(rc.get("bed", 3.0)), None
    if hasattr(terrain_rock, "bed_step") and hasattr(terrain_rock, "bed_offset") and "bed" not in rc:
        bed = float(terrain_rock.bed_step(T))
        base = lambda xy, T=T: terrain_rock.bed_offset(T, xy)
    # the beds wander in height along the strike, ~0.5 m over ~25 m and ~0.15 m over ~7 m (terrain_rock's offset alone
    # changes over hundreds of metres: every bed was a level ruler line across the wall)
    wa = min(1.0, 0.12 * bed)
    wander = lambda xy: wa * 3 * (noise.fbm(np.c_[xy, np.full(len(xy), 17.0)], 24.0, 2, seed=4242 + 25) - 0.5) + \
        0.3 * wa * 3 * (noise.fbm(np.c_[xy, np.full(len(xy), 5.0)], 7.0, 1, seed=4242 + 26) - 0.5)
    off = _gridded(lambda xy: wander(xy) + (base(xy) if base else 0.0), T)
    # bed steps ramp over 2 voxels either side of their plane (0.8 voxel meshed as a sawtooth that cast jagged
    # shadows); the crisp notch at the bedding plane is in the maps (terrain_bake.micro_relief)
    vox = float(cfg.get("voxel", DEFAULTS["voxel"]))
    out = {"size": size, "facets": fac, "bedding": bd, "bed": bed, "bed_offset": off, "seed": 4242,
           "reach": 1.4 * fac + 0.7 * bd + 1.0, "bed_edge": max(0.05, 2.0 * vox / bed)}
    bk = float(rc.get("blocks", 1.0)) * mult
    if bk > 0:  # jointed blocks (terrain_blocks); the big facets calmer on them: block faces are flat-ish
        from . import terrain_blocks
        out["blocks"] = terrain_blocks.config(size, vox, bk)
        b = out["blocks"]
        out["reach"] += b["relief"]
        # (the cliff overlay's push/shell keep main's sizes: the blocks mostly carve, within the old push's margin.
        # Thickening the shell by the blocks' relief re-cut the shells round pebble's karst passage and notch: a face
        # in a tile border plane, a non-manifold sliver, a 4-triangle piece floating 2 m over the heightmap)
    jt = float(rc.get("joints", 1.0)) * mult * (bk <= 0)
    if bd > 0 and jt > 0:  # joint sets: three families of vertical planes, candidate spacing ~a fifth of a facet
        sp = float(np.clip(0.2 * size, 1.2, 2.5))
        dirs = [math.radians(a) for a in (37.0, 107.0, 162.0)]
        out["joints"] = {"dirs": [[math.cos(a), math.sin(a)] for a in dirs], "spacing": [sp, 1.4 * sp, 2.0 * sp],
                         "prob": [0.4, 0.3, 0.2], "band": max(12.0, 3.0 * size), "edge": max(0.6, 1.5 * vox),
                         "depth": 0.22 * jt * bd}  # (0.3 m folded the 800-triangle LOD 2: 0.6% shards)
        out["reach"] += 0.35 * jt * bd
    return out


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
        if fieldjit.ON:
            return fieldjit.grid_at(coef, _f64(xy[:, 1]), _f64(xy[:, 0]), ys[0], xs[0], spacing)
        return ndimage.map_coordinates(coef, [(xy[:, 0] - xs[0]) / spacing, (xy[:, 1] - ys[0]) / spacing], order=3,
                                       prefilter=False, mode="nearest")
    from .terrain_incremental import Frame
    f.grid, f.frame = coef, Frame("gridded", coef.shape, "xy", xs[0], ys[0], spacing)  # (incremental export: per tile)
    return f


def _structure_grain(T, H, c):
    """0..1 per terrain cell: how cut up the rock is. Concave ground at the faces' own structure scale (gullies,
    couloirs), terrain_rock's gullies, and the top quarter of each face (the lip breaks up) score high; convex
    buttresses and open faces low. Smooth (a few cells): facet sizes change gradually."""
    rk = getattr(T, "rock", None) if isinstance(getattr(T, "rock", None), dict) else {}
    fh = float(rk.get("face_height", 20.0) or 20.0)
    sig = max(1.0, 0.25 * fh / c)
    Hs = ndimage.gaussian_filter(H, sig)
    lap = ndimage.laplace(Hs) / (c * c)
    gy, gx = np.gradient(H, c)
    steep = np.hypot(gx, gy) > 0.8
    ref = np.percentile(np.abs(lap[steep]), 85) if steep.sum() > 50 else np.abs(lap).max() + 1e-9
    conc = np.clip(lap / max(ref, 1e-9), 0, 1)
    w = max(3, int(round(fh / c)) | 1)
    lo, hi = ndimage.minimum_filter(Hs, w), ndimage.maximum_filter(Hs, w)
    top = smoothstep(0.7, 0.95, (Hs - lo) / np.maximum(hi - lo, 1e-6)) * steep
    g = np.maximum(conc, 0.8 * top)
    gul = rk.get("gullies")
    if gul is not None and np.shape(gul) == H.shape:
        g = np.maximum(g, np.clip(ndimage.gaussian_filter(np.asarray(gul, float), 2.0) * 3, 0, 1))
    return ndimage.gaussian_filter(g, 2.0)


def dig_bunker(T, H, m, depth):
    """A sand trap dug into the ground grid where its cover mask m (0..1) is: `depth` m down with a steep cut edge
    (most of the drop within ~1 m of the edge), the turf lip round it raised a little (0.15 x depth) as mown up to the
    edge; a flat-ish sand floor following the ground's own lie."""
    c = float(T.cell)
    m = ndimage.gaussian_filter(np.clip(np.asarray(m, float), 0, 1), 0.6 / c)
    inside = smoothstep(0.25, 0.65, m)
    ring = smoothstep(0.02, 0.2, ndimage.maximum_filter(m, size=3)) * (1 - inside)
    return H - depth * inside + 0.15 * depth * ring


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


THIN_LEVELS = 48  # at most this many height levels per thin piece (_local_thickness)


def _local_thickness(H, c, r_open, thin):
    """Where the ground is thin (`thin` > 0: fins, stacks, narrow headlands), the rock's local half-thickness per
    height level: at each level z, the radius of the largest disc inside {H > z} that covers the cell (the
    Hildebrand-Ruegsegger local thickness, in whole cells up to r_open), carried 2 cells out into the air and smoothed.
    Returns (labels, comps): labels (the grid, 0 = not thin) and per piece (j0, i0, z0, dz, hw (nz, ny, nx) m,
    tw (nz, ny, nx): how much the cap applies, 0 where the rock is r_open thick)."""
    m = thin > 0.02
    if not m.any():
        return None
    lab, n = ndimage.label(ndimage.binary_dilation(m, iterations=2))
    pad = 2 * r_open + 3
    big = r_open * c
    comps = []
    for li, sl in enumerate(ndimage.find_objects(lab), 1):
        j0, j1 = max(sl[0].start - pad, 0), min(sl[0].stop + pad, H.shape[0])
        i0, i1 = max(sl[1].start - pad, 0), min(sl[1].stop + pad, H.shape[1])
        Hs, own = H[j0:j1, i0:i1], lab[j0:j1, i0:i1] == li
        th = thin[j0:j1, i0:i1]
        zlo = float(Hs[own].min()) - 1.0
        zhi = float(Hs[own].max()) + 1.0
        nz = int(min(THIN_LEVELS, max(2, math.ceil((zhi - zlo) / c) + 1)))
        dz = (zhi - zlo) / (nz - 1)
        hw = np.zeros((nz,) + Hs.shape)
        for iz in range(nz):
            M = Hs > zlo + iz * dz
            if not M.any():
                continue
            edt = ndimage.distance_transform_edt(M)
            h = np.where(M, 0.5, 0.0)
            for R in range(1, r_open + 1):
                core = edt >= R
                if not core.any():
                    break
                # (the cells within R of a core cell: an EDT, not a disc dilation, which cost R^2 per cell)
                h[(ndimage.distance_transform_edt(~core) <= R) & M] = R
            # (into the air a little: the surface lies between cells, and carving reaches out to it)
            h = ndimage.grey_dilation(h, size=(5, 5))
            hw[iz] = ndimage.gaussian_filter(h, 0.8) * c
        tw = th[None] * (1.0 - smoothstep(0.6 * big, big, hw))
        comps.append((j0, i0, zlo, dz, hw, tw))
    return lab, comps


class Field:
    def __init__(self, T, vols: list[Tube], rock=None, dolines=None, cuts=None, bunkers=None):
        self.H = np.ascontiguousarray(T.H, float)
        self.x0, self.y0, self.c = float(T.xs[0]), float(T.ys[0]), float(T.cell)
        self.vols = vols
        self.rock = rock
        self.floor_guard = None
        self.grain = None  # where the rock is cut up (gullies, concave, near the top of a face): finer facets
        self.micro = None  # fine rock relief evaluated only when baking maps (terrain_bake.micro_relief)
        self.fall = None  # where fallen blocks lie (a grid, 0..1)
        for d in dolines or ():  # 2.5D ground edits (karst dolines: grassy funnels into a throat)
            self.H = dig_doline(T, self.H, d)
        for c in cuts or ():  # (a sea arch's neck: the bays either side of it)
            self.H = cut_neck(T, self.H, c)
        from . import terrain_ground
        gcfg = terrain_ground.config(T)
        if gcfg is None:  # (no ground character: sand traps dug into the grid, as 2-cell blurs)
            for m, depth, *_ in bunkers or ():
                self.H = dig_bunker(T, self.H, m, depth)
        if rock is not None:
            # where the rock character goes: steep ground (45-62 deg), as a smooth mask on the grid (~2 cells). From
            # each point's own column slope it switched on within 0.2 m at a cliff's lip (the B-spline's slope turns
            # fast there): the relief times that switch was a sub-voxel step in the field, meshed as black shards
            gy, gx = np.gradient(self.H, self.c)
            cs = 1.0 / np.sqrt(1.0 + gx * gx + gy * gy)
            # (dilated a cell first: a sheer cliff is a cell or two wide in plan and smoothing alone halved it)
            self.steep = ndimage.gaussian_filter(ndimage.maximum_filter(smoothstep(0.71, 0.47, cs), 3), 1.0)
            # thin fins and stack tops (narrower than twice the relief's reach) take little relief: carving a few
            # metres into a 3 m wide fin cut its top off (a block floating 14 m over the sea at pebble's point)
            r_open = max(2, int(math.ceil(2.0 * rock["reach"] / self.c)))
            yy, xx = np.mgrid[-r_open:r_open + 1, -r_open:r_open + 1]
            disc = (xx * xx + yy * yy) <= r_open * r_open
            thin = smoothstep(0.5, 2.5, self.H - ndimage.grey_opening(self.H, footprint=disc))
            self.thin = ndimage.gaussian_filter(thin, 1.0)
            # The relief's own weight keeps thin rock (an arch's fin, slim stacks, narrow headlands): bounded there by
            # the rock's local half-thickness at the point's height (`thin_cap`), so it can't carve through or cut a
            # top off. Field.steep (the cliff region, fallen blocks, the heightfield facets' removal) stays as before.
            self.relief_w = self.steep if THIN_RELIEF <= 0 else self.steep.copy()
            self.steep = self.steep * (1 - 0.9 * self.thin)
            if THIN_RELIEF <= 0:
                self.relief_w = self.steep
            else:
                self.thin_parts = _local_thickness(self.H, self.c, r_open, self.thin)
            self.grain = _structure_grain(T, self.H, self.c)
            # the heightfield's own facets (terrain_rock: tipped planes on jittered ~5-17 m cells) taken back out where
            # the solid rock gets its own: two facet systems on one face made a moire of lozenges
            fdel = (getattr(T, "rock", None) or {}).get("facet_delta") if isinstance(getattr(T, "rock", None), dict) \
                else None
            if fdel is not None and np.shape(fdel) == self.H.shape:
                self.H = self.H - np.clip(self.steep, 0, 1) * fdel
            # the faces' horizontal normal (downhill), smoothed over ~3 cells: which joint families cross a face
            sy, sx = np.gradient(ndimage.gaussian_filter(self.H, 3.0), self.c)
            self._fdx, self._fdy = -sx, -sy
            if rock.get("blocks") and rock["blocks"].get("fallen", 0) > 0:
                # where blocks that fell off the faces lie (terrain_blocks.fall_zone): at their feet, on gentler ground
                from . import terrain_blocks
                self.fall = terrain_blocks.fall_zone(self.H, self.c, self.steep) * float(rock["blocks"]["fallen"])
        # ground edits finer than the grid, per point in `column` (terrain_ground.Edits): the turf's step back from
        # every cliff lip, bunkers cut crisp (as a 2-cell blur on the grid they read as soft dishes)
        self.edits = terrain_ground.Edits(T, self.H, bunkers or (), gcfg) if gcfg is not None else None

    def column(self, x, y):
        """Ground height h and the slope correction 1 / sqrt(1 + |grad h|^2) at columns (with the ground edits:
        turf lips, bunkers)."""
        h, s = self._column(x, y)
        if getattr(self, "edits", None) is not None:
            return self.edits.column(np.asarray(x, float), np.asarray(y, float), h, s, self._column,
                                     getattr(self, "edit_riser", None), getattr(self, "edit_wmin", 0.0))
        return h, s

    def _column(self, x, y):
        if fieldjit.ON:
            x, y = _f64(x), _f64(y)
            return fieldjit.column(self.H, x, y, self.x0, self.y0, self.c)
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

    def grain_at(self, x, y):
        if fieldjit.ON:
            return np.clip(fieldjit.grid_at(self.grain, _f64(x), _f64(y), self.x0, self.y0, self.c), 0, 1)
        r = (np.asarray(y, float) - self.y0) / self.c
        q = (np.asarray(x, float) - self.x0) / self.c
        return np.clip(ndimage.map_coordinates(self.grain, [r, q], order=3, prefilter=False, mode="nearest"), 0, 1)

    def face_dir(self, x, y):
        """The face's horizontal normal at columns, as the smoothed ground's downhill gradient (its length the slope,
        tan): a smooth grid (cubic B-spline), so relief built on it stays continuous."""
        if fieldjit.ON:
            x, y = _f64(x), _f64(y)
            return np.stack([fieldjit.grid_at(a, x, y, self.x0, self.y0, self.c) for a in (self._fdx, self._fdy)], 1)
        r = (np.asarray(y, float) - self.y0) / self.c
        q = (np.asarray(x, float) - self.x0) / self.c
        v = np.stack([ndimage.map_coordinates(a, [r, q], order=3, prefilter=False, mode="nearest")
                      for a in (self._fdx, self._fdy)], 1)
        return v

    def steep_at(self, x, y):
        if fieldjit.ON:
            return fieldjit.grid_at(self.steep, _f64(x), _f64(y), self.x0, self.y0, self.c)
        r = (np.asarray(y, float) - self.y0) / self.c
        q = (np.asarray(x, float) - self.x0) / self.c
        return ndimage.map_coordinates(self.steep, [r, q], order=3, prefilter=False, mode="nearest")

    def relief_at(self, x, y):
        """The rock relief's weight at columns: Field.steep without thin rock's cut (`thin_cap` bounds it there)."""
        rw = getattr(self, "relief_w", None)
        if rw is None or rw is self.steep:
            return self.steep_at(x, y)
        if fieldjit.ON:
            return fieldjit.grid_at(rw, _f64(x), _f64(y), self.x0, self.y0, self.c)
        r = (np.asarray(y, float) - self.y0) / self.c
        q = (np.asarray(x, float) - self.x0) / self.c
        return ndimage.map_coordinates(rw, [r, q], order=3, prefilter=False, mode="nearest")

    def thin_at(self, p):
        """Thin rock at points: (hw, t): the rock's local half-thickness at the point's height (m; inf off thin rock)
        and how much thin rock's rules apply there (0..1: 0 where the rock is thick)."""
        hw_, t_ = np.full(len(p), np.inf), np.zeros(len(p))
        parts = getattr(self, "thin_parts", None)
        if not parts:
            return hw_, t_
        lab, comps = parts
        iy = np.clip(np.rint((p[:, 1] - self.y0) / self.c).astype(np.int64), 0, lab.shape[0] - 1)
        ix = np.clip(np.rint((p[:, 0] - self.x0) / self.c).astype(np.int64), 0, lab.shape[1] - 1)
        L = lab[iy, ix]
        for li in np.unique(L[L > 0]):
            k = np.flatnonzero(L == li)
            j0, i0, z0, dz, hw, tw = comps[li - 1]
            q = [(p[k, 2] - z0) / dz, (p[k, 1] - self.y0) / self.c - j0, (p[k, 0] - self.x0) / self.c - i0]
            hw_[k] = ndimage.map_coordinates(hw, q, order=1, mode="nearest")
            t_[k] = ndimage.map_coordinates(tw, q, order=1, mode="nearest")
        return hw_, t_

    @staticmethod
    def thin_cap(R, hw, t):
        """Rock relief R (+ carves) on thin rock, bounded by its local half-thickness hw: a soft clamp
        THIN_RELIEF x hw x tanh(R / that), blended in by t (0 where the rock is thick)."""
        k = np.flatnonzero(t > 0)
        if not len(k):
            return R
        out = np.asarray(R, float).copy()
        cap = np.maximum(THIN_RELIEF * hw[k], 1e-6)
        out[k] = out[k] + t[k] * (cap * np.tanh(out[k] / cap) - out[k])
        return out

    def fall_at(self, x, y):
        """0..1: the fallen blocks' density at columns (0 where there are none)."""
        if self.fall is None:
            return np.zeros(np.shape(x))
        r = (np.asarray(y, float) - self.y0) / self.c
        q = (np.asarray(x, float) - self.x0) / self.c
        return np.clip(ndimage.map_coordinates(self.fall, [r, q], order=1, mode="nearest"), 0, 1)

    def ground(self, p):
        h, s = self.column(p[:, 0], p[:, 1])
        return (p[:, 2] - h) * s

    def volumes(self, p, F, near=None, dvoid=None):
        """Each volume combined into F in order; `near` (if given) gets how close each point is to a volume, 0..1
        (rock character applies there); `dvoid` (if given) the distance to the nearest void (a subtract volume)."""
        for vol in self.vols:
            k = np.flatnonzero(np.all((p >= vol.lo) & (p <= vol.hi), axis=1))
            if not len(k):
                continue
            d, above, size = vol.sd(p[k], detail=True)
            if getattr(vol, "clip", None) is not None:  # (what it replaces: the ground within a cylinder over a plinth)
                rc, zc = vol.clip
                F[k] = smax(F[k], np.minimum(rc - np.hypot(p[k, 0] - vol.xy[0], p[k, 1] - vol.xy[1]), p[k, 2] - zc),
                            0.4)
            F[k] = smax(F[k], -d, vol.blend) if vol.op == "subtract" else smin(F[k], d, vol.blend)
            if dvoid is not None and vol.op == "subtract" and getattr(vol, "kind", None) != "arch":
                # (an arch goes through thin rock by design: its fin keeps thin rock's rules)
                dvoid[k] = np.minimum(dvoid[k], d)
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
        profiling.count("field.solid pts", len(p))
        with _span("field.solid", leaf=True):
            return self._solid(p, F, s)

    def _solid(self, p, F, s):
        near = np.zeros(len(p))
        self.floor_guard = np.ones(len(p))
        depth = -np.asarray(F, float).copy()  # (how far under the open ground: joints are a surface thing)
        dvoid = np.full(len(p), np.inf) if getattr(self, "thin_parts", None) else None
        F = self.volumes(p, F, near, dvoid)
        guard, self.floor_guard = self.floor_guard, None
        if self.fall is not None:  # fallen blocks at the faces' feet, unioned with a small fillet
            fz = self.fall_at(p[:, 0], p[:, 1])
            kf = np.flatnonzero((fz > 0) & (F < 3.0) & (F > -2.0))
            if len(kf):
                from . import terrain_blocks
                with _span("field.fallen", leaf=True):
                    sd = terrain_blocks.fallen_sd(p[kf], lambda xy: self.column(xy[:, 0], xy[:, 1])[0],
                                                  lambda xy: self.fall_at(xy[:, 0], xy[:, 1]), self.rock["blocks"])
                    F[kf] = smin(F[kf], sd, 0.3)  # (a fillet ~a voxel: a razor contact crease made slivers)
        if self.rock is not None:
            # steep ground (45-62 deg) and anything a volume shaped: faceted, jointed, bedded rock (not cave floors)
            rw = self.relief_at(p[:, 0], p[:, 1])
            nv = None
            if dvoid is not None:
                # near a void (a cave or notch; arches go through thin rock by design) the rule stays the old one: the
                # rock between a face and the void behind it is thin whatever the grid says (full relief over a sea
                # cave's mouth cut a piece of its roof free 4 m over the heightmap; capping it by the slab's thickness
                # instead folded cave walls into shards)
                nv = smoothstep(THIN_VOID, 0.5 * THIN_VOID, dvoid)
                j = np.flatnonzero(nv > 0)
                if len(j):
                    rw = rw.copy()
                    rw[j] += nv[j] * (self.steep_at(p[j, 0], p[j, 1]) - rw[j])
            w = np.maximum(rw * guard, near)
            k = np.flatnonzero((w > 0.01) & (np.abs(F) < self.rock["reach"]))
            if len(k):
                g = self.grain_at(p[k, 0], p[k, 1]) if self.grain is not None else None
                fd = self.face_dir(p[k, 0], p[k, 1])
                a_ = rw[k] * guard[k]
                u = near[k] / np.maximum(a_ + near[k], 1e-9)  # (the volumes' share of the relief)
                profiling.count("field.rock pts", len(k))
                blk = I = None
                if self.rock.get("blocks") and self.micro is not None:
                    # (the maps' fine relief needs the rock structure's ids at the same points: computed together)
                    from . import terrain_blocks
                    with _span("field.blocks", leaf=True):
                        zoff = self.rock["bed_offset"](p[k, :2]) if self.rock.get("bed_offset") else 0.0
                        blk, I = terrain_blocks.structure(p[k], self.rock["blocks"], fd, zoff, want_ids=True,
                                                          sharp=getattr(self.micro, "sharp", None))
                        if "sharp" in I:  # (the maps' share of the blocks weighted as rock_relief weights them)
                            I["sharp"] = I["sharp"] * smoothstep(4.0, 1.5, depth[k]) * (1.0 - u) ** 3
                hw, tw = self.thin_at(p[k]) if THIN_RELIEF > 0 else (None, None)
                if nv is not None and tw is not None:  # (none of thin rock's rules near a void: see above)
                    tw = tw * (1.0 - nv[k])
                ts = tw
                with _span("field.rock_relief", leaf=True):
                    R = w[k] * rock_relief(p[k], self.rock, g, smoothstep(4.0, 1.5, depth[k]), fd, u, blk, thin=ts)
                    F[k] = F[k] + (R if tw is None else self.thin_cap(R, hw, tw))
                if self.micro is not None:  # (bake-only fine rock: below the meshing voxel, for the maps)
                    with _span("field.micro", leaf=True):
                        F[k] = F[k] + w[k] * self.micro(p[k], fd, u, g, I)
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
    with _span("project"):
        return _project(field, P, v, fixed, iterations)


def _project(field, P, v, fixed=None, iterations=4):
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
        from . import terrain_ground
        for name, m in T.cover.items():
            c = design._spec_cover(T, name)
            typ = c.get("type", name)
            layer = LAYER_OF.get(typ, "grass")
            tree = bool(c.get("trees"))
            self.cover.append((name, layer, 0.6 if tree else 1.0, terrain_ground.KIND_OF.get(typ)))
            order.append(layer)
        self.layers = list(dict.fromkeys(order + ["rock", "earth"] + (["sand", "wet_rock"] if self.sea is not None
                                                                      else [])))
        col = ground_colours(T, cover=True)
        wet = ~np.isnan(T.water)
        col[wet] = np.array(LAYERS["sand"]["color"]) * 0.8
        if getattr(T, "spec", {}).get("ground_character", True) is not False:
            # (a cell's cover colour sampled as is drew every cover edge as the grid's staircase: fairways were cut-out
            # stickers with stepped edges; softened over about a cell, and warped a little where sampled)
            col = np.stack([ndimage.gaussian_filter(col[..., i], 0.9) for i in range(3)], -1)
        self.display = col
        if getattr(T, "spec", {}).get("ground_character", True) is not False:
            # the bare ground's colour (slope, height, roads, water) as a grid; the covers are painted over it per point
            # with the same crisp weights as the layers (from the cell grid, a fairway's or a bunker's edge was the
            # grid's 2-cell blur however crisp its weight: soft stickers)
            bare = ground_colours(T, cover=False)
            bare[wet] = np.array(LAYERS["sand"]["color"]) * 0.8
            self.display_bare = np.stack([ndimage.gaussian_filter(bare[..., i], 0.9) for i in range(3)], -1)
            self.cover_col = {name: np.asarray(design.cover_colour(T, name), float) for name, *_ in self.cover}
        self.rock_grid = rock_colours(T)
        steep = T._slope() > 45
        self.rock_ref = np.median(self.rock_grid[steep] if steep.any() else self.rock_grid.reshape(-1, 3), 0)
        self.routes = T.masks.get("routes")
        # the ground's character between the rock faces (terrain_ground): turf edges, shore, variation, cover kinds
        ed = getattr(field, "edits", None) or getattr(getattr(field, "base", None), "edits", None)
        self.ground = terrain_ground.Ground(T, field.H, self.sea, ed) if getattr(T, "spec", {}).get(
            "ground_character", True) is not False else None
        if self.ground is not None:  # (its per-cover grids made now, not lazily per worker)
            for name, layer, k, kind in self.cover:
                if kind == "mown":
                    self.ground.mown_sd(name, T.cover[name])
                    self.ground.stripe_frame(name, T.cover[name])
        for name in T.cover:  # (made now: a lazy cache filled in some processes and not others)
            self._covf(name)

    def layer_ref(self, name):
        """A layer's reference look for the manifest (rock: this terrain's own rock colour)."""
        ref = dict(LAYERS[name])
        if name == "rock":
            ref["color"] = [round(float(x), 3) for x in self.rock_ref]
        elif name == "wet_rock":
            ref["color"] = [round(float(x) * 0.45, 3) for x in self.rock_ref]
        return ref

    def _grid(self, a, xy):
        """A per-cell grid (cover, colours) at points: a cubic B-spline over the cells (approximating, no prefilter:
        smooth and never overshooting). Bilinear it had a crease in its gradient on every cell line, and the per-cell
        variation (tone, strata, slope-dependent beds) showed as a quilt of cell-sized squares on the rock, plainest
        from 100 m and more (5 m cells on the alps)."""
        T = self.T
        if fieldjit.ON:
            return fieldjit.grid_at(np.ascontiguousarray(a, dtype=np.float64), _f64(xy[:, 0]), _f64(xy[:, 1]),
                                    float(T.xs[0]), float(T.ys[0]), float(T.cell))
        return ndimage.map_coordinates(np.asarray(a, float), [(xy[:, 1] - T.ys[0]) / T.cell,
                                                              (xy[:, 0] - T.xs[0]) / T.cell],
                                       order=3, prefilter=False, mode="nearest")

    def _covf(self, name):
        """A cover's mask as a contiguous float64 grid (made once: per call it was most of a weights call)."""
        cache = self.__dict__.setdefault("_covf_cache", {})
        if name not in cache:
            cache[name] = np.ascontiguousarray(self.T.cover[name], dtype=np.float64)
        return cache[name]

    def _cover_d(self, name, kind, xy):
        """A cover's weight (0..1) at points: its mask as a cubic spline over the cells, cut crisp where the ground
        character asks: a bunker at its dug edge, a mown piece along the mower's line (as a 2-cell blur both read as
        soft-edged stickers)."""
        d = np.clip(self._grid(self._covf(name), xy), 0, 1)
        g = self.ground
        if g is None:
            return d
        e = g.edits.bunker_of(name)
        if e is not None:
            return smoothstep(0.06, -0.06, e(xy)) * np.clip(2 * d, 0, 1)
        if kind == "mown":
            return smoothstep(0.3, -0.3, g.mown_sd(name, self.T.cover[name])(xy)) * np.clip(2 * d, 0, 1)
        return d

    def _covers(self, P):
        """(per-layer weights, kinds, mown stripes [(weight, -1..1)], rest) as painted (later layers over earlier);
        kinds: terrain_ground.KIND_OF's mown/rough/scrub, plus "cut": the first cut, a mown band round each mown piece
        taken out of the rough round it."""
        xy = P[:, :2]
        n = len(P)
        W = {k: np.zeros(n) for k in self.layers}
        rest = np.ones(n)
        kinds, mown = {}, []
        bands = []
        for name, layer, k, kind in reversed(self.cover):  # painted in order: later layers over earlier
            d = self._cover_d(name, kind, xy) * k
            W[layer] += d * rest
            if kind is not None and self.ground is not None:
                kinds[kind] = kinds.get(kind, 0.0) + d * rest
                if kind == "mown":
                    mown.append((d * rest, self.ground.stripes(P, name, self.T.cover[name], along=True)))
                    bands.append(self.ground.first_cut(P, name, self.T.cover[name]))
            rest *= 1 - d
        if bands and "rough" in kinds:
            cut = np.minimum(np.max(bands, 0), kinds["rough"])
            kinds["rough"] = kinds["rough"] - cut
            kinds["cut"] = cut
        return W, kinds, mown, rest

    def _route(self, xy, kinds):
        """0..0.8: how worn the routes' ground is at points (None: no routes). Only off mown turf: a way across a fairway
        or a green is walked on grass (painted over everything it read as a pale sandy band across the fairways)."""
        if self.routes is None:
            return None
        r = np.clip(self._grid(self.routes.astype(float), xy), 0, 1) * 0.8
        if self.ground is not None and kinds:
            turf = np.clip(np.asarray(kinds.get("mown", 0.0) + kinds.get("cut", 0.0), float), 0, 1)
            r = r * (1.0 - smoothstep(0.1, 0.6, turf))
        return r

    def _paint(self, xy, wxy, rd=None):
        """The display colour before the ground's character: the bare ground's grid (at the warped points), each
        cover's colour painted over it in order with its weight (crisp-edged covers at the points themselves, the
        rest at the warped ones), the roads over everything (sRGB)."""
        c = np.stack([self._grid(self.display_bare[..., i], wxy) for i in range(3)], 1)
        rest = np.ones(len(xy))
        acc = np.zeros((len(xy), 3))
        g = self.ground
        for name, layer, k, kind in reversed(self.cover):
            crisp = kind == "mown" or g.edits.bunker_of(name) is not None
            d = (self._cover_d(name, kind, xy) if crisp else
                 np.clip(self._grid(self._covf(name), wxy), 0, 1)) * k
            acc += (d * rest)[:, None] * self.cover_col[name]
            rest = rest * (1 - d)
        c = acc + rest[:, None] * c
        if rd is not None:
            arid = self.T.world["kind"] in ("canyon", "dunes", "plateau")
            rd = np.broadcast_to(np.asarray(rd, float), (len(xy),))[:, None]
            c = c * (1 - rd) + (np.array([0.78, 0.66, 0.5]) if arid else np.array([0.55, 0.47, 0.36])) * rd
        return c

    def relief(self, P, Wt, texel):
        """The ground's maps-only relief (terrain_ground.Ground.relief) as a plan gradient (n, 2), weighted by the
        grass layers (not on rock or sand), or None without ground character."""
        if self.ground is None:
            return None
        _, kinds, mown, _ = self._covers(P)
        w = sum(Wt[:, self.layers.index(nm)] for nm in ("grass", "turf", "scrub") if nm in self.layers)
        if not np.isscalar(w):
            kinds = {k: v * w for k, v in kinds.items()}
            mown = [(m * w, st) for m, st in mown]
        return self.ground.relief(self, P, kinds, mown, texel)

    def kinds(self, P):
        """The cover kinds (terrain_ground.KIND_OF: mown, rough, scrub; "cut": the first cut round mown pieces) at
        points, as painted (later layers over earlier)."""
        return self._covers(P)[1]

    def weights(self, P, N):
        with _span("materials.weights"):
            return self._weights(P, N)

    def _weights(self, P, N):
        xy = P[:, :2]
        n = len(P)
        W, kinds, mown, rest = self._covers(P)
        W["earth"] += rest
        r = self._route(xy, kinds)
        if r is not None:
            for key in W:
                W[key] *= 1 - r
            W["earth"] += r
        # rock: steep or overhanging faces (from the field's normal), and anything below the heightfield's ground
        # (a cave's walls and roof, an arch's soffit)
        slope = np.degrees(np.arccos(np.clip(N[:, 2], -1, 1)))
        below = smoothstep(0.3, 1.2, -self.field.ground(P))
        rock = np.maximum(smoothstep(38, 58, slope), below)
        under = None
        if self.ground is not None:  # the turf's ragged edge back from a lip, rock breaking through, the splash zone
            g_rock, under, shore, ledge = self.ground.rock(self, P, N)
            g_rock = np.maximum(g_rock - shore * W.get("sand", 0.0), 0.0)  # (beaches stay sand)
            for key in ("forest_floor",):  # (not under trees)
                if key in W:
                    g_rock = g_rock * (1 - W[key])
            rock = np.maximum(rock, g_rock)
            # (green on the faces' ledges near a top, off the wet band and out of caves)
            rock = rock * (1 - ledge * (1 - below) * smoothstep(self.sea + 2.5, self.sea + 4.0, P[:, 2])
                           if self.sea is not None else 1 - ledge * (1 - below))
        if getattr(self.field, "fall", None) is not None:  # (a fallen block: anything standing clear of the ground)
            rock = np.maximum(rock, smoothstep(0.05, 0.25, self.field.ground(P)) *
                              np.clip(4 * self.field.fall_at(P[:, 0], P[:, 1]), 0, 1))
        tide = np.zeros(n)
        if self.sea is not None:  # under water: sand, unless rock
            wet = smoothstep(0.2, 1.2, self.sea - P[:, 2])
            for key in W:
                W[key] *= 1 - wet
            W["sand"] += wet
            # the splash zone: rock dark and wet from the water up a couple of metres, higher inside caves and notches
            # its upper edge wanders a metre and more (a level line read as paint), wettest right at the water
            sh = 1.6 * (noise.fbm(P * np.array([1.0, 1.0, 0.3]), 4.0, 2, seed=77) - 0.5)
            tide = smoothstep(self.sea + 2.2 + 1.5 * below + sh, self.sea + 0.3, P[:, 2]) ** 1.3
        for key in W:
            W[key] *= 1 - rock
        W["rock"] += rock * (1 - tide)
        if "wet_rock" in W:
            W["wet_rock"] += rock * tide
        Wm = np.stack([W[k] for k in self.layers], 1)
        Wm /= np.maximum(Wm.sum(1, keepdims=True), 1e-9)
        # display colour: the terrain's own preview colours (cover, roads, slope), rock over steep faces and caves
        if self.ground is not None:  # (cover edges wander ~0.6 m: not the grid's straight runs)
            Pf = P * np.array([1.0, 1.0, 0.0])
            wxy = xy + 0.6 * np.c_[noise.fbm(Pf, 4.0, 2, seed=631) - 0.5, noise.fbm(Pf, 4.0, 2, seed=632) - 0.5]
            c = self._paint(xy, wxy, self._route(wxy, kinds))
        else:
            c = np.stack([self._grid(self.display[..., i], xy) for i in range(3)], 1)
        if self.ground is not None:
            if "sand" in W:
                kinds["sand"] = W["sand"]
            c = self.ground.tint(self, P, N, c, kinds, mown)
        if self.sea is not None:
            wet = smoothstep(0.2, 1.2, self.sea - P[:, 2])[:, None]
            c = c * (1 - wet) + np.array(LAYERS["sand"]["color"]) * 0.8 * wet
        # the rock's own colour where the heightfield views paint it (the kind's rock, strata bands, rock cover
        # layers such as black lava or a cliff's grey), not one grey for every terrain
        rc = np.stack([self._grid(self.rock_grid[..., i], xy) for i in range(3)], 1)
        if self.field.rock is not None:  # beds and facets differ in tone (a single grey read as plaster)
            r = self.field.rock
            g = self.field.grain_at(P[:, 0], P[:, 1]) if self.field.grain is not None else None
            B = bed_planes(P, r, g)
            kb, fr = B["kb"], B["f"]
            # each bed's tone changes along the strike too (one tone per bed was a band ruled across the wall)
            calm = 0.35 if r.get("blocks") else 1.0  # (blocks carry the tone where they exist: less blotchy noise)
            if r.get("blocks") and getattr(self.field, "thin", None) is not None:
                # thin fins and stacks (an arch's fin) take little relief (Field.thin: carved, their tops floated off),
                # so their beds show in colour instead: Durdle Door's banding, not a smooth tan wall
                calm = calm + (1.0 - calm) * np.clip(self._grid(self.field.thin, xy), 0, 1) * THIN_TONE
            th = lambda k: 1 + calm * (-0.16 + 0.26 * _bed_noise(xy, k, 40.0, r["seed"] + 30))
            # (each bed's tone eases into the next over ~0.2 m where the plane shows, a step aliased along every
            # bedding plane in the maps; over metres where it doesn't: no line there)
            e = np.minimum(0.45, (0.2 + (1 - B["pres"]) * 4.0) / r["bed"])
            lo_, hi_ = smoothstep(-e, e, fr), smoothstep(-e, e, fr - 1)
            tone = th(kb - 1) * (1 - lo_) + th(kb) * (lo_ - hi_) + th(kb + 1) * hi_
            # (a smooth noise: the facet lattice's tone had straight edges and read as a checker of squares)
            tone = tone * (1 + calm * (-0.08 + 0.12 * (2 * noise.fbm(P, r["size"], 2, seed=r["seed"] + 40) - 1)))
            tone = tone * (1 + calm * (-0.07 + 0.14 * noise.fbm(P, 2.5 * r["size"], 2, seed=r["seed"] + 31)))
            rc = rc * tone[:, None]
            if r.get("blocks"):
                rc = block_colour(P, N, rc, r, self.field.face_dir(P[:, 0], P[:, 1]),
                                  lines=not getattr(self, "lines_in_maps", False))
            bf = self.field
            while bf is not None and not hasattr(bf, "thin_at"):
                bf = getattr(bf, "base", None)
            if THIN_RELIEF > 0 and THIN_STRATA["depth"] > 0 and bf is not None and getattr(bf, "thin_parts", None):
                # thin rock's strata in colour too: soft beds (sitting back) darker and warmer, hard ones paler
                _, tw = bf.thin_at(P)
                kt = np.flatnonzero(tw > 1e-3)
                if len(kt):
                    zoff = r["bed_offset"](P[kt, :2]) if r.get("bed_offset") else 0.0
                    so = strata(P[kt], zoff, r["seed"], tone=True)
                    st = np.sqrt(tw[kt])  # (as the geometry's strata)
                    f = 1 + st * THIN_STRATA["tone"] * (0.3 - so)
                    rc[kt] = rc[kt] * f[:, None] * (1 + st[:, None] * 0.06 * so[:, None] * np.array([1.0, 0.0, -1.0]))
        # crevices, joints and the backs of overhangs darker (how open the field is half a metre out along the
        # normal: a cheap occlusion that needs no ray tracing, the same in every engine)
        d = 0.8
        open_ = np.clip(self.field.value(P + d * N) / d, 0, 1)
        # (lighter with the rock structure: its recesses are already shaded by geometry and the AO map; with this too
        # every slot read as black-outlined)
        lo = 0.66 if (self.field.rock or {}).get("blocks") else 0.55
        rc = rc * (lo + (1 - lo) * open_)[:, None]
        if under is not None:  # (the rock just under the turf's lip: shaded by the overhanging mat)
            from .terrain_ground import LOOK
            rc = rc * (1 - (1 - LOOK["undercut"]) * under)[:, None]
        c = c * (1 - rock[:, None]) + rc * (1 - 0.55 * tide[:, None]) * rock[:, None]  # wet: its own rock, darker
        return Wm.astype(np.float32), c


THIN_STRATA = {"spacing": 1.7, "jitter": 0.2, "ramp": 0.5, "depth": 1.0, "tone": 1.0}  # thin rock's strata
# (`strata`): bed spacing, jitter share, plane ramp, soft beds' set-back (m); tone: soft beds' darkening
THIN_VOID = 8.0  # m: within this of a cave or notch thin rock keeps the old rule (Field.steep's tenth)
THIN_RELIEF = 0.35  # thin rock's relief: at most this share of its local half-thickness (Field.thin_cap); 0 = the old
# rule (thin fins and stacks took a tenth of the relief: smooth, Durdle Door without its beds)
THIN_TONE = 1.0  # how much of the full bed tone thin fins take back (Materials, rock colour)
BLOCK_TONE = {"bed": 0.06, "thin": 0.08, "block": 0.04, "p_fresh": 0.05, "fresh": 0.08, "warm": [0.04, 0.0, -0.06],
              "along": 0.10, "under_ledge": 0.12}
# block_colour's spread: per bed and per block (+-), thin packages darker, the share of freshly spalled blocks and how
# much paler (and warmer, per channel) they are; weathering along the beds (+-) and the darkening under each ledge


def block_colour(P, N, rc, r, fd, lines=True):
    """Rock colour from the block structure (terrain_blocks): each block and course weathered to its own tone, the
    joints and bedding planes as dark lines (eased to the line over ~0.15 m: a step aliases in the maps), dark water
    stains streaking down the faces in patches, pale grey-green lichen on ledge tops. Structure-driven colour instead
    of blotchy noise."""
    from . import terrain_blocks
    B = r["blocks"]
    zoff = r["bed_offset"](P[:, :2]) if r.get("bed_offset") else 0.0
    I = terrain_blocks.ids(P, B, fd, zoff)
    sd = B["seed"] + 500
    hsh = lambda i, j, s_: noise._hash(i, j, np.zeros_like(i), sd + s_)
    # 0 at an edge, 1 from 0.25 m (narrower lines stair-stepped on 16/m texels seen from 5 m)
    ease = lambda e: (lambda x: x * x * (3 - 2 * x))(np.clip(e / 0.25, 0, 1))
    K, j = I["K"], I["j"]
    eb = ease(I["bed_edge"])
    # each bed its own tone (thin packages darker), each block a little different; tones ease to neutral at their edges
    # (equal on both sides: no step to alias); closed joints show only as that tone change and the face's own tilt
    # (whole blocks only a little: +-13% per block read as pasted flat rectangles, a patchwork, at 40 m (n01). What
    # separates faces on real limestone/sandstone is weathering that runs along the beds and down from the ledges, with
    # soft transitions; the blocks' own geometry and the lines do the rest)
    # (a thin package is darker only where it sits back, by as much as it does (terrain_blocks._bed_value's stretches
    # and depth): darker all along, it was a ruled band across the pebble chasm)
    rec = terrain_blocks.package_recess(P[:, :2], K, j, B)
    tone = 1 + (BLOCK_TONE["bed"] * (2 * hsh(K, j, 1) - 1) - BLOCK_TONE["thin"] * I["thin"] * rec) * eb
    # (lines=False: the open bed planes and joints are drawn crisp from the lines map, terrain_swatch.structure_lines)
    dark = 0.5 * I["bed_crack"] * (1 - eb) * lines  # (bed planes: faint; the geometry draws the ledges)
    fresh = np.zeros(len(P))
    # (a block's tone is not uniform across it: weathering wanders within the face, and a spall bares only part of it;
    # a flat tone per block with crisp edges read as masonry tiles)
    within = noise.fbm(P, 1.6, 2, seed=sd + 6)
    spall = smoothstep(0.4, 0.6, noise.fbm(P, 1.8, 2, seed=sd + 7))  # (0.7 m read as camouflage at 40 m)
    for m, (bi, w) in enumerate(zip(I["blocks"], I["weights"])):
        jj = (K * 16 + j) * 5 + m
        e_m = ease(I["edges"][m])
        tone = tone * (1 + w * BLOCK_TONE["block"] * (2 * hsh(bi, jj, 2) - 1) * e_m * (0.55 + 0.9 * within))
        fresh = np.maximum(fresh, w * (hsh(bi, jj, 3) < BLOCK_TONE["p_fresh"]) * e_m * spall)
        if lines:
            dark = np.maximum(dark, w * (1 - ease(I["open"][m])))  # (open joints only: most boundaries are closed)
    # freshly spalled faces: paler and warmer (unweathered rock under the grey patina)
    tone = tone * (1 + BLOCK_TONE["fresh"] * fresh * eb)
    dark = np.maximum(dark, np.clip(1.6 * I["master"], 0, 1))  # (master joints: always open)
    tone = tone * (1 - 0.18 * dark)
    # stains: dark streaks hanging from the ledges (each super-bed's top), 0.25-0.8 m wide, 2-12 m long, narrowing and
    # fading down; a few per 10 m along the face, in patches. (Stretched noise made ink blots.)
    vert = np.clip((0.7 - np.abs(N[:, 2])) / 0.4, 0, 1)
    fdn = fd / np.maximum(np.linalg.norm(fd, axis=1, keepdims=True), 1e-9)
    u = P[:, 0] * -fdn[:, 1] + P[:, 1] * fdn[:, 0]  # (along the face)
    d = I["below_top"]
    K1 = I["K"]
    patch = np.clip((noise.fbm(P * np.array([1.0, 1.0, 0.3]), 25.0, 2, seed=sd + 4) - 0.4) / 0.2, 0, 1)
    stain = np.zeros(len(P))
    # (candidates every 3 m, a fifth present: every 1.5 m with half present read as a comb from 150 m)
    c0 = np.floor(u / 3.0).astype(np.int64)
    for dc in (-1, 0, 1):
        c = c0 + dc
        uc = (c + 0.5 + 0.8 * (hsh(c, K1, 10) - 0.5)) * 3.0
        L = 2.0 + 10.0 * hsh(c, K1, 11)
        wd = (0.25 + 0.55 * hsh(c, K1, 12)) * (1 - 0.5 * np.clip(d / L, 0, 1))
        on = hsh(c, K1, 13) < 0.22
        across = np.clip(1 - np.abs(u - uc) / wd, 0, 1)
        down = np.clip(1 - d / L, 0, 1) ** 1.5 * np.clip(d / 0.3, 0, 1)
        stain = np.maximum(stain, on * (across * (2 - across)) * down)
    tone = tone * (1 - 0.32 * stain * patch * vert)
    # weathering along the beds: tone bands a few metres long and under a metre tall, following the bed coordinate
    # (soft: no edge to alias), and each ledge's underside darker for a metre or so (runoff and shade), easing in from
    # the plane itself (a step there aliases in the maps)
    bz = P[:, 2] + zoff
    band = noise._value_noise(np.ascontiguousarray(np.c_[u / 6.0, bz / 0.9, K1 * 0.37]), sd + 8)
    tone = tone * (1 + BLOCK_TONE["along"] * (2 * band - 1) * vert)
    ul = np.exp(-d / 1.2) * smoothstep(0.0, 0.2, d) * (0.5 + noise._value_noise(
        np.ascontiguousarray(np.c_[u / 9.0, K1 * 0.53, np.zeros(len(P))]), sd + 9))
    tone = tone * (1 - BLOCK_TONE["under_ledge"] * ul * vert)
    out = rc * tone[:, None] * (1 + (fresh * eb)[:, None] * np.array(BLOCK_TONE["warm"]))
    # lichen on tops: up-facing ledges and block tops, patchy, a dull grey-green (pale lichen read as foam on the ledges)
    up = np.clip((N[:, 2] - 0.4) / 0.35, 0, 1)
    li = np.clip((noise.fbm(P, 0.9, 2, seed=sd + 5) - 0.55) / 0.2, 0, 1) * up
    lichen = rc * np.array([0.8, 0.86, 0.72])
    return out * (1 - 0.5 * li[:, None]) + lichen * (0.5 * li[:, None])


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
    if images:  # [(bytes, mime type) | uri]: embedded or (a str) a file beside the GLB; texture i = image i, one
        # sampler (trilinear, repeat)
        doc["images"] = []
        for im in images:
            if isinstance(im, str):
                doc["images"].append({"uri": im})
                continue
            data, mime = im
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
    if hasattr(field, "zlow"):  # (a cliff shell: as deep as it goes under these columns, see CliffField.zlow)
        zlo, zhi = float(np.min(field.zlow(XE.ravel(), YE.ravel()))), h.max()
    else:
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
    S_ = np.repeat(scol, len(ic))
    with _span("mc/lattice field"):
        for q in range(0, len(P), 400_000):  # (in pieces: a whole tile's lattice at once peaked at ~2 GB a worker)
            F[q:q + 400_000] = field.solid(P[q:q + 400_000], F[q:q + 400_000].copy(), S_[q:q + 400_000])
    eps = 1e-3 * v
    # (clamped to a few voxels: a far value (a cliff shell's 1e3 "air") pulled crossings onto the lattice node itself in
    # float32, and the border vertex lost its edge; only the sign decides which edges are crossed)
    F = np.clip(np.where(np.abs(F) < eps, np.where(F < 0, -eps, eps), F), -3 * v, 3 * v)
    F = F.reshape(len(ia), len(ib), len(ic))
    if F.min() > 0 or F.max() < 0:
        return None
    with _span("mc/skimage"):
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


PRE = 32  # x a coarse LOD's budget: what its dense-mesh fallback reaches in one pyfqmr pass before the budget search
# (replayed on the alps block's 12 fallbacks: 85 -> 37 s, faces <= the old ones in every case, summed error p99
# 6.2 -> 5.7 m; 4x and 8x were faster still but their meshes sat further off the rock at the same count)


def _decimate(P, faces, err, budget, field, border_ok=None, pre=None):
    """Fewest triangles (pyfqmr, open borders locked) whose surface stays within `err` of the field (99th percentile
    at face centres and edge midpoints, over what the undecimated mesh already misses), capped at `budget`.
    (pyfqmr's own lossless mode barely removed anything with the border locked.)
    border_ok(v): False when a vertex on a tile's border plane isn't one of the canonical border vertices. pyfqmr
    locks vertices on OPEN edges only: two border vertices joined by an interior edge (a shell's front and back
    meeting in the border plane) may collapse into a new point on the plane, and the export then died after every
    tile was baked ("border vertices moved in decimation", alps blocks). Such a result counts as a fold.
    pre: a face count to reach in one pyfqmr pass first (from a dense mesh), the tolerance staying the dense mesh's:
    counting down from a 265k-face mesh ran pyfqmr on all of it 20-60 times a LOD (10-28 s, the alps block's
    stragglers); the same search from PRE x the budget takes 2-5 s, to the same budget and tolerance."""
    import pyfqmr
    n_open = len(_boundary_edges(faces))

    def valid(v, f):  # manifold, no new holes (dropping a fin's twin faces can open one), the border kept
        return _manifold(f) and len(_boundary_edges(f)) == n_open and (border_ok is None or border_ok(v))

    def run(n, base=None):
        # pyfqmr sometimes folds a thin part (a cave mouth, an arch's soffit) whatever the count: other settings of
        # its aggressiveness usually don't
        Pb, Fb = base if base is not None else (P, faces)
        out = None
        for agg in (7, 5, 9, 6, 8):
            profiling.count("decimate.pyfqmr runs")
            with _span("decimate.pyfqmr", leaf=True):
                s = pyfqmr.Simplify()
                s.setMesh(Pb, Fb)
                s.simplify_mesh(target_count=int(n), aggressiveness=agg, max_iterations=300, preserve_border=True,
                                verbose=False)
                v, f, _ = s.getMesh()
                out = _drop_twins(np.asarray(v, float), np.asarray(f, np.int64))
            with _span("decimate.valid", leaf=True):
                ok = valid(*out)
            if ok and len(out[1]) <= 1.15 * n + 64:  # (a low aggressiveness can stall far above n)
                return out
        return out


    def error(v, f):
        if not valid(v, f):  # pyfqmr can fold a thin part into a fin (two faces on one directed edge)
            return np.inf
        c = np.r_[v[f].mean(1), (v[f[:, 0]] + v[f[:, 1]]) / 2]
        with _span("decimate.error"):
            if hasattr(field, "front"):
                # a cliff shell is judged where it is seen: faces with every corner on the visible rock (the rule
                # that sorts "surface" from "buried" in _job_tile), by the visible rock's own field. The buried
                # back's values aren't metres (slice_a's cave tile: |field| p99 0.59 at the dense mesh's own face
                # centres, all of it 5-25 m under the ground): counted, they were the tolerance
                thr = max(0.3, 2 * err)
                vis = (np.abs(field.front(v)) <= thr)[f].all(1)
                if vis.sum() >= 16:
                    return float(np.percentile(np.abs(field.front(c[np.r_[vis, vis]])), 99))
            return float(np.percentile(np.abs(field.value(c)), 99))

    tol = err + error(P, faces)
    if pre is not None and len(faces) > 1.5 * pre and len(faces) > budget:
        cand = run(pre)
        if valid(*cand) and len(cand[1]) < len(faces) and error(*cand) <= tol:
            profiling.count("decimate: a dense mesh taken down in one pass first")
            P, faces = cand
    if len(faces) <= budget:
        best, hi = (P, faces), len(faces)
    else:
        # the budget caps it: the first unfolded result at or under it (a fold at the budget itself used to hand back
        # the undecimated mesh: LOD2 came out bigger than LOD1)
        n = int(budget)
        best = None
        last = None
        while n >= 16:
            cand = run(n)
            if valid(*cand) and len(cand[1]) <= budget:
                best = cand
                break
            # pyfqmr stalled (a lower target gave the same mesh: it stops where its flip and border checks block every
            # collapse, far above the target from a dense mesh): every lower count would too. The steps below, each
            # from the last mesh, get past it in a second; counting down to 16 took ~100 runs (80-110 s a LOD, the
            # alps block's straggler tiles)
            if last is not None and len(cand[1]) == last:
                profiling.count("decimate: pyfqmr stalled above the budget")
                break
            last = len(cand[1])
            n = int(n * 0.8)
        if best is None:  # in one pass every count folded something: in steps, each from the last good mesh
            cur = (P, faces)
            while len(cur[1]) > budget:
                cand = run(max(int(len(cur[1]) / 1.6), int(budget)), cur)
                if not valid(*cand) or len(cand[1]) >= len(cur[1]):
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


WELD = 1e-3  # x voxel: canonical border vertices joined by a chain edge and closer than this are one vertex


def _weld_rows(plane_edges, CP, corner, tol):
    """{row: the row it is welded to} for canonical border rows joined by a border chain edge and closer than tol.
    Two marching-cubes crossings whose Newton steps converge on one point (a corner of pebble's karst passage in a tile
    border plane: 7e-7 m apart) are one vertex in the GLB's float32 positions: the sliver face between them turns
    degenerate and its neighbours meet on a non-manifold edge with doubled directed edges. Dropping one in the chain
    simplification wasn't enough (a border collapse that failed at a coarser LOD put it back at every LOD), so the pair
    is merged before any LOD is made: in the chains here and in each tile's dense mesh (`_job_dense`). Corners win."""
    par = {}

    def find(x):
        while par.get(x, x) != x:
            x = par[x]
        return x

    for e in plane_edges.values():
        for a, b in e:
            if a != b and float(np.linalg.norm(CP[a] - CP[b])) < tol:
                ra, rb = find(a), find(b)
                if ra == rb:
                    continue
                if corner[ra] and corner[rb]:
                    continue
                keep_, gone = (ra, rb) if corner[ra] or (not corner[rb] and ra < rb) else (rb, ra)
                par[gone] = keep_
    return {x: find(x) for x in par}


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


WORKER_GB = 2.0  # a tile worker's peak PSS with maps: 1.04 GB on pebble (0.5 m voxel), 1.93 GB on a 10 x 10 tile block
# of t3_alps (1 m voxel, a 3 x 4 km terrain in the parent); field calls chunked, dense meshes streamed through
# <out>/_work (2.2 GB on pebble before that)


def _pool():
    """A fork pool sized by free memory (`resources.workers`), guarded: 16 fixed workers x ~2 GB plus other jobs
    OOM-killed the user's desktop twice."""
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor
    from . import resources
    n = resources.workers(_CTX.get("worker_gb", WORKER_GB), cap=16)
    fieldjit.warm()  # (compiled kernels in the parent: the forked workers inherit them, none compiles its own)
    # (one BLAS thread a worker: each inherited the parent's 4, which spun on every small matmul)
    ex = ProcessPoolExecutor(max_workers=n, mp_context=multiprocessing.get_context("fork"),
                             initializer=resources._worker_init)
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
        h = np.ascontiguousarray(h.reshape(hm, hm)[::-1], np.float32)  # north-up rows, C order on disk
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
    kk = _border_keys(idx, rng, n, NX, NY)
    # the dense mesh goes to disk (per tile, streamed): only the border keys and edges come back to the parent,
    # which had held every tile's meshes at once
    np.savez(_work(c, "mc", i, j), idx=idx, faces=faces)
    bed = [(int(a), int(b)) for a, b in _boundary_edges(faces) if a in kk and b in kk]
    return rng, kk, bed


def _work(c, kind, i, j, k=None):
    return c["work"] / (f"{kind}_{i}_{j}.npz" if k is None else f"{kind}_{i}_{j}_{k}.npy")


def _dense(c, ij):
    d = np.load(_work(c, "dense", *ij))
    return d["P"], d["faces"], d["vrow"]


def _job_dense(ij):
    """A tile's LOD0 mesh: marching cubes on the lattice, interior projected, border vertices the canonical ones."""
    c = _CTX
    G, v0, field, reg, CP = c["G"], c["v0"], c["field"], c["reg"], c["CP"]
    rng, kk, _ = c["mc"][ij]
    d = np.load(_work(c, "mc", *ij))
    idx, faces = d["idx"], d["faces"]
    P = np.c_[G.origin[0] + idx[:, 0] * v0, G.origin[1] + idx[:, 1] * v0, (idx[:, 2] + ZOFF) * v0]
    border = np.array(sorted(kk), np.int64)
    rows = np.array([reg[kk[q]] for q in border], np.int64)
    alias, gone = c.get("alias") or {}, np.zeros(0, np.int64)
    if alias and any(int(r) in alias for r in rows):  # (welded rows: their vertices merged, `_weld_rows`)
        rows = np.array([alias.get(int(r), int(r)) for r in rows], np.int64)
        orig = np.array([reg[kk[q]] for q in border], np.int64)
        remap = np.arange(len(P))
        first = {}
        for v, r, o in sorted(zip(border.tolist(), rows.tolist(), orig.tolist()), key=lambda t: (t[1], t[2] != t[1], t[0])):
            if r in first:
                remap[v] = first[r]
            else:
                first[r] = v
        gone = np.flatnonzero(remap != np.arange(len(P)))
        faces = remap[faces]
        faces = faces[(faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])]
    inner = np.setdiff1d(np.arange(len(P)), border)
    N = np.zeros_like(P)
    with _span("dense/project"):
        P[inner], N[inner] = project(field, P[inner], v0)
    P[border], N[border] = CP[rows], c["CN"][rows]
    mov = np.ones(len(P), bool)
    mov[border] = False
    if c["cfg"].get("sharp", True):  # creases on mesh edges (extended marching cubes), not a sawtooth
        n0 = len(P)
        to_world = lambda q: np.array([G.origin[0] + q[0] * v0, G.origin[1] + q[1] * v0, (q[2] + ZOFF) * v0])
        with _span("dense/sharp features"):
            P, faces, N, _ = terrain_sharp.feature_points(P, faces, idx, N, field, to_world, v0, mov,
                                                          bounds=G.bounds(*ij))
        mov = np.r_[mov, np.ones(len(P) - n0, bool)]
    else:
        P = snap_creases(P, faces, field, v0, mov)
    vrow = np.full(len(P), -1, np.int64)
    vrow[border] = rows
    vrow[gone] = -1  # (merged into their weld's kept vertex: unused)
    with _span("dense/specks + save"):
        faces = _drop_specks(P, faces, vrow >= 0, float(c["cfg"].get("min_piece_m2", 4.0)))
        np.savez(_work(c, "dense", *ij), P=P, faces=faces, vrow=vrow)
    # the area its maps will cover (a cliff shell's visible front only): the export's texel density is chosen from it
    area = 0.0
    if len(faces):
        a = np.linalg.norm(np.cross(P[faces[:, 1]] - P[faces[:, 0]], P[faces[:, 2]] - P[faces[:, 0]]), axis=1) / 2
        if hasattr(field, "front"):
            with _span("dense/visible area"):
                a = a[np.abs(_chunks(field.front, P[faces].mean(1))) <= 0.3]
        area = float(a.sum())
    return True, area


def _chunks(fn, X, n=200_000):
    return np.concatenate([fn(X[i:i + n]) for i in range(0, len(X), n)]) if len(X) else np.zeros(0)


def _drop_specks(P, F, on_border, min_area):
    """Closed pieces of a tile's mesh smaller than `min_area` m2 that touch no tile border: bubbles where the field
    grazes zero just off a steep face (rock relief on a 60 deg wall: 14-triangle specks floating 15 m up)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    n = len(P)
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]]])
    nc, lab = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n)), directed=False)
    if nc == 1:
        return F
    area = np.linalg.norm(np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]]), axis=1) / 2
    ca = np.bincount(lab[F[:, 0]], area, minlength=nc)
    border = np.zeros(nc, bool)
    border[lab[on_border]] = True
    small = (ca < min_area) & ~border
    return F[~small[lab[F[:, 0]]]] if small.any() else F


def _job_collapse(args):
    ij, keep_rows, k = args
    P, faces, vrow = _dense(_CTX, ij)
    drop = np.flatnonzero((vrow >= 0) & ~np.isin(vrow, keep_rows))
    with _span("collapse border"):
        Fk, bad = _collapse_border(P, faces, drop)
    np.save(_work(_CTX, "col", ij[0], ij[1], k), Fk)
    return {int(vrow[u]) for u in bad}


def _job_dense_full(ij):
    """A tile's dense LOD0 (`_job_dense`), its marching cubes first when the last export made them (incremental: the
    border keys came from the state). Those must come out as stored: a difference would break the invariant."""
    c = _CTX
    if not _work(c, "mc", *ij).exists():
        r = _job_mc(ij)
        want = c["mc"][ij]
        if r is None or r[0] != want[0] or r[1] != want[1] or r[2] != want[2]:
            raise RuntimeError(f"tile {ij[0]},{ij[1]}: marching cubes made again differ from the stored ones")
    return _job_dense(ij)


def _job_prep_tile(ij):
    """The work files a tile's LODs read when the last export made its dense mesh and collapses: made again, with
    this export's kept vertices."""
    c = _CTX
    if not _work(c, "dense", *ij).exists():
        _job_dense_full(ij)
    for k, kr in enumerate(c["keep"]):  # (the same sorted rows the collapse loop passed)
        _job_collapse((ij, kr, k))


def build_field(T, cfg=None):
    """The 3D field of a terrain: (field, volume pieces, notes, caves)."""
    from . import terrain_caves
    cfg = {**DEFAULTS, **((T.spec.get("export") or {}).get("tiles") or {}), **(cfg or {})}
    vols, notes = volumes(T)
    if cfg.get("stacks", True) and _sea(T) is not None:
        sv, sn = stacks(T)
        vols = vols + sv
        if sn:
            notes = notes + [sn]
    rock = rock_config(T, cfg)
    caves = terrain_caves.build(T, rock)
    for cv in caves:
        vols = vols + cv.tubes
        notes = notes + cv.notes
    from . import terrain_design as design
    bunkers = []
    for name in getattr(T, "cover", {}):
        c = design._spec_cover(T, name)
        if c.get("type", name) == "bunker":
            bunkers.append((T.cover[name], float(c.get("depth", 0.6)), name))
            notes = notes + [f"{name}: bunkers dug {float(c.get('depth', 0.6)):g} m in, over "
                             f"{float((T.cover[name] > 0.5).sum()) * T.cell ** 2:.0f} m2"]
    field = Field(T, vols, rock, dolines=[d for cv in caves for d in cv.dolines],
                  cuts=[v.cut for v in vols if getattr(v, "cut", None)], bunkers=bunkers)
    for v in vols:
        if getattr(v, "kind", None) == "arch":
            v.view = through_view(field, v)
            notes.append(v.view["note"])
    return field, vols, notes, caves


def _swatch(out, rock, macro_density=8.0, source="procedural"):
    """terrain_swatch.write(out, rock, "rock"), or what the last export wrote when the swatch's inputs (the rock's seed,
    the swatch's code) and its files are the same."""
    import pickle
    from . import codehash, terrain_swatch
    from . import terrain_incremental as inc
    key = inc._h(codehash.digest("terrain_swatch"), int((rock or {}).get("seed", 4242)), terrain_swatch.SIZE,
                 terrain_swatch.RES, float(macro_density), str(source))
    p = out / "_incremental" / "swatch.pkl"
    files = lambda de: sorted(v for v in de.values() if isinstance(v, str) and v.startswith("materials/"))
    try:
        k, de, fk = pickle.loads(p.read_bytes())
        if k == key and inc.files_key(out, files(de)) == fk:
            return de
    except Exception:
        pass
    de = terrain_swatch.write(out, rock, "rock", macro_density=float(macro_density), source=source)
    p.parent.mkdir(exist_ok=True)
    p.write_bytes(pickle.dumps((key, de, inc.files_key(out, files(de)))))
    return dict(de)


def _fingerprint(T, cfg, base, field, mats, region, G, hrange):
    """What every tile's outputs read (terrain_incremental.Fingerprint): the export's field, materials, cliff region
    and detail projection, the terrain's cover grids and the settings; per tile windows of the grids."""
    from . import codehash
    from .terrain_incremental import Fingerprint, Frame
    frames = [Frame("terrain", T.H.shape, "yx", T.xs[0], T.ys[0], T.cell)]
    if region is not None:  # (the cliff region's heightmap lattice [ix, iy], nodes and cells)
        frames += [Frame("region", (region.nx, region.ny), "xy", G.origin[0], G.origin[1], region.d),
                   Frame("region cells", (region.nx - 1, region.ny - 1), "xy", G.origin[0], G.origin[1], region.d)]
    roots = {"field": field, "base": base, "materials": mats, "terrain cover": dict(T.cover),
             "terrain frame": (float(T.xs[0]), float(T.ys[0]), float(T.cell), tuple(T.H.shape)),
             "region": region, "detail": _CTX.get("detail"), "detail entry": _CTX.get("detail_entry"),
             "config": {k: v for k, v in cfg.items() if k not in ("incremental",)}, "heights range": hrange,
             "grid": G, "sea": _sea(T), "code": codehash.digest("terrain_mesh")}
    return Fingerprint(roots, frames, base.vols, float(cfg["cave_wall"]) + 3.0)


class TilesCheckFailed(RuntimeError):
    """The export's checks failed AFTER everything was written. `result` is what export_tiles would have returned
    (out, manifest, stats, timing, check): the files and manifest.json are on disk and complete; `summary(result)`
    is the report with the failures on top."""

    def __init__(self, msg, result):
        super().__init__(msg)
        self.result = result


OVER_BUDGET = 2.0  # a tile LOD with more than this x its triangle budget fails the export's checks (said per tile)


def budget_check(manifest_tiles, cfg, lods):
    """Tile LODs over OVER_BUDGET x their triangle budget, with what the numbers say about why."""
    over = []
    for e in manifest_tiles:
        for k, L in enumerate(e["lods"]):
            if not L or k >= lods:
                continue
            b = cfg["budget"][min(k, len(cfg["budget"]) - 1)]
            if L["triangles"] <= OVER_BUDGET * b:
                continue
            mc = L.get("marching_cubes_triangles") or 0
            if mc and L["triangles"] > 0.9 * mc:
                why = ("decimation removed nothing (every simplification folded the mesh or opened it: rock or shell "
                       "thinner than the voxel)")
            else:
                why = "decimation stalled above it (folds in thin rock, or its border chain alone is this long)"
            over.append({"tile": [e["i"], e["j"]], "lod": k, "triangles": L["triangles"], "budget": int(b),
                         "visible_triangles": L.get("visible_triangles"), "marching_cubes_triangles": mc,
                         "volumes": e.get("volumes", []), "why": why})
    return over


def export_tiles(T, out_dir, cfg: dict | None = None, log=print) -> dict:
    """See `_export_tiles`; holds the machine's heavy-job slot (`resources.heavy`) so exports don't stack up."""
    from . import resources
    # (PSS every 2 s: reading every worker's smaps_rollup each 0.5 s kept a parent thread ~40% busy)
    with resources.heavy("terrain tiles", log=log), resources.peak_memory(every=2.0) as peak:
        return _export_tiles(T, out_dir, cfg, log, peak)


def _export_tiles(T, out_dir, cfg: dict | None = None, log=print, peak=None) -> dict:
    """Mesh the terrain's field (heightfield + volumes) into seamless tiles; write GLBs per tile per LOD, collision
    GLBs, heightmap and splat tiles, trees.csv and manifest.json; run the seam check (raises if it fails)."""
    from PIL import Image
    import copy
    t_all = time.time()
    cfg = {**DEFAULTS, **((T.spec.get("export") or {}).get("tiles") or {}), **(cfg or {})}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    import shutil
    workdir = out / "_work"  # per-tile dense meshes, streamed through disk; removed at the end
    shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir()
    _CTX.clear()
    _CTX["work"] = workdir
    timing = {}
    prof = profiling.Report()  # per stage: wall, workers' busy share, stragglers; spans, field counts (manifest "profile")
    tile_key = lambda ij: f"{ij[0]},{ij[1]}"
    t0 = time.time()
    _st = prof.stage("setup (parent)")
    _st.__enter__()
    field, vols, notes, caves = build_field(T, cfg)
    base = field  # the whole rock (materials, trees, caves' walk, splats); `field` is what's meshed
    mats = Materials(T, base)
    G = Grid(T, cfg)
    if cfg.get("detail") and base.rock is not None:  # (the tiling detail's projection, read by the workers)
        from . import terrain_swatch
        _CTX["detail"] = terrain_swatch.DetailProjection(base, base.rock)
        de = _swatch(out, base.rock, cfg["texel_density"][0], cfg["detail_source"])  # (cached by seed + code)
        de.update(texcoord=1 + bool(int(cfg["splat"])), bins=_CTX["detail"].BINS, line_d=terrain_swatch.LINE_D,
                  layers=[nm for nm in ("rock", "wet_rock") if nm in mats.layers], recipe=terrain_swatch.RECIPE,
                  gltf=("each cliff tile LOD's baked material carries extras.hifipushie_detail: texture indices of "
                        "the embedded lines map and of the swatch images (files in materials/, by uri), and the UV "
                        "set; glTF viewers ignore it and show the macro maps"))
        _CTX["detail_entry"] = de
        # (the drawn lines go to the lines map, crisp, instead of blurring into the macro colour)
        mats.lines_in_maps = bool(cfg.get("lines", True))
    region = None
    if cfg["mode"] == "cliffs":
        from . import terrain_cliffs
        region = terrain_cliffs.Region(T, base, G, cfg)
        field = terrain_cliffs.CliffField(base, region)
    elif cfg["mode"] != "full":
        raise ValueError(f"export.tiles mode {cfg['mode']!r}: use cliffs or full")
    _st.__exit__(None, None, None)
    timing["setup"] = time.time() - t0
    tiles = [(i, j) for j in range(G.nj) for i in range(G.ni)]
    if cfg.get("only"):  # a block of tiles [[i0, j0], [i1, j1]] (inclusive), for trying things
        (i0, j0), (i1, j1) = cfg["only"]
        tiles = [(i, j) for (i, j) in tiles if i0 <= i <= i1 and j0 <= j <= j1]
    log(f"{len(tiles)} tiles ({G.ni} x {G.nj}) of {G.tile:g} m, voxel {G.voxel:g} m, LOD errors "
        f"{cfg['error'][:G.lods]} m, {len(vols)} volume pieces")

    # ---- 0. incremental: each tile's inputs keyed (terrain_incremental); the previous export's state if it applies
    from . import terrain_incremental as inc
    t0 = time.time()
    with prof.stage("incremental keys (parent)"):
        hrange = [float(np.nanmin(T.H)), float(np.nanmax(T.H))]
        fp = _fingerprint(T, cfg, base, field, mats, region, G, hrange)
        fkey = {ij: fp.tile(*G.bounds(*ij)) for ij in tiles}
        prev_state, why_cold = None, "incremental off (export.tiles incremental false or HIFIPUSHIE_TILES_COLD)"
        if fp.unknown:
            why_cold = f"inputs it can't fingerprint: {fp.unknown[:3]}"
            (out / inc.STATE).unlink(missing_ok=True)
        elif cfg.get("incremental", True) and not os.environ.get("HIFIPUSHIE_TILES_COLD"):
            prev_state, why_cold = inc.load(out, fp.parts["code"], fp.global_key, fp.parts)
        else:
            (out / inc.STATE).unlink(missing_ok=True)
    old = prev_state["tiles"] if prev_state else {}
    ns = {ij: {"field": fkey[ij][0], "parts": fkey[ij][1]} for ij in tiles}  # (the state this export leaves)
    redone = {}
    if prev_state is None:
        log(f"cold export: {why_cold}")
        for f in out.glob("*.glb"):
            f.unlink()
    timing["incremental keys"] = time.time() - t0

    # ---- 1. marching cubes per tile, and the canonical border vertices (decided once)
    t0 = time.time()
    v0 = G.voxel
    mc = {}
    reg = {}
    _CTX.update(field=field, G=G, vols=vols, base=base)
    redo = [ij for ij in tiles if not (ij in old and old[ij]["field"] == fkey[ij][0] and "mc" in old[ij])]
    if prev_state is not None:
        changed = [ij for ij in redo if ij in old]
        log(f"incremental: {len(redo)} of {len(tiles)} tiles' inputs changed" +
            "".join(f"; {ij[0]},{ij[1]}: {inc.why(old[ij]['parts'], fkey[ij][1])}" for ij in changed[:4]))
    redone["marching cubes"] = len(redo)
    if redo:
        with _pool() as ex:  # (in parallel: serial it was a third of the export)
            for ij, r in zip(redo, prof.pool_map(ex, _job_mc, redo, "marching cubes", tile_key)):
                mc[ij] = r
    mc = {ij: mc[ij] if ij in mc else old[ij]["mc"] for ij in tiles}  # (tile order: the chains' order follows it)
    for ij in tiles:
        ns[ij]["mc"] = mc[ij]
    for (i, j) in tiles:  # canonical border keys numbered in tile order (deterministic)
        if mc[i, j] is not None:
            for key in mc[i, j][1].values():
                reg.setdefault(key, len(reg))
    keys = sorted(reg, key=reg.get) or [(0, 0, 0, 0)]  # (a placeholder when no tile has a mesh)
    with prof.stage("border vertices (parent)"):
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
        rng, kk, bed = r
        for (p, q) in bed:
            if True:
                for plane in _planes(kk[p], kk[q], G, 0):
                    plane_edges.setdefault(plane, set()).add(tuple(sorted((reg[kk[p]], reg[kk[q]]))))
    _st = prof.stage("border chains (parent)")
    _st.__enter__()
    corner = fixed[:, 0] & fixed[:, 1]
    alias = _weld_rows(plane_edges, CP, corner, WELD * v0)
    if alias:  # (the chains run through each weld's kept row; every tile's dense mesh merges its vertices the same way)
        plane_edges = {pl: {tuple(sorted((alias.get(a, a), alias.get(b, b)))) for a, b in e
                            if alias.get(a, a) != alias.get(b, b)} for pl, e in plane_edges.items()}
        log(f"{len(alias)} border vertices welded to a neighbour closer than {WELD * v0:.2g} m")
    _CTX["alias"] = alias
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
    _st.__exit__(None, None, None)
    timing["border chains"] = time.time() - t0

    # ---- 3. per tile: LOD0 projected; each LOD = border chains collapsed to its kept vertices, then decimated
    t0 = time.time()
    _CTX.update(field=field, G=G, v0=v0, mc=mc, reg=reg, CP=CP, CN=CN, cfg=cfg)
    work = [ij for ij, r in mc.items() if r is not None]
    # each tile's border rows as its dense mesh takes them (welds merged), and what its dense mesh depends on: its
    # field, its canonical border vertices, and their order (a weld keeps the lowest row)
    rows_of, dkey = {}, {}
    for ij in work:
        kk = mc[ij][1]
        orig = np.array([reg[kk[q]] for q in sorted(kk)], np.int64)
        rows = np.array([alias.get(int(r), int(r)) for r in orig], np.int64)
        rows_of[ij] = rows
        dkey[ij] = inc._h(fkey[ij][0], "dense", inc.rank(rows), rows != orig, CP[rows], CN[rows])
    redo = [ij for ij in work if not (ij in old and old[ij].get("dense", {}).get("key") == dkey[ij])]
    redone["dense LOD0"] = len(redo)
    areas = {}
    if redo:
        with _pool() as ex:
            res = prof.pool_map(ex, _job_dense_full, redo, "dense LOD0 (project, sharp)", tile_key)
        areas = {ij: a for ij, (_, a) in zip(redo, res)}
    for ij in work:
        ns[ij]["dense"] = {"key": dkey[ij], "area": areas[ij] if ij in areas else old[ij]["dense"]["area"]}
    dense = set(work)
    _CTX["dense"] = dense
    # one texel density per LOD for every tile: the asked one, or what the tile with the most rock can fit in
    # texture_max (each tile used to lower its own: on the alps' walls tiles came out 11-16 texels/m side by side,
    # sharp rock beside soft in squares of tiles)
    area = max([ns[ij]["dense"]["area"] for ij in work] + [1.0])
    tmax = int(cfg["texture_max"])
    cfg["_density"] = [min(float(d), math.sqrt(DENSITY_FILL * tmax * tmax / area)) for d in cfg["texel_density"]]
    if cfg["_density"][0] < cfg["texel_density"][0]:
        log(f"texel density {cfg['_density'][0]:.1f}/m at LOD 0 (asked {cfg['texel_density'][0]:g}): the largest "
            f"tile's rock ({area:.0f} m2) in a {tmax} atlas")
    # skirts go into the rock, in the border plane, against the surface normal; never out through the other side
    # (a skirt under a cave roof would hang into the cave)
    dirn = -CN.copy()
    dirn[fixed] = 0.0
    ln_ = np.linalg.norm(dirn, axis=1, keepdims=True)
    dirn = np.where(ln_ > 0.2, dirn / np.maximum(ln_, 1e-9), np.array([0, 0, -1.0]))
    with prof.stage("skirt thickness (parent)"):
        thick = _thickness(field, CP, dirn, np.full(len(CP), 3.0), v0)
    pbr = {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0.0, "roughnessFactor": 0.92}
    mat = [{"name": "terrain_reference", "pbrMetallicRoughness": pbr},
           {"name": "terrain_skirt", "doubleSided": True, "pbrMetallicRoughness": pbr}]
    rounds = 0
    # border collapses: (tile, LOD) keyed by the tile's dense key and which of its border rows the LOD keeps; the
    # vertices it couldn't drop are stored as positions in the tile's rows (row numbers shift between exports)
    tile_state = {ij: old[ij]["tile"] for ij in tiles if "tile" in old.get(ij, {})}  # (each tile's LODs as on disk)
    rpos_of, tile_wanted = {}, {}
    col_known = {(ij, ck): pos_ for ij in work for ck, pos_ in old.get(ij, {}).get("col", {}).items()}
    col_used, col_file, col_all = {}, {}, set()  # (ij, k) -> the key this export's chains need; the file in _work's
    first = lambda rows: {int(r): p for p, r in reversed(list(enumerate(rows.tolist())))}
    redone["border collapses"] = 0
    while True:
        collapsed = {}
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
            todo = {}
            for k in range(G.lods):
                kr = np.array(sorted(keep[k]), np.int64)
                for ij in work:
                    ck = inc._h(dkey[ij], "col", k, np.isin(rows_of[ij], kr))
                    col_used[ij, k] = ck
                    col_all.add((ij, ck))  # (every round's: the next export walks the same rounds)
                    if (ij, ck) in col_known:
                        failed |= {int(rows_of[ij][p]) for p in col_known[ij, ck]}
                    else:
                        todo.setdefault(k, []).append((ij, kr, k))
            if todo:
                with _pool() as ex:
                    need_dense = sorted({a[0] for t in todo.values() for a in t if not _work(_CTX, "dense", *a[0]).exists()})
                    if need_dense:  # (tiles whose dense mesh the last export made: made again, one job a tile)
                        prof.pool_map(ex, _job_dense_full, need_dense, "dense LOD0 again (for collapses)", tile_key)
                    for k, jobs in sorted(todo.items()):
                        redone["border collapses"] += len(jobs)
                        for a, bad in zip(jobs, prof.pool_map(ex, _job_collapse, jobs, f"border collapse lod{k}",
                                                              lambda a: f"{a[0][0]},{a[0][1]}")):
                            failed |= bad
                            ij = a[0]
                            f_ = first(rows_of[ij])
                            col_known[ij, col_used[ij, k]] = tuple(sorted(f_[r] for r in bad))
                            col_file[ij, k] = col_used[ij, k]
            if not failed:
                break
            for kk in keep:
                kk |= failed
        else:
            raise RuntimeError("border chains didn't settle (vertices that can't be collapsed, or rock too "
                               "thin for a skirt)")
        for ij in work:
            ns[ij]["col"] = {ck: col_known[ij, ck] for (t, ck) in sorted(col_all) if t == ij}
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
                if base.rock is not None and base.rock.get("joints"):  # (the far LODs' maps: big structure only)
                    rk = dict(base.rock)
                    rk["joints"] = {**rk["joints"], "depth": rk["joints"]["depth"] * [1.0, 0.5, 0.0][min(k, 2)]}
                    bf.rock = rk
                dens = cfg["_density"][min(k, len(cfg["_density"]) - 1)]
                if getattr(base, "edits", None) is not None:  # (the turf's step crisper in the maps than the mesh)
                    bf.edit_riser = max(base.edits.lip_cfg["maps"], 2.5 / dens)
                    bf.edit_wmin = 2.5 / dens
                if base.rock is not None and float(cfg["micro"]) > 0:
                    bf.micro = terrain_bake.micro_relief(base.rock, float(cfg["micro"]), 1.0 / dens,
                                                         fine="detail" not in _CTX)
                if region is not None:  # (a cliff's visible face: the rock, its ground sunk toward the region's edge)
                    bf = terrain_cliffs.CliffField(bf, region).front_field()
                bfs.append(bf)
            # (the normal over ~0.4 m that picks layer weights and colour: from the rock WITHOUT the per-LOD fine relief,
            # so every LOD picks the same layers at a border; with it, the LOD's own band-limited rock structure moved
            # weights p95 0.26 between LOD 0 and LOD 2)
            gf = terrain_cliffs.CliffField(base, region).front_field() if region is not None else base
            _CTX.update(bakefield=bfs, weightfield=gf,
                        layer_rough=np.array([LAYERS[nm]["roughness"] for nm in mats.layers]))
        # every tile's LODs (decimation, atlases), and as each tile is done its atlases' texels baked in pieces across
        # the pool, and each atlas's maps assembled and its GLB written once its pieces are in: a 3 x 3 block's
        # stragglers (one tile decimating for minutes) no longer hold the bake back
        stats, t_dec, wanted, got, left = [], 0.0, set(), {}, {}

        def on_done(fn, arg, r):
            nonlocal t_dec
            if fn is _job_tile:
                entry, st, td, wt = r
                manifest_tiles.append(entry)
                stats.extend(st)
                t_dec += td
                wanted.update(wt)
                tile_wanted[entry["i"], entry["j"]] = set(wt)
                jobs = []
                for q in entry.pop("_bakes", []):
                    # (at most BAKE_PIECE texels a piece, and a small atlas still spread over ~16 jobs: a preview's one
                    # tile. Never by the pool's size: that follows free memory, and where a piece starts changes a few
                    # texels' facet lookups (the walk chains from the last point): exports differed run to run)
                    step = int(np.clip(q["n"] / 16, BAKE_PIECE / 6, BAKE_PIECE))
                    cuts = list(range(0, q["n"], step))
                    left[q["stem"]] = len(cuts)
                    jobs += [(_job_bake, (q["stem"], q["k"], a, min(a + step, q["n"])), f"{q['stem']}@{a}")
                             for a in cuts]
                return jobs
            if fn is _job_bake:
                left[arg[0]] -= 1
                return [(_job_finish, arg[0], arg[0])] if not left[arg[0]] else []
            got[arg] = r
            return []
        # each tile's LODs keyed by its dense mesh and everything _job_tile reads of its border vertices (rows as `pos`
        # finds them): which each LOD keeps, normals, weights, colours, skirt depths and directions; and the density
        kp = _CTX["keep"]
        tkey = {}
        for ij in tiles:
            if ij in dense:
                rows = rows_of[ij]
                rp = np.array([pos[tuple(CP[r])] for r in rows.tolist()], np.int64)
                rpos_of[ij] = rp
                tp = {"dense": dkey[ij], "keep": inc._h(*[np.isin(rows, kp[k]) for k in range(G.lods)]),
                      "keep at pos": inc._h(*[np.isin(rp, kp[k]) for k in range(G.lods)]),
                      "skirt depth": inc._h(*[depth[k][rp] for k in range(G.lods)]), "skirt dir": inc._h(dirn[rp]),
                      "normals": inc._h(CN[rp]), "weights": inc._h(CW[rp], CC[rp]),
                      "density": inc._h(cfg["_density"], mat)}
                ns[ij]["tile parts"] = tp
                tkey[ij] = inc._h("tile", *sorted(tp.items()))
            else:
                tkey[ij] = inc._h(fkey[ij][0], "tile without a mesh")
        redo = [ij for ij in tiles if not (tile_state.get(ij) and tile_state[ij]["key"] == tkey[ij]
                                            and inc.files_ok(out, tile_state[ij]["files"]))]
        redone[f"tiles round {rounds}"] = len(redo)
        stale = [ij for ij in redo if ij in dense and any(col_file.get((ij, k)) != col_used[ij, k]
                                                          for k in range(G.lods))]
        if redo:
            with _pool() as ex:
                if stale:  # (their dense meshes and collapses came from the last export: made again here)
                    prof.pool_map(ex, _job_prep_tile, stale, "dense + collapses again (for tiles)", tile_key)
                    for ij in stale:
                        for k in range(G.lods):
                            col_file[ij, k] = col_used[ij, k]
                prof.run_jobs(ex, [(_job_tile, ij, tile_key(ij)) for ij in redo], on_done,
                              f"tiles (decimate, atlases; maps baked in pieces) round {rounds}")
        for ij in tiles:
            if ij not in redo:  # (unchanged: its entry, stats and files as the last export left them)
                c_ = tile_state[ij]
                manifest_tiles.append(copy.deepcopy(c_["entry"]))
                stats.extend(c_["stats"])
                wanted.update(int(rpos_of[ij][p]) for p in c_["wanted"])
        order = {ij: n for n, ij in enumerate(tiles)}
        manifest_tiles.sort(key=lambda e: order[e["i"], e["j"]])
        stats.sort(key=lambda st: (order[st[0], st[1]], st[2]))
        _maps_done(manifest_tiles, stats, got)
        for e in manifest_tiles:
            ij = (e["i"], e["j"])
            if ij in redo:
                f_ = first(rpos_of[ij]) if ij in rpos_of else {}
                tile_state[ij] = {"key": tkey[ij], "entry": copy.deepcopy(e), "stats": [st for st in stats if st[:2] == ij],
                           "wanted": tuple(sorted(f_[r] for r in tile_wanted.get(ij, ()))),
                           "files": inc.sizes(out, inc.entry_files(e))}
        # a vertex a coarse LOD couldn't lose without folding (the dense mesh folded at every count, and an
        # earlier LOD's mesh couldn't drop it either): every LOD keeps it and the tiles are written again
        if not wanted or rounds >= 2:
            break
        rounds += 1
        for kk in keep:
            kk |= wanted
        log(f"{len(wanted)} border vertices kept for coarse LODs that folded; tiles written again")
    timing["tiles (decimate, project, write)"] = time.time() - t0
    shutil.rmtree(workdir, ignore_errors=True)
    for ij in tiles:
        ns[ij]["tile"] = tile_state[ij]
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
        gkey = {ij: inc._h(fkey[ij][0], "ground") for ij in tiles}
        og = {ij: old[ij]["ground"] for ij in tiles if "ground" in old.get(ij, {})}
        redo = [ij for ij in tiles if not (ij in og and og[ij]["key"] == gkey[ij] and inc.files_ok(out, og[ij]["files"]))]
        redone["ground tiles"] = len(redo)
        got_g = {}
        if redo:
            with _pool() as ex:
                got_g = dict(zip(redo, prof.pool_map(ex, _job_ground, redo, "ground tiles", tile_key)))
        ground = [got_g[ij] if ij in got_g else copy.deepcopy(og[ij]["entry"]) for ij in tiles]
        for ij, e in zip(tiles, ground):
            ns[ij]["ground"] = og[ij] if ij not in got_g else \
                {"key": gkey[ij], "entry": copy.deepcopy(e), "files": inc.sizes(out, inc.entry_files(e))}
        cfg.pop("_hrange"), cfg.pop("_ground_mat"), cfg.pop("_layer_rough")
        manifest_tiles = [e for e in manifest_tiles if any(e["lods"])]
        timing["ground tiles"] = time.time() - t0
        t0 = time.time()
    ents = ground or manifest_tiles
    mkey = {(e["i"], e["j"]): inc._h(fkey[e["i"], e["j"]][0], "maps", e["min"]) for e in ents}
    om = {ij: old[ij]["maps"] for ij in mkey if "maps" in old.get(ij, {})}
    redo = [e for e in ents if not ((e["i"], e["j"]) in om and om[e["i"], e["j"]]["key"] == mkey[e["i"], e["j"]]
                                    and inc.files_ok(out, om[e["i"], e["j"]]["files"]))]
    redone["heightmaps + splats"] = len(redo)
    got_m = {}
    if redo:
        with _pool() as ex:
            got_m = {(e["i"], e["j"]): x for e, x in zip(redo, prof.pool_map(
                ex, _job_maps, [(e["i"], e["j"], e["min"]) for e in redo], "heightmaps + splats",
                lambda a: f"{a[0]},{a[1]}"))}
    for e in ents:
        ij = (e["i"], e["j"])
        extra = got_m[ij] if ij in got_m else copy.deepcopy(om[ij]["extra"])
        ns[ij]["maps"] = om[ij] if ij not in got_m else \
            {"key": mkey[ij], "extra": copy.deepcopy(extra), "files": inc.sizes(out, inc.entry_files(extra))}
        e.update(extra)
    timing["heightmaps + splats"] = time.time() - t0

    # ---- 4b. ground clutter (bushes on the scrub, boulders on the shore): placements an engine's detail scatter can use
    if T.spec.get("ground_character", True) is not False and mats.ground is not None:
        from . import terrain_ground
        with prof.stage("clutter (parent)"):
            ks = ("bush", "boulder")
            cb = None
            if cfg.get("only"):  # (a block of tiles: only its ground)
                (i0, j0), (i1, j1) = cfg["only"]
                cb = [G.bounds(i0, j0)[0][:2].tolist(), G.bounds(i1, j1)[1][:2].tolist()]
            C = terrain_ground.clutter(T, mats, base, ks, box=cb)
            with open(out / "clutter.csv", "w") as f:
                f.write("x,y,z,kind,scale,yaw,squash\n")
                for r in C:
                    f.write(f"{r[0]:.2f},{r[1]:.2f},{r[2]:.2f},{ks[int(r[3])]},{r[4]:.2f},{r[5]:.0f},{r[6]:.2f}\n")
            notes.append(f"clutter.csv: {int((C[:, 3] == 0).sum())} bushes, {int((C[:, 3] == 1).sum())} boulders")

    # ---- 5. trees and the manifest
    _st = prof.stage("trees + layer textures (parent)")
    _st.__enter__()
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
            # nor in the splash zone (a cypress stood on the wave-cut platform at pebble's point), nor on a cliff face
            # (more than 45 deg: the trees' masks are cut on the heightfield, the solid rock is steeper)
            sea = _sea(T)
            wet = (zs < sea + 2.5) if sea is not None else np.zeros(len(zs), bool)
            _, gq = base.value_gradient(np.c_[inst[:, :2], zs], 0.25)
            steep = gq[:, 2] / np.maximum(np.linalg.norm(gq, axis=1), 1e-9) < 0.7
            n_wet, n_steep = int((ok & wet).sum()), int((ok & ~wet & steep).sum())
            ok &= ~wet & ~steep
            # nor perched on a cliff's lip: a tree's roots want soil, so none within its crown of the turf's edge
            # (terrain_ground.TREE_LIP m in from it; wind-shorn cypress may stand closer)
            n_lip = 0
            if getattr(base, "edits", None) is not None and len(inst):
                from . import terrain_ground
                Pq = np.c_[inst[:, :2], zs]
                bare_, d_, edge_, top_ = base.edits.bare(Pq)
                kinds_ = [layers.get(int(li), ("", ""))[1] for li in inst[:, 3]]
                need = np.array([terrain_ground.TREE_LIP.get(k_, terrain_ground.TREE_LIP["default"]) for k_ in kinds_])
                lip = (top_ > 0.3) & (d_ - edge_ < need)
                n_lip = int((ok & lip).sum())
                ok &= ~lip
            inst, zs = inst[ok], zs[ok]
            if n_drop:
                notes.append(f"{n_drop} trees dropped: no solid ground under them")
            if n_wet or n_steep or n_lip:
                notes.append(f"{n_wet} trees dropped in the splash zone (under 2.5 m over the sea), {n_steep} on "
                             f"faces steeper than 45 deg, {n_lip} on cliff lips (closer to the turf's edge than "
                             "terrain_ground.TREE_LIP)")
        for (x, y, _, li), z in zip(inst, zs):
            nm, kind = layers.get(int(li), ("", ""))
            f.write(f"{x:.2f},{y:.2f},{z:.2f},{kind},{nm}\n")
    groups = [mats.layers[g:g + 4] for g in range(0, len(mats.layers), 4)]
    layer_tex = {}
    if cfg.get("maps"):
        from . import terrain_bake
        layer_tex = terrain_bake.layer_textures(out, {nm: mats.layer_ref(nm) for nm in mats.layers})
    detail = _CTX.get("detail_entry")
    _st.__exit__(None, None, None)
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
        "collision": f"collision_<i>_<j>.glb: LOD {cfg['collision']} surface, no skirts, positions only (in cliffs "
                     "mode: the cliff shells, their buried backs included; load it WITH ground_collision_<i>_<j>.glb, "
                     "the heightmap's grid with the hole cells left out). A tile's collision is decimated further "
                     "when its LOD came out over collision_budget (tiles[].collision_triangles)",
        "sea_level": _sea(T),
        "materials": {
            "layers": [{"name": nm, **mats.layer_ref(nm), "weights": f"_WEIGHTS{g}", "channel": c,
                        **({"textures": layer_tex[nm]} if nm in layer_tex else {}),
                        "triplanar": nm in ("rock", "wet_rock")}
                       for g, grp in enumerate(groups) for c, nm in enumerate(grp)],
            "engine_recipe": "per pixel: weights w_i from the weights texture (cliff tiles: maps/<tile>_weights<g>.png "
                             "on TEXCOORD_0) or the splat (ground: TEXCOORD_1) or _WEIGHTS<g> per vertex. Rock on cliff "
                             "tiles: the tiling rock detail instead (manifest detail.recipe) when the export has "
                             "it. Each layer's "
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
        "config": {k: v for k, v in cfg.items() if not k.startswith("_") and k not in ("only", "incremental")},
        "texel_density_used": [round(d, 3) for d in cfg.get("_density", [])],
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
    if detail is not None:
        manifest["detail"] = detail
    if cfg.get("maps") and cfg.get("grass_detail", True) and any(nm in mats.layers for nm in ("grass", "scrub",
                                                                                                "turf", "sand")):
        from . import terrain_ground  # (the turf's tiling detail: terrain_ground.grass_swatch, one per kind)
        ge = terrain_ground.write_grass(out, mats.layers)
        wl = lambda lay: [[f"_WEIGHTS{mats.layers.index(nm) // 4}", mats.layers.index(nm) % 4] for nm in lay
                          if nm in mats.layers]
        for sw in ge["swatches"]:
            sw["weights"] = wl(sw["layers"])
        ge["weights"] = wl(ge["layers"])
        manifest["ground_detail"] = ge
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
                                  "format": "float32 .npy absolute metres, C order, row 0 = the tile's north edge, "
                                            "column 0 = its west; .png 16-bit over the range",
                                  "holes": "heightmaps/holes_<i>_<j>.png only for tiles with holes (ground[].holes)",
                                  "range": hrange, "note": "pushed under the cliff meshes; edges shared with "
                                  "neighbours; ground_<i>_<j>_lod<k>.glb are the same samples as grid meshes (stride "
                                  "2^k, hole cells left out, vertical skirts on shared borders)"}
    if caves:  # a person walked through every passage
        t0 = time.time()
        from . import terrain_caves
        with prof.stage("cave walk (parent)"):
            manifest["caves"] = terrain_caves.check(caves, base, sea=_sea(T))
        timing["cave walk"] = time.time() - t0
    over = budget_check(manifest_tiles, cfg, G.lods)
    manifest["budget_check"] = {"limit": f"{OVER_BUDGET:g} x the LOD's budget", "over": over}
    for o in over[:12]:
        log(f"OVER BUDGET: tile {o['tile'][0]},{o['tile'][1]} LOD {o['lod']}: {o['triangles']} triangles against "
            f"{o['budget']}: {o['why']}")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    # files no tile names any more (a tile that lost its cliff, a LOD without maps now) go; then the state the next
    # export builds on
    keep_files = {f for e in manifest_tiles + ground for f in inc.entry_files(e)}
    for f in list(out.glob("*.glb")) + [p for d in inc.OUT_DIRS for p in (out / d).glob("*") if p.is_file()]:
        if str(f.relative_to(out)) not in keep_files:
            f.unlink()
    inc.save(out, {"format": inc.FORMAT, "code": fp.parts["code"], "global": fp.global_key, "global_parts": fp.parts,
                   "tiles": ns})
    timing["total before check"] = time.time() - t_all
    t0 = time.time()
    if cfg.get("checks", True):
        # (what the checks compute from each tile's files, kept by those files' bytes: an incremental export decodes
        # only the maps of the tiles it rewrote)
        memo = inc.Memo(out, "checks", fp.parts["code"])
        with prof.stage("check: seams (parent)"):
            check = seam_check(out, memo=memo) if manifest_tiles else {"summary": {"failures": 0}, "failures": []}
        if region is not None:
            from . import terrain_cliffs
            with prof.stage("check: ground (parent)"):
                gc = terrain_cliffs.ground_check(out, manifest, region, memo=memo,
                                                 tile_keys={ij: fkey[ij][0] for ij in tiles})
            check["summary"]["ground"] = gc["summary"]
            check["failures"] += gc["failures"]
        # what the eye sees that the per-channel border comparison can't: squares locked to the terrain's grid in the
        # colour, and texel density jumping between neighbouring tiles (sharp rock beside soft)
        from . import terrain_seams
        with prof.stage("check: grid squares (parent)"):
            gs = terrain_seams.grid_squares(T, mats)
        if base.rock is not None:  # how regular the facets look (a lattice shows repeated diamonds from afar)
            from . import terrain_facets
            rk = base.rock
            with prof.stage("check: facet periodicity (parent)"):
                per = terrain_facets.periodicity(lambda P, fd: facet(P, 1.5 * rk["size"], rk["seed"], fd)
                                                 + 0.3 * facet(P, 0.6 * rk["size"], rk["seed"] + 5, fd))
            check["summary"]["facet_periodicity"] = per
            if max(per) > terrain_facets.PERIODIC:
                check["failures"].append(f"rock facets look regular (autocorrelation peaks {per}, limit "
                                         f"{terrain_facets.PERIODIC}): a quilt of repeated diamonds from afar")
        with prof.stage("check: texel density (parent)"):
            td = terrain_seams.texel_density(manifest) if cfg.get("maps") else {"summary": {}, "failures": []}
        check["summary"]["grid_squares"], check["summary"]["texel_density"] = gs, td["summary"]
        if not gs["ok"]:
            check["failures"].append(f"the colour bends on every terrain cell line (x{gs['ratio']} the kinks between "
                                     f"them): cell-sized squares on the rock")
        check["failures"] += td["failures"]
        if detail is not None:  # the swatch must tile: its wrap seam's jump against the steps beside it
            check["summary"]["swatch_wrap_seam"] = detail["wrap_seam"]
            if not detail["tileable"]:
                from . import terrain_swatch
                check["failures"].append(f"the detail swatch's wrap seam shows (jump excess {detail['wrap_seam']}, "
                                         f"limit {terrain_swatch.TILE_LIMIT})")
        for o in over:
            check["failures"].append(f"tile {o['tile'][0]},{o['tile'][1]} LOD {o['lod']}: {o['triangles']} triangles "
                                     f"against a budget of {o['budget']}: {o['why']}")
        check["summary"]["over_budget"] = len(over)
        check["summary"]["failures"] = len(check["failures"])
        check["summary"]["failed"] = check["failures"][:40]
        memo.save()
        redone["check samples"] = {"reused": memo.hits, "computed": memo.misses}
    else:  # (a preview: `preview_tiles`)
        check = {"summary": {"failures": 0, "skipped": "checks off (a preview)"}, "failures": []}
    timing["seam check"] = time.time() - t0
    manifest["seam_check"] = check["summary"]
    manifest["timing_s"] = {k: round(v, 2) for k, v in timing.items()}
    manifest["profile"] = prof.as_dict()
    # (in the profile: like the timings, it says how this export ran, not what it made)
    manifest["profile"]["incremental"] = {"previous export used": prev_state is not None,
                                          "why not": why_cold if prev_state is None else "", "tiles": len(tiles),
                                          "redone": redone}
    log(f"incremental: {json.dumps(manifest['profile']['incremental'])}")
    (out / "profile.txt").write_text(profiling.table(manifest["profile"]))
    log(profiling.table(manifest["profile"], top=25))
    if peak is not None:  # (what the job used, sampled every 0.5 s: PSS of the parent and its workers)
        manifest["memory_gb"] = {k: round(v, 2) for k, v in peak.items()}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    result = {"out": str(out), "manifest": manifest, "stats": stats, "timing": timing, "check": check}
    if check["failures"]:
        # (everything is written and the manifest is complete: the caller can still report it, see `summary`)
        raise TilesCheckFailed(f"seam check FAILED (the tiles and manifest.json were written to {out}):\n"
                               + "\n".join(check["failures"][:30]), result)
    return result


def preview_tiles(T, out_dir, at, radius=40.0, density=6.0, cfg=None, log=print) -> dict:
    """A fast look at the rock round `at` (an address or [x, y]): only the tiles within `radius` m, one LOD, maps at
    `density` texels/m, ground maps at half their density, no checks. The same code path as the export (so what it
    shows is what an export bakes), sized for rock design rounds: a tile or four in about a minute instead of a block
    export's 15+. Render it with `render_tiles(T, out_dir, views)`."""
    base = {**DEFAULTS, **((T.spec.get("export") or {}).get("tiles") or {}), **(cfg or {})}
    G = Grid(T, base)
    xy = np.asarray(at, float)[:2] if isinstance(at, (list, tuple)) else np.asarray(T.address(at)[0], float)
    lo = np.floor((xy - radius - G.origin) / G.tile).astype(int).clip(0, [G.ni - 1, G.nj - 1])
    hi = np.floor((xy + radius - G.origin) / G.tile).astype(int).clip(0, [G.ni - 1, G.nj - 1])
    c = {"only": [lo.tolist(), hi.tolist()], "lods": 1, "texel_density": [float(density)], "checks": False,
         "ground_density": 0.5 * float(base["ground_density"])}
    return export_tiles(T, out_dir, {**c, **(cfg or {})}, log)


def summary(r) -> str:
    """A short text report of an export_tiles result."""
    M = r["manifest"]
    what = "cliff mesh tiles" if M.get("mode") == "cliffs" else "3D tiles"
    lines = []
    fails = (r.get("check") or {}).get("failures") or []
    if fails:
        lines += [f"CHECKS FAILED ({len(fails)}). The export is COMPLETE on disk (every tile and manifest.json, whose "
                  "seam_check.failed repeats this list) and loads in an engine. Each failure names its tiles. Open "
                  "edges or shards in a \"buried\" primitive are under the heightmap (not seen); in \"surface\" they "
                  "show (black slivers, holes). A tile over its budget is a valid mesh, only heavy."]
        lines += [f"  FAILED: {f}" for f in fails[:30]]
        if len(fails) > 30:
            lines.append(f"  ... and {len(fails) - 30} more")
    lines += [f"{what} in {r['out']}: {M['grid'][0]} x {M['grid'][1]} tiles of {M['tile_size']:g} m"
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
    if "grid_squares" in sc:
        if "facet_periodicity" in sc:
            lines.append(f"facet periodicity (autocorrelation peak per plane orientation): {sc['facet_periodicity']}")
        lines.append(f"grid squares (colour kinks on cell lines vs between): x{sc['grid_squares']['ratio']}; texel "
                     "density " + ", ".join(f"{k} {v['min']:g}-{v['max']:g}/m (neighbours x{v['worst_neighbour_ratio']})"
                                            for k, v in sc.get("texel_density", {}).items()))
    sh = [f"LOD {k} {sc[f'lod{k}_shards']['area_pct']}%" for k in range(len(M["lods"])) if f"lod{k}_shards" in sc]
    if sh:
        lines.append("shards (corner normals against their face, share of the area): " + ", ".join(sh))
    lines.append("timing (s): " + ", ".join(f"{k} {v}" for k, v in M["timing_s"].items()))
    if M.get("memory_gb"):
        m = M["memory_gb"]
        lines.append(f"memory peak: {m['job_gb']} GB for the job (largest worker {m['worker_gb']} GB, parent "
                     f"{m['parent_gb']} GB); the machine's free memory never below {m['min_available_gb']} GB")
    return "\n".join(lines)


def _maps_done(manifest_tiles, stats, got):
    """Each textured tile LOD's GLB size and maps report (from _job_finish) into its manifest entry and stats."""
    for e in manifest_tiles:
        for k, L in enumerate(e["lods"]):
            if L and L["bytes"] is None:
                L["bytes"], extra = got[f"tile_{e['i']}_{e['j']}_lod{k}"]
                L["maps"] = {**extra, **L.get("maps", {})}
    for n_, st in enumerate(stats):
        if st[6] is None:
            stats[n_] = st[:6] + (got[f"tile_{st[0]}_{st[1]}_lod{st[2]}"][0],)


def _job_tile(ij):
    """Write one tile's LODs and collision (runs in a worker: everything it reads is in _CTX)."""
    i, j = ij
    c = _CTX
    G, v0, field, mats, cfg, out, vols = c["G"], c["v0"], c["field"], c["mats"], c["cfg"], c["out"], c["vols"]
    dense, collapsed, pos, depth, dirn = c["dense"], c["collapsed"], c["pos"], c["depth"], c["dirn"]
    CN, CW, CC, mat = c["CN"], c["CW"], c["CC"], c["mat"]
    stats, t_dec, wanted, wanted_bakes = [], 0.0, set(), []
    t_tile = time.time()
    lo, hi = G.bounds(i, j)
    trans = _to_gltf(np.array([[lo[0], lo[1], 0.0]]))[0]
    entry = {"i": i, "j": j, "min": [float(lo[0]), float(lo[1])], "max": [float(hi[0]), float(hi[1])], "lods": []}
    zmin, zmax = np.inf, -np.inf
    prevs = []
    # (a decimated mesh may only have canonical vertices on the tile's border planes)
    border_ok = lambda v: all(tuple(q) in pos for q in v[_on_border(v, lo, hi)])
    for k in range(G.lods):
        if (i, j) not in dense:
            entry["lods"].append(None)
            continue
        mark = profiling.snapshot()
        P, faces0, _ = _dense(c, (i, j))
        Fk = np.load(_work(c, "col", i, j, k))
        used = np.unique(Fk)
        remap = np.full(len(P), -1, np.int64)
        remap[used] = np.arange(len(used))
        Pk, Fk = P[used], remap[Fk]
        n_mc = len(faces0)
        td = time.time()
        _sp = _span(f"tile/lod{k}/decimate")
        _sp.__enter__()
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
                Pd, Fd = _decimate(Pp[used], remap[Fc], cfg["error"][k], cfg["budget"][k], field, border_ok)
                if len(Fd) > 1.15 * cfg["budget"][k] + 64:
                    Pd = Fd = None
        if Pd is None:
            if k > 0:
                profiling.count(f"decimate: lod{k} from the dense mesh (the last LOD's didn't reach its budget)")
                if os.environ.get("HIFIPUSHIE_DECIMATE_DUMP"):  # (the inputs, to replay a straggler offline)
                    Pp, Fp = prevs[-1]
                    np.savez(Path(os.environ["HIFIPUSHIE_DECIMATE_DUMP"]) / f"dec_{i}_{j}_{k}.npz", Pk=Pk, Fk=Fk,
                             Pp=Pp, Fp=Fp, keep=np.asarray(c["keep"][k]), lo=np.asarray(lo), hi=np.asarray(hi),
                             pos=np.array(list(pos.keys()), float), posv=np.array(list(pos.values())),
                             err=cfg["error"][k], budget=cfg["budget"][k])
            with _span(f"tile/lod{k}/decimate from dense"):
                # (a coarse LOD from the dense mesh: one pass to PRE x its budget first, LOD 0 as it always was)
                Pd, Fd = _decimate(Pk, Fk, cfg["error"][k], cfg["budget"][k], field, border_ok,
                                   pre=PRE * cfg["budget"][k] if k > 0 else None)
        if k > 0 and prevs and len(Fd) > max(cfg["budget"][k], len(prevs[-1][1])):
            # this LOD from the dense mesh folded at every count: from an earlier LOD's mesh instead (the last one
            # first), its border collapsed to this LOD's chain (the same chain either way: neighbours still agree)
            profiling.count(f"decimate: lod{k} retried from earlier LODs (the dense mesh folded at every count)")
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
                P2, F2 = _decimate(Pp[used], remap[Fc], cfg["error"][k], cfg["budget"][k], field, border_ok)
                if len(F2) < len(Fd):
                    Pd, Fd = P2, F2
                    break
        _sp.__exit__(None, None, None)
        t_dec += time.time() - td
        # border vertices must have come through untouched, and be this LOD's chain
        rowd = np.array([pos.get(tuple(p), -1) for p in Pd])
        on = _on_border(Pd, lo, hi)
        if np.any(on & (rowd < 0)):
            q = Pd[on & (rowd < 0)]
            inP = [bool(np.any(np.all(Pk == x, axis=1))) for x in q[:5]]
            be = np.unique(_boundary_edges(Fk)) if len(Fk) else np.zeros(0, np.int64)
            onb = [bool(np.any(np.all(Pk[be] == x, axis=1))) for x in q[:5]]
            raise RuntimeError(f"tile {i},{j} LOD {k}: {int(np.sum(on & (rowd < 0)))} border vertices moved in "
                               f"decimation, e.g. {q[:5].tolist()} (in the undecimated mesh: {inP}, on its open "
                               f"boundary: {onb})")
        bd = rowd >= 0
        N = np.zeros_like(Pd)
        before = Pd.copy()
        with _span(f"tile/lod{k}/project"):
            Pd[~bd], N[~bd] = project(field, Pd[~bd], v0)
        hn = NORMAL_H * v0
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
        with _span(f"tile/lod{k}/vertex weights"):
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
        with _span(f"tile/lod{k}/split normals + buried"):
            Ps, Fs, Ns, src = split_normals(Pd, Fd, N, field, bd, hn)
            bur = np.zeros(len(Fs), bool)
            if hasattr(field, "front"):
                # a cliff shell: faces off the visible rock (its back, buried under the heightmap) go in their own
                # primitive, so an engine or a bake can skip them
                # (off it at the centre, unless all three corners are on it: a big face across the turf's step or a
                # lip's crease has its centre 0.3 m+ off the rock with every corner on it; taken for buried, it was
                # drawn with the plain matte material: the pale flat triangles at cliff lips. A face with one corner
                # on the front is the back's edge where it meets it: still buried)
                thr = max(0.3, 2 * cfg["error"][k])
                bur = (np.abs(field.front(Ps[Fs].mean(1))) > thr) & (np.abs(field.front(Ps))[Fs].max(1) > thr)
        stem = f"tile_{i}_{j}_lod{k}"
        from .terrain_bake import material as terrain_bake_material
        images, binfo, deferred = None, None, None
        if cfg.get("maps") and (~bur).any():
            Pv, Nv, Cv, Wv, Fv = _compact(Ps, Ns, C[src], W[src], Fs[~bur])
            with _span(f"tile/lod{k}/maps prep"):
                prim, binfo, deferred = _textured_prep(Pv, Nv, Wv, Fv, k, origin, stem)
            prims = [prim]
        else:
            prims = [_prim(*_compact(Ps - origin, Ns, C[src], W[src], Fs[~bur]), 0, {"role": "surface"}, mats, lo, cfg)]
        tile_mats = mat + ([terrain_bake_material("terrain_baked")] if (cfg.get("maps") and (~bur).any()) else [])
        if bur.any():
            # (its own material name: an importer that drops extras, Godot's, saw the back as a second skirt surface)
            tile_mats = tile_mats + [{**mat[0], "name": "terrain_buried"}]
            prims.append(_prim(*_compact(Ps - origin, Ns, C[src], W[src], Fs[bur]), len(tile_mats) - 1,
                               {"role": "buried"}, mats, lo, cfg))
        if len(sf):
            prims.append(_prim(SP - origin, SN, SC, SW, sf, 1, {"role": "skirt"}, mats, lo, cfg))
        for pr in prims[1:]:  # (custom attributes on every primitive: Blender's importer can't merge them otherwise)
            for key in ("_DETAIL",):
                if key in prims[0]["attrs"] and key not in pr["attrs"]:
                    pr["attrs"][key] = np.zeros((len(pr["attrs"]["POSITION"]), prims[0]["attrs"][key].shape[1]))
        fn = f"{stem}.glb"
        glb = dict(path=out / fn, name=stem, prims=prims, trans=trans, mats=tile_mats,
                   extras={"tile": [i, j], "lod": k, "error_m": cfg["error"][k]})
        if deferred:  # (written by _job_finish once its texels are baked)
            import pickle
            with open(c["work"] / f"glb_{stem}.pkl", "wb") as fh:
                pickle.dump(glb, fh, protocol=pickle.HIGHEST_PROTOCOL)
            wanted_bakes.append(deferred)
        else:
            with _span(f"tile/lod{k}/write glb"):
                write_glb(glb["path"], stem, prims, trans, glb["mats"], extras=glb["extras"], images=images)
        if k == int(cfg["collision"]):
            cf = f"collision_{i}_{j}.glb"
            Pc, Fc = _collision_mesh(Pd, Fd, int(cfg.get("collision_budget") or OVER_BUDGET * cfg["budget"][k]))
            write_glb(out / cf, f"collision_{i}_{j}", [{"attrs": {"POSITION": _to_gltf(Pc - origin)},
                                                        "indices": Fc}], trans, None,
                      extras={"tile": [i, j], "collision": True, "from_lod": k})
            entry["collision"] = cf
            entry["collision_triangles"] = int(len(Fc))
        zmin, zmax = min(zmin, float(Pd[:, 2].min())), max(zmax, float(Pd[:, 2].max()))
        size_ = None if deferred else (out / fn).stat().st_size
        entry["lods"].append({"file": fn, "triangles": int(len(Fd)), "skirt_triangles": int(len(sf)),
                              "visible_triangles": int((~bur).sum()),
                              "marching_cubes_triangles": int(n_mc), "bytes": size_})
        if binfo:
            entry["lods"][-1]["maps"] = binfo
        entry["lods"][-1]["timing_s"] = _since(mark)
        stats.append((i, j, k, len(Fd), len(sf), n_mc, size_))
    entry["zmin"], entry["zmax"] = zmin, zmax
    entry["seconds"] = round(time.time() - t_tile, 1)
    entry["volumes"] = sorted({vol.name.split(":")[0] for vol in vols
                               if vol.touches(np.array([lo[0], lo[1], -1e9]), np.array([hi[0], hi[1], 1e9]))})
    entry["_bakes"] = wanted_bakes
    return entry, stats, t_dec, wanted


def _collision_mesh(P, F, budget):
    """A LOD's mesh for collision: as it is when within `budget` triangles, else decimated to it (pyfqmr, open borders
    kept; no fold or seam checks: physics doesn't shade, and a half-million-face trimesh for one 64 m tile is what an
    engine got when a LOD missed its budget)."""
    if len(F) <= budget:
        return P, F
    import pyfqmr
    s = pyfqmr.Simplify()
    s.setMesh(np.ascontiguousarray(P, float), np.ascontiguousarray(F, np.int64))
    s.simplify_mesh(target_count=int(budget), aggressiveness=7, max_iterations=300, preserve_border=True,
                    verbose=False)
    v, f, _ = s.getMesh()
    v, f = np.asarray(v, float), np.asarray(f, np.int64)
    return (v, f) if 0 < len(f) < len(F) else (P, F)


def _since(mark, min_s=0.05):
    """The spans (seconds, rounded) and field-point counts run since `mark` (a profiling.snapshot)."""
    now = profiling.snapshot()
    out = {}
    for k, (t, _) in now["spans"].items():
        d = t - mark["spans"].get(k, [0.0, 0])[0]
        if d >= min_s:
            out[k.split("/")[-1] if k.startswith("tile/") else k] = round(d, 2)
    n = now["counts"].get("field.solid pts", 0) - mark["counts"].get("field.solid pts", 0)
    if n:
        out["field points"] = int(n)
    return out


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


def _textured_prep(P, N, W, F, k, origin, stem):
    """A tile LOD's visible surface with its own UV atlas (terrain_bake): the primitive (material 2, the baked reference
    material), a partial report, and a bake request ({"stem", "k", "n" texels}). Its texels, AO and atlas go to the
    work dir; `_job_bake` bakes the texels in pieces across the pool and `_job_finish` assembles the maps (base colour,
    ORM, normal embedded; height and layer-weight maps beside the GLB in maps/) and writes the GLB."""
    from . import terrain_bake
    c = _CTX
    cfg, v0 = c["cfg"], c["v0"]
    dens = cfg["_density"][min(k, len(cfg["_density"]) - 1)]
    with _span("maps/unwrap"):
        uvc, size, d, _ = terrain_bake.unwrap(P, F, dens, int(cfg["texture_max"]))
    D = c.get("detail")
    with _span("maps/tangents"):
        bins = np.repeat(D.face_bins(P, F)[:, None], 3, 1) if D is not None else None
        sp = terrain_bake.split_corners(P, _unit_rows(N), F, uvc, extra={"W": W}, ids=bins)
        T4 = terrain_bake.tangents(sp["P"], sp["N"], sp["uv"], sp["F"])
    with _span("maps/texels"):
        tx = terrain_bake.texels(sp["uv"], sp["F"], size)
        # texels in space-filling-curve order of where they land (every map value is per texel, so the order is free):
        # a bake piece then covers a compact patch of rock, and its facet triangulations (terrain_facets, cached per
        # process) are few and reused; in atlas order every piece touched the whole tile
        bary = terrain_bake._bary(sp["uv"], sp["F"], tx["size"], tx["t"], tx["xs"], tx["ys"])
        o = _morton(np.einsum("nk,nkc->nc", bary, sp["P"][sp["F"][tx["t"]]]), 2.0)
        for key in ("ys", "xs", "t", "inside"):
            tx[key] = tx[key][o]
    ao_v = terrain_bake.bake_ao(c["base"], sp["P"], sp["N"])
    info = {}
    if k == 0:  # how well the triangles follow the rock's creases (terrain_sharp.crease_error)
        fn_ = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
        rock = fn_[:, 2] / np.maximum(np.linalg.norm(fn_, axis=1), 1e-12) < math.cos(math.radians(40))
        if rock.sum() > 16:
            with _span("maps/crease error"):
                info["crease"] = terrain_sharp.crease_error(P, F, c["field"], max(0.01, v0 / 32), rock=rock)
    np.savez(c["work"] / f"bake_{stem}.npz", P=sp["P"], N=sp["N"], T4=T4, uv=sp["uv"], F=sp["F"], ao=ao_v,
             size=np.array(tx["size"]), ys=tx["ys"].astype(np.int32), xs=tx["xs"].astype(np.int32), t=tx["t"],
             inside=tx["inside"], fill=np.array(tx["fill_pct"]))
    attrs = {"POSITION": _to_gltf(sp["P"] - origin), "NORMAL": _to_gltf(sp["N"]),
             "TANGENT": np.c_[_to_gltf(T4[:, :3]), T4[:, 3]], "TEXCOORD_0": sp["uv"]}
    sq = int(cfg["splat"])
    if sq:
        mg = int(cfg["splat_margin"])
        Nn = sq + 2 * mg
        Q = sp["P"] - origin
        attrs["TEXCOORD_1"] = np.c_[(Q[:, 0] / cfg["tile"] * sq + mg) / Nn, 1 - (Q[:, 1] / cfg["tile"] * sq + mg) / Nn]
    if D is not None:  # the tiling detail's projection (terrain_swatch.DetailProjection)
        with _span("maps/detail projection"):
            attrs[f"TEXCOORD_{1 + bool(sq)}"] = D.uv(sp["P"], sp["ids"])
            attrs["_DETAIL"] = D.attrs(sp["P"])
    Wv = sp["W"]
    for g in range(0, Wv.shape[1], 4):
        w = Wv[:, g:g + 4]
        attrs[f"_WEIGHTS{g // 4}"] = np.c_[w, np.zeros((len(w), 4 - w.shape[1]))]
    info.update(size=[int(size[0]), int(size[1])], texels_per_m=round(float(d), 2), height=f"maps/{stem}_height.png")
    return ({"attrs": attrs, "indices": sp["F"], "material": 2, "extras": {"role": "surface"}}, info,
            {"stem": stem, "k": k, "n": int(len(tx["t"]))})


def _morton(X, cell):
    """An order of points X (n, 3) along a Z-order curve over cells `cell` m across."""
    q = np.floor((X - X.min(0)) / cell).astype(np.int64)
    key = np.zeros(len(X), np.int64)
    for bit in range(20):
        for a in range(3):
            key |= ((q[:, a] >> bit) & 1) << (3 * bit + a)
    return np.argsort(key, kind="stable")


LIGHTS = {  # render_tiles(light=...) presets: the sky's dust/air (Nishita), sun watts, sky strength, exposure
    "hazy": {"dust": 0.3, "air": 0.8, "sun_energy": 2.4, "sky_strength": 0.12, "exposure": 0.0},
    # matched to a clear sunny photo (the Pebble 7th): its sky deep blue (v ~0.75 s ~0.45 at the top), crisp shadows
    # exposure metered on the sun's height (`meter` stops per doubling of sin(height) over 25 deg)
    "clear": {"dust": 0.02, "air": 1.0, "sun_energy": 3.2, "sky_strength": 0.08, "exposure": -0.35, "meter": 0.8,
              # the sky as the camera sees it, deeper (camera and glossy rays only: the light it casts is unchanged), and
              # the sea a deep blue body with water's IOR (measured against the photo: the sea there h 212 s 0.45-0.49)
              "sky_sat": 1.3, "sky_value": 1.12, "sky_horizon_tint": [0.5, 0.72, 1.0],
              "water": [0.006, 0.028, 0.065], "water_roughness": 0.12,
              "haze_scale": 3.0},  # (clear air: the photo's sea stays deep blue to the horizon, 3 km off)
}


def _light(light):
    """A light preset's settings (render_tiles(light=)): a LIGHTS name, a dict, or {} for none."""
    if isinstance(light, str):
        return LIGHTS.get(light, {})
    return light or {}


RELIEF_CHART = 2.5  # the ground's maps-only relief on cliff tiles is band-limited as if their texel were this x larger:
# their charts' texel grids don't line up across a tile border (ground tiles' do), so fine relief differed there
BAKE_PIECE = 120_000  # texels per bake job (a 64 m tile's LOD 0 atlas at 13-16 texels/m is 1.2-2.6M: 10-20 jobs)


def _job_bake(args):
    """One piece of a tile LOD's atlas: texels [a, b) baked (terrain_bake.bake_texels), saved for _job_finish."""
    from . import terrain_bake
    stem, k, a, b = args
    c = _CTX
    d = np.load(c["work"] / f"bake_{stem}.npz")
    reach = max(0.6, 4 * c["cfg"]["error"][k] + 0.5)
    bf = c["bakefield"][k]
    surface = lambda Pl, Nl: terrain_bake._surface(bf, Pl, Nl, c["v0"], reach)
    lines = None
    if c.get("detail") is not None and c["cfg"].get("lines", True):
        from . import terrain_swatch
        tx_ = 1.0 / c["cfg"]["_density"][min(k, len(c["cfg"]["_density"]) - 1)]
        lines = lambda Pl, Nl: terrain_swatch.structure_lines(c["base"], Pl, tx_, N=Nl)
    vals = terrain_bake.bake_texels(surface, c["mats"], d["P"], d["N"], d["T4"], d["uv"], d["F"], tuple(d["size"]),
                                    d["t"][a:b], d["xs"][a:b], d["ys"][a:b], d["inside"][a:b], c["layer_rough"],
                                    bf, first=a, gfield=c.get("weightfield"), lines=lines,
                                    texel=RELIEF_CHART / c["cfg"]["_density"][min(k, len(c["cfg"]["_density"]) - 1)])
    np.savez(c["work"] / f"baked_{stem}_{a:09d}.npz", **vals)

def _job_finish(stem):
    """A tile LOD's maps assembled from its baked pieces, and its GLB written. Returns (bytes, the maps report)."""
    import pickle
    from PIL import Image
    from . import terrain_bake
    c = _CTX
    out, work = c["out"], c["work"]
    d = np.load(work / f"bake_{stem}.npz")
    tx = {"size": tuple(int(x) for x in d["size"]), "ys": d["ys"], "xs": d["xs"], "t": d["t"], "inside": d["inside"],
          "fill_pct": float(d["fill"])}
    pieces = sorted(work.glob(f"baked_{stem}_*.npz"))
    vals = terrain_bake.concat([dict(np.load(f)) for f in pieces])
    maps, info = terrain_bake.assemble(tx, vals, d["ao"], d["uv"], d["F"])
    with _span("maps/encode + save"):
        (out / "maps").mkdir(exist_ok=True)
        Image.fromarray(maps["height"], "I;16").save(out / "maps" / f"{stem}_height.png")
        wfiles = []
        for g, w in enumerate(maps["weights"]):
            fn = f"maps/{stem}_weights{g}.png"
            Image.fromarray(w, "RGBA").save(out / fn)
            wfiles.append(fn)
        if "lines" in maps:
            Image.fromarray(maps["lines"], "RGBA").save(out / "maps" / f"{stem}_lines.png")
            info["lines"] = f"maps/{stem}_lines.png"
        images = [(terrain_bake.jpeg(maps["basecolor"]), "image/jpeg"),
                  (terrain_bake.png(maps["orm"], "RGB"), "image/png"),
                  (terrain_bake.png(maps["normal"], "RGB"), "image/png")]
    with open(work / f"glb_{stem}.pkl", "rb") as fh:
        glb = pickle.load(fh)
    de = c.get("detail_entry")
    if de is not None:  # the detail layer in the GLB: the lines map embedded, the swatches as files beside it
        ext = {"recipe": "manifest.json detail.recipe", "texCoord_detail": de["texcoord"],
               "attribute": "_DETAIL (strike x, strike y, side share, bed coordinate m)", "size_m": de["size_m"]}
        if "lines" in maps:
            images.append((terrain_bake.png(maps["lines"], "RGBA"), "image/png"))
            ext["lines"] = {"index": len(images) - 1, "texCoord": 0, "range_m": de["line_d"],
                            "channels": "R bed planes, G joints: signed distance (0.5 = on the line, +-range_m); "
                                        "B, A: their strengths"}
        for key in ("albedo", "normal", "rough", "variation"):
            images.append(de[key])
            ext[key] = {"index": len(images) - 1, "texCoord": de["texcoord"]}
        glb["mats"] = [dict(m) for m in glb["mats"]]
        [m for m in glb["mats"] if m["name"] == "terrain_baked"][0]["extras"] = {"hifipushie_detail": ext}
    with _span("maps/write glb"):
        write_glb(glb["path"], glb["name"], glb["prims"], glb["trans"], glb["mats"], extras=glb["extras"],
                  images=images)
    if os.environ.get("HIFIPUSHIE_KEEP_BAKE"):  # (debug: each atlas's texels kept in <out>/_bakes, to re-bake one map
        # alone with terrain_bake.bake_lines while trying line variants)
        (out / "_bakes").mkdir(exist_ok=True)
        import shutil
        shutil.copy(work / f"bake_{stem}.npz", out / "_bakes" / f"bake_{stem}.npz")
    for f in pieces + [work / f"bake_{stem}.npz", work / f"glb_{stem}.pkl"]:
        f.unlink()
    info["weights"] = wfiles
    return glb["path"].stat().st_size, info


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

def seam_check(out_dir, normal_deg=1.0, memo=None) -> dict:
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
            d["_roles"] = np.zeros(len(d["surface"][2]) if "surface" in d else 0, np.int8)
            if "buried" in d:  # (a cliff shell's back: part of the mesh's structure, not of what is seen)
                empty = (np.zeros((0, 3)), np.zeros((0, 3)), np.zeros((0, 3), np.int64))
                d["visible"] = d.get("surface", empty)
                (P1, N1, F1), (P2, N2, F2) = d["visible"], d.pop("buried")
                d["surface"] = (np.vstack([P1, P2]), np.vstack([N1, N2]), np.vstack([F1, F2 + len(P1)]))
                d["_roles"] = np.r_[np.zeros(len(F1), np.int8), np.ones(len(F2), np.int8)]
            data[i, j, k] = d
    # (2) watertight per LOD
    for k in range(lods):
        allP, allF, off, ftile, frole = [], [], 0, [], []
        for (i, j) in tiles:
            if (i, j, k) not in data:
                continue
            P, _, F = data[i, j, k]["surface"]
            allP.append(P)
            allF.append(F + off)
            ftile.append(np.tile([i, j], (len(F), 1)))
            frole.append(data[i, j, k]["_roles"])
            off += len(P)
        P = np.vstack(allP)
        F = np.vstack(allF)
        ftile, frole = np.vstack(ftile), np.concatenate(frole)
        _, uid = np.unique(P, axis=0, return_inverse=True)
        F = uid.ravel()[F]
        ok3 = (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])
        F, ftile, frole = F[ok3], ftile[ok3], frole[ok3]
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
        if sh["faces"]:  # (which tiles: a designer can't tell a feature from a world point)
            per = [((i, j), _shards([data[i, j, k].get("visible", data[i, j, k]["surface"])]))
                   for (i, j) in tiles if (i, j, k) in data]
            per = sorted(((q["area_m2"], q["faces"], ij) for ij, q in per if q["faces"]), reverse=True)[:6]
            sh["tiles"] = [{"tile": list(ij), "faces": n_, "area_m2": a_} for a_, n_, ij in per]
        summary[f"lod{k}_shards"] = sh
        if sh["area_pct"] > SHARD_LIMIT[min(k, len(SHARD_LIMIT) - 1)]:
            failures.append(f"LOD {k}: {sh['faces']} faces ({sh['area_pct']}% of the visible area, limit "
                            f"{SHARD_LIMIT[min(k, len(SHARD_LIMIT) - 1)]}%) with corner normals "
                            f"against the face: black shards (e.g. at {sh['at'][:3]}; most in tiles "
                            + ", ".join(f"{q['tile'][0]},{q['tile'][1]} ({q['faces']})" for q in sh["tiles"][:4]) + ")")
        if open_inside or nonman or dup_dir:
            bad = np.r_[a[~at_edge], u[cnt > 2] // nmax, fu[fcnt > 1] // nmax]
            ex = Pu[bad[:3]].round(2).tolist()
            # (which tiles and primitives the bad edges' faces are in: an edge's faces, by its undirected key)
            bad_keys = np.r_[single[~at_edge], u[cnt > 2], np.minimum(fu[fcnt > 1], (fu[fcnt > 1] % nmax) * nmax
                                                                       + fu[fcnt > 1] // nmax)]
            fe = np.tile(np.arange(len(F)), 3)
            hit = fe[np.isin(und, bad_keys[:20])]
            where = sorted({(int(ftile[f][0]), int(ftile[f][1]), ("surface", "buried")[int(frole[f])]) for f in hit})
            failures.append(f"LOD {k}: {open_inside} open edges inside the world, {nonman} non-manifold, "
                            f"{dup_dir} doubled directed edges (e.g. at {ex}; tiles/primitives {where[:6]})")
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
        ms = map_seams(out, M["tiles"], lods, memo=memo)
        summary["map_seams"] = ms
        for key, r in ms.items():
            if not r["ok"]:
                failures.append(f"{key}: baked maps differ across tile borders in {r['bad']}: "
                                + ", ".join(f"{c} p50/p95 {r[c]}" for c in r["bad"]))
    summary["failures"] = len(failures)
    (out / "seam_check.json").write_text(json.dumps({"summary": summary, "failures": failures}, indent=1))
    return {"summary": summary, "failures": failures}


def read_glb_images(path, n=None):
    """The images embedded in a GLB, decoded (float arrays 0..1, rows top first), in texture order (the first `n`)."""
    import io
    from PIL import Image
    b = Path(path).read_bytes()
    jl = struct.unpack_from("<I", b, 12)[0]
    doc = json.loads(b[20:20 + jl])
    binb = b[28 + jl:]
    out = []
    for im in doc.get("images", [])[:n]:
        if "bufferView" not in im:  # (a file beside the GLB: the detail swatches)
            out.append(None)
            continue
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


def _map_side(out, L, ax, lim):
    """Along a tile's border plane: points on its border edges (a quarter, half, three quarters along each) with what
    its maps say there: the normal decoded to world axes (through the tile's NORMAL/TANGENT: MikkTSpace-style, as
    engines recompute them), base colour, occlusion, roughness, the height map in metres and the layer weights.
    Returns (points (n, 3), {channel: (n, k)})."""
    return _map_sides(out, L, [(ax, lim)])[ax, lim]


def _map_files(L):
    mp = L.get("maps") or {}
    return [L["file"]] + ([mp["height"]] if mp.get("height") else []) + list(mp.get("weights", []))


def _map_sides(out, L, planes):
    """`_map_side` on several border planes of one tile LOD, its maps decoded once: {(ax, lim): (points, channels)}."""
    from PIL import Image
    path = out / L["file"]
    tr, prims = read_glb(path)
    p = prims[0]
    none = {pl: (np.zeros((0, 3)), {}) for pl in planes}
    if "TEXCOORD_0" not in p:
        return none
    imgs = read_glb_images(path, 3)
    if len(imgs) < 3:
        return none
    mp = L.get("maps") or {}
    hi = np.asarray(Image.open(out / mp["height"]), float) / 65535.0 if mp.get("height") else None
    wimgs = [np.asarray(Image.open(out / fn), float) / 255.0 for fn in mp.get("weights", [])]
    return {(ax, lim): _map_plane(p, tr, imgs, hi, wimgs, mp, ax, lim) for ax, lim in planes}


def _map_plane(p, tr, imgs, hi, wimgs, mp, ax, lim):
    origin = _from_gltf(tr[None])[0]
    P = _from_gltf(p["POSITION"].astype(np.float64)) + origin
    N = _from_gltf(p["NORMAL"].astype(np.float64))
    T = _from_gltf(p["TANGENT"][:, :3].astype(np.float64))
    w = p["TANGENT"][:, 3].astype(np.float64)
    uv = p["TEXCOORD_0"].astype(np.float64)
    be = _boundary_edges(p["indices"])
    be = be[(P[be[:, 0], ax] == lim) & (P[be[:, 1], ax] == lim)]
    if not len(be):
        return np.zeros((0, 3)), {}
    # (each edge's ends in a canonical order, so both tiles sample the same points)
    swap = np.array([tuple(P[a]) > tuple(P[b]) for a, b in be])
    a_, b_ = np.where(swap, be[:, 1], be[:, 0]), np.where(swap, be[:, 0], be[:, 1])
    t = np.repeat(np.array([[0.25, 0.5, 0.75]]), len(be), 0).ravel()[:, None]
    a_, b_ = np.repeat(a_, 3), np.repeat(b_, 3)
    lerp = lambda A: A[a_] * (1 - t) + A[b_] * t
    X = lerp(P)
    Nl = _unit_rows(lerp(N))
    Tl = lerp(T)
    Tl = _unit_rows(Tl - Nl * (Tl * Nl).sum(1, keepdims=True))
    Bl = np.cross(Nl, Tl) * np.sign(w[a_])[:, None]
    q = lerp(uv)
    tn = _bilinear(imgs[2], q)[:, :3] * 2 - 1
    ch = {"normal": _unit_rows(tn[:, :1] * Tl + tn[:, 1:2] * Bl + tn[:, 2:3] * Nl),
          "colour": _bilinear(imgs[0], q)[:, :3], "orm": _bilinear(imgs[1], q)[:, :2]}
    if hi is not None:
        ch["height_m"] = ((_bilinear(hi[..., None], q)[:, 0] - 0.5) * 2 * mp["height_range_m"])[:, None]
    for g, w in enumerate(wimgs):
        ch[f"weights{g}"] = _bilinear(w, q)
    return X, ch


def _job_sides(a):
    out, L, planes = a
    return _map_sides(out, L, planes)


def _side_pool(todo):
    """`_map_sides` of each (key, files key, args) across a fork pool (decoding the maps was 80% of the checks)."""
    from . import resources
    if len(todo) <= 2:
        return [_job_sides(t[2]) for t in todo]
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor
    ex = ProcessPoolExecutor(max_workers=resources.workers(1.0, cap=16, jobs=len(todo)),
                             mp_context=multiprocessing.get_context("fork"), initializer=resources._worker_init)
    with resources.guarded(ex, "map seams") as ex:
        return list(ex.map(_job_sides, [t[2] for t in todo], chunksize=2))


def map_seams(out, tiles, lods, kind="tiles", memo=None):
    """Baked maps across shared tile borders: every channel decoded from both tiles at the same border points (same
    LOD) and, for mixed LODs (0 against the coarsest), at the nearest point of the other tile's border within 0.6 m.
    Per pair: normals (deg), colour, occlusion, roughness, weights (0..1) and height (m) differences, p50/p95.
    Each tile LOD's maps are decoded once for all its borders, across a pool; `memo` (terrain_incremental.Memo)
    keeps each side's samples by its files' content, so an incremental export decodes only the tiles it rewrote."""
    from scipy.spatial import cKDTree
    from . import terrain_incremental as inc
    res = {}
    by = {(e["i"], e["j"]): e for e in tiles}
    pairs = [(k, k) for k in range(lods)] + ([(0, lods - 1)] if lods > 1 else [])
    need = {}
    for ka, kb in pairs:
        for (i, j), e in by.items():
            for di, dj, ax in ((1, 0, 0), (0, 1, 1)):
                o = by.get((i + di, j + dj))
                if o is None or not e["lods"][ka] or not o["lods"][kb]:
                    continue
                lim = e["max"][ax]
                need.setdefault((i, j, ka), set()).add((ax, lim))
                need.setdefault((i + di, j + dj, kb), set()).add((ax, lim))
    cache, todo = {}, []
    for (i, j, k), planes in need.items():
        L = by[i, j]["lods"][k]
        fk = inc.files_key(out, _map_files(L)) if memo is not None else None
        miss = []
        for pl in sorted(planes):
            got = memo.get(inc._h("map side", fk, pl)) if memo is not None else None
            if got is None:
                miss.append(pl)
            else:
                cache[(i, j, k) + pl] = got
        if miss:
            todo.append(((i, j, k), fk, (out, L, miss)))
    if todo:
        got_all = _side_pool(todo)
        for ((i, j, k), fk, _), got in zip(todo, got_all):
            for pl, v in got.items():
                cache[(i, j, k) + pl] = v
                if memo is not None:
                    memo.put(inc._h("map side", fk, pl), v)

    def side(e, k, ax, lim):
        return cache[e["i"], e["j"], k, ax, lim]

    for ka, kb in pairs:
        diffs = {}
        for (i, j), e in by.items():
            for di, dj, ax in ((1, 0, 0), (0, 1, 1)):
                o = by.get((i + di, j + dj))
                if o is None or not e["lods"][ka] or not o["lods"][kb]:
                    continue
                lim = e["max"][ax]
                XA, A = side(e, ka, ax, lim)
                XB, B = side(o, kb, ax, lim)
                if not len(XA) or not len(XB):
                    continue
                d, nb = cKDTree(XB).query(XA)
                m = d < (1e-6 if ka == kb else 0.6)
                if not m.any():
                    continue
                for c in sorted(A.keys() & B.keys()):  # (sorted: a set of names iterates in hash order, run to run)
                    va, vb = A[c][m], B[c][nb[m]]
                    if c == "normal":
                        v = np.degrees(np.arccos(np.clip((va * vb).sum(1), -1, 1)))
                    else:
                        v = np.abs(va - vb).max(1)
                    diffs.setdefault(c, []).append(v)
        if not diffs:
            continue
        name = f"lod{ka}" if ka == kb else f"lod{ka}_vs_lod{kb}"
        lim = MAP_SEAM[min(max(ka, kb), len(MAP_SEAM) - 1)]
        r = {"points": int(sum(len(v) for v in diffs["normal"]))}
        for c, vs in diffs.items():
            v = np.concatenate(vs)
            r[c] = [round(float(np.percentile(v, 50)), 3), round(float(np.percentile(v, 95)), 3)]
        bad = []
        if r["normal"][0] > lim["normal"][0] or r["normal"][1] > lim["normal"][1]:
            bad.append("normal")
        # (mixed LODs: height is measured from each LOD's own low poly, so it differs by design; occlusion is
        # interpolated over triangles of different sizes and gets a looser limit)
        for c in ("colour", "orm") + (("height_m",) if ka == kb else ()) + tuple(c for c in r if c.startswith("weights")):
            if c in r and r[c][1] > lim[c if c in lim else "weights"] * (1.0 if ka == kb or c != "orm" else 1.4):
                bad.append(c)
        r["ok"] = not bad
        r["bad"] = bad
        res[name] = r
    return res


SHARD_LIMIT = [0.01, 0.05, 0.5]  # % of a LOD's area allowed to have corner normals against its faces
# the same border point decoded from both tiles' maps (each samples its own texels, 8-bit, bilinear): normals p50 and
# p95 (deg) and colour p95 (0..1) allowed, per LOD. A seam would shift the median; a few aliased texels at sharp
# detail don't. LOD 2 (0.4 m texels on a mesh 0.5 m off the rock) is looser: where its triangles stray far from the
# rock's normal the map can't bend past its surface (z >= 0.02) and the two sides clamp differently
MAP_SEAM = [
    {"normal": (3.0, 15.0), "colour": 0.08, "orm": 0.08, "height_m": 0.03, "weights": 0.1},
    {"normal": (3.0, 15.0), "colour": 0.12, "orm": 0.1, "height_m": 0.06, "weights": 0.15},
    {"normal": (6.0, 50.0), "colour": 0.2, "orm": 0.15, "height_m": 0.15, "weights": 0.25},
]


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



def _site_props(T, box=None):
    """The sites' props for render_tiles' stand-ins: [x, y, ground z, yaw, name] (inside `box` if given)."""
    out = []
    for st in getattr(T, "sites", {}).values():
        pr = st.get("prop")
        if not pr:
            continue
        x, y = map(float, st["xy"])
        if box and not (box[0][0] <= x <= box[1][0] and box[0][1] <= y <= box[1][1]):
            continue
        out.append([x, y, float(T.height(np.array([x, y]))), float(pr.get("yaw", 0.0)), str(pr["name"])])
    return out

def render_tiles(T, out_dir, views, lod=0, size=(1400, 800), samples=48, trees=True, box=None, skirt_color=None,
                 parts="all", textured=True, channel=None, ids=False, detail_fade=True, detail_show=None, haze=5000.0,
                 props=True, clutter=120.0, grade=None, light=None, grass=True):
    """Cycles renders of the written tiles, imported by Blender's glTF importer. views: {"name", "eye": address |
    [x, y] | [x, y, z], "lift" (m above the ground or the sea), "look": address | [x, y, z], "fov", "sun": [bearing,
    height], "borders": bool, "lamp": watts (a headlamp at the eye, for inside caves), "out"}. box: [[x0, y0],
    [x1, y1]]: only tiles (and trees) inside. lod: a level, or
    "checker" (LOD 0 and the coarsest alternating, to see the skirts at work). parts (cliffs mode): "all", "ground"
    (the heightmap alone: what a game shows without the overlay) or "cliffs". textured: True (the baked material),
    "layered" (the engine recipe: tiling layers over the baked maps), "detail" (the tiling rock detail over the baked
    macro maps, as the manifest's detail recipe draws it: needs an export with cfg detail) or False (vertex colour). channel: one baked
    channel alone ("base", "ao": unlit; "normal": the normal map on flat grey; "clay": geometry only). ids: also an id
    pass per view (<out>_ids.npy: glb index + 1, chart, view distance) for `terrain_seams.measure`; the job's "glbs"
    and "kinds" say which file each index is. A view's "sun" may be [bearing, height], a word terrain_sun knows, or
    "auto" / left out (terrain_sun picks a raking sun for what the view sees; the choice is noted in render_job.json).
    haze: aerial perspective, metres for 63% (None/0: off). props: placeholder buildings, tee pads and baskets on the
    sites (the export's meta), for scale. clutter: metres round each eye where ground clutter placeholders stand
    (terrain_ground.clutter: bushes on the scrub, tussocks and tall grass in rough grass, boulders on the shore;
    0/None: none). grade: a view transform look ("AgX - Punchy"). light: a preset name from LIGHTS ("clear": a deep
    blue clear sky and a strong sun, like a sunny photo) or {"dust", "air", "sun_energy", "sky_strength",
    "exposure"}; default the hazy sky every earlier round was judged under. grass=False leaves the turf's tiling
    detail out (to tell what it adds)."""
    import subprocess
    out = Path(out_dir)
    M = json.loads((out / "manifest.json").read_text())
    glbs, kinds = [], []
    for e in M["tiles"] * (parts != "ground") + M.get("ground", []) * (parts != "cliffs"):
        if box and (e["max"][0] < box[0][0] or e["min"][0] > box[1][0] or e["max"][1] < box[0][1]
                    or e["min"][1] > box[1][1]):
            continue
        k = (len(M["lods"]) - 1) * ((e["i"] + e["j"]) % 2) if lod == "checker" else lod  # mixed LODs: seams show
        if e["lods"][k]:
            glbs.append(str(out / e["lods"][k]["file"]))
            kinds.append(["ground" if e["lods"][k]["file"].startswith("ground") else "cliff", e["i"], e["j"], k])
    jobs, notes = [], []
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
        sun = v.get("sun", "auto")
        if not (isinstance(sun, (list, tuple)) and len(sun) == 2):
            from . import terrain_sun
            sb, sh, snote = terrain_sun.for_view(T, {**v, "sun": sun}, eye, look)
            sun = [float(sb), float(sh)]
            notes.append(f"{Path(v['out']).name}: {snote}")
        jobs.append({"eye": eye, "look": look, "fov": v.get("fov", 55), "sun": list(map(float, sun)),
                     "lamp": v.get("lamp", 0.0), "exposure": v.get("exposure", 0.0), "fill": v.get("fill", 0.4),
                     "fill_at": v.get("fill_at", 8.0),
                     "borders": v.get("borders", False), "out": str(Path(v["out"]).resolve())})
    job = {"glbs": glbs, "sea": sea, "size": list(size), "samples": samples, "views": jobs,
           "trees": str(out / "trees.csv") if trees else None, "tree_box": box, "skirt_color": skirt_color,
           "textured": bool(textured), "channel": channel, "ids": bool(ids), "kinds": kinds,
           "haze": (float(haze) * float(_light(light).get("haze_scale", 1.0))) if haze else None, "notes": notes,
           "props": _site_props(T, box) if props else [], "grade": grade,
           "light": LIGHTS.get(light, light) if isinstance(light, str) else light}
    if textured == "layered":  # the engine recipe: tiling layers over the baked maps
        job["layers"] = [{"path": str((out / L["textures"]["height"]).resolve()), "scale": L["scale"],
                          "strength": L["textures"]["detail_strength"], "attr": L["weights"], "channel": L["channel"]}
                         for L in M["materials"]["layers"] if "textures" in L]
    if textured == "detail":  # the tiling rock detail (terrain_swatch) over the baked macro maps
        D = M.get("detail")
        if not D:
            raise ValueError("textured='detail' needs an export with the detail layer (cfg detail: true)")
        rock = [(L["weights"], L["channel"]) for L in M["materials"]["layers"] if L["name"] in D["layers"]]
        job["detail"] = {"uv": "UVMap" + (f".{D['texcoord']:03d}" if D["texcoord"] else ""), "size": D["size_m"],
                         "albedo": str((out / D["albedo"]).resolve()), "normal": str((out / D["normal"]).resolve()),
                         "height": str((out / D["height"]).resolve()), "height_m": D["height_m"], "rock": rock,
                         "bins": D["bins"], "line_d": D.get("line_d", 0.5),
                         "variation": str((out / D["variation"]).resolve()), "variation_m": D["variation_m"],
                         "variation_scale": D["variation_scale"], "variation_offset": D["variation_offset"],
                         "fade": (D.get("fade") or {}).get("footprint_m") if detail_fade else None, "show": detail_show}
    if clutter and not channel:  # ground clutter round the eyes (an engine's detail scatter, as placeholders)
        from . import terrain_ground
        cf, *_ = build_field(T)
        cm = Materials(T, cf)
        ks = ("bush", "tussock", "tallgrass", "boulder")
        eyes = np.array([j["eye"] for j in jobs], float)
        lo_, hi_ = eyes[:, :2].min(0) - clutter, eyes[:, :2].max(0) + clutter
        if box:
            lo_, hi_ = np.maximum(lo_, box[0]), np.minimum(hi_, box[1])
        C = terrain_ground.clutter(T, cm, cf, ks, box=[lo_.tolist(), hi_.tolist()], near=(eyes, clutter))
        if len(C):  # (no bush or boulder at an eye: a view from inside a bush was all leaves)
            from scipy.spatial import cKDTree
            de, _ = cKDTree(eyes[:, :2]).query(C[:, :2])
            C = C[(de > 2.5) | np.isin(C[:, 3], [ks.index("tussock"), ks.index("tallgrass")])]
        job["clutter"] = {k: C[C[:, 3] == i][:, [0, 1, 2, 4, 5, 6]].round(3).tolist() for i, k in enumerate(ks)}
        notes.append("clutter: " + ", ".join(f"{len(v)} {k}" for k, v in job["clutter"].items()))
    GD = M.get("ground_detail")
    if GD and textured and not channel and grass:  # the turf's tiling detail over the baked maps (as an engine draws it)
        job["grass"] = [{"albedo": str((out / g["albedo"]).resolve()), "normal": str((out / g["normal"]).resolve()),
                         "size": g["size_m"], "fade": g.get("fade_m", GD["fade_m"]), "weights": g["weights"]}
                        for g in GD.get("swatches") or [GD]]
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
