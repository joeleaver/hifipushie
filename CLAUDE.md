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
  -> full notes: docs/notes/anatomy.md
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
  -> full notes: docs/notes/render.md
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
  -> full notes: docs/notes/paint.md
- Hand-painted masks (`paint` generator `"painted": id | "new"`): a point cloud (world pos, normal, value, the
  painting object's voxel) content-addressed in `workspace/_painted/<id>.npz`, evaluated per point by
  `paint.painted_values` (8 nearest within 2 spacings, facing-gated so thin boards don't print through).
  `scene._paint_inputs` writes each object of the layer's parts an `hp_paint:<layer>` array; `blender_scene._inputs`
  makes it a POINT FLOAT_COLOR attribute (Vertex Paint, white = 1) and stores its checksum on the mesh
  (`hp_sum:<layer>`); `blender_scene._pull_painted` sends every object's points for any layer whose checksum
  moved, `scene._pull_painted` saves the cloud and writes the id (`paint.set_painted`). Prefab paint sits where
  the bake instance stands (world coords): moving that instance leaves the paint behind.
- Images as paint (2026-10-01, `images.py`, paint generator `image`; the user: "consume images on our models (framed
  painting, text on a page...)"): a planar decal (centre `at` = joint/xyz or a blob, seated on its face named by
  `dir`; right = up x dir so it reads from the front; depth window + facing ramp against print-through), image from
  -> full notes: docs/notes/images.md
- `materials.py`: `{"material": ...}` paint layers expand (`paint.layers`) into sub-layers `<name>:<sub>` built
  only from ordinary generators (plus `tiles`/`weave`, 2D patterns laid triplanar by `paint._planar`); the
  layer's own masks confine every sub-layer as a trailing nested multiply; coverage reports the first
  sub-layer under the material's name. Tune materials on `workspace/swatches` (panel + ball per material).
- `asset.py` + `blender_asset.py`: game-ready export. `split` decides what is meshed: the model's parts minus the
  instances of shared prefabs (2+ instances, `prefabs.<p>.export` not "unique"), plus each shared prefab's parts
  ("<prefab>/<part>") from its bake instance (first unmirrored), by `Prim.instance` (set from the element's
  -> full notes: docs/notes/asset.md
- `faceshapes.py` (2026-10-01, for oxidegen lipsync; design note `spikes/face_shapes/README.md`): export_asset(face_shapes=
  True | [names]) gives the parts that move with the face ARKit-named morph targets (glTF targets, sparse POSITION +
  NORMAL deltas, mesh.extras.targetNames; FBX shape keys). A shape is a displacement of space from the face kit's
  -> full notes: docs/notes/faceshapes.md
- `rig.py`: the export rig, a separate step over the modelling skeleton (the user, 2026-09-25: humanoids must be
  Mixamo-compatible and Unity/Unreal-retargetable, clean bone chains for non-humanoids too; spec bones stay for
  modelling). `humanoid` fits Mixamo's skeleton (mixamorig:Hips, Spine/1/2, Neck, Head, clavicles, arms, hand-kit
  -> full notes: docs/notes/rig.md
- `retopo.py`: character topology by template wrap (from `spikes/topology/wrap.py`): the CC0 template
  (`templates/male_stylized*`) carried onto a humanoid by its skeleton (`_skeleton_warp`), face landmarks by RBF, then
  patches cut at closed template loops and generated from the model *before* the fit and held fixed (the template flows
  -> full notes: docs/notes/retopo.md
- `base.py`: spec `base` = a template body as the start of a character (`{"template": "male_stylized", "eyes": part,
  "girth", "soften", "push", "head"}`): the template's joints are injected (spec joints win), the body warped onto them
  with radii kept (`_skeleton_warp(girth=)`; FK rotations, hands from a palm fit, see below), Catmull-Clark'd, and becomes one primitive (kind "base", first in the
  -> full notes: docs/notes/base.md
- `hair.py` + `blender_hair.py` (2026-09-29; replaced the SDF groom on branch hair-sdf-wip: a mop with corduroy grooves,
  13 min builds): hair as curve locks in the Blender scene. Each lock is a legacy Bezier curve object (collection "hair")
  with one shared Geometry Nodes group `hp_lock`: resample, flat side facing away from the head centre + Flip + Twist and
  -> full notes: docs/notes/hair.md
- Cloth (2026-10-01, `cloth.py` + `blender_cloth.py`, `pattern.py`, `tailor.py`, `freesewing.py`; the user: garments as
  real construction, drafted made-to-measure, sewn and simulated, never a finished garment warped onto another body).
  `spec["cloth"] = {name: garment}`: `pattern.from` a design in `cloth_designs.json` (FreeSewing parts by name, wraps,
  -> full notes: docs/notes/cloth.md
- Clothing workflow (2026-10-03/05, "clothflow" agent; the user: "what artists actually do: building tools so LLMs can
  operate like real artists", and "all these learnings need to be codified"; renders `workspace/cloth_renders/wf_*`).
  The rule: construction before solver. A day of solver tuning chased what were pattern faults (cap ease 44%, a
  -> full notes: docs/notes/cloth.md
- Skin (2026-10-05, "skin" agent; the user: humans read "flat, plastic-like"; textures "for humans of all sexes, ages,
  and genders", incl. cosmetics, scars, tattoos, wrinkles, freckles; renders `workspace/skin_renders/sk_*`, references
  `workspace/skin_refs/` (24 CC photos, README + refs.json with skin-only boxes; never in the repo)). Guide:
  -> full notes: docs/notes/skin.md
- Principle-based pattern drafting (2026-10-05, "clothflow" agent; the user: ready-made drafts are references, "we
  also need to distill the _principles_ so we can design jackets that don't exist yet, or any other arbitrary
  clothing"; sheets `workspace/cloth_renders/pd_*`). A new garment = a block + operations + details, as pattern makers
  -> full notes: docs/notes/cloth.md
- Garments (2026-10-06, "garments" agent, branch `garments`: both cloth tracks merged; renders `cloth_renders/ga_*`;
  scratch DURABLE in /mnt/data/hifipushie/garments/: env.sh, run.sh <script> (worktree code on the main workspace),
  tests.sh, gates.py (stages 1-3 on every wf_ / pd_ / zz_ / ly_ / ga_ model), st.py (stages with the garment patched in
  -> full notes: docs/notes/cloth.md
- Suit (2026-10-07, "suit" agent, branch `worktree-agent-a79355cc3032d8bee`; renders `cloth_renders/su_*`; target =
  Garrett's concept `workspace/garrett_v20/concept_v8_front_apose.png`: charcoal two-button notched jacket worn OPEN,
  pale shirt with the top button open, flat-front trousers with a crease; he is seated in the game. Scratch DURABLE in
  -> full notes: docs/notes/cloth.md
- Suit 2 (2026-10-07, "suit2" agent, branch `worktree-agent-a42af29b3a3f84fa9`, continues "suit"; renders
  `cloth_renders/su_2*`; scratch DURABLE in /mnt/data/hifipushie/suit2/ (the suit agent's scripts with W = this
  worktree, + run_main.sh <script> (MAIN's src on PYTHONPATH: before / after numbers), plb.py (the START as
  -> full notes: docs/notes/cloth.md
- Suit 3 (trousers, shirt) (2026-10-07, "trousers" agent, branch `worktree-agent-a5aa4e100572bcb0c`; scratch DURABLE
  in /mnt/data/hifipushie/trousers/: env.sh, run.sh <script>, tests.sh, q.sh <queue file> + run.py (one sim: report,
  renders incl. trims, `_waist`, `_waist_tex`, `_hem` close-ups for trousers), plr.sh <model> <garment> <tag> (the
  -> full notes: docs/notes/cloth.md
- Suit 3 (2026-10-07, "collar" agent, branch `worktree-agent-a5c847e94d5c52d32`; renders `cloth_renders/su_30..32_*`;
  scratch DURABLE in /mnt/data/hifipushie/collar/: env.sh, run.sh, q.sh + run.py (renders now draw seams WELDED),
  p.sh <tag> [-o] (blazer alone, collar made, place only; `-o` = the open start; collar numbers, CB column, notched-lay
  -> full notes: docs/notes/cloth.md
- Suit 4 (layers) (2026-10-07, "layers" agent, branch `worktree-agent-a237f0b282ae815f7`;
  renders `cloth_renders/su_41..45_*`; scratch DURABLE in /mnt/data/hifipushie/layers/: the collar
  agent's scripts retargeted (env.sh, run.sh, q.sh + run.py, plb.py, cu.py ...) + lay1.py <m> <g> <tag> [k=json] (START:
  -> full notes: docs/notes/cloth.md
- Seams (2026-10-07, "seams" agent, branch `worktree-agent-ae98ecda411a37796`; the user on the suits: "seams look huge
  and structural"; renders `cloth_renders/sm_01..08` (before = main 2aea2ac / after, the SAME cached sims: su_31
  blazer, su_05 shirt; sm_05 = raking light across the blazer's side panel seam); scratch DURABLE in
  -> full notes: docs/notes/cloth.md
- Suit 5 (2026-10-08, "suit5" agent, branch `worktree-agent-a7a27cfe57b8650a5`; renders `cloth_renders/su_5*`; scratch
  DURABLE in /mnt/data/hifipushie/suit5/: the layers agent's scripts retargeted + pl0.py <model> <garment> <tag>
  (build place_only ONCE, pickle Bp / mesh / placing body to out/<tag>.pkl) and pl1.py <pkl tag> <out tag> (place()
  -> full notes: docs/notes/cloth.md
- Suit 6 (2026-10-08, "suit6" agent, branch `worktree-agent-a567f36d476596530`; renders `cloth_renders/su_7*`; scratch
  DURABLE in /mnt/data/hifipushie/suit6/: suit5's scripts retargeted + lay1.py (the BUILD's start; PKL=<tag> also
  pickles it WITH the worn body, so pl1.py <pkl> <out> re-places in ~1 min with the current code; NORELAX=1, ENVR=<rounds>,
  -> full notes: docs/notes/cloth.md
- Suit 7 (2026-10-08, "suit7" agent, branch `worktree-agent-af71a3f0c0a4e3d8a`, continues suit6; renders
  `cloth_renders/su_8*`, `tr_24*`, `om_0*`, checklist sheets `cr_81*`; scratch DURABLE in /mnt/data/hifipushie/suit7/:
  suit6's scripts retargeted + run.sh (EVERY script through /mnt/data/hifipushie/bin/capped, peak RSS printed,
  -> full notes: docs/notes/cloth.md
- Suit 4 (trousers, shirt) (2026-10-07, "trousers2" agent, branch `worktree-agent-a06095d1485fd23a1`; scratch DURABLE in
  /mnt/data/hifipushie/trousers2/: the trousers agent's scripts with W = this worktree, + sdiag.py <tag> [1.05] (start
  stretch: largest principal stretch by piece and height band, p90 per band, the waistband's seam pairs), tdiag.py /
  -> full notes: docs/notes/cloth.md
- Placket (2026-10-08, "placket" agent, branch `worktree-agent-ab49e1b1d94e336bb`; the user: "We're really not getting
  the shirt placket right"; renders `cloth_renders/pk_*`, sheet `pk_05_placket_before_after.png` (before | after,
  textured + clay, beside cloth_refs/shirt_collar_worn.jpg); refs `cloth_refs/placket_*` (button macro, a placket with
  -> full notes: docs/notes/cloth.md
- Garments from reference art (2026-10-08, "clothlist" agent, branch `worktree-agent-a32bca676fcdb7416`; the user: "a
  similar list for clothing features [as the face's likeness list]"; guide(topic="cloth_reference") =
  `cloth_reference_guide.md`: how tech designers (POM tables, HPS-based), tailors (proportion tells), costume
  -> full notes: docs/notes/cloth.md
- `realism.py`: `spec["story"]` (validated; stripped by `spec.geometry`, like paint; its `directions` can be
  named in paint `facing`) and `audit`, the perfection warnings `check` always appends. `assemble` applies
  `spec["weather"]` ops: instances as rigid bodies first, then elements by tag. `chips`/`lumpy` live in the csg
  wrapper (`sdf.sd_csg`; chips weighted to edges by the element's own Laplacian). `surface.sky` is the upward
  openness input (rain, sun, shelter).
- `assemble.py`: prefabs/instances and element `array`s expand into plain joints/bones/blobs before kits
  (`kits.expand` calls `assemble.expand`, content-cached), so everything downstream sees ordinary elements.
  `select` resolves names/tags (instances, arrays and `tags` lists are tags). `spec._csg` wraps a primitive as
  -> full notes: docs/notes/assemble.md
- Joints can be `{"on": address, "lift", "shift"}`: `strokes.seat_joints` seats them on the model without
  them (`strokes.without_seated`, also what kits and strokes seat on, to avoid cycles).
- Style sheets (`stylesheet.py`, `styles/*.json`, guide 5c; 2026-09-29, the golfer): the user's verdict was "stylization
  is an artistic decision, not just make the eyes bigger", so a style is a bundle of decisions. `spec.style.sheet` names
  a sheet whose partial spec (base.style incl. `simplify`/`simplify_keep`, head fit/pose defaults, part `subsurface`,
  -> full notes: docs/notes/stylesheet.md
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
- `server.py`: MCP tools (mcp 2.x `MCPServer`, not v1 FastMCP). Every tool is wrapped (`_tool_with_errors`) so its exception
  text reaches the caller (the SDK sends a bare "Error executing tool x" otherwise). `edit_model` ops take any
  top-level key as `kind`, plus `set_key`; a failing batch names the op (`store.edit` bisects). Save replies carry
  WARNING lines (`paint.side_warnings`). check/compare/fit take `only_parts`/`hide_parts` (or plan `"parts"`).
  Plans for props: `plan.dimensions` (measured on named elements' own surfaces, `plan.extents`) and shapes with
  `"part"` (that part's silhouette, gaps closed at `plan.close`). look cameras report what blocks the eye -> target
  line and the nearest clear eye (`measure.sight`). export_asset: `parts.<p>.min_triangles` (per-copy floor) and a
  per-part `quality` report (`asset.mesh_quality`: error to the field, folds, non-manifold/open edges, slivers).
- `assets.py` + `assets.json`: third-party assets (GNM, MakeHuman, the HBM bundle) by URL + sha256 in one directory
  ($HIFIPUSHIE_ASSETS, else `<HOME>/_templates`); `uv run hifipushie-assets verify|fetch [packs]`. Code reaches them
  through `assets.pack/path`, which say how to fetch a missing pack. Never keep pipeline assets in /tmp.
- `resources.py` (2026-09-29, after two OOM crashes of the user's desktop: a terrain export's 16 fork workers x ~2 GB
  plus other agents' jobs): heavy jobs take the machine-wide slot `resources.heavy` (a file lock in $XDG_RUNTIME_DIR;
  $HIFIPUSHIE_HEAVY_SLOTS, default 1) and wait for it; pools are sized by free memory (`resources.workers(per_gb)`:
  -> full notes: docs/notes/resources.md
- `tests/test_tooling.py`: reproductions of the tooling cards' incidents (`uv run python tests/test_tooling.py`).

## Notes per thread (docs/notes/)
Every thread's history (findings, numbers, dead ends, handovers) lives in `docs/notes/<thread>.md`: rig, base, hair,
cloth, skin, onemesh, likeness, refstudy, garrett_head, measuremodels, terrain, streambeds, vegetation, clutter,
images, asset, faceshapes, resources, topology, blender_scene, ... Read the one(s) for your task before starting.
RULE: write new findings and handovers THERE, not here. This file is loaded into every agent on every turn: it was
775 KB (~190k tokens) on 2026-10-09 and burned the usage limits. Keep CLAUDE.md under ~40 KB.

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
Full notes: docs/notes/topology.md

## The Blender scene becomes the pipeline (2026-09-23, done)
Full notes: docs/notes/blender_scene.md

## Terrain (experimental; merged to main 2026-09-26)
Full notes: docs/notes/terrain.md

## Streambeds (2026-10-08, "streambeds" agent, branch `worktree-agent-aaf90ea1699c43e77`)
Full notes: docs/notes/streambeds.md

## Vegetation (2026-10-05, branch `vegetation`; stages 1-2 of 6: trees, foliage, bark)
Full notes: docs/notes/vegetation.md

## Clutter kit (2026-10-08/09, "clutterkit" agent, branch `worktree-agent-af12ac948388331b2`; sheets `workspace/veg_renders/ck_*`)
Full notes: docs/notes/clutter.md

## One human mesh (2026-10-06, "onemesh" agent, branch worktree-agent-aac6bb85823bc8809; renders `workspace/human_renders/om_*`)
Full notes: docs/notes/onemesh.md

## Likeness checklist (2026-10-08, "likeness" agent, branch worktree-agent-a2afc4d19c40fa784; needs onemesh2's branch on main first: it is merged in here)
Full notes: docs/notes/likeness.md

## Reference modelling study (2026-10-08, "refstudy" agent, branch `worktree-agent-a0066266ffbf99948`)
Full notes: docs/notes/refstudy.md

## Reference modelling study 2 (2026-10-08/09, "refstudy2" agent, branch `worktree-agent-ae4b2050b31cc1395`)
Full notes: docs/notes/refstudy.md

## Garrett's head, dressed (2026-10-09, "garrett3" agent, branch `worktree-agent-a134642c7a6403455`)
Full notes: docs/notes/garrett_head.md

## Measurement models (2026-10-09, "measuremodels" agent, branch `measuremodels`)
Full notes: docs/notes/measuremodels.md

## Made pieces constructed after the drape (2026-10-09, "collarbuild" agent, branch `worktree-agent-a5a0bbd568c7f3c68`; a SPIKE)

The user after ten collar rounds: "Do we need a different tack? Less simulation, more hand-editing?"; the coordinator:
simulate the garment's body, BUILD the collar onto the finished neckline; then the user: "that same principle probably
applies to other parts of clothing". suit8's branch is merged in here. Sheet `workspace/cloth_renders/
cb_01_constructed_vs_sim.png` (concept | simulated om_21 | constructed on the same sim; front, three-quarter, side,
back). Scratch DURABLE in /mnt/data/hifipushie/collarbuild/: run.sh <script> (this worktree's code, capped), run8.sh
(the same with the suit8 worktree's SOURCE first on the path: its cache keys; this worktree's own code found neither
garment cached), dump.py su_om_garrett jacket=<job out.npz> (cached shirt + a job's jacket -> out/su_om_garrett.pkl:
arrays, sew pairs, folds, the shirt as worn; 24 min at load 80, almost all of it cloth.build), jk.py <tag>
[shirt.k=v] [jacket.k=v] [nojacket] [hl] [zoom] [nolapel] [sheet] (both collars + pressed lapels built on the pickle,
tells of both, strips; 17 s), sc.py (shirt collar alone on any saved shirt npz), dbg.py / dbg2.py (a part's rows at
stations; the fall against the shirt's cloth), t.py (the tests), patch*.py / append.py (edits as scripts).
NO SIM WAS RUN.
- `cloth_made.py`, one interface for a made piece: its SEAM as it ended (`seam_chain`: the sewn pairs of the made
  piece against the rest, ordered by the made piece's pattern; or seam vertices lying together), a PATTERN as columns
  leaving that edge (angle + row lengths in metres = the uv), FOLDS (a roll of radius r about the edge), and what it
  lies ON (`Under`: layers wound outward, sheets or closed, each with a clearance). One operation, `march`: every
  column walks its pattern length from the seam, straight where free, along a surface where it touches, never nearer
  than its clearance. `shirt_collar` (stand + fall, two grids), `notched_collar` (one sheet: stand running out to
  nothing where the roll line meets the seam, the ends leaving the gorge seam flat, away from the turned lapel they
  are sewn to: `into_cloth`), `press_flap` (a flap of a DRAPED piece laid as its mirror image across the fold line
  on the piece's own triangles: no topology change, vertex ids kept: the lapels), `solid`, `stretch`.
  The seam's own vertices are vertices of the built piece's first row (join 0.000 mm on both garments).
- Numbers on su_om_garrett (om_21's sim | constructed): collar_show 14.8 | 13.9 mm (the jacket stand's height is SET
  from the shirt collar's top less `show`); collar_hug 15.3 | 14.6; lapel gap 6.8 / 6.3 | 3.0 / 3.0 (pressed: by
  construction); crossings jacket collar x jacket 49 | 2, jacket collar x shirt 0 | 6, shirt collar x shirt 2 | 5,
  x body 0 | 0; pattern stretch p50 0.97-0.99, p95 1.19 (shirt fall) / 1.37 (jacket collar), max 2.7-3.6 at the
  ends. 17 s for everything. (Jacket cloth x the worn shirt reads 402-444 either way: cloth_layers.tucked's shirt
  against a 2 cm jacket, not this work.)
- BLUNT READ. Back and sides: yes. The shirt collar is a crisp stand with a pressed fall where the sim had a crumpled
  ruff; the jacket collar lies flat round the back; the lapels lie flat on the foreparts. FRONT: no. The shirt's
  points are thin spikes hanging at the throat (the simulated fronts under them stand 30-35 mm off the chest,
  rolled back and crumpled, and the leaf has nothing sound to lie on); the jacket collar's ENDS are stiff straps
  along the gorge standing proud at the shoulder, not one surface with the lapel, and no readable notch; shards of
  the worn shirt still come through the left lapel. It does not yet read as the concept's collar from the front.
- What went wrong on the way (each cost a round): a stand that "hugs the neck" lay down on the shoulder (a stand
  RISES from the seam along the neck's axis, tipped in at most ~12 deg; where the seam ended 17 mm off the neck the
  fall of a hugging stand came down INSIDE the neckline); a fold whose angle faded with the stand's height made
  wings (the fold is always a full turn, the stand's HEIGHT runs out); a slab's thickness lies under its sheet, so
  the clearance is lay + thickness; frames from the seam's own tangent carry its kinks (normals out from the neck's
  axis instead); the pressed stand-in of an under garment is not coincident with its own collar at the back (use
  the finished result).
- The lesson for the principle: construction is only as good as what it stands on. Where the drape under the made
  piece is sound (back neck, shoulders, foreparts) it is immediately better than the sim and takes seconds; where
  the drape itself is the sim's mess (an open shirt's rolled-back fronts) it inherits the mess. So the made piece's
  NEIGHBOURHOOD must be simulated without the made piece's errors too: sim with a soft stand-in (or the seam only),
  not with a carried rigid collar whose placement error the neckline keeps.
- Not built: wiring (a `construct` key per made piece in cloth.build after the clean-up, results in res["made"] like
  res["buttons"], through look / scene / export as closures.buttons_mesh and cloth_trims.meshes go), the collar's
  ends as a continuation of the pressed lapel's own plane (today they march from the gorge seam on their own), the
  notch's drafted outline (ends are a plain width), the stand's button extension, detail maps for built pieces
  (they have pattern uv, no atlas), rig weights (from the body by surface like other cloth; the under collar worn
  rule), a Blender hand edit (offsets per built vertex on (piece, row, station): stable ids while the pattern
  parameters hold). Tests `tests/test_cloth_made.py` (a synthetic neck: stand, fall and point lengths honoured,
  seam welded, no crossings, clearances; a pressed flap is the mirror image).
- Round 2 ("collarbuild2", same day; sheet `workspace/cloth_renders/cb_02_notched_collar.png` = concept | simulated |
  round 1 | round 2, front / three-quarter / side / back + the notch close; NO SIM RUN; scratch adds jk2.py <tag> [s2]
  [conshirt] [noends] [nopat] [notuck] [hl] [drawin=<mm>] [jacket.k=v] [end.k=v] [views=wide,notch,sh] (12-30 s on
  out/su_om_garrett.pkl; `s2` = shirt2's s2_12 shirt, same mesh, swapped in by V), sheet2.py <jk tag> <jk2 tag>,
  pat.py (the collar and fronts in the pattern with seam pairs and roll rows -> out/pat.png: LOOK AT IT FIRST),
  in2.py, dbg3.py, ins_tests.py).
  - The jacket collar is built from its DRAFT: `collar_pattern` reads the sewn edge, the outer edge between the end
    corners and the roll line off the collar's own pattern mesh; `notched_collar(pattern=)` runs its columns sewn edge
    -> outer edge (first / last column = the drafted end edges), stand height per station = the draft's roll line,
    uv = the pattern's. `ends=`: past where the lapel's roll line meets the neck seam each collar point is carried
    across the gorge seam into the FRONT's pattern (`sewn_image`: same arc along the paired edges, same distance,
    other side), mirrored across ONE fold line (the lapel's roll line run on by the collar's own roll line), and laid
    on the forepart as a board (`on_pattern`: a Gaussian-weighted plane fit in the pattern, 2 cm; runs on past the
    piece's edge), carried onto the pressed seam vertices, blended with the band lay over 3 cm before / 1.5 cm after
    the meeting point, evened along the seam, drawn down onto what is under it (`end_hug` 6 mm).
  - Shards through the lapel: the shirt had been tucked under the UNPRESSED lapels (cloth.worn_together) and round 1
    pushed only the flap's vertices off it. Now the order is press -> build the collar -> `cloth_layers.tucked` again
    under the pressed jacket + collar slab (a body shim with V + normals() is all tucked needs). Lapel flaps x shirt
    crossings: simulated 59, round 1 110, round 2 25.
  - Numbers (simulated | round 1 | round 2): collar_show 14.8 | 13.9 | 15.9; collar_hug 15.3 | 14.6 | 14.5; lapel gap
    6.8 / 6.3 | 3 / 3 | 3 / 3; collar x jacket crossings 49 | 2 | 0, x shirt 0 | 6 | 0; collar pattern stretch p95
    - | 1.37 | 1.16 (max 2.66 -> 1.84); notch angle 104 / 108 deg, collar end edge 50 / 48 mm, lapel notch edge
    37 mm, end's face 8-9 deg off the pressed lapel's, end 3.5 mm (max 7) off the forepart.
  - BLUNT READ: collar and lapel now read as one turned surface with a notch, nothing stands at the shoulder, the
    back is clean, with shirt2's shirt under it nothing comes through. A tailor would NOT accept the notch, and the
    reason is the DRAFT, which the construction now shows faithfully: the front's neck edge is one straight diagonal
    hps -> cfNeck -> lapel point, only 33 deg off the roll line (gorge_drop 0.12 made it steeper), so turned over the
    gorge runs nearly straight DOWN the chest (19 deg off vertical), the lapel's top is a thin wedge and the collar's
    end is a 48 mm strap lying beside it down the chest, the notch opening sideways. The concept's gorge runs ~55-60
    deg off vertical: the gorge must be CUT at 65-75 deg to the roll line from a point ON the roll line (not the
    whole neckline tilted), collar end ~35 mm. That is a redraft + re-sim of the jacket (the front's outline changes).
  - collar_hug: the seam lies 20 mm (CB) / 15.8 mm (back median) off the shirt collar. `drawin=5` (the back seam ring
    moved to 5 mm off it after the drape, eased 8 cm into the cloth): hug 8.5, but the back ring goes 272 -> 248 mm
    (9% compression along the seam, edges 0.84-1.22): the draped neckline is 24 mm too LONG to lie there, so a
    post-drape draw-in is a HACK; the fix is the back neck's drafted length / a sim without the carried collar.
    And the metric counts the fall's vertices: a perfect collar reads ~8, not 0-6.
  - Not done: the cuff as a second case; the `ends` path of notched_collar has no synthetic end-to-end test (its
    steps do: sewn_image, on_pattern, collar_pattern, the mirrored lay on a flat front, the draft-following collar);
    wiring into cloth.build. A faint transverse lip remains across the collar where band and end lays blend
    (`blend_smooth` 5 / `blend_reach` 2; 8 / 3 made 7 crossings with the jacket).
  - RECOMMENDATION given to main: wire lapel PRESSING + the re-tuck now (cheap, always better); wire the constructed
    jacket collar behind a key once the gorge is redrafted; the sim should stop carrying the jacket collar as a rigid
    made piece (sew a soft, uninterfaced stand-in strip or leave the neck seam free) so the neckline settles where
    its length puts it.

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
