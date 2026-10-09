# Clutter: the small things a terrain is scattered with

Boulders, river rocks, cobble patches, bank slabs, driftwood, low bushes, leaf litter, reeds. A terrain export
places them (`clutter.csv`: rows `x, y, z, kind, scale, yaw, squash[, place]`); this kit is what draws them, in five
styles, at budgets for tens of thousands of instances.

Tools: `make_clutter` (one kind in one style), `look_clutter` (a sheet at 2.5 / 10 / 40 m), `clutter_kit` (every kind x
style + the manifest). Reeds are a plant: `grow_plant` with species `reed`, then `export_plant(grade="groundcover")`.

## How prop artists do it, and how this follows

1. **Sculpt a high form**, in the rock's own language. Here the high form is a signed distance: a loose block is
   6-9 faces at oblique angles round three unequal axes (long : mid : short about 1 : 0.7 : 0.5), a pair of
   off-parallel bedding faces, one or two corners broken off deep and a few shallow chips, thin partings along tilted
   beds, arrises weathered by a smooth max (rounder on top than at the foot), wider at the base than above.
   Water-worn = the same block blended toward a bowed ellipsoid. A box with parallel faces and one bedding slot is a
   quarried block, not a boulder (the first version: see the lessons).
2. **Variants differ in proportion**, not only in seed: a lump, a flat block, a tall wedge, a split block with a
   second leaning on it (`variant_forms` in the preset). Three or four shapes turned, scaled and squashed per
   instance don't read as clones; four seeds of one proportion do.
3. **Decimate to LODs that keep the outline.** Each LOD's outline is held against LOD 0's from 8 directions (IoU);
   a single stone's last LOD is a convex hull grown greedily (the point farthest outside is added until the count is
   reached), which keeps a near-convex rock's silhouette at 30-44 triangles where a decimator folds it into shards.
4. **Bake the high form onto the low.** One atlas per kind x style holds every variant: six box-projected charts a
   variant (a texel = the first surface a ray along that axis meets). UVs are a function of POSITION, so every LOD
   reads the same picture and nothing is unwrapped. Albedo, tangent-space normal (told apart from LOD 0's own
   interpolated normals, TANGENT written), occlusion + roughness. Cracks, grain, laminae live only in the maps.
