# hifipushie

MCP server for LLM-driven character/creature modeling. The design principle: give the model
representations it reasons well in (skeletons, named parts, numbers) and feedback it can act on
(consistent multi-view renders, rulers, numeric silhouette errors), not mouse control.

## Layout
- `src/hifipushie/spec.py`: spec format, ".L" → ".R" mirroring, compile to primitives. Read its docstring first.
- `sdf.py`: numpy SDFs (round cone, ellipsoid), smooth union/subtract, narrow-band grid eval (8³ blocks,
  exact only where the surface can be), marching cubes, Taubin smoothing, then `project`: Newton-steps
  vertices onto the exact field and takes normals from its gradient (renders/OBJ use these normals).
  Clipping uses `Prim.reach`/`inert` from `spec._set_reach`: a primitive may only be skipped where neither
  its own blend nor a later overlapping primitive's blend can see it. Flat bones and flat ellipsoids
  under-report distance, so their reach is scaled up. Break that and you get flat seams in fillets.
- `kits.py`: parametric parts (`hand`, `face`) stored under `spec["kits"]`, expanded into ordinary
  joints/bones/blobs before mirroring (`spec.expand_mirror` calls `kits.expand`). The face kit seats
  features onto the kit-free body by raycasting the field, so they follow skull edits. Eyelids are the
  `"shape": "lids"` blob (`sdf.sd_lids`: solid cap with a radial almond opening, never a thin sheet).
  Kit defaults keep details a few voxels wide at close-up resolution: sub-voxel creases render as zigzags.
  Chains (fingers, lips) are many short segments in one `group` (`sdf.units`): joined by hard min (or a
  small `join`), then blended into the body once. Per-segment smooth unions bulge at every joint.
