# hifipushie notes: blender_scene

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

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
  layers (a measured attribute is named by a hash of its definition: named by the layer alone, an edited ".L" mask
  kept its stale measurement); packed three to a FLOAT_VECTOR attribute per part (`hp0`, `hp1`...): a GPU shader reads ~16 vertex
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

