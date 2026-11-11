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
export_tiles, with terrain_tile_jobs (workers), terrain_tile_mesh and terrain_tile_border (one tile's mesh and border),
terrain_tile_job and terrain_tile_finish (a tile at one LOD, normals, bake); terrain_gltf the writer;
terrain_seam_check and terrain_map_seams the checks; terrain_tile_views the renders."""
from __future__ import annotations

import numpy as np

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


_CTX: dict = {}  # what the export's worker processes read (forked: shared, not pickled)


# The modules this one was split into (C414), in the order the pipeline runs them. The tile export's state hashes the
# code of all of them (codehash.digest(*MODULES)): before the split that was this one module's import closure.
MODULES = ("terrain_mesh", "terrain_volumes", "terrain_relief", "terrain_field", "terrain_materials", "terrain_gltf", "terrain_tile_mesh", "terrain_tile_border",
           "terrain_tile_jobs", "terrain_tiles", "terrain_tile_job", "terrain_tile_finish", "terrain_seam_check", "terrain_map_seams", "terrain_tile_views")
