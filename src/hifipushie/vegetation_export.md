# Vegetation: the export (LODs, wind, seasons, impostors, collision, the contract)

Read guide(topic="vegetation") first.

## The export is another object: look at it

A budget leaves out thin wood and draws fewer, larger cards. `look_plant(name, views=["leaf", "far"],
triangles=12000)` renders exactly what `export_plant(name, triangles=12000)` writes. Judge that picture, not the
full-detail one. A budget first gives branches fewer rings and sides, then leaves out the thinnest wood (wood you
marked, dead wood and drawn guides, stays down to a quarter of that girth), and draws the twigs that stand on wood
it kept; the export WARNS when cards would float.
When a budget buys fewer than a quarter of the twigs, the foliage is drawn as **bough cards** instead: the tree's own
limb ends (wood, branchlets, every twig) baked into pictures, each bough seen from its face and from its side on two
crossed cards, standing where the tree has such a bough. How the foliage is cut for a budget (`veg_bough.fit`):
- While the foliage's triangles buy at least 8% of the tree's FINEST cut (boughs of about two twig lengths) on
  seven-corner cards (10 triangles a crossed pair), the LOD is that finest cut THINNED: at most 45% of its boughs
  even at LOD 0 (more only stack layers: overdraw), spread evenly through the crown, each drawn larger until together
  they cover what the whole cut covered (measured on the cards' own polygons from two sides).
  LOD 0, 1 and 2 then share ONE atlas, one material slot and one silhouette, and nothing pops at a switch. This is
  what a foliage artist does (remove cards, grow the rest). A 20k conifer's three LODs are all of this kind; the
  triangles the foliage doesn't use go to finer wood.
- OVERDRAW is the cost of card foliage, not triangles: a stand of 20k spruces that drew 6.6 card layers per covered
  pixel cost 1.6x the GPU time of a stylised spruce with as many triangles. Read `card area / covered` per LOD
  (summed card area / covered area) and aim at 4-5 for LOD 0, 3-4 for LOD 1. And give a
  FOREST its stand forms (`environment.setting: "forest"`, `spacing`): open-grown conifers planted 3.5 m apart put
  the player's eye inside six skirts of foliage; an interior tree has a bare stem at eye level and a tenth of the cards.
- Under that, the tree is re-cut into fewer, larger boughs (whole limbs at a few hundred cards) on seven-corner
  cupped cards, its own atlas. A re-cut next to a fine cut does pop: a spruce's whole-limb LOD 1 covered
  0.85 of its LOD 0 and lost its top; and MID-sized boughs (2-3 m) on any card read as palm fronds or round leaves
  from 30 m. Fine or whole limbs, not between.
Judge every LOD at the distance and PIXEL SIZE it is drawn at (a 26 m tree at 64 m is ~310 px of a 1080p screen: a
6 m piece of crown is 150 px; needle detail is not there, silhouette and tone patches are), and in the engine
(covered area at each switch; overdraw = summed card area / covered area).
Raise the budget if the crown falls apart (a game tree: 10-40k; a hero tree 40-100k).

## Game-ready: LODs, wind, seasons, collision

`export_plant(name, triangles=20000, lods=3, impostor=True, seasons=["summer", "autumn", "winter"], wet=True,
lod_files=True)`:
- **LODs**: 100 / 45 / 18% of the budget from the same tree, then (impostor) two crossed quads with the plant's
  picture. `<name>.glb` shows LOD 0 and hangs the rest on it (MSFT_lod; extras list each LOD's triangles and the screen
  height to switch under). `lod_files` writes `<name>_LOD<k>.glb` too: most engines take LODs as separate meshes.
- **Wind**: every vertex carries trunk sway (0 at the foot, 1 at the top), branch sway (0 where its limb leaves the
  trunk, 1 at the limb's end), a phase per limb, and leaf flutter (0 at a card's foot, 1 at its tip): TEXCOORD_1 =
  (trunk, branch), TEXCOORD_2 = (phase, flutter), and all four in `_WIND`. The shader recipe is in the file's extras.
  `wind_plant(name)` renders the export swaying by that recipe: look at it (the foot still, limbs out of step).
- **Seasons** are states of the plant (`"season": "spring" | "summer" | "autumn" | "winter" | "bare" | "dead"`, `"snow": 0-1`,
  `"wet": 0-1`, `leaves.autumn` = the autumn colour; evergreens keep their needles and colour) for the looks, and
  material variants in the export (KHR_materials_variants: spring / summer / autumn / winter / snow / wet). SNOW IS THE
  WINTER STATE WITH SNOW ON IT: the same slots hidden and shown as in winter (a leaf-dropping plant: crown hidden, the
  bare wood and a style's forks shown; an evergreen keeps its crown, whose `snow` variant is the ready-mixed pale colour /
  frosted picture; a clump by its own winter state), and the snow impostor is the bare tree under snow. Snow lying on
  wood (and per pixel on anything) is the engine's shader: `<name>_seasons.json` `snow` gives the numbers our looks use
  (linear colour, coverage, the normal's up threshold `by_normal.from` / `to` and the formula).
- **Collision**: capsules along the trunk and main limbs (extras) and a low `<name>_collision` mesh node (outside the
  scene), and `<name>_collision.glb`: the same mesh as a file, its node IN the scene and named `<name>_collision-colonly`
  (Godot's importer makes a static body of a node so named and drops the mesh).
- **The impostor** (`impostor=True`) is HEMI-OCTAHEDRAL: the plant baked from 8 x 8 directions spread over the upper
  hemisphere (an octahedral grid: the border of the atlas is the horizon, its middle straight down) into one atlas, and
  drawn as ONE quad that the engine's shader turns to the camera, blending the four baked views nearest the camera's
  direction (one parallax step by a depth map, so neighbouring views line up). It holds from the horizon to looking
  straight down: two crossed quads read as a cross or a bird from a hill.
  What engines do (Ryan Brucks' octahedral impostors for UE, https://shaderbits.com/blog/octahedral-impostors; Amplify
  Impostors, https://amplify.pt/_AI; the Godot port https://github.com/SIsilicon/Godot-Octahedral-Impostors): the
  hemisphere variant for things never seen from below (twice the resolution of the full sphere), frame blending.
  Maps: albedo (unlit, the shade of what stands above each point baked in at half strength: an engine casts no shadow
  inside a picture) with alpha; an OBJECT-SPACE normal map (glTF axes, rgb * 2 - 1: the quad turns, so tangent space
  means nothing) with the depth behind each view's middle plane in its alpha (not a glTF normalTexture: it is in the
  impostor material's `extras.hifipushie_impostor.normal_texture_index`, and as `impostorNormalTexture` files in the
  seasons json). A picture per season (seasons with the same shape share the normal / depth / shade frames: only the
  albedo is rendered again). extras / the seasons json `impostor`: `frames`, `size` (each view's square, m), `centre`
  (glTF), `recipe` (the shader in words) and `shader`: `spikes/godot_veg/impostor_octa.gdshader` is a reference
  Godot 4 shader to drop in (uniforms from those numbers; MeshInstance3D.extra_cull_margin = size / 2, since the
  stored quad is a vertical square; no shadows received). `veg_impostor.view(atlas, direction)` draws in numpy what
  the shader draws (the tests hold the bake to it). Cost: ~4 min of Blender for the first shape of the plant (64
  views x albedo, normal, Cycles shade, depth), ~1 min for each further season. `impostor="cross"` keeps the old two
  crossed quads (any viewer draws them without a shader; from the side only): albedo + tangent-space normal map,
  front and back faces of their own, and the engine must not let the quads RECEIVE shadows (a dark wedge).
  Installing it in Godot 4 (what `spikes/godot_veg/octa.gd` does): (1) copy `impostor_octa.gdshader` into the project;
  (2) import `<name>_LOD3.glb` (the impostor LOD file) and read `<name>_seasons.json`: `impostor` = {frames, size,
  centre}, `seasons.<season>.impostor` = the season's `baseColorTexture.file` (albedo atlas) and
  `impostorNormalTexture.file` (object-space normal + depth); (3) make a ShaderMaterial with that shader and set
  `albedo_atlas`, `normal_atlas` (load the PNGs; generate mipmaps), `frames`, `size`, `centre`; (4) on the impostor's
  MeshInstance3D set `material_override` to it and `extra_cull_margin = size / 2` (REQUIRED: the stored quad is a
  vertical square, the drawn one turns to the camera and leaves that box from above, so without the margin Godot culls
  it while it is on screen); (5) leave casting shadows on, receiving off (the shader's render_mode already has
  `shadows_disabled`); (6) per season swap the two textures. `impostor="cross"` (export_plant) writes the old two crossed
  quads instead: any viewer draws them with no shader, from the side only.
  Measured (blobby oak, impostor vs LOD 2, three azimuths, orthographic, one sun): elevation 0 / 20 / 45 deg: coverage 1.01 / 1.01 / 1.02, luma 0.99 / 0.98 / 0.98, outline IoU 0.975 /
  0.939 / 0.910. The crossed quads on the same tree: coverage 0.96 / 0.92 / 0.66, luma 1.01 / 0.89 / 0.74, IoU 0.89 /
  0.84 / 0.63 (from a hill they read as a cross).
- **`<name>_seasons.json`** beside the GLB (written whenever there are variants). It LEADS with `contract`
  {"version", "changes" per version, "rule"} and `slot_list` [{"slot", "on": [{"mesh", "primitive"}], "hidden_in":
  [seasons], "channels": the vertex attributes on it}]: an engine that maps materials by slot name should refuse a
  version or a slot it doesn't know (a new slot drawn by default was how `bark_forks` showed in summer). Then:
  variant -> per material slot (the default material's name: bark, bark_forks, foliage, foliage_boughs<k>, impostor)
  its baseColorFactor, roughness, alpha mode and cut-off, `hidden`, `receive_shadows` (when false), and the base
  colour and normal pictures (image index in the GLB + the same PNG written beside it). For engines that drop
  KHR_materials_variants.
- **The export contract** (`veg_export.CONTRACT`, in the GLB's extras.hifipushie_plant.contract and the seasons
  json): version 10. 1 = slots bark / foliage (/ foliage_boughs<n>) / impostor, wind channels, COLOR_0, variants,
  collision file, seasons json. 2 = styled deciduous plants add slot `bark_forks` (the wood mesh's second primitive:
  hidden except in bare seasons); impostor pictures per season. 3 = impostor normal map + TANGENT + 16 vertices, its
  second picture no longer mirrored, baked shade; seasons json contract + slot_list + normal PNGs. 4 = style anime
  (leaf-cloud foliage: alpha-MASK cards with a dab atlas, TEXCOORD_3 = (clump gradient, clump id), Godot CUSTOM0.zw);
  seasons json `snow` numbers + `style`; impostor shade eased on bright colours. 5 = the `snow` variant of a
  leaf-dropping plant is its WINTER state (foliage hidden, `bark_forks` shown), not the crown painted white. 6 = the impostor
  is hemi-octahedral (one quad turned by the engine's shader, an N x N atlas of views, object-space normal + depth in
  `extras.hifipushie_impostor`, `impostorNormalTexture` files, the seasons json `impostor`, null for a plant exported
  without one: small plants); `impostor="cross"` = 5's quads;
  slot `heads` carries COLOR_0 (each part's colour: petals / dab / ball, the flower's centre, the stalk) under a white
  baseColorFactor. 7-9: see CONTRACT_LOG (ramp textures, cropped impostors, pixar's foliage_cards). 10 = the
  groundcover GRADE of small plants (its own folder; one `foliage` slot of single-sided alpha cards with TANGENT +
  a normalTexture per season, no COLOR_0; see "Groundcover grade"). Whoever adds,
  renames or re-purposes a slot or a vertex channel bumps the number and adds a line to CONTRACT_LOG and here.
- What importers do with the file (checked: Blender 5.1, Godot 4.7; Unity and Unreal are NOT checked):
  Blender brings in every node (hide LOD1+ and `_collision`), flips v on every uv set (branch = 1 - uv1.v, flutter =
  1 - uv2.v; `_WIND` arrives unflipped as an attribute) and reads the variants. Godot (4.x) imports the scene's nodes only
  (LOD 0 of the combined file: use the `_LOD<k>.glb` files; a node outside the scene, the collision mesh, never
  arrives: use `<name>_collision.glb`), keeps TEXCOORD_1 as UV2 unflipped and TEXCOORD_2 as CUSTOM0, drops `_WIND`,
  drops KHR_materials_variants entirely (only the default season's materials arrive: read `<name>_seasons.json`), and
  its default material ignores COLOR_0 (switch vertex colour on: a style's mass tones live there).
