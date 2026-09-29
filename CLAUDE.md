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
  Digit fans (the kits' `<kit>_f<n>_<k>` / `_th_` chains): knuckles on the back (the palm side is where the digits
  curl), webs between neighbours, a pad before the roots, a thenar pad. `kits._digit` now makes one bone per phalanx
  (hard min): three short segments per phalanx left a ring at each boundary, and a join blend swelled there instead.
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
  `skin_parts` (export and the rig tool): `parts.<p>.rig_bone` binds a part rigidly (a bag to Hips, a disc to
  RightHand: split between bones they tore); with a base, rig flesh is a cone per rig segment sized from the base
  body and every part blends the weights of the base quads' 4 nearest vertices (the export's skin under clothes is
  dropped, so clothes can't copy from it). A base's fingers (fingerN_k / thumb_k) fill the Mixamo hand.
  Export scene parts finer than the model voxel (`scene.part_voxel`) get their own grid (a 6 mm collar shredded at 7.8).
  `spec.geometry` strips `rig`.
- `retopo.py`: character topology by template wrap (from `spikes/topology/wrap.py`): the CC0 template
  (`templates/male_stylized*`) carried onto a humanoid by its skeleton (`_skeleton_warp`), face landmarks by RBF, then
  patches cut at closed template loops and generated from the model *before* the fit and held fixed (the template flows
  into them): digits as tubes on the hand kit's chains, ear bones as flat tubes with equal-arc rings (a blade ear keeps
  its rim), eyes as rings over the lids (rays from the lids' centre: star-shaped near the eye; the cut loop follows the
  lid edge's shape + `eye_phi`: at a fixed angle it crossed a wide almond opening). Ear/eye loops are carried to their
  targets first (`_carry`, and as RBF landmarks: left to the skeleton they sat behind the jaw / on the cheek). Mouth and
  nostril cavities (template verts whose normal ray hits the template again, in the face json) follow instead of
  projecting: the old "inside the model near the head" rule held the goblin's cheeks 15-25 mm inside. goblin_anat 3.11
  -> 0.85 mm mean, 10/10 rings; troll_anat 1.24 mm. Judge with `spikes/topology/wrap_eval.py` (error by region incl.
  ears, rings at `anatomy.loop_planes`, turned faces; `closeup` draws turned faces or, `ERR=3`, the model surface the
  mesh misses: the only view that caught the cheek bug). Export: `parts.body.topology = "wrap"` (asset.topology_parts:
  the wrap kept through the decimation, skin buried under other parts dropped). Base bodies (2026-09-29): digits are
  tubes on the base's own finger joints (`c["model"]` = the template's names), each base loop carried to its first
  ring, ring angles from the template's clean digit, `_stitch` winds tubes by a vote over the loop's edges (another
  cut's tip side took the face on loop[0]->loop[1]: an inside-out index finger); a grafted GNM head keeps its own quads
  (`graft_head`: un-subdivided once in Blender, 12k -> 6k quads with diagonal flow on the cranium; both meshes cut at
  clean neck loops, `_neck_cut`: plane cuts zigzagged and twisted the bridge; bridged, projected, relaxed; a closed
  mouth zipped, `_zip_mouth`). The template's face onto GNM's proportions folded round the mouth and jaw whatever the
  landmarks (tried RBF with lip/chin landmarks, a global similarity, a smoothed registration): dropped. dgf: 13.9k
  verts, 98% quads, mean error 1.34 mm, head 0.78.
- `base.py`: spec `base` = a template body as the start of a character (`{"template": "male_stylized", "eyes": part,
  "girth", "soften", "push", "head"}`): the template's joints are injected (spec joints win), the body warped onto them
  with radii kept (`_skeleton_warp(girth=)`), Catmull-Clark'd, and becomes one primitive (kind "base", first in the
  prims): IMLS over the vertices with a compact Wendland kernel (a Gaussian's tail truncated by the k nearest speckled
  creases) whose width grows with distance (h >= 0.7 d: shells stay smooth; a fixed h dimpled a shirt); exact only a few
  cm out, so big blends or deep strokes on the base make plates: use `push` (normal bumps on the mesh) for volume.
  `soften` = Taubin smoothing of the heroic template (hands/feet/head kept). `head: {"source": "gnm"}` grafts Google GNM
  (Apache 2.0, `workspace/_templates/gnm/`, SOURCE.txt; not in the repo) above a neck plane: the template's own head is
  cut at a neck loop under its jaw and the loop extruded as a quad tube (`_neck_tube`; columns of points built from
  its vertices, or tapered to GNM's neck, left ruffs, lips and 45 degree steps: probe the surface per height before
  guessing), GNM's neck bent onto it per height under the plane (`_match_neck`), linearly blended across the band;
  GNM's bib (open edge) and mouth bag are cut away, the mouth filled behind the lips. `identity`/`fit` (face proportions
  in interocular units, ridge LS on its 68 landmarks, `fit_identity`)/`expression` (eye regions 000/001 open the lids)/
  `eyes` (scale about the eye centres)/`scale` (1.12 = 1/7 of 1.8 m). Face landmarks become `lm_*` joints (jaw, chin,
  brows, lids, lips, nose) to address strokes and paint. Builds are keyed on `base.VERSION` (bump it with any field
  change: the build cache didn't see base code changes). Worked example: `examples/disc_golfer_base_src.py`.
  Body sources: `body: {"source": "makehuman", "age", "weight", "muscle", "height"}` (`makehuman.py`: CC0 base mesh +
  macro targets from `workspace/_templates/makehuman/`, our own loader; joints from its default skeleton) or the
  template. The graft (2026-09-28): the body's head cut at the highest template neck loop wholly `LOW_LOOP` under the
  overlap (a bigger head's plane sat on the loop: ridge + flecks), a tube from it following the body's slope then the
  head's own neck slice by slice, both as ONE point set with C2 weights across +-SEAM (k = 4K there). Style layer
  `base.style = {"eyes", "head", "simplify"}` multiplies the head's settings (reusable across characters); simplify is
  Taubin on the head mesh, masked off the lid rims, lips, nostrils and the graft's neck (it moved the neck's open
  edge). Eyes: the eyeball (0.96 x GNM's eye radius) moves back until the lid landmarks clear it by EYE_SEAT (it
  bulged); both look at `base.look_at` (default 2 m ahead), joint `eye_front.L` carries iris/pupil paint (its r = the
  opening's height; iris ~1.1 x that). `parts.<p>.voxel` makes a scene part finer (a crisp iris). Lid rims need look
  resolution >= 384 in face close-ups (3 mm lids alias at 1.4 mm voxels).
  Garments (`parts.<p>.garment` on a shell part, `base.garment`): the body's quads pushed out by offset, closed by
  outward-only smoothing, hung, eased (`ease`, `ease_at`), plus tubes: `tube` (a shirt's torso) and `legs` (trouser
  legs along hip -> knee): per 1 cm slice the convex hull round its own centre (the femur axis runs near the thigh's
  side: rays from outside a hull miss), hanging from wider slices above, drape folds where loose; handed over to the
  body cloth by weight across TUBE_BAND (`_tube_weight`; a smooth union of the two swelled ~k/6: a ridge). The region
  blobs cut hems as with any shell; collars/plackets/cuffs are ordinary blobs/bones (layer 1), folds crease strokes.
  Tube `taper` (+ `taper_len`, `hem`): looseness taken in toward the hem, against the body's own hull. Garments are
  pushed clear of the real body (a grafted neck is wider than the template's). Collars: blob shape "collar"
  (`sdf.sd_collar`, a folded collar swept round the neck: stand + fall at `spread`/`spread_back`, `points`, `gap`);
  the shirt's region ends at a plane tilted like the neckline (a level box top left the shoulders bare or the chin
  covered). A strap is a shell of the shirt inside a chain of round cones, pressed in by a crease on the shirt.
  Necklines (2026-09-29, `garments.py`, kit type "neckline"; replaces the "collar" blob + neck cylinder cut): the
  neckline is measured on the body (per direction round the neck axis, where the neck has flared `flare` below its
  narrowest: low at the front notch, high on the trapezius; never dipping behind the sides, or the collar made a heart
  shape from behind), the shirt cut above it out to its own outer face (cut further, the fall sat over a shelf and
  showed skin under it), a V cut down to the first closed button, the collar a swept stand + fall whose fall angle is
  the least that clears the cut shirt (per point round the neck), placket strips left over right seated on the shirt,
  buttons (undone ones on the under strip). Everything is a blob shape "sweep" (`sdf.sd_sweep`: a 2D profile,
  "collar" or "band", along a polyline with per-vertex frames and numbers; `mirror` evaluates at |x|, a mirrored
  path's start on x = 0 isn't capped). `tests/test_sweep.py`.
  `base.head.mouth_gap` closes (or opens) the lips (least change of GNM's lower-face components); a closed mouth's
  cavity is filled (base.inject): left open it was an outside pocket in the head that the wrap projected into.
  Example: `examples/disc_golfer_mh.json` (MakeHuman + GNM, style, polo from the neckline kit (collar, open placket, buttons), shorts, trail sneakers,
  bag on a strap, disc, hair as a scalp shell + swept top; exported rigged).
- `hair.py` + `blender_hair.py` (2026-09-29; replaced the SDF groom on branch hair-sdf-wip: a mop with corduroy grooves,
  13 min builds): hair as curve locks in the Blender scene. Each lock is a legacy Bezier curve object (collection "hair")
  with one shared Geometry Nodes group `hp_lock`: resample, flat side facing away from the head centre + Flip + Twist and
  the curve's own tilt, a lens profile (width x thickness, the edges cupped toward the head) swept with Curve to Mesh,
  scaled along it (Root, Belly, Taper) x the point radius; it stores hp_along/across/out/lock/grey/tangent for the
  material (`material`: gaps and roots dark, a sheen band along the crest, per-lock value, grey, uneven soft grooves as
  bump). Chosen over Hair Curves + the Essentials groom nodes: those are strand tools (clump/curl/trim around guides)
  and give a fuzzy strand look; stylised hair wants a few big editable locks, and legacy Bezier curves give handles, Alt+S
  radius, Ctrl+T tilt and per-object modifier numbers a person can edit, instantly (a lock evaluates in ~1 ms).
  Capture profile attributes BEFORE scaling the profile (captured after, "across" was +-2 mm and the material never
  showed). Tilt is applied on top of a Free curve normal (checked): `lie_tilt` turns each lock's flat side onto the
  volume's own normal (facing the centre, locks across the upper side stood on one edge); `lie_cup` = the head's sag
  over half the width.
  Spec `spec["hair"]` = groom (hairline from the landmarks, parting, volume per region, flow words, tiers, `drawn`
  clumps), locks ([azimuth, elevation, height over the scalp] per control point round a centre from the landmarks, so
  they follow head edits; width, thickness, cup, taper, belly, root, twist, flip, grey, radius/tilt/handles per point),
  look, stage ("mass" = the groom's volume as one shell). `spec.geometry` strips it; `store.save` of a hair-only
  change skips the base-body validation. Scalp = rays from the centre, cached on disk by geometry
  (`hair_scalp_<key>.npz`). The volume (`envelope`): a dome highest behind the front hairline falling to the crown,
  rounded across, each side azimuth's profile filled to its convex hull (`_fill`: the top over close sides pinched a
  waist, the user's "divots"). The underlayer is the volume sunk by the covering locks' thickness (`under`); never a
  visible surface. Tiers: `strip` (sides/back: long locks along the streams converging on a point under the nape, in
  shingled segments), `gap` (roots where the locks so far leave the volume bare, splatted coverage), `drawn` (the top
  drawn by hand on the top view: the user's call after every generated top came out busy or jumbled), plus the older
  `big`/`crown`/`clumps`. Looks (`look`): the head-cropped stage file `hair_stage.blend` (the scene cropped to the
  head; 42 MB vs 300-440), EEVEE, material + clay rows, thumbnail, reference crop; 4-15 s. Gates measured every look:
  `silhouette_gate` (front + near side of 3/4: outline dent inside its own hull <= 1.5 mm at a 12 mm scale over
  brows+2 cm .. top-2 cm; notches at 6 mm reported; `hair_point_owners.npz` says which lock makes each outline bin)
  and `mass_share` (an ID render: bare volume / visible hair, target < 10%). Round trip: `blender_hair.read` compares
  each lock with the state the sync wrote (`hp_set`), `scene.pull` -> `hair.pull_locks` writes moved points, handles,
  radius, tilt and modifier numbers back (tested: 3 locks edited headless, pulled, re-synced, second pull empty).
  Export (`hair.export_part`, called by `asset._export` when the spec has locks): the locks at 12 x 8 + the underlayer
  decimated, one uv island per lock (round the lens x along) + smart-projected underlayer, packed by Blender, colour /
  roughness / normal baked by Cycles from the low poly's own material (selected-to-active from full-res locks picked up
  neighbouring locks where they overlap); its own atlas in the GLB with KHR_materials_anisotropy (rotation 90 deg:
  along the lock) and KHR_materials_sheen; bound to `parts.hair.rig_bone`.
  Reference matching (2026-09-29, the user's call after hand-drawn tops kept missing the reference's part and flow):
  `fit_camera` (pose + focal by least squares on lm_* joints vs reference pixels, pinhole at the image centre, the crop
  as Blender lens shift; `blender_scene.render` takes a view "shift"), `ref_trace.json` (part, hairline, outline,
  clump flows, landmarks; example `examples/disc_golfer_ref_trace.json`), `from_trace` (rays through the camera onto
  the volume/scalp -> parting `line` (`_part` then measures distance to it), hairline `front_points`, drawn clumps as
  `azel`), `fit_metrics` + the matched row in every `look`. dg_hair2: part 30 px -> 0.2 px off, clump directions
  20 -> 4.7 deg, IoU 0.53 -> 0.62 (the stylised cranium sits left of ours: hair can't close that). `parting.flat` /
  `parting.full`: the part side flatter, the swept side fuller. The back view was never gated and was ~20% bare
  volume: gap locks 60 mm wide at spacing 0.7 (sides/back/top) fixed it. Pull skips a lock whose scene copy was built
  from another version of the spec (`hp_hash` != `lock_hash`): a stale scene.blend had clobbered the spec with zero
  widths on export. Sync the hair (`hair.sync`) before exporting after a regrow.
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
  half of RAM at most, 12% or 6 GB kept back; $HIFIPUSHIE_MEM_GB) and run under `resources.guarded`, which kills the
  workers and raises MemoryGuardError if free memory falls under half the reserve. Wired into terrain_mesh
  (`_pool`, `export_tiles`), asset (`export`, `flatten_parts`) and blender_asset's worker Blenders. Any new pool or
  batch job must use them, and agents must not run sweeps/exports in parallel with each other.
- `tests/test_tooling.py`: reproductions of the tooling cards' incidents (`uv run python tests/test_tooling.py`).

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
- Loops from the anatomy (2026-09-26, `anatomy.loop_planes`, `spikes/topology/topo_anat.py`): hinge crease planes
  constrained alone give exact rings (elbows, knees, ankles 0.0 mm; 8.4k tris, mean 1.55 mm). Limb-root planes
  (through the cap top and both pits) cut open curves (they run onto the torso at the pit); slid down the limb to
  the first closed cut (shoulder 0.6 r, hip 0.4 r) they close, but constraining them breaks other loops, differently
  left and right and per budget: QuadriFlow's integer layout drops feature loops unreliably past a few. Sized runs also
  overshoot their face target ~4x with cuts (the calibration rerun then lands on a coarse lattice).
- Template wrap (2026-09-26, the user agreed; `spikes/topology/wrap.py`, template notes in `spikes/topology/template/`):
  Blender Studio's CC0 "Human Base Meshes" stylized male (12.5k quads, A-pose) carried onto troll_anat through
  matching skeletons (per segment: rotation, stretch, radius ratio per angle at 5 stations along the bone; hands and
  feet scaled uniformly by wrist/ankle thickness), face landmarks by a Gaussian RBF (face kit eyes, nose tip, mouth,
  ear joints), shot along normals onto each vertex's own region (the target prims nearest its segment and the
  neighbours: hands landed on thighs otherwise), relaxed. Deep interiors in the face (mouth bag, eye sockets) are
  kept, not projected. Result: 10/10 closed rings at shoulders, hips, elbows, knees, ankles, symmetric; the shoulder
  deforms with a real armhole loop; mean error 1.85 mm. Open: ears (human ears onto blade ears make flaps by the
  neck), eyelids tangle, the mouth interior pokes through the lips, toes collapse on club feet, two flaps behind
  the armpits; hands need finger correspondences (the goblin has 3 fingers); a quadruped needs its own template;
  25k tris is dense for a game (un-subdividing the template isn't clean).
  Then (2026-09-26): toes smoothed away on toeless feet; `untangle` (turned faces smoothed and re-projected: armpit
  and mouth-corner spikes gone); template eye openings follow instead of projecting (the troll's squint opening is
  ~4x2 template quads: still a small tangle); region-limited projection only for the first placement, whole body
  after (a finger cone buried in the palm left vertices inside); template finger/thumb chains measured
  (`male_stylized_joints.json`) and mapped onto the hand kit's chains, missing fingers smoothed into the palm.
  Goblin: body, arms, legs, face clean; its blade ears are lost (the template's ears are human). Hands are the open
  problem: the troll's fat fingers touch (no gaps for the template's finger sides: stubs), the goblin's thin ones
  collapse into strings. Fixed by digit tubes (`spikes/topology/tubes.py`): each template digit is cut at the
  closed quad loop nearest its base (every 45 deg sector round the axis, cutting off < 400 verts), the loop is moved
  onto the model's finger a finger radius past the knuckle, rings (the loop's count, angles carried along the
  chain, spacing = circumference / count, extra rings either side of each knuckle) are placed by rays from the kit's
  chain onto that digit's own prims (touching fingers keep their sides), a 45 deg ring and a quad fan close the tip;
  template digits the model lacks are capped; 4 rings of palm round each loop relaxed onto the surface. Result, all
  quads: troll 12.6k, goblin 13.0k faces, 10/10 joint rings, hand error < 1 mm, clean in the rig test pose.
  Open: blade ears (goblin: lost, most of its 3.1 mm mean error), eye-corner tangles, a small tangle at a capped
  finger's web, then a lower-poly version and wiring into export_asset/rig.
- Decimation stays for environments and props either way.
- 2026-09-28: the wrap moved to `src/hifipushie/retopo.py` (see Layout): blade ears, eye patches, fixed patches, the
  cavity rule. Then the user's priority moved to the base (`base.py`): the template as an SDF body, GNM as a head
  source (evaluated vs the template: realistic, 17.8k verts, 253 identity / 383 regional-PCA expression components,
  linear, so blendshapes are possible but not ARKit-named: card "Facial blendshapes"), the golfer rebuilt on it. User
  corrections on the golfer, in order: head 1/7 of the height (not the fit's), beard as stubble paint (not a shell),
  hair as a mass (not a shell), middle-aged soft body (not the heroic template; MakeHuman deferred: interim `soften` +
  `push`), clothes with volume and folds (card "Garments with volume and folds": next).

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

- `terrain_sea.py`: the sea (below a level, outside a `land` zone or the low ground reaching the frame's edge; it is
  low ground for the base, so a crater ring inside the land becomes a cone) and its coast as a continuous signed
  distance (re-cut from cells, cliffs were a staircase): shore forms per stretch (rocky, beach, cliffs at ~70 deg
  leaning into the water, beaches at a cliff's foot), coves (horseshoe bays with a beach, an apron and a scar at the
  head, optionally opening toward a valley). The sea is a lake named "sea" downstream (shores, sight lines, export).
  Two blind rounds (island, Cornish coast, `workspace/s1_*`, `s2_*`): the big shapes read (a cone with a crater lake
  and wave-cut cliffs); what still looks fake is eye-level character (plaster-smooth scars and cliffs, no stacks,
  ledges or boulders; domes for peaks; lava as a tan bump), and trails fail at cove scars (routes through cliffs).
- Route breaks (`terrain_design._breaks`, `_cut_break`): cliffs over 50 deg are walls to the route search (30 m
  smoothing hid them), except around the stops; where they close a route off, the barrier is the gap between what each
  end reaches at its grade, broken where lowest, thinnest and nearest the way: switchback legs along the cliff (as long
  as its top and foot run on, dry; its own downhill direction, not the line between the two points), benches with rock
  cut between, capped near the step's height; rolled back if it doesn't open the way. Many dead ends on the way there:
  steps along a relaxed path (fragile), fixed short legs (a 1 km trench), the frame's edge as a barrier, pairs far off
  the route. Planner rebuild (2026-09-26): the search runs on the full-resolution grid (every other cell hid one-cell
  cliff bands) over ground smoothed ~6 m with a 1 m bump allowance per step (30 m smoothing hid 45 deg risers: plans
  went where no road could be built), roads are planned at 0.85 of the limit, the grid path is NOT smoothed (every
  smoothing tried moved turns off the checked ground, over lips and down risers), crowded switchback legs (closer
  than their beds plus a 45 deg bank) are blocked and re-planned. Same pass rate on the test set, worst cases far
  smaller (mean as-built/limit 4.9 -> 2.6); roads are longer and jaggier (grid staircase). Next if routes matter
  more: a road planner in (x, y, road height) state so earthworks are part of the plan.
- `terrain_volcano.py` (2026-09-28): `volcanoes`, built into the base after `_hills` (large-scale ground, before
  texture, sea, erosion). Cone profiles (strato concave exponential from avg + top slope, shield convex, cinder
  straight, crater share 0.4 of the footprint); the flank blends local ground to the rim height (an offset from the
  centre's ground raised a cone's uphill rim 43 m on a slope); crater/caldera pit, breach (a small collapse from the
  floor), lake (a lake landform injected into the spec); radial gullies in two generations; collapses (U outline,
  walls from the rim at `walls` so `width` is rim to rim, floor = the flank's own long profile minus a sink easing
  to the mouth; a straight floor stood above a concave flank), debris hummocks; flows traced down the smoothed
  built ground with inertia and a slow random walk, a sheet over it (surface = smoothed ground on the path +
  thickness; the ground wins where higher: a flow fills a gully), levees, bowed pressure ridges, lobed edges,
  deltas at the sea. `settle` after erosion restores designed volcano forms and peak forms within the kind's gully
  depth (erosion had smeared 20 m gullies and taken 20-30 m off rims). Report measures rim (per bearing: first near
  top outward from the floor; a shield's flat top ran on past its caldera), lake + spill side, flank slopes by thirds,
  collapse width across its head, flow thickness over the ground it buried (the old "stands above the ground beside"
  read 60-81 m for an 18 m flow on a cone).
- `terrain_rock.py` (2026-09-28): rock character on every face over ~40 deg after erosion/settle: buttresses and
  couloirs as the ground resampled a horizontal distance along the fall line (profile kept, lip and foot notched;
  strike coordinate from the heavily smoothed gradient, ribs elongated along the fall line with wandering spacing:
  short blobs read as raindrops, even spacing as a comb; a third of the strength on 40-50 deg mountainsides), ledges
  (heights pulled toward a staircase, off designed walls: treads broke their unclimbable run), a boulder foot. Peak
  arêtes, routes, sites, water kept out. Measured: share of face cells turned > 25 deg from the face's line (canyon
  2% -> 37%), cliffs' width in cells (a 70 deg face 2-3 cells across renders as facets: `write_mesh` now resamples
  2x cubic for the render). Sea cliffs get stacks and a wave-cut platform (`terrain_sea`).
- Peak forms (`terrain_forms.peak_forms`, after volcanoes): pyramid/horn = planes through the summit and each pair of
  neighbouring arêtes (continuous across them), arêtes along the ridges that leave the peak at their gentlest fall
  (never cutting the ridge) but at least the form's own slope near the top (following the ridge made a 2 km "horn"),
  fillers up to the face count; faces hollowed next to the arêtes (sin^0.7: sharp crests); carve only the upper part
  (height-weighted), never into other ridges/cols/peaks (a 35 deg guard cone round them: a face cut a col 110 m down),
  fill only hollows the carving made (a basin floor in the zone had been filled whole). Default pyramid in alpine
  kinds. Measured: summit fall, faces, arête crest angle across (knife ~100, rounded 150+).
- Cover masks cut on the slope of the ground smoothed a cell, thresholds (slope and elevation) shifted by noise a few
  cells across (cut on the raw slope, snow and rock speckled cell by cell and every boundary was a pasted line).
  Floors and plateau tops get a gentle swell at player scale in `_texture` (they were flat plaster from the air).
  The rocky shore keeps land dry only a few cells in (`0.2 * min(sd, 3 cells)`; uncapped it lifted ground 400 m
  inland to 80 m: found by another agent's level).
- Views (`blender_terrain`): matte ground (specular 0.12: dark cover read brown at grazing angles), water with a
  noise ripple (bump on ~4 m features: 30 m swells were too gentle and it stayed a mirror), no site pole where a camera
  stands (views from a site rendered inside it, all black). The ground beyond the frame is a ring round it, never
  under it: its inner edge is the frame's own edge (heights and colours), carried on level then eased down to the
  30th-percentile edge height (a plane at the lowest point read as a sea on every alpine horizon; a plane at the edge
  height cut through a canyon). Blender's Python has no scipy.
- Blind rounds 2026-09-28 (`workspace/terrain/b1_volcano`, `b2_alps`, `b2_coast`; testers ran from this worktree while
  the agent developed in a scratch copy of `src/` on PYTHONPATH): the volcano, the horn and the stacks read only after
  the fixes that followed each round (collapse width, flow measure, arête slope near the top, stacks placeable and
  broken). Still open then (most since done, see Terrain2 below): a basin must be a closed ring, lake
  levels vs sites on their shores, village pads always on mounds, rugged barely visible on domes, sea cliffs 2 cells
  wide in plan (soft vertical drapes), horns still near-symmetric, no cairns/markers, lighting fixed from the SW.
- `terrain_sun.py` (2026-09-28, the user's decision): each view's sun. "auto" (default) builds a small image of the
  view (a ray per column, the ground point each pixel lands on; water left out: sea views had been scored on the
  seabed), shades it with each side sun (45-135 deg off the line of sight, 12-40 deg high, cast shadows) and scores
  neighbour-pixel contrast x3 plus overall, docked when >30% is dark or all of it dim. `views[].sun` / spec `"sun"`:
  side, bearing, {"from", "height"}, "morning"... The run notes each view's sun and warns on flat (behind the eye,
  >135 deg) or against-the-light suns. The Sky texture's sun follows (Blender 5.1: `sun_rotation = bearing`; `-bearing`
  put the sun disc in frame on the wrong side). The fixed SW sun had hidden b2_alps' pyramid faces (render 17).
- Terrain2 (2026-09-28, branch worktree-agent-a671e877e8eeb1ea4, renders 17-21):
  - Rock (`terrain_rock`): noise ribs read as melted wax and round pits (main's read of 17). Now: chiselled ribs
    (`_chisel`: piecewise-linear across the face, V couloirs); `facets` (a plane least-squares fitted per jittered
    cell, tipped, creased with its neighbour; weighted by how planar the ground was: a plane over a small cliff and its
    clifftop was a 50 deg ramp through a 70 deg face, the "drape"); pits the faceting closes are filled; buttress shift
    resamples the ground, never cross-fades (the fade bevelled every lip and foot); `bedding` on cliffs >55 deg (steps
    of max(2 m, 6 cells): 3 m beds on a 1 m grid were sub-cell, rms 0.24 m, invisible); scree `aprons` (cones at 33 deg
    below cliffs, in patches, sized to the face). Rugged crags are `facets` of the noise. Report: pits/km2 (> max(0.5 m,
    0.1 cell), rubble left out), roundness (median |laplacian| x cell), apron area. Views: a rock bump on faces >~55 deg
    (Voronoi joints at two sizes + stretched noise beds) in the ground material: sub-cell relief, like an engine's
    cliff material.
  - `terrain_detail.py`: `detail` (auto 2 with sea cliffs or cliffs < 3 cells across, fine side <= 1100). After erosion,
    `refine` resamples EVERY grid-shaped array on T (walks vars, dicts, lists; heights cubic in range, masks/ids nearest,
    NaN arrays nearest) and moves T to the fine grid; `terrain_sea.recut` re-cuts sea cliffs from `sd`/`top` (face
    plane, lip). Rock, checks, lakes, cover, export and views then run fine. ~2x build time.
  - Sea (`terrain_sea`): cliff lines jut and bay (sd moved by noise at ~3x the cliff height, only near cliff coast),
    wandering bevel, talus aprons (in `st_mask`, which recut and rock leave alone), placed `geos` dict, per-stretch
    `cliffs.heights`, shore `"rocks"` (graded bank + boulder strip, zone "rocks"), `cliff_feet()` + address
    `cliff_foot:<address>` (terrain3d's hook for caves/notches) + meta "cliff_feet". The sea beyond the frame uses the
    frame's water material (a glossier plane read as a pale shelf).
  - Basins open to a side: `inside` an open ridge + `opens` (compass or "edge:s"): the polygon is the ridge closed by
    rays out of the frame; walls stop past the nearer end (`mouth`, exempt in the wall check); zone `{"inside": ridge}`
    uses the basin's inside.
  - Rivers (`forms.water`): the level never stands above the banks (min of the ground beside, falling downstream) and
    banks are graded 1:3 within 30 m (not canyons, sites, routes): the river had been a stepped slab in a trench.
  - Lone hills combine by max (a saddle), not sum (+6 m stacking). Erosion's deepest cut is capped at 2x the kind's
    gully (tanh). Pads: level at the 40th percentile (cut in), big pads (r > 40) keep half the ground's lie (`flat`);
    the report says how far above the water beside it a pad ended and warns when its lake settled lower.
  - Blind round t2 (`workspace/terrain/t2_coast`, `t2_alps`, `t2_farm`; renders 24, 25). Fixed: routes on a pad run on
    its surface (`_profile` pins pad points; between two pads the grade is at least what their heights need, past the
    limit if it must: an even FAIL and a warning naming the pads, not a 4 m step at one pad edge); the as-built grade
    is judged on the deck over water and not on pads; ridge dome peaks rounded over `radius` (they were cusps: 41 deg
    "pimples"); the tilt's lift on ridge peaks is said; a land-zone coast with rivers keeps `world.base` away from them
    (the solve between rivers and seabed sank the land 16 m); rugged runs after the water (sea/lake zones work), on dry
    land only, and rock no longer re-facets it (spires); geos are flooded to their head last (platform/talus refilled
    them) and reported; stacks shrink 0.8x outwards; cliff heights judged per stretch; report lines for trench rivers,
    uncovered ground, detail left off, detail's cost; a river over a dammed lake's dam is a 0.15 m spillway.
    `terrain_rock.bed_step/bed_offset/params` are shared with terrain3d's solid rock (same beds, facet sizes, colour);
    views darken rock at the waterline (+0.4..2.2 m, the tiles' wet band).
- Terrain forms (2026-09-29, branch worktree-agent-a13c3e7dac22b5635, renders 26-32, blind round t3_coast/alps/farm):
  - Rock big structure first (`terrain_rock._structure`): buttresses/gullies spaced ~0.9x the local face height
    (`face_height`, octave bands 20-320 m, 17% amplitude, strong/slabby stretches), on a frame smoothed at their own
    scale (the ribs' frame turned round every spur: blades), the shift clamped to the room above/below (past a thin
    crest it pulled the far side up as saw teeth) and smoothed 1.2 cells (chisel knots made 1-cell spires at cliff feet);
    ribs inside are small (0.15 crag / 0.035 face height) and change every 3.5 spacings down the fall line (long thin
    fins read as wax). The faces' shift runs on into the sea (kept, waterline cells stood as spires). Tiers (`_tiers`) on
    non-sea cliffs; sea cliffs get ledges in their own profile (`terrain_sea._cliff_face`, T.sea["run"] = lip->foot, used by
    cliff_feet). `T.rock` ledges/gullies/tone; `terrain_rock.colour(T)` / `base_colour` for 3D rock (terrain3d uses it).
    Aprons are concave cones fed from gullies, ending at their toe (a -inf past it; they had spread 400 ha). write_mesh
    splits quads along the flatter diagonal.
  - Coves: asymmetric (`_headland_sides`: auto = the higher side), a cliffed headland (`head_m` forces cliffs), a low
    point opposite, the bay swung away, and a hollow (`rim`): on a 55 m plateau coves were pits ringed by 60 m walls.
    Report measures the bay/mouth along the axis on the coastline field (stacks and rocks awash were "a 1 m mouth").
  - Basin `walls.from_top` (`terrain._from_top`, `_wall_profile` branch): bands laid by horizontal distance floor edge ->
    ridge line (the harmonic t crowded to the ends: every band at the wrong slope), H over the wall from the floor edge to
    the ridge's own height; zones `<basin>.<band>` re-cut on the built ground by its form (`design._profile_zones`: scree
    down gullies and fans, forest up ribs; ruled stripes otherwise), auto cover per band (`_profile_cover`).
  - `terrain_detail.ground` after refine: undulation in a size spectrum (2.5/1/0.4 x scale), swales from D8 drainage of
    the undulating ground (stretched noise seamed along divides), hummocks in patches on gentle dry ground, hollows > 0.6 m
    refilled; off routes/sites/passes/water/intent sight lines (1 m hummocks blocked pebble_disc's holes).
  - Lakes with `dam: "moraine" | "rock bar"` (`_natural_dam`): across the valley at the lake's downstream end, level from
    the floor when left out, lake side a bank, downstream face 22/58 deg to the floor (ending the profile at lake level
    left a 300 m plateau and a 50 m scarp), a V spillway cut at the lake level; lakes with such a dam may run 8 r up.
  - `terrain_lines.py`: `lines` (hedge/stone wall/fence/bank/ditch/trees; along/follows/around/network). Networks default
    to `_subdivided_fields` (convex splits across the longer axis, sizes by noise: a grid read as a ladder, Voronoi as
    honeycomb). Lines stop at water/pads/crossed routes and slopes > 38 deg; banks/ditches never touch routes/pads (they
    had broken a lane's grade); ditches >= 3 cells; bank/ditch measured per cell against a local ring mean. Views: walls
    with each foot on its side's ground, fences, hedges as one lumpy ribbon (shrub balls read as beads; shrubs stay in
    trees.csv), no tree within 7 m of an eye. Export meta "lines".
  - Blind round t3: layouts land; still fake: rock faces up close (heightfield: smooth fins, no beds at 50 m range), the
    head as a mesa, stacks at a headland fuse like a causeway, hedges uniform dark, ground "lumpy" still subtle at eye
    level, the ground beyond the frame streaks, cliffs/scree bands under peak forms don't hold their asked slopes.
- `terrain_tools.py` + tools in `server.py`: `set_terrain` (spec or merge `patch`; `workspace/terrain/<name>/` with
  history), `check_terrain`, `look_terrain`, `export_terrain`, `terrain_history`; builds cached by spec content;
  questions come back as JSON (`Questions.data`). `guide(topic="terrain")`. `examples/terrain_tool.py` calls the same
  functions from a shell (for sessions whose MCP server predates the tools).
- `terrain_mesh.py` + `terrain_caves.py` + `blender_tiles.py` (3D terrain, 2026-09-28; card "3D terrain: SDF-meshed,
  seamless tiled mesh export"): the design stays heightfield + 3D shapes: `volumes` (arch, cave, overhang) and
  `caves` (skeletons: entrances and chambers joined by passages; kinds sea/karst/lava), all `Tube`s (a polyline with
  an elliptical section per node, rounded ends, a flat floor; rough fbm on walls and roof only). Output is optionally
  glTF mesh tiles (`export_terrain(tiles=True)`, `terrain_run.py --tiles`, cfg `spec.export.tiles`). Field, global and
  pointwise: `(z - h) / sqrt(1 + |grad h|^2)` with h the grid as an UNprefiltered cubic B-spline (C2, no overshoot at
  cliffs), each volume by smooth max/min, then solid rock relief (`rock_relief`: `_pl_facets`, random heights on a
  rotated lattice interpolated linearly over the Freudenthal tetrahedra = planar facets meeting in C0 creases, 2
  octaves; beds with a V notch and a proud or set-back offset each, stepping over in a ramp ~2 voxels wide, on
  terrain_rock's own `bed_step`/`bed_offset`) on ground steeper than 45-62 deg (a smooth grid mask, `Field.steep`)
  and near volumes (capped at 0.2 of a passage's size), never on floors. THE FIELD MUST BE CONTINUOUS: a jump (the
  nearest Voronoi cell's plane alone, a per-bed offset, the slope mask switching within 0.2 m at a cliff lip, a
  volume's box cutting inside its blend/NEAR reach) meshed as steps whose field normals pointed sideways = black
  triangular shards; blending cells smoothly read as mush. Crisp needs creases: MC vertices beside a crease are moved
  onto it (`snap_creases`: the QEM point of the ring's tangent planes, DC-style) and `split_normals` gives a corner
  its own normal only where it faces away (>75 deg; at 30 deg the zigzag creases showed as shaded teeth). Normals at
  1/8 voxel. Sub-voxel creases still zigzag; the seam check counts shards (`_shards`, `SHARD_LIMIT` per LOD). Rock
  colour = the heightfield views' rock (`rock_colours`: terrain_rock.colour when present, else kind + rock cover
  layers), toned per bed/facet, darkened by a field occlusion (F half a metre out along the normal). Facets ~8 m;
  voxel 0.5 m.
  Meshing: marching cubes (lewiner) per tile on the global lattice (voxel divides the tile; z planes offset 0.137
  voxel: flat floors at round heights lay on lattice planes and left non-manifold slivers), z only over the tile's
  own range (cost in area). Lattice values kept >= 1e-3 voxel from 0; border vertices keyed by lattice edge, each
  computed ONCE (crossing, Newton steps in the border plane, field normal, weights) and substituted into both tiles:
  bit-identical. LODs are LOD0 decimated, not re-meshed: each shared plane's chain (`_polylines`) is simplified by
  Douglas-Peucker once per LOD, nested (LOD k keeps a subset of LOD k-1), and both tiles collapse the dropped border
  vertices along the border (`_collapse_border`: half-edge collapse, link condition, no flips, never stranding a
  vertex; one that can't go is kept at every LOD by both tiles, and the settle loop reruns). Mixed-LOD gaps are then
  <= the tolerances (0.5 m; re-meshing at 2x/4x voxels gave 2.9 m). Interior: pyfqmr (dependency) with
  `preserve_border`, the fewest triangles within `error` (p99 |F| at face centres/edge midpoints) by a log search,
  capped by `budget`; its fins (twin faces) are dropped, non-manifold or hole-opening candidates rejected, other
  aggressiveness values tried; a LOD that folds at every count is decimated from an earlier LOD's mesh with its border
  collapsed, and if even that can't drop a vertex, every LOD keeps it and all tiles are written again. Interior
  re-projected. Skirts: in the border plane against the normal, as deep as the other LODs' chains stray (+25%),
  clamped to rock thickness; where the rock is too thin for the skirt a gap needs, every LOD keeps that vertex.
  Tiles run in a fork process pool (`_CTX`, up to 16 workers): marching cubes, dense projection, collapses, tiles
  and maps all parallel. LOD k>0 is decimated from LOD k-1's mesh (border collapsed to its chain), the dense mesh
  only if that fails; `_decimate`'s count search halves from the last good mesh (then 0.75, 0.88) instead of a log
  search over the dense mesh: pebble 256 s -> 61 s, LOD0 +6% triangles. `seam_check` reads the GLBs back (per-LOD watertight except the outer
  edge, identical border vertices/edges/normals, every LOD pair's gap under a skirt, heightmap edges) and raises; it
  caught a LOD2 fin, a vertex stranded at a tile corner, sliver non-manifolds at round-height floors and holes from
  dropped fins. Arches go where the land is shortest for their height (within `search` m); notches 5 m deep with the
  floor in the water; `wet_rock` layer and splash band (sea to +2.2 m, higher inside volumes); trees with no solid
  ground under them dropped. Caves: `terrain_caves.check` walks a person through every passage (floor by vertical
  field columns, headroom, width at 3 heights, the body as a capsule tested by SIGN on a ring of points and allowed
  0.8 m sideways: the field is no distance near relief and blends; steps <= 0.6 m; water depth) into the manifest.
  Karst: a wide bedding-plane tube with a flat roof (`Tube(roof=)`) over a slot, smooth walls (no facets) with thin
  beds as ledges (`Tube(beds=)`, `wall_beds`), shaft entrances in dolines (`dig_doline` lowers the Field's own copy
  of H: a grassy bowl, uneven rim; plus a rocky pit tube at the throat; depth limited by the rock over the passage).
  Lava: `"flow": name` runs a tube down a terrain_volcano flow line, floors on the flow's smoothed grade (following
  the surface put 1-3 m steps in), benches, breakdown `Mound`s (cones: tubes/ellipsoids have round ends that made
  steps or domes) under skylights and in collapse pits, standing on the lowest floor under them. Test level
  `examples/lava_field.json`. Chambers take `"in": m` from a directed address (`cliff_foot:<address>`).
  Renders through Blender's glTF importer (`render_tiles`: lod "checker" mixes LODs, `skirt_color` shows skirts,
  `lamp`/`exposure`/`fill` for views inside caves (a second light down the view: a lone headlamp blew out the near
  walls and read as fog), no tree within 7 m of an eye). pebble_disc, 0.5 m voxel, 208 tiles: LOD0 ~370k triangles,
  0 seam failures, shards 0.0005% of LOD0, Khronos 0 errors, ~1 min. Rock parameters agreed with terrain2 (no dip,
  their bed step/offset, a matching wet band in their views); rock colour is now theirs per cell.
  Views: an eye near a pit or skylight must stand within a few metres of it (from 10+ m the ground hides it), and a
  render job's `box` applies to every view in it.

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