- `anatomy.py`: modelling lore by joint type instead of a kit per body part (`spec["anatomy"] = {}` opts in; per-joint
  overrides). Limb roots are found from the skeleton (side chains of 2+ bones: next to a centre hub, or the chain's
  inner end). Each gets a cap (one bowed, flattened bone over the joint's outer side: separate heads read as lumps),
  and, beside the body (limb runs back along the body's axis: arms), pec/lat sheets ending on the limb's inner side
  (the pit's folds); leaving the body's end (legs, a quadruped's legs), a round bowed mass behind (glute, triceps) and
  no front sheet. The joint's bones slim to 0.8 r there. Sheet origins are seated by a ray from inside the torso
  (`_exit`; from outside the fox's glute landed on its tail). Expands after kits, before strokes (`expand_mirror`,
  `fit`, `paint`). Tried on troll, goblin (arms moved clear of the belly: `goblin_anat`), fox (`*_bare` / `*_anat`).
  Hinges (every joint inside a limb chain): a small crisp bony point on the extensor side (rest bend projected onto
  the front-back plane: an arm hanging out from the body bends sideways, which isn't flexion), bones slimmed 0.9.
  Each limb's bones become one group (join 0.15 x the thinnest hinge), blended into the body once: one by one they
  swelled all round every joint. `spec._compile` gives every group member the group's first blend/join: the
  evaluator culls per chunk, so a group with mixed blends blended differently chunk to chunk (dotted seams).
- `strokes.py`: sculpting on the surface. A stroke's path is addressed on the kit-expanded, stroke-free body
  (out from a bone axis, or a raycast), resampled on a Catmull-Rom curve and re-seated, and becomes a
  "displace" or "flatten" blob: an op "modify" primitive (`sdf.MODS`) that reshapes the field combined so far
  instead of unioning a shape. A stroke is a normalised sum of dabs along its densely resampled path (each
  depth * profile(distance across the surface / width)), like a sculpt brush: measuring from the nearest point
  of the polyline instead kinks the surface at every sample (stripes in raking light/curvature). Seated paths
  and normals are Gaussian-smoothed along the path (normals over lids/nostrils swing and streak deep strokes).
  Width/depth ease between control points (smoothstep). Modifiers make the field steeper than 1 (`Prim.lip`); `evaluate` widens its
  band by the max lip.
- `render.py` + `blender_render.py`: headless Blender workbench/matcap renders, contact sheet with rulers.
  `look(strokes=True)` draws stroke paths (visibility by raycasting the field); `shading="raking"` uses a
  generated low-side-light matcap, `"curvature"` colours vertices by the field's Laplacian (convex warm).
  `smin` is cubic (C2): the quadratic one left curvature jumps at every fillet edge, visible in highlights.
  `look(hide_parts/only_parts/clip)` goes through `store.view_mesh` (`<stem>_view.npz`: a face subset, verts
  beyond a clip plane pulled onto it, `src` = indices into the base mesh) and `store.section_caps` (grid cells
  on each plane inside a shown part's exact field, part colour darkened; shell parts only fill what solid parts
  don't, so clothes cut as a rim), loaded by Blender as an extra object. `camera` panels are perspective
  (`render.camera_frame`, `blender_render` switches the camera type per view; no rulers, no stroke overlay);
  an eye [x, y] stands on `measure.stand_height`. Camera-only looks also cull faces outside the frusta.
  Painted looks go to the Blender scene (`scene.look`, see "Next session"); these views are clay per part.
  `measure.clearance` (tool `clearance`): walkability
  from vertical columns of `field_at` (floors, headroom), a capsule clearance test and horizontal width rays.
- `measure.py`: cross-sections of the exact field (`sdf.field_at`): rays from a bone axis, or world-axis slices.
  `stand_spot` (cameras' [x, y] eyes): the floor there, stepping off furniture (a surface the floor drops away
  from 0.25-1.3 m in 70%+ of directions: not a doorstep or raised floor) or from under a table. `doorways` (box
  cuts with targets, 1.6 m+, reaching the floor) and `check_doorways` (a person walked through each, the element
  in the way named): part of `check`.
- `compare.py`: reference mask extraction, placement (FFT shift search per scale + sub-pixel refine, kept as a
  continuous transform onto the full-res image), diff image, band tables.
- `fit.py`: silhouette auto-fit. Levenberg-Marquardt on a symmetric outline chamfer; Jacobian columns come from
  `field_at(clip=False)` at each outline point's closest-approach depth (envelope theorem), so no autodiff.
- Parts: every element has a `part` (default "body"); `sdf.streams` splits prims by part, each part is its own
  field (evaluate/field_at hard-union them) and its own mesh (`store.build` meshes each on one shared grid,
  npz carries `part`/`part_names`/`part_colors`, OBJ export writes one object per part). A shell part
  (`spec["parts"][name] = {"shell": base, "offset"}`) is its base part's field pushed out (`sd_shell`),
  intersected (op "intersect") with the union of its layer-0 adds. Solid on purpose: thin sheets alias.
- `surface.py`: `Points`, a set of surface points (mesh vertices or baked texels) with position/normal/part and
  lazily computed field inputs: `curvature` (field Laplacian / 2), `thickness` (depth where rays along -normal
  leave the part), `hidden` (buried in another part), `grain`/`grain_seed` (element axis). `ao` and `sky` come
  from Cycles (the scene) through `cache`. `moved` drops offset points back onto the surface with one field step.
- `paint.py`: `spec["paint"]` layers. Most generators compile to shader nodes (`paintnodes`); what nodes can't
  do (paths, near distances, blur, ".L" mirroring, weave) is evaluated per point here (`layer_mask`,
  `_generate` on a `surface.Points`) and handed to the scene as vertex attributes. Paint never rebuilds geometry. `spec.geometry` strips paint and plan before expansion/compilation: keep it that way, or every paint
  edit re-seats strokes and rebuilds. A layer's mask (`layer_mask`) is a stack: flat keys become leading
  multiply entries, then `"mask": [...]`; each entry is one generator (`_generate`: path seated with the stroke
  machinery, `strokes._generate`, as a sum of dabs with a faces-the-same-way test against print-through; near
  (primitives' own SDFs; kit names expand to `<stem>_*<sfx>`); facing; axis; cavity; noise (value fBm on rotated
  lattices, optional stretch/domain warp); cells (3D Voronoi F1/F2/id); ao; thickness; nested mask) then
  `_post` (breakup = noise-shifted threshold, levels, invert), then blended. `blur` averages at jittered points
  (`_View.jittered`) but only where a cell grid of the unblurred mask shows variation (`_blurred`): keep that,
  it's 10x. ".L" layers take the max of the stack at the point and its mirror (`_View` mirrors position and
  normal; field inputs stay the point's own). `bump`: layers' `height` x mask summed, slope by central
  differences across the surface, tilts normals (vertex normals in look, the normal map + height map in the
  bake). Coverage counts only points not `hidden`. Colours are sRGB everywhere in the spec; `blender_render`
  converts part/paint colours to linear for the colour attribute. OBJ export writes `v x y z r g b` (Blender
  reads it). `look(shading="flat")` is unlit colour.
- Hand-painted masks (`paint` generator `"painted": id | "new"`): a point cloud (world pos, normal, value, the
  painting object's voxel) content-addressed in `workspace/_painted/<id>.npz`, evaluated per point by
  `paint.painted_values` (8 nearest within 2 spacings, facing-gated so thin boards don't print through).
  `scene._paint_inputs` writes each object of the layer's parts an `hp_paint:<layer>` array; `blender_scene._inputs`
  makes it a POINT FLOAT_COLOR attribute (Vertex Paint, white = 1) and stores its checksum on the mesh
  (`hp_sum:<layer>`); `blender_scene._pull_painted` sends every object's points for any layer whose checksum
  moved, `scene._pull_painted` saves the cloud and writes the id (`paint.set_painted`). Prefab paint sits where
  the bake instance stands (world coords): moving that instance leaves the paint behind.
- `materials.py`: `{"material": ...}` paint layers expand (`paint.layers`) into sub-layers `<name>:<sub>` built
  only from ordinary generators (plus `tiles`/`weave`, 2D patterns laid triplanar by `paint._planar`); the
  layer's own masks confine every sub-layer as a trailing nested multiply; coverage reports the first
  sub-layer under the material's name. Tune materials on `workspace/swatches` (panel + ball per material).
- `asset.py` + `blender_asset.py`: game-ready export. `split` decides what is meshed: the model's parts minus the
  instances of shared prefabs (2+ instances, `prefabs.<p>.export` not "unique"), plus each shared prefab's parts
  ("<prefab>/<part>") from its bake instance (first unmirrored), by `Prim.instance` (set from the element's
  "instance" key, which `assemble._place` writes with a "local" world->prefab frame; lumpy/chips noise runs in
  that frame and is seeded by the prefab element, so instances are identical, mirrored ones too). Prefabs mesh
  in their own box (`mesh_parts`, voxel down to their size / resolution). Projection uses the export part's
  stream (`ctx["streams"]`); AO, sky and paint use the whole model (`ctx["full"]`, model part names), so a
  prefab is painted as it stands at its bake instance. `write_glb` puts a prefab in one mesh (a primitive per
  part, its frame) with a node per instance (TRS, mirrored = negative x scale, extras.prefab); `triangles` counts
  drawn triangles (`budgets` weighs parts by copies). `texel_density` (texels/m): `density_groups` bins units
  (a prefab's parts together) first-fit by load at a guessed pack fill (`FILL`), Blender unwraps with per-atlas
  sizes (`textures`/`margins` in the job), then each atlas takes the smallest power of two meeting the density;
  an atlas that can't at `texture` triggers one regroup with the measured fill. `prune_hidden` drops faces buried in another part.
  Flat regions are dissolved first (`planar.planar_regions`, numpy: grown against the SEED face's normal and plane,
  so gentle organic curvature never chains; disks only; one ngon per region), per part in a process pool before
  Blender starts (`asset.flatten_parts`, cached as `lowpoly_flat.npz`: 258 s -> 18 s on cabin5), and a part's
  triangle floor shrinks with its flat share. Worker Blenders (`blender_asset.reduce`, up to 8) collapse every part
  on its own to 80x its average share (`PRE`), then one joint collapse of all parts decides each part's share
  (quadric error: area shares starved small round parts next to big walls; the pre-collapse keeps the full joint's
  shares within ~3%), then `budgets` applies `triangle_weight` and a floor; a part keeps its piece of the joint
  result unless its budget moved or the mirrored collapse folded triangles (Blender skips its fold check when
  mirroring: black triangles on flat faces), then workers decimate it alone from its pre-collapsed mesh. The joint
  result undershoots the drawn target ~2x (it can't see that cups are drawn 18 times), so nearly every part is
  redone: that's expected. Low poly on cabin5: ~13 min -> ~2 min. Per atlas (`parts.<p>.atlas`,
  `atlases=n` by load): smart project, `_charts` merges islands too thin/small for their margin into a neighbour
  if the chart stays within a 75 deg normal cone (re-projected along its mean normal), `texel_focus` spheres cut
  their own islands, every island is scaled to its density, pack (CONCAVE, margin = texture/512 texels as an
  exact fraction; the old "scaled" margin around thousands of islands left the cabin atlas 6% full). Hands back
  per-corner uv/normal/MikkTSpace tangent and each part's atlas; the json reports mm/texel per part.
  `bake` (per atlas) rasterises triangle ids (PIL "I" polygons), projects each texel onto its part's exact surface
  (`asset._project`: every 4th texel both ways by `surface.newton` from the low poly, the rest from the offset
  interpolated off the anchors of their own uv island (`uv_islands`), 1.6-2x faster; a texel falls back to the low poly only if it moved > 6 voxels or
  its exact normal faces away, dot < -0.2: steep outward detail like shingle butts is real), reads normal
  (tangent space against the exported low-poly frame, z >= 0.02), height (along the low-poly normal), paint
  channels, AO and painted height from the Blender scene (`scene_maps`, see "Next session" step 4). Maps are
  dilated (EDT nearest fill). `write_glb` writes glTF by hand (one material per atlas; Y up: x, z, -y; uv v flipped; ORM; specular in
  the alpha of an extra texture, KHR_materials_specular with specularColorFactor 2 so 0.5 = F0 0.04). `preview`
  (`hide=` parts) renders the GLB in Cycles through Blender's importer, which ignores glTF occlusion: check the
  AO map itself too. Sub-voxel detail (the cabin's 22 mm shingles at 24 mm voxels) makes a broken high mesh
  (inverted faces); those texels fall back, the log counts them per part. After the cone merge, `_grow` joins
  charts sharing >= 30% of the shorter perimeter when the union is a disk (Euler characteristic 1: a log's strips
  join but never close into a tube), unwrapped conformally together, kept if `_stretch` <= 1.08 (30% fewer islands,
  fill 58 -> 60% at 8k). What limits fill is each island's texel footprint (rasterised + margin), not strips: at
  2048 / 24 mm texels thousands of tiny and 1-2 texel wide islands (chinking, cups) cap every packer near 45%.
  xatlas (tried 2026-09-25) mixed islands up when packed together (0.0.11 binding) and gained ~10% where it
  worked: dropped. Ray misses (~5%) are 84% edge texels (centre outside the triangle: Blender bakes centres only,
  dilation fills them); the rest are low-poly faces bridging gaps (between books, slats, window frames), logged
  per part.
- `rig.py`: the export rig, a separate step over the modelling skeleton (the user, 2026-09-25: humanoids must be
  Mixamo-compatible and Unity/Unreal-retargetable, clean bone chains for non-humanoids too; spec bones stay for
  modelling). `humanoid` fits Mixamo's skeleton (mixamorig:Hips, Spine/1/2, Neck, Head, clavicles, arms, hand-kit
  fingers as Thumb/Index/Middle/Ring/Pinky 1-4, legs, ToeBase, *_End) to pelvis/chest/neck/head/limb joints (Neck
  at shoulder height, clavicles 20% out from it; `spec["rig"]["joints"]` overrides); `chains` for other creatures
  (`spec["rig"] = {"type": "chains", "root", "chains": {name: {"from", "joints"}}}`). `rig_weights`: each rig bone
  gets flesh: the piece of a modelling cone it lies along (`_cone_piece`: Spine/Spine1/Spine2 split the spine
  cone), modelling bones inside its segment, the rest by the nearest rig segment to their middle, blobs by their
  middle; empty rig bones get a thin cone. Then `weights` on the rig tree: exact per-flesh distance,
  exp(-(d - d_min) / (0.5 r)), limited to the nearest bone's family within two steps (unrelated bones crowding the
  4 slots made cracks), smoothed over the mesh, top 4, then `_settle` (smoothing with each vertex's 4 fixed, so a
  dropped bone fades instead of stepping: hairline cracks). Judge with the `rig` tool (test pose, front/side);
  export_asset(rig=True) writes the joints (identity rotations at their heads, rest pose as modelled) and skin.
  `spec.geometry` strips `rig`.
- `realism.py`: `spec["story"]` (validated; stripped by `spec.geometry`, like paint; its `directions` can be
  named in paint `facing`) and `audit`, the perfection warnings `check` always appends. `assemble` applies
  `spec["weather"]` ops: instances as rigid bodies first, then elements by tag. `chips`/`lumpy` live in the csg
  wrapper (`sdf.sd_csg`; chips weighted to edges by the element's own Laplacian). `surface.sky` is the upward
  openness input (rain, sun, shelter).
- `assemble.py`: prefabs/instances and element `array`s expand into plain joints/bones/blobs before kits
  (`kits.expand` calls `assemble.expand`, content-cached), so everything downstream sees ordinary elements.
  `select` resolves names/tags (instances, arrays and `tags` lists are tags). `spec._csg` wraps a primitive as
  kind "csg" (`sdf.sd_csg`) for `hollow` and for subtract/intersect elements with `targets` (the cut is folded
  into each target, not a primitive of its own). Cuts only raise the field, so bounds/reach stay the target's.
  A subtract is folded only into targets its box (+ blend) overlaps: every log carrying every window cut made
  moving one window re-mesh the whole wall (the scene's per-part grids diff primitive fingerprints).
  Order in `expand`: `_walls` (spec["walls"] -> board/box blobs, targeted box cuts, frame/window/door instances
  tagged "from_wall" so `placements` and `scene.pull` know them; pull writes a swung door back as the opening's
  "open"), instances without "on" placed, arrays (then `_between`: flat bones between neighbouring copies of a
  bone array, found along its first step's offset; `_arrays_of` remembers the steps during expansion),
  then "on" instances (`_place_on`, dependency order; `top_of` raycasts a mini-spec of the named elements plus
  cuts into them; resolved positions go to `_ON[key]` so `placements` agrees), then weather on elements.
  `placements` pads [x, y] ats and includes wall-generated instances.
- Joints can be `{"on": address, "lift", "shift"}`: `strokes.seat_joints` seats them on the model without
  them (`strokes.without_seated`, also what kits and strokes seat on, to avoid cycles).
- Style (`spec["style"]`, guide 5c): `style.shape` is applied in `assemble._style_shape` (round, chunk, lumpy, chips,
  bow, blend on every element and prefab) and `spec._deform` (`deform.py`: sag/bulge/taper/lean/twist/wobble; building
  primitives are evaluated through the csg wrapper at the undeformed point, field / stretch; `sdf._Undeformed`
  undeforms each point set once; prefab instances stay rigid and ride the bend, "on" props ride their carrier).
  `style.paint` is applied in `paint.layers` (HSV, pattern scale, materials' wear/dirt) and to part bases in
  `scene.sync`; `spec.geometry` strips it. Worked example: `workspace/cabin_toon.py` (storybook/cartoon/toybox).
- `plan.py`: the 2D blockout plan (`spec["plan"]`): per-view unions of 2D shapes in world units, landmarks,
  sections. `reference()` rasterises a view with its world placement; `compare.place(world=...)` puts it on
  the model canvas exactly (no scale search), so `check`/`compare`/`fit` with against="plan" measure real
  size errors. Workflow stages (plan → blockout → secondary forms → detail) are in the server INSTRUCTIONS.
- `store.py`: `workspace/<model>/spec.json` + `history/`, build cache keyed by spec hash.
- `scene.py` + `blender_scene.py` + `paintnodes.py`: the live Blender scene (see "Next session"): per-object
  meshing and content cache, paint compiled to shader nodes, pull/sync round trip, EEVEE looks, Cycles bakes.
  The scene cache is pruned every sync (`scene.prune_cache`): files none of the last 3 syncs used are deleted
  (content-named files piled up: cabin5's cache was 8.8 GB, 714 MB after). Headless saves keep no scene.blend1.
  Scene parts keep their block grids between syncs (`scene._LIVE`, `LIVE_CELLS` budget per model, most recently
  used kept): an edit re-meshes the blocks it reaches (moving a door: 1.0 s, cold 5.5 s; must equal cold).
  Cycles bakes use emissive materials: every such material needs `cycles.emission_sampling = "NONE"`, or each
  bake call builds a light tree over every triangle (10M on cabin4, ~5 s a call). `bake_maps` renders only the
  part and its low poly per call, 1 sample, passes color / rms / aoh (red ao_raw, green painted height).
- Paint validation at save (`paint.check_refs`): every `near` resolves, every layer `part` exists (a cut named
  in near has no surface: folded into its targets). Weather tags must match something (`assemble.expand`).
  `random` generator: `paint.element_random(grain_seed)`, measured per vertex in the scene (not a native node).
- Live Blender: `scene.live_session(name)` asks the Blender MCP add-on's socket (JSON + NUL, port 9876 or
  $BLENDER_MCP_PORT) whether the person's running Blender has this scene.blend open; then `scene.pull`/`sync` run
  `blender_scene` inside it (`_blender_live`: imports the module, `live: True` skips opening the file; a sync saves
  the session). `blender_scene` dispatches only when run as a script. Test with a headless add-on server:
  `blender -b workspace/<m>/scene.blend --command blender_mcp --port 9877` + `BLENDER_MCP_PORT=9877`.
- `server.py`: MCP tools (mcp 2.x `MCPServer`, not v1 FastMCP).

## Performance (keep these properties when changing things)
- `sdf.field_at` sorts points into Morton-ordered chunks, culls the primitive list per chunk (`_cull`: region
  "intersect" prims always stay) and runs chunks on a thread pool (`_run`; nested calls run inline). Grid
  blocks are processed the same way. Results are identical to the serial path (`_field_serial`).
- `sdf.PartGrid` keeps a part's block grid between builds; `update` diffs primitive fingerprints and redoes
  only blocks in the changed primitives' influence boxes (a shell part also gets its base's changed boxes).
  `store._LIVE` holds these per model plus each part's projected mesh; `_mesh_part` re-meshes and reuses the
  projection of every vertex at the same (quantised) position outside the changed boxes. Incremental builds
  must equal cold builds: compare faces/verts after any change here.
  `PartGrid` records its grid key/fingerprints only after its blocks are filled, and `store.build` holds a
  per-model lock (MCP tools run on worker threads) and drops `_LIVE` if a build fails: a half-updated grid
  (unwritten `np.empty` blocks) meshed into millions of vertices and NaNs that Taubin spread (cabin2, gable).
- `project` uses a tetrahedral stencil (value + gradient in 4 evaluations) and drops converged vertices.
- Displacement strokes query only nearby dab samples (KD-tree, `k` nearest within `radius`).
- Caches keyed by content: `compile_prims`, kit expansion, each stroke's seating, seated joints, KD-trees.
  `expand_mirror` copies structure but shares numeric leaf lists (`_tree_copy`): don't mutate those in place.
- `fit` works on a frozen copy (kits, strokes, seated joints expanded once) and applies the fitted values to
  the real model; its Jacobian recomputes a column only at points a changed primitive can reach.
- Renders go to one persistent headless Blender (`render._Blender`, `blender_render.py --serve`); the stroke
  overlay's visibility is a z-buffer splatted from the built mesh's vertices.

## Conventions
Metres, Blender axes: Z up, creature faces -Y, its left is +X. Side view shows it facing left.

Second test subject: `workspace/goblin` (upright biped, big face, hands), so we don't tune for the fox alone.
Bump `store.BUILD_VERSION` whenever meshing output changes; the build cache is keyed on the kit-expanded
spec + resolution. `look` with focus + zoom builds only a box around the focus (`build(box=...)`, its own
`closeup.npz`), with `resolution` counted across that box.

## Next session (agreed 2026-09-25): character topology spike

**Where things stand.** 2026-09-25 closed these backlog cards on Overboard (project "hifipushie"):
- painted looks with clip planes and close-ups;
- export quality (edge vs interior ray misses, chart growing);
- hand-painted masks;
- export time (the flatten pool, pre-collapse workers, parallel unwrap, anchor-interpolated projection).

It also added the rig step (`rig.py`, the `rig` tool, `export_asset(rig=True, fbx=True)`), the blade primitive,
the foot kit (fixed after the user saw toes sprouting mid-foot: the instep must slope into toes lying on the ground)
and scene-cache pruning. Rig standards are in memory (`rig-standards`): Mixamo-compatible humanoids, clean chains,
the rig separate from the modelling bones.

**Character topology spike: results (2026-09-25, `spikes/topology/`, README there).** Troll body, `rig.test_pose`,
the same `rig_weights` on every mesh; error = field -> mesh distance, by region (rest / head / hands).
- Skin modifier over the rig graph (+ skull, ears; radii by rays; rings at bending joints; shot onto the field along
  normals, relaxed): DROPPED. Its limbs were the cleanest, but hubs break (chest with neck + clavicles: a
  self-intersecting hull even after dropping the crowding nodes and building it thin; the arm/torso junction
  shreds at 8 segments around), every limb gets the same ring count (4 x 2^subsurf: fingers as many as the torso),
  and the head is a projected sphere with no vertices for nose or brow (63 mm max error).
- Blender QuadriFlow: clean quads flowing along the limbs, the best bends; beats decimation on broad forms per
  triangle (rest 1.2 vs 1.45 mm at 10k), but density is uniform: head and hands need ~4x the triangles (hands 2.2
  vs 0.9 mm at 10k). At 5k: mitten hands, and a web under the raised arm (big quads across the armpit take
  blended arm/torso weights). Loses the thin blade ears.
- QuadriFlow with our sizing field (patched build: `QF_SIZING` file of relative edge lengths; the stock `rho` is
  always 1, its `-adaptive` isn't density; also fixes a comma-operator bug in subdivide.cpp). Sizing = edge <=
  0.5 / max principal curvature (normal turn along edges: mean curvature cancels on a face's saddles and left the
  face coarser than the belly), shortened near bending joints, clamped 0.25-1.6, normalised to the budget, one
  calibration rerun. Head and hands 1.6-2x better than plain at the same budget, no armpit web, a readable face
  at 5k. Overall close to decimation (10k: mean 1.67 vs 1.36 mm, max 21 vs 10). Clenched fingers still merge
  and the ears are still lost.
- Decimation: the best detail per triangle (face, fingers, ears), but slivers along the limbs kink at elbow and knee.
- The dip on top of the raised shoulder is the same on every mesh, the dense one too: that's the weights (linear
  blend skinning), not topology.
- The user saw it first: QuadriFlow's quads aren't loops. `topo_loops.ring_check` (walk quad edge loops from the
  crease): skin mesh rings at all 4 elbows/knees; plain and sized QuadriFlow at 1-2 of 4, the rest spirals (open
  walks of 100-400 edges). Judge loops with the ring check, not by eye.
- Joint loops as features (patch `QF_FEATURES`: crease planes sliced into the high mesh, their edges constrained
  like boundaries: orientation + position): 4/4 rings exactly on the crease (0.1 mm), and the loops beside them close
  too (15/16 at +-0.6 and +-1.2 limb radii) with parallel flow, no poles against the ring. Three constrained loops a
  joint (0 and +-0.6 r) break at 5k (constraints closer than the quad size: the lattice can't fit) and work at 10k
  (4/4, error mean 1.33 mm, decimation 1.36). Rule: constrained loops no closer than ~1.5 local edges; at low
  budgets the crease loop alone, its neighbours follow.
- Shoulders (2026-09-26): a plane can't cut an armhole (a hanging arm's plane runs into the torso). Loops on the level
  curves of a harmonic field from the rig weights (patch `QF_FEATURE_IDS`: per-vertex curve ids, carried through
  QuadriFlow's subdivision) exposed bad weights instead: the arm owned 42% of its own shoulder (the collar cone's
  round end over the upper arm; the torso's radius set the blend width; the goblin's arm flesh sat 39 mm outside the
  arm: `_cone_piece` ignored bones reached from their far end). Fixed in `rig.py` (bisector cuts, thinner-bone blend
  width, piece direction; bones off every rig segment split in quarters). But constrained QuadriFlow runs on those
  level curves stall in the integer stage (>10 min, elbows/knees too; plane cuts took seconds): unresolved.
- The user then called the real problem: shoulders were balls pasted on bodies (troll and goblin), bad geometry to
  rig. Asked for general modelling lore rather than kits: `anatomy.py` (see Layout). Next: the hinge rule (bony
  point on the extensor side, flexor crease, flesh narrowing at the joint); hands and feet as presets over it;
  loops placed from the anatomy (the cap's and folds' edges are the armhole); sheets skinned smoothly along their
  length (four pieces hand over in steps: a fold on the pec's edge when the arm lifts); the pit still streaks under a
  raised arm (LBS, as before anatomy). Face rings, ears QuadriFlow drops, the QuadriFlow stall: still open.
- Decimation stays for environments and props either way.

**Then, in the order the user saw them:**
1. **Rig check in a real engine:** the rigged goblin FBX in Unity or Unreal with a Mixamo animation. This decides
   whether we need a T-pose rest or bone orientations; joints are currently unrotated, rest pose as modelled. It
   needs the user or an engine on this machine.
2. **Export time** (card "Export time: texel projection and Cycles map bake"): at 256/m texel projection is
   ~26 min and the Cycles map bake ~15 min. Skip texels on triangles already on the surface (probe each triangle
   on a voxel lattice). Find why the roof's shingle-array field is slow. Merge parts per Cycles pass. Benchmark
   with nothing else running.
3. **Face kit quality:** cheeks and nose read as stuck-on balls.
4. **Cabin:** the weathering restraint pass, then its final export.

**Gotchas from 2026-09-25:**
- Keep heavy exports alone on the machine, or the timings mean nothing.
- Exports and scene caches can fill the disk. The scratchpad lives in /tmp, which is on the root disk: clear old
  export folders.
- Background shell jobs can start minutes after launch.

## The Blender scene becomes the pipeline (2026-09-23, done)

Agreed with the user (2026-09-23): lean on Blender's strengths instead of maintaining our own versions of what it
does best-in-class (ray-traced AO/sky, shading, baking, viewing). The spec stays the source of truth and what the
model reasons in; Blender holds the derived scene, renders it, bakes it, and lets the user look and edit.
User's words: "we can lean on blender's strengths", and on AO/sky even without a speed win: worth it "so we
don't end up maintaining a code path that's already best-in-class". They want two-way editing (their tweaks in
the .blend come back as spec edits).

**The spike (done, `3ca1d04` + later commits), on `workspace/cabin2`:**
- `scene.py` / `blender_scene.py`: `workspace/<model>/scene.blend` derived from the spec. One object per part
  and per shared prefab (prefabs meshed once in their own frame, voxel = thinnest feature / 2.5 via
  `scene.thinnest`; collection instances). Meshes cached by content (`scene_cache/<hash>.npz`); scene parts
  on a lattice fixed in space so unrelated edits don't move it. No-op sync 1.5 s; editing the stove re-meshed
  only `metal` (1.6 s). Headless EEVEE works on the Radeon 890M (0.3 s/frame warm; shader compile 10-35 s for
  the cabin's ~180 expanded layers). `scene.look(show_layer=)` renders one layer's mask, per pixel.
- Round trip (`scene.pull`, run first in every `sync`): moved/turned/scaled instances come back as instance
  edits with the weather's offsets taken back out (spec + weather lands where the person put it); exposed
  paint numbers (a spec-level layer's opacity, colour, and its entries' ranges / noise scale / within / axis
  from-to: named `hp:<json path>` Value/RGB nodes) come back too. Each node stores `hp_set` (what the sync
  wrote) and only values moved from it count, so spec edits made elsewhere aren't clobbered.
- `paintnodes.py`: paint layers (materials expanded) compile to a node program per part. Nodes: noise (Blender
  noise remapped through a quantile curve to our fbm's distribution, `noise_quantiles.json`, so spec ranges
  keep their meaning), tiles (triplanar, stagger, per-tile id), cells (Voronoi F1/F2/colour), facing, axis,
  ramps (smoothstep), breakup, levels, invert, blends, per-channel mixing (linear colour), Principled out.
  Measured per vertex by our code: ao, sky, curvature, `near` distances, paths, weave, blurred entries, ".L"
  layers; packed three to a FLOAT_VECTOR attribute per part (`hp0`, `hp1`...): a GPU shader reads ~16 vertex
  attributes and more fails to compile (magenta). Inputs are measured at each object's own voxel, where its
  bake instance stands (`wpos`/`wnrm` attributes), cached in two keys: field inputs (geometry only) and
  measured masks (geometry + their definitions).
- Cycles bake of a part's node material onto the export low poly (`blender_scene.bake`, selected-to-active):
  logs basecolor 1024^2 in 4.4 s vs 758 s for our texel bake, and cleaner.
- `blender_scene.bake_inputs`: AO and sky by Cycles (AO shader node; sky = AO node with the normal forced up,
  distance 0.3 x model size), baked as emission to vertex colours, all objects in one bake per pass, prefabs on
  a stand-in at the bake instance. 1.08M verts: CPU 168 s, GPU(HIP) 175 s, ours ~190 s: no speed win (the iGPU
  isn't faster than 12 cores; AO needs tens of rays per point). AO correlates 0.88 with ours (Cycles reads more
  open: calibrate); sky only 0.64 rank-correlated: a different measurement (full upper hemisphere vs our 35 deg
  cone): sees sky through windows/eaves at an angle. Needs retuning of `sky` ranges, not just a curve.

**Plan, in order:**
1. DONE (2026-09-23): `scene.sync` takes ao/sky from Cycles (`scene.raytraced` -> `blender_scene.bake_inputs`).
   Agreed with the user: nothing baked may depend on where movable things stand ("the engine would light them"):
   the building (non-instance prims) shades itself; every prefab instance is its own object (`split(min_share=1)`)
   and shades only itself (AO pass with each prefab parked in its own far slot); a prop's sky is taken at its bake
   instance under the building (props do shelter each other's sky there: minor, noted). Three passes in one
   Blender run, each pass's targets merged into ONE mesh (Cycles bakes selected objects one by one with seconds of
   set-up each: 22 objects took 116-141 s, merged 18-32 s). Incremental: building prims are diffed against
   `scene_cache/rt_state.json`; only vertices a change can reach (`_near_change`: AO reach, or under it in a 45 deg
   cone) are re-baked, the rest of the object stays as occluder. Per-vertex values smoothed (2 rounds), AO through
   `input_quantiles.json`; sky raw, reach 2 x model size (interior walls read sheltered); walls top out near 0.5.
   Inputs are keyed per object and packed files named by content, so only changed objects are replaced in Blender.
   Moving a prop: 1.6 s sync; moving a prefab's bake instance re-bakes that prefab only (~13 s); cold ~110 s.
   `scene.clashes(spec, inst)` / `clear_of(name, inst)`: a moved instance cutting into something is logged by pull.
2. DONE (2026-09-23): grain per element. `surface.grain`: each point's element = the nearest additive primitive of
   its own part (its base SDF, cuts ignored), axis from `surface.element_axis` (bone axis; box/ellipsoid longest
   side; cylinder axis if taller than wide, else across); a box face wider than `surface.PANEL` (0.25 m) both
   ways is a panel, grain along its longer side (the counter's side isn't end grain). `grain_seed` (crc of the
   element name) offsets the pattern per element. Paint: `stretch.dir: "element"`, `facing: "element"` (|n.axis|);
   materials wood/planks/metal/rust take `dir: "element"` (planks keep board rows on world axes). Nodes: a
   `grain` FLOAT_VECTOR attribute (`scene.VECTOR_INPUTS`) + packed `grain_seed`. The cabin's wood layers use it
   (one logs layer, one timber layer). The grain vector's length is `surface.end_weight` (cross-section chunkiness:
   1 for logs/legs/beams, 0 for slabs and boards): facing "element" reads it, stretch normalises it, so table-top,
   seat and board edges aren't pale checked end grain. Next: end-grain rings need a radial coordinate.
   Materials rebuild when `blender_scene.py` changes too (its hash is in the program hash).
3. DONE (2026-09-23): per-part voxel for scene parts (`scene.part_voxel`): 2.5 voxels across each element's
   thinnest feature and 8 along its length, never coarser than the scene voxel nor finer than a quarter of it;
   the sync log names the element that set it. Cabin: metal 6.2 mm (pot/basin walls, capped), furniture 9.6,
   glass 13.8 (lantern), door/trim 16, roof 17.6 (424k verts), 1.57M verts total (1.1M before), cold sync
   ~3 min with the Cycles bake. Basin moved onto the counter top (it was sunk into it).
4. DONE (2026-09-23): the export's paint and AO maps are Cycles bakes from the scene (`asset.scene_maps` ->
   `blender_scene.bake_maps`): selected-to-active per part (only its own scene mesh selected, so a log never
   picks up the chinking), cage from how far the low poly strays from the exact surface (probed at triangle
   centres and edge midpoints), passes color / rms (roughness, metallic, specular) / ao (the scene's `ao_raw`
   vertex attribute: Cycles AO, uncalibrated, each asset's own) / height (painted relief: the materials sum
   height x mask into an `hp_height` node that also drives a Bump node, so EEVEE shows it). Texels whose ray
   misses (alpha 0) are filled from neighbours and counted in the log (~5% on the cabin). Normal and height
   stay ours (exact projection), tilted by the baked relief's slope in texture space. Cabin at 2048: 709 s
   (low poly ~180, maps ~350: 4 passes x ~23 parts, per-part set-up dominates; merging parts per pass where
   they can't see each other is the next speed-up), was 1129 (710 of it our per-texel painted height).
   Export and scene both split with `min_share=1`: every instance is a movable prefab (the table too).
5. DONE (2026-09-23): MCP tools `sync`, `pull`; `look` renders painted views from the scene (EEVEE, hide/only
   parts, cameras, flat, paint_layer = the scene's show_layer with coverage counted from the render: surface
   pixels by alpha, lit where r - b > 30); geometric views (raking, curvature, strokes, clip, close-ups) are clay
   per part. Retired: `store.painted`/`coverage` (the OBJ export carries part colours), `surface.ao`/`sky`
   (Points raises for them unless passed in), the export's per-texel paint/AO (`_ao_map`, apply_channels in bake).
   The scene now always bakes AO (painted or not: the export needs it). paint.py's mask code stays: the scene
   measures paths, near distances, blurred and mirrored masks with it.
Also: material rebuild on any paint change rebuilds every part (~55 s): hash per part. `scene.look` renders
EEVEE with screen-space ray tracing + fast GI (without it glossy things indoors reflect the open sky: jars had
glowing rims); a 4-camera look went ~15 s -> ~77 s. Push the scene into the user's running Blender over
the Blender MCP (port 9876; wasn't running today) so they see edits live. Hand-painted masks: DONE (2026-09-25).

**Found on the way (fixed and committed):** `surface.laplacian` used clipped `field_at`, exact only within a
primitive's blend reach, so near thin boards with small blends one stencil sample came back as 1.0 m: curvature
~1400/m on flat tops, cavity masks everywhere (also in the old look and exports). `assemble.select` and paint
`near` took only an array's first copy when given the array's name (copy 0 is named like the tag). Array
`vary` on a blob's size was overwritten. Paths can't address interior walls (a path point's ray comes from
outside the model and hits the outer wall first): use axis masks there, or add an "inside" address later.

**The four-room cabin test (2026-09-23/24):** `workspace/cabin4` (source `workspace/cabin4_src.py`: 765
primitives, 33 prefabs, 65 instances, 46 layers) took 29:49 from nothing to a painted scene, then 55 min to
export (31 of it Cycles map bakes). The wishlist from it was built the next day: early validation, `walls`,
instances `"on"`, `"between"` seams, `check` doorways, `look(instances=True)` facing arrows, `random` paint,
cameras off furniture, per-part live scene grids, the bake fix (export 55 -> 25 min). `workspace/cabin5`
(source `cabin5_src.py`) is cabin4 rebuilt with them. Exports also split a part too big for one atlas at the
asked density into slabs (`asset.split_big`: "roof~2", sharing seam vertices so the joint decimation keeps them
joined; cfg "split" stops lowpoly re-decimating one alone; bake_maps bakes each from its part's scene object via
"scene_key"), and a regroup re-unwraps without re-decimating (`<out>/lowpoly_decimated.npz`, keyed on what the
decimation depends on). cabin5 at 256/m: 40 atlases, 41 min, 250 MB; projection (per texel Newton) is most of it.

**The cabin (paused until the pipeline settles):** `workspace/cabin2`, a readable hand-written spec, source in
`workspace/cabin2_src.json` (story, log arrays with vary/flip/bow/lumpy/flat ends, chinking, targeted door and
window cuts, board gables trimmed by roof-plane cuts, shingle-course arrays, sagging beams, window/chair/stool/
table/cup/bowl/jar prefabs, stove, bed, counter, rug, firewood, ~35 paint layers). Clearance through the door
passes (0.91 m). Old script-built cabin kept in `workspace/cabin` for reference. Remaining cabin work after the
pipeline: wood grain per element, thin parts, restraint pass on weathering, export.

Parallel agents: give each its own git worktree (Agent `isolation: "worktree"`); `.claude/worktrees/` is
git-ignored. An agent working in the main tree sees code change under its feet.

Validate every exported GLB with the Khronos validator (gives 0 errors today). In the scratchpad:
`npm init -y && npm i gltf-validator`, then a 3-line `v.mjs`: `import v from 'gltf-validator'`,
`await v.validateBytes(new Uint8Array(fs.readFileSync(path)))`, print `.issues`. Blender's importer
ignores glTF occlusion, so the Cycles preview can't show AO: look at the ORM/AO PNGs themselves.

## Terrain (experimental; merged to main 2026-09-26)

Goal (the user's, 2026-09-25): terrain an LLM can author in designer language, not raise/lower/flatten brushes.
Three scales kept apart: the *implied world* (the brief's kind of terrain at real size), the *level footprint*
(compressed: game levels shrink distances), the *player* (exact: 1.8 m, trees, tracks). Design intent is
authoritative; realism fills in between and never moves what the designer placed. Five rounds of blind tests
(fresh agents given only `terrain_guide.md` and a prose brief) drove everything; ledger on the Overboard card
"Terrain: an LLM vocabulary..." (project hifipushie).

Modules (separate from the creature pipeline; heightfield, not SDF):
- `terrain.py`: spec normalisation (units, "30%" values), skeleton (peaks, cols, open/closed ridges with wander,
  rivers), base from three harmonic fields (t, floor, crest) plus automatic divides and ribs, basins (floor ramps by
  relative distance to the drain; walls are real mountainsides: width per stretch from the crest behind, average
  slope, tiered cliff bands, `character`), lone hills as domes, tilt, landforms (lake with ring/downhill/no dam,
  fan, moraine, terrace), lakes filled to their own level, report, map/mask-sheet/Cycles views, export.
- `terrain_world.py`: terrain kinds with real reference ranges, compression (c = frame / real width, heights by
  sqrt c; small kinds and small frames crop), heights chosen when left out, player-scale detail. Unknown kinds raise
  `Questions` for the designer (their answers define the kind, saved to `workspace/terrain/kinds.json`).
- `terrain_design.py`: zones, passes (a notch that ends where it daylights; descents are routes), walls, sites (pads
  with fall/overlooks), routes (least-cost on 32 headings, graded, carved; explain failures), cover masks and tree
  instances, sight lines (from across a site), realism check, intent.
- `terrain_forms.py`: canyons cut into a plateau through horizontal strata, mesas, river water, fords, rim addresses.
- `terrain_erode.py`: fastscapelib (dependency) stream power + diffusion after the design, protected places, heights
  restored at large scale, per-cell hardness (cliffs stand), thermal slumping. Blender has no terrain erosion.
- `blender_terrain.py`: Cycles preview (tree instances, water, ground beyond the frame).
- `terrain_guide.md`: the user-facing vocabulary (what blind agents read). Run: `examples/terrain_run.py <spec>
  [--no3d] [--export]` (exit 3 = questions for the designer).

Lessons worth keeping: a report must measure the *built* ground, never restate the plan (a pass "ramp" sat over a
65 m cliff; strata "ledges" were 40-52 deg); unbounded reaches bite (lake banks, pad banks and pass ramps each once
shaved or buried whole mountains); erosion scaled to the geology cuts trenches across a game level (cap it in
metres); whole walls as steep as "unclimbable" read as curtains (put the steepness in cliff bands); when a result
regresses, bisect by building one spec at each commit and diffing heights.

- `terrain_tools.py` + tools in `server.py`: `set_terrain` (spec or merge `patch`; `workspace/terrain/<name>/` with
  history), `check_terrain`, `look_terrain`, `export_terrain`, `terrain_history`; builds cached by spec content;
  questions come back as JSON (`Questions.data`). `guide(topic="terrain")`. `examples/terrain_tool.py` calls the same
  functions from a shell (for sessions whose MCP server predates the tools).

More lessons (plan C, 2026-09-25): measuring the built ground finds build bugs, not just report bugs. Canyon strata were
eroded to 51 deg mounds (now restored after erosion: `terrain_forms.settle`, which also fills hollows it would dam);
basin walls came out 9 deg steeper than asked (sized from the floor's high end: now per stretch from where the floor
meets them); the wall check passed any 2 m step (now the tallest steep run along each outward ray; walls are built
taller by ~0.6 cell of rise because the grid rounds lip and foot). Binary erosion protection makes pillars at its edge:
protect earthworks in proportion (`masks["earthworks"]`). Keeping hard cliff cells from creeping made pinnacles
(scattered hard cells stand): restore designed forms after erosion instead.

**Plan C (agreed 2026-09-25): done 2026-09-26.** C5, the blind round through the tools
(valley, farm, canyon, island; `workspace/c5_*/`), found layouts land and edits are easy, but at eye level none reads as
its brief (smooth caldera walls, dome peaks, no sea or cone, a featureless plateau), plus trust leaks since fixed (see the
Overboard card). Roads are judged as built with earthworks capped at 25 m, so several mountain roads now honestly FAIL:
they need breaks through cliff bands (plan A). Next, in the order the round asked: sea and coast, volcano cone, route
breaks through cliffs, peak forms and wall structure, surroundings beyond the frame.
1. DONE: trust leaks and bugs from round 5 (every report number measured; see lessons above; peaks report how far their
   top stands above the skyline beside/behind them, `min_prominence`).
2. DONE: export (Unity `.raw` + size/position, tree layers out of the splats, masks always, rivers' water, fords, site
   planes in meta).
3. DONE: questions (mixtures "crater + coast", a shape question, what can't be built said first; answers in the
   designer's words matched to options).
4. DONE: MCP tools.
Then maybe A (more forms per kind: sea/coast, cones, lava, canyon breaks) and B (realism: SDF cliffs).

## Testing without restarting the MCP
Call the tool functions directly: `uv run python -c "from hifipushie import server; ..."`;
`look` returns `[Image, str]` and `Image.data` is PNG bytes you can write to a file.

OpenBLAS is capped at 4 threads in `__init__.py`: uncapped, 100x100 solves take ~300 ms on a 24-core box.

## How we work
Experimental: build a small piece, test it on a real model (troll, goblin, fox), judge honestly from renders,
pivot when it isn't paying off, and say what tooling would help. Send renders to the user as files
(`look(save=...)` / SendUserFile): tool images aren't visible to them. Commit to `main` and push when a piece
works (the repo is public: github.com/joeleaver/hifipushie; `workspace/` is git-ignored, shareable models go
in `examples/`). The MCP server running in a session has the code from when it started: after changing the
server, test by calling `server.*` functions directly (see below) or restart the session.

## Status and roadmap
Done: skeleton + blobs, kits (face, hand), fit, plan workflow (set_plan/check), strokes (summed dabs; repeat,
scatter; overlay/raking/curvature views), parts (separate meshes, clothing shells), surface-seated joints,
paint (layers with path/near/facing/axis/cavity/noise/ao/thickness/cells/tiles/weave/sky generators, mask
stacks, breakup, painted height, coverage and per-layer mask feedback, coloured OBJ), a material library
(cloth, leather, wood, planks, brick, stone, metal, rust, moss), repetition (prefabs/instances, arrays with
vary/flip/jitter, tags), hard-surface solids (box, cylinder, hollow, targeted cuts, flat bone ends, bow, lumpy,
chips), the imperfection stage (story, check's realism audit, weather ops), interior viewing (look hide/only
parts, clip, perspective cameras; clearance tool), game-ready export (export_asset: joint decimation with
per-part weights, packed atlases with texel density/focus, texel-exact PBR maps, GLB; prefab instancing, density-driven atlases), the playbook
(`guide.md` via the `guide` tool, `.claude/skills/hifipushie`), and performance passes.
`examples/troll.json` is the reference character.

Older notes on paint: bake time at 2048 on the troll ~290 s before the field_at chunking fix (AO was most of it);
painted height in `look` is vertex-normal tilt only; thickness is ready for a subsurface map but nothing exports
it; AO is broad (grime recipes use ao [0.55, 0.3] + tight cavity).

Next, roughly in priority order:
1. The Blender scene pipeline, then the cabin: see "Next session" above.
   Remaining cabin-test friction not yet addressed: painting huge meshes for look is slow (hide/clip/camera
   looks paint only what's shown; per-layer mask caching would help full looks); log end grain can't show
   rings (world noise has no per-log axis: an "along the element" pattern option); saddle notches are manual
   cuts; glass has no transparency (a part "alpha"/transmission in the GLB material); per-layer grain
   direction needs a layer per orientation (an `along: element` option for stretch/dir).
   Asset follow-ups: rig (armature from the skeleton + skin weights), LODs, FBX.
2. Part tools: check that parts don't cut into each other (looking at one part alone: `look(only_parts=)`).
3. Topology for characters (discussed 2026-09-23, for when we return to organic shapes): decimation stays for
   environments/props (adaptive, keeps hard edges, quads buy nothing on static meshes; QuadriFlow would spend
   uniform quads on flat walls and chokes on many-piece parts: at most a per-part option for static organic
   pieces someone will sculpt further). Deforming meshes need loops (around limbs, extra at joints, rings at
   eyes/mouth), which decimation can't give. Plan: skeleton-driven quads (Blender's Skin modifier over our joint
   graph + radii, joint rings added, projected onto the exact field, relaxed; face kit templates for eye/mouth
   rings); skin weights nearly free (each ring belongs to a bone). First a spike on the troll: skin-modifier topology
   vs QuadriFlow vs decimation, with a test bend at elbow/knee.
4. Feet/toes: DONE (2026-09-25): the foot kit (`kits._foot`: body, ball, heel, toes as `_digit`s).
5. Close-ups at a new focus rebuild from scratch (~5 s): the grid moves. Could snap close-up boxes to the
   full build's block grid so PartGrid can reuse blocks.
6. Face kit features read as stuck-on balls (cheeks, nose); strokes did better for brows/cheeks. Consider
   softer kit blends or stroke-based features.
7. Older ideas: (blade primitive: done 2026-09-25, `sdf.sd_blade`); adaptive resolution near small features; skeleton →
   Blender armature for posing; soft priors in fit.
