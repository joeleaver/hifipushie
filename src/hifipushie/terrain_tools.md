# Terrain: tool reference

## Tool reference

The full documentation of this topic's tools: their MCP descriptions are the short form. guide(topic="<tool name>") returns one section. These tools are the `terrain` toolset: enable_toolset("terrain") turns it on.

### `set_terrain`

`set_terrain(name, spec=None, patch=None, note='')`

Create or change a terrain (a landscape or game level described in a designer's words: guide(topic="terrain")
has the vocabulary). `spec` replaces the whole spec; `patch` merges into the stored one (objects merge key by key,
null deletes: {"sites": {"camp": {"radius": 30}}, "cover": {"old": null}}). Every version is kept
(terrain_history). Builds it and returns the report (in the spec's units, WARNINGS last), or, when its kind needs
the designer to decide something, the questions as JSON: relay them, don't answer them.

### `check_terrain`

`check_terrain(name)`

The terrain's report, measured on the built ground: the world kind and its compression, peaks as built,
rivers and their banks, basins and walls (how much of each edge is unclimbable, climbable spots), passes, sites
(cut/fill), routes (grades, switchbacks, crossings: fords or bridges), cover shares, intent checks (sight lines,
skyline, flood heights, grades), drainage, WARNINGS last. Questions for the designer come back as JSON.

### `look_terrain`

`look_terrain(name, map=True, masks=False, views=None, spec_views=False, size=1100, tiles=False, haze=5000.0, light=None, styles=False)`

Images of a terrain. map: north-up hillshade with cover colours, contours, rivers, ridges, routes, sites,
walls (red where climbable), names and a scale bar. masks: each cover mask alone (white = dense). views:
perspective renders (Cycles, with trees and water; ~30 s + ~10 s a view): [{"name", "eye": address | [x, y, z],
"lift": m, "look": address, "fov": deg, "sun": "auto" | side | {"from", "height"} | "morning"}] (auto: a raking
sun per view); spec_views=True renders the spec's own "views". tiles=True renders the views from the 3D mesh
tiles of the last export_terrain(name, tiles=True) instead (the way an engine shows them: baked maps, tiling rock
detail, arches and caves, the ground's character, trees, the sites' props as stand-ins for scale, a raking sun and
aerial haze: `haze` m for 63%, None off; `light`: "clear" = a deep blue clear sky and a strong sun, as in a sunny
photo, default the hazy sky); a view may add "lamp": watts (a headlamp, inside caves). styles=True: the spec's
terrain styles (and realistic) as a swatch sheet (per style x layer: albedo tiled 2 x 2, lit, normal) and a
transition strip per layer, as the recipe blends them; with tiles=True the views are drawn with each zone in its
style (the manifest's styles recipe in Blender: a reference for an engine's shader). Files are also
written to workspace/terrain/<name>/. Read the images, not just the report.

### `export_terrain`

`export_terrain(name, size=None, engine=None, out_dir=None, tiles=False, styles_only=False)`

Write the terrain for an engine (default workspace/terrain/<name>/export/): height (.npy float32 absolute,
16-bit .png and Unity .raw offset to 0), masks per cover layer plus water, roads, sites, playable and walls,
splat weights for the ground layers, trees.csv, and meta.json (heights, the Unity terrain size and position,
sites with their planes, passes, routes, rivers with water surface and width, fords, lakes). size: an engine
grid (Unity 257/513/1025/2049, Unreal 505/1009/2017); engine="unity" picks 2^n+1 if no size. Defaults from the
spec's "export". tiles=True writes 3D mesh tiles instead (default workspace/terrain/<name>/tiles/): the ground
and its volumes (arches, caves, overhangs) as seamless glTF tiles with LODs, skirts, collision, heightmap and
splat tiles and a manifest.json, tuned by the spec's "export": {"tiles": {...}}; a seam check runs on every
export; when it (or a tile's triangle budget) fails the reply starts with CHECKS FAILED and lists each failure
with its tiles: the files are still written, complete and loadable. While it runs, each stage's start and a tile
counter (done / total, elapsed, ETA, every 30 s) go to <tiles dir>/export_log.txt and out as MCP progress. A spec with "styles" adds the per-style
layer textures, zone maps and the manifest's `styles` section (guide, "Styles"); styles_only=True writes ONLY
those (seconds, no meshing) into out_dir or beside the last tiles export, updating its manifest.json.

### `terrain_history`

`terrain_history(name, revert_to=None)`

List a terrain's versions, or restore one (saved as a new version, so nothing is lost). With no name
("" ), lists the terrains.
