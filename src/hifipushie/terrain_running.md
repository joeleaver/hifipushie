# Terrain: running it, and the export

Read guide(topic="terrain") first: describe the brief, then write the spec.

## Running
Through the MCP tools (a terrain lives in `workspace/terrain/<name>/`, every version kept):
- `set_terrain(name, spec=...)` saves and builds it and returns the report; `set_terrain(name, patch=...)` merges a
  change into the stored spec (objects merge key by key, `null` deletes), so edits stay small.
- `check_terrain(name)`: the report again. `look_terrain(name, map=True, masks=True, views=[...])`: the images
  (views take ~30 s plus ~10 s each). `export_terrain(name, size=1025, engine="unity")`. `terrain_history(name,
  revert_to=3)`.
- Questions for the designer come back as JSON from any of them.

Or from a shell:
```
uv run python examples/terrain_run.py <your.json>            # report + map + mask sheet + 3D views (~1-2 min)
uv run python examples/terrain_run.py <your.json> --no3d     # report + map + mask sheet (~20 s)
uv run python examples/terrain_run.py <your.json> --export   # also the engine files
```
The shell run writes its outputs beside the spec:
- `<stem>_map.png`: north-up hillshade with cover colours and contours. It shows rivers (blue), ridges (dashed
  red), routes (orange), sites (purple squares), walls (dark dots on the edge, bright red where climbable), names
  and a cover legend.
- `<stem>_masks.png`: each cover mask alone (white = dense).
- With `--export`, `<stem>_export/` holds (`"export": {"size": 1025, "engine": "unity"}` in the spec):
  - the heightmap: `height.npy` (float32, absolute metres), `height.png` (16-bit) and `height.raw` (Unity: 16-bit
    little-endian, first row south), both offset to 0; `meta.json` "unity" gives the terrain size and position
  - square at the engine size, padded if the frame isn't square
  - density masks per cover layer, plus water, roads, sites, playable and walls masks (always written: with no walls,
    playable is the dry ground a person can walk)
  - `splat*.png`: RGBA weights for the ground layers that sum to 1 (tree layers are instances, not in the splats)
  - `trees.csv`: tree instances (x, y, z, kind, layer)
  - `meta.json`: extent, height encoding, sites with their planes (level, fall, direction), passes, routes, rivers
    with their bed and water (surface height and width per point), fords, lakes