5. **Seat it in the ground.** The pivot is the ground line; `sink_m` of the mesh is below it (a quarter of a
   boulder's height), and the band above the line is baked darker (damp, soil-stained). A rock placed ON the ground
   looks placed.
6. **Scatter with variation**: yaw any, scale within the kind's `size_range_m`, squash 0.75-1.3, variant by the
   row's hash.

## Kinds

| kind | what | LODs (triangles) | collision |
|---|---|---|---|
| `boulder` | loose angular block: talus, field boulders | 300 / 100 / 44 | convex hull, ~24 |
| `river_rock` | water-worn, flattened, a mossy band above the water line, darker foot | 300 / 100 / 44 | hull |
| `cobbles` | a PATCH of 14-24 cobbles as one asset (lay patches overlapping) | 420 / 150 / 48 | none |
| `slab` | flat bank stone / ledge piece | 220 / 80 / 32 | hull |
| `driftwood` | log, forked branch, a butt with its root plate, a small jam (the four variants); broken ends, bark patches; scale = length | 220 / 88 / 24 (jam x2.3) | none |
| `bush` | low scrub, OPEN: stems + spray cards on a grown shrub's twigs -> ~40% of the same sprays, larger -> 2 crossed cards; seasons; wind (blobby / cartoon: closed lumps standing on the ground) | ~260 / 90 / 8 (lumps 270 / 100 / 24) | none |
| `litter` | a leaf / twig debris card; a picture per season; hidden under snow | 8 / 2 | none |
| `reeds` | the `reed` plant preset (fans of strap leaves + plume stalks, 1.9 m), groundcover grade (cards baked from the full plant) | 480 / 160 / 36 | none |

Gravel bars are the bed material's job (a terrain layer); `cobbles` patches are what stands proud of it.

## Styles

A style sheet (`clutter_styles/<style>.json`) changes the FORM and the PAINT; colours start from the terrain's rock
colour (grey [0.36, 0.34, 0.31]; give `color` for sandstone) turned by the terrain style's saturation / value.

- `realistic`: weathered blocks, cracks, lichen on up-facing rock; silver wood with grain; small-leaved scrub.
- `blobby`: pebble-smooth beans and potatoes with a soft dent, no cracks or beds, two soft tones; bushes are smooth
  lumps with no cards.
- `anime`: crisp planes, small bevels, painted strata bands along the (tilted) bedding, a pale top; bushes with big
  painted leaf dabs in three tone steps.
- `cartoon`: few big facets, a clear lighter top plane, a dark line along every arris; bushes as scalloped lumps.
- `pixar`: generous bevels, two big chamfers, a warm lit top with moss, darker foot; soft leafy bushes.

Override any number: `make_clutter("boulder", style={"sheet": "anime", "rock": {"paint": {"bands": 0.5}}})`, or
`form={...}` / `paint={...}` for one asset. Unknown keys are refused with the list of known ones.

## Form keys (rocks)

`aspect` [[mid/long], [short/long]], `faces`, `jitter`, `face_in`, `bedded`, `tilt`, `dip`, `tumble`, `chips`,
`broken`, `break`, `chip`, `bevel`, `top_round`, `taper`, `round`, `bend`, `dent`, `split`, `split_gap`, `beds`,
`bed_set`, `bed_thick`, `lumps`, `lump_size`, `sink`, `lean`, `cluster` {count, stone, pile}.
Paint: `tone`, `face_tone`, `speckle`, `edge_light`, `cavity`, `ink`, `bands`, `gradient`, `top_light`, `foot` +
`foot_tint` / `foot_color` (the damp, soil-stained band above the ground line), `top` (moss film on up-facing rock),
`lichen` + `lichen_size` / `lichen_colors` (crusts in blotches, on tops and one weather side), `streaks` (rain streaks
down steep faces), `minerals` (each variant's own rock tone), `moss` + `moss_band`, `ao`, `roughness`; bake-only relief `grain`, `cracks`, `laminae`, `pits`;
`normals` (deg: faces meeting sharper keep their own normals).

## What an engine gets

A folder per kind x style, beside the plants: `<stem>_v<k>_LOD<j>.glb` (one mesh, one material, textures by uri),
`<stem>_v<k>_collision.glb` (node name ends `-convcolonly`), `<stem>_albedo[_<season>].png`, `_normal.png`,
`_orm.png` (R occlusion, G roughness), `<stem>.glb` (all variants in a row, to look at) and `<stem>_seasons.json`:
the plant contract's shape (`contract`, `grade: "clutter"`, `kind`, `slot_list`, `seasons`, `snow` numbers) plus a
`clutter` block: `size_m` 1 (scale = the largest plan dimension in metres), `height_m`, `sink_m`, `size_range_m`,
`variants` (files, triangles, outline IoU, collision), `lod_switch_m` (x the instance's scale: LOD 1 from 14 m,
LOD 2 from 40 m, gone at 130 m), `wet` (darken, roughness, the band above the water line), `tint` + `instance_tints`
(ROCK MATCHES ITS CLIFFS BY A PER-INSTANCE COLOUR: tint = the terrain's rock colour where it stands / `color_linear` x
one of `instance_tints` x 0.92-1.08, multiplied into the albedo in linear RGB), `instancing` (one MultiMesh per variant per LOD; instance = T * Rz(yaw) *
S(scale, scale, scale * squash)). `clutter.json` at the root maps every terrain kind to its folder per style.

Bushes carry the plants' wind channels (TEXCOORD_1 = trunk, branch; TEXCOORD_2 = phase, flutter; `_WIND`) and are
alpha MASK (the dome is opaque: a far bush never thins to nothing; scale alpha by the mip level for the sprays).

`sedge`, `tussock` and `tallgrass` rows map to the grass tuft's groundcover grade (`<style>_grass_ground`).

Engine cost measured (Godot 4.7.2, `spikes/godot_veg/clutter_field.gd`, 1280 x 720, a Radeon 890M, shadows on): 5,000
boulders + 20,000 bushes over 400 x 400 m with the json's LOD distances and cull = 6,900 drawn, 462k triangles, GPU
4.5 ms; everything at LOD 0 with no cull = 7.0M triangles, 15-17 ms. Use the LODs and the cull.

## Judging

- 2.5 m: does it read as rock (or wood, or a bush) of THAT style, the same family as the style's cliffs?
- 10 m / 40 m: does the LOD keep the outline (the report's IoU: under 0.9 pops)?
- side by side: do the four variants differ in proportion? On terrain: are they IN the ground?
- Reference photos: `workspace/level_refs/boulders/` (erratics, field boulders, driftwood; licences in fetched.txt).
  Erratics and field boulders in them: height / width 0.5-0.75 (two tall eggs at 1.1), 5-7 outline corners, arrises
  rounded over about a tenth of the size, narrower at the top than at the base, sunk in the turf.

## Lessons

- Two joint families at right angles + level bedding = a brick. A loose block's faces are oblique; its beds tilted.
- A decimator at 30 triangles folds crisp blocks into shards and changes the outline between LODs (a pop). Hull.
- The normal map must be baked against the low mesh's OWN interpolated normals: baked against a smooth guess, flat
  faces with split normals shaded pillowy and dented.
- pyfqmr overshoots far below the target on smooth pebbles at high aggressiveness and stalls above it on crisp
  blocks at low: try several, keep the nearest.
- A form bounded by few oblique faces can be open on one side (a 12 m "boulder"): always cap with far axis planes.
- Fracture lines from a noise's isolines are closed loops (worm doodles). A crack is where a wandering PLANE meets
  the stone. Lichen as small bright dots is confetti: big, thin, merging crusts in two or three dull colours.
- Mineral tints of +-10% made brown and blue stones; +-5%.
- A script error in Godot under a hidden compositor leaves the process idle for ever: run with a timeout, log to a file.
- A closed leafy dome with sprigs on it is a moss-covered rock, whatever its texture (the first clutter bush). A shrub
  is OPEN: thin stems from the ground, foliage in separate sprays with sky and ground between them (60% of its side
  view is gaps), darker inside. Build it from a grown shrub: sprays on the plant's own twig clusters; the middle LOD is
  a SHARE OF THE SAME SPRAYS (spread over the bush, each a little larger, where they stood): bough cards composited
  from the sprays read as another plant (big leaf plates on bare stems) and popped at the switch; then two crossed
  cards FROM the whole; the last LOD casts no shadow (crossed cards shadow each other).
- Closed styles (blobby, cartoon): the lumps stand ON THE GROUND (round above, a tucked foot), never on stems:
  lumps on stalks read as mushroom clouds on wire legs.
- A rock's pictures must hold a CLIFF's tone range (`paint.tone_range`: luminance p5 .. p95 over its mean) and its
  stated colour as their mean, or a per-instance tint cannot land it beside its cliff (painted gradients, top light
  and ink spread a cartoon boulder over 0.15 .. 2.9 of its mean, 40% under its stated colour: charcoal with chalk tops).
- A card's back needs vertices of its own: two triangles on the same three vertices are one face to Blender's importer
  (half of every bush's cards went missing in looks, unnoticed until the two-card LOD showed one card).
- A plant's card must be FILLED by its picture: the first reed was one thin stem on a metre-wide card (0.4% of the
  atlas opaque: near-invisible in the engine, and test_atlas_and_cards failed). Look at every asset you deliver.
- A styled tree shrub at 400 triangles is one ball on a stalk; its LODs don't go down (style floors). A clutter bush
  is its own thing: an opaque leafy dome (blocks see-through, holds at any distance) + a few spray cards.
