# hifipushie notes: vegetation

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

## Vegetation (2026-10-05, branch `vegetation`; stages 1-2 of 6: trees, foliage, bark)

The user's track: game/video-ready trees, shrubs, grass, in styles from blobs to photoreal, with wind, seasons, LODs;
"start with a best-in-class tree algorithm", hero trees editable, forest sets, and "how do real artists work".
Research summary + plan: the first hand-back (SpeedTree's generator hierarchy with hand-drawn overrides, The Grove's
grow/bend/prune years, Palubicki 2009, Megascans atlases, proxy-normal blob trees, Nanite assemblies, impostors).
- `vegetation.py`: `grow(spec)` = a self-organising tree (Palubicki et al. 2009): shadow-propagation light on a voxel
  grid (cell = one metamer), extended Borchert-Honda allocation (`apical` per order = the continuing axis's share; the
  trunk's fades to `apical_old`), shoots = bud direction + light + tropism per order + `plagio` (pull to an elevation) +
  per-order `jitter` + forces, shedding by light per internode, pipe-model widths with a memory of shed wood, bend under
  weight that sets (`_pose`: each node's internode in its parent's rest frame + a bend angle that never decreases).
  Numba kernels (`_collect`, `_distribute`, `_pipe`, `_pose`, `_shed`); nodes are appended parent-first and compacted
  after shedding. Randomness is hashed from each bud's lineage key (`_child`, `_u`): same spec = same tree, and an
  edit changes only what it shades. Unit = `habit.unit` m per metamer; with `height`, an unedited run sets the unit
  first so guides/prunes stay in metres. 5-40k nodes grow in 0.3-3 s (first call compiles ~3 s).
  Direct controls (the main session's condition: what SpeedTree artists have): `guides` (a drawn path at ANY order:
  attaches to the nearest node at `from_year`, its nodes lie exactly on the path, pinned = never shed or bent, children
  regrow from it; a path from the origin at year 0 is the trunk), `prune` (box / sphere / above / `below` = clear the
  trunk), `envelope` (soft crown shape as shade outside it), `forces`, `environment` (light direction, wind = lean +
  windward buds suffer, `setting: forest` = a canopy rising with the tree, `neighbours`), `decay.min_radius` (a dead
  tree: thin wood has fallen), `habit.clear` (m of trunk that never branches).
  Presets: `vegetation_presets/*.json` (oak, birch, scots_pine, norway_spruce, weeping_willow), bundles of habit +
  leaves + colours; every key overridable, unknown habit keys raise.
- Judging by measure: `silhouette` (PIL, ms), `shape_measures` (width/height, bole, widest height, lopsided, porosity,
  profile), `outline_iou` (row-filled outlines at equal height, feet together), `branch_angles`, `reference_mask`
  (photo against sky: colour vs the row's background at the crop's edges; or a traced `polygon`), `match`,
  `fit_habit` (random + shrinking search of named habit numbers on IoU and ratios; ~1 min; how the presets were
  tuned: inverse procedural modelling, small). References: `workspace/veg_refs/` (README, masks.json).
- `veg_mesh.py` (tubes per axis with axis/order/along/radius/tan per vertex; `collar` flares a branch's first rings
  into its parent: a flare, not yet a welded fork), `veg_look.py` (`render`, `reference_sheet`: photo | outlines |
  clay | bare | in leaf | close-up + numbers; 5-12 s), `veg_tools.py` (plant.json + history in
  `workspace/plants/<name>/`). `tests/test_vegetation.py`. Renders `workspace/veg_renders/vg_*`.
- Species pass + first foliage (same day, the main session's order after seeing vg_01-09: "birch fails, spruce a pagoda,
  trunks too slim; pull stage 2 ahead"):
  - Girth: `habit.ring` = m of radius every living piece of wood adds a year, on top of the pipe model (the pipe model
    alone under-sizes a trunk under a sparse crown: oak 0.8 -> 1.7 m at 90 years with ring 0.0022).
  - Shadow weights: a leafy node shades by its internode's length. Without it short internodes (a spruce's 15 cm
    branch metamers, six leaf-years deep) shaded themselves to death: every branch a 3-node stub. A spruce also needs
    a narrow shallow shadow (`shadow` [0.03, 3, 2]: shade-tolerant) or the 45 deg pyramid under each whorl starves
    the tips of the whorl below, and branch metamers a third of the leader's (`length` [1, 0.32, 0.45], shoot_max 1):
    the cone's width is the ratio of the two growth rates.
  - `force_orders` (per order: how far wind and forces turn a shoot; trunk 0.15): a birch in wind 0.8 leans, it no
    longer lies down.
  - `veg_leaf.py`: `leaf_mesh` (shape ovate / triangular / lanceolate / lobed, length, width, lobes, fold, curl,
    petiole, serrate), `twig_mesh` (a short shoot with leaves by its own arrangement, or needles: `needle_tuft` round
    the shoot's end, `needle_spray` = a flat spray with side shoots; per-vertex tone, leaf ids, wood/leaf material per
    face; variants by hash), `place` (a twig ends every young shoot, more along shoots born within `twig.steps`:
    per_m, golden angle, spread, up; `where: "ends"`). Mesh needles are far wider than life (`needle_width`): a
    1.2 mm needle is sub-pixel at any view of a tree, and a spruce is its needle surface. Counts: 12-35k twigs,
    2-40M instanced triangles, 4-11 s in EEVEE.
  - `blender_vegetation.py`: twig protos per variant instanced on point meshes (Geometry Nodes; rot/size/tint
    attributes; the leaf shader reads `col` + the instancer's `tint`, Principled mixed with Translucent); bark
    without UVs = a 3D noise stretched along each branch by the mesh's `tan` attribute (kinds furrowed / lenticel /
    plates; `base_color` under `base_height` = a birch's black foot, `upper_color` above `upper_from` = a pine's
    orange crown wood, `twig_color` where thin). View transform Khronos PBR Neutral (AgX and a strong blue world
    greyed everything).
  - Fit: `fit_habit` now also charges bole misses harder, `droop` (shoot ends hanging under the crown's base, away
    from the trunk) and, for winter photos, branch directions: `line_directions` (structure tensor: angle from the
    vertical of the lines in an image) on the photo inside the tree's outline (`photo_branch_directions`) vs on our bare
    silhouette at the same pixel scale (`tree_branch_directions`). Honest limit: the photo's measure is full of
    fine level twigs we don't have (oak photo p50 53 deg from vertical, ours ~24): it pulls the right way but the
    numbers don't meet.
  - Presets after the pass: oak (IoU 0.88, plagio 0.34 toward ~4 deg: level heavy limbs), birch (leader 1, apical
    0.63, hanging orders 3+, twigs hang), scots_pine (needle tufts on 3-year shoots, orange upper bark), norway_spruce
    (above), weeping_willow (trunk loses its lead early, scaffold at 45 deg, orders 2+ hang).
- Lessons so far: the raw shadow grid's gradient stacked shoots in voxel layers (smooth it, cap the pull); a
  normalised light pull and a sag constant 1e5 too big made everything curl; straight shoots read as a broom whatever
  the outline (oak needed jitter 0.4 on its limbs; the trunk keeps 0.14); the fit happily droops limbs to the ground
  to fill an outline: check bole and the clay view, not IoU alone; a tree doesn't read without real twigs and leaves
  (the stand-in sprays failed birch and pine by eye; the same skeletons pass with twigs).
- Cards, bark maps, forks, look (same day; the main session after vg_10-16: "spruce and pine need needle MASS", "a
  real sky and sun so the judgement isn't of a diagram"; renders vg_20-25):
  - Atlases + cards (`veg_leaf.atlas`): each card variant's twig rasterised from above in numpy/PIL (painter's order by
    height; `rasterize`: colour with the alpha's edge bled outward, alpha, tangent normal, mask R = light comes
    through / G = roughness / B = shade), 4 variants in a 2 x 2 atlas (768 px); `card_mesh` cuts a convex polygon of
    <= 7 corners round the alpha (`_enclose`: drop the edge whose neighbours meet nearest), a cupped fan in the twig's
    frame, `cross` 2 for tufts. `leaves.card` = what the PICTURE is made from (`card_spec`: a card can afford 400-500
    true-width needles and a 3-year fan with `sub_shoots`; a mesh twig can't): that is where the conifers' mass came
    from. `render(foliage="cards" | "mesh")`, cards the default: 7-14 triangles a twig, 90-300k foliage triangles a
    tree (mesh twigs: 2-40M). `fill` (alpha / card area) is reported: 0.3-0.5 on oak/pine/spruce, 0.13-0.22 on the
    long thin birch and willow twigs (overdraw to fix: cut those cards as strips).
  - Colours in plant specs are sRGB like the rest of the repo; `blender_vegetation.lin` converts. (They were being fed
    to shaders as linear; and `rasterize` once converted them a second time: pale teal spruce.)
  - `veg_bark.py`: bark as tiling maps on the torus (FFT noise + Voronoi with wrapped distances): furrowed (tall
    interlacing ridges), plates (flaky plates between cracks), scales, lenticel (dashes and peeling bands round the
    stem); height, normal, albedo multiplier, roughness; tile sizes in metres. `veg_mesh.tubes` now has `uv` (u round
    the branch in WHOLE tiles, v along it in tiles; a doubled seam column). `bark.base_kind` = a second map set under
    `base_height` (birch: furrowed black foot). The colour zones (base / upper / twig) stay shader mixes.
  - Forks: `tubes(weld=True)`: the collar's first ring is carried back along the branch onto its parent's surface
    (ray-cylinder), so a branch starts on the bark, flared. Not shared topology: a seated fork, no blended normals.
    `tip` tapers shoot ends.
  - Look: Blender's sky texture with its sun where the lamp is, a grass-toned ground to the horizon, the sun set per
    view from behind the eye's left shoulder; a shadowless upward "bounce" lamp (EEVEE has no bounce: foliage in shade
    lit by the sky alone went blue). Perspective views (`eye`/`look`/`fov`): the sheet adds "from 70 m" and "from 5 m".
  - Birch: straight dominant trunk (jitter 0.04, apical 0.66, leader to 0.9), fewer scaffold limbs (`bud_break` 0.4
    on the trunk), ring 0.0024.
- Lessons so far: the raw shadow grid's gradient stacked shoots in voxel layers (smooth it, cap the pull); a
  normalised light pull and a sag constant 1e5 too big made everything curl; straight shoots read as a broom whatever
  the outline (oak needed jitter 0.4 on its limbs; the trunk keeps 0.14); the fit happily droops limbs to the ground
  to fill an outline: check bole and the clay view, not IoU alone; a tree doesn't read without real twigs and leaves;
  mass in conifers comes from the card's picture, not from more geometry; judge colour only under a sky with a
  bounce, and check the colour space before blaming the light.
- Tools (same day; the main session: "MCP tools + guide first: an LLM can't use any of this yet"): `grow_plant`
  (spec or merge patch -> saved version -> report; "" lists plants and presets), `edit_plant` (ops: guide,
  remove_guide, prune, clear_prunes, envelope, force, clear_forces, set "habit.apical.0"), `look_plant` (views clay /
  bare / leaf / far / near / close, or the reference sheet), `plant_reference` (photo + crop/foot or traced polygon,
  optional `fit`), `export_plant`, `plant_history`; `guide(topic="vegetation")` = `vegetation_guide.md` (stages:
  reference, skeleton, direction, foliage and bark, export; the habit table; what goes wrong).
  `veg_tools.report` measures the grown plant (form on its own silhouettes, limb angles, twigs, each guide's order /
  reached its end / branches from it, the reference match) with WARNINGs. `examples/plant_tool.py` calls the tools
  from a shell. `veg_export.write_glb`: `wood` (bark colour x albedo, normal, roughness, REPEAT) + `foliage` (every
  card realised into one mesh, atlas with alpha MASK, double sided, COLOR_0 tint), Y up, textures embedded, Khronos
  validator 0 errors (2 warnings: no tangents). One LOD, no wind/seasons yet.
  Strip cards (`card.strips`): a ladder of quads along a long twig; it gives hanging twigs their droop but did NOT
  raise fill (birch 0.25, willow 0.23): the pictures themselves are sparse between the leaves.
- Blind rounds (2026-10-05; fresh agents with only the guide + a brief: old pollard willows by a ditch, a wind-flagged
  pine, a veteran oak, a stand): what they could not say became vocabulary, what misled them was fixed.
  - `cuts` (`{"year", volume, "every", "until_year", "sprouts"}`): the wood in the volume is cut AT that year and each
    stub (the 12 stoutest) sprouts: pollards, coppice, lopped limbs, storm breaks. `prune` with `from_year` = held
    for ever; without = a cut after growth. Volumes: box, sphere, above, below, under. Unknown keys anywhere are
    refused (`resolve`): a tester's `prune.until_year` had been silently ignored.
  - `habit.angle` is indexed by the PARENT's order (angle[0] had been unused: testers set it and nothing moved);
    a side shoot's first segment keeps its angle (0.2 weight of light/tropism/jitter). Jitter has momentum
    (independent kicks read as wire kinks). `trunk_diameter` + `trunk_taper`, `habit.clear` (also on a drawn trunk),
    guide `bare` / `on` / `until_year` (paces the axis to the path's end), envelope "umbrella" + `center` + `lean`.
  - A guide that leaves existing wood must not clear that wood's tip: it killed a young trunk's leader (half trees).
  - `veg_export.budget` (wood min radius + card keep share solved for the triangle count; the count written is the
    count asked, e.g. 11994/12000) and `look_plant(triangles=)` renders that object: the full-detail look had said
    nothing about what a 12k export looks like. Looks: file names carry azimuth/budget, a ruler pole, water level,
    the eye lifted onto a hillside, `look_plants` in real coordinates. Edit echoes are diffs of the RESOLVED spec.
  - The report measures cover above the crown base (the trunk had counted), trunk lean, each guide's reach, each
    cut, and warns on a prune that removed everything, `height` with a drawn trunk, an age far past the preset's.
  - Not built (said in the guide): buttresses/roots/foot on a slope, swollen pollard bolls, deadwood beyond stubs,
    banks/ditches, a non-weeping willow preset, needle and willow card pictures (feathers, bamboo), an ortho side
    view that isn't mostly hillside on a slope.
- Named limbs, Blender, sets (2026-10-05/06): `vegetation.limbs` (first-order limbs by compass + rank, each with a
  lasting id `limb_id(key)` "Lk7f3" from its bud's lineage; `stout_path` = a limb as the eye follows it: the growth's
  own axis often ends a metre out). `take_limb` -> a guide with `replaces` (the bud's shoot is not grown beside it).
  `veg_tools.sync/pull` + `blender_vegetation.add_curves/read_curves`: plant.blend with guides and limbs as stamped
  Bezier curves; pull must be idempotent WITHOUT a re-sync (compare against the spec too) and take_limb ops resolve on
  the tree as it stood before the batch (earlier ops regrow it: the wrong limb was taken). `spec.set` -> `variants`
  (`name#k`, hero edits dropped), one GLB with shared materials.
- Species pass: a card is a SPRAY (`twig.side_shoots`, side_angle/length/taper, needle `spray_angle`): one shoot per
  card read as bamboo/ivy. `habit.tip_life` (spruce branchlets hung for metres: a witch's hat), `habit.uneven`
  (ragged outline). Bark tiles: >= 3 round any branch, the pattern scaled with it. Cut `boll`, `dead` (limb or volume;
  barkless grey; `tubes` carries `dead`/`node` per vertex), `roots` (lobed section at the foot), the trunk 0.3 m under.
- Foliage colour by measurement (`scratch hsv.py`: lit/shade HSV of leaf pixels, photo vs render): we were V 0.43 /
  hue 85-117 against a photo birch's 0.69 / 58. Causes: the atlas's median leaf was 0.7 of `leaves.color` (tones x
  blade shade x mask shade: now normalised to it), cards lit by their own normals (now bent out from the crown,
  `leaves.round`, in looks and in the export's normals), AgX (now Khronos PBR Neutral), cold presets. After: birch lit
  (73, 0.46, 0.61), willow (76, 0.55, 0.75) vs photo (69, 0.35, 0.87); shade hue still 20-40 deg colder than photos.
- Budgets (`veg_export.budget`): rings and sides first (`tubes(simplify=)`, RDP by radius), then the thinnest axes;
  `protected` wood (dead, guides) stays to a quarter of the cut-off (absolute protection was 23k triangles of antlers);
  `pick_twigs` draws twigs standing on kept wood first and reports `floating`.
- Stage 4 (`write_glb`): LODs 100/45/18% + an impostor (two renders, crossed quads), MSFT_lod + `<name>_LOD<k>.glb`;
  wind = TEXCOORD_1 (trunk, branch), TEXCOORD_2 (phase, flutter), `_WIND` (`wind_nodes`); `wind_plant` =
  `blender_veg_wind.py`: Blender's own importer + the shader recipe per frame (also the importer check: all nodes come
  in, v flipped on every uv set, `_WIND` an attribute; Godot 4.7: scene nodes only, UV2 unflipped, TEXCOORD_2 ->
  CUSTOM0, `_WIND` dropped; Unity/Unreal unchecked). Seasons/snow/wet: spec states for looks (`_weather` on the
  finished materials) and KHR_materials_variants in the export. Collision: capsules + a low mesh. Khronos: 0 errors.
- Foliage direction + species pass 2 (2026-10-06): the user saw "all the leaves on top of the branches"; measured, no
  card had a normal below horizontal (71-85% faced up). `twig.face` (twigs rolled round their shoot), `twig.light`
  (blades to the sky vs as the bud set them), spiral `divergence`, `twig.needles` radial / fascicles / ranked,
  `leaves.retention` (years). Arrangement comes from flora TEXT and plates (workspace/veg_refs/botanical/), not photos:
  guide table "from a botanical description to our keys"; divergence fractions and light values are marked assumptions.
  Oak's level bands were the growth model: the shadow pyramid ended at its depth, light returned there and the next
  layer formed (`_shadow` now fades below it; `habit.shadow_tail`, 0 for spruce: with the tail its skirt went bare).
  Blue-black bark = the sky's fill: the world lights plants with the sky 70% greyed, the camera sees it blue.
  `cluster_leaves`: under a quarter of the twigs drawn, a card shows a bough (spread per crown cell, 35% wood).
- HANDOVER (2026-10-06, the agent's context was full; a fresh agent should take over from here). Branch `vegetation`
  = main 79e4ebe + this note. How to work: `guide(topic="vegetation")` first; presets in
  `src/hifipushie/vegetation_presets/`; a species sheet = `veg_look.reference_sheet(spec, {"image", "mask", "credit"},
  out)` with masks from `workspace/veg_refs/masks.json` (oak_winter_b, birch_a, pine_b, spruce_a, willow_a); quick
  silhouettes = `vegetation.silhouette`; fit = `vegetation.fit_habit(spec, reference_mask, {"habit.key": [lo, hi]})`
  (~1-2 min); leaf HSV vs photo and card-normal histograms were scratch scripts (re-write: 30 lines each).
  The coordinator's order: (1) weeping willow and Scots pine against the NEW whole-tree photos (veg_refs willow_f,
  willow_e, pine_c, pine_e: trace a `polygon` mask for each into masks.json, they have none): willow = broad rounded
  crown on a short stout trunk, arching scaffold, curtains from the crown's outside, bottoms uneven and off the
  ground, NOT the preset's dome envelope over a column (remove `envelope` from weeping_willow.json once the habit
  spreads by itself); pine = a few stout crooked limbs, foliage plates in clumps, orange trunk continuing into the
  crown, thicker trunk (ring / trunk_diameter), plus a younger conical one; (2) pine card as crossed bottlebrush
  tufts judged at 2 m against botanical/plate_pine.jpg; (3) white_willow re-render (preset changed after its last
  sheet); (4) wet smear, snow on ground and limbs, wind measured by vertex displacement, the 8k pine set and the
  three forest-kit trees re-run; (5) stage 3 small plants + palm, stage 5 styles, terrain integration. Report at each
  mergeable point with an all-species sheet (vg_36_all_inleaf.png was made by cropping each sheet's lower row).
- Vegetation 2 (2026-10-05/06, branch `vegetation2`, renders vg_60-62; scratch scripts in the worktree's untracked
  `scratchpad/`: q.py one look, sweep.py = silhouettes of habit variants in a column (the fast loop: 1 s a tree),
  sheet.py / allsheet.py <tag> = the species sheets + `vg_<tag>_all_inleaf.png`, sprdiag.py = limbs by height band).
  Masks traced for willow_f, willow_e, pine_c, pine_e (masks.json).
  - Weeping willow: the mushroom was hanging orders that grew for ever with `shed` 0 under a dome envelope. Now no
    envelope: scaffold `plagio` toward 50 deg, the order below the curtains level (22-25 deg, `tip_life` 12), hanging
    orders with `tip_life` 8 / 6 and `uneven` 0.5, `shed` 0.05, `prune under 1.2` (browse line). Order 2 with a
    negative elevation ran straight to the ground as spokes. IoU 0.79 on willow_f; reads as a weeping willow.
  - Scots pine: `habit.bud_each` (bud_break drawn per bud: with it per node, whole whorls of four broke or none =
    a pagoda of tiers on a bare pole), trunk `apical` 0.72 so it runs on through the crown, `pipe` 1.95, 11 limbs,
    bark `twig_radius` (orange only on wood over 5-14 cm: every thin branch orange read as a fan of sticks).
    Card = a bottlebrush tuft: `twig.fascicle` 2 (pairs), `needle_angle` [75, 30], `bud`, `card.cross` 2 + `card.end`
    (a third card across the shoot with the tuft seen from its tip, its own atlas cell, a shallow cone).
  - Norway spruce's cage of brown hoops (the user's arrows), by measure (sprdiag): lowest limbs 32 cm thick under a
    60 cm trunk (`ring` added to ALL wood: now per order, [0.003, 0.0005, 0.0002] -> 8 cm), foliage only on the last
    17-20% of each limb (branchlets stopped at `tip_life` 7; given longer life they hung 4 m: `habit.slowing` = an old
    axis's segments shrink, so branchlets creep and their needle-bearing ends stay by the limb: foliage from ~45%),
    twigs 20 per m, cards x1.15. Before/after with the photo: vg_62_spruce_cage.png. Cost: 60k nodes, 42k twigs,
    Blender 45-120 s. Honest read: the cage is gone, but the cone is now too even and solid (no tiers, no dark gaps).
  - White willow: vigour 6.5, shed 0.035, crooked limbs: a small vase-shaped tree, thin.
  - Small-plant groundwork in veg_leaf (not yet used by a plant): leaf shapes linear / strap / round / petal, twig
    arrangements `basal` and `pinnate`, `taper`, `flower` (ray / cup / spike, own colours through a per-vertex `rgb`),
    `leaves.parts` (several pictures in one atlas: `part_specs`, `part_cards`, `card_variant`), `tree["twigs"]`
    (a plant that brings its own card placements).
  - Looks: snow / wet lie on the ground too; `wind_plant` reports displacement in metres per class of vertex
    (foot, trunk top, limb ends, leaf tips) and how far the limbs swing in step, with warnings.
  - Round 2 (vg_63-66): spruce on 2-year steps (`years_per_step` 2, `unit` 1.0: whorls 1 m apart ARE the tiers; 14k
    nodes, 16k twigs, was 60k / 42k), limbs droop and turn up, twigs lie flatter (`face` 0.75). `bud_each` + strong
    `uneven` on the spruce gave juniper lobes or a ragged column: not used. Pine: `apical_old` 0.46 from 40% of its
    age (the bare leader spike was a trunk tip that kept its lead while its whorls rarely broke), limb jitter 0.42.
    Willow: twigs 8.5 per m, cards x1.2; two buds per node on the hanging order starved it into a table with three
    tassels (reverted). Snow: on every card that faces up (by the crown's direction alone only the tree's top went
    white); wet leaves 0.75 x roughness (0.4 x mirrored the sky: grey smears). Bough cards drop the end-on card.
    Wind on a 20k birch: foot 0, trunk top 31 cm, limb ends 25 cm mean / 55 most, limbs in step -0.2.
    FAILS at low budgets: 8k pines (vg_63_pine_set_8k) and a 12k forest spruce (vg_63_forest_kit_12k) are heaps of
    fern / palm-frond cards: `cluster_leaves` enlarges a twig's picture, it does not show a bough. What artists do:
    bake a real limb end (its branchlets and twigs) into the card. Not built.
  - Bough cards (`veg_bough.py`, 2026-10-06; the coordinator: "bake real limb ends, hierarchy by LOD"; sheets
    vg_67_lods_*.png = full | 20k | 12k | 8k at 30 m and 100 m, vg_68_sets.png): `subtrees` (twigs carried and reach
    along the wood per node), `plan(tree, cards)` = the smallest bough size whose roots (reach <= size < the
    parent's) number no more than the budget's cards: every twig belongs to one bough; `atlas` bakes 4 of the tree's
    own boughs (60-97th percentile by twigs x length) with `veg_leaf.rasterize`, each from its FACE and from its SIDE
    (two crossed cards, 14 triangles); `place` stands a card on every bough root, scaled by its length against the
    picture's. A bough's face = the plane its twigs spread in (PCA; thinnest axis): from above only, a spruce's
    hanging combs were slats of a blind. `budget` sets `boughs` when keep < 0.25 (trees only; clumps keep
    `cluster_leaves`); write_glb and the looks take them through `foliage_mesh(tw=)`; seasons through
    `season_atlas(make=)`. Wood `simplify` tolerance is capped at 12 cm of radius (a budget straightened the pine's
    sinuous trunk). Read: oak at 8k ~ the full tree at 100 m; pine good; spruce recognisable but gappy, a big card on
    its leader. Not done: twig cards on top of boughs for mid LODs, depth / subsurface maps beyond the twig maps.
  - Stage 3, small plants (`veg_small.py`, sheet vg_70_small_plants.png; guide section "Small plants"): ASSEMBLED,
    not grown: `"plant": "clump"`, pictures = `leaves` + `leaves.parts` (one atlas), arrangement = `clump.layers`
    (part, count, ring, lean, scale, facing, stem / stem_radius / bend / tilt, on + along, trunk; `clump.size`).
    `grow` returns a tree-shaped dict (a tiny skeleton: stalks; `twigs` = its own card placements; `free` = stalks
    that start at their own foot, read by `veg_mesh.tubes`), so looks, budgets, wind and export are the tree's.
    Presets meadow_grass, fern, daisy, clover, feather_palm; `shrub` is grown (`habit.stems` 6 + `stem_angle`).
    Clump normals lean up (`leaves.normals`), each card bends from its foot in its own phase (wind). Tools:
    grow_plant / get_plant (layer keys) / look_plant (atlas | side | stand | above for a clump) / export_plant work;
    report = `veg_tools._report_clump`. Read: all six read as what they are; fern thin, daisy leggy, clover sparse,
    palm trunk a plain pole, grass seed heads too big. Not built: scatter on terrain, GPU blade grass, ivy, reeds.
  - Ground + where it stands (2026-10-06, the user: branches went through the ground; forest-interior conifers are
    bare below a live top; sheet vg_71_open_edge_interior.png): `vegetation.ground_at` (environment.ground level /
    slope): wood under it is laid along it at the end of `grow` (stats `on_ground`), `veg_leaf.place` lifts twigs
    whose tips would go under. `environment.setting` "open" | "edge" (+ `open_side`) | "forest": `habit.stand_shed`
    is added to `shed` inside a stand (spruce 0.17: skirt in the open, live crown in the top half in a stand),
    `habit.dead_keep` years (spruce 30, pine 10, oak 8, birch 3): first-order limbs the shade killed are remembered
    in the shed step (`dead_log_`) and put back at the end as thin grey drooping 3-node stubs (`dead` wood).
    Read: the three forms are plainly different and right in kind; stubs are pale straight spikes (no twigs, no
    lichen), the edge spruce shows bare live limbs on its closed side, the stand from inside is sunlit with a
    lawn floor. No forest-interior photo was fetched to put beside it.
  - HANDOVER (2026-10-06, context full). Branch `vegetation2` (see git log; main merged in at 6f996de). Scratch
    scripts are in this worktree's untracked `scratchpad/` (q.py, sweep.py, allsheet.py, sprview.py, lodsheet.py,
    small.py, forest.py, kit.py, sprdiag.py, setpreset.py): copy what you need. NOT DONE, in the coordinator's order:
    (1) spruce LODs: cap the leader's card, an inner core of darker cards near the trunk, faster atlas (PIL
    rasterising 1900 needles x hundreds of twigs: 95-190 s; rasterise each twig variant once and composite);
    (2) pine leader spike across a set's ages / seeds (cause: bud_break 0.15 leaves young tops bare; fix = every
    whorl breaks and lower limbs are shed by shade: a re-tune); (3) the forest-kit picture with trees side by
    side (pass `at=[[-18, 0], [0, 0], [18, 0]]` to look_plants in scratchpad/kit.py); (4) twig cards on top of
    bough cards for mid LODs; (5) spruce width (photo w/h 0.58) and ground-hugging lowest limbs, pine limb girth
    at the trunk, snow thickness / drift; (6) dead stubs with twigs and lichen, a dark forest floor in stand looks,
    a forest-interior photo; (7) stage 5 styles (blob to photoreal), terrain integration (scatter, slopes).
    The all-species sheet vg_66 predates the forest/ground changes (spruce shed, dead_keep): re-render first
    (`scratchpad/allsheet.py <tag>`).
  - A sheet is not a heavy job (one EEVEE Blender): waiting for `resources.heavy` behind a cloth sim cost 25 min.
- Vegetation 3 (2026-10-06, branch `vegetation3`; scratch in the worktree's untracked `scratchpad/`: audit.py <tag>
  (ground audit of all six trees at full / 20k / 12k / 8k + GLB), gshot.py (ground-level shots, one camera per species
  kept in g_cam_*.json), gsheet.py (before / after sheet + table), sil.py (side silhouettes of spec patches, 1 s a tree),
  commons.py (Wikimedia Commons search / fetch with licence lines; it is rate-limited: one query at a time)).
  - The ground (the user on vg_72: spruce limbs and willow curtains "clip through the ground: placement or tree?").
    Measured (`veg_ground.audit`, sheet vg_81_ground_before_after.png, table vg_81_ground_table.txt): NOT placement
    (the foot is at the look's ground plane) and not wood (0 limb vertices under it on every tree and path: the old
    end-of-growth clamp held). It was CARDS: a card is a polygon round its anchor and a hanging one reaches its whole
    length below it. Spruce: 145 of 15.9k twig cards up to 333 mm under at full detail, 24-39 bough cards up to 0.97 m
    under at 20k / 12k / 8k, the same in the exported GLB's three LODs. Weeping willow: 57 twig cards up to 1.16 m under,
    16-27 bough cards up to 1.96 m under. Oak, birch, pine, white willow: nothing within 1 m of the ground.
  - `veg_ground.py`: `clear(spec, tw, cards, var)` = placements with no card corner under `leaves.clear` m (default
    0.03) over `vegetation.ground_at`: turned up about its foot (not a hanging card), shortened to >= 0.4, or left out;
    called for twig cards, twig meshes and bough cards in `veg_look._plant_job` and `veg_export.foliage_mesh` (so
    looks, budgets and every LOD of the GLB). `audit` (what a look / export draws at a budget), `audit_glb` (the file
    read back), `report` (the `ground:` line + WARNING with counts) in grow_plant's report (cards only once the atlas
    exists: `veg_tools.ground_lines`), look_plant(triangles=) and export_plant. View "ground" (eye 1 m, 8 m from the
    lowest foliage). Clumps are not cleared (their cards stand on the ground).
  - Growth: `habit.ground_clear` (m, default 0.05; spruce 0.6, weeping willow 1.0 with `leaves.clear` 0.3): a shoot
    never grows under it; a hanging one (steeply down, or an order with tropism < -0.3) STOPS there (sliding instead,
    a willow's curtains ran along the line as a squiggle), any other slides along and turns ~20 deg up. `_pose`: the
    ground stops the sag ROTATION (the bend an internode takes is cut to what rests on the ground, and its subtree
    turns with it), then clamps. The environment's slope is the ground in growth too.
  - `veg_leaf.rasterize` is one numba pass (per pixel the highest face, within half a pixel: thin needles still draw)
    instead of four PIL polygons a face: a spruce's 3-LOD export 1204 s -> 264 s, pictures the same to the eye.
    Twig atlases are kept on disk by content + veg_leaf.py's hash ($HIFIPUSHIE_VEG_CACHE, else
    ~/.cache/hifipushie/veg_atlas, 60 files; 8-bit, so a fresh and a cached atlas are the same). Bough atlases are not.
  - Forest references fetched: workspace/veg_refs/forest/ (8 spruce stand interiors, 3 pine, 1 edge; fetched.jsonl
    has titles, authors, licences). spruce_in_a / _b / _e = the dead-branch haze; spruce_in_g = a cut edge showing
    interior trees (live crown the top ~35-40%).
  - Forest interior (task 1; sheet vg_82_forest_vs_photos.png = ours beside the fetched photos, vg_83_interior_spruce_
    full_vs_12k.png; scratch stand1.py <out> <species> [patch] [sil] = open | edge | interior row with dead-wood and
    live-crown numbers, inside.py = a stand of 54 from inside (more trees at full detail LOST THE GPU CONTEXT twice on
    the 890M: keep stands under ~60 full trees or use budgets), fsheet.py):
    - A limb the shade kills is no longer a 3-node white spike: its WOOD is remembered when `_shed` cuts it (first-
      order limbs always; in a stand also the branches a living limb loses, attached by their parent's key) and put
      back at the end as dead wood decayed by its years (`vegetation.DEAD`, spec `deadwood`: broken back, thin twigs
      fallen, drooped and bowed). `tree["shade_dead"]` marks it (not `protected` in budgets: it goes by girth).
    - Fine dead twigs are CARDS: `leaves.parts.dead` (a bare-twig picture: `"bare": true`, `wood_color`) in the same
      atlas; `veg_leaf.place` = `place_live` + `place_dead` with `card` / `part` per placement (silhouettes and the
      report's twig counts use `place_live`). Bough atlases bake dead boughs from the dead part's twigs and give dead
      boughs dead pictures (`veg_bough.dead_boughs`, at["dead"]). Dead wood carries no leaves (artist's `dead` too:
      antlers used to have twigs; that had hidden a budget fault: `veg_export.budget` now gives up the thinnest
      marked wood when keeping it leaves the live cards floating, unless nothing helps).
    - `environment.spacing` (m between a stand's trees) caps the canopy gap: at 3 m an interior spruce is a bare stem
      with a narrow live crown of 36% (photo spruce_in_g: 35-45%), 60 dead limbs from 1.6 m up; without it (gap = 18% of
      the height) 59% and a lollipop. `stand_shed` is per node: an edge tree keeps its skirt on the open side
      (live crown 92%) and carries whole dead limbs on the closed side. Presets: spruce dead_keep 40, pine 20
      (ASSUMPTIONS; sources and what is unsourced in workspace/veg_refs/forest/README.md).
    - Stand looks stand on litter (`veg_look.FOREST_FLOOR`) with a dim brown bounce (the lawn's yellow-green bounce
      turned grey twigs olive); a tree stood many times in a look is meshed once.
    - BLUNT read: the spruce row is right in kind. From inside it reads as a plantation but the stand is too small
      (open sky at the horizon, sun pouring in), the dead haze is far thinner than spruce_in_a / _b (ours: ~60 limbs
      with ~200 m of dead wood a tree; the photos' young stands hold them to the ground), dead twig pictures are
      fishbones, the floor is one flat brown. The 12k interior spruce's dead zone is a dense brown fur (bough
      cards of dead limbs: too many, too opaque). The pine interior FAILS: a crooked stick with antlers, nothing like
      pine_in_a's straight poles (its habit dissolves the leader; needs its own stand tuning).
  - HANDOVER (vegetation3, context full). Done: the user's ground question (merged to main at 13863c9) and a first
    forest-interior pass (this branch, after main was merged in). Open, in the coordinator's order:
    (1) forest: denser dead haze low on young stands (dead_keep vs age; `deadwood.break`), irregular dead-twig
    pictures (veg_leaf.twig_mesh draws ranked side shoots: jitter their angles and drop some for `bare`), dead
    bough cards at budgets (fewer, thinner alpha), a closed stand look (fog or a ring of impostors rather than more
    full trees), floor clutter (brash, needles, moss patches), pine stand habit (straight leader in a stand: apical
    0.72 already; its interior tree bends and keeps antlers), open-grown trees on a lawn in the same row (the floor
    is scene-wide); (2) spruce LODs (vg_81 top right: flat fern cards, a huge pale card: cap bough card size by the
    tree's width at that height, small upright leader card, darker inner core), pine leader spike, kit picture, twig
    cards over boughs; (3) small plants incl. ground clearance for clumps (veg_ground.clear skips clumps; audit them
    first: `veg_ground.audit` works on any tree dict) and the weeping willow's leaning foot after the stop rule
    (trunk jitter 0.12 + a changed growth history: try seed or `jitter[0]` 0.06); (4) styles, terrain.
  - All-species re-render after the ground change: vg_80_all_inleaf.png (spruce skirt and willow curtains end over
    the ground with a shadow gap; the willow regrew with a slightly leaning foot).
- Vegetation 4 (2026-10-06, branch `vegetation4`; scratch in the worktree's untracked `scratchpad/`: run.sh <script>
  (env + uv), pm2.py out habit.json [patch] (the pine cases: measures vs bands + silhouettes, 10 s), pm3.py habit.json
  'key=v1;v2' seeds cases (sweep one habit key), pinesheet.py (age / setting row), one.py (one tree), setp.py species
  'json' (merge into a preset), stand_try.py stem 'stand json' views max_full, atl.py (a twig atlas as a picture),
  ccat.py / commons.py (Commons category contact sheets / fetch), gridc.py (photos with a 10% grid to read boxes),
  sheet90.py). The sandbox refuses compound shell commands that mention variables or heredocs: write scripts with the
  Write tool and run them one per call.
  - Scots pine by measurement (the user on vg_82: "those pine crowns look far too wide"; sheet
    vg_90_pine_ages_vs_photos.png, references workspace/veg_refs/pine_form/ + fetched.jsonl). The preset was ONE point:
    fitted to one open-grown photo at 80 y (w/h 0.90, crown 0.50), it was a bare pole at 15-35 y (`clear` 6 m,
    bud_break 0.15), w/h 1.28 and dbh 2.9 m at 150 y, a crooked stick in a stand. `vegetation.crown_measures` (height,
    crown width / height, live crown / height above the 8th percentile of leafy wood, widest level, dbh, top_off),
    `form_cases` / `form_miss` / `fit_form` (one habit against target bands at several ages and settings; tool
    `plant_form`). Targets: boxes read off 10 fetched whole-tree photos (young open-grown 0.85-0.97 wide, crown to
    the ground: young solitary pines are BROAD cones, not narrow; mature solitary 0.69-0.79 / crown 0.8; stand trees
    0.27 / 0.3; stand edge 0.42 / 0.4), Wikipedia (35 m, 1 m dbh, "long bare straight trunk topped by a rounded or
    flat-topped mass"), a search snippet (stands > 80 y: dbh 30 +- 6 cm, 18.7 +- 2.3 m; the papers themselves were
    403). The random-search fit ran at ~5 min an iteration on a machine at load 80: the preset was steered by hand
    with pm2 / pm3 instead; `fit_form` is tested but has not produced a preset yet.
    What it took: `clear` 0 (young trees branch from the ground), `leader` 4 + `slowing[0]` 14 (height 6.5 / 12 / 21 /
    30 m at 15 / 35 / 80 / 160 y), `limb_pace` [1, 0.9, 0.75] (NEW: no side shoot outgrows that share of the leader's
    pace at that age; without it limbs born late overtopped an old slow leader: umbrella tops), `tip_life[1]` 44
    (old limbs stop: the veteran's crown lifts), `pipe` 2.45 + `ring` per order (dbh 50 cm at 80 y, was 98),
    `sag` 0.35 and limb jitter 0.26 (long limbs were snakes), wood past its last living branch is shed (NEW in the
    shed step, every species: bare dead-end snakes), twigs 18 per m on 5 steps of shoots, cards x1.6.
    Stands: the canopy's shade now deepens steadily below its top (`below` over 2 x depth, floor 0.8; a step at one
    depth made a stand crown all or nothing) and the side shade closes over half a gap (crowns 4 m apart interlocked
    8 m wide); `habit.sdi_max` (NEW: Reineke; a stand stem no stouter than 25 cm x (sdi_max / stems per ha)^(1/1.6);
    spruce 1500, pine 1000: 3 m apart 30 cm, was 42 cm = 173 m2 / ha). Spruce `stand_shed` 0.17 -> 0.09, pine 0.01.
    After (seed 1): 15 y 0.49 / 0.69; 35 y 0.67 / 0.78; 80 y 0.79 / 0.77, dbh 50; 160 y 0.67 / 0.53, dbh 85; edge
    0.63 / 0.81; stand 0.22 / 0.13-0.4, dbh 34. KNOWN: a stand pine's crown ratio is still on a cliff of `stand_shed`
    (0 -> 0.41, 0.015 -> 0.17; seeds differ: pine's own shadow reaches only 6 cells = 1.8 m, so nothing lifts the
    crown smoothly); the edge tree keeps too deep a crown (0.81 vs the photo's 0.4); the veteran's limbs are sparse.
  - Dead twigs: `veg_leaf.dead_twig_mesh` (a `bare` part's picture: a crooked sagging axis forking at uneven
    intervals to either side, never in pairs, forks shorter / thinner / some broken to stubs, lichen threads, tone per
    branch; keys forks, depth, crook, broken, fork_angle, child, flat, lichen; `"form": "spray"` = the old leafless
    spray = fishbones). 5 variants in the conifer presets, lichen-grey. Wood in card pictures takes its mesh tone.
    At a budget `veg_bough.plan` keeps at most `DEAD_SHARE` 8% of the cards (>= `DEAD_MIN` 12) for dead boughs: the
    longest of each height band up the stem; their pictures are baked from `DEAD_THIN` half of their twigs.
  - Stands (`veg_stand.py`; tools `grow_stand`, `look_stand`, `export_stand`; guide section "A forest"): spec =
    species (or a mix by share), age + spread, spacing, size, variants, edge sides, rows, clearings, paths, floor,
    lod, haze, light. `grow` = interior variants (setting forest at the spacing) + edge variants (setting edge, open
    side turned to face out) + a jittered offset grid + per-tree yaw / scale + the floor's scatter (brash under the
    stems = `brash_mesh` from the dead twig tangle pressed flat; `stump_mesh`; ferns where light reaches);
    `measures` / `report` = stems / ha, height, dbh, basal area, live crown, canopy cover + warnings; `lods` by
    distance to the nearest eye; `look` (views inside / aisle / edge / above / canopy or cameras; at most `max_full`
    full trees); `layout_json` + `export` (a GLB per variant with LODs + impostor, floor OBJs, layout.json; heavy).
    Blender (`blender_vegetation`): a plant stood again is a COPY of the first's objects (`_BUILT` by npz: shared
    meshes, materials, textures; 54 trees each with its own atlas textures was what lost the GPU context); the hull
    normal and snow read a per-instance "hull" attribute stored by the hp_twigs node group from per-object modifier
    inputs Crown / Yaw (a material can't know its object's crown once shared); per-plant `scale`; `add_scatter`;
    `HAZE` (`_hazed`: every shader mixed toward the haze colour by 1 - exp(-distance / haze distance), before the
    alpha cut on cards); an `ambient` shadowless light from above (under a closed canopy EEVEE rendered night);
    ground `moss` patches and `litter` flecks. `veg_look.render(others=[(tree, at, yaw, triangles, scale)],
    scatter=, job=, scale=, yaw=)`.
- Vegetation styles, stage 5 start (2026-10-07, "vegstyle" agent, branch `worktree-agent-af611e5c1af1d81a5`; consumer brief:
  /home/joe/dev/pushieworld/docs/hifipushie-notes.md "Vegetation style brief"; sheets `workspace/veg_renders/vs_*`;
  deliveries /mnt/data/hifipushie/vegstyle/; scratch in the worktree's untracked `scratchpad/`: run.sh <script>
  (worktree code on the main workspace), sheet.py <species> <style> <out.png> [season] (realistic | styled: far, far
  90 deg round, near, clay + the numbers), seasons.py, export.py <name> <species> <style> <out dir> (through
  server.grow_plant / export_plant), imp.py (Blender's importer + wind displacement), t1.py; Khronos:
  `node /mnt/data/hifipushie/vegstyle/v.mjs x.glb`).
  - `veg_style.py` + `vegetation_styles/<name>.json`: spec `"style": "blobby"` | {"sheet", ...overrides}. A style is a
    sheet of numbers over general operations (`wood` = which limbs are drawn / how fat / how far, `crown` kind
    "masses" = k-means of the twig positions -> ellipsoids -> smooth union (`sdf.smin`) -> marching cubes -> pyfqmr
    per LOD -> back onto the field, normals = the field's gradient, one tone per mass in COLOR_0, wind = a mass moves
    with its limb). Growth never reads it (`test_same_individual`). `fit` (once per tree + sheet, cached by id) picks
    the number of masses by outline IoU against the realistic tree (`compare`: row-filled side outlines in ONE metric
    frame, 3 azimuths; `vegetation.outline_iou` normalises height, so it can't see a tree that grew), `dress(tree, st,
    triangles, season)` = one LOD. `veg_export.write_glb`, `veg_look._plant_job` (`_styled_job`), `blender_vegetation`
    (`solid_*` arrays: one closed mesh with a colour attribute and custom normals; flat bark), `veg_tools.report` /
    `describe`, the server's grow_plant / export_plant docs follow the style. Guide section "Styles".
  - Blobby oak (vs_03, vs_04 seasons): 4 limbs of 5, 8 masses for 17,840 twigs, IoU 0.859 (0.87 / 0.83 / 0.88), height
    20.16 vs 19.83 m, width 23.8 vs 25.7 m; LODs 4,999 / 2,250 / 1,036 + impostor; Khronos 0 errors 0 warnings on all
    five files; Blender's importer reads the variants and wind (limb ends 12 cm mean / 58 cm most, foot 0).
  - What it took: PCA ellipsoids of flat clusters were lily pads (`roundness`: no semi-axis under 0.6 x the longest),
    which then stood 1.3 m over the tree (masses sink to the tree's own top); COLOR_0 over 1 is a glTF ERROR (tones
    are divided by `color_gain`, the material's factor carries it); empty `textures` / `images` arrays are errors too;
    limbs ended in the air until they were cut `bury` m inside the first mass they enter.
  - Read: a toy tree of balloon lumps on fat-ish limbs, plainly the same crown from 70 m. Weak: masses read as
    separate balloons more than one bumpy cloud (the oak's foliage is a shell, the middle is hollow), limbs look thin
    under so much crown and shade with a hard crease near the fork, winter = four bare noodles.
  - Spring: `season_color` / `veg_export.spring_leaves` (colour + smaller leaves; realistic and styled; export
    variant "spring"). No blossom, no catkins; clumps have no seasons (consumer notes 14, 15).
  - Round 2 (the coordinator on vs_03: "balloons on wires"; the consumer in Godot 4.7.2 agreed: notes 32-38; sheets
    vs_05 / vs_06, delivery re-exported in place). (1) One cloud: a `core` mass in the shell's hollow + the union's k =
    `blend_share` 0.9 x the masses' mean radius (3.55 m; at 0.4 x they were still eight lumps with creases). The "hard
    crease" was two ellipsoids meeting with k 1.2 m; no normal seam. (2) Wood is a field too (`wood_field`: hard min
    along an axis, smin between axes; `mesh_field` with a coarse pass first: evaluating every voxel took 150 s, the
    narrow band 5 s), girth from the crown (`limb_mass`, `trunk_mass`), limbs AND their stoutest forks (`stubs`) run
    into the crown and end `keep_in` + their girth under its surface, stopping at the first exit (a limb crossing a
    shallow lobe showed as a stick in the air). Forks can't be chosen "inside the crown": an oak's limbs fork 2-3 m
    BELOW its foliage shell (measured), so forks are taken along the whole limb. (3) Winter: the forks are that second
    order; and the fit is made `in_leaf` whatever the season (a winter spec had no twigs: no masses, no forks, four
    noodles). (4) Collision is the grown tree's again. IoU 0.859 -> 0.860 (masses unchanged; only blend, core, wood).
    (5) Export, all plants: impostor picture unlit (`"flat": true` views in blender_vegetation), single sided with
    back faces and up-and-out normals (8 triangles: test_vegetation's count changed); `<name>_collision.glb` (node
    `-colonly`, in the scene); `<name>_seasons.json` (`veg_export.seasons_json`, read back from the GLB) + the variant
    pictures as PNGs; `extras.hidden` on bare-season materials. Realistic birch impostor vs its atlas: 0.60 / 0.69 /
    0.39 vs 0.65 / 0.78 / 0.39.
  - Read of vs_05 / vs_06: a toy oak: one bumpy crown on a stout trunk with forking limbs, winter a stubby armature.
    Still weak: the fork's fillet shades in angular patches from 5 m at 5k; the crown's underside is one dark flat
    green; autumn's factor clips at pure orange; LOD 2 is 1,134 for a share of 900; impostor has summer only.
  - Clumps in a style (not built; what it takes): veg_small's plants are cards from an atlas, so "fat rounded tufts"
    need geometry instead: a `clump` style op that replaces each layer's cards by a few capsule / paddle blades
    (5-9 a tuft; `wood_field`-style round cones, or a swept lens) with vertex tones, through the same `dress` ->
    `write_glb` / `_styled_job` path (the `tree["clump"]` branch in dress), wind from the card's own phase / flutter
    as now. Clump SEASONS need states first (veg_small has none): per layer a colour per season + `hidden` + a
    `flatten` (winter grass lies down), flowers only in their months; then both realistic (atlas tint per season)
    and styled (factor per season) can read them. About a day; the spruce first.
  - Round 3 (spruce + the oak's leftovers as general ops; sheets vs_07 spruce, vs_08 spruce seasons, vs_09 / vs_10
    the oak again; deliveries /mnt/data/hifipushie/vegstyle/blobby_spruce, blobby_oak; scratchpad/round3.sh runs the
    lot, logs r3_*.log).
    - Conifers: a sheet's `conifer` block is merged over it for needle trees (`veg_style.conifer`): crown kind
      "tiers" (`masses`: one upright ellipsoid per height band, seated low in its band: `tier_seat`, `tier_height`,
      `tier_power`; no core, blend 0.3 x), wood = the trunk alone. Norway spruce: 5 tiers, IoU 0.851 (0.85 / 0.84 /
      0.86), height 26.3 vs 26.0 m, width 14.8 vs 14.7 m. Read: a stacked-dumpling chess piece, plainly the same cone;
      the top tier is a long finger; the skirt hides the trunk (as on the realistic tree).
    - Forks only when bare: the wood is two meshes (`fit`: "wood" = trunk + limbs, "forks" = order 2), `dress` returns
      "forks" for deciduous trees; looks append them when the crown is hidden; the GLB's wood mesh has a SECOND
      primitive with material slot `bark_forks` (hidden: MASK cut-off + extras.hidden) switched to `bark_forks_bare`
      by the bare seasons' variants (in the seasons json too; only written when a bare season is exported).
    - Limb ends are pulled under the crown's surface by their girth + `keep_in` (the last 40% of the path bends).
    - `material_color`: the season colour x the tones' gain, scaled as a whole under 1 (autumn clipped to flat orange).
    - `_decimate` retries with more aggressiveness (a pole stalled at 2.4x its target); minimums lowered (LOD 2's
      over-share).
    - Impostor: a picture per season (`veg_tools.impostor(season=)`, materials `impostor_<se>` as variants, in the
      seasons json with PNGs), and the flat (unlit) view's world now fades to 0.35 from below: a little shade under
      crowns baked into the albedo.
  - HANDOVER (vegstyle, context full, 2026-10-07). Check `scratchpad/r3_*.log` first: if `r3_done` exists the run
    finished; r3_test_style / r3_test_veg must show no FAIL, r3_val 0 errors on every GLB. NOT DONE, in order:
    (1) the consumer's impostor pop (their notes 39-42, picture pushieworld/docs/img/blobby_oak_lods.png): a NORMAL
    MAP for the impostor. Design: a third kind of view in blender_vegetation (`"normal": true`: view-layer material
    override, emission = world normal x 0.5 + 0.5, Standard / Raw), rendered from the same two views as the albedo;
    converted to each quad's tangent frame (right = the view's right, up = z, out = toward that camera) and written
    as normalTexture. For that the quads' vertex normals must be their FACE normals (today: up-and-out, which was
    the fix for the black quad) and the back faces need their own vertices with the opposite normal and the x of the
    normal map mirrored (or TANGENT written explicitly with w = -1): get that right in Blender's importer and ask the
    consumer to check Godot. For realistic card foliage the true geometry normal is noise: mix toward the direction
    out of the crown's middle (`leaves.round`), as the leaf shader does. Not attempted here.
    (2) LOD 2's crown "faceted creases" in Godot (note from the coordinator): the export already writes the field's
    gradient as NORMAL at every LOD (`dress` -> `onto`), so this is unexplained: read LOD2's NORMAL back and compare
    with face normals; suspect Godot regenerating normals / tangents on import, or 300-500 triangles being too few.
    (3) Clump style path + clump seasons (design in the note above: a geometry op replacing a layer's cards by 5-9
    capsule blades through `dress`; per-layer season states in veg_small first), meadow grass first.
    (4) anime / cartoon / pixar sheets; sets and stands with a style (untested); `wind_plant` on a styled plant
    (untested); blossom / catkins; the spruce's top tier (try `tier_power` 0.8 so upper bands are shorter).
    The guide's "Styles" section does NOT yet describe round 3 (conifer block, tiers keys, bark_forks slot, impostor
    per season, `forks_share`): add it.
  - Vegetation styles 2 (2026-10-07, "vegstyle2" agent, branch `worktree-agent-a76bb94fddaac769e`; sheets vs_11 spruce,
    vs_12 oak, vs_13 spruce seasons, vs_14 meadow grass seasons; deliveries re-exported in place in
    /mnt/data/hifipushie/vegstyle/blobby_oak, blobby_spruce + new blobby_grass, real_grass; scratch in the worktree's
    untracked `scratchpad/`: run.sh, sheet.py, seasons.py, clump_sheet.py <species> <style> <out>, tiers.py (a conifer's
    tiers as numbers + silhouette, 10 s), setstyle.py <sheet> '<json>' (merge numbers into a style sheet), imp1.py (an
    impostor's maps as a picture), impvar.py (impostor-only GLBs with other numbers), gd.sh <tag> <height> <mesh.glb>
    <impostor.glb> (Godot check + measure), export.py / export_clump.py / export_real.py, round4.sh / round5.sh).
    - THE IMPOSTOR (consumer notes 38 / 42 / 45; all plants, realistic too). Three causes, found by measuring in the
      consumer's own engine (`spikes/godot_veg/check.gd` + `measure.py`: Godot 4.7.2 loads LOD 2 and the impostor with
      its own importer, each alone on magenta, 4 views x 3 suns; mean luma of foliage / wood pixels, impostor / mesh):
      (1) the "unlit" picture was a Principled surface under a white world: sky reflected in it (pale, blue 0.28 vs
      0.20) and no shade; (2) up-and-out vertex normals lit it as a flat card; (3) the DARK WEDGE was one quad's
      SHADOW on the other (alpha-scissored, the sun's elevation makes it a triangle), not mips, not normals.
      Now `blender_vegetation._pass_material` (view key `"pass"`: "albedo" = emission of what feeds the Principled's
      Base Color, "normal" = the shading normal x 0.5 + 0.5 in Raw, "shade" = Cycles' AO node with the normal forced up
      = how much sky straight above reaches the point; cut out by the material's own alpha mix), `veg_export.
      impostor_maps` (albedo x (1 - 0.5 + 0.5 x shade); world normal -> each quad's tangent frame, `depth` scales the
      toward-camera share: 1.0 styles, 0.5 card foliage; everything bled under the alpha), quads with front and back
      as their own vertices (16), opposite normals, TANGENT w = -1 behind; the second picture was MIRRORED on its quad
      (r_ = +y for a camera whose right is -y): fixed (`impostor_frames`). The material's extras + the seasons json say
      `receive_shadows: false` (Godot `disable_receive_shadows`): that is what removes the wedge, and it is the
      ENGINE's switch. Blobby oak: foliage 1.20 (0.99-1.51) / wood 1.42 before -> foliage 0.95 (0.85-1.03) / wood 1.08 (0.95-1.23). Blobby spruce: foliage 0.98 (0.94-1.01), wood 0.98 (0.73-1.48: its trunk is a few pixels).
      Realistic birch (20k): foliage 0.94 (0.81-1.01), wood 0.97 (0.85-1.06); lowest with the sun behind (a picture's
      normals face its camera; a real crown lets light through). Left: from a diagonal the two quads meet in a visible
      vertical line; the realistic birch's impostor shows the look's black foot (bark `base_color`), the GLB's bark
      texture doesn't. Blender's importer was NOT checked on the new impostor (it computes its own tangents).
    - Contract (consumer note 46): `veg_export.CONTRACT` 3 + `CONTRACT_LOG`; `<name>_seasons.json` leads with
      `contract` and `slot_list` (slot -> mesh / primitive, hidden_in, channels); normal PNGs written too; textures
      with the same bytes are stored once in the GLB. Bump the number with any slot / channel change (guide: "The
      export contract").
    - LOD 2's creases: gone in the consumer's last import and never Godot's. `test_lod_normals_are_the_fields` holds
      every LOD's NORMAL (dress and the file) to the field's gradient.
    - Spruce (consumer note 44): tiers are EGGS (`e["down"]`: a shorter semi-axis below the middle, read in `field`):
      round above, flat below, seated low, the dome closing under the next tier's wider foot = overhang + undercut;
      sheet keys trunk_show, tier_under, tier_uneven, tier_cap, tier_power (conifer block), blend 0.1 x; conifer tones
      [0.72, 1.3] and value 1.35; trunk fat (trunk_mass 0.45) but ending at 45% (at 85% and floor 0.85 it poked out
      between the top tiers). IoU 0.85 -> 0.75 (bare foot + notches: the report warns; lower trunk_show to get it
      back). With undercuts `onto` could put a decimated vertex on the other sheet (holes / turned faces in LOD 2 in
      Godot): faces turned by the move, or moved > half the blend, go back to where the decimation left them.
      First tries that failed: tier_height 1.0 (each dome swallowed the next tier: a bell with a nipple), band jitter
      x the smallest band (bands of 9 / 3 / 9 / 3 m), 4 tiers.
    - Oak: limb_mass 0.3, trunk_mass 0.32, taper_floor 0.8, wood blend 1.0, share 0.35. The "notch at the fork" from
      5 m is a ragged SHADOW edge (EEVEE's terminator on big smooth triangles; clay shows nothing).
    - Small plants: `veg_small.SEASONS` / `clump.seasons` (colour, flatten, scale per season), a layer's `seasons`
      list, `season_state`, `hidden_parts`; realistic export = the season's atlas recoloured with out-of-season
      pictures blanked; `veg_style.dress_clump` (sheet block `clump`): leaf cards -> 5-9 fat closed blades chosen by
      farthest tips, flowering cards -> balls on stalks in slot `heads` (the foliage mesh's 2nd primitive, hidden out
      of season). Meadow grass: 9 blades for 18 cards, 3 heads, height 0.58 (0.55), spread 0.53 (0.45). Read of vs_14:
      a toy tuft, clearly the same plant through the year; blades are flat-ish paddles more than "fat rounded" ones,
      winter is a starfish of nine blades, the snow column's blades stay brown (snow lies by the normal's up share
      and the blades lie on edge).
    - HANDOVER (vegstyle2, 2026-10-07). NOT DONE: (1) ANIME oak (the consumer's next style). Design: reuse the blobby
      fit's masses as the clumps (they are the proxy the guide's sources transfer normals from); per mass 3-5 depth
      layers of alpha cards facing out of the mass (shells at 0.6 / 0.8 / 1.0 of its radii, cut into `veg_leaf.
      card_mesh`-style polygons), pictures = a new atlas of painted leaf-DAB clusters (rasterise a few dozen big
      leaves per tile with `veg_leaf.rasterize`; edges are the dabs), NORMAL = out of the mass's centre, TEXCOORD_0 =
      (gradient 0 base .. 1 top of the clump, clump id), COLOR_0 = the 3-step gradient; wood = blobby's `wood` with
      radius 1.0 and a dark cool bark. `veg_bough.place` is NOT reusable (it stands cards on bough roots); the card
      material / season-atlas / export path of the realistic foliage is (foliage_material, with_variants). (2) Blobby
      fern / daisy / clover judged (the clump path runs on any clump; nobody looked). (3) Clump impostors, flatten in
      the export (a morph target or a second mesh), stands / sets with a style, `wind_plant` on a styled plant,
      blossom. (4) Blender's importer on the new impostor; an engine fade of each quad by how edge-on it is.
  - Vegetation styles 3 (2026-10-07, "vegstyle3" agent, branch `worktree-agent-ac910597cf0676b73`, round 1 merged as
    main 78cb0ad; sheets vs_20..vs_28; deliveries /mnt/data/hifipushie/vegstyle/{anime_oak, anime_spruce, anime_grass}
    + the blobby / real ones re-exported at contract 5; Godot measures /mnt/data/hifipushie/vegstyle3/gd/; scratch in
    the worktree's untracked `scratchpad/`: run.sh, sheet.py, seasons.py, clump_sheet.py, q.py <species> <style name or
    json> <out> [season] [triangles] (styled panels only, ~1 min), a1.py (dress numbers + atlas + silhouette, no
    Blender), tsweep.py <species> '<list of conifer.crown overrides>' [sheet] (tier IoU sweep), setstyle.py, gdc.sh
    <tag> <height> <mode> <dir> <stem> (Godot card check at the LOD switch distances), r1-r4.sh (queues), t_one.py
    <test module> <test names>).
    - ANIME (`vegetation_styles/anime.json`, `veg_cloud.py`; crown kind "clouds"): the style's masses are the clumps
      (the proxy artists transfer normals from); every clump gets `layers` shells (0.6 / 0.8 / 1.0 / 1.12 of its
      ellipsoid) of alpha cards facing out of it (tilt, roll, cup), sized `card` x the clump's radius (lower LODs: fewer,
      larger cards, `lod_grow`), cards buried in another clump dropped; picture = a generated grey DAB atlas
      (`dab_atlas`: the species' leaf outline fattened, `count` dabs per tile, ragged rim; needle trees a pointed
      spray stroke); NORMAL = out of its clump's middle (`normals` toward the crown's middle); COLOR_0 = a 3-step painted
      gradient per clump, one step per CARD (inner layers darker by `depth_dark`, top warmer); TEXCOORD_3 = (gradient 0
      base .. 1 top, clump id) (Godot: CUSTOM0.zw, checked). Two sizes of cloud (`edge_share` 0.35 of the foliage
      furthest out of the crown's middle clustered into `edge_count` x more, smaller clouds): one size of cloud read as
      one layer. Wood: true radii, more forks (`stubs` 14) in ONE mesh (`wood.forks_in_leaf`: no bark_forks slot) and
      `wood.feed` (new, general): a clump with no drawn wood within feed x its radius gets the grown tree's own path to
      it (floating outer clumps). Bark `colour.bark_mix` toward a dark warm neutral. Conifer block: clouds on TIERS
      (`masses_kind: "tiers"`), `under` 0.25 (cards facing the ground left out under each bough: the tier shadow),
      `clump_min_cards` 80 (small top tiers were confetti). Clump block: `fan` 3 (each chosen card gives 3 blades,
      +-`fan_angle`: one blade per card was a sparse tuft), long thin sweeping blades.
    - Numbers: oak IoU 0.91 (height 20.1 vs 19.8: cards are held under the tree's height), 12k / 5.4k / 2.2k + impostor, alpha fill 0.69 (overdraw ~1.45x); spruce IoU 0.80 (12.7k:
      clump_min_cards pushes it over the budget a little), fill 0.56; grass 27 blades, height 0.57 (0.55), spread 0.56
      (0.45). Godot 4.7.2 (`spikes/godot_veg/cards.gd` + `measure_cards.py`: each LOD at its switch distance,
      alpha scissor): covered area 0.94-1.0 of LOD0 at every switch (spruce 0.87-0.97, impostor 0.78), pixels flipping
      on a half-pixel move = an outline's worth only (no interior shimmer). Khronos 0 / 0.
    - THE BUG it caught: `veg_export._png` multiplies by 255, and the dab atlas is uint8: it wrapped into noise and the
      first anime delivery's foliage vanished under alpha scissor in Godot (test: the GLB's atlas equals the made one).
    - SNOW = THE WINTER STATE UNDER SNOW (consumer note 52; contract 5): a leaf-dropping plant (realistic or styled) has
      its foliage hidden and forks shown in the `snow` variant (it was the tree in full leaf painted white); evergreens
      keep their crown; the snow impostor is the bare tree under snow (`veg_tools.impostor` sets season winter);
      `season_color` / `season_atlas` return None for a deciduous snow. Test `test_snow_is_winter_under_snow`.
    - Seasons json (contract 4): `snow` = numbers our looks use (linear colour, coverage, by_normal from / to, the
      formula) and `style` {name, foliage}. Impostor albedo: the baked shade is eased on bright colours
      (`IMPOSTOR.shade_bright`: autumn's brown patches; consumer: gone). Clump roots are a 1 cm stub (the tree's 0.3 m
      foot was the grass "stalk" under every tuft; consumer: gone). Blobby spruce: 6 tiers, IoU 0.75 -> 0.805.
    - Read: oak = a painted (Ghibli-ish) oak, big inner clouds, small outer ones, dark limbs in the gaps; winter a
      spreading bare tree (sparser than the realistic one). Spruce = layered bough clouds with tier shadows; the near view
      is big palm-frond strokes. Grass = a sweeping tuft; flowers are still small balls on stalks (the brief: colour
      dabs), snow turns the blades white.
    - NOT DONE (my list, in order): anime flowers as dabs (a dab card instead of a ball); blobby blades with a rounder
      section and winter blades that curl / shorten IN THE EXPORT (decide: a morph target per season vs a second
      primitive per season hidden by slot_list); the impostor's diagonal line (3 quads at 60 deg vs a camera-facing
      card with 8 baked views + an engine recipe: measure in Godot, pick one); cartoon sheet (oak: chunky faceted clumps,
      scalloped edge, big single leaves on the silhouette, per-clump id, S-bend trunk); the anime spruce over budget;
      spruce near-view strokes too big; the guide's "Styles" section does not yet describe anime / clouds / feed /
      edge clouds / fan (add it).
  - Vegetation styles 4 (2026-10-07, "vegstyle4" agent, branch `worktree-agent-a4adb8908a498b15c`; sheets vs_30..vs_39;
    deliveries re-exported in place at contract 6 in /mnt/data/hifipushie/vegstyle/{blobby,anime}_{oak,spruce,grass} + new
    cartoon_{oak,spruce,grass,daisy}; Godot checks /mnt/data/hifipushie/vegstyle4/gd/ (`*_sheet.png`: pairs mesh LOD2 |
    impostor, 3 elevations x 3 azimuths; `octa_vs_cross_oak_blobby.png`); scratch in the worktree's untracked `scratchpad/`:
    run.sh, export.py / export_clump.py / oe.py (export through the tools), gdo.sh <tag> <height> <dir> <stem> [season]
    (octa impostor vs LOD2 in Godot + numbers), gdc.sh (cards at the LOD switches), q.py / sheet.py / seasons.py /
    clump_sheet.py / close.py (looks), sil.py / csweep.py (styled vs realistic silhouettes, conifer sweeps, no Blender),
    a1.py (dress numbers, no Blender), hk.py (head kinds), setmany.py / setjson.py (sheet numbers, indent 1), q4-q8.sh
    (queues), oc1.py (octa bake vs direct renders)).
    - HEMI-OCTAHEDRAL IMPOSTORS (`veg_impostor.py`, contract 6; the consumer: crossed quads from a 330 m volcano read as
      crosses / an orange bird). 8 x 8 views on a hemi-oct grid (border = horizon; frames on the grid's corners so the
      horizon is baked exactly), 256 px each, orthographic through the bake sphere's centre (`bounds`), camera frame
      from `basis(d)` (right = cross(+Y, d); Blender gets an exact camera matrix: view key `basis` in
      blender_vegetation), passes albedo / normal / Cycles shade / depth (new pass "depth": Camera Data view Z mapped by
      the view's `depth_range`); atlas = albedo with half the shade baked in + OBJECT-space normal map with depth in
      alpha. Seasons with the same shape share normal / depth / shade (`geometry_key`): ~4 min a shape, ~1 min a season.
      One quad in the GLB (uv = corners), turned by the engine's shader: `spikes/godot_veg/impostor_octa.gdshader` (4
      nearest frames bilinear, weights ^ `blend_sharp` 2, one depth-parallax step; orthographic shadow pass uses the
      light's axis); `veg_impostor.view` = the same in numpy (tests). extras.hifipushie_impostor {kind, frames, size,
      centre, normal_texture_index, recipe, shader}; seasons json top-level `impostor` (null without one) + per season
      `impostorNormalTexture`. `impostor="cross"` keeps the old quads. Godot: MeshInstance3D.extra_cull_margin = size / 2
      (required). Measured (impostor / LOD2 at elevation 0 / 20 / 45; coverage, IoU): blobby oak 1.01-1.02, 0.976 /
      0.938 / 0.902 (crossed: 0.96 / 0.92 / 0.66, IoU 0.89 / 0.84 / 0.63); blobby spruce 0.984 / 0.968 / 0.923; anime oak
      0.857 / 0.840 / 0.819 (the impostor fuller than LOD2's ragged cards); anime spruce 0.733 / 0.751 / 0.760 (LOD2 is
      the weak one); cartoon oak 0.929 / 0.888 / 0.863; cartoon spruce 0.987 / 0.972 / 0.918. Consumer: in the game,
      shader unchanged, impostors from above read as trees.
    - Anime spruce: budget within 12k (`clump_min_cards` now traded inside the budget: 11,988 / 5,406 / 2,160), cards
      0.36 x clump (max 0.9 m), 110 finer strokes a tile, conifer `lod_grow` 2.4 (LOD2 covered 0.70 of LOD0 at its
      switch -> 0.85), spring = `seasons.spring.tips` (the spring dab picture paints stroke tips lighter / yellower;
      `veg_cloud.dab_atlas(season=)`, the export's foliage_spring has its own texture). IoU 0.796.
    - Heads: `_head` kinds ball | dab | petals (`_slab`: closed plates, ALWAYS counter-clockwise: a clockwise petal
      showed its underside), `heads_kind` may be a table by the realistic flower's form, `petal_size` x the realistic
      flower's radius; heads carry COLOR_0 per part (petals / centre / stalk) under a white factor (contract 6). Daisy
      preset: flowers spring + summer only.
    - Small plants' winter IN THE EXPORT: slot `foliage_winter` (the blades lying, the plant regrown at season winter
      and dressed; shown in winter / snow while foliage is hidden). Second primitive, not a morph target (reasons in the
      guide). Blobby blades rounder (thick 0.85).
    - CARTOON (`vegetation_styles/cartoon.json`): crown `scallop` bumps per clump (`of` = their clump; `join` crisper),
      `normals_clump`, `hue_jitter`, 2 tones, `big_leaves` (`_big_leaves`: leaf-outline plates on the outermost points);
      wood `taper`, `flare`, `s_bend` (below the crown's base only); conifers `tier_shape` "cone" (`_cone_d`: a cone on a
      flat foot, `teeth` zigzag rim, `cone_height`); clumps: few big blades, daisies as petals. Oak IoU 0.861 (7k), spruce
      0.81 (cones lose area against the realistic bands), grass / daisy heights within 2%. Read: a toy cartoon oak of
      scalloped clumps with leaf tufts on the outline on an S-bent flared trunk; a saw-tooth fir with pleated tiers;
      fat-bladed tuft with seed balls; white-petalled daisies with yellow eyes.
    - NOT DONE: PIXAR (brief: sculpted canopy shells per branch cluster + a layer of real leaf cards on the outer 20-30
      cm: the blobby masses + veg_cloud cards with species leaves at 1.5x, canopy-centre normals 0.5, a thickness
      channel); cartoon conifer spring is barely distinct; cartoon oak winter is a few fat limbs (more stubs?); anime
      grass dabs read as flat coins on sticks from the side; realistic small plants' winter primitive; impostor depth
      parallax beyond one step; the guide's styles table for stands / sets.
  - Vegetation styles 5 (2026-10-07, "vegstyle5" agent, branch `worktree-agent-a0b734a7496db7e3e`; sheets vs_40..vs_46;
    deliveries /mnt/data/hifipushie/vegstyle/{pixar_oak, pixar_spruce, pixar_grass, pixar_daisy} new + every tree
    re-exported in place (contract 9); Godot checks /mnt/data/hifipushie/vegstyle5/gd/; references
    workspace/veg_refs/stylised/ (fetched.jsonl: BBB forest, Spring, Sprite Fright plants; no whole stylised broadleaf tree
    found: Commons rate-limits after ~4 fetches); scratch in the worktree's untracked `scratchpad/` (vegstyle4's scripts
    + p1.py <species> [style json] (pixar numbers per LOD, no Blender), q2.py (far | 25 m | crown edge | clay), iou.py
    <species> <sheet> '<list of crown overrides>' (IoU sweep), od.py (anime overdraw per LOD), foot.py, tieru.py,
    inject_crops.py / shrink_crops.py (crops into a delivered seasons json: Godot test), fetch_ref.py, q5.sh / q6.sh
    (export queues, logs q5_*.log / q6_*.log, *_done files)).
    - Cartoon fixes: big leaves were `leaves.width` read as metres (5x wide plates, horizontal: green shards edge-on from
      eye level): now leaf-shaped plates on clump EDGES, face turned sideways (`big_leaf_soft`, `big_leaf_roll`); flare =
      concave foot `flare_height` trunk diameters tall, foot node under the ground (a sphere on the ground = the mound);
      `head_up` = how far a flower faces the sky (a head along a leaning stalk showed shaded petal backs), petal normals to
      the sky; anime `heads_kind` "dab" = clusters of blobs along the head (`dabs`, `dab_length`, `dab_size`, `dab_flat`);
      `seasons.<se>.tips` {color, band [whole, gone]} = a RAMP texture over TEXCOORD_0.x in that season's material
      (`veg_style.season_ramp` / `ramp_texture`; cartoon fir spring = lime tier rims; contract 7); `seasons.spring.evergreen`.
    - Impostor crops (contract 8): `veg_impostor.crop` / `crops` / `drawn_share`; extras `crop`, `crops` (per frame,
      k = column * n + row), shader `crops[256]` + `has_crops` = the union of the 4 blended frames' crops; octa.gd sets them
      and now applies a season's factor + baseColorTexture from the json. Frames average ~0.62 of the square (oak): ~35%
      fewer impostor pixels, coverage / IoU in Godot unchanged; a shrunk-crop test proved the shader reads them.
    - Anime LOD overdraw: `crown.lod_layers` [kept < lod 0.6, < 0.3] (outer layers) + `lod_area` (card growth exponent).
      Oak [2, 1] / 0.3, spruce [2, 2] / 0.35. At 0.2 the oak's LOD2 covered 0.83 of LOD0 at its switch in Godot.
    - PIXAR (`vegetation_styles/pixar.json`): masses (`spread` 1.3) + `crown.sub` secondary clumps (`_subclumps`: each
      mass's own twigs k-meansed again, `sub_spread`, `sub_min`, `sub_join`), `crown.gradient` + `warm_tip` on the shell
      (`_shell_and_cards`), `crease_dark` / `crease_width` (AO where two clumps meet: the two nearest elements nearly
      equally near), `thickness` (ray in along -N, TEXCOORD_3.y), `crown.cards` = `veg_cloud.shell_cards` (+ `shell_atlas`:
      dab_atlas with `true` species outlines; `leaf`, `count`, `length`, `out`, `cover`, `tilt`, `roll`, `cup`, `under`,
      `tone`, `warm_tip`, `share`, `verts`, `width`, `size_m` (needles), `rim`, `lod_grow`), slot `foliage_cards`
      (contract 9), extras.translucency. Conifers: tiers `tier_shape` cone + sub-clumps (bough lobes) + needle sprays.
      Clumps: lush thin blades (`fan` 6), petals, dab spikes. Oak round 1 (vs_41: 8 balloon shells + confetti, the
      coordinator: "not Pixar yet") -> round 2 (vs_46): IoU 0.941, LOD0 20,000 (cards 14,450), reads as a leafy canopy at
      two scales. Godot (round 1 file): impostor/LOD2 coverage 0.98-0.99, card coverage at switches 0.88-0.96.
    - Realistic small plants: slot foliage_winter too (`veg_export` realistic branch: the plant regrown at winter, its
      cards lying; main foliage hidden in winter / snow by a hidden copy material). test_winter_blades_lie_in_the_export.
    - Tests: test_veg_style (+ test_pixar, test_cartoon_fixes), test_veg_impostor (+ crops), test_vegetation: 67 passed.
    - NOT DONE / open: judge pixar against a real feature-animation tree still (none found under CC yet); pixar spruce
      tiers blur into one lumpy cone with the sub-clumps; pixar oak's limbs visible only low; thickness is ~4 m nearly
      everywhere on the oak (the core fills it: a shell-only thickness would vary more); impostor octagon instead of a
      rectangle; cartoon oak winter stubs; anime spruce LOD2 covers 0.79 of LOD0 at its switch (lod_layers [3, 3] /
      0.45; [2, 2] / 0.35 gave 0.69).
    - Round 3 of pixar after the coordinator's read of vs_46 ("broccoli in a blur"): `crown.clump_shade` [dark, 1] =
      each clump's (sub-clumps included) own vertical gradient, lit top / shadowed underside, on shell and cards;
      `crease_dark` 0.6 (vs_47_oak_pixar_clumpshade.png).
    - All deliveries re-exported and checked (Khronos 0 errors 0 warnings on every tree; Godot octa impostor vs LOD2
      coverage 0.99-1.07 except anime spruce 1.02-1.25 (its LOD2 is the thin one)): pixar_oak (IoU 0.941, card coverage
      at switches 0.96 / 0.97, 0.94 / 0.89, 0.89 / 0.99), pixar_spruce (0.865), anime_oak (switches 0.96-0.97, 0.93 / 0.91,
      0.90 / 0.94), anime_spruce, cartoon / blobby oak + spruce, pixar / anime / real grass, pixar daisy. Realistic
      grass: LOD2's clustered atlas has slot `foliage_boughs2_winter` (lying cards: keep 1.0 when the LOD's keep share
      leaves none).
    - Pixar LOD overdraw (consumer note 87: the vale's pixar wood at 56 ms): `crown.cards.lod_keep` [share of the cards
      kept under lod 0.6, under 0.3] + `cards.lod_area` (growth exponent; 0.5 = same area): the shell carries the mass.
      scratchpad/od2.py = summed card area / covered area (overdraw before alpha) per LOD. Oak [0.5, 0.55] / 0.4: LOD1
      13.3 -> 6.2, LOD2 10.3 -> 5.9 (front; LOD0 13.6 untouched: the next lever if the vale is still slow); Godot card
      coverage at the switches 0.96 / 0.91, 0.89 / 0.85, 0.86 / 0.99 ([0.45, 0.35] / 0.35 gave LOD2 0.82). Spruce [0.45,
      0.35] / 0.35: LOD1 3.0 -> 1.4, LOD2 3.0 -> 0.9; Godot 0.96 / 0.94, 0.91 / 0.89. Both re-exported, Khronos 0 / 0.
  - Impostor pixel cost (2026-10-08, "impostor" agent, branch `worktree-agent-a4a49e9b179132f6a`; consumer note 89: impostors
    ~13 ms of the vale probe, crater rim worst). Scratch DURABLE in /mnt/data/hifipushie/impostor/: bench.sh <cfg> (waits for
    gpu_busy < 15%, runs spikes/godot_veg/bench.gd), q.sh <tag> <cfgs> (queue), mkcfg.py <tag> <set> (field configs b1 / b2),
    mkpath.py + path.py (pop test: camera arc 420 -> 80 m round a small wood, frame-to-frame change), report.py <out prefix>
    (gpu ms med / min, minus the no-impostor run, coverage / IoU / colour diff vs a reference variant), octagon.py (tightest
    45 deg octagon in the quad's uv over every view cell), octa.sh (octa.gd + octa_measure vs LOD2), old.gdshader (the
    contract-9 reference + the consumer's `cheap` mode), and pw/ = a COPY of the pushieworld project (never their repo):
    imports.py <mips 0|1> <compress mode> sets the impostor atlases' import options there, port.py ports the reference
    shader's new parts into the copy's own impostor shader (pw_old_ / pw_new_impostor.gdshader), pw/tools/dev/imp_probe.gd
    = GPU ms with / without impostors at crown_rim, vale, crown_camp, overview (logs g_*.log, shots_old / shots_new_mips).
    - ROOT CAUSE: the consumer imports every impostor atlas with `mipmaps/generate=false` (and lossless), so a far impostor
      (a 2048 atlas, 256 px frames, drawn 30-90 px) misses the texture cache on all 12 fetches a pixel; and the reference
      shader read the parallax depth at `textureLod(..., 0.0)`, which stays level 0 even with mips. Our own octa.gd always
      generated mipmaps, so no check of ours ever saw it.
    - Reference shader (spikes/godot_veg/impostor_octa.gdshader; same uniforms, new ones with defaults, so contract 6-9
      files work unchanged; GLB and contract NOT changed): one mip level per fragment from its footprint on the bake square
      (`lod`, + `mip_bias`, <= `max_lod` 5), the bake square's size on screen from the same footprint (frame_tex / foot px;
      VIEWPORT_SIZE in vertex() read 0 in 4.7) -> t = 0 at >= `near_px` 160 .. 1 at <= `far_px` 64: blend power
      blend_sharp -> `sharp_far` 16 (by t^2), parallax faded by 1 - t and skipped at t = 1, frames under `min_weight` 0.02
      skipped (renormalised), coverage summed from the albedo fetches and `discard` before any normal fetch. Continuous: the
      pop test shows no spike (largest step / its neighbours x1.17, as the full blend's x1.19); far mode differs from the full
      blend by 0.13e-3 mean per frame (the consumer's `cheap` mode: 0.37e-3, max 2.7e-3).
    - Bench (spikes/godot_veg/bench.gd, 1280x720 MSAA 2x, 508 trees at 150-256 m + 2273 at 256-640 m thinned from 320 m,
      camera 120 m up, gpu_busy 1-2% before each run; impostors' own ms = minus the no-impostor run 1.0 ms), pixar spruce /
      oak: consumer now (old shader, no mips, cheap far) 19.9 / 23.1; old shader + mips 10.9 / 13.0; new shader no mips 11.1
      / 13.7; NEW + MIPS 2.2 / 3.1 (coverage 0.999 / 0.998 vs now, IoU 0.997 / 0.993); new full blend everywhere + mips
      4.1 / 5.4; + S3TC (DXT5) 1.6 / 1.9; mip_bias 1 1.6 / 2.0; thresholds 256 / 128 1.7 / 2.1, 96 / 32 3.0 / 4.7;
      octagon mesh (area 0.89 of the cropped rectangle) 2.2 / 3.3 = no gain: dropped.
    - IN THE GAME (pw copy, island, imp_probe GPU median, impostors on minus off): crown_rim 14.6 ms (now) -> old shader +
      mips 5.8 -> new shader no mips 5.6 -> NEW + MIPS 0.34; vale 4.5 -> 1.6 -> 2.1 -> 1.1; overview 0.6 -> ~0 -> 0.4 -> 0.2.
      island_shots frame median crown_rim 25.2 -> 8.5 ms, vale 18.8 -> 12.5, downs 12.5 -> 8.9. Pictures side by side
      (cmp_island_crown_rim.png, cmp_rim_zoom.png): the same forest, a touch softer and without the no-mip sparkle.
    - octa.gd (orthographic, so t = 0: the full path) vs LOD2: identical to the old shader to 0.001 (spruce coverage 1.05-1.09
      IoU 0.90-0.93; oak 1.06-1.09 / 0.86-0.90).
    - For the consumer: (1) set `mipmaps/generate=true` on every *impostor*.png import (both atlases; keep the normal atlas'
      compress/normal_map off: RGTC would drop its alpha = depth); (2) take the fragment of the new reference shader into
      game/style/plant_impostor_octa.gdshader (port.py shows the splice: uniforms + fragment up to ROUGHNESS); (3) `cheap`
      can go (t reaches 1 by itself at ring 4 distances; keeping it maps cheap -> t = 1); thinning is theirs to keep;
      (4) optional: compress/mode=2 (VRAM, DXT5) for another ~0.5 ms in the bench and 4x less VRAM (53 atlases x 21 MB with
      mips uncompressed). Tests: test_veg_impostor (+ far mode lands the plant, shader keeps its uniforms).
  - Groundcover grade (2026-10-08, "groundcover" agent, branch `worktree-agent-a8f70ddf07e7751be`; consumer note 102:
    pixar grass 4,752 / 2,430 triangles a clump, the vale 6.5 M of grass unthinned, so the game thinned to 1,200 / 300 a
    clump and the meadow read sparse; the user's steer: judge quality first, near may be 500-800 triangles, target
    mainstream GPUs not the 890M). `veg_groundcover.py`, `export_plant(grade="groundcover")` (veg_tools.export(grade=)),
    contract 10, guide "Groundcover grade". Scratch DURABLE in /mnt/data/hifipushie/groundcover/: run.sh <script>
    (worktree code on the main workspace), t1.py <plant> <seasons|all> [rebake] (bake cached in bakes/<plant>.pkl, export
    into out/<plant>), q.py <plants> (through the MCP tool into the delivery folders; logs q3.log), gs.sh <tag> <style 0-4>
    <full dir> <gc dir> (each LOD ALONE in the GAME's shader + light, measured against the full LOD 0: gdm/<tag>_sheet.png
    + numbers), g3.sh (gs three ways: mips / no mips / mips + mip-scaled alpha), gm.sh (the same in Godot's
    StandardMaterial: spikes/godot_veg/ground.gd), mw.sh <tag> <style> <season> <full|gc> <grass dir> [flower dir]
    (meadow.gd: a meadow placed, thinned and budgeted as pushieworld's groundcover.gd does; MEADOW_CELL, NOMIPS, MIPALPHA
    env), msheet.py (meadow rows into one sheet), gd/ = a Godot project with a COPY of pushieworld's plant / style shaders
    (+ plant_mip*.gdshader: the mip-scaled alpha), mkplants.py (vs_{grass,daisy,clover,fern}_{real,blobby,anime,cartoon,
    pixar} in workspace/plants), h.py (heads / extent per plant), tris.py (a delivery's triangles by part).
    - How: per LOD a star of vertical cards through the foot (TIERS: 8 / 5 / 3 planes, grids 3x5 / 2x4 / 1x3, pictures
      448 / 128 / 64 px), each card baked square on from the full plant AS THE FULL EXPORT DRAWS IT (veg_look.render, the
      styled dress or the realistic cards) with only what stands in its own double wedge round the foot: a `sector` view
      key in blender_vegetation (pass materials get nodes hp_sec_*: cut by azimuth about the foot). Parts are cut WHOLE by
      their middle (attribute hp_c = (x, y, flag) on the solid / wood meshes and on twig instances, veg_look.part_middles):
      flag 1 = a part pointing one way from the foot (within WHOLE_DEG 12; a fan of blades joined at its root is cut by
      pixel, flag 0: kept whole, pixar's 6-blade fans lay on one card as one broad leaf), 2 = a HEAD (veg_look.parts:
      compact, < HEAD_SIZE 0.12 H, middle over HEAD_UP 0.4 H; gathered into heads by single linkage, veg_groundcover.clusters)
      -> two crossed cards of its own per head (a round head on a wedge card seen along it was a sliver), phase of its
      stalk's card; tiers with more heads than TIERS.heads leave them on the wedges. Low wide plants (H < FLAT 1.15 R:
      clover, fern) add a card lying flat at 0.45 H baked from above. Bake: SUPER 2x renders averaged to coverage, alpha /
      COVER 0.55 (thin blades kept), the clump's shade baked in (as impostors), a tangent-space normal map against each
      face's frame. Front and back single sided, NORMAL = up + LEAN 0.6 out from the foot + FACE 0.7 toward its own face
      (mirror images; TANGENT w +-1): straight-up normals caught blobby's rim light from the side (pale far clumps, colour
      off 0.12-0.14; with FACE 0.02-0.035). Seasons = variants of one `foliage` slot (winter regrown lying, snow = winter +
      spec snow 0.8); one atlas per season holds every tier; the picture extents are the union over seasons. Bakes are
      cached by spec + code (~/.cache/hifipushie/groundcover); 1-10 min of Blender a plant for 5 seasons.
    - ALPHA THROUGH MIPS (the main finding): with generated mipmaps an alpha test drops thin blades (pixar LOD 0 covered
      0.50 / 0.44 / 0.23 / 0.07 of the full plant's area at 2 / 4 / 8 / 12 m). A halo (alpha just under the cut round every
      shape) kept far coverage but fused close blades into broad leaves near (HALO kept as a per-tier option, off). No
      static picture holds from mip 0 to 3, so the engine must either import WITHOUT mipmaps (pushieworld's PNG imports
      already do: 0.59-0.80 at 2-12 m, shimmer) or scale alpha by the mip level (MIP_ALPHA_RECIPE, Golus: alpha *= 1 +
      mip * 0.25; 0.76-0.98 at 2-12 m) — in the material extras `alpha_mips` and the contract log.
    - Numbers (game shader, pixar grass, mips + mip alpha): LOD 0 512 triangles (was 4,752 full LOD 0), LOD 2 36; meadow
      (meadow/px_sheet.png): BEFORE 405 clumps / 1.32 M triangles (the game's thinning), AFTER all 2,587 clumps / 0.36 M.
      Blobby grass: LOD 0 504 / LOD 2 60 vs 720 / 246; colour within 0.02-0.035, IoU 0.6-0.7 near.
    - Read: the meadow is dense and reads as the style; near, cards are a touch paler and sparser per clump than the full
      plant, a blade seen exactly along its card thins out, heads are flat discs on crossed cards (no ball shading in
      blobby: the style ignores normal maps; `FORM` paints the part's own shading into the albedo instead).
    - Bakes are cached by spec + `BAKE_VERSION` + the growth / style / Blender code (not this module's bytes: composing
      never re-renders). The style SHEET's content is not in the key: after editing a sheet's `clump` block, rebake.
    - STATE (2026-10-08, evening; contract 12): deliveries /mnt/data/hifipushie/vegstyle/<style>_<species>_ground/:
      grass x 5 and daisy x 5 and real clover stand (in pushieworld's game: grass + the four styled daisies, "GOOD");
      fern x 5 and styled clover x 4 are WITHDRAWN (a DROPPED.json in the folder). Judged in Godot against the full
      plants (allm.sh / jm.sh / clm.sh; full references by qfull.py in full/): fern FAILS (real: lies flat from 8 m, the
      full one is a standing shuttlecock and only 172 triangles; cartoon: the bold 8-leaf rosette becomes a thicket of
      strokes with the flat top card's edge as a bar): `veg_groundcover.UNSUITED`, the export refuses. Styled clover: the
      full plant is 288 triangles, the grade 378. Real daisy: 0.17 of the full plant's area (thin stalks), full 406
      triangles: delivered, not worth loading. Real clover 1,102 -> 498, a denser mat than the full one at distance.
      Pixar daisy: heads read, leaves thin (IoU 0.3-0.4). Rule of thumb: under ~1,000 full triangles, scatter the full plant.
      A fix for rosettes, not built: fronds on the wedges square to each card, no top card when H > ~0.5 R.
      The bake cache is zlib'd (was 300 MB a plant, 4.8 GB). `<name>_seasons.json` carries grade / lods / alpha_mips
      (Godot drops material extras) and is written even when no slot changes with the season.
      Godot under godot-quiet: quit() hangs for minutes after the files are written; the harnesses end with OS.kill.
  - SWARD (2026-10-08, the same agent; the user on the tuft meadow: "what about just grass?"; contract 11;
    `veg_sward.py`, species presets sward / sward_mown / sward_rough, sheet block `sward` in every style, guide "A field
    of grass"; sheets workspace/veg_renders/gs_01_grass_three_ways.png, gs_02_sward_styles.png, gs_03_sward_variants.png;
    deliveries /mnt/data/hifipushie/vegstyle/<style>_sward_<variant>/ (15, plants vs_sward<variant>_<style>); scratch in
    /mnt/data/hifipushie/groundcover/: sw1.py <out> name=<spec json> (swards straight to files), swall.sh "<variants>"
    (all styles exported + judged), fd.sh <tag> <style> sward|tufts|tufts_full|bare <dir> (spikes/godot_veg/field.gd in
    gd/ + field_measure.py -> field/<tag>_eye.png, _high.png, table.txt), fsheet.py (rows + numbers), swc.py (the card
    patch alternative, veg_sward_cards.py), qs.py (deliveries through the tools)).
    - A 2 m TILE of blade ribbons (opaque geometry, no alpha): roots jittered on a torus, height / lean direction / tone
      / clumping from periodic noise, so tiles laid edge to edge with quarter turns show no grid; 4 LODs = nested subsets
      of the blades, wider (share x width = 1), 3 / 2 / 1 / 1 segments, rings 8 / 20 / 35 m then the fade (mown: 2-segment
      blades, rings 5 / 10 / 18). Undersides are their own triangles with normals mirrored through the blade and never
      pointing down (double sided, Godot flipped the up-leaning normals: black blades; straight-up normals caught the
      blobby / anime rim light: white blades).
    - Picked by measure (Godot, the game's shader, realistic meadow, standing): card patches (7 alpha cards / m2) cost a
      third of the GPU time and hide as much ground, but read as a maze of little hedges from 2-8 m; tufts on the game's
      grid hide 2-14% (full plants thinned) or 10-40% (groundcover grade); blades 38 / 78 / 94 / 100% at 2 / 6 / 12 / 30 m.
    - Numbers (this laptop's 890M under load: an upper bound; bare scene 1.4 ms): realistic meadow 3.37 M triangles /
      16 ms, mown 1.35 M / 8 ms, rough 2.37 M / 11 ms; blobby meadow 1.17 M / 7 ms; cartoon 1.32 M / 8 ms; anime 2.57 M /
      12 ms; pixar 4.99 M / 22 ms (1.5 x the blades: the heaviest). Per m2 (realistic meadow): 5,025 / 1,206 / 201 / 80.
    - The far end: the engine shrinks blades into the ground and mixes their colour to the terrain grass colour past
      `fade.start` (recipe + ground / root / tip colours in the seasons json `sward`); roots take the terrain's grass
      colour for the cover kind through the plant style's `colour`.
    - PER-BLADE LOD (contract 12; the coordinator from 25 m up: darker tile-aligned squares where the rings change, a
      brightness step at the fade): each vertex carries `across` (its offset from the blade's centre line, TEXCOORD_4)
      and (rank, this mesh's width multiple) (TEXCOORD_5); the vertex shader draws the share S(d) of the blades for the
      vertex's distance (log-interpolated through the rings): a blade of rank r sinks as S passes r and the rest widen,
      so mesh k at its ring draws what mesh k - 1 draws there (tested in numpy: test_lod_thins_per_blade...). Tiles pick
      their mesh by their NEAREST point. Rings moved in (meadow 5 / 12 / 24, last LOD 5% of the blades x 20 wide):
      60 m field real 3.37 -> 2.03 M triangles at the same ground hidden, pixar 4.99 -> 2.22 M (density 1.5 -> 1.1),
      anime 1.49, cartoon 0.77, blobby 0.69; mown 0.6-1.9 M, rough 0.5-1.6 M. The fade: albedo, NORMAL and ROUGHNESS go
      to the ground's from `fade.blend_from` (roughness alone left an arc in pixar's specular light).
      Reference lines spikes/godot_veg/sward_blades.gdshaderinc; the scratch project's copy of the game's shader
      (gd/game/style/plant_mip.gdshaderinc, SWARD_FADE) is what the pictures were made with.
    - Density (`sward.density`): how a sward ends; shader-only (no channel): Sd = S x density in the threshold, the
      width factor keeps S, blades shorten. FIELD_PATH=1 ./fd.sh draws a path through the field.
    - Seasons: factors = terrain_style.season_colours of the grass / turf layer in the same style (`season_factors`);
      winter = lying straw by a world-drifting direction (per-blade by NORMAL tore blades into confetti: the two edges'
      normals differ and the underside's is mirrored); snow = the tile sunk by `snow.depth_m` (clamping buried vertices
      to y 0 would z-fight the ground), fade colour = the snow's. SEASON=winter|snow|autumn ./fd.sh.
    - In pushieworld's game (their note 111): "the best single change to the ground so far", 2.0 M triangles / 24 ms in
      the vale on the 890M, renderer built from the json's recipes alone. They asked for contract discipline: batch
      changes, announce a bump to the coordinator BEFORE files change, never three bumps in an afternoon.
    - Sheets: workspace/veg_renders/gs_04_sward_styles_blade_lod.png, gs_05_sward_path_winter_snow.png,
      gs_06_sward_mown_rough_styles.png (gs_01-03 = before the per-blade LOD).
    - Open: winter straw is thin (~30% of the ground hidden near) and one tint; snow depth is a constant (the engine
      should drive it); tiles are flat (the renderer recipe says tilt or sample the height); no flowers in the tile;
      the styled swards' winter / snow were not rendered (realistic only); the card-patch path (veg_sward_cards.py) is
      dead code kept for the comparison: delete it.
- Open (read of vg_36, 2026-10-06; superseded by Vegetation 2 above for pine, spruce, willows): pine still an umbrella with a pole trunk and ribbon-like needle cards; spruce a
  good cone but bare wood shows through low down; weeping willow a mushroom (dome envelope over a stalk of curtains);
  white_willow thin after the shadow change; birch good at range, bark marks not judged close; oak the best.
  Not done: wet smear, snow on ground/limbs, wind measured by displacement, 8k pine set re-run. Earlier: low LODs need bough-sized cluster cards (20k oak = a few big clumps); spruce close-ups are feather cards;
  weeping willow is a ragged column, not a dome; snow doesn't lie on the ground; wind clip's difference image is
  muddied by alpha dithering; collision mesh 2.5k triangles on a birch; stages 3 (small plants, palm), 5 (styles) and
  terrain integration not started.


## Realistic trees (realtrees agents, branch worktree-agent-aaf6ba14fbb49e2c5)
- Realistic trees for the consumer (2026-10-08, "realtrees" agent, branch `worktree-agent-aaf6ba14fbb49e2c5`; pushieworld's
  realistic region showed anime stand-ins; deliveries /mnt/data/hifipushie/vegstyle/real_spruce, real_pine (+ _interior,
  _edge), real_oak, plants `vs_<species>_real[_in|_edge|_b|_c]`, contract 9 unchanged, budget 20k like pixar_oak; sheets
  `workspace/veg_renders/rt_*`; scratch DURABLE in /mnt/data/hifipushie/realtrees/: run.sh <script> (capped, worktree
  code, main workspace), grow.py, lod.py <plant> <png> [budget] (each LOD at the PIXEL size a 1080p / 70 deg camera
  gives it at 5 / 30 / 64 / 128 / 192 m), view.py (game-resolution crops, full vs budgets), atl.py (the atlas each
  budget draws), cov.py <plant> [budget] (per LOD: cards, grow, covered area vs LOD 0, card area / covered: seconds, no
  Blender), export.py, check.sh <tag> <height> <dir> <stem> (od_glb.py triangles / overdraw / under ground, Khronos,
  gd.sh = octa impostor vs LOD 2 + cards at the switches through godot-quiet), bench.sh (impostor forest GPU ms),
  stand.sh <tag> name=dir/stem ... (spikes/godot_veg/stand.gd: 64 trees at 3.5 m seen from inside: GPU ms, fragments
  per pixel), sheet.py, sil.py, variants.sh, q*.sh (export queues), tests.sh).
  - The realistic export at 20k as it was FAILED by eye: a spruce's 937 fourteen-triangle bough cards were 2.7 m
    boughs = a heap of palm fronds at 30 m (its LOD 2, whole limbs, read better than its LOD 0). `veg_bough.fit` now:
    the FINEST cut of the tree (boughs of ~2 twig lengths: `most`), on seven-corner cards without a middle vertex (10
    triangles a crossed pair, `FORMS[1]`); a LOD draws at most `FULL` 0.45 of that cut's boughs (never fewer than
    `FULL_LEAST` 500 or all of them), chosen evenly in space (`place`: one per grid cell, then by hash), each grown
    until the kept cards cover what the whole cut covered (the cards' own polygons from two sides; sqrt(k / n) made a
    sparse pine's LOD 2 25% fat in Godot). All LODs: one atlas, one slot `foliage_boughs1`, one silhouette. Under
    `THIN` 0.08 of the cut the old re-cut into whole-limb cards (form 0). Triangles the foliage can't use go to
    the wood (`_budget`: spare > 10%). Bough tone per card 0.88-1.12 (0.75-1.25 read as pale and dark leaves).
  - Overdraw (consumer note 108: real_spruce stand 46 ms vs 17-22 with the anime stand-in on the 890M). Reproduced
    with stand.gd (1280x720, 37 LOD 0 + 27 LOD 1 trees, no shadows): real 8.4 ms / 121 card fragments per pixel, anime
    5.2 / 76, pixar 4.8 / 99. Card area / covered area in the file (od_glb.py) LOD 0 / 1 / 2: spruce 6.6 / 6.4 / 5.8 ->
    4.1-4.5 / 3.8-4.0 / 2.8-3.1; pine 8.3 / 7.3 / 6.0 -> 4.3-4.7 / 3.6-3.9 / 2.4-2.6 (anime spruce 5.6 / 4.3 / 3.2, pixar
    3.5 / 2.0). What did it: fewer boughs grown to the same cover, spread evenly, tighter cards.
    DEAD ENDS: culling boughs hidden behind others (`outer`: 22 directions, first two card layers): a spruce's and a
    pine's boughs are ALL first-layer from somewhere, the crown is already a shell (`CULL` off); one card of each
    crossed pair, the one facing out (`SINGLE` off): overdraw 3.0-4.2 but the spruce went ragged and see-through, its
    flank cards edge-on; a whole-limb re-cut for LOD 1 (covered 0.85 of LOD 0, lost its top).
    What a STAND needs most is the stand FORM: 64 open-grown spruces at 3.5 m put the eye inside six skirts; the
    interior tree (`environment.setting` forest, spacing 3.5: bare stem, live crown the top 31%) has ~170 boughs.
  - Variants = separate plants (seed / age / a small `forces` lean on order 0), stand forms = `environment.setting`
    forest / edge + spacing. An export takes 27-75 min on the loaded machine (the impostor's 64 views x 4 passes).
  - Limb layer (`leaves.card.limbs`: true = every first-order limb, a number = masses of that size in m, a pine's
    plates; `veg_bough.limbs_on / limb_plan / extra`): under the fine bough cards every whole limb on its own crossed
    pair in the same atlas (tiles `size_limbs` 512), tinted dark toward the trunk (`veg_export.CORE_DARK`), its top card a
    ladder of `LIMB_STRIPS` rungs at the heights the limb's foliage has (flat, a sweeping limb was a shelf). It is what
    closes a spruce seen from 30 m; from below at 5 m the limb cards are blurred green blobs (few texels): open.
  - Round 2 (2026-10-09, "realtrees2"; sheets `veg_renders/rt2_spruce.png`, `rt2_pine.png`, `rt2_bark.png`,
    `rt2_stand_godot.png`, `rt2_interior.png`; scratch adds q6.sh <tag> (quick LOD exports without impostor of the four
    main plants + gview frames + a stand: ~25 min), q7.sh (the six folders), tg.py, deadcnt.py, tile.py, ab.sh).
    - Bark by the photos (workspace/veg_refs/bark/, barksheet.py): spruce "scales" as steps of a noise with drawn rims
      were worms / camouflage (isolines close into loops, as terrain found); now SHINGLES: Voronoi cells of every size
      (`_cells(loose=)`: that share of the seeds anywhere; `local=` = each pixel's offset from its seed), each flake
      rising toward its lower edge, no grout, a thin shadow only under a proud edge, ragged edges by a fine warp.
      Pine "plates": the jittered grid of tall cells with smooth warps was a woven basket; loose seeds + ragged warp +
      less columnar blocks read as furrowed plated bark. Pine bark colours browner (it rendered purple).
      `test_bark_maps_tile` now averages the seam over six seeds (one tile can have a plate's edge on the seam by chance).
    - Spray: `twig.curl` (side shoots sweep forward: straight ones at one angle were a fern frond / fishbone) and
      `twig.tips` (lighter toward every shoot's end); spruce card: curl 0.6, tips 0.45, sub_shoots 1, 7 side shoots.
    - Spruce limbs turn up (tropism[1] 0.45, sag 0.6): the open tree's skirt stands 0.6 m clear; the interior / open
      crown-base gap shrank to 0.195 of the height (test margin 0.2 -> 0.15).
    - The gv/new_* "before" frames of 02:20-02:40 predate commit 1a4d43f: the interior spruce's dense dead haze in
      them was already gone in what q5 delivered (dead bough cards "keep their size"): compare against a fresh export
      of HEAD, not old frames.
    - BLUNT: spruce = a plausible dark conifer, too broad and lumpy against spruce_a's narrow tiered spire, foliage
      still reads cedar / cypress at 5 m; pine = a young clumpy pine with blue-dark blobs, nothing like an old
      Caledonian pine; bark is the clear win (both read as their bark in a stand). Interior spruce: bare poles with
      straight stub spikes and a few black tangles: the dead haze is too thin and its cards shade black from behind
      in Godot's standard material.
    - NOT DONE: stand debris (dead haze density / tone, floor brash), the 5 m view from under limb cards, spruce
      silhouette (narrower, tiers), oak and variants (no real_oak folder exists), impostor re-judged by eye.

