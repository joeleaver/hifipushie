# Vegetation: tool reference

## Tool reference

The full documentation of this topic's tools: their MCP descriptions are the short form. guide(topic="<tool name>") returns one section. These tools are the `plants` toolset: enable_toolset("plants") turns it on.

### `grow_plant`

`grow_plant(name, spec=None, patch=None, note='', copy_from=None)`

Create or change a plant and grow it (guide(topic="vegetation") has the vocabulary and the stages). `spec`
replaces the whole spec; `patch` merges into the stored one (objects merge key by key, null deletes:
{"age": 60, "habit": {"apical": [0.6, 0.5]}, "environment": {"wind": {"from": "w", "strength": 0.5}}}).
A spec is botanical words: {"species": preset, "age": years, "seed", "height": m, "habit": {...overrides...},
"environment": {...}, "guides": {...}, "prune": [...], "envelope": {...}, "forces": [...], "leaves": {...},
"bark": {...}, "season", "decay", "style"}. "style": "realistic" (default) | "blobby" | "anime" | "cartoon" | "pixar", or
{"sheet": "blobby", "crown": {"masses": 6}, ...} to override a sheet's numbers: the SAME grown plant (skeleton,
height, crown extent, lean) dressed another way (blobby: few fat limbs + smooth closed masses; anime: painted leaf clouds; cartoon: scalloped clumps; pixar: every limb + a soft canopy shell with a layer of real leaf cards); the
report says what was simplified and the outline IoU against the realistic tree. Looks and exports follow the style.
"season": summer | spring | autumn | winter. The same spec always grows the same plant. Every version is kept
(plant_history). Returns the report: size, form measured on its own silhouettes, limbs, foliage, guides, the
reference match if it has one, WARNINGS last, and (for a patch) every changed value old -> new with what the tree
did. In a patch, lists REPLACE (give the whole per-order list; `"prune": null` removes every prune: use
edit_plant to add or remove one). copy_from: start `name` as a copy of another plant (+ patch): variants of one
description, e.g. {"seed": 2, "age": 14}. Use get_plant first to see the values you are about to override.
With no arguments but a name: the report of the stored plant; name "" lists the plants and the species presets.

### `edit_plant`

`edit_plant(name, ops, note='')`

Direct the plant the way an artist does between growth years; it regrows around every edit. ops, in order:
{"op": "guide", "name", "path": [[x, y, z], ...] (m), "from_year", "until_year", "vigour"}: a drawn axis at any
branch order (it starts from the nearest wood at from_year, lies exactly on the path, is never shed or bent, and
branches grow from it; a path from [0, 0, 0] at year 0 is the trunk). {"op": "remove_guide", "name"}.
{"op": "take_limb", "limb": "SW1", "name"?, "path"?}: a GROWN main limb (the report names them) becomes a guide of
the same place and shape, which you can then redraw; the rest of the tree regrows around it (it may change).
The same with "on": another guide's name (or "trunk") makes it leave THAT axis. Paths are splined through
their points ("straight": true keeps corners).
{"op": "prune", "box": [[lo], [hi]] | "sphere": [[c], r] | "above": z | "below": z (limbs LEAVING the trunk under
z) | "under": z (nothing but the trunk hangs under z)}: a clean cut on the finished tree, nothing else changes;
with "from_year" it is cut from that year on and the tree answers it (regrows elsewhere).
{"op": "remove_prune", "index"}, {"op": "clear_prunes"}.
{"op": "cut", "year": N, <a volume as for prune>, "every": years, "until_year", "sprouts": n}: the wood in the
volume is cut AT that year (and again every `every` years) and the stubs sprout `sprouts` new shoots each: a
pollard ("above": 2.5, "every": 6), a coppice ("above": 0.3), a lopped limb or a storm break (a box, sprouts 0-2).
{"op": "clear_cuts"}. {"op": "dead", "limb": name | id | guide (or a volume), "min_radius", "from": m along it},
{"op": "clear_dead"}. {"op": "envelope", "shape": ellipsoid | cone | column | dome, "radius", "top", "base",
"soft"} (a soft crown shape; no other keys = remove). {"op": "force", "dir": [x, y, z], "strength", "orders"},
{"op": "clear_forces"}. {"op": "set", "path": "habit.apical.0" | "age" | "leaves.length"..., "value"}.
Returns the report after regrowing, with what changed in size.

### `get_plant`

`get_plant(name='', species='')`

A plant's spec as stored ("own"), what it RESOLVES to once its species preset and the defaults are under it
("resolved": every habit, leaf, twig and bark value actually in force), what each number usually is
("habit_ranges", "leaf_twig_ranges") and how many growth steps its age makes. Read this before overriding
anything: an override replaces the resolved value, and per-order lists are replaced whole. With `species` and
no name: that preset resolved (to see what a species gives before using it).

