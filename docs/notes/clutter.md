# hifipushie notes: clutter

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

## Clutter kit (2026-10-08/09, "clutterkit" agent, branch `worktree-agent-af12ac948388331b2`; sheets `workspace/veg_renders/ck_*`)

The consumer (pushieworld notes 110) had never drawn the terrain export's clutter.csv: no assets for its kinds. Now:
`clutter.py` + `clutter_presets/*.json` (boulder, river_rock, cobbles, slab, driftwood, bush, litter) + `clutter_styles/*.json`
(realistic, blobby, anime, cartoon, pixar) + `blender_clutter.py` (looks) + the `reed` plant preset (groundcover grade).
Tools `make_clutter`, `look_clutter`, `clutter_kit`; `guide(topic="clutter")` = `clutter_guide.md`; `tests/test_clutter.py`.
Deliveries: /mnt/data/hifipushie/vegstyle/<style>_<kind>/ (35 folders, "realistic" -> "real") + <style>_reed_ground/ +
clutter.json (terrain kind -> folder per style, instance rule). CONTRACT 13 = grade "clutter" (plants unchanged).
Scratch DURABLE in /mnt/data/hifipushie/clutterkit/: run.sh <script>, ex.py <root> <kinds> <styles> (export), go.sh <tag>
<kinds> <styles> (export + sheet), kit.py <root> (everything + sheets per kind), mkstyles.py / mkpresets.py (the style and
preset JSON are WRITTEN from these: edit there, re-run with the target dir), scat2.py <folder> <png> (nine instances close,
in the ground), scatter.py, gd.py <tag> <style> <boulder root> <bush root> <lod 1|0> (Godot field), v2.mjs (Khronos with
external images), prof.py / dbg1.py / dbg2.py (profile, a variant's decimation, proportions), reeds.sh, plant.py, fetchb.py
(reference photos into workspace/level_refs/boulders/), p1..p19.py (the patches as applied: history only).
- What existed before (asked by the consumer): a styled `shrub` exports through grow_plant + export_plant at 400 triangles
  but is one ball on a stalk and its LODs don't go down (anime 448 / 420 / 420, pixar 276 x3: style floors); boulders had
  nothing callable (terrain_ground places rows, blender_terrain's protos are render-only, fallen blocks live in the tiles'
  field). export_asset would take minutes of Blender per rock with no LODs.
- A rock = a signed distance (class `Stone`): 6-9 faces at oblique angles round an ellipsoid of three unequal axes (a golden
  spiral of directions, jittered; each face at 0.7-0.95 of the ellipsoid's reach), an off-parallel bedding pair, 1-2 corners
  broken deep + shallow chips, thin partings on tilted planes, a smooth max whose radius grows upward (`top_round`), wider
  low (`taper`), blended toward a bowed ellipsoid (`round`, `bend`), `split`, `dent`, a second block leaning (`lean`).
  The FIRST version (two joint families at right angles + level bedding with a mid-height setback) read as quarried
  bricks (the coordinator's call): a loose block is never a box. Far axis planes always cap it: few oblique faces left
  one side open (a 12 m "boulder", a 60-triangle dense mesh).
- Variants differ in PROPORTION (preset `variant_forms`: lump, flat block, tall wedge, split + leaning), not only seed;
  forms layer as preset < variant < style < spec (`_layered`), so a pebble style still rounds every variant.
- LODs: pyfqmr (several aggressiveness values, the nearest count that is closed and manifold: it overshoots far under the
  target on pebbles and stalls above it on crisp blocks, and can leave fins), back onto the field (Newton steps capped at
  3 cm: a far vertex's step left the form), outline IoU against LOD 0 from 8 directions written per LOD
  (`silhouette_iou`; under `LOD_IOU` 0.9 a single stone's LOD becomes its hull). The last LOD of a stone is a convex hull
  grown greedily (`_hull`: the point farthest outside is added until the count): at 30 triangles a decimator folded crisp
  blocks into shards. A cobble patch = a hull per stone, faces shared by surface (`cluster_lod`); driftwood LOD 1 / 2 and
  jams = built tubes (`wood_lod`: 5 / 3 sides). Thin things read low IoU honestly (driftwood 0.65-0.85, cobbles LOD 2
  0.5-0.9).
- The bake: ONE atlas (1024) per kind x style for all variants and LODs: six box charts a variant (`CHARTS`), a texel = the
  first surface a ray along the axis meets (found on the marching-cubes volume, refined on the exact field), so uv is a
  function of POSITION and nothing is unwrapped. Albedo (`_paint`), tangent normal against LOD 0's own interpolated
  normals (`_raster_normals`: baked against a smooth guess, flat faces with split normals shaded pillowy and dented),
  ORM; relief only in the maps (`_micro`: grain, fracture traces, laminae, pits, leaf bumps, bark). TANGENT is written
  (the chart's axes; w from the picture's up).
- Paint that made it read as rock: fracture traces = wandering PLANES cutting the stone, present along stretches
  (isolines of a noise drew closed worm loops), lichen crusts = cells merging into blotches at 45-75% opacity on tops and
  one weather side (small bright ones read as confetti), rain streaks down steep faces, a damp soil-stained foot band,
  each variant's mineral tone (`minerals`; at +-10% the stones were brown and blue: +-5%), `instance_tints` in the json.
  Rock matches its cliffs by a per-instance colour (json `clutter.tint`): terrain rock colour / color_linear x a tint.
- Bush, round 2 (the coordinator on the first one: "a solid mossy green lump with sprigs stuck on reads as a moss-covered rock"):
  `clutter_bush.py`: an OPEN bush from a grown shrub (vegetation.grow of the `shrub` preset, 1 m across; variants = height,
  stem count and lean): LOD 0 = its 6 stoutest stems as 3-sided tubes + 36-42 spray cards on k-means clusters of the
  plant's own twigs (a card runs the way its twigs run, faces out, inner ones take darker pictures: `bough_tile`), LOD 1
  = 7 bough cards whose pictures are the LOD 0 sprays composited in software into each bough's plane (`composite`:
  PIL perspective warps, far first) + 3 stems, LOD 2 = 2 crossed cards with the whole bush; ~260 / 64 / 8 triangles;
  58-67% of the side view is gaps; "cover kept" LOD 1 0.62-0.69, LOD 2 0.67-0.85 (alpha-aware IoU, `_mask`). Far pictures'
  alpha is grown 2 texels (`_fatten`) or they vanish under mipmaps. A card's back has its own vertices (Blender's
  importer merges two faces on the same three vertices: half the cards were missing in every look). Blobby / cartoon
  (`form.open` false): 3-5 separate closed lumps on stems (`Bush` lumpy mode, a hull per lump, stems appended as tubes
  with a bark patch in the atlas's last cell). The old dome path (`bush_cards`, `spray_tile`) is dead code kept for
  the lumps' field. Read: LOD 0 is a shrub in realistic / anime / pixar; LOD 1 reads as a small tree (boughs up top,
  bare stems); the leaves are hazel-like, not gorse needles.
  Light grey patches on the first bush's shaded side were sky sheen on a too-dark albedo at roughness 0.8, not holes.
- Reed (`vegetation_presets/reed.json`): the first one was ONE thin stem per card (0.37% of the atlas opaque, fill 0.05:
  near-invisible; test_vegetation's test_atlas_and_cards failed on main and I had not run it or looked at a reed).
  Now fans of 20 strap leaves (1.15 m x 5.5 cm, wider than life) + plume stalks with a 7.5 cm head: 2.7% opaque, fill
  0.24, 1.86 m x 1.02 m. Seen in Godot (ground.gd, 2 / 8 / 20 m): ck_14_reed_godot_vs_refs.png; reads as bulrush.
  RULE: the whole vegetation set (test_vegetation, test_veg_style, test_veg_groundcover, test_veg_impostor, test_veg_sward,
  test_clutter) before any report, and a picture of every delivered asset.
- `terrain_mesh.render_tiles(extra=[{glb, at, yaw, scale, squash, tint}])` stands GLBs in a tiles render (blender_tiles
  imports them, multiplies the tint into the base colour): boulders beside styled cliff tiles (scratch fam.py,
  sheets ck_16_family_<style>.png). render_tiles(clutter=0) raised KeyError 'clutter' on main (guarded).
- Litter (`litter_tile`, `_export_litter`): an 8-triangle domed octagon / a quad with an RGBA picture per season (the
  same patch, leaves added in autumn), hidden under snow.
- Engine (Godot 4.7.2, `spikes/godot_veg/clutter_field.gd`, 1280 x 720, 890M, shadows on): 5,000 boulders + 20,000
  bushes over 400 x 400 m as MultiMeshes per variant per LOD with the json's LOD distances and cull: 6,922 drawn,
  462k triangles, GPU 2.7 ms on a quiet GPU (4.5 with other jobs on it); cartoon 319k, 2.4 ms; all 25,000 at LOD 0
  with no cull: 7.0M triangles, 15-17 ms. Khronos validator: 515 GLBs (495 clutter + 20 reed), 0 errors, 0 warnings.
  A Godot script error leaves the process idle for ever under godot-quiet: always run with a timeout and log to a file.
- Kinds agreed with the "streambeds" agent (terrain_stream.py): scale = largest plan dimension in m (assets are 1 m at
  scale 1), squash RELATIVE, yaw 0 = +X, z = surface (pivot on the ground line, `sink_m` below); old `boulder` rows are
  sunk 0.12 x scale already. `sedge`, `tussock`, `tallgrass` map to <style>_grass_ground in clutter.json (no sedge preset).
- Open: the clutter bush close up; driftwood is plain (bark patches, broken ends and a root-plate variant exist, no
  splintered detail); realistic litter clusters in the middle; no `sedge` / pebbles / wrack assets; photo silhouette
  measures were read by eye (no traced masks); the consumer has not loaded any of it yet.
- Takeover read (2026-10-09, a fresh agent judging the sheets cold; scratch adds val_all.sh, tests3.sh; scratch
  scripts must be given to run.sh by ABSOLUTE path: it cds into the worktree):
  - ck_16_family_<style>: blobby / pixar boulders sit in their cliffs' colour family. CARTOON FAILS: the boulders are
    near-black charcoal with pale tops beside warm tan cliffs (the cartoon rock's dark facet tones x the tint; the
    cliff is lit by the terrain recipe's macro colour, the boulder by its own atlas): the tint recipe (terrain rock
    color_linear / kit color_linear) matches MEANS, not the tone range: a cartoon boulder needs its dark tone lifted
    or the tint taken from the lit cliff. Anime close: boulders paler and chalkier than the cliff, fracture lines
    read as ink scribbles. Realistic terrain has no style manifest: no tint is applied (rock colour None); the
    untinted boulders read a little greyer than the cliff: acceptable.
  - ck_14 reeds: blobby / cartoon read as bulrush (cartoon heads are tulip-sized balls); anime as sedge with seed
    spikes; realistic near is a dense ragged tuft and at 20 m a green blob with detached pixels; PIXAR is too thin
    (wiry blades, at 20 m a few specks: it will vanish in a field).
  - ck_15 bush: realistic / pixar LOD 0 read as open shrubs; LOD 1 at 10 m is a different plant (a few big leaf
    cards on bare stems: a sapling) and will pop at 14 m; anime leaves are hand-sized; blobby / cartoon are
    mushroom clouds on wire legs; none resembles the gorse / broom / heather references (no flowers, hazel leaves).

- Round 3 (2026-10-09, "clutterkit3", Pushieworld note 114):
  - `"snow": null` fixed: absent states are {} or say so (litter snow = numbers with coverage 0, hidden true), lists [],
    only text / file / single number may be null; written into CONTRACT_LOG[13] (number unchanged); test_no_state_is_null.
  - River rocks: 2 of 4 variants angular / broken (round <= 0.3), moss only on up-facing faces (`moss_up`) and per
    variant (`moss_vary`, some stones none). Wet: clutter.wet.row = "water" (csv column, m over the row's z) + `sink`
    column; streambeds3 asked to write them (terrain_stream.py writes neither yet).
  - Rock tone: `tone_range` step (clutter.tone_range) sets the pictures' mean to the stated colour and squeezes
    luminance p5..p95 into a cliff-like range. Cartoon family sheet ck_17: boulders now grey-tan in the cliff's family,
    no charcoal. Measured (scratch tone.py): kit p5..p95 0.6-1.5 x mean vs cliff textures 0.8-1.2: still wider than cliffs.
  - Bush: closed styles (blobby / cartoon) = gumdrop lumps standing on the ground (no stems). Open bush LOD 1 = ~42% of
    LOD 0's own sprays, x1.3 larger, growth capped so LOD 1 never rises past LOD 0's top (a tall low spray grown 1.3x
    stood 18% above the bush: test caught it).
  - Reeds: plume stalk radius 0.009 -> 0.014; pixar redone with clump width 0.095 (gdr/n_pixar_sheet.png): broad blades,
    a clump at 20 m, plume stalks break to specks at 20 m.
  - Closed bushes' last LOD 24 -> 44 triangles (bush.json lods): at 24 the greedy hull read as a box / a house shape at 40 m.
  - Delivered (/mnt/data/hifipushie/vegstyle/<style>_<kind>, clutter.json manifest, contract 13): Khronos 515 GLBs 0 / 0;
    tests: test_clutter 27 passed, test_vegetation + test_veg_style 63 passed. Sheet ck_10_bush_styles: open LOD 1 now
    the same plant (pop gone); the tall closed variant is still box-sided at 40 m.
  - Still wrong: no gorse / broom / heather look (hazel leaves, no flowers); pixar reed plume stalks dotted at 20 m;
    kit rock tones still wider than cliff textures; wet line needs streambeds to write `water` / `sink`; nobody has
    judged river rocks in the consumer's scene.