- **3D mesh tiles** (`export_terrain(name, tiles=True)`, `terrain_run.py --tiles`): the ground and its volumes as a
  grid of seamless glTF tiles in `tiles/`, for any engine. Two modes (`"mode"`):
  - `"cliffs"` (default, how games do it): the ground is the heightmap (`ground_<i>_<j>_lod<k>.glb` grid meshes, the
    same samples as `heightmaps/height_<i>_<j>.npy`: float32 metres, C order, row 0 the tile's NORTH edge, column 0
    its west; and, only for the tiles that have holes, `heightmaps/holes_<i>_<j>.png` (255 = hole, one pixel per
    heightmap cell, row 0 north; the ground entry's `holes` in the manifest) where a cave mouth, arch or shaft opens
    through it; the ground GLBs and `ground_collision_<i>_<j>.glb` leave those cells out), and `tile_<i>_<j>_lod<k>.glb` are 3D cliff meshes laid over it wherever the ground is steeper than
    `"cliff_slope": 42` (deg) or a volume opens, reaching `"cliff_margin": 4` m past it. Under a cliff the heightmap is
    pushed a few metres into the rock, so the cliff face covers it; each cliff mesh is a closed shell of rock that
    sinks under the heightmap at its edges (its buried back is primitive `extras.role = "buried"`: skip it if you
    like). Nothing to stitch. `"cave_wall": 3` m of rock is kept round every cave.
  - `"full"`: the whole ground as 3D mesh tiles (no heightmap in the scene).
  Both bake maps per tile per LOD (`"maps": true`): each tile has its own UV atlas and embeds base colour, ORM
  (occlusion, roughness) and a tangent-space normal map from the exact rock (with bake-only fine detail: small facets,
  cracks, the bedding notch), so detail comes from textures, not triangles. `"texel_density": [8, 4, 2]`
  (texels per metre per LOD: the unique maps carry the macro look only, the tiling rock detail in `materials/` and
  the manifest's `detail.recipe` draw what is finer than ~0.5 m), `"texture_max": 2048`, `"ground_density": 4`, `"micro": 1` (fine rock detail; 0 none).
  Beside the GLBs: `maps/<tile>_height.png` (16-bit displacement) and `maps/<tile>_weights<g>.png` (layer weights),
  `materials/<layer>_albedo/_normal/_height.png` (tileable detail textures) and the manifest's `engine_recipe` (how
  an engine blends the layers over the baked maps, triplanar on rock). The ground gets tiling detail too, one swatch
  per kind (`materials/turf_detail_*.png` on mown turf, `grass_detail_*.png` on long grass and scrub,
  `sand_detail_*.png` on sand: ripples, grit, pebbles; the manifest's `ground_detail.swatches` with its recipe: laid
  from above at 2 m, fading out by 20-70 m; `"grass_detail": false` leaves it out). Below that the ground's maps carry
  its own relief in their normals (tussocks, scrub lumps, the mower stripes' lean).
  See them as an engine would: `look_terrain(name, views=[...], tiles=True)` renders the last tiles export (baked maps,
  rock and turf detail, arches and caves, trees, the sites' props as stand-ins for scale: baskets, tee pads, a lodge),
  under a raking sun chosen per view (`"sun"` as for views) with aerial haze (`haze`: metres for 63%, default 5000);
  `light="clear"` swaps the default hazy sky for a deep blue clear one and a strong sun (what a sunny photo shows:
  judge colours against photos in it; the sky as a camera sees it, deeper than the light it casts, and a deep blue sea). Other settings (metres):
  `"tile": 64` (tile size), `"voxel": 0.5` (the meshing voxel, dividing the tile; coarser LODs are LOD0 decimated),
  `"lods": 3`, `"origin": [x, y]` (the grid's origin, default the frame's south-west corner), `"error": [0.04, 0.15,
  0.5]` (how far each LOD may stray from the true surface), `"budget": [12000, 3000, 800]` (triangles per tile per LOD: a tile LOD over twice its budget FAILS the export's
  checks, named with its count and why; `"collision_budget"` caps the collision mesh, default twice its LOD's),
  `"skirt": 0.3` (minimum skirt depth), `"collision": 1` (the LOD the collision mesh comes from), `"heightmap": 65`
  (samples per tile, 2^k + 1; 0 = none), `"splat": 128` (splat texels per tile; 0 = none), `"corridors": true` (or
  `{"spacing": 0.25, "buffer": 15, "size": 128}`; off by default): fine heightmaps along the water for a nested water
  solve, `corridors/corridor_<n>.npy` (float32, row 0 north, column 0 west) on rects of at most `size` m round every
  river's water path, lake shore and fall pool (+ `buffer` m), each listed in the manifest's `corridors.rects` (file,
  extent [[x0, y0], [x1, y1]] of the outer samples, cols, rows, spacing, follows): the top surface as the tiles build
  it (the ground with its stream beds and banks, the cliff meshes' rock at fall lips and faces where it stands
  higher), sampled from the export's field, no clutter; where a cliff shell is on top, its drawn LOD 0 surface
  (`drawn_samples` counts them), so water solved there stands on what is drawn.
  - `tile_<i>_<j>_lod<k>.glb`: one node at the tile's south-west corner (glTF: x east, y up, z south), primitives
    by `extras.role` and material: "surface" first (what is seen; material `terrain_baked`), then in cliffs mode
    "buried" (the shell's back under the heightmap: skip it, or draw it; material `terrain_buried`, a flat dark rock colour), then "skirt"
    (double-sided, material `terrain_skirt`). An importer that drops extras (Godot) can go by the material name. Per
    vertex NORMAL, TANGENT, TEXCOORD_0 (the baked maps),
    TEXCOORD_1 (the splat) and `_WEIGHTS0`, `_WEIGHTS1` (ground layer weights, 4 per attribute, summing to 1); with
    `"maps": false`, COLOR_0 (a display colour) instead of the baked material.
TEXCOORD_2 and `_DETAIL` belong to the tiling
    rock detail (the manifest's `detail`).
    `collision_<i>_<j>.glb`: positions only (cliffs mode: the cliff shells, backs included; load them together with
    `ground_collision_<i>_<j>.glb`, the heightmap grid with its hole cells cut). `heightmaps/`, `splats/` (RGBA = the same layers, a margin into the
    neighbours), `trees.csv`.
  - `manifest.json`: the grid (origin, tile size, count), per tile its bounds, files, triangle counts and the volumes
    it holds, the LODs, the material layers (name, colour, roughness, triplanar scale, which attribute and channel),
    the sea level, timings and the seam check.
  - Tiles meet exactly: neighbours share identical border vertices and normals at every LOD, and each tile's skirts
    reach past the neighbour's other LODs, so any mix of LODs shows no cracks. Every export runs a seam check on the
    written files (watertight joins, identical borders, normals, LOD gaps covered, heightmap edges, and black shards:
    faces whose corner normals point away from them, over 0.01% / 0.05% / 0.5% of LOD 0 / 1 / 2; baked maps decoded
    from both sides of every shared border; in cliffs mode the ground tiles' borders, heightmap never standing in a
    void, never showing through a cliff face, no cliff-mesh piece floating clear of the ground; no step in the baked
    surface on soft ground, which the normal map would draw as a thin dark line on the grass; every lake flooded on
    the tile heightmaps to its level covers no more than 1.5x its area) and fails loudly. The manifest's `lakes`
    gives each lake's level, area and outline rings ([x, y] m) for a water system. The
    manifest's `memory_gb` says what the export used (it runs one heavy job at a time, workers sized by free memory).
- `<view name>.png`: the views, with trees instanced from forest masks, roads as pale worn tracks and each site marked
  by a thin red pole 12 m tall (to judge what a view sees).

Read the images, not just the report. The report is in your units and ends with WARNINGS: read them.
