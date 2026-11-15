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


Where the code is (split by responsibility, C414): this module holds the defaults, the layers and the smooth min / max;
terrain_volumes, terrain_relief, terrain_field and terrain_materials the field and what it is made of; terrain_tiles
export_tiles: its stages in order over one context, the later ones in terrain_tiles_build (the tiles' meshes and LODs),
terrain_tiles_ground (heightmaps, splats, clutter, trees) and terrain_tiles_manifest (the manifest, the checks); with
terrain_tile_jobs (workers), terrain_tile_mesh and terrain_tile_border (one tile's mesh and border),
terrain_tile_job and terrain_tile_finish (a tile at one LOD, normals, bake); terrain_gltf the writer;
terrain_seam_check and terrain_map_seams the checks; terrain_tile_views the renders."""
from __future__ import annotations

import numpy as np
from . import moved

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
    "corridors": False,    # river-corridor heightmaps (terrain_corridors): true | {"spacing", "buffer", "size"}
    "detail": True,        # the tiling rock detail (terrain_swatch): swatches in materials/ and, on cliff tiles, a
                           # strike-binned UV set (TEXCOORD_n, metres) + _DETAIL (strike x, y, side share, bed v)
    "detail_source": "procedural",  # the swatch: "procedural" (terrain_swatch_make.swatch) or "scan:<set>" (a CC0
                           # photoscan from the rock_scans asset pack: terrain_swatch_make.scan_swatch)
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
    # a stream's bed and banks (terrain_stream; only on terrains with running rivers)
    "gravel": {"color": [0.44, 0.41, 0.36], "roughness": 0.7, "scale": 2.0},   # cobbles and gravel
    "silt": {"color": [0.33, 0.29, 0.22], "roughness": 0.6, "scale": 2.0},     # fine sediment in pools and slack water
    "bank": {"color": [0.25, 0.21, 0.15], "roughness": 0.8, "scale": 2.0},     # the bank's damp foot
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
# the rock relief is evaluated only where its weight is over RELIEF_CUT (a cost cull), and eased in from there to
# RELIEF_FADE, so the field stays continuous where the cull starts (Field._solid)
RELIEF_CUT = 0.01
RELIEF_FADE = 0.1
JUMP_LIMIT = 3  # sampled texels with a step under them (terrain_bake_maps.bake_texels) a tile LOD may have (seam_check)
BURIED_DEEP = 0.1  # a face is buried when its centre is deeper in the rock than this x sqrt(its area) (and > the LOD threshold)
FLOAT_PIECE = 50.0  # m2: closed cliff pieces off the tile border that never reach the ground, under this: dropped, logged
FLOAT_TOL = 0.15  # m over the pushed heightmap that still counts as reaching the ground (terrain_cliffs_checks.floating's tol)
EXPOSED_OFF = 0.5  # m out along a face's normal: rock there = behind the visible surface (terrain_cliffs.EXPOSED_OFF)
BURIED_SHADE = 0.6  # the buried back's material: the rock's mean colour under it x this (never white)
FALL_SEAT = 0.5  # fallen blocks seat this share of the rock relief's reach (x its weight) under the column's ground

TUBE_RUN = 16  # segments a tube evaluates together, at the points in their run's reach (Tube.sd)


STACK ={"radius": 0.75}
STACK_BUILD = 0.05  # m: the most rock relief may build out from a stack
STACK_CARVE = 0.3  # m: ... and carve into it (cartoon facets 1.4 x cut a fin of a stack loose 5 m up: the stack's own
# form carries its shape, the relief is texture on it)
# a solid sea stack's radius x the sea's stack radius; its form is terrain_stack.FORM (a jointed column), a style's
# sheet may override it (rock.stack)

ROOF_SPAN = 0.5  # the rock over an opening: at least this share of its span (thinner read as a lid on a hole)

# a fixed rotation for the facet lattice, so its creases don't line up with the world's axes
_ROT = np.linalg.qr(np.array([[0.62, -0.51, 0.33], [0.27, 0.71, 0.58], [-0.49, -0.12, 0.74]]))[0]


# a second rotation, for the lattice that warps the facet lattice (see _pl_facets)
_ROT_W = np.linalg.qr(np.array([[0.3, 0.8, -0.2], [-0.7, 0.1, 0.6], [0.5, -0.4, 0.7]]))[0]

THIN_LEVELS = 48  # at most this many height levels per thin piece (_local_thickness)

HOLD_REACH = 30.0  # m from a river's water line where the 3D field's ground keeps the banks the terrain grid has
HOLD_FREEBOARD = 0.3  # m over the water the banks are kept (forms.water grades banks from level + 0.3)

FACE_SLOPE_H = 0.25  # m: the stencil of the slope correction where a fall's face edits the column (Field.column)

THIN_STRATA = {"spacing": 1.7, "jitter": 0.2, "ramp": 0.5, "depth": 1.0, "tone": 1.0}  # thin rock's strata
# (`strata`): bed spacing, jitter share, plane ramp, soft beds' set-back (m); tone: soft beds' darkening
THIN_VOID = 8.0  # m: within this of a cave or notch thin rock keeps the old rule (Field.steep's tenth)
THIN_RELIEF = 0.35  # thin rock's relief: at most this share of its local half-thickness (Field.thin_cap); 0 = the old
# rule (thin fins and stacks took a tenth of the relief: smooth, Durdle Door without its beds)
THIN_TONE = 1.0  # how much of the full bed tone thin fins take back (Materials, rock colour)
BLOCK_TONE = {"bed": 0.06, "thin": 0.08, "block": 0.04, "p_fresh": 0.05, "fresh": 0.08, "warm": [0.04, 0.0, -0.06],
              "along": 0.10, "under_ledge": 0.12}

# ---------------------------------------------------------------- tiles

# the lattice's z planes sit this fraction of a voxel off round heights: flat floors at round heights (sea level, a
# cave floor at 5.5 m) lay exactly on lattice planes, every corner there was a zero, and marching cubes left
# non-manifold slivers (the seam check caught them). x and y stay on the tile borders.
ZOFF = 0.137

PRE = 32  # x a coarse LOD's budget: what its dense-mesh fallback reaches in one pyfqmr pass before the budget search
# (replayed on the alps block's 12 fallbacks: 85 -> 37 s, faces <= the old ones in every case, summed error p99
# 6.2 -> 5.7 m; 4x and 8x were faster still but their meshes sat further off the rock at the same count)

PINCH_GAP = 0.005  # m each copy of a pinched vertex steps into its own sheet (`_unpinch`)


SPECK_FACES = 16  # a closed piece this small split off by `_unpinch` is dropped (`_drop_closed_specks`)

WELD = 1e-3  # x voxel: canonical border vertices joined by a chain edge and closer than this are one vertex

_CTX: dict = {}  # what the export's worker processes read (forked: shared, not pickled)


WORKER_GB = 2.0  # a tile worker's peak PSS with maps: 1.04 GB on pebble (0.5 m voxel), 1.93 GB on a 10 x 10 tile block
# of t3_alps (1 m voxel, a 3 x 4 km terrain in the parent); field calls chunked, dense meshes streamed through
# <out>/_work (2.2 GB on pebble before that)

OVER_BUDGET = 2.0  # a tile LOD with more than this x its triangle budget fails the export's checks (said per tile)

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

RELIEF_CHART = 2.5  # the ground's maps-only relief on cliff tiles is band-limited as if their texel were this x larger:
# their charts' texel grids don't line up across a tile border (ground tiles' do), so fine relief differed there
BAKE_PIECE = 120_000  # texels per bake job (a 64 m tile's LOD 0 atlas at 13-16 texels/m is 1.2-2.6M: 10-20 jobs)

BORDER_FLAT = 1.5  # texels: every LOD's normal maps eased to the low poly's normal this close to a tile's edge

WORST_BORDERS = 4  # borders listed per failing map channel
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

# The modules this one was split into (C414), in the order the pipeline runs them. The tile export's state hashes the
# code of all of them (codehash.digest(*MODULES)): before the split that was this one module's import closure.
MODULES = ("terrain_mesh", "terrain_volumes", "terrain_relief", "terrain_field", "terrain_materials", "terrain_gltf", "terrain_tile_mesh", "terrain_tile_border",
           "terrain_tile_jobs", "terrain_tiles", "terrain_tiles_build", "terrain_tiles_ground", "terrain_tiles_manifest", "terrain_tile_job",
           "terrain_tile_finish", "terrain_seam_check", "terrain_map_seams", "terrain_tile_views")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C427)