### `look_plant`

`look_plant(name, views=None, azimuth=0.0, size=640, foliage=None, sheet=False, triangles=None)`

Images of a plant (Blender, 5-40 s). views, any of: "clay" (the bare skeleton as clay: judge the structure
here first), "bare" (in colour, no leaves), "leaf" (in leaf; these three are side views from `azimuth`, 0 = looking
along +y), "far" (at eye height from far enough that the tree is half the picture: how it reads in a scene), "near"
(standing by it, 2-5 m, looking up: trunk, bark, forks), "close" (foliage: leaves and twigs), "under" (from under
the crown, up along a limb), "ground" (eye 1 m up, 8 m from the lowest foliage: where the plant meets the ground;
the report's `ground:` line counts what rests on it and what was turned, shortened or left out), or a camera of your
own {"name", "eye": [x, y, z], "look": [x, y, z], "fov": deg, "clay": bool}. Default clay + leaf + far. The ground
is flat grass unless the spec has environment.ground {"slope": deg, "toward": [x, y], "water": z} (a hillside
falling that way; a water level z m against the foot). clay and bare show a pole banded every metre (every fifth
band red) beside the plant. triangles=N shows the plant as export_plant(triangles=N) writes it (thin wood left
out, fewer and larger cards): judge the budgeted plant before exporting it. Files carry the view, azimuth and
version in their names. foliage: "cards" (the twig
atlas on cut cards: what a game draws; default) or "mesh" (real leaf meshes: close-ups, video).
sheet=True returns the reference sheet instead (photo | outlines over each other | every view, with the numbers);
it needs plant_reference first. Files are also written to workspace/plants/<name>/. Read the images.

### `look_plants`

`look_plants(names, at=None, spacing=None, views=None, azimuth=0.0, size=640, foliage=None, triangles=None)`

Several plants standing together in one picture (a stand, a hedge line, a tree with its neighbours): do they
belong together, do their sizes relate? at: [[x, y], ...] m per plant, or spacing m apart on a loose ring
(default 0.35 x the tallest). views: "far" (default), "near", "clay", "top", or a camera {"eye", "look", "fov"}.
The first plant's environment (ground slope) sets the scene. The same plant may be named more than once.
A plant with a `set` (grow_plant patch {"set": {"count": 5}}): "oak#*" names its whole set, "oak#2" one of it.
`at` goes with the names in order (a set's plants #1, #2... in turn). triangles=N shows every plant at that
budget, as export_plant(triangles=N) writes it.

### `plant_form`

`plant_form(name='', species='', cases=None, fit=None, iters=30, seeds=2)`

A tree's form ACROSS AGES AND SETTINGS, measured the way foresters do, and optionally fitted: the habit that
looks right at one age is often a bare pole at half that age and a monster at twice. Each case grows the plant
(or a species preset) at {"age": years, "environment"?: {"setting": "open" | "edge" | "forest", "spacing": m,
"open_side": [x, y]}, "name"?} and measures height (m), width_over_height (crown width / height), crown_ratio
(live crown / height), widest_at (height of the widest level / height), dbh_cm, top_off (m the top stands off
the foot), nodes. A case may carry target bands for any of them, e.g. "crown_ratio": [0.3, 0.45] (from yield
tables, crown-ratio studies or boxes read off whole-tree photographs); the reply marks every miss.
Default cases: the plant at 0.2 / 0.45 / 1 / 2 x its age in the open, and at its age on a stand's edge and
inside a stand 4 m apart. fit = {habit path: [lo, hi]} (as plant_reference's) searches those numbers for the
least miss over ALL cases (`iters` rounds x `seeds`; minutes) and, for a stored plant, saves them.

### `plant_reference`

`plant_reference(name, image_path, crop=None, foot=None, polygon=None, tol=30.0, horizon=None, bare=False, credit='', fit=None, fit_iters=40)`

Give the plant a reference photo and measure against it. The silhouette is taken from the photo either by
`polygon` (the tree's outline traced on the photo in image pixels, closed: use this when the tree fills the frame
or stands against other trees) or by `crop` [x0, y0, x1, y1] + `foot` (the trunk's x in px): pixels more than
`tol` from the sky colour at the crop's edges are tree; below `horizon` (image y where ground or far trees
start) only the trunk counts. bare=True for a winter photo (compared without leaves). Returns outline IoU,
width/height, bole and widest height, ours vs the photo's.
fit = {habit path: [lo, hi]} searches those habit numbers for the best match (~1-2 min; e.g. {"apical.0":
[0.45, 0.65], "angle.0": [40, 80], "vigour": [3, 6], "sag": [0.2, 2]}; integer bounds stay integers) and saves them
into the plant's habit; it also charges limbs drooped under the crown's base, so it can't cheat the outline.

### `export_plant`

`export_plant(name, out_dir=None, triangles=None, set=False, lods=1, impostor=False, seasons=None, wet=False, lod_files=False, grade='full')`

Export the plant as a GLB (workspace/plants/<name>/export/<name>.glb unless out_dir): a `wood` mesh (bark
colour, normal and roughness as tiling textures on the branch uv) and a `foliage` mesh (every twig's card; the
twig atlas with alpha MASK, double sided, normals bent out from the crown, COLOR_0 = a per-twig tint).
triangles: LOD 0's budget (a game tree: 10-40k; without it everything grown is written, often 100-400k):
branches get fewer rings and sides, the thinnest wood is left out (marked wood stays), twigs are thinned and the
rest drawn larger. lods: 1-3 mesh LODs (100 / 45 / 18% of the budget); impostor=True adds a HEMI-OCTAHEDRAL impostor as
the last LOD: one quad the engine's shader turns to the camera, drawing the nearest of 8 x 8 views baked over the
upper hemisphere (holds from the horizon to straight down: trees seen from a hill; recipe in the material's extras,
reference Godot shader spikes/godot_veg/impostor_octa.gdshader; ~2-3 min of Blender per shape of the plant, ~40 s
per further season); impostor="cross" = the old two crossed quads (any viewer draws them; read as a cross from above). LOD 0 is the scene, the others hang on it
(MSFT_lod) and are listed in extras with the screen height to switch at; lod_files=True also writes each LOD as
its own <name>_LOD<k>.glb (Unreal, Unity, Godot take LODs as separate meshes).
Wind is always written: TEXCOORD_1 = (trunk, branch) sway weights, TEXCOORD_2 = (phase, flutter), the same four in
_WIND; the shader recipe is in extras. seasons: any of "spring", "summer", "autumn", "winter", "snow" as material variants
(KHR_materials_variants; a deciduous winter hides the foliage; "snow" frosts the foliage picture, snow on wood is
an engine shader: recipe in extras); wet=True adds a "wet" variant. Collision: capsules for the trunk and main
limbs in extras + a low `<name>_collision` mesh node outside the scene.
A plant with a `style` exports in its style with the same node, mesh and material names (wood / foliage; bark /
foliage), LODs, wind channels, variants and collision: its foliage is closed untextured geometry (colour = the
material's baseColorFactor per season x COLOR_0), `triangles` defaults to the style sheet's budget, and the reply
says what was simplified (also in extras.hifipushie_plant.style). A styled deciduous tree's wood has a second
primitive, slot `bark_forks` (hidden unless the season is bare); a styled small plant's foliage has one, slot
`heads` (flower / seed heads, hidden out of their seasons).
The impostor is lit by the engine: albedo (unlit, with the shade of what stands above baked in) + a tangent-space
normal map, a picture per season; its material must not receive shadows (the quads shadow each other).
<name>_seasons.json leads with `contract` (version: bumped whenever a slot or vertex channel changes) and
`slot_list` (every slot: its mesh / primitive, the seasons that hide it, its channels): an engine should refuse a
version or slot it doesn't know. Small plants (clumps) export their seasons as variants too (colour; layers out
of season hidden); their lying down in winter is in the looks only.
set=True writes the plant's `set` as ONE file (<name>_set.glb): a node per plant in a row, the bark and foliage
materials and textures shared (a forest kit); `triangles` is then each plant's own budget.
A SWARD (species sward / sward_mown / sward_rough: plain grass as a 2 m tile of blades, see the guide) exports as its
own files: <name>_LOD0..3.glb (fewer, wider blades), <name>.glb, <name>_seasons.json with a `sward` block (tile size,
LOD rings, the fade into the terrain's grass texture and its colours); triangles / lods / impostor don't apply.
grade="groundcover" (small plants: grass, daisy, clover, fern... in any style) = the SCATTER grade: the clump as it
is drawn in full, baked per season onto a few alpha cards: LOD 0 6 cards (288 triangles), LOD 1 4 (96), LOD 2 3 (36).
Each card shows the slice of the clump in its own wedge round the foot, so every blade is drawn once. Same slots
(foliage; seasons as variants of it, winter = the plant lying, snow = winter under snow), wind channels and seasons
json; adds TANGENT + a normalTexture; no bark / heads slots (stalks and flower heads are in the pictures). Written to
its own folder (default export_groundcover/) as <name>_LOD0..2.glb, <name>.glb (MSFT_lod) and <name>_seasons.json:
point the game's groundcover at that folder. ENGINE: import its PNGs WITHOUT mipmaps, or WITH them and alpha scaled up
by the mip level in the shader (recipe in the material's extras.alpha_mips; with plain mipmaps thin blades vanish past
~4 m), and turn the importer's own LOD generation off for these meshes. ~5-10 min of
Blender the first time (cached by the spec).

### `wind_plant`

`wind_plant(name, triangles=20000, seconds=4.0, strength=1.0, wind_from=270.0, azimuth=0.0)`

The plant in the wind, as a game would move it: its export (at `triangles`) is opened with Blender's glTF importer
and swayed from the file's own wind channels (trunk sway, limbs each in their own phase, leaf flutter) by the
shader recipe in the file's extras. strength 0.3 = a breeze, 1 = a fresh wind, 2 = a gale; wind_from = the compass
bearing it blows from (270 = from the west, +x is east). Returns a strip of six frames over their difference from
the first (bright = moving: the trunk's foot must stay dark, the crown's edge and the limb ends bright), the mp4's
path, and what the importer found (uv sets, attributes, variants). 30-90 s.

### `sync_plant`

`sync_plant(name, pull_only=False)`

The plant as a Blender file a person (or you, through a Blender session) can edit by hand:
workspace/plants/<name>/plant.blend holds the plant with its guides (orange, collection "guides") and its named
main limbs (blue, "limbs") as Bezier curves. First every edit made there comes back into the spec: a guide curve
moved or given more points = that guide redrawn; a limb curve moved = that limb taken over as a guide with the
new shape; a curve added to "guides" = a new guide; a guide curve deleted = removed. Then (unless pull_only) the
file is written again from the spec. A running Blender with the file open is read live and reloaded. Only
what moved from what the last sync wrote counts: syncing twice changes nothing. Returns what came back and the
report.

### `plant_history`

`plant_history(name, revert_to=None)`

List a plant's versions (plant_history(name)), or restore one: plant_history(name, revert_to=3) saves version
3's spec again as a new version, so nothing is lost.

### `grow_stand`

`grow_stand(name, spec=None, patch=None)`

A forest stand as a game builds one: a few grown trees per species and role, stood many times at a spacing,
with a floor. spec (or a merge `patch`; null deletes): {"species": "norway_spruce" or [{"species", "share",
"patch": plant spec patch}], "age": years, "ages": +- spread over the variants, "spacing": m between stems,
"size": [m, m] (the plot; x across, y deep), "variants": interior trees grown per species (3), "edge": any of
"n", "s", "e", "w" = sides open to the light (their outer rank is edge trees: foliage down the open side, turned
to face out), "rows": true = planting rows along y (a plantation's aisles), "jitter": 0-0.5 x spacing,
"scale": [0.9, 1.1] per-tree size, "clearings": [{"at": [x, y], "r"}], "paths": [{"points": [[x, y], ...],
"width"}], "floor": {"brash": fallen branches per m2 (0.35), "stumps" per m2, "ferns" per m2 (they stand where
light reaches: clearings, paths, open edges, a few patches), "fern": a clump preset, "moss": 0-1, "litter": 0-1},
"lod": {"near": m, "mid": m, "budgets": [null, 10000, 1500]}, "haze": {"distance": m, "color"}, "light":
{"ambient", "bounce", "sun_energy"}}. Interior trees are grown with environment.setting "forest" at this spacing
(bare stems, dead branches kept by the species' dead_keep, a small high live crown; their girth capped by the
stocking, habit.sdi_max), edge trees with "edge". Returns the forester's numbers (stems / ha, height, dbh, basal
area, live crown ratio, canopy cover, each variant) with warnings. No arguments but a name: the stored stand.

### `look_stand`

`look_stand(name, views=None, size=720, max_full=25)`

Pictures of a stand (Blender; 2-8 min: every variant is meshed at up to three levels of detail). views, any
of "inside" (default: eye 1.7 m among the stems), "aisle" (down a row), "edge" (from outside an open side),
"above" (a high oblique), "canopy" (from the floor, straight up), or a camera {"eye": [x, y, z], "look", "fov"}
in the plot's metres (0, 0 = its middle). Each tree is drawn at the level its distance from the nearest eye
gives (the stand's `lod`), at most `max_full` at full detail (GPU memory: a laptop holds a few dozen full
trees; hundreds at budgets). Distance haze and the canopy's diffuse light are the stand's `haze` / `light`.
The reply counts what was drawn.

### `export_stand`

`export_stand(name, out_dir=None, triangles=None, lods=3, impostor=True)`

Export the stand as a forest kit (workspace/stands/<name>/export unless out_dir): one GLB per variant with
`lods` mesh LODs from `triangles` (default 2 x the stand's mid budget) + an impostor, wind and collision as
export_plant writes them; the floor's meshes (brash0-3.obj, stump0-1.obj, the fern's GLB); layout.json = every
tree (x, y, yaw, scale, variant) and floor thing, the LOD distances, the haze. A heavy job (minutes per variant;
one at a time on the machine).
