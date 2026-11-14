"""Baked maps for terrain tiles: the detail comes from textures, not triangles.

Each cliff (or full-mode) tile mesh gets its own UV atlas per LOD (`unwrap`: charts by the axis a face faces, as a
triplanar projection would pick, split where they'd overlap, packed on 4-texel blocks), and every texel goes onto
the exact rock field plus `micro_relief` (fine facets, cracks and laminae below the meshing voxel, bake-only: meshed
they would zigzag) to bake:
- normal (tangent space, glTF/OpenGL convention: +Y = up the texture), against MikkTSpace-style tangents (written as
  TANGENT; Blender and most engines recompute Mikk and ignore it, so the bake must match Mikk);
- height (16-bit, the exact surface's offset along the low-poly normal, range per tile in the manifest);
- AO (from the field: how far open the rock is along the normal and round it, the same in every engine);
- base colour (the terrain's own macro colour at the exact point: cover, strata, rock tone, wet band);
- roughness (from the layer weights) packed with AO as ORM;
- layer weights (RGBA per group of 4 layers, the manifest's order) for engines that blend tiling layers.
Gutters: texels round each chart are baked from the surface beyond its edge (the chart's triangles extrapolated),
so filtering and mips at a seam read the real neighbour (across tile borders too), then dilated.
Ground tiles use their planar UV (the tile's square) and bake colour, normal and ORM the same way.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at terrain_bake.NAME: C422). terrain_bake_maps: baking a tile's maps: fine rock relief, the surface's texels,
lines, ambient occlusion, `assemble`, `bake`. terrain_bake_unwrap: unwrap: adjacency and components, charts split and
packed, split corners, tangents. terrain_bake_layers: tiling layers: a layer's height and textures, PNG / JPEG, the
material.
"""
from __future__ import annotations

import numpy as np
from . import moved

def _unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


# ---------------------------------------------------------------- fine rock (bake only)
SHARP_MIN = 0.25  # m: the narrowest edge filter the maps use for the rock structure (see micro_relief)

# ---------------------------------------------------------------- unwrap
_DIRS = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]], float)
# (u, v) axes per direction, u x v = the direction (faces keep their winding in uv)
_UV = {0: ([0, 1, 0], [0, 0, 1]), 1: ([0, -1, 0], [0, 0, 1]), 2: ([-1, 0, 0], [0, 0, 1]), 3: ([1, 0, 0], [0, 0, 1]),
       4: ([1, 0, 0], [0, 1, 0]), 5: ([1, 0, 0], [0, -1, 0])}

CHUNK = 25_000  # texels per field call: whole atlases at once (2.6M texels x 4-point stencils x fbm temporaries) made
# each bake worker 2+ GB; 200k a call ran 25% slower than 25k with 12-16 workers busy (temporaries out of cache:
# the memory bus, not the cores, set the pace)

# a step in the bake field's value on soft ground (rock layers under JUMP_SOFT, rock relief weight under JUMP_RELIEF):
# the normal at JUMP_H and twice that differs by more than JUMP_DEG right at it. Counted per tile LOD (every 7th
# texel, as the texel error)
JUMP_SOFT = 0.2
JUMP_RELIEF = 0.1  # (terrain_volumes.RELIEF_FADE: past it the rock character is in full)
JUMP_H = 0.03  # m: the surface normal's own stencil scale (terrain_mesh: the voxel / 16)
JUMP_DEG = 6.0

# ---------------------------------------------------------------- tiling layers

# per layer: the detail pattern (a tileable height field) and how strongly it shows. Patterns are spectra (periodic by
# construction): "grit" = rock grain and lumps, "grain" = fine grit, "ripples" = sand ripples, "clods" = soil lumps,
# "blades" = grass (streaky fine noise), "litter" = leaf litter blobs, "soft" = snow.
LAYER_DETAIL = {
    "rock": ("grit", 0.35), "wet_rock": ("grit", 0.25), "grass": ("blades", 0.5), "turf": ("blades", 0.3),
    "forest_floor": ("litter", 0.6),
    "sand": ("ripples", 0.4), "earth": ("clods", 0.6), "snow": ("soft", 0.25),
}


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("terrain_bake_maps", "terrain_bake_unwrap", "terrain_bake_layers")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
