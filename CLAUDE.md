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
- Images as paint (2026-10-01, `images.py`, paint generator `image`; the user: "consume images on our models (framed
  painting, text on a page...)"): a planar decal (centre `at` = joint/xyz or a blob, seated on its face named by
  `dir`; right = up x dir so it reads from the front; depth window + facing ramp against print-through), image from
  "file" (copied at `store.save` into the content store `workspace/_images/<sha16>.png`, transparent pixels' colour
  bled from the nearest visible one, spec keeps "id" + "name") or "text" (PIL page, DejaVu from the system or PIL's
  default, ink colour everywhere + coverage in alpha spread by `INK` (alpha^0.5: thin glyphs read grey mixed in linear),
  cached as `_images/t_<key>.png`). `"color": "image"` = the picture's colours (paintnodes `color_from`), else a mask.
  Native nodes (`blender_scene._Nodes.decal`): u, v from `wpos` per pixel, Image Texture (Cubic, CLIP), a Non-Color
  copy for luma/r/g/b masks; a ".L" layer of image-only entries stays native with the mirrored placement (picture
  unmirrored), others fall back to the measured per-vertex mask. Export: `asset.decal_focus` adds texel_focus spheres
  (image px/m capped at `DECAL_MAX` 2000, <= `DECAL_GAIN` 16x, scene parts only: a prefab's part is in its own frame).
  Measured on `img_book` (4.2 mm text): 0.38 mm/texel readable in the GLB, 2.5 mm smudges. `asset.preview(cameras=)`
  renders a GLB through perspective cameras. Examples: `examples/image_decals_src.py` (img_painting, img_book,
  img_disc), `examples/framed_painting.json`; `tests/test_images.py`.
  Wraps (2026-10-01, `"wrap"`; renders workspace/image_renders/w0*): `cylinder` (axis = bone / two joints / point +
  dir / the `at` cylinder blob's z; `span` deg or width in m round the surface; `seam` = where the wrap is cut), the
  surface's radius measured by a ray from the axis (`images._hit`) above and below the centre = a local cone (r0 + m t,
  also the depth window and facing normal). `unroll` auto: |m| > `TAPER` 0.02 is fan-cut (u = angle x r0, v = slant
  distance from the apex: rows round the axis, ends along the generators, even height: the main session's call after
  "arc" (u = arc length at the point's own radius, v = axis height) sheared a shoulder band's ends into a
  parallelogram). `sphere` (lat/long; span [deg, deg] = equirectangular, or metres at the surface). Both per pixel in
  nodes (ARCTAN2, FLOORED_MODULO, ARCSINE). `surface` (`decalmap.py`): a discrete exponential map (Schmidt 2006,
  numba Dijkstra with upwind-averaged coordinates and frames) on its own mesh of the parts' field in a box round the
  seated centre (reach 1.3 x half diagonal, <= 160 voxels across; the box padded past the model's own bounds: cut at
  them, a ball's front pole had a hole), cached `_images/m_<key>.npz`; a point is looked up on its nearest triangle.
  In the scene u, v, weight are measured per vertex (fallback kind "decal", three packed scalars) and the picture
  sampled per pixel. Since 2026-10-01 the default is the vector heat method's log map (potpourri3d, dependency;
  `decalmap.METHOD`/`LOGMAP` "AffineLocal"; potpourri's default "VectorHeat" strategy was worse than the DEM: 2.5-5
  deg, 4-9% radius): the mesh vertex nearest the centre moved onto it (splitting its face to insert the centre left
  a T-junction: angles flipped 180 deg on one side), only the centre's connected piece, the library's tangent basis
  carried onto right/up by a Procrustes fit next to the centre. Against the sphere's exact log map (16 cm sticker,
  10 cm ball, off-axis): angle <= 0.12 deg out to 0.8 rad (DEM 1.85), radius <= 0.25% (0.38), 3.5-5 s a placement
  (DEM 0.4-2 s). The DEM stays as the fallback (no potpourri3d). Renders f02_*. `images.footprint` = the decal as it lies
  on the surface; `asset.decal_focus` covers it with spheres (one round it, or greedy ones of the decal's smaller
  side for a wrap: one round a can took the whole can) and now does prefab parts / split slabs too (decals reaching
  their mesh as it stands at the bake instance). `"style": true` = the image through the paint style's HSV
  (`images.styled_path`, a cached `s_<key>.png`). Examples `examples/image_wraps_src.py` (wrap_mug, wrap_bottle,
  wrap_sticker), images from `examples/images/make_images.py` (label, neck, sticker).
  Decals in the Blender scene (2026-10-01, renders f03_*): `scene.decal_gizmos` gives every image entry (entries
  alike in `images.PLACE_KEYS` share one: a picture, its impasto and brushwork) a wire object (`images.gizmo`:
  planar/surface at the centre, axes right/up/dir, scaled by the size; wraps on the axis at the label's height,
  x = toward the centre, z = the axis, scaled by the height; collection "decals", hide_render), stamped `hp_set`.
  `pull` -> `scene._pull_decals` -> `images.from_gizmo`: each of position/orientation/size counts only if it moved
  from the stamp, then is ABSOLUTE (the decal goes where the gizmo is; pulling twice changes nothing: a relative
  version double-applied when a headless pull wasn't followed by a sync). A decal at a joint/blob comes back as
  `"offset"` (new image key, world axes, added after a blob's face seat) while within its own larger side of where
  the anchor puts it (it keeps riding the blob through model edits), else as a world `at` with dir/up/axis written
  out; a spin about the normal as `rotate`, a tilt as dir/up (a surface sticker keeps only the spin); a wrap's turn
  round its axis as dir, a tilt as axis, a scale as span/size. A placement that no longer works (a label moved past
  a mug's cut rim) is logged and left. A cylinder wrap's taper probes step in to 0.25/0.1 h where the surface ends.
  Tested headless through the Blender MCP add-on (move, pull, sync, second pull empty) and in tests/test_images.py.
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
  per part. Chart borders (2026-10-01, the wrapped mug's label stepped a texel at a seam, renders f01_*): Cycles
  bakes one point per texel centre, unfiltered, so a sharp printed edge landed on each chart's own texel grid, and
  texels past an island's edge were nearest-copied. Now `bake_maps` bakes `BAKE_SS` 2 x 2 points per texel (box
  filter by alpha; skipped past `BAKE_SS_PX` 8192, one pass's images at a time), with no margin, and every map
  carries each island a ring past its edge: `rasterize(ring=)` extrapolates the triangle (slivers under 0.5 texel
  clamp), our own maps project those points, and `_across_seams` gives Cycles' maps the value the chart across the
  seam baked there (the face across found by topology: the edge the texel lies past and the fans of its two
  vertices; centroid KD-trees missed the decimated mug's 300-texel strips) and completes part-baked edge texels
  with it. Blender's own "Adjacent Faces" margin measured a bit better on the mug (0.91) but left a dark rim round
  islands: dents along a ball's chart borders (f04). `seam_steps` (export report `parts.<p>.seams`, WARNING over
  `SEAM_LIMIT` 1.5): along every seam edge the step across (half a texel into each chart, bilinear) vs the steps
  beside, steps under 0.2% of the map's range counted as noise; mug 1.64 -> 1.08, ball 1.0. What's left on the mug
  (~0.1 texel at 4x zoom) is bilinear reconstruction of a sub-texel edge at each chart's own phase: a texture made
  analytically from the low poly's own z shows the same. `asset.preview(denoise=False)` for texture close-ups.
- `faceshapes.py` (2026-10-01, for oxidegen lipsync; design note `spikes/face_shapes/README.md`): export_asset(face_shapes=
  True | [names]) gives the parts that move with the face ARKit-named morph targets (glTF targets, sparse POSITION +
  NORMAL deltas, mesh.extras.targetNames; FBX shape keys). A shape is a displacement of space from the face kit's
  anatomy (parting line, corners, jaw pivot, lid margins, brows, cheeks), applied to the same low-poly vertices: no
  re-projection (projection slid a 4 cm jaw move along the surface and dropped lips onto teeth). Needs the kit's
  `mouth.interior` (slit sweep subtract through the lips into a box bag; teeth/tongue parts); the export meshes the
  slit's part at <= slit/2.2 and its NEUTRAL closes the slit (after bake + skin). Weights are measured at the meshed
  (open) position, moves applied at the neutral. The nose and eyeballs never move. Rolls are moves (a turn tore);
  blink skin follows the lid's outer sphere (turning far skin about the eye swung a lever). Sheet:
  `examples/face_shapes_sheet.py` (`asset.preview(poses=)`); `tests/test_face_shapes.py`.
  Round 3 (2026-10-03, s0urc3's Garrett, base VERSION 61): `Face.seal` closes whatever gap the neutral left, on the
  low poly (3 passes: gap measured over points on each lip's triangles, bins across the mouth x a little back,
  smoothed over the mesh, 0.2 mm overlap, clamped at where the lips meet so corners don't cross; behind the front only
  the front's gap except past `SEAL_POCKET` 0.85, the corners' pockets). Tests ray-cast the posed mouth from the front
  and +-30 deg (`_front_hits`: triangles culled to the grid, then one row of rays at a time against the triangles
  spanning its height; the goblin has ~240k triangles by the mouth and rays x all of them OOM'd the box). Known cost
  of sealing: A2F's roll/shrug/pucker combos press the lower lip up in front of the upper by a few mm from the front
  (goblin PK+RL 2.7, RL+SL 3.9, PK+CL+JO 5.0, warm f31 13.1 mm; 0-10.5 with the slit open; not the overlap, which
  changes it <1 mm: the lips' depth order where they meet). `Face.owns`: only the slit's skin part (+
  `face_shapes.parts`) takes skin shapes; clothes none. Teeth: the upper row hangs `show` (0.5 x upper lip radius)
  below the parting line so jawOpen 0.3-0.6 shows it; the lower row 3.2 half-thicknesses back (at 2.2 the rows
  blended into one connected piece and the upper row rode the jaw: rows are told apart by connected component).
  Focus warp budgets: the joint collapse runs a second time on the joint mesh put back (unwarped), only to count each
  part's unfocused share; budgets are shared by those, a focused part gets its focused/unfocused ratio on top
  (`focus_extra` in the lowpoly info). A per-triangle estimate (sum of 1/magnification) missed most of the extra and
  left the clothes under the 10% redo threshold: Garrett's jacket stayed at 1,532 (v11 2,771) at 15k.
  But the focus is not where most of a dressed character's face-shapes extra comes from: the export meshes the
  slit's part (the whole body) at <= slit/2.2 and adds the mouth interior, so the body's own joint-decimation share
  grows (Garrett 5,742 -> ~8.5-9.9k) and the clothes lose ~45% at the same `triangles`. Pin the clothes with
  `parts.<p>.min_triangles` at the earlier export's counts and raise `triangles` (Garrett v15: 20k, clothes = v11's,
  45,966 total with hair), or give the body a lower triangle_weight. A GNM head's upper teeth: Garrett needed
  `base.head.interior.teeth.show` 0.0035 (the 0.5 x ru default showed ~1 mm) and `parts.teeth.min_triangles` 600 (the
  300 x flat floor left 128-149 triangles: a flat band, 30-40% of its texels missed).
  Round 2: GNM heads (`GnmFace`, `examples/gnm_talk.json` = the golfer's MakeHuman body + GNM head without clothes,
  hair or the wrap topology, which zips the lips): each shape = 68-landmark moves solved in GNM's expression basis
  (as `base.pose_expression`), carried onto the export (eye scaling, narrowing, placement, then Catmull-Clark like
  the skin, all shapes side by side; inverse distance over the 6 nearest head vertices, between the lips only its
  own lip's, by GNM's lip groups: by height, the inner rolls mixed and tore the slit walls); interior = the kit's,
  placed from the lip landmarks (`base.mouth_interior`; GNM's own teeth stood in front of the style-pushed lips);
  bag/teeth/tongue by the jaw's Procrustes motion for jaw shapes. Needs `base.head.interior` + `mouth_gap` >= 0.002.
  Export triangle focus (`focuswarp.py`): the high mesh is magnified 2x round the lids/lips before decimation and put
  back after it in Blender; Blender's Decimate vertex group protects ANY weighted vertex outright (useless).
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
  Twist chains + rigid head (2026-10-05, s0urc3's Garrett: a hand turned 75-105 deg was wrung at the wrist, the jaw
  lagged a head turn; renders `workspace/rig_renders/tw_*`): `_add_twist` appends leaf joints AFTER the Mixamo set
  (its names / order / indices / rest unchanged), children of their segment's joint: `<Side>ForeArmTwist1..3` and
  `LegTwist1` follow the Hand's / Foot's roll (share k/n at station k/n, 1.0 at the wrist), `ArmTwist1..2` and
  `UpLegTwist1` counter their own joint's roll (-1.0 at the shoulder / hip). `spec.rig.twist` = false | n | {arm,
  forearm, upleg, leg} (default 2/3/1/1: LBS between stations d apart keeps cos^2(d/2) of a section; forearm at
  105 deg on MakeHuman: none 0.49, two 0.80, three 0.87). Twist bones carry no flesh (`_segments` skips them):
  `_spread_twist` shares the segment bone's weight between the two stations a vertex lies between, so undriven the
  skin is the old skin. A fifth bone: the smallest weight is dropped, unless a split's smaller half is within
  `TWIST_MERGE` x it, then the split goes back (always dropping moved the goblin's arm/belly web 10 mm undriven;
  always merging sheared thigh triangles when driven; now <= 3.5 mm on 2% of its vertices). Driving is the engine's
  (glTF has no constraints): `drive_twist` / `roll_about` (swing-twist) are the reference, the GLB's twist joints
  have local +Y along the segment and `extras.hifipushie_twist`, the json has `rig.twist` + `rig.twist_recipe`
  (Godot / Unity / Unreal; `asset.TWIST_RECIPE`). `head_field`: h = 1 where a point is head, by the Head bone's
  flesh being no farther than any other's (kit characters), a floor from GNM's jaw landmarks (chin -> jaw angle,
  level behind, `HEAD_UNDER` lower), or typical proportions (a base without landmarks); `_rigid_head` blends weights
  to Head by h (falloff `HEAD_BAND` on the throat), a part >= 0.9 head on average is all head (teeth, tongue,
  eyes); the export then makes every vertex a face shape moves 3 mm or more Head 1.0, less in proportion from 0.5 mm (`rigid_near`; a big jaw's field reaches the goblin's chest by fractions of a mm). Judge with the
  rig tool's text (`rig.report`: `twist_check` per chain, `head_check`) and `pose={"RightHand": ["roll", 105]}`.
  Known: twist bones fix roll, not bend (shoulder dip, elbow crease stay); a 33 deg head turn folds the throat
  under the jaw over the 3 cm band. `tests/test_rig_twist.py`.
  Weights audit + template weights (2026-10-05/06; the user on the twist sheets: "the fingers are getting mangled and
  so is the jaw. We might have serious issues with how our skin weights are getting made"; renders `rig_renders/wa_*`).
  Three things were tangled: (1) the rig tool's look build (11 mm voxels on a human: fingers fused AT REST; the real
  export's hand is fine at rest); (2) the weights: by distance, one finger's bones held 0.2 of the next finger and
  moved it 4-8 mm, a thigh moved the other thigh 20 mm; (3) the RIG: on MakeHuman bodies the "neck" joint is the
  neck's BASE, so Head (placed on it) pivoted 10 cm low, at chin height, and Neck sat inside the chest.
  - `rig_audit.py`: `read_glb` (an export as an engine gets it), `audit` (each joint turned alone through
    `AUDIT_TURN`: rigid = its own skin against a rigid turn, leak = other bones' skin moved and whose, flipped
    triangles, volume on closed meshes; digit bleed; L/R asymmetry; sums, influences) and `audit_text` ("<- BAD").
    Ownership is by nearest bone segment, so it only judges CLEAR skin (`CLEAR` 0.7: the web between two fingers and
    the knuckle zone are nobody's; `BURIED` bones, clavicle and thumb metacarpal, are judged on their descendants):
    without that it called MakeHuman's own hand-made weights bad (bleed "0.94") while every pose was clean.
  - `rig_template.py`: a base body made from MakeHuman takes MakeHuman's hand-made weights (`makehuman.weights()`,
    rigs/default_weights.mhw, CC0) by TOPOLOGY (`base.surface()["src"]` = each quad vertex's template index, kept
    through the neck graft), its 139 bones folded onto the Mixamo joints (`_mixamo`; spine / neck bones by where
    they lie, `_central`; face, jaw, tongue, eye bones -> Head). Every other mesh (the export's low poly, clothes)
    reads the base's weights at the closest point of its SURFACE that faces the same way (`from_surface`,
    `AGAINST`): the 4 nearest base VERTICES of a finger's side were as often the next finger's. Then
    `_spread_twist`, then the rigid head. `spec.rig.weights = "distance"` for ours; the stylised template and kit
    characters have no hand-made weights and stay on distance (now also read by surface).
  - `rig.humanoid`: a template's `rig` hint ({rig joint: [joint a, joint b, t]}; `makehuman.body`) places Neck on
    the "neck" joint and Head 63% of the way to "head" (MakeHuman's own head bone); clavicles stay where they were.
    This MOVES Neck and Head on MakeHuman characters (names / order unchanged): re-export, and a game's cached rest
    pose changes.
  - Exported human (15k), same mesh re-skinned: BAD joints 13 -> 5 of 51; digit bleed 0.21 -> none; fingers'
    leak 4-8 mm -> 0; thigh on thigh 20 mm -> 0; knee rigid 5 mm -> 0. Left BAD are MakeHuman's own choices at our
    thresholds (elbow at 90 deg moves upper-arm skin 8.6 mm, the foot's weight runs 25 cm up the shin) and 35
    flipped triangles in one groin at 60 deg.
  - The mouth and jaw that looked "mangled": at REST the 15k export's mouth is already faceted and lumpy, and
    jawOpen alone (no weights) is lopsided: the low poly and the face shape, not the skin. Not fixed here.
  - Bone heat (Blender automatic weights) vs ours on kit characters (look builds): goblin 13 vs 17 BAD of 45 (rigid
    better, leak worse: 30 vs 13 mm arm <-> thigh), troll_anat 40 vs 38 of 51. Neither is good: their limbs are
    fused to the body in the look build. Not adopted; kit creatures' weights are an open problem.
  - Dressed characters (2026-10-05, the golfer's export re-skinned; renders `rig_renders/wa_golfer_*`): (1) the
    grafted neck/head copied the template neck LOOP's weights all the way up (Shoulder 0.38 / Arm 0.19): an arm at
    60 deg pulled the neck's side and the collar 25-36 mm. Now it hands over to the Neck joint within
    `rig_template.GRAFT_REACH` 4 cm. (2) The head rule is by height, so a collar's top (1-2 cm over the floor at the
    nape) was Head 1.0 and turned with the face (47 mm, 299 flipped): a part other than the skin (`spec.rig.skin_part`,
    "body", + face_shapes.parts) that is under `HEAD_WORN` 0.5 head is worn and takes no head rule;
    `parts.<p>.rig_head` overrides. (3) A worn part's transferred weights are smoothed `WORN_SMOOTH` 6 rounds over
    its own mesh, seam-split vertices welded (a collar's two faces and edge read three places: its wing crumpled).
    (4) The head floor climbs one jaw landmark up the ramus behind the jaw's angle; up to the Head joint it put the
    ear lobes in the band (30 flipped triangles under each ear). The audit counts smoothed cloth as leak and cloth
    folding at 60 deg as flipped: read its cloth rows with the renders. Open: a strap shell beside a rigidly bound
    bag shreds at the hip, hems fold (no hem bones), fingers touching round a held disc read the wrong finger.
    Then: `parts.<p>.rig_attach = "<part with rig_bone>"` (within `ATTACH` 8 cm of it the part blends to that
    joint: the strap's end goes with the bag; 48 flipped strap triangles at a 60 deg thigh -> 9), `rig_smooth`.
    A neighbour-majority mend of stray digit vertices was tried and dropped (it missed the one welded vertex in
    the web and worsened another). Hems: guide only (no hem bones).
  - Judge exports as an engine draws them: `rig(glb=)` leads with `asset.preview` of the GLB (maps + normal map;
    preview poses take `"turns": {joint: [x, y, z, deg]}`, carried into each imported bone's rest frame as
    rest^-1 R rest, plus face shapes) over the clay row. The human's "lumpy mouth" was clay: 7.5 mm facets at 15k
    (1,541 face triangles; 40k: 3,690, 4.9 mm) read smooth with the normal map, and jawOpen is symmetric as a
    shape. Real at 15k: a crease beside the nose in jawOpen and kinked smile corners (gone at 40k); real at both:
    the blink's lid line is ragged (open: seal the lids on the low poly as `Face.seal` does the lips).
  - Kit creatures on REAL exports: the goblin (goblin_talk) tears a slab of skin at the shoulder and webs when the
    arm rises, because its arms are modelled against the belly: one skin once meshed. `rig_audit.fused_limbs`
    (the rig tool's WARNING): the share of a limb segment's own flesh surface within `GAP` 8 mm of unrelated
    flesh (goblin_talk 25%, goblin_anat 2%, trolls 8-12%; warns over 20%). The audit takes ownership from the
    modelled flesh on kit characters (`flesh_distances`): by bone segment the arms "owned" 830 belly vertices and
    read 116 mm off a rigid turn.
  - Blink (`GnmFace._lid_seal`, `LID_SEAL` / `LID_OVER` / `LID_BAND`; render `wa_gnm_blink_seal.png`): the basis
    DID close the eye (front rays reaching the ball: 43% open, 0.1% blinked); the ragged line was each low-poly
    margin vertex landing at its own height. Now 14 bins across the eye put both margins on a parabola through the
    lower lid's (each vertex by its share of its margin's travel), then the band 1.5 mm either side is squeezed
    onto its own lid's side. Clean line in clay on the 40k human; 1-2% of rays see the ball at the outer corner
    (the fade past the corners). Not yet seen through a fresh export with maps; the face kit's `_blink` unchanged.
  - Fresh golfer export (2026-10-06, 30k / 2048, scratch `rigtwist/exp_golfer`): Khronos 0 errors 0 warnings;
    audit 11 BAD of 51 (old export 20, old meshes re-skinned 16-17), no digit bleed, Head not flagged; left: knee
    onto the shorts' hem 17-27 mm, arm onto the collar 18-20 mm, forearm 10 mm, cloth flips. workspace/dg_fix2's
    own spec has no `rig_attach` (only the examples do): its strap was exported unattached.
  - HANDOVER (rigtwist agent, context full): branch `worktree-agent-aaa260409e3ad0ff7`. Scratch scripts in the
    session scratchpad `rigtwist/`: aud.py (audit a GLB), reskin.py (re-skin a GLB's meshes with the code as it is;
    env GR / WS / ATT), wa2.py (dressed before/after sheets), blink.py (lid seal before/after + rays), facesheet.py
    (GLB with maps, 6 shapes), dbg8/10/12.py (whose vertices leak / where triangles flip / stray digit vertices),
    fused.py, val/v.mjs (Khronos), expg.py (golfer export). Open, in order: (1) the blink through a fresh export
    with maps + test in test_face_shapes; (2) goblin_anat and troll real exports audited (never run); (3) the
    goblin: its model must be fixed (arms clear), the tool says so; "fail soft" weights for fused limbs not built;
    (4) kinked smile corners at 15k; (5) the throat card; (6) hem bones; (7) a rig check in a real engine.
  - Rig round 2 (2026-10-05/06, "rig2" agent, branch `rig2`; renders `rig_renders/wb_*`; exports in
    /mnt/data/hifipushie/rig2/exp_*; scratch in the session scratchpad `rig2/`: run.sh <script> (worktree code on
    the main workspace), exp.py (export), sheets.py (posed sheets through `rig(glb=)`), reskin.py + cmp.py (re-skin
    an export's meshes with the code as it is, audit, clay rows side by side), throat.py (head falloff variants +
    fold numbers), lidline.py (blink gap per bin), geo.py (surface-geodesic weights spike), val/v.mjs (Khronos)).
    - Throat: the head's falloff on base bodies is `HEAD_FALL` 0.2 x head size (~5 cm), was 3 cm. Skin fold
      (`throat.py`: change of dihedral across the neck's edges) p99 at a Head-only 33 deg turn: bare human 40 -> 24
      deg, golfer 20 -> 12; nod 56 -> 43. A longer falloff on the FRONT of the throat only (the card's idea)
      changed nothing: the fold is at the sides and the nape. Kit characters and `rigid_near` keep 3 cm. A hard
      Head-only nod still folds (the chin meets the chest on these short necks): share it with Neck.
    - Blink: `_lid_seal`'s last step mapped the band either side of the line LINEARLY, which parked the upper
      margin ~0.5 mm above the line and the lower ~0.75 mm below: the thin slit that still showed (gap between the
      margins +0.4 .. +1.5 mm on the head mesh). `LID_PINCH` 3 draws the band to the line: -0.5 .. +0.2 mm.
      `tests/test_face_shapes.py::test_blink_lids_meet` (head mesh and pyfqmr-decimated to a third). A per-bin
      vertex measure is NOT valid on a 15k export (bins without a margin vertex read 25 mm): judge those by render.
    - `parts.<p>.rig_drop = [joints]` (`rig.drop_joints`): a garment's influences pruned, their weight up the chain
      to the nearest kept joint (a name without a side = both sides + the segment's twist joints). Golfer: shorts
      ["Leg"], shirt ["ForeArm"], collar ["Arm"]: knee -> hem 17-27 mm and elbow -> sleeve 10 mm gone, the hem stays
      a tube on the thigh (`wb_drop_knee90.png`). This is the cheap answer to hems; hem BONES still not built.
    - Export: with rig, parts bound to their own joint (`rig_bone`) don't bury their neighbours' faces
      (`surface.hidden(apart=)`, `ctx["apart"]`): the golfer's shorts had a HOLE where the hip bag sat, shown by
      a lifted thigh (a dark patch in every earlier thigh sheet, read as shadow).
    - Assets: `assets.pack(name, files=)`; `makehuman.root` needs only base.obj + default.mhskel, so a male body
      opens with the pack as it was before the female targets and default_weights.mhw were added (s0urc3 BLOCKER);
      missing weights -> distance weights + a WARNING in `rig` and the export log (`rig_template.weights_note`).
    - Kit creatures, spike (`geo.py`, goblin_anat look build at 256): weights from SURFACE GEODESIC distance to each
      bone's own skin (scipy dijkstra over the welded mesh, max with the Euclidean flesh distance) remove every
      leak and rigid error (arm 5.9 mm rigid / 14 mm leak -> 0, thigh on thigh 5 mm -> 0 at full strength, 4-5 at
      half), but blends get narrower and flipped triangles rise at elbows / knees (53 -> 130-270) and Spine2 (420).
      Digit bleed is unchanged on a look build (fingers fused at 3.6 mm voxels). Not adopted yet: see HANDOVER.
    - `rigid_near` (the face-shape pass in the export) skips parts no shape moves: the golfer's collar took Head
      0.56 from the moved throat skin beside it and turned with the face (26 mm at 33 deg) in every export WITH
      face shapes (Garrett too); the worn-part rule held in `skin_parts` only.
    - Fresh exports (all Khronos 0 / 0): `exp_golfer` (dg_fix2, 30k / 2048; BEFORE rig_drop and the hole fix:
      audit 10 BAD of 51, no digit bleed), `exp_gnm` (tw_gnm 15k + face shapes: 5 BAD), `exp_talk` (model
      `workspace/wb_dg_talk` = dg_fix2 + `base.head.interior` + mouth_gap 0.003, no wrap topology; 36k + face
      shapes, with rig_drop and the hole fix, BEFORE the rigid_near fix: its head-turn sheet shows the collar going
      with the head). Sheets `wb_golfer_*` (head33 good; nod: a lump of nape skin between hair and collar from the
      side; arm60 clean; thigh60 shows the hole; handroll105: forearm smooth, dark cracked patches where the hand
      grips the disc, unverified), `wb_talk_*` (thigh60 clean: no hole, hem a tube; blink closed with a clean line;
      jawopen good), `wb_gnm_*` (15k blink: closed, small dark notches at the eye corners; smile fine).
      workspace/dg_fix2's spec now has the strap's rig_attach and the three rig_drops (v8).
  - HANDOVER (rig2 agent, stopped by the session's usage limit, 2026-10-06). Branch `rig2`. Tests green on the
    head: test_rig_twist, test_rig_audit, test_tooling, test_face_shapes. State of jobs: a goblin_anat export
    (15k / 1024) was running into /mnt/data/hifipushie/rig2/exp_goblin_anat (log scratch `rig2/exp_goblin_anat.txt`)
    when the queues were stopped: check whether it finished. NOT started: troll_anat export, the golfer re-export
    (dg_fix2 with rig_drop + hole fix, into exp_golfer) and the talk re-export (rigid_near fix, into exp_talk):
    `bash rig2/run.sh exp.py <model> <out dir> '<json kwargs>'`, one at a time (they take the heavy slot; Oxidegen's
    exports hold it for long stretches). Next, in order: (1) those three exports, Khronos (`node val/v.mjs x.glb`),
    sheets (`run.sh sheets.py <model> <glb> <prefix> [poses]`), the talk head-turn sheet must show the collar
    staying; (2) kit creatures: run `run.sh geo.py goblin_anat 256 <glb>` (ours vs geodesic on the REAL export;
    `GATE=1.5,3.5 MIX=1` = the gated variant, the promising one: Euclidean blend kept, an influence cut where the
    path along the skin is over 1.5-3.5 limb radii), render both in the test pose (`reskin.py` saves weights,
    `cmp.py` draws them side by side), adopt it in `rig.weights` if the renders agree with the audit; watch the
    flipped triangles at Spine2 (413 on the look build: probably the pec / lat sheets) and digit bleed on the real
    mesh; (3) the audit card (id cmuvoqmmf00f8k6f29lu2bvex, NOT the project id) and the throat card
    (cmuvmbarn00f6k6f2jcsm4x7b) still need this round's numbers; the twist and rigid-face cards were already DONE;
    (4) open: hem bones, the nape lump on a nod, the hand / disc dark patches, the arm's 20-25 mm on trapezius
    skin near the neck (MakeHuman's own Arm weight; sheet looks fine), a rig check in a real engine.
  - Rig round 3 (2026-10-06, "rig3" agent, branch `worktree-agent-ac0c3684da084a02f`; renders `rig_renders/wc_*`;
    exports /mnt/data/hifipushie/rig3/exp_*; scratch in the session scratchpad `rig3/`: run.sh, exp.py, sheets.py
    (poses incl. nod_shared, knee90, rest_hips, hand_rest, smile_far / smile_near), strip.py (several sheets' engine
    rows side by side), reskin.py + cmp.py + leak.py (RS=<rs npz> = re-skinned weights), throat.py, geo.py,
    queue1-3.sh, tests.sh, gposes.json (Godot poses)).
    - Geodesic weights for kit creatures: NOT adopted. On the REAL goblin_anat export (15k) both variants are worse
      than ours by the audit (knee rigid p95 14 -> 22-28 mm, elbow 7-8 -> 15-17, leaks 20 -> 25-30 mm; only the
      shoulder's rigid error improves, 11 -> 3.7 mm, with 3x the flipped triangles) and they TEAR in the render
      (cracks in the armpit and the groin: `wc_geo_goblin_knee90.png`, glb = ours on top). On a decimated mesh the
      edge-path distance is 10-40% long and jumps between neighbours, so the gate cuts an influence on one vertex and
      not the next. The spike's good numbers were a look build's dense mesh. goblin_anat's own export (never checked
      before): Khronos 0 / 0, rest / arm 60 / thigh 60 read clean in the engine row (`wc_goblin_anat_*`); its audit
      says 29 of 45 BAD, which on stubby limbs (a blend zone as long as the segment) is the audit's human
      thresholds, not the skin. Digit bleed 0.40-0.45 on its 3-finger hands is real and unchanged.
    - Head falloff (the throat card): on base bodies the head's weight now fades down the neck's LENGTH
      (`HEAD_FALL` 0.44 x head size ~11 cm, was 5) inside the neck's column (`HEAD_COLUMN`: full within 9 cm of the
      Neck -> Head line, none past 15.5; outside it the old 5 cm, `HEAD_SHORT`), and `rigid_near`'s band on base
      bodies is `HEAD_NEAR` ~8 cm (was 3). What riggers paint: a head-to-neck gradient over the whole neck. Bare
      human 15k, Head alone (throat.py): turn 33 deg fold p99 / max 25.8 / 161 -> 11.7 / 30 deg, nod 25 deg 36 / 153
      -> 14.5 / 28, edges folded over 30 deg 16-33 -> 0 (`wc_throat_fall_gnm.png`). Either change alone did half.
      By height alone the long falloff reached the shoulders (trapezius skin moved 70 mm): hence the column. And
      under it a collar averaged over `HEAD_WORN` and turned with the face again (57 mm): which part is head or
      worn is judged on the SHORT field (`hf["part"]`). A `nape` factor (longer behind) changed nothing: left at 1.
      Garments never take the long falloff (tried: the collar crumples). Cost on a dressed character: on a hard
      Head-only nod the nape skin swings back against the collar's stand and pokes a sliver through it
      (`wc_throat_golfer_nod.png`); the chin still sinks into the collar. Both go when the nod is shared with Neck.
      Kit characters unchanged. `spec.rig.rigid_head` = {fall, band, under, column, nape}.
    - `rig_drop` takes shares: `{"UpLeg": 0.5}` = half that joint's weight (its twist joints' too) up the chain.
      The shirt hem on the golfer hardly reads it (its hem is already the pelvis's): no visible change at a 60 deg
      thigh, flipped 41 -> 23. Hems, what riggers do (web search + the guide's section from rig2): weights toward
      pelvis + thighs for shirts and shorts (have), skirt / coat chains driven by the thighs or springs in the
      engine (not built: no test garment needs it; build it with the first skirt, as leaf joints after the set).
    - THE TORN HANDS (the coordinator: "the most important thing you found"; the user's first complaint was mangled
      fingers). By stage on dg_fix2 (`rig3/stage.py`, sheets `wc_hand_stages_R.png`, `_L.png`): the body's field
      meshed at the export voxel is clean, fingers apart; `retopo.wrap` tears BOTH hands at the webs and the thumb's
      root, at rest, disc or no disc (the wrap sees only the body's prims): the stylised template's digit tubes and
      palm carried onto MakeHuman's close-set fingers ("untangle: 2251 faces still turned after 12 passes" was in
      every export log). Decimation, hidden-face pruning and the bake only inherit it. Fix at the cause: a base body
      ships its OWN quads (`retopo.base_quads`: `base.surface()["quads"]`, MakeHuman's or the template's own
      animation topology, each vertex dropped <= 4 mm onto the field (the cage stands 0.5 mm mean off it), a GNM head
      grafted on as before). `parts.body.topology = "wrap"` now means that on a base; `"template"` = the old carry
      (kit characters, which have no quads of their own, are unchanged). The whole body, before / after: folded edges
      217 -> 33, faces turned against the field 416 -> 12, non-manifold edges 18 -> 0, p99 off the field 2.26 ->
      1.41 mm; clusters at finger1_1.L 88, finger4_1.L 81, finger4_1.R 71, finger1_1.R 66, thumb_1.R 22, knee.L 46
      -> none on the hands (ankle.L / toe.L 9 / 8, under the shoes).
    - So it can't ship silently: `asset.mesh_quality` counts `turned` faces (normal against the field's gradient,
      faces near the surface only) and returns the defects' `spots`; `asset.defect_regions` groups folded edges +
      turned faces by the model's nearest joint (`DEFECT_CLUSTER` 12; spots inside another part don't count: the
      skin behind an eyeball), and the export's quality line says "WARNING ... TORN OR TANGLED at finger1_1.L
      (88), ..." with `quality.defects_by_joint` in the json. Tests: test_tooling `test_mesh_quality`,
      test_handwarp `test_export_topology_is_the_bases_own`. Decimated bodies (wb_dg_talk, no wrap) had clean hands.
    - The ragged shirt hem: the shirt is a SOLID shell with a smooth rounded rim (look build: fine); the export
      dropped its faces "hidden in another part" exactly where it goes under (its inside lies in the body /
      shorts), so the cut ran along the rim, a triangle deep and wavy, and shed shards over a lifted thigh.
      `asset._deep_hidden` (`HIDDEN_RIM` 12 mm): a hidden vertex with a visible vertex of its own part within the
      rim stays, in `prune_hidden` and `topology_parts`; the cut lies inside where nothing looks. Test
      `test_hidden_faces_are_cut_inside_the_rim`.
    - troll_anat's real export (15k / 1024, Khronos 0 / 0; `wc_troll_anat_*`): rest, thigh 60, knee 90 read fine;
      arm 60 drags a pale stretched patch of trapezius skin from the neck to the shoulder; fingers are fused
      (digit bleed 0.27-0.38, a finger joint moves its neighbours 20+ mm; audit 45 of 51 BAD). Body usable, hands not.
    - The golfer shipped with all of it (dg_fix2 30k / 2048, /mnt/data/hifipushie/rig3/exp_golfer, 849 s, Khronos
      0 / 0): body quality line 3 folded edges / 2 turned faces (was 217 / 416), p99 / max off the field 1.13 /
      2.7 mm (2.26 / 16.5); audit 6 BAD of 51 (rig2's export 10; left: arm onto 30 neck-side vertices 18 mm, Spine1
      onto the shirt hem 10 mm, cloth flips); sheets `wc2_golfer_*`, before / after `wc2_hand_before_after.png`
      (hand at rest, maps + clay: clean), `wc2_handroll_hem_before_after.png` (hand roll 105: no cracks; hem at a
      60 deg thigh: a smooth edge, no shards), `wc2_golfer_head_engine.png` (head 33: collar stays; nod: a lump of
      nape skin still stands over the collar's stand, Head-only AND shared with Neck: NOT fixed), Godot
      `wc2_golfer_godot.png`. The collar's line now says "TORN OR TANGLED at neck (24)": its fold (stand + fall)
      reads as folded edges; a look shows nothing torn. A designed fold is a false alarm there.
    - `rig_audit.fused_limbs` also warns when FINGERS are modelled touching (`DIGIT_AIR` 2 mm, past the first
      phalanx): the troll's are (12 mm radii on axes 18 mm apart: 7.5 mm into each other at the first phalanx, 3.5
      at the second), which is its fused mitten: MODEL, not weights. goblin_anat's fingers have 8-14 mm of air and
      still bleed 0.4: that one is weights (distance weights between thin close chains). The troll's pale patch
      from neck to shoulder is in the maps at rest too (clay is smooth at arm 60): paint / bake, not the skin.
    - `base_quads` skips the head graft for body.source "human" (the "onemesh" agent's fused source: its quads
      hold the head already).
    - The nape on a nod, by numbers (`rig3/nape.py`, `napes.py`): the golfer's collar stands to z 1.565, 0.8 cm under
      the hairline and 6 cm under the Head joint; the floor ran level from the jaw (z ~1.57) and the falloff is long
      (head size here is neck joint -> head top = 34 cm, so `HEAD_FALL` is ~15 cm, not 11), so the nape skin inside
      and just over the collar was Head 0.98. A 25 deg nod about the Head joint swung it 16-28 mm back and 40 mm
      up: 38 vertices came out past the collar's back by up to 8.4 mm, and the hair lifted 4.6 cm off it: the lump.
      (Not hidden skin: it is the skin above the collar's top.) `HEAD_OCCIPUT` 0.1: behind the Head joint the floor
      climbs to the skull's base; Head weight there 0.86, nothing past the collar (-2.9 mm; shared with Neck
      -11.5), bare-human folds unchanged. A higher floor or a shorter nape falloff clears more and folds the bare
      nape (nod p99 17-22, max 40-73 deg). The chin still sinks into the collar on a hard Head-only nod.
    - `parts.<p>.folds = true`: folded by design (a turned collar): counts stay in the quality line, no TORN alarm.
      Set on the collar of dg_fix2 and wb_dg_talk.
    - Kit digits, tried and dropped: making digits exclusive in `rig.weights` (a finger's skin never takes another
      finger's bones) turned the goblin's soft bleed (0.40-0.45, 13-17 vertices, 10 mm) into a few vertices wholly
      on the wrong finger (0.89, 19 mm); limited to past the first phalanx it changed nothing. The bleed sits at the
      knuckles: the anatomy's webs / pads and the first phalanges are handed to ONE finger's rig bone by their
      middle (`rig_weights`), so a neighbour's side skin reads that bone. Next try: webs and pads to the Hand bone,
      then exclusivity.
    - Goblin proof of the guide's rule: `wc2_goblin_fused_vs_clear_arm60.png` (examples/goblin_talk.json exported
      as it is: a torn jagged web under the raised arm; the same with goblin_anat's elbow / wrist + anatomy {}:
      clean). Both Khronos 0 / 0; models `workspace/wc_goblin_talk`, `wc_goblin_talk_clear`.
    - HANDOVER (rig3, 2026-10-06, context full). Exports in /mnt/data/hifipushie/rig3: exp_golfer (final:
      re-exported last with the nape floor + collar folds; check `rig3/queue6.txt` says "golfer3 exit 0" and judge
      `sheets.py dg_fix2 <glb> wc3_golfer nod nod_shared head33` for the nape), exp_talk (wb_dg_talk, decimated
      body + face shapes, final falloff of round 3 before the nape floor: `wc2_talk_strip.png`), exp_talk_wrap
      (`workspace/wc_dg_talk_wrap` = wb_dg_talk + parts.body.topology "wrap": FACE SHAPES ON THE BASE'S OWN QUADS,
      the case s0urc3's Garrett needs; if this note still says so it was NOT judged: log `rig3/exp_talk_wrap.txt`,
      then blink / jawOpen / smile / jaw_head33 sheets; expected trouble: the GNM head's fixed quads carry no mouth
      interior (bag, teeth, tongue are their own parts or missing), the lips' slit isn't re-meshed, `Face.seal`
      and the carry assume a decimated mesh), exp_troll_anat, exp_wc_goblin_talk(_clear). Open, in order: (1) that
      face-shape check; (2) kit digit weights (above); (3) the chin into the collar on a nod, the 9 neck-side
      vertices rigid_near's 8 cm band gives wholly to Head under the collar (talk export: Head leak 69 mm on 9
      vertices); (4) hem bones with the first skirt; (5) a Mixamo clip retargeted in Godot; (6) 15k smile corners;
      (7) the troll's fingers want re-modelling (the tool warns), its pale patch is card cmux1btxc000pk9f23weo12lj.
    - A real engine: `spikes/godot_rig/` (check.gd, sheet.py): Godot 4.7 loads the GLB with its own importer at run
      time, poses the Skeleton3D, drives the twist joints from `<name>.json` `rig.twist` by the recipe, sets face
      shapes, writes PNGs. `godot --path spikes/godot_rig -s check.gd -- x.glb x.json <prefix> poses.json` (opens a
      window for a few seconds). All 79 joints found (colon -> underscore), skin, maps, twist driving and shapes
      work as exported; nothing needed changing. Not checked: a Mixamo clip retargeted, Unity, Unreal.
    - 15k smile (`wc_gnm15k_smile_distances.png`): fine at full-figure distance, the corners kink from a bust
      shot inward; 36k (`wc_talk_smile.png`) is fine. Blink at 36k: closed, a clean line.
  - Regen round (2026-10-07, "regen" agent, branch `worktree-agent-a9a6d594238eb9139`; s0urc3 hand-patched every
    export of Garrett with keep_weights.py + fix_blink.py; renders `rig_renders/rg_*`; export
    /mnt/data/hifipushie/regen/exp_garrett; model `workspace/rg_garrett` = garrett_v20's spec with skin.only ["eyes"];
    scratch DURABLE in /mnt/data/hifipushie/regen/: run.sh <script> (worktree code, main workspace), seatlib.py
    (`game_pose`: s0urc3's seated_pose.json on a GLB's bones; clay rows coloured by part), rs.py + r.sh / g.sh
    (re-skin a GLB's meshes with the code as it is, audit, layers, sheet; RS_SMOOTH / RS_TWO = the old behaviour),
    proof.py (rows of (GLB, weights) with the SAME cameras), blink.py (Garrett's blink on v23's body mesh: under-eye
    measure, rays reaching the eyeball), blinksheet.py, final.py, chk.py / chk2.py / chk3.py (export vs v23), tests.sh).
    - Clothes seated: the cards' diagnosis (lookups alternating thigh / pelvis) was wrong, and so were a kernel
      lookup and a harmonic solve I tried first. Per part NOTHING was wrong (weight steps, stretch, folds read the
      same as the good export). The fault was BETWEEN parts: `WORN_SMOOTH` smoothed each garment over its OWN mesh, so
      two layers 2 mm apart drift (a jacket's hem toward the pelvis above it, the trousers on down the thigh); at 90
      deg of hip the jacket sinks into the trousers where it has less thigh, and the line where two coarse meshes
      cross is the sawtooth. Now `WORN_SMOOTH` 0 (`parts.<p>.rig_smooth` still there) and cloth reads the skin from
      both its faces (`rig_template.from_surface(two_sided=)`, `rig.TWO_SIDED`: what the smoothing papered over on
      collars). `parts.<p>.rig_weights` "surface" | "around" (`rig_template.around_surface`, a kernel average: worse
      for layers, each layer's kernel differs; kept for loose single garments) | "distance".
    - `rig_audit.layers` + `seated` + `layers_text`: vertices of one part lying on another at rest and > 3 mm under
      the same spot posed, per pair, with where; over `LAYER_BAD` 12 is BAD. In the rig tool's text (always, seated),
      `rig(pose="seated")`, the export log (WARNING) and json `rig.layers_seated`. Garrett seated, v23's meshes: old
      code jacket through trousers 18 (20 mm), new 0; weights audit 15 BAD -> 6 (the smoothing was also the leak at
      knees / elbows / feet). Golfer re-skinned: 7 -> 7 BAD, arm leak 18 -> 14 mm, thigh flips 41 / 30 -> 27 / 24.
    - Blink: on a 20k low poly most of the seal's 14 bins hold no margin vertex, so a bin's "highest lower-lid
      vertex" was a cheek vertex 13 mm under the eye, lifted to the lid line. `GnmFace._lid_edge` finds margins by
      their lid's posed envelope (`LID_EDGE`), `_lid_share` fades the correction by distance from the margin
      (`LID_REACH` 9 / 4 mm). `spec.face_shapes.lid_seal` false | amount | {amount, over, band, reach}.
      `faceshapes.unevenness` (a vertex's move outside its edge neighbours' range, per m of edge; tears and the
      blink's own margins left out) in the export log, WARNING over 0.2 for non-mouth shapes (the kit's mouth shapes
      read 0.2-1.6 at the slit's ends by design); json `parts.<p>.face_shape_unevenness`. A gradient or Laplacian
      measure does not separate the fault (a closing lid is steep). s0urc3's under-eye measure on the fresh
      export: 0.18 / 0.25 and 0.16 / 0.26 (faulty 0.41 / 0.73, their repair 0.15 / 0.20).
    - `skin.only` = [groups] (eyes, eye_rims, zones, lips, roughness, micro, features, shading); without "shading"
      `skin.part_base` is None, `_pre` is stripped (ordinary layers) and the part's shading is untouched.
    - Posing with s0urc3's seated_pose.json: twist joints REST ROTATED (+Y along the segment): take the rest
      rotation out of model quats, or thighs collapse to planks (cost me an hour of wrong diagnosis).
    - Found on the way, NOT fixed (main's state, not these cards): (1) a fresh export's meshes are no longer vertex
      for vertex v23's (hidden-face pruning changed since: `_deep_hidden`), so s0urc3's patches could not even be
      applied to it; (2) rig3's long head falloff makes Garrett's neck skin Head 0.70 on average 12-16 cm under the
      Head joint (v23: 0.16), out to |x| 12 cm: in the game's idle and at head 33 the audit reads "body through
      jacket_trim 52-73, body through shirt 40" (v23: 0), and Head 33 leaks 72 mm onto 300 shoulder-owned vertices;
      in clay it is modest (skin at the neckline); (3) this export's low poly has "TORN OR TANGLED at eye_front.L
      (12)": the left upper lid is a few big triangles with a hard vertical edge, a dark crease up the lid in every
      blink (v23's lid is smoother); the right eye has a small dark notch at the outer corner in a full blink.
  - `rig` tool: `glb=` judges an exported GLB (its mesh, joints, weights), `pose={}` = rest, `focus` / `zoom` /
    `views`, `shapes`; warns when the look's voxel is too big for the fingers; prints the audit.
    `tests/test_rig_audit.py`.
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
  with radii kept (`_skeleton_warp(girth=)`; FK rotations, hands from a palm fit, see below), Catmull-Clark'd, and becomes one primitive (kind "base", first in the
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
  Hands in the warp (2026-10-03, s0urc3's Garrett: "those fingers are terrible"): MakeHuman rests with the forearm
  bent; an A-pose turns the whole hand ~0.3 m. Per-bone minimal-arc rotations gave each finger bone a different roll
  and the Gaussian blend averaged them across every joint (bulging knuckles, grooves, a thumb ring, nails cut in, up
  to 14-18 mm off), and a girth R1 was read at the target frame's angle (`off`), stretching flat fingers. Now
  `retopo._hand_rotations`: the hand's rotation = Kabsch of its palm joints (wrist, digit roots), each digit bone =
  parent's composed with the minimal arc from the parent-carried axis (FK, consistent roll), no `off` for a girth R1;
  past the template's wrist (`HAND_BLEND` 3 cm ramp, and only where the arm's bones carry the point: the thigh beside
  a hanging hand keeps the warp) the hand's bones only, blended tighter (`HAND_SIGMA` 0.5). Joints that keep the
  template's hand pose -> one rigid move (Garrett: 0.1 mm of the Kabsch-moved MakeHuman hand); curled fingers bend
  at their joints. `tests/test_handwarp.py`.
  The rest of the body (2026-10-03, base.VERSION 60; director: "we have to fix the warping issue, too"): the same
  causes outside the hands left Garrett's base up to 13 mm L/R asymmetric (right shoulder, chest) and twisted at
  elbows/wrists. Now `retopo._body_rotations`: rigid fits where several bones start (`FITS`: pelvis + hips + chest
  joints, chest + neck + shoulders; each palm) and FK down every chain (parent's rotation + the minimal arc to the
  bone's target: consistent roll); a bone ending at a fit (forearm -> palm, spine -> chest) twists into the fit's roll
  along its length (`_twist`, applied in `carry`; Garrett's forearms 7.6 deg) instead of the wrist taking it all; no
  `off` for any girth radius lookup (R1 is the template's own). The blend: related bones (a shared joint, or one
  starts at a fit whose root joint the other has: thighs relate to the spine, not to each other) blend over the full
  width (sigma 0.8 x distance), others over `FAR_SIGMA` 0.35 of it, the width chosen by a soft nearest bone
  (`NEAR_SOFT`) so weights stay continuous (the neck's base had been pulled 2-12 mm by an arm raise, an inner thigh
  14 mm by the other leg). Narrowing sigma itself (0.6, 0.5) creased bent elbows/knees more than it helped: kept.
  Garrett: asymmetry 13.3 -> 0.0 mm; bumpiness (vs the template) shoulder 1.17 -> 1.00, elbow 1.07 -> 1.03, wrist 1.09
  -> 1.01, neck 1.05 -> 1.00; up to 15 mm moved (the right side onto the left's mirror); face (GNM graft) unchanged.
  A spec in the template's pose gives it back; a rigidly moved skeleton gives a rigidly moved body (0.000 mm).
  `tests/test_bodywarp.py` (symmetry, rest/rigid, joint bumpiness, unrelated bones; MakeHuman when its pack is
  present). Known: bending an elbow further than the template's rest still creases like any linear blend (x1.16
  bumpiness at +35 deg on MakeHuman, the same before). The wrap path (no girth) gets the FK rotations and twist but keeps the
  full-width blend for all bones: with FAR_SIGMA its untangle left ~7% more turned faces (goblin_anat, troll_anat);
  as merged, 1215 / 1781 turned faces vs 1185 / 1725 before (+3%), misses and field error unchanged.
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
  Head shape (`base.head.shape`, or `base.style.shape` in a sheet; 2026-09-30, the golfer's face toward the
  reference): `planes` (each 2 mm horizontal section in front of the jaw contour moved onto a superellipse of that
  exponent in its ellipse's normalised coordinates: a tighter front/side corner at temple, cheekbone and jaw; the eyes
  held by `planes_hold_eyes`, or the interocular grew 7%), `under_eye` / `nostrils` (weighted shrinking Laplacian:
  the crease filled, the openings closed), `push` (landmark-addressed Gaussian bumps, mirrored, along the normals or
  a world `dir`: along the normals a muzzle push opened the mouth, the lip seam faces up/down); the landmarks ride
  the pushes (left behind, the lip outlines and mouth fill broke the mouth). `plane_measures` (corner radius, muzzle)
  feeds `style_check`. The proportions were already within ~5% of the reference: the "moon" read was round planes,
  a muzzle, full lower cheeks, sleepy lids and paint. `base.look_at` off the centre line sets `eye_front.R` too; a
  near look_at reads cross-eyed, use a far point. Fast clay iteration of head shapes: build `base.head_of` alone and
  render the mesh (~10 s; a painted face look needs a sync, 4+ min on a head-cropped copy).
  Nose and chin (2026-09-30, renders n01-n05): `base.head.regions` = GNM identity components applied only inside a
  feathered region group (`region_weight`) or a landmark bump (`near`), so one feature is reshaped without moving the
  eyes or jaw. Fitted by least squares to 3D targets (ala width, nasolabial angle, tip projection, chin forward/up/
  narrower, mentolabial fold, under-chin sag), reading the targets off the reference through two matched cameras
  (near + the far figure). Fitting 2D silhouette chamfers directly made a noisy objective and odd noses: fit smooth 3D
  measures and check them in 2D. `shape.push_more` adds a model's bumps to the sheet's (a model's `push` replaces the
  sheet's list); a push `dir` now mirrors its x on the mirrored side. Pushes near the nostrils are mostly smoothed
  away by `shape.nostrils`; small chin pushes read as a chin "button" under stubble, and jaw-narrowing pushes cut
  marionette grooves (use regions). The user's rule (2026-09-30): the reference wins, so a sheet rule the reference
  itself would fail is wrong. Rules are banded on the reference's own values, each image ratio carried to 3D by the
  model's own 3D/image ratio in the same camera: `ala_width` (`base.ala_width`, the outer wings; it replaced
  `nose_width` = lm31-35, the nostril base, which blocked narrowing the wings), `chin_over_philtrum`, `muzzle_mm` (not
  measurable without a profile). `_planes` (the superellipse push) acts on the features' own sides too: it boxed
  the nose and flattened the lips and chin into slabs. It now keeps `PLANES_KEEP` (nose feathered 10, lips+chin 30:
  at 10 the kept muzzle met the pushed cheek in a smile-fold crease), `shape.planes_keep_features`. The user's "flat,
  sliced-off nose" in the dg_face renders was that head-only copy's `face_crop` box (front face 19 mm behind the nose
  tip), not the head: widen a crop to y size 0.22 before judging a nose.
  Face finish + the whole golfer (2026-09-30, renders g01-g0x, model `workspace/dg_full` = full body + face + dg_hh's
  hand-shaped locks; `examples/disc_golfer_style.json` (on the sheet) / `disc_golfer_mh.json` (resolved)): jowl in
  (a normal push on the jaw ahead of lm12: the far jaw outline in the matched view is the jowl at mouth height, not the
  jaw contour), mouth down 4 mm by `pose.mouth_raise` -0.004 (nose-to-mouth 0.30 -> 0.38 io), chin block (corner pushes).
  Eyes: `base.eye_size` (lid landmarks from the front / interocular) and sheet rules `eye_w_over_io`, `eye_h_over_io`
  banded on the reference (0.69 / 0.22-0.24 io; we had 0.18 high: "sleepy"). Brows: traced in both reference figures
  (`workspace/dg_nose/brow_trace.json`), carried onto the head through the matched cameras (four traces agreed on ~9 mm
  thickness), painted as an `outline` layer from the brow landmarks (`brows_top.L` + a softer `brows_soft.L`; the
  sheet's `brows.L` off: its later warm overlays washed a model's brow layer to a thin line, card filed). Under-eye:
  `shape.push_late` = pushes applied AFTER the `under_eye`/`nostrils` smoothing (which erased pushes in its region):
  the upper cheek filled under the lower lid (section hollow 1.43 -> 0.58 mm); the dark ring was that slope, not paint.
  `base.head.mouth_gap` closes (or opens) the lips (least change of GNM's lower-face components); a closed mouth's
  cavity is filled (base.inject): left open it was an outside pocket in the head that the wrap projected into.
  Closed lips are zipped in the head mesh itself (`base._zip_lips`, 2026-09-30): the rings from the skin's open mouth
  loop to the contact ring (`LIP_RING` 2, where lm 61-63/65-67 sit) dropped, the contact ring's halves welded. The
  inner lip rolls had left sealed air pockets behind the lips and a slot: the export's low poly and its bake fell in
  (a dark jagged slit with flecks, g08c). Now the field is solid with a ~0.5 mm groove, the wrap's seam is that edge
  loop (`graft_head` skips `_zip_mouth`), `head["skin_index"]` maps GNM skin indices past the dropped vertices.
  Export vs look (same day, renders x01-x05): rendered with the same camera, suns, world and engine (EEVEE), the
  export's skin and stubble match the scene (chin HSV equal, contrast within 4%); the "grey stubble" was the old
  preview (grey world, other lights) plus 1.1 mm texels under 1 mm stubble noise: `parts.body.texel_focus` on the
  face (2.5x: 0.5 mm). `asset.preview(lighting=)` / export_asset's preview now use the model's style look.
  Golfer fix (2026-10-01, renders g10-g14, model `workspace/dg_fix2`): the exported hair read near-black in EEVEE
  because the lock profile (unit circle with x/y swapped: a mirror) made Curve to Mesh wind every face inward; the
  glTF importer (and engines) cull back faces on a single-sided material, so EEVEE drew each lens's dark underside.
  A Flip Faces node fixes it (GLB vs look on the same hair pixels: V -59% -> +4%). Rebuilding the node group (a
  VERSION bump) used to reset every lock's modifier inputs (width 0, which the next pull wrote into the spec):
  `node_group` now keeps them. Skin was dark because AgX rolls lit skin off at V ~0.8 whatever its paint: the
  sheet's look is now `view` "Khronos PBR Neutral" (what glTF viewers use), look None, exposure -0.5; skin
  #e4ae86, key light moved to his left as in the reference, a pink-neutral fill; measured through the matched face
  camera at landmark points (lit h/s/V 19.7/0.455/0.946 vs the reference 18.9/0.448/0.926, shadow/lit V 0.82 vs
  0.87, GLB = look within 0.001). Rules `skin_val_lit`, `skin_val_shadow_over_lit` (shadow samples follow the key's
  side, `stylesheet.skin_samples`). Chin: regions fitted (linearised with `zip_lips` off: the zip changes the vertex
  count) to a narrower jowl and wider chin corners at the far figure's length (chin_over_philtrum 1.84); the near
  figure's open mouth biases its lip-to-chin length, so don't fit chin length to it.
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
  Export (`hair.export_part`, called by `asset._export` when the spec has locks): the locks at 24 x 10 (`hair.EXPORT`,
  `spec.hair.export` overrides; 12 x 8 read faceted and dark in Cycles: the thin lens edges shaded as flat planes) + the underlayer
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
  Hand-shaping (2026-09-30, the user's call after the procedural rounds: "hand shape the front locks in blender"; model
  `workspace/dg_hh`, a copy of dg_hair2, renders hh01-hh04): edit the curves in scene.blend (a live session: the person's
  Blender, or `blender -b scene.blend --online-mode --command blender_mcp --port N` + BLENDER_MCP_PORT=N), then
  `scene.pull`. Every lock edited there comes back with `"hand": true`; curves added to the "hair" collection (Shift+D
  on a lock, or a new Bezier curve) come back as new locks (tier "hand", named by their object); deleted ones leave the
  spec and are listed in `hair.removed`. `hair.groom` (regrow) keeps hand locks and never regrows a removed name; the
  sync records the locks it made (collection prop `hp_made`) so deletions are seen; a live pull re-syncs the edited
  locks (`scene._restamp_hair`: stamped with the old hash, the next edit of the same lock read as stale). What worked:
  few BROAD locks (7-10 cm wide, 6 mm thick, thin edges `edge` 1.6) lying on the volume (h = volume - 2 mm, tilt =
  `lie_tilt` smoothed along the lock, the root's tilt = the next point's: the volume's normal turns sideways at the
  parting and roots stood as fins), a top fan from the part whose rows never cross (slerp arcs, an under-row between
  each pair where the fan spreads), sides/back as ~8 broad locks brushed back to the nape (the procedural strips and gap
  locks read as tiles and shingles on edge), sideburn, nape and behind-ear locks for coverage. The groom's volume still
  shapes the silhouette: `volume.ramp` (0.028 default: the front a wall the front locks jutted over like a cap's peak;
  0.06 leans it back), `volume.across`, `parting.depth` (0.45: the roots stopped climbing out of a trench). Dents in
  the gate: find the lock that makes each height of the outline (`hair_point_owners.npz`) and pull it out 2-4 mm.
  Hair through MCP (2026-10-01; the user: another LLM consuming hifipushie over MCP couldn't do hair at all): tools
  `groom_hair` (groom patch deep-merged, null deletes, then regrow; hand locks kept), `look_hair` (sheet + layout +
  gates as text, incl. `hair.hierarchy`: area share by lock width vs the artists' 6-3-1, width spread), `hair_reference`
  (store the trace, fit the camera from its landmarks, `apply` = from_trace into the groom), `sync(hair_only=True)`
  (pull, then hair.sync); `edit_model` takes dotted kinds ("hair.locks", "hair.groom") and a hair-only edit validates
  only the hair (a base body recompile was ~1 min). `guide(topic="hair")` = `hair_guide.md`: the artists' workflow
  with sources (silhouette volume, big drawn shapes with a size hierarchy, sides/back as drawn ROWS of broad blunt
  locks, a light breakup, material) for the tools. Found doing it through the tools (renders hair_t01-t13): under
  clumps sank 1 x thickness, i.e. under the underlayer, so the volume showed between every pair of wedge tips (now
  `drawn_under` sink 0.35, per row); unders across az 180 averaged through the front (a lock over the face); the
  generated strip/gap tiers read as tiles and a mop (t13: 47 drawn locks in rows, no tiers, back bare 0.07).
  Silhouette round (2026-10-02, model `workspace/hair_vol`, renders hv01_*/hv02_*):
  - `trace.views` adds matched views: another figure in the same picture shares the lens (`fit_camera(focal=)`;
    with a free focal it ran off to orthographic). They are stored in `ref_cameras.json` and listed by
    `hair.ref_views`; each gets a matched row and its own fit.
  - `outline_regions`: on rays from the head centre in each matched view, the outline per head region (labelled by
    the volume point that makes the outline there), ours vs the reference vs the bare head, in mm; plus
    `over_brow_mm`.
  - A face-only camera fit left the cranium's pitch loose: the bare skull already reached the reference's hair top.
    One ear-side landmark (`lm_jaw_0.R`) fixed it.
  - The golfer's hair was 10-14 mm TOO TALL and too full on the swept side, not flat. New `volume.crest` and
    `volume.taper`. IoU near 0.73 -> 0.76, far 0.75 -> 0.84 (mass), 0.74 / 0.86 with locks.
  - The flakes along the part were roots twisting and climbing. lie_tilt at a root came out ~100 deg off the next
    point (now the root takes the next point's tilt, and |tilt| <= `TILT_MAX`), and roots were sent to the scalp
    under a 2 cm volume (now they dive just under the underlayer).
  - `hair.folds` (look_hair "folded locks"): in-plane bend x half width >= 1. `ease_bends` on drawn paths.
    `look_hair(only=)` isolates locks.
  Hairline round (2026-10-02, model `workspace/hair_r3` = copy of hair_vol, renders hr00-hr04; guide 3b/3c): new
  look_hair numbers per matched view: `front_edge` (rendered edge along the traced hairline: rough_mm vs its running
  median, tooth_mm, teeth by lock), `front_flow` (strand angle to the hairline, structure tensor on the reference and
  our render; the golfer's reference reads 10-30 deg, a shallow diagonal), `bare_where` (bare pixels by head region,
  "hairline" = within 15 mm), `fins`, `root_ends` (blunt cut ends). Fixes: cap rows follow the hairline (a 1 deg
  grid serrated the rim), traced front_points ease onto the default line (`HAIRLINE_JOIN`), `parting.front`,
  `volume.edge_sink`, drawn `to_hairline` / groom `hairline_edge`, `root` + `climb` (narrow roots growing out of the
  layer: full-width roots read as scales along the hairline and crescent fins at the part), roots past the hairline
  buried in the skin, ROOT_TILT (nape fold flags were the root's climb in a tilted lens), drawn clumps patched by name.
  hair_vol -> hr04: edge rough/tooth 1.21/6.4 -> 0.54/2.0, bare front 0.176 -> 0.095, direction err 25.5 -> 19.8 deg,
  hierarchy 0.8/0.2/0 -> 0.64/0.27/0.09, folds 7 -> 2. Open: the part-side temple corner's direction (ours ~80 deg vs
  15-40), sideR1's root fin on the swept side, 3-way nape splits read as a comb from behind.
  Drawn
  clumps take `"split"` (`split_tips`: tip into n narrower locks fanned apart, the clump tapering out under them, held
  inside the hairline); look keys `band_shift` (each lock's sheen band slides along it) and `tip`/`tip_amount`. The
  look's reference image is the trace's own (no golfer default).
  Soft, loose hair (2026-10-05, "hair cards" agent, branch worktree-agent-aff168a4b06a3ed59; cards s0urc3's Tess:
  plates, hard hairline, stiff one-sided tail; renders `workspace/hair_renders/hc_*`, references
  `workspace/hair_refs/` (CC photos + CC-BY Sketchfab card models, refs.json; `ponytail_right.jpg` is the target look);
  guide part "Hair: soft, loose hair as strand cards" with the artists' method and sources). STATE: two spikes, a
  decision pending with the user (Blender's hair system vs our cards); nothing is wired into MCP, tests or docs yet.
  - Built (numpy, works in look_hair's pipeline): `hair.style: "cards"` (default "locks": untouched path, but NOT yet
    checked bit-for-bit) realises every lock as layered cards (`hair_cards.py`: `atlas` = generated strand atlas, 10
    tiles dense/medium/sparse/hairline/fly/baby/band with colour+alpha, normal, aux root/id/depth/alpha; `spine` /
    `frames` / `_lock_cards` / `mesh` / `fit_budget` / `join`), `hair.strands` numbers (wave, wavelength, curl, random,
    clump, frizz, flyaway, layers, card_width, tips, baby, soft, round), the underlayer as a hair cap wearing the
    hairline tile (`hair.card_cap`), baby hairs (`hair.baby_locks`), `blender_hair.card_material/card_object` (dithered
    alpha, bent custom normals, id pass and clay for cards), tied hair `groom.tie` (`hair_tied.py`: gather rows to a
    tie point, tail round a core line under gravity, coil = bun, plait, escape strands, a band mesh), locks that leave
    the head (`"space": "xyz"`, `free`, `core`; `hair.lock_world` / `lock_address`; pull writes them back in their
    space), solid locks' `Free` input (node group VERSION 11: a hanging lock's underside is lit), `hair.export_cards`
    + asset.py COLOR_0 / alpha MASK / extras (WRITTEN, NEVER RUN).
  - Blender's own hair, spiked on the user's question (scratch scripts kept in `spikes/hair_strands/`: strands.py +
    bl_strands.py, atlas_bake.py + bl_atlas.py, look.py, tess.py, refs.py): our locks' spines as guides of a Hair
    Curves object + the Essentials node groups loaded headless from
    `<blender>/5.1/datafiles/assets/nodes/procedural_hair_node_assets.blend` (Duplicate, Clump, Curl, Frizz, Noise,
    Shrinkwrap, Set Hair Curve Profile; Braid has a hair-tie input; Interpolate needs a surface UV map: not tried),
    Principled Hair BSDF. Works headless with no fuss. Cycles strands are far the best LOOK (hc_12: tess's scalp hair
    and hairline read as real hair; hc_13: the golfer as realistic combed hair): 42k strands / 1.9M points, ~20-25 s
    a 640 px frame on the laptop's CPU, evaluation < 1 s. EEVEE draws the hair BSDF near black (needs its own
    material) at ~8 s a frame. Settings are touchy: frizz / noise distances of 2-4 mm made a cloud (0.2-0.4 mm is
    right), Clump at 0.15-0.35 collapses every guide's strands into a round ROPE (dreadlocks), 0 gives the soft mass.
    A lock as a broad FLAT clump (the golfer's sculpted look) is not one Essentials setting: Duplicate spreads
    radially; it needs our own lens-shaped child distribution or guides per clump edge. The golfer as strands is
    bigger and softer than his reference (IoU 0.57 vs 0.63 cards, ~0.74 locks) and has no distinct clumps.
  - "Volumised" strands (points -> volume -> mesh, 2 mm voxels, decimated 379k -> 12k): a lumpy blob / shower cap
    (hc_13 lower row). As tried it fails; no source for the remembered production pipeline was found in one search.
  - Atlas baked from Blender strand clumps (bl_atlas.py, Cycles, 10 s): works; first try has too little coverage in
    the dense tile, no ragged tips, lit colour baked in (hc_15: scalp shows through). Needs tuning + id/depth/root
    passes; then it replaces `hair_cards.atlas`'s drawing, the card mesh / budget / export code stays.
  - Recommended to the coordinator (not yet agreed): groom + look = Blender Hair Curves with our locks as guides
    (Cycles strands as the truthful look and the video path); game path = our card mesh from the same guides with
    an atlas baked from those strands; stylised solid locks stay as they are.
  - Open, in order, whatever is decided: the grey band / hard arc at tess's forehead (on the old dark-skin stage it
    was skin's shaved-scalp paint; hc_tess was re-synced without it, not re-judged with numpy cards), scalp gather
    coverage holes above the ear, tail collision with neck / shoulders (only the head's rays are used), export never
    run, bit-for-bit check of style "locks", MCP tools (groom_hair docs for tie / strands, look_hair numbers:
    triangles, hairline softness), tests, guide workflow section.
  Strand grooms (2026-10-05, "hair2" agent, branch `hair2` from the cards branch + main; decided with the user: the
  groom and the look move onto Blender's Hair Curves; renders `workspace/hair_renders/hs_*`; models `hs_tess` (copy of
  hc_tess, tied wavy groom) and `hs_golfer` (copy of hc_golfer); scratch scripts kept in `spikes/hair_strands/hs2/`:
  run.sh <script>, look.py (a look with overrides, HS_SKIP=Noise,Frizz drops modifiers), mk_tess.py, tiers.py
  (strands + every card tier in one sheet), atlas.py, export.py, golfer.py (locks | strands with gates), cmp_locks.py,
  v.mjs (Khronos)). STATE: WIP, stopped by the session's usage limit; no tests, no MCP wiring, no guide workflow yet.
  - `hair.style: "strands"` (`hair_strands.py` + `blender_strands.py`): the spec's locks are GUIDES. `hair_guides` /
    `hair_guides_free` = one Hair Curves curve a lock with per-point `hp_side` / `hp_out` (the lock's half width and
    half thickness as vectors) and per-curve hp_n (strands / 8), hp_k (sub clumps = width / clump_size), hp_fd
    (fly-away reach <= 0.8 x width), hp_rs (root stagger x4 on locks rooted at the hairline), hp_ts. Children come
    from OUR node group `hp_lens` (VERSION 9), not Essentials Duplicate (radial = the ropes): each copy is placed in
    the lock's lens section, drawn toward its sub clump's line by Clump x t^(0.35 + 2.65 x Clump Shape), let go again
    at the tip (Tip Spread), each sub clump swings on its own phase (Wave / Wavelength / Curl), single strands wander
    (Loose), some let go (Flyaway), every strand has its own start and end (Roots, Tips). It stores hp_sub, hp_cv (a
    value per sub clump: the material's streaks), hp_rand. Then Essentials Hair Curves Noise + Frizz (Cumulative
    Offset OFF: on, thin locks fanned out), Shrinkwrap, Set Hair Curve Profile. `hair_under` = the scalp layer: flow
    guides seeded every 11 mm inside the hairline (direction = the nearest lock spines laid in the scalp's tangent
    plane, rising to just under them; baby-hair seeds on the line), children by Essentials "Interpolate Hair Curves"
    on `hair_scalp` (a mesh of the scalp with UV = azimuth / elevation and `hp_density` = hairline fade x parting).
    `hair_scalp` also renders a dark tint by density (`look.scalp_tint` 0.85): without it 30k strands showed skin.
  - `hair.strands` (hair_cards.STRANDS) holds the dials, 0..1 mapped onto safe ranges in `hair_strands.physical` /
    `SAFE` (frizz <= 0.6 mm, coherent noise <= 6 mm, fly-aways <= 12% of strands, tips lose <= 55%): count, thickness,
    clump, clump_size, clump_shape, tip_spread, loose, roots, under, under_length, flat, wave, wavelength, curl,
    frizz, flyaway, tips, source.
  - COST: Essentials Shrinkwrap against the body mesh took 70-250 s a look; against `hair_collide` (the head, neck
    and shoulders as the scalp's rays see them, ~8k triangles) the whole look is 10-25 s in EEVEE at 30k strands.
    Curl Hair Curves subdivides x4 (dropped: the lens group's Wave/Curl does it).
  - `hair_tied`: escaped strands fall down the cheek (they left the head at 45 deg: tufts), 6-14 mm wide.
    `groom.parting.side` defaults to "left": a tied groom needs `"none"` or the cap and scalp density get a part cut.
    Thin free locks (< 16 mm) keep their point, get few strands and less wave; a tail's locks are x1.5 wide and
    round in section (flat ribbons twisted like bacon), lock phases nearly in step (random phases = pasta).
  - Game path (design a-g agreed with the coordinator after research; see hair_guide.md's last section):
    `hair_strands.evaluate` builds a strands job in an empty Blender scene and dumps every strand (mode
    `hair_strands_eval`; `strands_of_model` caches it in `<HOME>/_cache/hair_strands`). The card atlas's tiles are
    now the groom's own strands: `tile_job` = one flat guide lock a tile (dense .. baby) through the same lens group
    and numbers, `tile_lines` -> `hair_cards._tile(lines=)` (the drawn generator is `_drawn_lines`, `strands.source:
    "drawn"`); rasterised in numpy/PIL (alpha, id, depth, root; NOT a Cycles bake: say so). The atlas is 2 : 1: the
    right half is the SCALP CHART (`cap_chart`: every strand close over the scalp drawn where it lies over an opaque
    base that starts `soft` inside the hairline); `hair.card_cap` maps the cap mesh onto it (seam vertices doubled)
    and the cap is lifted 2 mm + its sagitta. `hair.CARD_TIERS` hero 40k / main 16k / npc 6k / far 1.5k (layers,
    card width, segment, cap step); `hair_cards.fit_budget` now drops cards one by one by `prio` (it dropped whole
    layers). `hair.export_hair(name, out, tiers)` -> `<name>_hair_<tier>.glb` (one atlas, MASK, two-sided,
    anisotropy + sheen, extras.hifipushie_hair with the recipe and layer ranges) + `<name>_groom.abc` / `.usda`.
    RUN on hs_tess: /mnt/data/hifipushie/hair2/tess_export, 78 s for four tiers, Khronos 0 errors 0 warnings
    (39,994 / 15,994 / 5,974 / 1,478 triangles). `hair.export_part` sends style "strands" through the cards too.
  - Groom export, tested (spikes/hair_strands/bl_groom_export.py): Blender 5.1's Alembic writer keeps curves, widths
    and the object's custom properties (groom_version_*) but DROPS per-curve / per-point attributes; its USD writer
    keeps them all as primvars. So the .abc is the minimum Unreal imports (guides, ids, root uv = importer defaults);
    the full schema would need pyalembic.
  - Style "locks" is unchanged: hs_golfer's look rendered with main's src and with this branch's is pixel-identical
    (max diff 0 over three views; cmp_locks.py). The job dict gained keys (free, strands, core, new look defaults).
  - The golfer as strands (hs_14_golfer_locks_vs_strands.png, NOT yet looked at by me: judge it first): IoU 0.597
    vs locks 0.624, bare 0.06 vs 0.107, silhouette gate FAILS (front 4.1 / 6.6 mm vs 1.3 / 1.4; hairline edge rough
    0.88 mm / tooth 5.3 vs 0.29 / 1.4) with clump 0.9, clump_size 12 mm, shape 0.3, flat 1.6. No recommendation yet.
  - READ so far (EEVEE only; the user called the spike's strands "kind of ok"): hs_12_tess_tiers.png = strands over
    hero / main / npc / far. Strands: reads as a ponytail with a loose wavy tail, no ropes, soft face wisps; still
    crimped wisps, clumps a bit pasta-like in the tail, strands at the temples stand off in arcs. Cards: hairline
    and cap read (no skin through, the far tier is a helmet with real flow); cards are much darker than the strand
    look (two materials, unreconciled), tails thin out to wisps at npc / far.
  - NOT DONE, in order: (1) a Cycles look: every attempt waited 30+ min on `resources.heavy` behind exports and
    cloth sims and was cancelled; needed for the before/after on "kind of ok" (count, taper, hair BSDF, rim light)
    and to settle the card-vs-strand colour; (2) the first sheet to the coordinator: Tess strands beside
    ponytail_right.jpg + the tier sheet; (3) judge the golfer sheet, recommend on migrating stylised hair; (4) one
    per-clump volumise try, then close it in the guide (research found nothing documented; Sprite Fright's hair
    meshes were sculpted by hand); (5) round trip: `blender_strands.read` exists (moved guides by stamp, stack
    numbers) but nothing in hair.py / scene.pull consumes it, and hair.sync was not run with strands; (6) look_hair
    numbers for strands (coverage = id pass red share is there; hairline softness in mm, IoU on tied hair not);
    (7) MCP tools (groom_hair / look_hair docs for strands + tie, an export_hair tool), guide workflow section for
    strands, tests (none exist for hair), GLB preview render of each tier, usdc instead of 32 MB usda; (8) Braid
    node for plaits, tail collision beyond the proxy, baby tile nearly empty (coverage 0.06).
  Hair 3 (2026-10-06, "hair3" agent, branch `hair3` = hair2 + main; renders `workspace/hair_renders/ht_*`, exports
  /mnt/data/hifipushie/hair3/tess_export_v*, scratch in `spikes/hair_strands/hs3/`: run.sh <script>, var.py (rows of
  spec variants), iso.py (what makes a pattern in a tier), diag.py (export + check_tiers), pair.py (GLBs side by
  side, alpha test / dither), dist.py (tiers at their distances), clear.py (cards under the skin), tools.py (the MCP
  tools called directly), cmp_locks.py, groom_check.py (Alembic / USD read back), regroom.py; Khronos validator in
  /mnt/data/hifipushie/hair3/val). The user on hs_12: the strand look "is looking really good", the game export
  "seems to get corrupted"; so this round was the card path. Supersedes the hair2 notes above where they differ.
  - Cycles strand look works (87-270 s): three causes of the pale haze it was: `hair_strands.STRAND_RADIUS` is now
    a real hair (0.04 mm) at `REAL_COUNT` 100k, wider by (100k / count)^0.8 (EEVEE draws >= 1 px, a path tracer the
    true width); `hair_bounces` 10 (render() cut transmission at 2); lights `hair.LIGHTS["salon"]` (key, fill, rim;
    default for strands / cards, `look.light`; locks keep the stage's sun). Own `hp_profile` group for the radius
    (root, taper to the tip: `strands.taper`). Cycles reads lighter and more ginger than EEVEE: not reconciled.
  - Pasta and crimp: sub clumps swing nearly in step (`Wave Random` = strands.random; they were on random phases
    and wavelengths, and at 3x the lock's own amplitude: `SAFE["sub_wave"]` 0.25), `strands.stray` (strands that
    only half join their clump fill between clumps), per-curve `hp_ws` / `hp_wl` (a wisp swings less and slower).
    Gather locks (`hair_strands.is_gather`: name t<i>g<row>_<n>) narrow into the tie and are not tip-trimmed.
    Lens group VERSION 10. Wisps root 8 mm inside the hairline (`hair_tied`: at 2.5 deg they rooted on skin).
  - DIAGNOSIS of the "corrupted" tiers (ht_01, ht_02): not the atlas, UVs, normals or colour space. (1) baby-hair
    cards under an alpha TEST = brown stamps; (2) the tail a lattice of thin ribbons on separate phases, no opaque
    base; (3) fixed costs (cap, baby, tie) ate 22-68% of a tier and lower tiers were the same thin cards thinned
    out; (4) shade applied twice (atlas depth AND vertex colour x0.6 on layer 0: the dark band above the forehead,
    with every upper card starting 2 cm behind the line); (5) the budget stretched every hero card to 3 cm segments.
  - Cards are cut from the STRANDS now (`hair_cards.strand_grid` / `_clump` / `clump_cards`): strands resampled on
    a common grid of their lock's parameter (NaN outside each strand's own start / end), clustered by tier key
    `group` ("sub" = the groom's sub clumps, "pair", "lock", "free" = only hair off the head), a card's centre = the
    clump's mean, width = 2.5 x its spread (cards overlap a third: where they only met, every seam was a shadow
    slit), wide clumps cut across into slices by strand; frame carried on where "outward" degenerates (cards stood
    on edge round the tie). Layers: 0 dense (hairline tile at the line), 1 the hairline tile again (its roots come
    in one by one: staggered roots on the dense tile drew brick lines under an alpha test), 2 medium, outlier
    strands = fly cards (hero). Wisps (free lock < 16 mm): 2-3 thin cards on the fly tile (a few THICK hairs, 3
    texels, root at full strength, no depth shade). `tail_cores` + `core_mesh`: a solid surface in a tied tail from
    the strands' radial extent per station / direction (layer -1 like the cap). `hair.CARD_TIERS` hero / main /
    npc / far: group sub / pair / lock / free, card_width 12 / 20 / 28 / 70 mm, far's cap = the groom's volume
    (`cap: "mass"`, eased up from the line). `fit_budget`: segment x1.5 at most, then cards by `prio` (fly, baby,
    top layers first; coverage last). Old lock-cut cards remain for `strands.source: "drawn"`.
  - One shade: atlas colour = gap -> lit by depth (0.45 + 0.55 d) x a value per strand (x3 vary) x `look.card_gain`;
    vertex colour = root-tip ramp x per lock / card value only. Card material and GLB: roughness >= 0.5, specular
    halved and tinted to `look.sheen` (KHR_materials_specular without the texture; a card mirrored the rim light
    as a white plate). Tiles (`hair_strands.TILE_KIND`): medium / sparse roots staggered over the first quarter,
    baby = 4-6 hairs with empty margins, fly / baby lines >= 1 texel and faded before every quad border.
  - `hair.card_clearance` (in every cards job): vertices under the skin (the head as the scalp's rays see it)
    counted by lock, then moved out to `CARD_CLEAR` 1.5 mm; `detached` = free cards whose root lies outside the
    hairline. Measured on Tess: 0 hero vertices under the skin (11-12 gather vertices <= 2.7 mm at main / npc);
    the wisps "starting on skin" were roots faded by alpha + two rooted 3.7 mm outside the line.
  - Tooling (what found all of the above): `hair.look_glb` (a GLB re-imported by Blender's glTF importer on the
    head stage; alpha "test" | "dither" | "off"; `dist`), `hair.look(debug=)` "layers" | "cap_only" | "cards_only"
    | "no_normal" | "unlit", `hair.check_tiers` + `tiers_text` (sheet, table, WARNINGs), `hair_checks.py` (iou /
    bare / value / sat vs the strands, `stamps` = detached rectangular blobs, `straight_share` = plank edges,
    `mesh_verdict`). MCP: `export_hair` (new; check=True, save=sheet), `look_hair(tier=, debug=, engine=)`,
    `groom_hair(style=, strands=, look=)` + tie in its docs; guide section "Strand grooms through the tools".
    `tests/test_hair_strands.py` (9 tests; the last exports npc through Blender on hs_tess).
  - Tess after (export v8; ht_07 / ht_09 / ht_10 sheets): 39,986 / 15,990 / 5,984 / 1,468 triangles, 94 s for four
    tiers + groom; Khronos 0 errors 0 warnings (infos: the unused specular texture). bare vs strands (alpha test)
    hero 6-21%, main 7-24%, npc 8-28%, far 13-50% (front views: face wisps and the strands' fringe); value x strands
    0.89-1.05 (back view 0.78: strands glow under the rim, cards don't transmit), sat 1.0-1.2; stamps 0. Groom read
    back by Blender: 29,977 curves / 489,076 points; .abc in cm (position, radius), .usdc in m with groom_* (10 MB;
    the .usda was 33).
  - Style "locks" unchanged: hs_golfer's look with this branch vs main's src differs by <= 1 level on 2-11 of 1.57M
    pixels, and main against itself by 9 (EEVEE's own run-to-run noise); same code twice can also be identical.
  - Cycles colour, one more data point (ht_t_cyc3.png: flat light | salon without denoise | vary 0.2 + no tip
    colour): the strands read light ginger-blond in ALL three, so it is neither the rim light nor the per-strand
    value: the hair BSDF's colour itself comes out ~2x lighter than `look.lit` (#5c3b28, dark brown) and than EEVEE.
    Next step: calibrate the BSDF colour (a gain, or melanin) against lit by measurement. Without the denoiser
    (200 samples) strands keep their grain; with it the mass goes waxy. The three renders waited 19 min, 107 min and
    8 min for the heavy slot: queue Cycles looks and do other work.
  - Volumise, tried once and CLOSED (volumise.py, ht_12): Points to Volume -> Volume to Mesh per sub clump of the
    tail = 3.6M triangles in 45 s, rows of beads, no strand detail; written up in the guide. Stylised hair stays on
    locks.
  - READ: hero at bust distance is combed hair with a clean hairline and matching colour, still smoother and
    flatter than the strands; a few dark slits between cards on the back / top; npc cards lift at the crown like
    roof tiles; far = helmet + solid tail, no wisps; tails have mass at every tier.
  - NOT DONE: Cycles atlas bake + flow / AO passes (the atlas is the numpy raster; said in the guide), Godot render
    (godot is installed at ~/.local/bin/godot: untried), clearance against a decimated game skin, core for loose
    long hair (only tied tails), the golfer as strands judged (hs_14: strands lose the designed clump shapes and
    fail the silhouette gate 4.1 / 6.6 mm vs 1.3 / 1.4; my read: keep stylised hair on locks, no migration), the
    round trip (`blender_strands.read` exists; nothing consumes it), strand measures in
    look_hair beyond the @@strands counts, hair_r3 / golfer card exports re-checked with the new cards.
- Cloth (2026-10-01, `cloth.py` + `blender_cloth.py`, `pattern.py`, `tailor.py`, `freesewing.py`; the user: garments as
  real construction, drafted made-to-measure, sewn and simulated, never a finished garment warped onto another body).
  `spec["cloth"] = {name: garment}`: `pattern.from` a design in `cloth_designs.json` (FreeSewing parts by name, wraps,
  a seam table, button stitches, interfaced pieces, `fit_alterations`, tailoring `words` -> FreeSewing options) or own
  `pieces` + `seams` (a tablecloth is one piece). FreeSewing (MIT) is drafted in Node from `tailor.measure` (convex-hull
  girths and surface tapes on the body, FreeSewing's names), pack "freesewing" in assets.json, drafts cached
  (`<HOME>/_cache/freesewing`); missing Node/pack raise with the fetch command. `pattern` ops (turn, slash_spread,
  move_point, scale) are general 2D alterations; `large_abdomen` = front - back hps-to-seat past 25 mm, spread at the
  waist. Mesh: one flat mesh of all pieces, seams sampled jointly (chains with gaps = pleats), 1 cm triangles (2 cm made
  blobby padded folds), vertex mass scaled by area (Blender's mass is per vertex), solver quality 6 x (2 cm / h).
  Placement is isometric so rest = start: torso pieces on one generalized cylinder (the densified hull: a hull vertex
  as the start put the bodice 69 mm off centre), sleeves on the bent arm axis (sharp kink), a self-buttoned piece
  (cuff) closed on an exact spiral at its closed girth and moved off the hand's base with the sleeve's excess folded
  under (left open or over the hand it crumpled / dragged the shirt up), neck bands at their own girth on the neck's
  narrow part (`Body.neck_rows`; the neck joint is ~22 mm behind the neck's centre), curved bands on a cone from their
  sewn arc, a turned collar folded round a U with fold-line vertex rows. Sim stages (`blender_cloth.sim`): 0 the bodice
  sewn alone (shoulder seams lift it ~10 cm; with the sleeves on it dragged them up the arms), 1 everything sewn without
  gravity at sewing force 6 over 90 frames (30 whipped the hem up 15 cm) with cuffs held, 2 gravity + self-collision,
  hang (body removed, pins on a hook, rack colliders), self-collision settle. Interfacing (whole pieces or bands
  `{"piece", "near", "within"}`: cut-on plackets) stiffens bending, shear and stretch. Fit report: strain vs the start
  per girth region, negative ease from the flat pattern (`sizing`) = TOO SMALL, and `integrity` (self-crossings per
  piece, crumpled/folded faces, twisted seams) leading the verdict with CORRUPT. Diagnose with per-edge strain by
  piece and direction, start seam gaps per seam, and per-frame traces (`_trace`, `TRACE["stage0"]`): every fix above
  came from those numbers, not from tuning stiffness. Scene: `blender_cloth.show` (collection "cloth", pattern uv,
  Solidify); export: `cloth.export_part` (two-sided, the flat pattern as its atlas). Renders `workspace/cloth_renders/`.
  Cloth 2 (2026-10-02, the user: "learn how to do clothes" like hair, and everything through MCP; renders c20-c22):
  - Tools: `dress` (stores spec.cloth[g] merged, starts the sim in a background thread (`cloth.dress`/`_run_job`,
    progress in `workspace/<m>/cloth_<g>.progress`, `status`), waits `wait` s, returns progress or `cloth.report`),
    `look_cloth` (`cloth.look`: clay views + strain row + report; focus "g:piece", textured EEVEE with detail maps;
    hung garments show the rack, not the body), `sync(cloth_only=True)` (`cloth.sync` -> blender_scene `cloth_sync`),
    pull brings garment colour (`hp_color` node), roughness and SHAPE (Blender sculpt -> per-vertex offsets on that sim,
    `cloth.<g>.sculpt`, dropped and reported when the sim changes). `cloth.validate` at save; a cloth-only edit validates
    only hair+cloth (`store._validate_light`). Guide `guide(topic="cloth")` = `cloth_guide.md` (artists' workflow with
    sources: MD's 20 mm block -> 5-10 mm final, layers, fold lines, clean-up sculpt, Hogarth folds, seams last).
  - Sims never block a sync: `scene_job` takes only cached sims (`build(cached_only=True)`). The sim cache key is the
    sim's own inputs (start, pattern, triangles, seams, stitches, interfacing, both meshes) + blender_cloth.py's hash +
    fabric, not cloth.py: report/clean-up edits never re-simulate (`NOT_SIM` keys: color, roughness, cleanup, detail).
  - quality "final" = the whole sim at `coarse` 2 cm (~45 s), then `transfer` (barycentric in pattern space) onto the
    1 cm mesh whose REST is the coarse placement carried over (placed again at 1 cm its cuff spiral differed and an
    interfaced cuff crumpled), settled 40 frames with self-collision (`blender_cloth.refine`: Basis = rest, shape key
    "start" eased out, Dynamic Mesh). Shirt 3-5 min (was 8-25). "draft" = the coarse sim alone.
  - CORRUPT causes found: (1) no self-collision while sewing (fronts passed through each other): on in every stage;
    (2) the sleeve laid round the kinked elbow overlapped itself inside the crook (58 crossings in every START, grown into
    tangles): the excess round the mitre (r (u . n) tan(theta/2) per angle) is laid as a fin standing out in the mitre
    plane (`wrap.no_fin` off); (3) the hung coat: hang sewing force 200 drew it into a sack (now sew_force) and rack
    colliders kept Blender's 2 cm outer thickness (now 3 mm); the hang stage had no self-collision (now on).
  - Clean-up (`cleanup`): Taubin 4 passes at 1 cm (scaled by (1 cm / h)^2), each move capped at `keep` 4 mm, interfaced
    vertices not smoothed (smoothing crumpled a cuff 2 -> 6%), seams the sim closed welded, pushed off the body (not when
    hung). Strain/fit read the sim's own surface (`V_sim`), integrity the cleaned one (and the sim's, reported).
  - `shape_numbers`: crinkle = median dihedral between neighbouring triangles (1 cm sim 8-10 deg, cleaned 5-6), crinkle_mm
    and folds_mm along the smoothed surface's normal (plain Laplacian over ~15 cm; Taubin keeps low frequencies).
  - Detail maps (`detail_maps`/`write_maps`) on the flat-pattern atlas from the pattern itself: seam grooves + allowance
    ridge on sewn border edges, dashed topstitch at arc length along the outline, turned hems on free edges, buttons
    (discs, holes, button colour) on button* marks, slots on buttonhole*; normal + shade + basecolor; into the scene
    material (normal map on the "pattern" uv) and the export.
  - Neck bands: a piece sewn to an already placed neck piece starts at that piece's edge (the design's fixed "above"
    left the collar 2 cm over a lowered stand); `wrap.tilt` optional (no tilt helped the thin body); the report HINTs a
    band pushed > 8 mm off the neck (taller than the neck: lower the stand).
  - `integrity`'s candidate search: per-edge radius + a few big triangles apart (one global radius made 70M pairs, 11 s).
  - Body: `Body.m` lazy (a collider that isn't a body measures {}); state "draped" collides with the model's built
    mesh (`model_body`), pieces wrapped "flat". `tests/test_cloth.py`.
  - Solver-neutral job + GPU spike (2026-10-02, `cloth_job.py`, `spikes/gpu_cloth/`, renders g01-g02): the sim is a
    folder (job.json + in.npz -> out.npz: flat pattern = rest, start X, F, piece, sew/stitch pairs, interfacing, body,
    pins/hook/rack, `fabric.physical` SI numbers, the stage schedule spelled out by `cloth_job.stages`). Garment key
    `backend`: "blender" (default) | "file" (write the job, wait for out.npz) | "remote" ($HIFIPUSHIE_CLOTH_REMOTE run with
    the folder, e.g. `spikes/gpu_cloth/remote.sh` over ssh); results take the same clean-up/fit/integrity path, and a
    non-Blender backend is in the cache key. `run_newton.py` = NVIDIA Newton 1.6 VBD (warp, Apache-2.0): seams close as
    zero-length springs whose rest length shrinks, then are WELDED into one vertex for the gravity/hang stages (springs
    and self-contact fought: the yoke stretched 22-29%); a CUDA graph per frame; full-surface body contact (SDF) is
    CUDA-only. Results on a rented 4090 (shirt 1 cm 13.5k verts): 50-75 s vs Blender final 425 s / direct 1 cm 2530 s;
    smooth, no tangles, but VBD is convergence-limited (a hung sheet is ~100x softer than its stiffness at 10 substeps;
    stiffer material changes nothing, substeps do): strain p95 17.6% at 10 substeps, 9.9% at 40 (hem rides up, a waist
    crease); 5 mm shirt 56% / 17% with split sleeve seams; the hung coat rubbery at 10 substeps and NaN in the hang
    stage at 30-40 substeps or 5 mm. The user picked the 1 cm / 10-substep Newton shirt as the best LOOK (smooth, no
    tangles) despite its strain: the report now has a "reads" line (sim crinkle, fold depth) ranked before strain.
    Round 2 in run_newton.py: position-based strain limiting after each frame (`strain_limit`; edges past 1+limit
    pulled back, moves capped at 1 mm: 4 cm strain p95 8.9 -> 2.6%), interfaced pieces take their bending rest from the
    placement (`bend_rest`: with the flat pattern's 0 the turned collar unfolded into a hood; Blender's rest is the
    placement), seams stay welded while hung (the hang re-opened them as springs). ZOZO ppf-contact-solver (Apache-2.0;
    strain limiting, stitches; rest = the asset's 3D shape, uv only orients anisotropy; writes vertices REORDERED, map
    back by frame 0) via `run_zozo.py`/`zozo.sh`: its self-contained release (own Python, own HIP runtime) runs on this
    laptop's 890M with the ROCm backend and no SDK: 4 cm shirt 0.45 s/frame, 0 crossings, strain ~0.1%; at 1 cm it
    needs contact-gap 0.3 mm (the 1 cm pattern mesh has 0.5 mm sliver edges along seams: CCD fails at frame 0 with
    1 mm) and runs 9 s/frame (~45 min a shirt): too slow locally; spatial interfacing bend + bend rest from geometry
    together hit a non-PD block once.
    Round 2 on a 4090 (renders g04, g05): Newton shirt 1 cm, 10 substeps, 20 VBD iterations, strain limit 3%: 64 s,
    verdict "fits", 0 crossings, nothing crumpled, the collar turned down properly, smooth (sim crinkle 3.2 deg), strain
    p95 10.4% (round 1: 17.6%, CORRUPT stand, collar a hood). The strain limit alone barely helps at 1 cm (8 Jacobi
    iterations; 60 with a 2 mm cap dropped the coat through the body): iterations do. Hung coat 1 cm, 30 substeps +
    strain limit: 167 s, no NaN (welded hang), reads like a coat on a hanger, strain 8%, crossings only at the back
    vent (Blender has them there too). ZOZO on CUDA, shirt 1 cm: 451 s, strain 0.1% and cotton-like torso wrinkles,
    but the sleeves bunch at the elbows and tear (332 crossings inside the placement overlaps that
    `allow-existing-intersection` exempts) and the collar crumples: its rest = placement inherits the sleeve fins.
    ZOZO's coat: stitches whose ends start together give a NaN force (dropped now); then 2.3 s/frame, unfinished (90
    of 364 frames) at the pod's deadline. Runner defaults now: 10 substeps x 20 iterations + 3% strain limit worn,
    30 substeps hung.
    ZOZO round 3 (2026-10-02, local 890M at 2 cm, renders z0x): the 4090 sleeves rode up and tore because ZOZO sets a
    pin's pass-through (`allow_intersection`) once at build and keeps it after the unpin: every piece pinned while the
    bodice assembled (sleeves, cuffs, collar) passed through the body for the whole sim; and the cuff hold was (hold -
    fixed) = empty. Now garment key `placement: "smooth"` (backend file/remote only): ZOZO's membrane rests on the
    FLAT PATTERN (rest_vert written into the built scene: the frontend only derives a rest from pins), the made pieces
    (`cloth.made_pieces`, wholly interfaced) rest as placed in stretch and bending (`set_bend_rest_vert`; spatial bend
    x40 on them ran without the old non-PD failure); the garment is placed on `Body.straight_arms` (forearms turned
    into line, blended over +-4 cm at the elbow's mitre plane) and a "pose" stage bends them back through 4 poses with
    the sleeves on (sleeves are tubes on one straight fitted axis: a wandering axis stretched the cap 7%, past the
    limit; blousing compressed along the arm, not turned under); the start must be clean: `_piece_crossings` moves
    sleeves down the arm / overlapping torso pieces a layer apart, a cuff's outer layer moves out with the inner one,
    cuffs clear the wrist by CLEAR + h/4. Strain-limited solvers can't START past the limit: check sigma of flat ->
    start per triangle before a run. Runner for smooth jobs: no pins on pieces (a pinned cuff on the wrist is two
    prescribed things in contact: "contact starts overlapping"), allow-existing-intersection on (only the start's
    linked pairs are exempt), the arms split off the static body (a body with a move is solved: 2.95 -> 1.24 s/frame),
    a hung garment's body stops colliding by `collision_windows` (moved away down through the sleeves it dragged them
    against the hanger pins; windows act on solved objects only, so the static body gets a still move; and the session's
    dyn_param.txt (gravity) overwrote the scene's windows file: run_zozo appends them back), output rows by `map_by_name` (frame-0 matching failed on coincident vertices; `zozo_recover.py` rebuilds
    out.npz from a session's vert_N.bin). Mesh: FreeSewing notches were vertices 0.47 mm inside the outline (the 1 cm
    sliver edges); marks within 0.4 h of the outline are its vertex now (min edge 4.1 mm, min quality 0.26).
    Shirt 2 cm: fits, 0 crossings, nothing crumpled, sleeves to the wrists on the bent arms, collar turned down; reads
    crinkly at 2 cm (9.5 deg), strain p95 5.5% (outside of the elbows).
    Rack (`run_zozo`, hung jobs): capsules far from the hook stand still; the hanger's arms start inside the body under
    the hanger loop (`rack_drop` 8 cm lower: from the loop itself they touched the collar, "contact starts overlapping")
    and rise with the pins, colliding from the hang on: the coat is held by its shoulders. 1 cm on a 4090 (z02, z03;
    `pod_zozo.sh check|run`, the release fetched on the pod from GitHub): shirt 164 s (was 451), fits, 0 crossings,
    nothing crumpled, crinkle 7.4 sim / 5.0 cleaned, strain p95 4.9%; hung coat on the rack 664 s, holds its shoulders
    with the sleeves hanging (the best hung coat of the three backends to the eye), but 100 crossings at centre back and
    the stand/collar 18/11% crumpled where the hanger loop is gathered (the 2 cm run: 0 crossings). Open: cuffs start
    as circles round an elliptic wrist (pushed out 18 mm, so the made cuff is too big and ruffles), collar points stand
    up, the back crossings at 1 cm.
  - On a hanger (2026-10-02, "hanger" agent, renders h01-h1x; the user: "none of the coats ended up hanging on their
    hangers": every backend held the coat by pin patches at the neck, the rack decoration). `hanger.py`: a shaped
    hanger fitted to the body (`fit`: arms under the shoulders' upper surface (vertical rays, `clear` 8 mm) along their
    slope, width = shoulder points - 2 cm, wood arms 1.6 cm round at the centre broadening to 4 cm deep rounded ends,
    optional `bar`; the hook's rod up the neck's centre to 5 cm over the garment's start collar, curled over a face-out
    bar running BACK to a post: a through rail put a post in front of the coat), meshed from its own field as one
    closed collider (OUTWARD normals: the first mesh's inward faces held the cloth inside the arms and the coat climbed
    them). State "hung" = `{"hang": {"hanger": {...}, "rail": {...}}}` (the old pinned hang kept). It sits inside the
    body while the garment is dressed; stage "lower" (`Body.arms_down`: arms turned about the shoulder joints until the
    forearms are 7 cm off the torso, 26 deg here; poses `bodyLower`) brings the sleeves to the sides (left in the A-pose
    they hung splayed); then the body goes and gravity settles it onto the hanger with nothing pinned. Blender: seams
    WELDED while hung (as springs they opened under the weight, 36 mm mean, and the arms came out through the shoulder
    seams), hanger skin `HANGER_SKIN` 0.25 h (1 cm held the coat 4 cm up, bouncing), air damping `HANG_AIR`, 240
    frames, the sim's rod thickened to `HOOK_GUARD` 0.4 h (2 cm cloth folded through the 6 mm wire); the fine refine is
    SKIPPED on a hanger (the coarse hang carried onto the 1 cm mesh: the settle flailed 62 mm/frame and crossed at the
    back). ZOZO: hanger + rail static colliders from the start, the body's collision window ends at the hang; the
    lower stage moves the arms object. Newton: static meshes; it can't move its body, so "lower" is skipped there.
    Report `hanger:` line (`hanger.support`, `on_hanger`, `verdict`): the load each support carries = cloth mass by
    nearest support over the cloth graph (contact within 8 mm, by part, pins), still moving (p99 move over the last 6
    frames, `Vprev` from every runner: p90 per vertex <= 1.5 mm/frame and the centre of mass <= 0.5; Blender jitters single
    vertices ~2 mm on a coat whose mass stands still), floor; inside = rays front/back/up from 40-95% along each arm meet cloth, the
    rod crosses no cloth, cloth behind it (4/4 back sectors) and on both sides from 3 cm under the arms to 8 cm up (an open front
    is fine: lapels, V necks). NOT ON ITS HANGER leads the
    verdict; a coat floating in front fails (`tests/test_cloth.py`). ZOZO 2 cm (h04): on the hanger, arms 56/44%, 0
    pins, reads as a coat on a hanger. 1 cm on a 4090 (h12 ZOZO 911 s, h13 Newton 361 s): both ON THE HANGER (arms 100%,
    still), ZOZO's collar sits round the hook; crossings at the back vent (ZOZO 80, Newton 190), sleeves still ~20 deg
    out (arms_down stops 7 cm off the torso), Newton's splayed (no lower stage). Blender final h11 smooth (4.3 deg). Disk: run_zozo prunes vert_N.bin while running, deletes its session after, and
    refuses < 20 GB free / stops < 10 GB; cloth sims refuse < 20 GB.
  - ZOZO as a backend (2026-10-03, "zozo2" agent, renders zz01-zz1x; the user: "defer more Newton and double down
    on ZOZO"; Blender stays the local default). Garment key `backend: "zozo"` (`cloth_job.run_zozo`): the runner is
    `src/hifipushie/cloth_zozo.py`, run by the release's own Python (no hifipushie imports); the release is
    $HIFIPUSHIE_ZOZO / $PPF_ROOT or the optional asset pack "zozo" (assets unpack keeps symlinks: its Python's bin/ is
    symlinks). Local: under resources.heavy, a systemd scope (MemoryMax $HIFIPUSHIE_ZOZO_MEM 6G), device cuda/rocm/cpu
    found or $HIFIPUSHIE_ZOZO_DEVICE. Remote: $HIFIPUSHIE_ZOZO_REMOTE (spikes/gpu_cloth/remote.sh, GPU_RUNNER=zozo,
    GPU_SSH_OPTS; copies the job + the runner; `pod_setup_zozo.sh` unpacks the release on a pod by sha256). Defaults
    for zozo: placement "smooth", ONE sim at `resolution` (no coarse -> fine), clean-up without Taubin (it rounded
    ZOZO's fold crests 20-40%: sleeve crest radius p50 12 -> 17 mm at 1 cm; crinkle 7.0 deg unsmoothed, 0 crossings),
    garment key `zozo` = solver options into job.json (contact_gap, strain_limit, dt, interfacing_bend, snap, set,
    shear_model, uv_frame, ...). The sim cache key hashes the solver's runner (`cloth_job.solver_code`), never
    blender_cloth.py, and not where it ran; `look_cloth(result=)` applies any out.npz. The runner logs per stage where
    the time went (`profile`, from ZOZO's output/data/advance.*: steps/frame, how much of dt each step advanced and
    whether contact or the strain limit stopped it, newton, PCG, contacts) and `progress:` lines; `zozo_rows.npy` maps
    a session's vert_N.bin rows. Report: `sleeves from vertical` for hung garments.
    Material: ZOZO's shell hinge = BEND_SCALE 1.28e-5 x bend x areal density x |e|^2/A, so `zozo_bend` = B / (1.28e-5
    x density) from Kawabata B in PHYSICAL (shirting 0.02 gf cm2/cm -> 1.3, wool coating 0.2 -> 3.5; the runner had
    passed 1.0 for every fabric). Its Baraff-Witkin membrane takes E and nu; a patch test (spikes/gpu_cloth/
    zozo_patch.py) showed nu 0.045 makes it STIFFER in stretch and shear, so the old mapping (E = stretch/density,
    nu 0.3) stays. Placement: cuffs on a spiral round the arm's own (elliptic) sections at their closed girth; bands
    cleared by ZOZO's zone (4 mm, faces checked) not Blender's 8 mm; pieces closed round an arm rest as placed BEFORE
    the push off the body (`_made_rest`; pushed, a cuff rested 17-30% big and ruffled) with a strain limit above their
    start stretch (spatial "strain-limit"); collars/stands rest as placed. Hung: arms down straightened to 3 cm
    (`arms_down(straighten=True)`). Carlton's seam table was wrong: 867 mm of sleeve cap into a 603 mm armhole (the
    hindarm seam runs up to the back pitch / usTip), the stand sewn to the whole 425 mm neckline (now to the lapel's
    roll line), the 341 mm tail gathered into 243 mm (now pleated: FreeSewing points on an outline become outline
    points, `pattern._points_on_outline`). Open: hung sleeves spring out 13-26 deg within ~8 frames of the body
    going (at 8-10 deg at the end of lowering; not bend, not mesh size, not the hanger; compressed underarm cloth
    springing back is the lead), collars stand up, the coat's back side seam is 4 cm shorter than the front's.
- Clothing workflow (2026-10-03/05, "clothflow" agent; the user: "what artists actually do: building tools so LLMs can
  operate like real artists", and "all these learnings need to be codified"; renders `workspace/cloth_renders/wf_*`).
  The rule: construction before solver. A day of solver tuning chased what were pattern faults (cap ease 44%, a
  stretched stand, a missing belt, a pleat sewn shut, no sleeve placket, no lapel roll or facing, nothing pressed, one
  bend for every fabric). Stages, each readable before the next (`cloth_workflow.py`, `guide(topic="cloth")`):
  1. design sheet (`design_garment`, `spec.cloth.<g>.design`; `garment_design.py`): kind, from (draft source), fit,
     fabric, details, method, made. Defaults come from `garment_kb.json`; `cloth.expanded(g)` compiles the sheet into
     the ordinary garment keys (pattern options, drop, folds, generate, fabric, detail), the garment's own keys win.
     A choice the source can't make, or one that needs another (barrel cuff -> sleeve placket), fails.
  2. pattern (`look_pattern`; `pattern_sheet.py`): the flat sheet image (roles, grain, notches, seams numbered both
     sides, folds, interfacing) + evidence that every choice is in the pieces/seams (`garment_design.evidence`, roles
     not piece names), `cloth_check` seam bands (cap band by kind), ease per girth in the fit's band, loose pieces.
  3. construction (`check_garment`): sewing order, layers/lap, fold lines, interfacing, each piece made or draped
     (`made_or_draped`: draped cloth wholly interfaced fails, it is frozen as placed), the sim's stages.
  4. place: the start rendered and checked (crossings: fail for "smooth"/ZOZO, warn for Blender; neck band pushed
     > 8 mm; start stretch past ZOZO's strain limit; layer gaps).
  5. sim: verdict + `garment_kb.json` targets (`sim_measures`: collar cover, layer gaps, collar points, hem level,
     waistband height, sleeves hung, crest radius), each judged at draft or final; appended to `look_cloth`.
  `dress` (the MCP tool) runs `cloth_workflow.gate` (stages 1-3) and refuses to start a sim on hard failures unless
  `force=True`; `cloth.build`/`cloth.dress` in Python aren't gated.
  - `garment_kb.json` is the knowledge base (`garment_reference`): kinds (fit ease bands, default details, cap ease,
    lap, sewing order), details (collar, cuff, sleeve_placket, front_closure, placket, waistband, fly, skirt_closure,
    pockets, hem, yoke, darts, pleats, back_vent, belt, lining, shoulder, topstitch; each choice: made_of, seams,
    folds, needs, dims, evidence, lessons), fabrics with physical numbers -> solver preset + overrides, `designs` (what
    simon / carlton / skirt_block can and can't make, with recipes), targets, lessons. New kinds and details go there.
  - Fold lines: garment/design-table key `folds` [{piece, line, angle, strength, kind press|roll, radius}], angle on
    the pattern-face side (180 flat, 0 over onto the face, 360 under); `garment_design.fold_polyline` resolves the
    line forms; carried in `Bp["folds"]`. The solver side (mesh rows, placement, rest dihedral) is the "clothsim"
    agent's; until then evidence also accepts the old `wrap.fold` U and stage 3 warns.
  - `garment_blocks.py`: own drafts (`pattern.from: "skirt_block"`: front, two backs, darts, CB seam) and `generate`
    (bands sized from the drafted edges they're sewn to: waistband with lap + button, rib neckband as a ring).
    Torso wrap `"level": "waist"` (pattern y = 0 at that body line; the hull's z range stops at the pieces' top);
    `sizing` skips bands closed on themselves and girths the garment doesn't reach (a skirt read "TOO SMALL at chest").
  - `method: "settle"` (construct made pieces finished, settle draped cloth lightly, author fine folds; full sim for
    hung/draped) is the path under test by clothsim: the sheet and plan carry it, the solver doesn't yet.
  - Proved on Simon (`workspace/wf_simon`) and a new kind, the skirt (`workspace/wf_skirt`), at draft quality. Simon:
    the gate stops it (no sleeve placket, cuff seam -1.8%); forced, the collar-cover target reads -19 mm (the funnel).
    The recipe now drafts Simon's collar with no gap and width 1.45 (the seam was -2.4%, the fall covered 3 mm).
    Skirt: stages connect; the draft reads as a skirt but is strained at the dart tips, its hem dips 28 mm and it
    sits 21 mm low; with 11% seat ease one side seam gaped and the waistband crumpled (the pieces start on a cylinder
    far wider than the waist: a waist-fitted start is needed).
  - Open: Simon's sleeve placket (a slit op + cuff start at the slit), Carlton's belt/vent/facing/roll (clothsim),
    leg wraps for trousers, hoods/linings/pockets as pieces, button size and buttonhole direction per design in the
    maps, crease width and fold spacing as tool measures, per-piece fabrics. `tests/test_cloth_workflow.py`.
- Skin (2026-10-05, "skin" agent; the user: humans read "flat, plastic-like"; textures "for humans of all sexes, ages,
  and genders", incl. cosmetics, scars, tattoos, wrinkles, freckles; renders `workspace/skin_renders/sk_*`, references
  `workspace/skin_refs/` (24 CC photos, README + refs.json with skin-only boxes; never in the repo)). Guide:
  `guide(topic="skin")` = `skin_guide.md` (the artists' stages with sources); tools `skin`, `look_skin`, `skin_reference`.
  - Diagnosis (`skin_measure.py`: CIE Lab contrast per octave of feature size inside skin-only boxes, zone colour,
    highlight share / blob size / breakup, micro contrast; same code on renders and photos; a*/b* hardly see the light, so
    they read albedo). Flat colour + one roughness vs 13 photographed faces: lightness contrast at 0.35-1.4 mm 0.04-0.08 vs
    0.8-1.3; a* contrast at 1.4-11 mm 0.04-0.11 vs 0.4-0.6; no highlight at all vs 5-13% of a patch; cheek a* +0.3 vs
    +1..7. Ranked: no fine relief / highlight breakup, one albedo colour, no visible specular, no scattering colour, flat
    painted lips/brows.
  - `skin.py`: `spec["skin"]` (tone, age, variation, detail, oil, thin, sun, zones, lips, features, wrinkles, hair, scars,
    tattoos, makeup, shading) expands into ORDINARY paint layers "skin:<x>" laid under the model's own (`paint.layers`),
    plus the skin part's base (`part_base`: tone colour, roughness, specular 0.36 = F0 0.028, subsurface by tone, a coat
    lobe scaled by `oil` on the same bump, sheen; `scene.sync` merges it under the part's own keys). `spec.geometry`
    strips it. Tone = pigments, not a colour: melanosome fraction of the epidermis x haemoglobin fraction of the dermis ->
    spectral reflectance (Jacques' numbers, Kubelka-Munk dermis, Wyman CIE fits) -> sRGB (`tone_rgb(tone, melanin=,
    blood=, oxygenation=, epidermis=, yellow=, grey=)`); every layer is "this skin with more/less of a pigment", so
    cheeks, lips, palms, scars are right on any tone. Calibrated by eye to F1 #cda590 .. F6 #55331c (the raw model went
    orange at high melanin: a 130/cm flat term on melanin and a small back-scatter term fixed hue and floor).
  - Zones (`skin.zone`, paint generator `{"zone": name | {"name", "grow"}}`, expanded in `paint.layers` before anything
    else sees them): FACE (spots at lm_* landmarks in interocular units), LINES (tapered polylines: nasolabial, brow,
    lash lines), OUTLINES (lips), UNIONS (beard, nose, t_zone), BODY (shoulder, elbow/knee on the extensor side, hand,
    palm = hand x facing the palm normal from the finger chains, knuckles, fingertips, nails, forearm, sole). ".L"/".R"
    or both. A missing joint says which.
  - New general paint pieces: generator `spot` (soft ellipsoids / tapered polylines at joints, native per pixel), `tile`
    (a tiling grey image triplanar, `vary` = a second copy at 1.618x mixed by a 7 cm noise, `rotate`; native image nodes:
    mip-mapped), layer `mix` (multiply/screen/overlay/soft_light), entry op `"vertex": true` (measure this entry per
    vertex), a breakup-only entry.
  - THE LIMIT that shaped it: a renderer's shader holds a few dozen layers. EEVEE compiles a material into one GPU
    shader: the first 96-layer skin took > 5 min and 10 GB before I killed it (stage 1's 42 layers: 60 s). Cycles ran out
    of SVM stack ("out of SVM stack space": black skin, no exception) from exposed Value/RGB leaf nodes (every leaf is
    computed first and held: 96 colours x 3 slots), then from the Bump node (it compiles its height subgraph three
    times; one mask of ~20 tapered lines alone overflowed). So: (1) layers marked `_pre` (broad, soft: zones, mottling,
    lips, roughness patches, flush/tan, shadows under hair, foundation/blush...) are composited per VERTEX in Python
    (`paint.precomposite`, linear colour) into five measured scalars the material starts from (`prog["pre"]`); (2) what
    needs detail finer than the mesh is built ONLY from tiling swatches, images and a few line spots, never procedural
    noise/Voronoi (`skin_swatch.py`: depth swatches pores / lines / coarse / lips with the 0.5-3 mm grain folded in; mark
    swatches stubble / freckles / wrinkles / hairs; `brow_image` = a drawn picture of ~900 tapered hairs laid as a decal
    from the brow landmarks: noise strokes read as a smudge); (3) zone masks confining fine layers are measured per
    vertex (`"vertex": true`); (4) skin layers expose no named nodes, unexposed colours are socket constants; (5) one
    layer carries relief + cavity tint + roughness (one mask instance). Heavy test character (63 layers, 26 fine): EEVEE
    compile 130 s -> 75 s, 6-7 s a frame; export bakes (no Bump in emission passes) compile.
    Also: node LINKING is quadratic in tree size (1000 nodes 10 s, 2000 65 s, 3000 168 s in a bare Blender): every mask
    is now its own node group (`_Nodes.group/subtree/instance`, groups named `hpm:<part>:<n>`, dropped on rebuild; pull
    reads `hp:` nodes inside them). Round trip on a copy of dg_fix2: renders mean 0.18/255 apart (every object was
    re-meshed), both pulls empty, spec unchanged.
  - Features (`skin_features.py`, each a number or {"amount", "where": [zones], "mask": [...], ...}): freckles, moles
    (scattered or `at`), age_spots (default age x sun), blemishes, veins (default from age / thin), flush, sunburn, tan
    (`mask` for tan lines); wrinkles default from age (folds / crow's feet / under-eye as tapered lines, forehead / neck /
    lip lines / cheek lines from the wrinkles swatch, crepe from the coarse one); hair: brows, lashes (lash lines only),
    stubble (cool shadow pre + dots), body; scars cut / surgical (stitch dots) / keloid / burn / pockmarks with age 0..1
    and no pores on scar tissue; tattoos (`tattoo_image`: the picture blurred by years in its own mm, black toward
    blue-green, colours faded; multiplied into the skin under its relief). Make-up (`skin_makeup.py`): foundation (also
    hides 75% x coverage of the fine pigment layers, which composite after the pre base), concealer, contour, blush,
    highlight, eyeshadow, eyeliner + wing, mascara, brows, lipstick, nails; each with a finish (roughness / specular /
    metallic).
  - Eyes (`skin.eyes`, on where the base has eyeballs; `_eyes`): a painted picture per eyeball (`skin_swatch.eye_image`:
    radial iris fibres, collarette, limbal ring, soft pupil, a sclera pinker toward its edge with forking vessels) laid
    as a decal on the eyes part, wet (roughness 0.04), a shadow under the upper lid; caruncle and waterline on the skin.
    Flat iris/pupil paint on `eye_front` read as toy eyes at bust distance. No cornea bulge, no lash geometry yet.
  - Shaved / cropped heads (`hair.scalp`: amount, color, hairline): the hair's shadow under the scalp skin (pre) + cut
    hairs from the stubble swatch, inside ONE ellipsoid bigger than the skull whose exit from the skull is the hairline,
    nape and the line over the ears. The head joint is at brow height and the cranium ~1.5 interoculars round it
    (interocular = pupil distance, 6-9 cm on these heads): the first version's spots, sized by guess, ended just inside
    the skull and nothing showed, though the mask read 1 at test points (which were inside the head). Test masks at
    points found on the surface (a ray through `sdf.field_at`), not at joint + offset.
  - Wrinkle swatch: three families of wandering lines (main, a branch family crossing them at a slight angle, fine),
    each line's depth from noise much longer along the line than across (`_smooth_noise(cells, cells_u)`), so creases run
    on for centimetres, fade at their ends and fork. Isotropic depth noise chopped them into dashes ("scratches").
  - `skin_look.py` (`look_skin`): cropped stage models `workspace/_skin_<model>_<head|arm>` (bare skin + eyes, ~1 mm),
    re-synced when the spec or the skin code changes, EEVEE under fixed lights (studio / soft / back) or `engine=
    "cycles"`; views bust, face, three_quarter, side, cheek, eye, mouth, forehead, ear, hand, palm, forearm; `layer=`
    shows one mask; prints the face's measurements beside the photographs' with hints.
  - MakeHuman: the female macro targets are in assets.json (48 files) and `base.body.sex` is the continuous gender
    slider (1 male default: byte-identical; 0 female). GNM heads have no age/sex controls of their own (seeded
    identities): see headfit below.
  - Heads follow the body (2026-10-05, `headfit.py`, renders sk_07 / sk_08; the main session: every head was the same
    adult face). MakeHuman's topology is fixed, so `makehuman_lm68.json` (made once by `spikes/headfit/make_table.py`:
    the two neutral heads aligned by eye centres, similarity ICP on the face, a local ICP per feature, nearest
    vertices, pairs forced symmetric; checked in a picture) names its vertices at GNM's 68 landmarks + 4 cranium
    points. For a body, the landmarks' MOVE from MakeHuman's reference head (25 years, sex 0.5) to the body's own, in
    interocular units round the eye midpoint, is added to the seeded GNM head's landmarks (delta transfer: the
    table's millimetres of mismatch cancel, the seed's individuality stays) and solved in 120 identity components
    (ridge, components past +-2.6 sigma fixed and the rest re-solved), eye centres held. Head scale = the body's
    interocular / the fitted GNM's (0.74 for a 7-year-old, ~0.92 adults; the old default 1.4 made every head a
    doll's). OFF unless asked: `base.head.follow_body: true` or a strength 0..1.5 (the main session: existing
    characters with seed-only heads, s0urc3's Garrett, must not change; without the key the built base is
    bit-identical to main's, checked by checksum on three bodies and in `tests/test_headfit.py`); the `skin` tool
    hints at it and the skin guide's stage 0 recommends it for new characters. 60-70% of the asked move is made.
    What it took: lids and lips weighted 0.3 / 0.5 / 0.15 (in full, the child's lips twisted and lid margins tore);
    the neck and bib HELD (90 skin vertices under the chin: no landmark sees them, and left free the fit flared the
    bib up to the graft plane = the stand-up collar round old bodies' necks; with them held the head's neck matches
    the body's within a few mm); the graft plane follows the chin; a monotone neck taper. `tests/test_headfit.py`.
    Honest read: the child and the men read as their age; the old woman reads as an old man (GNM's space and a
    bald head), the adult woman androgynous.
  - Heads by age / sex / weight, second pass (2026-10-05, renders sk_10 grid, sk_h_*; supersedes the solve described
    above): MakeHuman isn't needed at runtime. `head_axes.npz` (spikes/headfit/make_axes.py) samples how the table's
    points (68 landmarks, 4 cranium points, ~350 dense pairs over face / cranium / neck) MOVE from MakeHuman's
    reference head (25 y, sex 0.5, weight 0.5) across ages x sex and with weight (`headfit.shape_delta`). The move is
    made in two steps: GNM identity components by ridge (60-70% of it), then the residual as a Gaussian RBF warp of
    the head (`head["warp"]`: jaw / chin width, brow ridge, neck girth; lids and lips take little of either). The seed
    first loses its OWN component along the sex / age / weight directions (`_body_axes`: a heavy-jawed seed left a
    woman a man). Keys, all opt-in (without them the base is bit-identical): `base.head.follow_body` (true |
    strength: age, sex, weight and scale from the MakeHuman body), `base.head.like` {"age", "sex" 0 female .. 1 male,
    "weight"} (set apart from the body, or on any body incl. the stylised template), `base.head.features`
    {brow_ridge, jaw, chin, nose, lips, cheeks, eyes, cranium: -1.5..1.5} (one part of the sex / child move on its
    own). `headfit.report(base)`: asked move, share reached by identity / after the warp, largest local stretch.
  - `skin.sex` (0 female .. 1 male, unset = neither; `params` -> `fem` / `masc`): sex-linked DEFAULTS, each still
    settable: finer thinner brows, darker lash lines, finer pores (detail x 0.78), lips with 25% more blood for a
    woman; heavier brows and coarser skin for a man. Stubble stays `hair.stubble` (off unless asked).
  - Eyes, second pass: `base.cornea` (a smaller sphere proud of the eyeball where the gaze leaves it, ONE group with
    its eyeball: as two elements with different blends the scene's chunked evaluation blew the mirrored eye up to
    twice its size, in the scene only, the clay look was fine); look lights take `"window"` (the highlight from a
    rectangular area light, the sun keeps diffuse + shadow) and `"specular": 0` on fills: one window catchlight, not
    two discs; a tear line on the eyeball where the lower lid meets it (paint `near: ["base"]` works).
    `look_skin`'s stage key now includes base.py / headfit.py: a stale stage hid two fixes for an hour.
    Not done: lash cards, re-measuring against the 24 photos, export fixes, grooms; nostrils show a pale thing
    behind them on followed heads.
  - Mirrored decals (the user on sk_07: "the left eyebrow is backwards"): a mirrored image decal kept the picture
    reading the same way round (right for text), so the other brow's hairs ran toward the nose. Image key
    `mirror_image: true` reflects the whole frame (`images.mirrored`: right = the reflected right, planar decals);
    the brows set it. Lashes, lip lines and wrinkles are zone masks / tiling swatches, not mirrored pictures; eyes
    are one decal per side; tattoos and text stay unmirrored. `look_skin` view "brows"; sk_09; tests in
    test_images (`test_mirror_image`) and test_skin (`test_brows_mirror`).
  - Heads as MakeHuman FIELDS (2026-10-05, "skin2" agent, branch worktree-agent-acd58d9aa9f53c1da; renders sk_20_*,
    sk_2w_*, sk_21_*; replaces the identity solve + RBF warp for age / sex / weight, which reached "93%" of 426 sampled
    points and still made a woman a soft man). Diagnosis by rendering MakeHuman's OWN heads beside ours: MakeHuman's f32
    reads female, its f78 an old woman; ours didn't, because (1) only the DELTA from MakeHuman's neutral was added to a
    GNM seed, and GNM's mean head is itself wider-jawed and heavier than MakeHuman's neutral (mean vs reference rms
    0.14 interoculars: more than the whole female move, 0.11); (2) a seed's individuality at spread 0.7 is as large
    as the sex move and reads male on a bald head; stripping the seed along a linear sex axis (landmark- or
    dense-fitted) does not change that. Now `spikes/headfit/make_field.py` registers GNM's mean head onto MakeHuman's
    reference head once (pairs RBF as a first guess, 4 rounds of closest point on MakeHuman's triangles facing the same
    way for the OUTER skin, each displacement smoothed over GNM's mesh by Laplacian least squares; lids' insides, mouth
    sock, ears ride; lips weighted 0.2; eyeballs / teeth carried by the skin beside them) and stores, per GNM vertex,
    `ref` (GNM mean -> MakeHuman reference) and the moves to every age x sex and weight (`head_fields.npz`, 2.6 MB,
    float16, interoculars; no MakeHuman pack at runtime). `headfit.field_vertices(desc)` -> `base.gnm_head` adds it
    x the head's interocular (head["field"] = a small descriptor, not the array: head dicts are cache keys).
    `follow` = seed stripped (`_body_axes`: the fields fitted in GNM's components) + field; `features` alone still go
    through the identity solve + warp and get NO field. New opt-in keys: `base.head.dimorphism` (default 0.8: the
    sex difference pushed past MakeHuman's own, half as far on the male side: a man at 0.8 read as a brute),
    `base.head.toward` (share of the absolute move, 1). Abs transfer through the 426 pairs alone made a lumpy skull;
    identity-space-only abs made a pouting boy. base.VERSION 76. `headfit.solved_points(h)` for tests.
    READ: woman 32 and teen girl read female bald; the old woman reads as an old woman or an ambiguous elder (was: a
    man); child fine; use `spread` <= ~0.45 for women and children (0.7 masculinises). The head's `scale` now comes
    out ~0.88 child / 0.97 adult (the field carries the size ratio).
  - Skin realism pass 2 (same agent): the "dried mud" was the `lines` / `coarse` swatches' Voronoi NET (every cell
    outlined at one depth) + crepe laid at 2-4 mm with a dark tint. Now `skin_swatch._glyphics`: families of nearly
    parallel furrows crossing at an angle with whole-number line counts (tiles), each fading in and out. Wrinkle
    swatch: rounded troughs 2-3 mm wide with rolls between (a 0.7 mm V = a scratch), forehead tint 0.2 -> 0.08; crepe
    relief 0.16 mm, tint 0.1, off forehead / chin; coat 0.04 + 0.16 oil -> 0.015 + 0.07 oil at roughness 0.34 (the
    varnish), base roughness +0.03, pores 0.21 -> 0.34 mm relief with less tint. Elder woman, measured: lightness
    contrast 0.7 / 1.4 / 2.8 / 5.6 mm 0.54 / 0.49 / 0.56 / 0.58 -> 0.38 / 0.47 / 0.57 / 0.61 (photos 1.26 / 0.83 / 0.78 /
    1.2), highlight 10% blobs 4.8 mm breakup 1.69 -> 5% / 4.6 / 1.33, micro 0.019 -> 0.010 (photos 0.05): it reads
    less like mud and MORE airbrushed by the numbers: fine relief is still 2-3x under the photographs. Dark woman:
    micro 0.033, highlight 15% in 11 mm blobs: still oily.
  - Whole humans by age, first honest line-up (the user: "we haven't seen any whole face-and-body children or
    babies"; `spikes/headfit/lineup.py`, sk_21_ages_lineup_clay.png + sk_21_ages_lineup_measures.txt; clay, no skin
    yet, the sheet's columns are mis-cropped). `base.body.age` goes to 1 through put_model; the pack has baby / child
    targets. MEASURED (ours | MakeHuman's own head | reference charts): stature 60 / 74 / 103 / 131 cm at 1 / 3 / 7 / 11
    (refs 75 / 95 / 122 / 144: MakeHuman's children are 10-20% short; pass `height`); heads in the height 4.87 / 5.51 /
    6.52 / 7.29 (MakeHuman's own 4.59 / 5.20 / 6.16 / 6.89; refs 4 / 5 / 6 / 6.75; adults 7.7-8.3 vs 7.5): heads are
    too SMALL at every age, MakeHuman's own by ~12% at 1 year, ours a further ~6% (partly lm_chin vs MakeHuman's
    chin_z: not untangled); hip joint / stature 0.43 at 1 (crotch ref 0.36: legs too long); interocular 37.8 mm at 1.
    FAILS seen: the baby's nose is torn open (a ragged hole at the nostrils: the field at age 1 turns the nostril
    walls inside out); the toddler has a long thin neck (graft) and an adult-ish torso; every face is the same stern
    seed; no fat rolls; rig / hands / skin zones on a baby NOT checked.
  - Whole children and babies (2026-10-05/06, "humans3" agent, branch `humans3`; renders sk_30_* (clay line-up),
    measures sk_30_ages_lineup_measures.txt; references `workspace/skin_refs/ages/` (README = spikes/humans/
    REFERENCES.md): WHO stature + head circumference, Snyder 1977 children's anthropometry from NIST AnthroKids,
    compiled by `spikes/humans/make_growth.py` into `growth.json`). The sk_21 line-up failed; by MEASUREMENT the
    causes were not the ones guessed:
    - Heads were NOT too small. The "reference" heads-in-height (4 / 5 / 6 / 6.75) were artists' chart numbers from
      memory; measured children (WHO stature / Snyder vertex-to-chin) are 4.6 at 1 y, 5.4 at 3, 6.4 at 7, 7.1-7.3 at
      11, 8.0 adult. MakeHuman's proportions were within 2-3% of that at every age. Its SIZES were wrong: baby ->
      child (10 y, not 11) -> young (25 y) blended in straight lines of age gave 60 / 74 / 103 / 149 cm at 1 / 3 / 7 /
      16 (medians 75 / 96 / 122 / 173 for boys), and a 20-year-old was a third child. `makehuman.grows`: under 25 (and
      unless `base.body.growth: false`) the age slider is SOLVED so the shape's heads-in-height = `anthro.heads(age,
      sex)`, then the body is scaled to `anthro.stature(age, sex)` x (MakeHuman's adult / WHO's at 19: 0.98 / 0.975,
      so 19-24 = the 25-year-old). From 25 nothing changes (bit-identical). `height` still overrides the size.
      After: stature, heads, head height, sitting height, trochanter height, hand length within 0-5% of the
      references from 1 to 19 y, both sexes. Off: MakeHuman's women have narrow shoulders (joint breadth 0.85 of
      the taped biacromial; men 0.94-0.97), small feet (0.84-0.89) and slim waists (0.85); under 1 year the shape
      stays a one-year-old's (heads 4.7 vs ~4.4 at 6 months).
    - `anthro.py`: `stature`, `head_height`, `heads`, `head_circumference`, `reference(age, sex)` (Snyder's segment
      means scaled to WHO's stature), `measure(P, J, chin_z)` (the same measures off a body mesh; girths = hulls of
      level slices cut at the shoulder joints, so toddlers' waists read small) and `table`.
    - The toddler's "long thin neck", the baby "cropped below the chest": the graft's neck tube. A followed head
      brought GNM's adult neck, and `_neck_tube` took the loop `loops[-1]` when no loop cleared the plane (a baby's
      chin lies on its chest): `_stitch` then cut the shoulders and arms off with the head. Now a head that follows
      its body fully (`follow_body` true, no `like`, toward 1; `headfit.follow` sets `own_neck`; `base.head.neck:
      "tube"` opts out) keeps the body's own neck: no cut, no tube (`src` = every template vertex: the hand-made
      weights reach the whole neck), the head's points above the plane eased onto the body's own head along their
      normals over `OWN_REACH` 3.5 cm x scale, the two point sets cross-faded as before. The GNM field head is the
      body's own head within 2.5 mm mean (p95 6-9 mm; chin landmark 5-8 mm higher than the table's: definition).
    - The "torn nose" at age 1 / the pale thing in followed heads' nostrils / flecks at the lip corners: the
      mouth fill (`base.inject`) was sized in absolute metres for a head of scale ~1.1; in a child's head (0.74-0.84)
      it came out through the nostrils and lips. Scaled by the head's scale for followed heads.
    - The stern thin mouth: `mouth_gap: 0` (the least-change lip closing + zip) presses the lips into a line. With
      the key left out the lips are GNM's own, a hair parted and full: `humans.spec` leaves it out. (Face shapes
      still need `mouth_gap` >= 0.002 + `interior`.)
    - "Breasts" on the toddler / child: mostly clay shading of MakeHuman's modelled nipples and the sk_21 strip's
      crop (arms cut off, so the torso read narrow-shouldered); MakeHuman's female child (10 y) does have a waist
      (waist / hip girth 0.70 vs a woman's 0.69, a toddler's 0.86). `base.body.nipples: 0` moves the skin round each
      nipple (found as the smallest mesh rings near the breast bone's tail) onto a quadratic sheet fitted through the
      ring outside it. Relaxing those vertices puckered the pole; a centre found by "most forward" landed on the
      belly, by "most proud of its ring" 2.5 cm off (the pole then stayed and the body's field creased in a star).
    - `humans.py` + tool `human(name, age, sex, weight, muscle, height, seed, outfit, tone, skin, head)`: a whole
      DRESSED person as an ordinary spec (body with growth, followed head, eyes + cornea, outfit, skin) and its
      measures against the references in the reply. Outfits (`humans.outfit`): tee_shorts, onesie (under 2),
      underwear, none: plain shell parts whose region boxes / sleeve cones / neck hole are placed from the body's
      joints, crotch and chin. The garment option (`close` / `hang` / tube) made studs at the nipples' rings, ruffs
      in the armpits and a line at the tube's top on small bodies: not used. Children get muscle 0.35, nipples 0.
      `tests/test_humans.py` (references, proportions 1-22 y both sexes, adults / opt-out unchanged, dressed by
      default, own neck). `spikes/humans/lineup.py [clay|skin]`.
    - Never render or send a child's figure unclothed: the tool dresses by default; diagnosis used numbers and
      scratch-only clay.
    - The head tables (head_axes / head_fields) were sampled along MakeHuman's OWN straight-line ages, so a head
      following a grown body is looked up at `makehuman.table_age(body)` (the age whose old slider has this shape:
      a grown 11-year-old -> ~13); `like.age` under 25 is converted the same way when the pack is there.
      spikes/headfit/make_axes.py / make_field.py pass `"growth": false`. base.VERSION 85.
    - STATE AT THE STOP (usage limit, 2026-10-06; branch `humans3`, last commit = this note): tests green at commit
      0f967b6 + the table_age fix (test_humans, test_headfit alone, test_skin, test_images, test_bodywarp; the last
      seq1 run's test results are in the worktree's `scratchpad/seq1.log`, read it first). NOT YET REPORTED to main
      and NOT JUDGED: the final clay line-up `workspace/skin_renders/sk_30_ages_lineup.png` + `_measures.txt` (14
      dressed figures, front + side, at true height, faces under). The copy I last looked at still showed the OLD
      composition (one face per person, 12 + 2 rows) and nipples as RINGS on the adults' tees although the script
      (`spikes/humans/lineup.py`, face row = front + three-quarter, two rows) and the smoothing (r 0.04 H, blend
      0.9 r) had changed: check whether the file was really rewritten (COMPOSE=1 re-lays the sheet from the
      panels in the session scratchpad `humans3/lineup/` without rebuilding) before believing it.
      My read of the previous render: babies, toddlers, 7s, 11s read as their ages and sizes (72-74 / 93-94 / 118-119 /
      140-141 cm), whole, arms on, no long necks, no torn noses. Still failing: tees are skin-tight shells (adults'
      muscles, navels and nipple rings print through: they read as body paint, not cloth); all faces are near one
      face (seeds at spread 0.35-0.5 after the seed loses its sex / age part: raise spread per person or add
      `features`); eyes read half shut at line-up size; a hatch of fine marks on the throat where head and body
      point sets cross-fade (own neck: try a wider band than +-SEAM); faint ring where a nipple was; shorts' box hem.
    - NEXT, in order: (1) verify + judge sk_30, SendMessage to "main" with branch, commit, tests, sheet path, the
      measured table and a blunt read; (2) looser cloth without the garment option's studs (a patch over each
      nipple pole, or fix `base.garment` closing at dense poles), varied faces, open eyes; (3) skin on
      (`lineup.py skin`: needs scene syncs, heavy), per-person front / three-quarter / side rows, face close-ups
      (look_skin stages take the base: check they handle own_neck and the onesie); (4) rig, hands, skin zones on a
      baby (rig_template reads `src`: now every vertex has one; rig.humanoid Neck / Head on a neckless toddler
      unchecked; retopo.graft_head / export topology "wrap" with own_neck UNTESTED and likely needs the no-cut
      path); (5) the `human` tool in guide.md / the skill; (6) priority 2 list from the task (elder woman, fine
      relief, oiliness, lashes, export of one human).
    - Scratch (worktree `scratchpad/`, untracked): run.sh (env), one.py <age> <sex> <outfit> [zoom] (one clay human),
      face.py (face variants), t4.py (bodies vs references table), t5.py (GNM head vs the body's own), quick.py (a
      PIL clay view of a mesh without Blender), seq1.sh (line-up then tests).
  - Chests, clothes with volume, faces, the throat (2026-10-06, "humans4" agent, branch
    `worktree-agent-ab7ea373ab4099300`; sheet sk_40_ages_lineup.png + _measures.txt; the user on sk_30, arrows at the
    woman's chest: "What is going on with this poor woman's boobs?"). Scratch in the worktree's untracked
    `scratchpad/`: run.sh, d1.py / d3.py (bare adult chest views + bust numbers; scratch only), g1.py (one clothed
    clay human, ZOOM=2.4 for a torso close-up), f1.py (face rows for a list of people), n1-n3.py (throat field
    probes), z1.py (a close look at a joint), tile.py.
    - THE CHEST, by measure (`anthro.measure` -> `bust_projection`: how far the fullest level of the chest's front
      stands ahead of the breast bone; ~10-20 mm flat, 30-40 an A/B cup, 50-60 C/D): (1) `base.body.nipples: 0`
      smoothed a patch 4% of the stature wide (6.4 cm on a woman) onto a sheet fitted through the ring outside it:
      it scooped a crater out of each breast = the dented ring. (2) MakeHuman's own female at average cup stands
      18 mm ahead of the breast bone, a small pointed AA cup, and our loader read only the macro targets: its
      breast modifiers were never fetched. (3) The tee was a shell of the skin (see below). Now the pack has
      targets/breast (228 files, CC0, in assets.json; `makehuman._bust`): `base.body.bust` / `firmness` 0..1
      (female x age x muscle x weight x cup x firmness, as MakeHuman blends them; no target at average / average, so
      a body without the keys is bit-identical), `nipples` = MakeHuman's nipple-point / nipple-size targets scaled
      by the body's size (an adult's millimetres turned a baby's chest inside out), then `_smooth_nipples` over 1.2%
      of the stature (wide, 4%, only under 11 years: MakeHuman models a mound under a child's nipple).
      `humans.bust_default`: bust 0.7 growing in from 11 to 17, firmness 0.65 at 30 -> 0.4 at 75, +0.2 dressed (a
      bra). Woman 30: 32 mm; children and men 0-2 mm. base.VERSION must be bumped when makehuman.py changes a body
      (the build cache is keyed on it, not on makehuman's code: a stale build hid two fixes).
    - CLOTHES: `humans.outfit` now uses `parts.<p>.garment` (close + hang + a torso tube; legs tubes for shorts),
      lengths scaled by stature / 1.7. What had made it unusable on these bodies: (1) the garment's field was
      EXACTLY 0 between 6 cm and the mesh's largest face size from the cloth (`_imls`'s far value, max(d - hmax, 0)),
      so the region's box showed as slabs in the air before a loose tee: garment point sets carry `far_fit` (the
      plane fit, capped at half the nearest vertex's distance; the body's own field is untouched); (2) the "studs
      at the nipples" were the nipples (flattened now); (3) notches in the hem at the side: the torso's region box
      was as wide as the shoulder joints and a woman's hips are wider (`tee_hips` box, `breadth()` = the torso's
      half breadth with the arms left out), and the shorts lay outside the tee (thinner shorts, tube_ease 12 mm);
      (4) tube key `"arms": "taper"` (what counts as arm narrows toward the wrist) and `"band"` (the hand-over's
      length, scaled). Onesie: close 60 + a nappy (a layer-1 blob round the seat). Underwear: close 12 / 6.
    - FACES (`humans.face(age, sex, seed)`): per-seed `features` (nose, lips, cheeks, chin, jaw, brow_ridge, eyes)
      leaning with age and sex, spread 0.45 (women, children) .. 0.6, lids opened by `pose` (lid_upper -2.6 mm:
      eye height 0.19-0.23 of the pupils' distance, was 0.15 = half shut), a trace of a smile, `mouth_gap` 0.001
      (lips together; parted, the fill behind showed as ragged teeth).
    - THE THROAT (own-neck graft, `base.surface`): three things were tangled. (1) Fine level lines down the whole
      neck = MakeHuman's neck rings of long thin quads with the IMLS kernel at the MEAN edge length: now the
      longest edge at each vertex (own-neck bodies only). (2) A ragged slot with shards under a child's jaw: there
      the body's and the head's skins are different surfaces 5-10 mm apart inside the overlap, each with a
      few-mm kernel, so the sheets ended in free edges: each point's kernel is now as wide as the gap (they blend
      into one closed skin). (3) The head is eased onto the body's TRIANGLES (closest point facing the same way,
      `rig_template.from_surface`) with trust falling off smoothly by distance and facing. Tried and dropped: a
      step onto the body's IMLS field (tore a ring round the neck), snapping the overlap's points sideways onto the
      body with its normals (a ribbed band). The mouth fill of a followed head is lower and flatter.
    - NOT the cause, for the record: the IMLS and `soften` do not flatten the chest (the tool sets no soften).
    - Read of sk_40 (clay, 14 dressed figures): the clothes read as cloth (tees hang from the bust and belly, no
      navel / muscles / nipples; the woman's chest is a normal chest under a tee, 33 mm; teen girl 28, woman 75
      11 (MakeHuman's old shape hangs low), children and men -6..+4). Still wrong: shorts are puffed tubes, a level
      crease across the bust where the tube takes over, one boat neckline for everyone, no sleeves' drape; babies'
      mouths are lumpy and grim, children still stern; the woman of 75 still reads as an old man; a faint line
      across the 11-year-old girl's throat; nostril interiors are lit pale dishes in clay.
    - `look_skin`'s head stage is BARE skin: for a body under 18 it is cut just under the neck (never a child's bare
      chest or shoulders).
    - Tests: test_humans (+ test_bust, test_faces_differ), test_headfit, test_skin, test_images, test_bodywarp pass.
    - NEXT, in the coordinator's order: (4) skin on (`lineup.py skin`: scene syncs, heavy, one at a time),
      per-person front / three-quarter / side rows, face close-ups; rig, hands, skin zones, export topology on baby
      proportions (retopo.graft_head / topology "wrap" with own_neck UNTESTED); (5) fine relief vs the photographs,
      the dark woman's oiliness, lashes, nostril interior (a dark paint zone inside the nostrils), one human
      exported. Also open from this round: baby / child mouths (try `features.lips` lower and no smile pose under
      3), the elder woman (longer `dimorphism`, or hair), shorts as a real garment, a neckline per outfit, the
      `human` tool in guide.md / the skill.
  - Open: EEVEE shows no light through ears/nostrils (Principled subsurface + thickness set, nothing visible); the
    shadow edge's colour is unmeasured against a matched light; real lashes and long brow hairs want geometry; nipples
    / areolae have no landmarks; freckle swatch repeats at 6 cm if a zone is large; a Cycles LOOK still fails on a heavy
    skin (Bump x3); per-vertex pre layers need a body voxel <= ~1.5 mm to hold 3 mm mottling (look_skin's stages do).
    `tests/test_skin.py`.
- Principle-based pattern drafting (2026-10-05, "clothflow" agent; the user: ready-made drafts are references, "we
  also need to distill the _principles_ so we can design jackets that don't exist yet, or any other arbitrary
  clothing"; sheets `workspace/cloth_renders/pd_*`). A new garment = a block + operations + details, as pattern makers
  work (Armstrong's three principles: dart manipulation, added fullness, contouring; Aldrich's blocks; FreeSewing's
  own designs derive from Brian/Bent/Titan the same way).
  - `pattern_blocks.py`: blocks by stated rules from `tailor.measure`: `bodice` (dartless or darted, to waist/hips;
    the front neck depth SOLVED so the neckline = half the neck girth + ease), `knit`, `sleeve` (drafted into an
    armhole: `solve_cap` finds cap height and top shift so front/back cap parts = front/back armhole x (1 + ease) at
    the asked biceps width; wider than the armhole is long -> not ok), `trouser` (forks, slanted back seam, the back
    fork dropped until the back inseam is 5 mm short). HALF pieces, centre at x = 0, every construction point named,
    `sym` = pair | fold | copy.
  - `pattern_draft.py`: the draft D (pieces, seams, `edges`, `notes`, `log`) and `OPS`: style_line (+ take_in),
    dart (pivot; the section holding the centre line never turns; an apex off the dart's centre line is trued onto
    it), dart_to_ease, flare (the centre side stays, the slashed edge is trued to a cubic), lengthen, extend, reshape,
    facing, collar (band / flat / roll from the neckline's own curve), sleeve, two_piece, unfold. What makes them
    compose: NAMED EDGES SURVIVE (`D["edges"]`: armhole_front, neck_back, hem_front, shoulder_front, centre_front...;
    `_remap` rewrites edges and seams through index maps when an outline is cut or a dart moves, breaking a chain
    where two old neighbours aren't neighbours any more; arcs must be resolved on the piece WITH the cut points
    inserted, or the bit up to the cut is lost). `consistency(D)`: every seam's sides equal, or its ease declared in
    `D["notes"]` (cap ease, gathers, the inseam); carried to `Bp["seam_notes"]` and honoured by stage 2 as kind
    "declared". `unfold` mirrors pieces and seams (fold pieces use ".m" names on the right).
  - Wiring: pattern `{"from": "draft", "block", "block_options", "ops"}` through `garment_blocks.draft` and
    `cloth.pieces`; the design sheet takes `block` / `block_options` / `ops` (chest ease defaults to the fit band's
    middle; judged by evidence, no recipe table). Knowledge: `garment_kb.json` `principles` (three principles, blocks
    with their rules, operations with what each keeps, derivations per garment category with why, rules of ease /
    balance / grain / shaping / proportions, sources), `garment_reference(principles=...)`; guide section
    "Designing a garment that doesn't exist". Don't re-dump garment_kb.json with json.dump (it reflows the file).
  - Checked against FreeSewing's Brian on the same body at the same ease (`pd_00_block_vs_brian.png`): chest width,
    armhole depth, shoulder and side seams equal to 0.1 mm, back armhole -2 mm, necklines within 1 mm, back outline
    1.9 mm mean; our front armhole is 9 mm longer (across-front 93%), our sleeve 35 mm narrower with a 26 mm higher
    cap (Brian widens the sleeve by its own rule). A drafted knit tee went through stages 1-4 (`workspace/pd_test`).
  - Style ops (`pattern_styles.py`, registered into `pattern_draft.OPS`; 2026-10-05, sheets pd_10..pd_17): `neckline`
    (widened on front AND back, so the shoulders still match), `shawl` (cut on, on the roll line; neck seam = back
    neck; `pair_seams` = an edge sewn to its own mirror at unfold), `lapel` + `collar` `"stop"`, `cut_away`,
    `darts_to_seam`, `raglan`, `kimono` and `hood` (pattern only: no placement), `pleat`, `buttons`
    (`pair_stitches`), `stitch`. `unfold` may be put in the ops list: ops after it work on one side (asymmetric).
    Bugs these found: a collar's outer edge was drawn on the neck hole's side (flat / roll collars shorter than
    their neck edge, crossing themselves; a band's top longer than its base): the body lies AWAY from the hole;
    a facing as a plain offset of its edge made beaks at corners (now the piece's own band within the width);
    a take-in inside a cropped hem left a hook (its end slides along the hem); point-given fold lines weren't
    mirrored at unfold; `cut_away` dropped the shortened shoulder seam instead of letting consistency fail.
  - `cloth.place` wrap `leg.L` / `leg.R`: one vertical generalized cylinder per leg (hull of that half of the body
    from waist to hem, cut flat 4 mm off the middle plane; outer part of each piece round the outside from the
    front / back corner, the fork's extension on the flat; isometric except the crotch hollow, squeezed under the
    crotch). Slices its own loops: `Body.hull` drops loops wider than the shoulders as arms, i.e. an A-pose's calves
    (the pieces started 37-52 mm inside the legs). Leg pieces count as torso for the assembly stage. `sizing`:
    facings / linings add no girth, pieces carry `wrap.half` (which side of x = 0 they're on: what crosses is
    overlap), side panels measure from their own inner edge (a princess jacket read +74% chest).
  - Three garments from prose through the tools (models `workspace/pd_trousers`, `pd_wrap`, `pd_jacket`; renders
    pd_20..22): wide trousers fit (0 crossings; slide 9 cm down, pool at the feet); the asymmetric wrap tunic reads
    as one (strain 11.8%, hem 9 cm lower on the wrap side); the shawl jacket's pattern and plan pass but its draft
    sim is CORRUPT (the cut-on collar starts up the front of the neck and Blender doesn't bring it round; two-piece
    sleeves bunch at the shoulders). No ZOZO release was on the machine: method "settle" untested on these.
  - Blazer from our blocks vs FreeSewing Jaeger (`pd_30_blazer_vs_jaeger.png`, scratch script): CB length, shoulder,
    back neck, upper armhole within 1-5 mm, armhole 2%, sleeve width 2 mm; Jaeger's shaped CB seam, side panel
    from the armhole, waist +17% (ours +29%), hem +12% over the seat (ours +2%), longer bent sleeve with a hollowed
    under sleeve and a straight gorge are what ours lacks.
  - Open: a start that lays a cut-on collar round the neck, a tailor's under sleeve, shaped CB seam, fish-eye darts
    in hip-length blocks, pockets / linings, head wrap, kimono placement, seat ease not reported for leg pieces
    (sizing reads torso pieces), trousers' length option for bare feet, a waistband that grips.
    `tests/test_pattern_draft.py`, `tests/test_pattern_styles.py`.
  - Round 2 (2026-10-05, "drafting" agent, branch worktree-agent-aaf5034835ab4c449; renders pd_40..pd_4x; scratch
    in the session scratchpad `drafting/`: run.sh <script>, st.py (stages), pl.py (place + crossings by pair + start
    strain by piece), dj.sh (dress + look in its own session), jg2.py (blazer vs Jaeger)).
    - HINGES (`pattern_draft.apply_hinges`, run at unfold): one cloth placed on two parts of the body. `D["hinges"]`
      {piece, at, dir, mid, origin, x, wrap, fold, part}: the piece is cut along the line for PLACEMENT only, the far
      part "<piece>_<part>" moved into its own frame with its own wrap, joined by a seam noted `"virtual": true`
      (seam_notes; `_sewn_arc` skips it; the maps should not draw a groove there: not done). Pieces traced from it
      (`pc["traced"]`: facings) are cut the same way, fold lines that cross are cut with it (`_split_fold`; a
      line point ON the hinge counts as across), and the cut gets a vertex where each fold crosses. `op_shawl` uses
      it: the collar past the neck point goes on the neck wrap (`flip`: pattern face out, `girth`: the whole circle
      a partial band belongs to, `apart`, `out`). The start-gap warning's 279 mm neck seam is now 88 mm.
    - The shawl's back collar needs SPRING: a strip run straight on from the roll line can't turn down (a cylinder's
      top has no isometric fold). It is an annular sector now (`spring` = outer edge - neck seam; default from the
      fall), laid on a cone flaring up, its fall folded at the ONE isometric angle (2 x the cone's half angle) as a
      single crease (a roll's rows round a curved line stretched the flap 70%).
    - `wrap.lies_on` + `cloth._lay_on`: a facing is placed as its front's placed surface, LIES 3 mm off the inside
      face (so on a turned lapel it is the side that shows), with a small untangle against that piece; it takes the
      front's fold lines (same mesh rows). Wrapped and folded by itself it had to pass through its front. The left
      front laps 4 mm + 12 (a fold) + 4 (a facing) out: what lies between the fronts. `style_line` panels start
      2 mm apart (`wrap.shift`): edge on edge they read as crossings. `cloth.mesh`: a roll's rows each end on their
      own outline vertex (sharing one bent every row's end: 150% stretch at the piece's edge).
    - Two-piece sleeve: the under sleeve was built wrong side up (folded-in strips) and so went round the arm the
      other way: both sleeve seams started ~15 cm apart and the sewing knotted the sleeve at the shoulder. Turned
      over now. `elbow` (m the wrist comes forward) bends each piece about its forearm seam's elbow point
      (`pattern.bend` / `unbend`; `wrap.bend`: place lays the straight sleeve): forearm seams equal, the top's
      hindarm 9 mm longer (elbow ease, declared), hem square to the forearm. A jacket sleeve needs `hem_width`
      ~0.28 (the block's default is a shirt cuff's: the forearms read red).
    - `pattern_tailor.py`: `contour` (an edge moved in / out per level: shaped CB seam, hem spring; a style line's
      name shapes BOTH its edges), `join` (two pieces sewn together become one: a side panel with no side seam; the
      seam's shaping is reported lost; b's clashing names become "name@b"), `round_corner` (cut-away hem; the corner's
      name stays on the curve's middle), `fisheye` (run on to the hem as a closed 3 mm cut: no holes in a cloth mesh;
      `darts: true` on a hip-length bodice now makes them), lapel `gorge: "straight"` + `gorge_drop` + `notch`.
      `take_in` on a STRAIGHT cut shaped nothing (two vertices): edges are densified first; a shaped panel seam's
      length difference under 2% is declared (`press_note`: pressed / eased on). `tests/test_pattern_tailor.py`.
      Blazer vs Jaeger again (pd_45): waist +16% (Jaeger +17), hem +12% (+12), CB length +1 mm, CB seam and side
      panel there; left: Jaeger's narrower side panel, its under sleeve's S-shaped top, chest +8% vs +4%.
    - ZOZO start: stage 4 passes for the jacket (0 crossings). Draped triangles that start past the strain limit by
      construction (fold rows on a curving chest, a stand pushed 1-3 mm: 0.7%, up to 16%) get the local strain
      limit in cloth_zozo (`start_over` 3%) and are info in stage 4; more, or > 60%, still fails.
    - Trousers: block `length` words (TROUSER_LENGTHS: floor, shoe, ankle (default: barefoot bodies), cropped, calf,
      knee, shorts); stage 2 `leg_ease`: seat ease in the fit's band from the legs' pieces, per-leg thigh / knee / hem
      against the body's own leg. The waistband slid 9-10 cm because it STARTED wrong: `place`'s torso hull ran up to
      the shoulders for every garment (`max(ytop, -0.03)`: a bug), so a waistband alone lay on the chest's curve,
      its back half 16-25 cm from the trousers. Now the hull stops at the pieces' own top, a band buttoned to itself
      alone on the torso lies at its CLOSED girth a few mm off the waist with its lap a layer out (start gap 161
      -> 46 mm). `waistband` op: the generate entry's chain is made at unfold from the waist edges as they are
      then (it had to be written by hand).
    - Stage 4 `seam_start_gaps`: `turned` = the rotation that lays one side of a seam on the other is > 35 deg
      with a median gap > 8 cm, for seams with a chain side. A waistband mis-ordered by half a turn has gaps of
      only a waist's diameter (247 mm < the 250 mm "far" limit: the distance check did NOT fire); a ring inside a
      ring (hood vs neckline) and a shoulder seam are not turned. `tests/test_cloth_workflow.py`.
    - Placement by hinge again: `kimono` (the sleeve past the underarm-to-shoulder line on the arm: `wrap.cx` =
      the pattern x along the top of the arm, front half `front: -1`, back `+1`, mirrored on the right arm: pair
      pieces on arms in unfold); wrap `head` (hoods: one plan curve round the head from the back, the sides `apart`
      by the centre seam's bow). `pocket` (patch, kangaroo: traced, `lies_on` + `face: "out"`, tacked by
      `sym_stitches` mirrored at unfold; a tacked piece counts as attached in stage 2), `lining` (every body piece
      traced, seams repeated, laid inside, sewn to the shell at hems / sleeve hems / back neck; same outline, no
      pleat, one fabric). Not drafted: welt / flap / in-seam pockets.
    - `skirt` block for the ops (pattern_blocks.skirt; a cut ACROSS a piece names the upper part first and keeps the
      centre seam on both parts; a pleat on a piece cut on the fold is pressed on both halves; pleat `underlays`
      are not girth in `sizing`).
    - Two new garments from prose through the tools (sheets in examples/garment_sheets): `raglan_anorak` (bodice
      cf fold, neckline, sleeve, raglan, hood, kangaroo pocket; model pd_anorak) and `yoke_skirt` (skirt block,
      yokes, a pleat each side, flared back, waistband op; model pd_skirt). What the tools lacked on the way, all
      fixed: a tacked pocket read "sewn to nothing"; the hoodie had no boxy fit band (a straight body on a V-shaped
      torso is +51% at the waist); the turned check fired on a raglan seam (single edges at an angle) and on the
      hood (ring in ring); the kangaroo pocket's default ran past a short hem; the skirt had no block for ops and no
      waistband op; the yoke's centre seam and the second pleat were missing; pleat cloth read as +12% seat ease.
    - Results (renders pd_41 Blender jacket, pd_44 ZOZO jacket (raw V), pd_46 trousers, pd_47 tunic, pd_50 anorak,
      pd_51 skirt): the shawl jacket on ZOZO settle: "fits", 0 crossings, strain p95 1.5% (646 s at 2 cm), lapels
      turned, sleeves smooth; its raw surface had the centre back OPEN from the neck (coincident centre-seam
      stitches are dropped by the solver: centre seams now start 2 mm apart, NOT re-run). Blender draft: reads as
      the jacket, 1 crossing, facing collar 4% crumpled, puffy. The skirt stays at the waist (Blender); the
      trousers on Blender still slide 99 mm (run before the waistband start fix; the ZOZO run never started).
      The anorak's body, pocket and hood read, its RAGLAN SLEEVES crumple at the shoulders (22 crossings): the
      sleeve's shoulder part lies along the arm, 173 mm and ~60 deg from the body's cut. Stage 4 names it
      (turned). Fix = a hinge in `op_raglan`: the shoulder parts placed on the torso in the coordinates they were
      cut in, the sleeve on the arm. The tunic reads as a wrap tunic but is over-cinched (take_in 56 / 62 mm over
      9 cm now really shapes) and strained at the tie.
    - THE ZOZO RELEASE IN THE SCRATCHPAD BROKE during this session (its python/lib/python3.12 lost most of the
      standard library some time after 12:49 on 2026-10-05: "No module named 'encodings'"): every zozo job fails
      until it is unpacked again (asset pack "zozo"). Not caused by these changes.
    - Open, in order: re-run jacket + trousers on ZOZO once the release is back (dj.sh); the raglan hinge; a
      facing's free inner edge (tack it, or settle's treatment of made pieces that lie on draped cloth: asked
      clothsim); virtual seams still draw a groove in the detail maps and the pattern sheet draws hinge parts
      apart from their piece; welt / in-seam pockets; lining trimmed to the facing; the under sleeve's S-shaped
      top; `hem height spread` reads designed curves and yokes as unevenness (skirt 490 mm, tunic 82 mm).
    - Round 3 state at the stop (usage limit): added the raglan hinge (shoulder parts on the torso), pleats laid closed by the wrap (`wrap.pleats`, folds `in_wrap`), welt / flap / in-seam pockets, `y: "waist"` in point specs, the tunic re-cut at the waist. Facings are still wholly interfaced (= made); marking them draped (clothsim's advice) stretched them 100%+ round the roll's rows: reverted, open.
      Sims queued through `drafting/seq.sh` and NOT judged: pd_52_jacket_zozo (running), pd_53_trousers_zozo, pd_54_anorak_blender, pd_55_skirt_zozo, pd_56_tunic_blender (logs in the scratchpad `drafting/<tag>.log`, renders in cloth_renders). Not started: the remaining Jaeger differences (under sleeve `shift_back`, side panel width, chest ease).
    - Stale option trap: `design_garment` merges key by key, so an old `block_options.darts: true` (which did
      nothing at hip length) suddenly made fish-eye darts under a princess line. Give `"darts": false` with panel
      seams, or replace the sheet.
    - Round 4, construction faults (the user on pd_52 / pd_55: "lapels aren't attached right", "stitches super
      visible", "the skirt is unzipped"; renders pd_62..pd_6x). Diagnosed on the raw sims, all three were the same two
      things: MADE PIECES PLACED WHERE THEY CAN'T END, and ZOZO stitches too weak to close a seam.
      - The jacket's board: `front_facing` (wholly interfaced = made = carried rigid by the settle) was a plank 54 mm
        off the body, 16-64 mm off its front, its seams never closed. A facing is now FUSED to its piece
        (`op_facing` sets `wrap.fused`; `cloth.pieces` sets fused pieces and their seams aside in `Bp["fused"]`: one
        cloth for the sim; `"separate": true` keeps a piece). The left front's lap is 4 + 10 mm (was 20).
        `folds.apply`: a flap is only the cloth BESIDE its line: the button stand below a roll line's break point was
        turned 170 deg into the other front (28 crossings, a "70 mm push").
      - The skirt's V at centre back: the waistband (made) was laid on the garment's one cylinder (hip girth), 30 cm
        open at the back, and carried rigid: its button stitch ended 352 mm open and the yokes sewn to its ends were
        held apart. Now a band closed on itself among other torso pieces lies on the body's hull at ITS OWN level
        (the narrowest slice over its height) at its closed girth; shorter than that + the solver's 4 mm clearance
        is `B["band_short"]`, a stage 4 failure (the skirt needed waist ease 3%: its band sits above the waist line).
      - Seams: the runner's own last line had said it all along (seam gaps mean / p95: trousers 3.5 / 14.5 mm, jacket
        15.5 / 57.7, skirt 19.3 / 97.1). ZOZO's `stitch-stiffness` (default 1, its force capped by
        `stitch-length-factor`) at 30 closed every draped seam to ~1 mm (a side seam starting 124 mm apart: 1.4 mm)
        at 7x the time; 8 gives mean 3.1 mm at 3x. The sheets set `zozo.stitch_stiffness: 8`; the default is
        clothsim's call (it stays 1). Clean-up welds seams again after the push off the body (the push reopened
        them) and clay looks draw welded faces (`cloth.welded_faces`: duplicate seam vertices shaded as a pale line).
        Stage 5 measures `seam_gap_p95_mm` (target <= 0.5) and `closure_gap_max_mm` (<= 6) and fails on them.
      - Closures: stage 3 `cloth_workflow.openings`: every pair "<name>.L" / "<name>.R" at the centre must be joined
        by a seam (a zip is sewn as one), stitches (buttons, a tie) or be declared (`design.open: [name]`). The
        skirt sheet said `skirt_closure: "none"`: now `cb_zip`. A zip has no record or geometry yet: clothsim's
        `closures` key (kind, over / under, line, lap, at, state) is agreed; the draft ops (buttons, stitch,
        waistband) should emit its entries once it is on main.
      - Tried and dropped: a waist-SHAPED start (per-level plan curves: the body's hull at each level out to the
        pieces' span there). Seam start gaps 124 -> 15 mm, but 10-30% shear in the start: a pattern puts its taper in
        the side seams and darts, a level-by-level wrap spreads it round the body, and arcs from the centre drift
        between levels. Like CLO, pieces start apart on a simple surface and the SEWING closes them: the stitch
        strength is the lever. Kept from it: in smooth placement the cylinder's girth is the SPAN of each side's
        pieces per level (pleats closed, laid-on pieces out), not the sum of widths.
      - Across cuts (a yoke): the lower part starts 6 mm off and a 3 mm layer out (a flared panel's top corner rises
        past the yoke's at the side seam, on the same surface: crossings once a pocket added vertices there).
      - Results (pd_66 jacket before/after, pd_67 / pd_65 skirt): jacket raw seam gaps 15.5 / 57.7 -> 1.4 / 2.5 mm
        (mean / p95), after clean-up p95 0.5, no board, button 9 mm (target 6: fails), back collar 4% crumpled
        (CORRUPT), body bloused and 6 cm shorter (stiffer stitches haul the fronts up to the carried collar). Skirt
        19.3 / 97.1 -> 1.8 / 4.8 mm, closed at CB, fits; the top of the CB seam 14.8 mm and the band's button 25 mm
        still open (a made band is pushed 4 mm off the body), pleat folds did not hold, pocket bags lump at the sides.
      - `collar` type "tailored" (stand_height + fall on a roll line, back part an annular sector: outer edge 36 mm a
        half longer than the neck edge, ends at the gorge; points cbNeck / cbRoll / cbOuter / endNeck / endRoll /
        endOuter, edges collar_neck / _outer / _end). Pattern + unfold tested only; clothsim places it.
      - STATE at the stop (usage limit, 2026-10-05): main merged in (60ffb1f). pd_64_trousers_zozo was queued behind
        the heavy slot (log `drafting/pd_64_trousers_zozo.log`), not judged. The merge changed the sim cache key:
        pd_62 / pd_63 need a re-sim for new looks. clothsim's taut `hpsToWaistBack` (on main after its merge) moved
        every block: pd_wrap now fails stage 2 (waist ease +11.1%), and numeric y options in the sheets (lapel
        break_y, style line y) need re-reading. Next: judge trousers; the button / band-top gaps (lap, the made
        band's clearance); switch buttons / stitch / waistband ops to clothsim's `closures` key once merged and read
        it in `cloth_workflow.openings`; re-fit the sheets to the new measures; anorak + tunic on ZOZO; run
        tests/test_cloth.py; the ranked "any garment from prose" proposal.
  - Fold lines, method "settle", authored fine folds (2026-10-05, "clothsim" agent, renders fl_*; the user: the cloth
    "appears thick", garments lacked construction; then the north star: artists construct and press collars and
    cuffs, drape the loose cloth, author the fine folds).
    - `folds.py`: garment/design key `folds` ({"piece", "line", "angle" (180 flat, 0 over onto the outside, 360
      under), "kind" press | roll, "radius", "strength", "flap"}; `pattern.fold_line` resolves the line and runs
      its ends out to the outline: a fold must cross its piece). `cloth.mesh` puts a vertex row on the line
      (`folds.rows`/`row_samples`: ladder twins beside the outline, ends snapped onto ring vertices, `force_edges`
      flips; `M["folds"]`). `cloth.place` lays every piece UNFOLDED on its wrap, pushes the base clear, then
      `folds.apply` turns the flap about the row per station as far as asked or as it clears its obstacles (own
      base, earlier pieces on the same body part, the body), eased along the line.
    - A curved crease has ONE isometric fold angle (180 - 2 x the cone's half angle: the fall's cone reflected);
      opened further the flap is stretched (130 deg: 17-75%). The collar blocked at 130 deg until both neck pieces
      shared a radius: each used to clear the neck over its own heights, so the collar stood 4-5 mm inside its stand.
    - Neck bands now go on the neck's own hull a clearance off the skin (`_cuff_spiral(m_min=)`, arc length kept),
      seated where their girth fits but with their top still on the neck (`_neck_frame(band=)`): the old circle
      clear of the neck's widest radius was 20-30% longer than the band, which stood open and far off the sides.
      Seated at the neck's base (1 cm lower) the yoke bunched up behind the collar. A stitched stand (button to
      buttonhole) closes exactly if it is long enough; Simon's isn't on a 4 mm solver standoff (it would need
      ~15% collar ease), so the shirt is open-necked. tailor's "neck" is the narrowest girth (370 here); a collar
      sits lower (385-397).
    - Solver: made pieces rest as placed (the fold is in the placement). Cloth resting flat gets
      `folds.bend_reference` (in.npz `bend_rest`: the flat pattern with flaps turned 170 deg; ZOZO reads hinge rest
      angles from it) and `fold` weights (bend x (1 + 20 x strength) on the rows, one spatial multiplier with the
      interfacing). `zozo.rest_flat: ["collar"]` runs a made piece that way: the collar held 157 deg (rest as
      placed: 129, the shirt lifts the stiff fall), cover 8.5 mm. Blender: `mesh(fold_width=FOLD_WIDTH_FITTED)`
      makes each fold a U 8 mm across (a single crease was blown open to 87 deg by its collision distances and
      crumpled).
    - A simulated crease can't have layers under ~3 mm apart: its first ring of vertices needs a contact gap
      (`wedge` = 1.2 mm / h in `folds.apply`). Layers <= 2 mm come from construction, not from the solver.
    - Method "settle" (`build`: `settle`/`construct`): `_carry` (made pieces pinned in ZOZO, in.npz carryIdx /
      carryPoses = a Kabsch move per pose fitted to the body vertices under each piece; cloth_zozo pins them for
      the whole sim), a 150-frame schedule without the assemble stage, then `_constructed`: transfer onto the fine
      mesh, the made pieces from the fine mesh's own placement (`FOLD_WIDTH_MADE` 1.6 mm U) fitted rigidly to
      where the coarse ones were held, flaps laid again (`_relay`), loose seam vertices drawn onto the made edges,
      `_tuck`. The cache key leaves the fine size out. 184 s sim + ~20 s on the 890M.
    - `cloth_detail.py`: fine folds from the drape's compression (per-triangle smallest principal stretch of
      pattern -> drape; amplitude (L / pi) sqrt(c)), Gabor-like dabs into a height map on the atlas,
      `cloth.fine_folds` -> `detail_maps(extra=)`. Sleeve crease width 6.7 -> 3.4 mm, spacing 19.7 -> 8.7 mm
      against the 1 cm full sim (zz16), measured on renders with the audit's profile method.
    - Folds, second pass (the main session: "combed/hatched"): `cloth_detail.fold_dabs` makes each dab ONE fold (a
      crest or crease, envelope half a wavelength: no ripple trains), bowed, its direction jittered 10 deg, lengths
      and wavelengths log-uniform, fewer where the compression is even; a second, sparse population 2.8x the size goes
      into the GEOMETRY of a mesh <= 1.2 cm (`displace`: outward only, fading 2 cm from outlines; build sets
      `folds_in_geometry`), the fine ones into the normal map.
    - Crossings: 44-90 came down to 18 (collar / front.R 10, sleeves 4 + 4; verdict "fits") once `transfer` ran on
      past the coarse outline instead of clamping (two fine vertices beyond one coarse corner landed on one point:
      a zero-area triangle) and the slit had parallel lips (a wedge's lips were 0.02 mm apart near the tip). The
      tuck and the seam draw still make the rest: moving cloth vertices without contact.
    - The fine settle (default with method "settle"; `fine_settle: false | [press, settle frames]`; `_press_plan`,
      cloth_job mode "fine_settle", cloth_zozo carryIdx / carryPoses / releaseIdx / restIdx; cached `<key>_fine.npz`):
      the constructed fine mesh settled for ~36 frames with the made pieces held and their flaps FREE from frame 0,
      resting folded as made (a fall bends over the shoulder cloth), LOCAL: only cloth within `FINE_REACH` 10 cm of a
      made piece is solved, the rest is held (solving it all, the sleeves crumpled again). What it took, in order:
      `_clear_of_body` (ZOZO's fatal pairs were body VERTICES 1.6-1.9 mm under the middle of sleeve triangles: now
      an exact body-vertex to cloth-face pass, held vertices too); `_relax_stretch` + a strain limit the start can
      meet (triangles at piece outlines started 5-70% stretched: "ccd failed"); flaps never prescribed against cloth
      (two prescribed things squeezing a third: "intersecting pairs"), opened only as far as clears what is under
      them; `_untangle` before and after; the clean-up reverts any vertex it would re-cross. Shirt: 0 crossings,
      "fits", fall covers the neckline seam 7.9 mm at CB, fall over what is under it 2.4 mm median, collar points
      5.4 / 2.2 mm off (with `tacks`: design key, points of a made piece held to the cloth under them, as collar
      stays / buttons do), sleeve crease width 2.7 mm / spacing 6.3 mm (zz16: 6.7 / 19.7). ~260 s settle + 50-100 s
      fine settle on the 890M. Fold flaps are stretch-capped in placement (`max_stretch` 0.30: at 0.04 the shirt
      collar turned 2 deg), and the draped start is relaxed with fold rows and flaps left as laid.
    - The neck-point knot (the main session: "diagnose it with numbers"): `tailor` put the shoulder point at the
      shoulder JOINT's x, inside the arm's root: the shoulder seam was 183 mm for ends 134-139 mm apart. Now the point
      where the shoulder line turns down (slope > the line's + 10 deg, never inside the joint) and shoulderToShoulder
      as a taut tape: 176 vs 148. The 28 mm left: the stand's ~12 mm standoff, the shoulder end 7 mm inside, the
      across-back drafted as a flat width (~10 mm). Three bodies re-checked: shoulderToWrist = the joints' path
      (553 / 583 / 544 mm), hanger width 2 cm inside the shoulder points.
    - Layered garments (`over: "<garment>"`, `cloth_layers.py`, renders ly_*; model `workspace/ly_suit`, Jaeger over
      Simon): the under garment is built first and frozen; `_collider` joins its result to the body (riding the
      body's poses by nearest body vertex), the outer garment is placed on `padded_body` (the body pushed out to
      cover it + `layer_gap` 3 mm). `support` (`SUPPORTS`: shoulder_pad, sleeve_head) are pads on that body, not
      cloth. `cloth_layers.tells` (in `res["tells"]`, the report, targets `layer_*` in garment_kb.json): under collar
      showing above the outer at CB 10-20 mm, cuff past the sleeve 10-15 mm, lapel gap, collar hug, crossings between
      the layers. `hidden` -> `export_part` leaves out the under garment's faces the outer covers (further than
      `hidden_margin` 3 cm from its free edges; `export_hidden: true` keeps them). Jaeger's table (flip_y on stand /
      collar, lapel roll folds on `breakLine`, vent folds, the armhole as one closed seam chain, pads) is in
      cloth_designs.json; its seam check passes except cap ease +1.8% (band 3-6). NO JACKET SIM HAS RUN: the ZOZO
      release was deleted from the scratchpad mid-work. Not built yet: the joint settle where the layers touch,
      lapel facing + gorge, chest canvas, weights copied from the outer layer, `over` in the design sheet.
    - ZOZO drops nothing now: stitches whose ends start together (edge-to-edge panels, a facing on its front) had no
      direction (NaN) and were dropped, so nothing sewed the seam (the "drafting" agent's jacket CB stood open).
      `cloth_zozo.part_stitches`: each such end steps 1 mm back into its own cloth (layers part along the normal),
      held/made ends stay; job `stitch_gap` (0 = drop as before).
    - Jacket rounds (2026-10-06, renders ly_01-ly_03, models `workspace/ly_jkt` (Jaeger alone) / `ly_suit`):
      ly_01 (Jaeger over Simon) was a puffer with a ruff. Causes, each separated on the jacket alone first:
      (1) `padded_body` spread every fold's crest three rings round (pad 29 mm at the median, to 71, over a shirt
      8-16 mm off the body: "biceps" 534 vs 340). Now one ring, and the under garment is `pressed` first (its loose
      cloth to `UNDER_CAP` 8 mm off the body along the body's normals, made pieces as they are, eased 3 cm round
      them; garment key `under_cap`): that pressed surface is the pad, the sim's collider, what the tells read and
      what renders show under the jacket (`res["under_V"]`).
      (2) The neck wrap is a ring round the neck: a tailored collar's stand (291 mm, sewn to a neckline that lies on
      the shoulders and runs down to the gorge) stood under the skull; tilted it went through the shoulders. Wrap
      `"to": "seam"` (`cloth._on_seam`): the piece's sewn edge laid on the edge it is sewn to (the seam's own vertex
      pairs), at the PATTERN's lengths, marched from the middle along the body's surface (the placed neckline is
      not one curve: fronts and backs start apart, 778 mm for 291; past a gap it heads for the edge's end), the piece
      running up the surface from there; `turn` {at, deg, gap} lays a fall over in the wrap (its fold `in_wrap`).
      Pieces are placed in listed order: what it is sewn to must come first.
      (3) `sizing` read -116 mm at the chest: the body's chest line is 10 cm above Jaeger's side panel's top, so the
      panel wasn't measured; the chest is now taken just under a panel that starts under the arm.
      Jaeger alone, 2 cm ZOZO settle: reads as a jacket, 0 sim crossings (4 from the clean-up at the vent), strain
      0.8%, sleeves to the wrists, lapels 164 deg; the collar is a lumpy roll (its fall starts 1.25x stretched: in
      FreeSewing's draft the collar's outer edge is SHORTER than its neck edge, both bow toward the fall; the author's
      own comment says the collar wants a redesign), fronts spread below the buttons (no facing), surface crinkly.
    - BODY MEASUREMENTS MOVED (2026-10-06; every draft changes, results before it are not comparable). Checked
      against FreeSewing's own standard masculine body (packages/models neckstimate: chest 1000, hpsToWaistBack 470,
      waistToArmpit 210, hpsToBust 280, shoulderToShoulder 450, biceps 350, shoulderSlope 13):
      (1) the down-the-body tapes are TAUT now (a hull over the lumbar hollow and the slices' bumps; `tailor.down`).
      hpsToWaistBack standard / heavy / thin body: 545 -> 486, 536 -> 510, 542 -> 481 mm; hpsToBust 331 -> 282.
      FreeSewing's armhole depth is hpsToWaistBack - waistToArmpit: 314 -> 255 (its standard: 260). Simon's and
      Jaeger's armhole base sat 331 mm below hps on a body whose armpit is 207 below it: the "bomber" jacket, the
      rolls across the upper back with the arms out, the body of every shirt 6 cm long. Now 273; Jaeger's CB length
      802 -> 732.
      (2) shoulderSlope is the slope of the shoulder LINE (a fit through the top of the shoulder from 2 cm outside
      hps to the shoulder point), not the chord from hps, which is taken 2 cm up the neck's side: 28 -> 21, 26 -> 26,
      29 -> 22 deg (the hanger's own fit to the surface had read 17; `at["shoulder_slope_chord"]` keeps the old one).
      Still unlike the standard: shoulderToWrist 553 (630: these bodies' arms are short), slope 21 (13).
      The sim cache can't reuse an old sim across this: its key is the sim's own inputs (start, pattern, seams).
      Not yet verified by a sim when written; drafting's blocks use the same measures uncompensated.
    - STATE at the usage-limit stop (2026-10-06, clothsim; branch worktree-agent-a2f0fa7013024989a, NOT mergeable):
      nothing after ly_03 is verified by a sim. Unverified, in order of risk: the taut tape + shoulder slope (every
      draft), the clean-up against the real body + crossings reverted for every garment + group welds, the fine
      settle's body offset fitted to the start (`_start_separation`), closures (band rows, relief, buttons in look /
      export / scene), `pressed` + the one-ring pad. Running when stopped: `cl_01` (zz_shirt with closures, scratch
      log clothsim/cl_01.log; its coarse sim is cached, the fine settle was waiting for the heavy slot; it was
      started BEFORE the shoulder-slope change, so its draft has the taut tape only). Next: judge cl_01 (front / cuff
      close-ups, clay + textured, against fl_17; seam gaps line; closures line), re-run it on the final measures,
      then `go.sh ly_03` again (ly_suit shirt re-simulates first), then pads (`support`), collar hug, vents (a
      lapped vent = one extension flat under, the other folded: both are folded under today), drafting's tailored
      collar (`{"op": "collar", "type": "tailored"}` on its branch, commit 112c5bf) in place of Jaeger's, Simon's
      cuff seam (-3.0%: sleeve hem 198.9 into a 205.1 cuff, probably the slit's lips). Gates old vs new measures:
      only pd_wrap changed (waist +11.1%, band +3..+10).
    - Seams (the user: "stitches super visible"): ZOZO leaves seams a few mm open (Jaeger mean 4.3 / p95 17.8 mm at
      stitch stiffness 1; drafting measured 30 closes them at 6x the time). `cleanup` welds sewn vertices as GROUPS
      (a vertex in two seams kept only its last pair), weighted toward interfaced vertices, and again after the push
      off the body. Gaps over 1.5 h stay: a seam the solver didn't close should fail, not be hidden.
    - Closures (`closures.py`, design-table / garment key `closures`; the user on the shirt: "doesn't have a placket
      or buttons"; schema agreed with drafting): {name, kind buttons | zip | hooks | tie, over, under (same piece for
      a cuff / waistband), holes / buttons mark prefixes or `at` pairs, edge {over, under}, band, size, lift, state
      closed | open | {open_above}}. `expand` -> the stitches (one per closed fastening), a vertex row on each
      band's inner line (a fold entry at 180 deg, `in_wrap`), zips' seams; `M["closures"]` = vertex pairs;
      after the sim `measure` (`res["closures"]`, the report, stage 5: fastenings closed, sides <= 6 mm apart, none
      lost in the mesh), `relief` (bands `lift` 0.8 mm proud) and `buttons_mesh` (`res["buttons"]`: discs with a rim
      on the over layer; in `look`). Stage 3 lists them and fails a chosen front_closure / cuff / fly with no entry.
      Simon's front and cuffs are entries now (its table's bare stitches are gone). Not done: buttons in the export
      and the scene, drafting's zip-in-a-seam / fly / waistband extension, `cloth_workflow.openings` reading state.
    - Open: the yoke ridge behind the collar; the upper sleeve's folds still read busy; Carlton pinned to
      `method: "simulate"` (upper-back pleat bunches, tail knife pleat is a seam gap, cap split +7.5 / -5.0%, stand
      +4%, collar +4.5%).
    - `made` (design table and garment: {piece or role: "made" | "draped"} through garment_design.made_or_draped ->
      `M["made"]` -> `made_pieces`): interfaced-whole pieces can be draped. Carlton's fronts are, with roll-line folds
      `lapel.L/R` (placement only so far: the fronts turn back along the roll line into a V; no facing, no sim).
      Fold flaps of torso pieces lie on their own base only (earlier torso pieces lap them either way).
    - Also: pattern ops `slit` (Simon's sleeve placket: the cuff's seam chain starts and ends at the slit, the cuff
      turned to it: `wrap.turn`, or the mean seam angle when unset) and `trim` (a band cut to the length of the
      edges it is sewn to); torso wrap `align_x`; Carlton's belt (joined at CB), tail vent as a lapped fold
      (seam check: back / belt / tail / side all within +-0.2%); `tests/test_folds.py`.
- Garments (2026-10-06, "garments" agent, branch `garments`: both cloth tracks merged; renders `cloth_renders/ga_*`;
  scratch DURABLE in /mnt/data/hifipushie/garments/: env.sh, run.sh <script> (worktree code on the main workspace),
  tests.sh, gates.py (stages 1-3 on every wf_ / pd_ / zz_ / ly_ / ga_ model), st.py (stages with the garment patched in
  memory), pl.py (place only: crossings by pair, closure start gaps, saves the start), rs.py (clay render of a saved
  start / result), lap.py (how an over band lies on its under piece, by height, for X0 / Vsim / V), band.py (a band's
  closed girth against the body's hull per level), seglen.py, dbg_d.py (a named edge after each draft op), run.py +
  q.sh <queue file> (sims one after another, logs <tag>.log, arrays out/<tag>.npz); prev/ = the two earlier agents'
  scripts. The sandbox refuses heredocs with code and loops: write a script file and run it.)
  - Gates: stages 1-3 no longer simulate a layered garment's under garment (the jacket's gate sat on the heavy slot);
    a garment with no design sheet is judged on its kind's `regular` fit band (was the first: slim); design-table
    `seam_notes` [{"seam": index, "ease", "why"}] (Simon's cuff is 3% longer than the sleeve hem because the placket
    strips aren't sewn on: declared, not hidden); two seam CROSSINGS near each other aren't a notch miss. Jaeger's
    armhole seam chain started at the front pitch and put the sleeve's top notch 27 mm off the shoulder seam (the
    sleeve sewn in rotated): the chain starts top <-> shoulder now. `pattern._points_on_outline` tolerance 0.1 mm
    (Carlton's rollLineEnd fell 2 um off the outline on the new measures and the table crashed). Carlton FAILS stage 2
    honestly (cap split +10.2 / -7.1%, collar on stand +4.5%, chest "+78%": sizing counts the lapel overlap): legacy.
  - `closures.seat` (in `build` after the clean-up, `cleanup.seat: false` turns it off; report line "lap ... laid
    closed"; `res["closures_sim"]` = the sim's own gaps): between the first and last closed fastening the over band is
    laid `LAY` 1.2 mm off the under piece along its normal, easing out over 3 cm; then each fastening's two sides are
    brought together in the surface (half each, sigma 2.5 cm, only up to 12 mm). Why: on the old shirt (lap.py on
    cl_01) the lap was 3-4.6 mm proud all down the chest (the solver's contact gap: construction, not physics, must
    close it) and 22-53 mm apart above the top button and 33 mm at the hem (the fronts part there: as worn, left).
  - Bands closed on themselves: `B["band_short"]` is now measured on EVERY path at the end of `place` (smooth only:
    Blender sews bands shut): the start distance between a piece's own stitched points > 12 mm. A torso band (a
    waistband, alone or among other pieces) lies on the hull of the narrowest level in its height at its closed
    girth, `BAND_CLEAR` 2.5 mm off at least (was 4 mm + the wrap's `out` 4 mm = 50 mm of girth: the trousers' band
    started 77 mm open, the skirt's 25); `B["band_clear"]` makes the ZOZO job run with body_offset 1 mm + contact_gap
    0.5 mm. Stage 4: pd_trousers and pd_skirt start closed. NOT VERIFIED BY A SIM when written (queue q3).
  - Neck bands: seated by their CLOSED girth when buttoned (not their length with the button extensions), and the
    hull is taken over sections that are the neck (8 mm above a 3 cm stand on this body's 3.5 cm neck the sections cut
    the chin, 44-48 mm forward: 6 cm of girth).
  - A buttoned collar is CONSTRUCTED closed (the coordinator's rule: a made band is held, not contact-solved, so it
    needs no solver standoff). `place`: a neck band with its own button stitch lies at its buttoned girth on the hull
    of the neck's sections, each round its own centre (`_cuff_spiral(recentre=)`; this neck leans: the centres drift
    8 mm over 3 cm, 2 cm of girth in one frame; each vertex is shifted by the drift at its height), over the band's
    own height from where it sits (a curved stand's ends are 1-2 cm lower in the pattern: the hull took in the
    trapezius), `HUG_CLEAR` 1.2 mm off the skin; `B["hug"]` (the stand and what shares its spiral) -> job array
    `hugIdx` -> cloth_zozo pins those held vertices with allow_intersection (free of body contact), the job runs with
    body_offset 1 mm + contact_gap 0.5, and a hug band's flap may lie HUG_CLEAR + 2 mm off the skin. Numbers (start):
    collarEase 0.03 -> 30 mm open, 0.07 -> 17, 0.10 -> 6, 0.115 -> 4 (closed, a layer apart): 410 mm round a 397 mm
    neck base = 13 mm of collar ease. The fall then stood up (turned 15 deg, every station at the same 8% = the
    stretch cap): NOT the roll line's curvature (plan radius 72 mm open and buttoned alike) but the 30 mm stand on a
    35 mm neck: pushed 7 mm off the chin, and the flap is turned from the unpushed row. collarStandWidth 0.055
    (20 mm stand; collarWidth 2.0 keeps the fall 44): no push, the fall turns 155 deg. Simon's table has the
    `collar` closure and these options now (ga_03_collar_closed_start.png: reads as a buttoned collar at 2 cm).
    NOT YET SEEN SIMULATED when written (ga_14 / the shirt under ga_11). A general rule is missing: the stand's
    height from the body's neck height (tailor has no neckHeight; `Body.neck_rows` has it: 35 mm here).
  - Seams after the clean-up (stitch stiffness 1 + group welds; shirt ga_01 on the final measures): the sim leaves
    p50 1.7 / p95 5.4 / max 8.8 mm, the clean-up p95 2.05 mm with 66 of 502 sewn pairs still open (target 0.5).
    Cause found: the pass that sends the clean-up's crossings back to the sim's surface also took every crossing the
    SIM itself has (the made collar's ends) and grew the patch two rings a round, undoing the welds round it; it now
    reverts only crossings the clean-up made (not yet re-measured). Stitch stiffness 8 is not a default: the shirt's
    2 cm coarse sim ran 27-30 s/frame (150 frames) against 287 s in all at stiffness 1.
  - Drafting: a SHAPED centre back seam (`contour` on centre_back) was dropped by the next style line
    (`_replace` asked for two points on x = 0): the blazer's back was open from neck to hem and stage 2 passed; a
    piece now keeps its centre if it holds an end of its named centre edge. An edge-form fold line on a piece cut
    on the fold runs on across the fold at unfold (a collar's roll line stopped at centre back). `collar` type
    "tailored" is laid from its seam (wrap "seam" + turn) with its roll fold `in_wrap`; KB front_closure
    `button_stand` (a jacket's 2-3 buttons below the break, no placket).
  - Model `workspace/ga_suit` (mk_blazer.py): ly_suit's shirt + a blazer from OUR blocks (bodice fitted, CB seam
    shaped, side panel with no side seam, lapel with straight gorge, tailored collar, fused facing, 2 buttons, bent
    two-piece sleeve; CB length 751 mm; gate passes; pattern sheet ga_02_blazer_pattern.png). Its START reads as a
    tailored jacket's pieces (lapels turned, seat covered), 11 crossing vertices, but the tailored collar is WRONG
    past the neck point: a band standing round the back of the neck that stops at the neck's sides, its seam to the
    gorge 156 mm away and turned 54 deg. Cause (construction): the op gives the roll line a constant stand height to
    the collar's end, and the collar is placed before the lapels are turned. In a real notched collar the roll line
    runs from 3 cm above the neck edge at CB down to the neck edge where the lapel's roll line meets the neckline;
    past that point the whole collar lies on the turned side, in the lapel's plane, sewn to the gorge. To build:
    the op's fold line from cbRoll to that point; placement of the part past it AFTER the lapel flap is turned, as
    a continuation of the flap (`lies_on` the turned lapel's plane), the part behind it as now.
- Suit (2026-10-07, "suit" agent, branch `worktree-agent-a79355cc3032d8bee`; renders `cloth_renders/su_*`; target =
  Garrett's concept `workspace/garrett_v20/concept_v8_front_apose.png`: charcoal two-button notched jacket worn OPEN,
  pale shirt with the top button open, flat-front trousers with a crease; he is seated in the game. Scratch DURABLE in
  /mnt/data/hifipushie/suit/: env.sh, run.sh <script>, q.sh <queue file> + run.py (one sim: report, OPEN SEAM lines,
  renders; `over=null` runs a layered garment alone; logs <tag>.log, arrays out/<tag>.npz), pl.py (place only),
  cu.py (close-up of a saved start / result: piece or x,y,z, half size, front | back | collar), seamdiag.py (one
  seam's gaps in X0 / V_sim / V along the seam), fs_dbg.py + fs_dbg2.py (where a fine settle's start is stretched,
  from the job's in.npz), pairs.py (a piece's sewn pairs in pattern coordinates), lap_geo.py (lapel / roll line
  numbers of a draft), ro_dbg*.py, gates.py, mk_garrett.py (model `su_garrett` = garrett_v20 COPY + ga_suit's shirt
  and blazer + pd trousers), tests.sh.)
  - VERIFIED BY SIM (first time for all three): trousers pd_trousers 2 cm (su_01: fits, band closed at CB, stays at
    the waist, seams 0.5 / 1.3 / 3.2 mm in the sim at stitch stiffness 8, 0 crossings; but a wide cropped pyjama
    cut, no fly / crease / loops); shirt zz_shirt 2 cm + 1 cm fine settle (su_05: 0 crossings, seams p95 0.24 mm,
    collar closed with the fall turned 155 deg and covering the stand seam 11 mm; "STRAINED at waist" 17.8%, front
    closure sides 12.1 mm apart, collar closure 8.1 mm; reads tall / tight / small points); blazer from our blocks
    alone, 2 cm (su_06: reads as a tailored jacket, 0 crossings, strain 0.4%; neck / gorge seam OPEN 12 of 12 pairs
    to 14.5 mm, shoulder seams 5-6 mm, CB seam 2.7 mm showing as a pale zigzag, back collar a fat roll, fall 108
    deg); Jaeger alone on the new measures (su_07: no longer a bomber in length, but CORRUPT: side seams open 17-34
    mm, armholes 30-36 mm, 165 of 336 pairs open at stitch stiffness 1, side panels crumpled, collar a band: legacy,
    the drafted blazer is the base).
  - Made pieces sewn to each other are ONE construction (`cloth._carry` groups them by seams, root = the piece with
    the most seam to draped cloth; `carry["roots"]`; `_constructed` and `_press_plan` fit the fine placement onto
    the coarse one on the root). Each fitted by itself, the shirt's collar landed 16-25 mm off its stand at all 43
    pairs and the fine settle died ("ccd failed", made pieces 277% stretched at the start): the shirt as merged by
    the garments round could not finish.
  - Notched collar (`op_collar` type tailored after a `lapel`; `_roll_meets_neck`): the roll line is a polyline from
    `stand_height` at CB down to the neck edge where the lapel's roll line crosses the neckline (profile exponent
    from the crossing angle so the two lines meet as one), given as the fold's points and as wrap `turn.line` (run
    on 16 cm as the lapel's roll line). `"roll": "parallel"` = the old constant stand.
  - Wrap "seam" (`cloth._on_seam`): `"worn": true` = the edge it lies on is each torso partner's point at its
    pattern x / height (y = 0 at hps) on the body's front / back (`worn_pt`), at the pattern's lengths from the
    middle: the old march headed for where the fronts START (15 cm ahead on their cylinder) and hugged the neck
    like a shirt band. Frames along the edge come from the body's normals 12 mm above the seam, smoothed (nearest-
    vertex normals in the neck / shoulder crease swung 60 deg), the piece's side of its edge from ONE handedness
    read at the edge's middle (per point by the centroid it flipped along the collar's slanting front: this was in
    the old code too). `turn.line`: points beyond the line are laid as their foot + distance in the turned
    direction; where the line has left the piece (and blended in over its last 5 cm) the point is reflected about
    the line in the pattern, carried into the PARTNER's pattern by the two exact seam pairs (the pairs between are
    off by up to 13 mm along the seam: fold rows on either side: a mesh fault, not fixed) and laid with `worn_pt`.
    Dead end: laying the collar's front as a continuation of the turned lapel where the lapel STARTS (the fronts
    start on a cylinder, the collar is made and held: 3.8x stretch).
  - Seam-wrapped pieces take the bands' clearance (SMOOTH_CLEAR), not the draped 12 mm (the collar's neck edge was
    held 8 mm outside the back neck). Blazer alone re-simulated with it (seamdiag.py, no render): neck / gorge
    seam 6 in the sim 2.1-5.6 mm (was 9-15) with ONE pair at 14.8 mm: the pair beside the roll rows, where the
    mesh pairs the seam's two sides up to 13 mm apart ALONG the seam (pairs.py: collar 0.132 <-> front 0.046; fold
    rows inserted on each side shift the pairing): fix that pairing in `cloth.mesh` next. The clean-up left all 12
    pairs as the sim had them (V = V_sim): the weld did not act on a seam between the made collar and draped
    cloth: not understood (same for the CB seam's 4 pairs at 2.7 mm: the pale zigzag).
  - Layered run (blazer over the shirt, su_08 / su_10): the GPU did NOT crash; ZOZO stops at frame 0, "ccd
    failed", start 1650-1750% stretched. From the job's in.npz (fs_dbg.py): only the COLLAR, 24 triangles to 9.6x
    at pattern |x| 0.09-0.13 (the roll's end / the blend into the front part), and in the layered job the collar
    is not carried (carryIdx empty) and rests on the flat pattern, i.e. it is not treated as made there. pl.py's
    start on `Ctx.body` shows only 1.58x: `build` places on `padded_body` (the pressed shirt, its collar round the
    neck), where the worn chart and the seam frames meet the shirt collar's surface. Next: place with build's own
    body (run.py's res["X0"] is saved in out/<tag>.npz only when the sim finishes: add a place-only path through
    `cloth.build`), find why the collar is not made / carried when `over` is set, and lay the jacket collar over
    the shirt collar (its stand OUTSIDE the shirt's, the "layer_collar" tell 10-20 mm).
  - `worn_pt` returns the point at the body's depth (not a body vertex: two points on one vertex = a rest triangle
    of no size).
  - Garrett: stages 1-3 PASS for shirt, blazer, trousers on `su_garrett`; never placed or simulated on him.
  - Tests: test_pattern_draft, _styles, _tailor, test_folds, test_cloth_workflow, test_cloth, test_cloth_layers,
    test_closures, test_cloth_check pass at 86629f8 (the worn_pt change after it: only the pattern / folds /
    workflow set re-run). No test yet for the notched collar's roll line, wrap worn / turn.line or made groups.
  - NEXT, the coordinator's order: (1) the blazer's neck / gorge seam by construction: re-run `q.sh` with
    "su_09 ga_suit jacket over=null" on the clearance change and read seam 6 / 7 with seamdiag.py (if still open:
    where does the collar's neck edge start against the worn neckline, and does the front's turned gorge reach it:
    the worn chart lifts the collar off_ + 6 mm), then the back fall (108 deg) with the shirt under; (2) CB seam
    zigzag: 2.7 mm should weld (limit 1.5 h): check `cleanup`'s weld on a seam between two draped pieces whose
    vertices were left by `seat` / the crossings revert, or whether the look's `welded_faces` draws it; (3) wear
    state: jacket `closures` state open (the `buttons` op makes stitches, no closures entry: CLOSURES [] in su_06),
    shirt collar open_above; (4) shirt collar proportions as a KB rule from `Body.neck_rows` (stand from neck
    height, fall = stand + 10-15 mm, points 65-75 mm), the 12 mm front gape and the waist strain (stage 2 ease says
    +23% at the waist: so the strain is the lap / buttons, not size: unexplained); (5) trousers: slim straight leg
    to a slight break, crease folds, fly, loops; first place + sim on su_garrett. su_08 (blazer over the shirt,
    the job that crashed the 890M in ccd_collision_edge_edge) fails at its start now: see above.
- Suit 2 (2026-10-07, "suit2" agent, branch `worktree-agent-a42af29b3a3f84fa9`, continues "suit"; renders
  `cloth_renders/su_2*`; scratch DURABLE in /mnt/data/hifipushie/suit2/ (the suit agent's scripts with W = this
  worktree, + run_main.sh <script> (MAIN's src on PYTHONPATH: before / after numbers), plb.py (the START as
  `cloth.build(place_only=True)` makes it, padded body when layered: made / carried, stretch by piece, crossings,
  seam start gaps), pairchk.py (sewn pairs' mismatch along each seam), welddiag.py (what the clean-up's weld does
  and which edges cross which triangles after it), gapgeo.py (a seam's gaps split along / across / normal),
  groove.py (a welded seam's vertices over the chord of their neighbours: pucker), collar_pat.py (the drafted
  collar against what it is sewn to), tests.sh (the nine cloth / pattern test files -> tests.log)).
  - Seam pairing (`cloth.mesh`): a fold line (and a roll's further rows) ending on a sewn edge moved the outline's
    nearest vertex onto itself on ITS side only (up to 0.6 h, 1.3 h for further rows): the seam's two sides were
    paired up to 15.7 mm apart along it (blazer collar / gorge, pairchk.py). Now the fold's ends are found first
    and added as samples of the seam on BOTH sides (and of every other seam the points land on: `sample(extra)`,
    `on_seams`, `at_fraction`); an end within `SEAM_JOIN` 0.15 h of a sample ends on it. 0.0 mm on all 15 seams;
    the blazer's start stretch 125% -> 39%, the sim's worst neck pair 15.0 -> 7.0 mm. EVERY garment with a fold
    ending on a seam re-simulates (Simon: its mesh changed).
  - Why the weld "did not act" on collar / CB / shoulder seams (V == V_sim): it welded, then build's crossing
    check sent it back. A solver leaves layers a contact gap apart (a made collar's fall on the back neck, a lapel
    on its front: 0.5-1.6 mm); a seam vertex welded 1-5 mm went through that layer by a fraction of a mm (134 new
    crossing vertices on the blazer), and the revert, two rings wide at once, reopened every seam within 4 cm.
    `cloth._weld_clear` (before the revert): a vertex whose move made a crossing loses the part of the move along
    the crossed triangle's normal, with the draped vertices welded to it; the revert grows ring by ring
    (`_crossing_hits` = the edge / triangle pairs). Blazer: CB seam 4 open pairs -> 0, shoulders 7 -> 5 of 9, neck
    seams still 1.3-6.6 mm (they end under the tangled collar ends: the collar, not the weld).
  - The CB "pale zigzag" is PUCKER, not a gap: the welded seam's vertices alternately 4 mm sunk / 5-9 mm proud of
    the cloth beside them (groove.py); the two sides share their samples (not an offset along the seam).
    `cloth._seam_relax` (cleanup option `seams`, default on): each closed seam smoothed along its own polyline
    (6 passes, ends kept, <= 2 x keep), the first ring following by half; seams with an interfaced side stay. The
    first version (toward all neighbours, 4 mm cap) took the median 2.0 -> 0.86 mm and still read as a zigzag;
    the along-seam version (su_25_blazer, scratch out/su_25_back.png beside su_21_back / su_23_back): CB, side
    and sleeve seams read as smooth lines, no welts or zigzag in clay at 2 cm. groove.py's number hardly moved
    (median 1.7, p10 / p90 -4.8 / 6.8 mm): it reads the first ring's own scatter and the back's curve, not the
    line: judge seams by render. su_25 also has the front as a closure: 2 of 2 closed, sides 2.8 mm apart.
  - Wear state: op `buttons` writes a closure (`D["pair_closures"]` -> `D["closures"]` at unfold: left over right,
    `state`, `size`; no bare stitches), `pattern_draft.build` returns `closures`, `cloth.pieces` takes them; a
    garment's `closures` entry is laid over the design's of that name key by key ({"name": "collar", "state":
    "open"}; {"name": "front", "state": "open"}); `cloth_workflow.openings` lists a closure worn open as fine.
    Docs: cloth_guide.md (Closures), the dress tool, garment_kb.json. NOT simulated yet (a shirt collar worn open
    falls back to the unbuttoned neck-band placement: unverified since the garments round).
  - THE COLLAR (the open job; the coordinator: before anything layered). ga_suit and su_garrett carry `"made":
    {"collar": "draped"}` since 10-06: the blazer's collar is wholly interfaced but rests on the FLAT pattern, a
    stiff strip bent round the neck = the fat roll in su_06 / su_20-23 (the clearance change did not cure it).
    Made (`made={}` on the command line), its lay (`_on_seam` worn + turn.line) is a ruff of spikes round the neck:
    36 triangles to 3.6x at the front ends (out/pb_alone_made_c.png); `cloth._true_lengths` (wrap key `"true":
    true`, off by default) brings every edge to its pattern length (max 1.06) but the SHAPE stays a crumpled ruff
    (out/pb_alone_made2_c.png): the lay is wrong, not the lengths. The PATTERN is right (collar_pat.py): neck edge
    199.6 mm = back neck 84.2 + front neck 115.4, spring 36 mm (outer 236 for 200), roll line from 30 mm at CB to
    the neck edge 113 mm round (29 mm past the neck point), where the lapel's roll line (break (-20, -400) to
    (58, -16) on front.L) crosses the neckline; the collar's last 87 mm is sewn to the lapel's top (hps side of
    the crossing to cfNeck (-14, -65)); reflected about the lapel's roll line that end lies at x ~105 mm, 89 mm
    under the neck point: on the chest. The lay to build (agreed with the coordinator): (a) from CB to the
    crossing, a back band standing on the worn neckline as an isometric cone, stand + fall folded on the roll line
    at the one isometric angle (as `op_shawl`'s annular sector / `folds.apply`); (b) past it the collar end FLAT in
    the turned lapel's plane, placed AFTER the lapel flap is turned (`lies_on` / `_lay_on` on the turned lapel, or
    the reflected pattern point laid with `worn_pt`: the seam's pairs are exact now, so the two-pair rigid fit in
    `_on_seam` can use all of them), sewn along the gorge. Targets at the START (plb.py): neck seam p50 < 10 mm
    against the WORN neckline (today 128-135 mm: the fronts / backs start on their cylinder, so measure against
    where they will be worn or accept this number for a carried piece), no triangle over 1.3x, 0 crossings; then
    made + carried in the sim, then `over`.
  - Layered run su_24 was stopped unrun (a known-bad collar). The 9.6x layered start was measured BEFORE the
    pairing fix; `plb.py ga_suit jacket <tag>` (no over=null) shows the layered start once the shirt is re-simulated.
  - Tests: test_folds (+ test_fold_ending_on_a_seam_keeps_the_seam_paired), test_cloth (+ test_weld_beside_a_layer_
    stays_welded), test_closures (+ test_drafted_buttons_are_a_closure_with_a_wear_state), test_cloth_layers,
    test_cloth_check, test_cloth_workflow, test_pattern_draft / _styles / _tailor passed after the closures commit;
    re-run tests.sh after the along-seam `_seam_relax`. Still no tests for the notched collar's roll line, wrap
    worn / turn.line, made groups (`_carry` roots).
  - NEXT, in order: (1) (done: su_25 judged, tests.sh green); (2) the collar's made lay (above); (3) the layered start
    (collar made + carried under `over`; `cloth_layers.tells`); (4) Garrett's wear state simulated (jacket front
    "open": do the fronts hang straight or spread? shirt collar "open"); (5) trousers (slim straight leg, crease
    folds, fly, loops / belt); (6) shirt collar proportions as a KB rule from `Body.neck_rows`, the 12 mm front gape
    and the 17.8% waist strain by numbers; (7) all three on su_garrett against the concept. Not touched: 4-7.
- Suit 3 (trousers, shirt) (2026-10-07, "trousers" agent, branch `worktree-agent-a5aa4e100572bcb0c`; scratch DURABLE
  in /mnt/data/hifipushie/trousers/: env.sh, run.sh <script>, tests.sh, q.sh <queue file> + run.py (one sim: report,
  renders incl. trims, `_waist`, `_waist_tex`, `_hem` close-ups for trousers), plr.sh <model> <garment> <tag> (the
  START: plb.py + a clay render out/<tag>.png, log <tag>.log), st.py (stages with patches), psheet.py (pattern sheet
  image), meas.py (tailor measures), parts.py (a model's shell parts), mk.py [garrett] (model `tr_trousers` = the
  test body + suit trousers; su_garrett's cloth.trousers replaced by the same sheet)). PATTERN WORK ONLY: NO SIM RAN
  (root disk under the sims' 20 GB floor: 14 GB free, /tmp/claude-1000 = 41 GB).
  - A kind that drafts itself: `kinds.<k>.draft` {block, block_options, fit_options per fit}, and a detail choice's
    `draft.ops` (its operation, added unless the sheet's own ops hold one of that name; `{"choice", "op": {...}}`
    patches it) and `trims` (`garment_design.compile_sheet`). `{"kind": "suit_trousers", "fit": "tailored"}` alone
    -> trouser block + waistband (opening front) + fly + crease + belt / loops. Evidence types `closure` (kind, on
    role) and `trim`. Sheet -> garment key `trims` (NOT_SIM).
  - Block (`pattern_blocks.trouser`): `leg` = LEG_CUTS skinny / slim / tapered / straight / wide (`leg_cut`: knee =
    knee girth x (1 + ease), never under calf x (1 + ease); hem = a share of the knee, never under heel + 20 mm);
    `tailor.measure` has upperLeg, knee, calf, ankle, heel (`_leg_girths`; heel = a 45 deg plane through the
    ankle). `dart_taper` (a shaping point on each dart leg 35% from the tip: the tip's angle under half), `dart_length`.
    Garrett tailored: knee 428 mm round, hem 377 (heel 342), seat +4.7%, thigh +17%.
  - Ops (pattern_tailor): `crease` (press fold on the piece's `crease` line, angle 205 = a ridge OUT, strength 0.6,
    `in_wrap`, `reach` 5 cm; a fold must cross its piece so the back's runs to the waist too), `fly` (point flyEnd on
    the centre front; `edges.centre_front` becomes the part below it; `pair_closures` kind zip -> at unfold a
    closure {zip, front.L over front.R, seam = the opening}; line `fly_stitch` (a J) kept on the over piece only;
    `cloth.mesh` carries lines named *_stitch as `M["stitch_lines"]`, `detail_maps` draws them as dashes: NOT yet
    seen in a render). `waistband` `opening: "front"`: chain front.L -> back -> front.R, `garment_blocks.generate`
    `extension: "end"` (lapEnd; button on the extension at the high-x end), wrap side "back" + `over: "low"` (the
    lap ramp in `cloth.place` on the low-x end). No band row for the fly's facing: an offset line would end inside
    the piece (folds must cross).
  - `cloth_trims.py` (`validate`, `check`, `meshes(res, g)`): belt (a strap of rectangular section on the band's
    middle line, the over end a thickness out, a buckle box at the buttonhole mark) and belt_loops (strips from the
    band's top over the belt to its bottom) built from the finished band's chart (pattern uv -> position / normal);
    in `cloth.look` and run.py; tested on a synthetic band only (test_trims_ride_a_band), NEVER seen on a sim.
  - Stage 2 (`cloth_workflow.leg_ease`): seat ease from the centre seam's line to the side seam (the forks lie
    between the legs: a 5% draft read +13% on the test body, whose seat line is 6 mm above its crotch); a hem that
    ends on the foot is judged against the heel girth (it read TOO SMALL against the foot's section).
  - Start (`plr.sh su_garrett trousers pl_g2`, out/pl_g2.png): band closed, 0 crossings, but the leg wrap is ONE
    vertical cylinder per leg as deep as the seat: a slim leg's front and back start as slabs, side seams 174 /
    inseams 213 mm apart (p50), the front hem pushed 32 mm off the foot (2 triangles 2.25x), waistband seam p50 223
    mm (the fronts / backs are far from the band, not a mis-ordered chain: check it once the legs start closer).
    Stage 4 fails on it (start past the strain limit on 0.8% of the triangles). The fix to build if the sim can't
    sew it: below the crotch lay each leg's pieces on the leg's own sections (a tube on the hip -> knee -> ankle
    axis, as sleeves on the arm), blended into the torso cylinder over ~10 cm at the crotch. The foot is left out
    of the leg hull (z under ankle + 4 cm).
  - Shoes: his `shoes` part is an 8 mm shell of the foot and the soles lie inside z 0..15 mm: the bare foot stands
    in for the shoe; length "shoe" (hem 30 mm over the floor) is cut for it. Not added to the collider.
  - Darts as "open tucks" in su_01: argued, not measured: pucker of the welded seam (suit2's `_seam_relax` came
    after su_01), the unshaped tip, 10% seat ease. Verify on the first sim's back close-up.
  - Tests: the nine files green at 9b66b6f (tests.log); new in test_pattern_tailor: leg cut, shaped dart, crease /
    fly / front waistband, the kind drafting itself, trims.
  - NEXT, in order: (1) free the disk, then `bash q.sh q1.txt` (tr_01_trousers su_garrett trousers, 2 cm ZOZO
    draft); judge 4 views + _waist / _waist_tex / _hem against the concept (stays at the waist, crease a line,
    one break on the foot, no puff, darts, fly J, belt + loops sitting on the band); (2) if the legs don't sew or
    crumple: the leg-following start above; (3) pattern sheet tr_00_trousers_pattern.png is judged (reads as a
    tailored trouser); in-seam / slant pockets exist as `pocket` type in_seam, not added to the kind; (4) the
    SHIRT, untouched: collar rule from `Body.neck_rows` (stand from the neck's height, fall = stand + 10-15 mm,
    points 65-75 mm, spread for an open collar) through Simon's options, the 12 mm front gape and the "waist
    strain 17.8%" at +23% ease by numbers, then worn with `{"name": "collar", "state": "open"}`; (5) trims in the
    scene / export, a hem's break as a stage 5 target, the back crease ending at the seat.
- Suit 3 (2026-10-07, "collar" agent, branch `worktree-agent-a5c847e94d5c52d32`; renders `cloth_renders/su_30..32_*`;
  scratch DURABLE in /mnt/data/hifipushie/collar/: env.sh, run.sh, q.sh + run.py (renders now draw seams WELDED),
  p.sh <tag> [-o] (blazer alone, collar made, place only; `-o` = the open start; collar numbers, CB column, notched-lay
  info, worst edges), pl.sh (the same layered), pv.sh (p.sh + close-up), plb.py, cu.py (welds closed seams unless
  `raw`), clr.py (collar neck edge vs partners: clearance off the body), fg.py (a seam's pairs: sim / final gap),
  gapgeo.py, zig.py (a seam's line vs itself smoothed), hps.py (where collar / front / back put the neck point),
  unmade.py, tests.sh (the nine + test_collar)).
  - THE NOTCHED COLLAR'S MADE LAY (`cloth._notched_lay`, wrap `lay: "notched"`, set by `op_collar` type tailored
    when the lapel's roll line meets the neck edge): two parts meeting where the roll line comes down to the neck edge.
    The band: the stand runs up the body from the WORN neckline at the seam's clearance (`hug`), the fall turns about
    the roll line station by station as far as clears what is under it (172 deg at CB, ~150 at the neck's side). The
    end: FLAT in one plane through the lapel's roll line (as worn), turned about that line until it rests on the
    chest (a board bridges hollows), isometric (edges 1.00). Stations share position / tangent map / normal / turn,
    smoothed along the line; the sewn edge is a spline (laid per sample, the stand jumped 12-15 mm at every sample);
    the end's plane takes every point past the meeting point ALONG THE NECK EDGE (by foot on the roll line the outer
    end fanned 2-3x), eased over `NOTCH_BLEND` 4 cm; nothing turned stands over `NOTCH_BRIDGE` 12 mm off the body
    (the plane run on past the shoulder's ridge stood up as a wing); a relax pass draws in long edges (`lay_limit`).
    In `_on_seam`: `worn_pt` keeps to the body's own back / front (at the nape the nearest vertex in x, z was the
    throat's: the back neckline charted 9 cm forward) and past the outline sits on the shoulder's top; the worn
    neckline is a CHAIN at the pattern's lengths pulled toward the chart with a fading pull (`lay notched`; smoothing
    the chart and snapping it out walked it 1-2 cm up the slope). Start (blazer alone): collar max 1.15x (p99 1.06),
    0 collar crossings; layered over the pressed shirt 1.10x (9.6x in su_08). LAY_INFO[piece] keeps the lay's numbers.
    The worn neckline rides 1.5-2.5 cm higher than the chart (the chain keeps the pattern's length, the neck narrows
    upward): the jacket's neckline is cut to sit there, and the sim's back sews up to it.
  - SEWN ON OPEN, THEN ROLLED (`_open_start`, method settle): the sim starts with the fall standing open
    (`NOTCH_OPEN_DEG` 40 from the stand, eased in over `NOTCH_OPEN_FADE` 8 cm from the meeting points) and the
    carried poses turn it down (`NOTCH_OPEN_STEPS` 1 / .75 / .5 / .25, last pose closed). Laid down from the start
    (su_30) the fall was a LID over the seam: the draped back came to rest on top of it, 14 mm off the neck, the
    neck seam open at 13 of 13 pairs. build's arrays X = `Xstart`; rest stays the closed lay.
  - su_31 (blazer alone, ZOZO settle 2 cm, 443 s): reads as a tailored jacket, fits, 0 crossings, strain 0.6%; the
    collar hugs the neck and lies on the back (stand off the neck at CB 7 mm, fall 157 deg over the seam, no roll).
    Left: neck seam 10 of 13 pairs open (back neck pairs overlap 5-7 mm, 3 of 5 weld; the NECK POINT: front.L's hps
    sits 16 mm forward of the collar's along the seam and 7 mm further out, shoulder seam open ~10 mm there: front,
    back and collar disagree on hps; gorge 1-11 mm). Not fixed.
  - The "CB zigzag" was never in the garment: the scratch renders drew raw faces (two rows of vertices per closed
    seam, each with its own normal). look_cloth welds (`welded_faces`); the seam line is smooth (zig.py: su_31 final
    max 3.6 mm). `test_cloth::test_cleaned_seam_is_a_smooth_line`.
  - `_collider` drops the under garment's sliver faces (`UNDER_SLIVER`): ZOZO refused the layered job ("degenerate
    shell face" in the pressed shirt).
  - ga_suit / su_garrett: the jacket's `made: {collar: draped}` override is gone (that is why su_10's layered job had
    no carried collar).
  - su_32 (blazer OVER the shirt, first finished layered sim, 2 cm): BAD. The jacket collar stands high round the
    shirt collar (collar_show -19 mm: the jacket covers the shirt collar; collar_hug 27 mm), shirt shows through
    at the armholes / shoulders / back side seams (seams 0-11 open 22-63 mm), cuffs hidden (-29 / -33). The armhole
    and side seams open is NOT the collar: alone (su_31) they close; under `over` the draped jacket is placed on the
    padded body and its seams don't close. Diagnose that first (plb.py layered: start gaps / start stretch by seam vs
    su_31's; padded_body thickness at the armholes), then lay the jacket collar on the shirt collar's OUTSIDE at
    the jacket's own neckline height (the shirt collar 10-20 mm above it at CB): today `worn_pt` reads the padded
    body, whose neck is the shirt collar's cylinder.
  - Tests: the nine cloth / pattern files + test_collar pass (main 17ee597 merged in); merged to main at 2aea2ac.
  - NEXT, in order: (1) su_32's open seams under `over`; (2) the jacket collar against the shirt collar (layer tells);
    (3) the neck point (front / back / collar on one hps: the worn chart of front.L at hps vs where the draped front
    settles; maybe the front's lapel fold start near hps); (4) Garrett's wear state (front open, shirt collar open)
    and su_garrett.
- Seams (2026-10-07, "seams" agent, branch `worktree-agent-ae98ecda411a37796`; the user on the suits: "seams look huge
  and structural"; renders `cloth_renders/sm_01..08` (before = main 2aea2ac / after, the SAME cached sims: su_31
  blazer, su_05 shirt; sm_05 = raking light across the blazer's side panel seam); scratch DURABLE in
  /mnt/data/hifipushie/seams/: run.sh / runb.sh (this branch / main 2aea2ac's src in orig/), prof.py (load a cached
  result: `load(model, garment, patches)`; cross profiles, too few points at 2 cm to trust), m2.py (per stage the
  angle between a seam's two sides' normals vs the cloth's own: THE measure), orient2.py (winding per seam), rs.py
  (clay + textured sheets + close-ups of a cached sim), rk.py (raking-light close-up of one seam), cmp.py).
  Three causes, by measure:
  - WINDING: the pattern mesh winds each piece as its pattern lies; on the blazer back.L/R, top.L, under.L faced IN,
    the rest out (side seams' two normals at 160 deg). Welded, the shared normal cancelled into a pale / dark line;
    Solidify (offset 1) grew one side out and one in; the export's single global flip kept it, its inner shell went
    out on those pieces. `piece_flips` / `oriented_faces` (seam votes, max spanning tree over pieces, then out from
    the body) in every look (`welded_faces` orients; textured looks now weld too, with per-corner uv `uv_corner`),
    the scene's faces and the export (`shared_normals`: a closed seam's vertices one normal). A body-majority rule
    per piece was wrong for folded pieces (the collar's fall outweighs its stand). M["F"] (the sim's) is unchanged.
  - The FREE HINGE: a solver stitch passes no bending, so each side's last rows tilt alone: after the weld the sides'
    normals met at 29 deg median (side seams 20, CB 45, sleeve 30-37) against the cloth's own 10.
    `cleanup.press` (`_seam_press`, PRESS reach 3 cm, 40 Taubin passes, cap 0.4 h; welded groups move as one, ALONG
    THE NORMAL only: a uniform Laplacian slid seam vertices 6 mm in plan, a zigzag; interfaced cloth and "welt" seams
    stay): blazer 29 -> 14 deg (side seams 6-12), shirt 26 -> 14 (yoke 19 -> 7). The shirt's side seams stay 22-31 (a
    deep fin from the sim, not cap-limited). What's left on sleeves is mostly the 2 cm tube's own curvature.
  - The MAPS: a 1.2 mm groove 2.5 mm half width with 0.6 mm ridges 5.5 mm out each side, darkened 45% in the base
    colour, topstitching 6 mm in on EVERY edge. Now seam finishes (garment_kb.json `seam_finishes`, `seam_kinds`,
    detail `seam_finish` / `seam_finishes`; kind default `kinds.<k>.seam_finish`): pressed_open 0.3 mm x 0.7 mm, a
    0.12 mm rise over the allowances, no rows; felled two rows on one side (shirts); welt = the old look, not pressed.
    Hem topstitching from the kind's hem (`hem_topstitch`: blind hems none). Cavity 1 + H / 4 mm, floor 0.7.
  - Before was rendered with main's textured look on RAW faces: every seam was also an open boundary with Solidify
    rims (the stair-stepped pale beads in sm_05).
  - Tests `tests/test_seams.py` (winding, press, finishes in the maps, export normals) + the ten cloth files green.
  - Open: the shirt's side seams (a fin the press can't flatten: look at why the sim folds there), sleeve seams at
    2 cm, a "toward" side per seam for pressed_to_side / felled (today the seam's second piece), seam finishes in the
    pattern sheet, closures / collar seams were not judged one by one (made pieces are interfaced: untouched).
    Careful: `cloth.export_part` / `garments(simulate=True)` STARTS SIMS for uncached garments (an orphaned ZOZO job
    of mine had to be killed): test exports on cached models only.
- Suit 4 (trousers, shirt) (2026-10-07, "trousers2" agent, branch `worktree-agent-a06095d1485fd23a1`; scratch DURABLE in
  /mnt/data/hifipushie/trousers2/: the trousers agent's scripts with W = this worktree, + sdiag.py <tag> [1.05] (start
  stretch: largest principal stretch by piece and height band, p90 per band, the waistband's seam pairs), tdiag.py /
  vdiag.py / col.py (one band's triangles: row / column stretch and shear; one piece's column of vertices), legsec.py
  (the leg's sections), wstrain.py <npz> (a sim result's stretch vs the pattern by piece and direction), marks.py (the
  closures' fastening pairs, flat and at the start), collm.py <model> (neckHeight, collar options, the drafted collar's
  stand / fall / points), neckrows.py, t1.py <test file> <tests...>, run_base.sh (code at ./base, a detached checkout
  of another commit: `git worktree add --detach base <commit>`), patch_*.py (the sandbox refuses heredocs with code)).
  - Trouser legs START ON THE LEG (`cloth._leg_tube`, wrap "follow": false = the old seat cylinder all the way down):
    below the crotch each leg's front + back go on a tube square to a smooth leg axis (quadratic through the
    sections' plan middles), its section the leg's own (radius per direction smoothed `LEG_SMOOTH` up and down)
    pushed out to the cloth's girth (+ `LEG_APART` per seam, >= `LEG_CLEAR` off the leg; `LEG_TAPER` caps how fast
    the girth may fall, 5 = off), front crease line on its front, the back's half the girth round, pattern length
    along the axis, the leg under `LEG_EASE` over the ankle compressed until the hem clears the foot; blended into the
    seat cylinder over `LEG_BLEND` 15 cm under the crotch (the seat cylinder now stops just under that). su_garrett
    start: side seams 174 -> 15, inseams 213 -> 8 mm (p50), 0 crossings, every triangle within 5%: stage 4 passes.
  - THE FIND: a start whose edges are all within 5% can be 9-12% stretched (principal) along the diagonal: a column
    leaning 0.1 against its rows is already ~5% (shear is first order). A tube that narrows down a leg leans its
    outer columns by about a quarter of the narrowing rate; horizontal rows on a leg splayed 11 deg are a shear of that
    slope; a row anchor (the piece's row middle) drifting toward the fork shears the top of the thigh. `_relax_strain`
    (in place()'s start relaxation, after `_relax_stretch`): per triangle the deformation's singular values clamped to
    1.03 (compression left), vertices drawn toward that shape, Jacobi, 300 iterations, 6 rounds with the body clearance.
    It took the trousers from 24-27% of the triangles over 5% to none. Fold rows are held there EXCEPT a trouser leg's
    in-wrap press folds (the crease: held, it pinned a leaning column's shear). It runs for every smooth (ZOZO) start.
  - Front-opening waistband laid the wrong way round (seam p50 223 mm, "half a turn"): its chain starts on the left
    front and runs round the back, laid from the back centre it went to the left first; wrap `"dir": -1` (pattern +x
    round toward -x from the start), set by op_waistband's front opening. Band seam p50 now 54 mm (the seat cylinder
    is wider than the band at the waist).
  - Shirts are WORN as their kind is (the user: "a dress shirt with no tie would have top button unbuttoned and
    open"): garment_kb `kinds.shirt.wear` {no_tie, tie} closure overlays (garment_design.wear, laid in cloth.pieces
    before the garment's own), garment / sheet key `tie` (default false): collar "open", front `{"open_top": 1}` (new
    closure state: the n highest fastenings undone, by their mark's height). Every Simon shirt now starts open.
  - Unbuttoned stand: `_open_closure` (girth from the open closure's fastening pair) and a branch in place()'s neck
    code: seated and laid like a buttoned stand (hull of the neck's own sections over the band's height, recentred),
    no lap, its ends `NECK_OPEN` 35 mm apart at the throat. su_garrett: 114 -> 35 mm open, collar 2.2x -> 1.15x.
    NOT YET SIMULATED: do the fall and points spread into the concept's soft V? The stand is made / carried rigid, so
    the start's gap is the worn gap: judge it on the first sim and tune NECK_OPEN.
  - Collar proportions from the neck: garment_kb `kinds.shirt.collar` + `cloth.collar_options` (design tables with
    `"collar_rule": "simon"`): stand = tailor `neckHeight` (the neck's base up to the jaw landmarks / the girth run) -
    13 mm in 20-35 mm, fall at CB = stand + 12, points 70 (Simon's collarBend solved on its own collar geometry).
    Garrett: neckHeight 29 -> 20 / 32 / 69.6 mm (Simon's table defaults gave 22 / 44 / 57); the test body 40 -> 27 /
    39 / 76. Every Simon shirt's pattern changed. A garment's own pattern options still win.
  - "STRAINED at waist 17.8%" (su_05) was not fit: the pieces' interiors stretch p95 1.5-2%; the worst triangles are
    the fronts' x~0 placket fold rows (0.3x across, 1.5-2.3x along). fit() leaves fold rows out like seam rings. Not
    yet re-read on a sim. The 12 mm front gape: the fastening pairs match in the flat (dy 0) and start 4 mm apart; read
    it on the next sim (the folded placket's layers + contact gaps, or closures.seat reverted).
  - Stage 4: pieces crossing where they are sewn / stitched (or a piece itself) warn instead of fail
    (`cloth_workflow.sewn_crossings`): ZOZO starts with existing intersections allowed and su_05 simulated clean from
    them. The shirt's start on su_garrett has back/sleeve, collar/stand, cuff laps crossing: pre-existing (the base
    17ee597 too), open. Its torso pieces still start as slabs (side seams ~125 mm apart).
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
- Style sheets (`stylesheet.py`, `styles/*.json`, guide 5c; 2026-09-29, the golfer): the user's verdict was "stylization
  is an artistic decision, not just make the eyes bigger", so a style is a bundle of decisions. `spec.style.sheet` names
  a sheet whose partial spec (base.style incl. `simplify`/`simplify_keep`, head fit/pose defaults, part `subsurface`,
  paint layers on the `lm_*` landmarks, `style.look` lights) sits under the model: `store.load` resolves (model wins
  key by key, null deletes), `store.save` strips back to the model's own. `style_check` measures the sheet's `rules`:
  posed face ratios (`base.posed_measures`), the eye opening seen from the front (`base.eye_opening`: the skin runs
  on into the socket, so there's no edge loop; where the eyeball stands in front of the skin), iris share via
  `IRIS_SPOT` (a spot's front diameter is 1.83 x its width on the eyeball), skin HSV lit vs shadow sampled from a
  render in the sheet's look (sample off the stubble). GNM: `fit` gained nose_width/mouth_width/eye_seam, but the
  identity space can't make a short philtrum (chin/philtrum stuck at ~2.2): `head.pose` (least change of the
  regional expressions on landmark moves: smile, mouth_raise, lids, brows) does it. `look` lighting: `style.look`
  (suns, world, AgX look); a pink-warm bounce fill is what turns skin shadows red (hue shift 2 -> 5 deg). Paint
  `outline` (a closed polygon of landmarks seen along a view dir: lips, a beard border) replaced paths for lips and
  stubble: paths through the mouth crease seated into the seam and painted blobs at their control points. The
  written sheet: `workspace/character_renders/style_sheet.html`; renders s01-s0x there.
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
  Admission by memory (2026-10-07, "slot" agent; the one slot cost hours of hand coordination between sessions, a
  waiting export said "running", the lock wasn't FIFO, and a cancelled export_terrain held it for an hour):
  `resources.heavy(name, log, gb=, kind=, gpu=, model=)` declares a peak (GB; else `estimate(kind, model)` = the
  `KIND_GB` default, RAISED by peaks measured on earlier runs in ~/.cache/hifipushie/heavy_peaks.json, never lowered:
  a pool sized from its grant would measure less each run and shrink itself). Admitted when the running jobs'
  declared peaks + its own fit the budget ($HIFIPUSHIE_HEAVY_GB, default RAM - max(8, RAM/3): 40 GB on this 60 GB
  laptop) and, if others run, what's really free (MemAvailable - reserve - what running jobs declared but don't use
  yet); a lone job always runs. The rule, in order: FIFO by when a job started waiting; a waiting job that doesn't
  fit blocks every younger one, except SMALL ones (<= 25% of the budget) that fit now, and each blocked job can be
  passed at most PASS_LIMIT 3 times (no starvation). GPU jobs (`gpu=True`: local ZOZO; `gpu_claim()` for a GPU
  stage inside a job) run one at a time, FIFO among themselves, and don't block others' memory. Pools inside a job
  size from its GRANT (`workers()` = min(grant - 1 GB, free memory) / per worker): two jobs both seeing "free" memory
  is how the desktop died. $HIFIPUSHIE_HEAVY_SLOTS=1 brings the one-at-a-time behaviour back.
  State in $HIFIPUSHIE_HEAVY_DIR (default $XDG_RUNTIME_DIR/hifipushie): jobs/<id>.json + jobs/<id>.lock (flocked by
  its owner while alive; a lock anyone can take = a dead owner, swept), all decisions under queue.lock, polled every
  ~1 s (no CPU). Old code's slot heavy0.lock: every new job holds it SHARED (old code's LOCK_EX waits), an old job
  holding it is counted as LEGACY_GB 12. A waiting job logs "waiting for memory: needs X GB, Y of Z declared; held by
  <name (pid, GB, since)>; N ahead of you" (cloth also into its progress); export_asset's reply says how long it
  waited; `resources.status()` / `status_text()` / MCP tool `heavy_status` show running + queue + why.
  Fork safety: every state fd is closed in forked children (`os.register_at_fork`, never LOCK_UN there: the lock
  belongs to the parent's open file description) and is O_CLOEXEC; a forked child of a holder passes through
  `heavy`. Cancellation: server.py runs every sync tool via `anyio.to_thread.run_sync(abandon_on_cancel=True)` under
  `resources.cancel_scope(event)`, set when the call is cancelled or the client goes; then a waiting job leaves the
  queue, and a running one has its `track`ed subprocesses (process groups: `resources.run` replaces subprocess.run
  for Blender in asset / scene / veg_look; cloth Popens tracked) and `guarded` pools killed, `Cancelled` raised IN its
  thread (PyThreadState_SetAsyncExc, once; cleared if the job ends first; `cancel_scope` releases a grant left
  behind), and `profiling.run_jobs/pool_map` check between jobs. `dress`'s background sim thread is not under a cancel
  scope on purpose. Tests: tests/test_heavy.py (+ heavy_job.py), own state dir, ~10 s.
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
  Douglas-Peucker once per LOD, nested (LOD k keeps a subset of LOD k-1; rows joined along a chain and closer than
  1e-3 voxel are welded into one first, in the chains and every tile's dense mesh, `_weld_rows`: two crossings 7e-7 m
  apart were one float32 vertex in the GLB, a degenerate sliver and a non-manifold edge in pebble's karst passage;
  pebble welds 180), and both tiles collapse the dropped border
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
- Cliff overlay + baked maps (2026-09-29, "cliffs" agent; the user: games put 3D cliff faces over the heightmap, and
  the caves read low-poly/sawtooth). export.tiles `mode`: "cliffs" (default) | "full".
  - `terrain_cliffs.py`: `Region` (S = steep > `cliff_slope` 42 deg + the rock character's mask, grown `cliff_margin`,
    and round openings; pointwise, a grid read bilinearly), the ground = heightmap eroded in plan by a ball of radius
    push x S (push = relief + 0.6 m, only `push_open` 0.9 m round openings: pushed deeper round a lava skylight it
    went through the tube's roof and every round of holes pushed it further), holes = heightmap cells standing in a
    void (iterated with the region). `CliffField` = a closed rock shell: front = the full field with its ground part
    sunk by sink x (1 - S), back = `thick` m behind the smooth ground or `cave_wall` m round a void, joined by smax
    (a hard max shaded shards); where sink(1 - S) > thick it pinches out buried: no open edges. Points away from the
    region and voids return +1e3 (air), so each void's box is grown to hold its whole shell (the tube's own box is cut
    ~2 m under its floor: the shell ended in a flat face there with zero normals). The same tile machinery meshes it
    (`_tile_mc` reads `zpad`/`vol_pad`, `empty` skips tiles); faces off the visible front are primitive role
    "buried" (the seam check merges them for structure, shards count the visible ones). Ground tiles:
    heightmap npy/png, holes png, grid GLBs (stride 2^k, vertical skirts), `ground_check` (borders, heightmap never in
    a void, never through a cliff face).
  - `terrain_sharp.py`: extended marching cubes on the exact field (per cell with a normal cone > 20 deg: QEF vertex,
    fan, flip edges onto the crease; patches at tile borders keep their boundary, so chains stay canonical) and
    `crease_error` (sharp edges' distance off the surface, face normals vs the field's). Modest on its own (dense tile:
    crease p95 7.2 -> 6.5 cm, normals p95 17.9 -> 16.1 deg): half the sawtooth was sub-voxel bed ramps, now 2 voxels
    wide in the meshed field, the crisp notch in the maps.
  - `terrain_bake.py`: per tile per LOD its own atlas (faces labelled by the axis they face, smoothed; components;
    split where the projection overlaps and where longer than half the atlas; placed bottom-left on 4-texel blocks by
    FFT correlation; atlas as tall as used), then every texel projected onto the front field + `micro_relief`
    (bake-only facets 1.2/0.45 m, cracks, the bedding notch, laminae; band-limited to the LOD's texel: unfiltered it
    aliased and the two sides of a border disagreed), normal (tangent, +Y up the image, our TANGENT), height,
    AO (field SDF samples along 5 directions), base colour and weights from a 0.4 m normal (the fine normal flipped
    rock/grass per texel), roughness. Gutters are baked by extrapolating the nearest chart triangle. Ground maps use
    planar uv with texel centres on the tile edges (a half-texel inset put the sides a texel apart). The Materials
    bed tone eases between beds (a step aliased). `map_seams` decodes both sides' maps at shared border points
    (limits per LOD `MAP_SEAM`). Tiling layer textures (`layer_textures`: tileable spectra, no Voronoi honeycomb) +
    the manifest's `engine_recipe`; `render_tiles(textured="layered")` builds it in Blender (box-projected height per
    layer x _WEIGHTS attributes modulating the baked colour and bumping the baked normal).
  - Lessons: a close view magnifies texels: sharp features in maps stair-step (the bed notch at 10 px/m), so LOD 0 is
    16 px/m and map features are smooth at the texel; geometry creases below ~2 voxels mesh as sawtooth whatever the
    mesher: put them in the maps.
  - Round 2 (after the user saw seams and the machine OOM'd twice): NEVER filter across an atlas image (a sparse
    texel grid + blur bled each chart into its unrelated neighbours: lines along every chart edge, tile borders
    included): AO is per vertex (identical both sides of a border) interpolated per texel, the 0.4 m normal per texel.
    Tangents MikkTSpace-style (Blender's glTF importer ignores TANGENT; so do most engines). Colour tone from smooth
    noise (the facet lattice made a checker of squares). `map_seams` decodes every channel from both sides of each
    border (world normal, colour, ORM, height, weights) at each LOD and LOD 0 vs the coarsest; `scratch`-style check in
    Blender (its own tangents) agreed (p95 2.7 deg at LOD 0). `terrain_cliffs.floating`: pieces of the cliff meshes
    that never reach the heightmap fail the check (a 3 m fin's top cut off by relief, 14 m over the sea; sealed air
    pockets between the shell and the rock round a cave). Causes fixed: `Field.thin` (a grey opening of H: fins and
    stack tops narrower than twice the relief's reach take 10% of it), `_drop_specks` (closed pieces < 4 m2 off the
    tile border), the shell reaches 2 m past the cave wall. Rock geometry: joint sets (`_joints`: three families of long
    vertical planes, candidate planes ~1.6 m apart each present or not and jittered (many small blocks, a few big),
    patchy bands of strength, 0.22 m grooves (flat faces, rounded floor, 1.5 voxels wide) fading out a few metres
    under the open ground (on deep cave walls and at 0.3 m they made black shards); a first version with regular spacing,
    per-bed stagger and pillowed blocks read as hammered metal from 150 m; the far LODs' maps get half / none of
    them) and facet size following the
    face's structure (`_structure_grain`: concave/gully/top of face = small broken facets, buttresses big planes).
    Wet band edge wanders, roughness varies (`_grain`). Memory: dense meshes streamed through `<out>/_work`, field
    calls chunked; `WORKER_GB` 2.0 measured; the manifest's `memory_gb` (resources.peak_memory) states each export's
    peak: pebble 9.1 GB job / 1.07 GB worker / 0.75 GB parent, lava 7.2 GB, alps 10x10 block ~17 GB. MC lattice
    values are clamped to 3 voxels (a 1e3 "air" pulled a float32 crossing onto a node: "isn't on one lattice edge").
  - Round 3, "seams/squares" (2026-09-30, seams agent, renders q01-): tile and chart borders were already invisible
    (measured in render space, every channel); the squares were patterns, all lattice-locked: (1) `Materials._grid`
    sampled the per-cell colour/cover grids bilinearly: a kink on every cell line, 5 m squares on the alps' rock (now
    a cubic B-spline, no prefilter); (2) `_pl_facets` creases lay on one rotated cubic lattice (a few fixed crease
    directions at a fixed spacing: a quilt of diamonds, mostly in the normal map). Warping the lattice
    (`_pl_walk(vec=True)`) barely helped (periodicity 0.55 -> 0.46); a 3D Delaunay of Poisson-disk seeds has slivers
    (needles 4x the lattice's slope). Now `terrain_facets`: random heights on the 2D Delaunay triangles of hashed
    Poisson-disk seeds (deterministic and local: tiles agree), laid triplanar on the face from `Field.face_dir`
    (normal ~ (fd, 1), weights^4, projections under 3% dropped continuously, blend renormalised), 1.4x up the face;
    `facet()` uses it for rock_relief and the bake's micro relief, the warped lattice only for a volume's share
    (caves: the ground's gradient says nothing there). Periodicity 0.30 max; the heightfield's own facets
    (terrain_rock, `T.rock["facet_delta"]`) are taken back out of Field.H where the solid rock has relief (two facet
    systems made a moire of lozenges). Cost: none measurable once points are triangulated per 64-size piece (one box over a sparse map-wide sample asked for 57M seeds: parent 7 GB); alps 9-tile block 14.4 min, pebble 12.5; (3) every joint
    family cut every face: long diagonal grooves crosshatched into diamonds; a family now fades where its planes run
    along the face (`Field.face_dir`, continuous where the slope vanishes); (4) each tile lowered its own texel
    density to fit texture_max (13.8-16/m side by side on a wall): one density per LOD for the export now, from the
    largest tile's visible area (`_job_dense` returns it, `DENSITY_FILL`), `texel_density_used` in the manifest.
    Checks (`terrain_seams`/`terrain_facets`, in the export's seam check): `facet_periodicity` (autocorrelation peak
    above its radial mean, 4 plane orientations; fails > 0.4), `grid_squares` (colour kinks on cell lines vs between:
    bilinear 2.4-5.9, now 1.1; fails > 1.5), `texel_density` (neighbours within 1.25x); `render_tiles(ids=True)`
    writes an exact id pass (glb, chart, distance) per view and `terrain_seams.measure` gives each border class's
    jump excess (step across vs the steps beside it: creases on chart borders don't count; ~1.0 = invisible);
    `channel=` "base"/"ao" (unlit), "normal", "clay" isolates a channel. `floating` treats pieces running off an
    `only` block as continuing (a wall steep across the whole block never came down inside it).
  - Round 4, the ruled bed (2026-09-30, renders s01_*): the user's "reads like a seam" on the alps wall at 40 m was the
    bedding, uniform along the whole wall: one proud/set-back offset, one 0.3 m V groove (creases +-1.5 m: the second
    edge under the line), one tone per bed, the maps' notch on nearly everywhere, all on a plane whose offset changes
    over ~750 m (isolated by channel: strong in "normal", faint in "base", nothing in "clay"). Now `bed_planes`: per
    plane along the strike a presence (patches ~20 m, off in gullies; absent = the step ramps over metres, no notch,
    tone eased over metres), a sharpness and per bed an offset and tone that vary along the strike (`_bed_noise`: the
    bed index as the lattice's third coordinate); beds wander in height (~0.5 m / 25 m + 0.15 m / 7 m, in the gridded
    offset); the notch's width wanders and breaks more. Presence/sharpness are only evaluated near a plane (field ~+15-35%,
    noisy machine). Open: the joints are still dead-straight vertical grooves 25-50 m long from 150 m (4 rulers);
    bowing their planes (~0.4 m over 40 m) fixed that but pushed pebble's LOD 0 shards 0.004 -> 0.011% (limit 0.01).
    `terrain_seams.straight_lines` (also in `views`): Canny off borders/silhouettes, Hough, longest run per peak; a
    ruler = >= 25 m (distance x pixel angle) or >= 40% of the view, and >= 1.6x the view's median edge gradient.
  - Export speed (2026-09-30, "profiling" agent; the user: "it's taking a very long time to output those rocks").
    `profiling.py`: spans + counters per process (`count` is also credited to the innermost open span, so "field.solid
    pts @ bake/surface" says who asked), `Report.pool_map` / `run_jobs` (jobs that unlock jobs) time every pooled job
    in its worker: wall, busy, utilisation, straggler tail, slowest jobs per stage. The export writes it to the
    manifest (`profile`), `profile.txt`, the log, and per tile LOD (`lods[k].timing_s`). HIFIPUSHIE_CPROFILE=<dir> dumps
    a cProfile per job; py-spy (`uvx py-spy record --subprocesses --format raw`) works on the whole export.
    Measured: the maps bake was 96% of the tile stage's CPU. That was 21M texels (pebble), each ~15 field points
    (Newton 9, the 0.4 m normal 4, weights 1) at ~17 us, and a field point was ~60% terrain_facets and ~27% value
    noise. Changes (identical up to fp rounding; the facet change moves values ~1e-15, which on the alps block
    tips pyfqmr into other, equally valid LODs):
    - Atlases are baked in pieces (`_textured_prep` -> `_job_bake` -> `_job_finish`, BAKE_PIECE texels, texels in
      Morton order) as soon as their tile is meshed. `terrain_bake.texels/bake_texels/assemble` are bake() split up.
    - Facet triangulations are cached per fixed block (GROUP 32).
    - The joint-band and bed-notch noise are evaluated only where a groove/notch exists.
    - One BLAS thread per pool worker (`resources.blas_threads`: forked workers inherited 4 and spun them, cpu 5x
      wall).
    - 25k-point field calls: memory-bound, +34% throughput at 12-16 workers. The machine saturates ~66k texels/s.
    - The PSS sampler reads every 2 s (smaps_rollup every 0.5 s kept a parent thread ~40% busy).
    Pebble 656 -> ~425 s of stages. Alps 3x3 on main after the bedding fix: 938 -> 627 s export. The alps block's
    critical path is now decimation: a LOD whose budget the previous LOD can't reach falls back to the 265k-face
    dense mesh with pyfqmr retries (80-210 s a LOD; Overboard card).
    The per-texel exact bake can't scale much further in numpy: a V3 prototype (height by secant along the low-poly
    normal, normals from neighbouring texels) cut field points 15 -> 7/texel for ~1.9x, but normals moved p90 4 deg.
    A compiled field (numba/C) is the next lever (card). For rock design rounds use `preview_tiles` (one LOD, low
    density, no checks; `examples/terrain_rock_look.py` exports + renders the tiles round a point): ~40 s a tile.
  - Compiled field (2026-09-30, "compiled field" agent; the user: "prototype the compiled field"). `fieldjit.py`: numba
    (dependency) kernels behind the numpy leaves, which keep their signatures and stay the reference
    (HIFIPUSHIE_JIT=0): noise._hash/_value_noise/fbm, Field.column/steep_at/grain_at/face_dir, `_gridded`,
    Materials._grid, Region.s, terrain_facets.facets/pl2d/_seeds, _pl_walk. BIT-IDENTICAL, exports byte-identical:
    each kernel repeats numpy/scipy's operations in their order (map_coordinates' spline weights and 4x4 accumulation
    from ni_splines.c/ni_interpolation.c; find_simplex's lifted walk, directed walk, brute force and start chaining from
    _qhull.pyx). Facets locate through a bucket grid per triangulation and fall back to scipy's walk only within 1e-9
    of an edge (where the walk's choice of triangle shows in the last bit). What can't be matched stays in numpy and is
    passed in: `x ** 4` (SVML pow), matmuls (BLAS FMA). Points must be (n,) float64 / int64 (other int widths wrap
    differently: numpy path). `fieldjit.warm()` runs in the parent before the pool forks (5 s cold, 0.5 s from
    numba's cache in __pycache__). `tests/test_fieldjit.py`: kernels + pebble/lava/alps fields, 0 differing values.
    Measured (shared, loaded laptop): leaves 3-34x per point (value noise 34x, column 8x, facets 3-5x), the bake's
    whole field ~3.5x, the pool 1.2M -> 3.1M points/s at 15 workers; pebble export 466 -> 182 s, alps 3x3 494 ->
    276 s, peak memory unchanged (5-6 GB, workers 0.4-0.6 GB). Not 10x because the composition (rock_relief,
    micro_relief, bed_planes, joints) is still numpy, and facet triangulation misses are cold per worker (a 2.5x
    bigger cache missed as often), ~16 ms each now. Alps was then 95% one decimation straggler: pyfqmr stalls far
    above the budget from a dense mesh and `_decimate` counted down to 16 (~100 runs); it now stops at the stall and
    steps from its last mesh (same meshes, 4-12x fewer runs: alps 3x3 276 -> 130 s, byte-identical;
    HIFIPUSHIE_DECIMATE_DUMP=<dir> saves a dense fallback's inputs to replay).
    terrain_blocks compiled (2026-10-01, "compiled blocks" agent): `_blocks_bed_coord`, `_blocks_offsets` (bed slots,
    bed values, minor joints per bed with the box filters, the maps' sharp window), `_blocks_masters`, `_blocks_ids`,
    per point, bit-identical (test_blocks + the terrain tests with blocks on). Numpy-only pieces come in: each
    super-bed's cuts (`h ** 1.2`, SVML pow) and every bed's joint frames (sin/cos) as tables over the points' K range
    (`_blocks_tables`, cached), the master joints' plan projections (`q[:, :2] @ n2`, BLAS, on numpy's own subset),
    the carve (logaddexp) applied after. Exact shortcuts: a value-noise corner of weight exactly 0 adds +0.0 to a sum
    that is never -0.0, so it's skipped (a bed or family index as a coordinate zeroes half the corners); a window
    wholly under the interval is exactly 0 (not the side above: (t+a)-(t-a) rounds, and numpy's tiny nonzero counts).
    structure() 11.7 -> 1.6-1.9 us/pt (synthetic, every family on); the pebble bake field 6.6 -> 3.6 us/pt.
    Remaining numpy in the composition: rock_relief/micro_relief's glue, bed_planes/_bed_noise (value noise compiled),
    block_colour, fallen_sd (small share).
  - Round 5, jointed and bedded rock (2026-09-30, "rock" agent, renders r01-r12, r*_vs_main; the user: "keep working
    on the rock" after q09/q10/s01 read flat, soft and blotchy: removing the lattice patterns removed structure).
    `terrain_blocks.py`, the medium scale (0.3-10 m), added in rock_relief (spec `rock.blocks` 0..1, default on; off
    brings the old joints, laminae, crack net and full bedding back):
    - beds: super-beds (`super` ~0.5 x facet size, a monotone `_warp` of height: they pinch and swell) each split at 0-5
      random cuts (`_cuts`): often one massive bed, sometimes a thin package. Thin beds (< 0.7 m) sit back as a package,
      thick ones stand out, how much changing along the strike (~9 m); beds undulate (10 and 28 m: one octave left
      ledge shadows ruler-straight for 40 m) and are rough (+-0.15 m over 3 m). Minor joints only inside their bed,
      spaced 1.3 x its thickness, each bed's set turned +-20 deg and dipping 72-90 deg, a third of boundaries absent
      (blocks merge), faces tipped, one or two corners chipped, a few blocks missing or proud. A few master joints
      (`_masters`): en echelon segments 20-50 m up the face, leaning +-15 deg, wavy at two scales, a rounded groove. The
      big beds (bed_planes) step at 0.4 and lose their notch with blocks: they ran whole cliffs as ruled lines.
    - CONTINUITY: every piecewise-constant value is box-filtered in its own coordinate (`_win`: a box of +-ramp softened
      by `SOFT`, so creases are C1 curves over 0.2 m; the filter width carried through the warp's slope). A ramp per
      boundary jumped where two boundaries came closer than the ramp; the box filter averages thin beds/blocks. A
      per-bed/per-block choice must use a per-cell constant (the nominal thickness), never the point's warped one.
      Detail under ~2 voxels in the MESHED field makes shards at tile borders (rough edges over 1 m, razor-edged
      fallen blocks: pebble LOD 0 0.09%): rough at 3 m, fallen blocks rounded >= 0.2 m and smooth-chipped. The
      structure mostly carves (`_carve`: set back `back` 0.3 m, building softly capped at `build` 0.12 m): proud beds
      over a cliff's lip built a slab in the air (a piece floating 27 m over pebble's heightmap: `floating` failed).
      The field's reach takes the blocks' MEASURED range (-0.12..1.44 m, 1.6 used); the cliff overlay's push and shell
      (`rock["relief"]`) keep main's sizes: thickening the shell by the blocks re-cut the shells round pebble's karst
      passage and notch (a face lying in a tile border plane at a corner: "border edges differ"; a non-manifold sliver;
      a 4-triangle piece floating 2 m up). Volumes' walls keep main's facets and bedding (the blocks' changes are
      weighted by 1 - u): the export's border machinery is fragile there and any change of their shells re-rolls it.
    - The maps get the structure filtered over +-max(2 texels, `terrain_bake.SHARP_MIN` 0.25 m) instead of the mesh's
      +-0.5 m (`structure(..., sharp=)`, micro_relief's `f.sharp`; weighted like rock_relief's blocks, so not in caves).
      0.1 m failed the seam check's LOD 0 vs LOD 2 normals (p50 7 deg, limit 6: it compares border points up to 0.6 m
      apart, and crisp 1 m-scale structure varies within that); 0.25 m measured 5.6. The layer/colour normal (0.4 m)
      is taken from the field without the per-LOD fine relief (`weightfield`): with it, weights differed p95 0.26.
    - colour (`block_colour`): bed and block tones easing to neutral 0.25 m from their edges (no step to alias), open
      joints only (8%) and some bed planes as faint lines, master joints dark, stains hanging from each super-bed's top
      (candidates every 3 m, a fifth present, 0.25-0.8 m wide, 2-12 m long), dull lichen on tops, the old tone noise at
      0.35, the field occlusion floor 0.75 (0.55 outlined every slot in black).
    - fallen blocks (`fall_zone`, `fallen_sd`): chipped rounded boxes at the faces' feet on gentler ground, >= 1.8 voxels
      (0.3 m ones meshed a non-manifold sliver at a tile border), smin 0.3 into the ground; the cliff Region covers them.
      Blocks on cave walls weighted (1 - u)^3 (at a cave mouth the face's blocks stepped its roof).
    - What read wrong on the way: every block outlined + right-angle joints + uniform courses = masonry / dry-stone wall
      (r01-r03); long straight master joints = knife cuts; a recess the same along a whole bed = a ruled black line;
      fat stretched-noise stains = ink blots, thin regular ones = a comb; even bed splits = plywood; isolated near-black
      blobs at 40 m (deep slot ends?) still open. Judge 40 m and closer at the export's 16 texels/m, not preview density.
    - Measured (`examples/rock_measure.py`, the alps wall): 1-3 m relief band 0.064 -> ~0.09 m rms; blocks median
      ~2.7 m2, p90 ~21; beds p10/50/90 0.7/2.8/5.5 m; joint traces off the beds' perpendicular p10/50/90 5/17/38 deg (32%
      within 10: not all right angles); drawn cracks 6% of all edges.
    - Tools: `examples/rock_round.py` + `rock_views.json` (fixed views: far pass 6/m on the block, near pass 16/m on one
      tile; `--noblocks` = main's rock for before/after), `examples/rock_measure.py`.
    - COST: numpy terrain_blocks made a field point ~4.6-6.6 us vs ~1 without (alps 3x3 ~940 s, pebble ~900 s). Now
      compiled (`fieldjit.blocks_*`, 2026-10-01, see "Compiled field"): alps 3x3 125 s, pebble 223 s (184 before the
      check), main's were 130 / ~182.
  - Detail by scale (2026-10-01, "detail" agent, renders m01_*/m02_*; the user: full unique tiles would overwhelm a
    game, and 16/m was still mush at 10 m). Geometry >= ~1 m; unique maps are MACRO only (`texel_density` default
    8/4/2, was 16/6/2.5); below ~0.5 m a tiling swatch per rock type (`terrain_swatch.py`, export cfg `detail`, default
    on). Experiment (`examples/detail_round.py` + `detail_sheet.py`, u16/m4/m8/u32 on rock_views): 4/m lost the block
    structure (0.3-1 m: block edges, bed steps, cracks) at 15-40 m; 8/m + detail matched 16/m at 40/150 m and was
    far sharper at 10 m; 32/m bought nothing at 40 m and was still mush at 10 m.
    - Swatch: 4 m at 256/m, every term periodic (terrain_facets seeds hashed on a torus, `_seeds(period=)`; FFT
      spectra band-limited to <= a quarter of the swatch: swatch-sized features repeat visibly): facets 0.45/0.16/0.07
      m, few deep fractures of varied width, spall scars with a conchoidal bowl, pits, clustered mineral grain in albedo
      and roughness, lichen. No laminae (lines at fixed v repeated every 4 m up a wall as ruled stripes). Anti-tiling:
      a second sampling at 1.618x, chosen by a periodic variation mask at uv / 24 m. `tileability` (wrap seam jump
      excess) is an export check (TILE_LIMIT 1.5).
    - Projection: a global strike UV can't exist (round a peak the faces close into a ring: a least-squares strike
      coordinate came out at 0.37 m/m, 2.7x stretch). Instead strike-binned planes: 8 vertical (u = p . d_k) + top, v =
      the bed coordinate (z + bed_offset), the plane from the field normal averaged over 1.5 m (position only: tiles
      and LODs agree). Per vertex `_DETAIL` = (strike x, y, side share, bed v) for a seamless blend of the two nearest
      planes; TEXCOORD_2 = each triangle's nearest plane (stock engine detail maps; seams). Blender's importer mixes
      custom attributes of different widths: keep them all VEC4 and on every primitive.
    - Lines map (RGBA per tile LOD, embedded as texture 3): SIGNED distances to the open bed planes / open joints
      (`structure_lines`, sign by a probe) + strengths faded within ~1 texel, so cracks are cut crisp at any density
      (unsigned distances beaded; the sign flip half-way between planes must be gated, and joints faded near their
      bed's planes or every crack end drew a hook). These lines leave the macro colour (`Materials.lines_in_maps`).
      micro_relief drops its 0.45 m facets when the detail is on (the smallest facet size held most of the bake's
      per-area triangulation misses: 3800 -> 958).
    - GLB: the baked material's extras.hifipushie_detail (texture indices, the swatches by uri in materials/);
      manifest "detail" (files, wrap seams, recipe). `render_tiles(textured="detail")` draws the recipe in Blender.
    - Cost (loaded machine): alps 3x3 bake 1140 -> 595 CPU s, export 187 -> 149 s; pebble bake 2577 -> 954, export
      337 -> 234 s; all checks pass, Khronos 0 errors. Decimation is now the alps block's critical path.
    - Open: no dip in the projection; TEXCOORD_2 seams not judged in a render.
  - Rock by measurement (2026-10-01, "rockmid" agent, renders n01-n03; the user, on m02: 40 m only equal to the unique
    bake, 10 m "faceted plaster"; then "compare away" with CC0 scans "to learn how to generate our own").
    - Scans: asset pack `rock_scans` (optional; Poly Haven rock_face_03 2.7 m, rock_06 1.5 m, cliff_side 1.83 m,
      rock_wall_02 2 m; 2K diff/nor_gl/rough/disp; CC0). `terrain_swatch.scan_swatch(set)` (albedo/rough as mean-1
      multipliers, height scale fitted to the normal map), export cfg `detail_source: "scan:<set>"`.
      `examples/scan_compare.py` renders swatches through the same detail pipeline (one preview export, swatch files
      swapped) + `swatch_stats` per swatch. assets.py sends a User-Agent (Poly Haven answers 403 without).
    - What the scans had (swatch_stats): surface slope 0.08-0.21 rms per octave, flat from 1 m to 1 cm (ours 0.02-0.07),
      median slope 0.2-0.4 (ours 0.08), albedo 0.10-0.23 rms per octave (ours 0.01-0.04: stucco), albedo uncorrelated
      with concavity and +0.2 with proud places. Retuned (`TUNE`): polygonal facets at 0.32/0.09/0.03 m
      (`periodic_cells`: Voronoi planes on a torus, soft-min over the 6 nearest seeds with softness a share of the LOCAL
      spacing (a share of the size speckled the dense patches); blending two nearest jumped at every corner), two
      fracture nets, every facet its own tone, clustered pits (crisp cups; thresholded noise read as cauliflower), veins,
      iron. Now slope 0.08-0.20/octave, albedo 0.05-0.11. Sub-texel lines alias into dashes: fracture/vein half-width
      >= 1.5 texels, faded by depth/darkness, never narrowed to 0.
    - Fade by repetition, not by energy (a fine-band-energy fade blurred 40 m: the 8/m macro can't carry it; mipmaps
      handle aliasing): `repetition_profile` lays the anti-tiled swatch as the shader does, reads the mip level a GPU
      picks, measures contrast and periodicity per footprint in LOCAL windows (a whole-view autocorrelation averaged
      the repeat away across the anti-tiling mask's patches: rock_face_03 read as a grid at 40 m but scored 0.28); the
      detail fades where both show (REPEAT 0.3 / 2%: every scan, 1.5-2.7 m, is 0.37-0.61 from 37 m and shows a grid;
      ours, 4 m, stays 0.16-0.26). Ours fades only past ~400 m; the scans would fade from 26-37 m, so a scan source
      needs a bigger set or stochastic/hex tiling before it ships. Manifest detail.fade, recipe step 6, render_tiles
      sets the pixel angle per view.
    - The id pass's sea plane read as tile 1 (a new colour attribute starts white): every waterline counted as a tile
      border. Pebble's chasm "tile jump excess 2.7-2.9" was that; fixed, there are no tile borders in those views, and
      the arch view's tile excess is 0.99 (was 1.61).
    - Lines: joints drawn by `joint_openness` (a smooth field: fracture corridors running through beds) and only in beds
      >= 1.4-2.4 m (bed-bound joints in thin beds were "pen ticks"); the family drawn at a point is the strongest there,
      not the nearest; the map is measured at the texel's LOW-POLY point (at the projected point every texel of a
      triangle bridging a ledge sat on the bed plane: filled triangles); shader crack half-width never 0 (a 0-6 cm width
      under +-2.5 cm jitter gated it on and off: dashes). Debug: `render_tiles(detail_show="lines")`.
    - Block tones: per block +-4% (13% read as pasted rectangles), per bed 6%, partial fresh spalls; tone bands along
      the beds (6 x 0.9 m) and each ledge's underside darker for ~1 m (`BLOCK_TONE`). Thin packages recess only in
      stretches and bed cracks are open over about a third of a plane in ~8 m pieces (both ran the pebble chasm as
      ruled lines; terrain_blocks + fieldjit, bit-identical).
  - Lines from the rock, swatch albedo, the pebble band (2026-10-01, "rock5" agent, renders p01-p0x).
    - The thorns/sawteeth were not the mesh's zigzag but the lines map's own values (measured on a kept bake,
      HIFIPUSHIE_KEEP_BAKE=1 keeps each atlas's texels in <out>/_bakes; `terrain_bake.bake_lines` re-bakes the lines map
      alone): the signed distance went to the nearest plane of the texel's OWN bed (noise inside a thin package, a plane
      every few cm) and the strength was gated to ~1 texel round the line so the noise stayed dark: the drawn line
      followed that 1-texel band, stepping texel row to texel row (period = the voxel). Joints the same (ids' nearest
      boundary switches half-way). Now `structure_lines`: the distance to the nearest DRAWN bed plane (`_drawn_beds`)
      or joint boundary (`_drawn_joints`), strength 1.5-2.5 texels wide (`LINE_GATE_TX`), faded where it meets the
      next line's sign flip (`guard`), distances across the surface (/ sine to the plane, from the interpolated normal;
      a surface within ~20 deg of the plane fades the line). Moving texels level onto the exact rock first changed
      nothing measurable (dropped). Jitter (structure tensor, fine vs coarse direction, lines-only renders): alps 10 m
      11.3 -> 1.2 deg, 40 m 5.4 -> 1.0 (line ends per 100 px 12 -> 1.4), pebble 15 m 4.2 -> 2.0, 40 m 3.5 -> 2.2.
      Clean, a bed crack read as a ruled ink stroke at 10 m: its opening wanders over ~1.7 m, it closes for a metre or
      two every few metres (4.5 m noise) and breaks where a joint crosses. tests/test_swatch: clean ramps, continuous
      strength.
    - Swatch albedo (TUNE): softened per-facet tones (hard ones that strong read as terrazzo), weathering patches,
      grime round and under fractures, a skew (`exp`: long pale tail, short dark one, as the scans). Per octave 0.05-0.07
      -> 0.13 at 0.25-1 m falling to 0.06-0.09 below 6 cm (scans 0.10-0.12 flat: flat at that level read as speckled
      dirty granite on pebble's dark rock at 15 m, so the energy sits in the larger octaves); percentiles of the
      multiplier = rock_face_03's.
    - Pebble's mid-cliff band: a thin package (super-bed 0's two beds of 0.24-0.32 m, z 2.3-2.9 m) set back along the
      whole chasm. Not in the mesh (clay shows nothing: the mesh's +-0.5 m filter averages it away) but in the MAPS
      (the bake's +-0.25 m filter keeps the slot; the bed above's underside faces straight down: a dark band in the
      normal channel, 0.2 m tall, 8 m long). The package's depth now wanders: flush for a metre or two every few
      metres, lumpy over ~1 m (`_bed_value`, fieldjit bit-identical); the maps' thin-plane notches and the darker tone
      follow it (`terrain_blocks.package_recess`). At 40 m the band is three shorter pieces; at 15 m one stretch that
      really recesses is still a dark slot.
    - The cliff overlay's edge was a TRENCH: the front sank by sink x (1 - S) and the heightmap was pushed by push x S,
      so they crossed where both were metres down (pebble S 0.73, 2.5 m under the true ground): every cliff-top edge
      sagged into a channel with a V crease (the "terraces" along pebble's cliff tops in the 150 m view were this). Now
      the front sinks only where S < SINK_EDGE 0.2 (`terrain_cliffs.sink_share`) and the heightmap is pushed by push x
      S^PUSH_POW 3: they cross ~2 cm down, the cliff mesh covers a little more of the margin. Arch view: overlay step
      0.086 -> 0.011, excess 1.96 -> 1.39 (regression export 1.25); heightmap_through_cliff unchanged (0.50%). Also
      `terrain_seams.classes` leaves out pairs across a depth JUMP (2% of the distance is 3 m at 150 m: the ground in
      front of the arch's cliff mesh counted as an overlay border). A faint line with small dents remains at the
      crossing.
    - Debugging tools used (scratch, worth knowing): render_tiles(channel=base/ao/normal/clay) splits a dark feature
      into colour vs maps vs mesh (the band was normal-only, the trench clay); a pixel's world point from the id pass's
      distance + the view ray; field profiles along the face normal per field (base, bake = CliffField front + micro).
    - Regression (cold, loaded machine: cloth sims and another export holding the heavy slot, 7 workers): pebble export
      271 s (main ~162-176; bake/lines 31 of 500 CPU s in the bake jobs), 0 failures, floating 0, shards LOD 0/1/2
      0.006/0.014/0.31%, Khronos 1040 files 0/0; alps 3x3 105 s (main 84-96), 0 failures, Khronos 72 files 0/0; views:
      0 rulers, chart 0.99-1.04, tile 0.97-1.0, overlay (arch) 1.25.
  - Whole-level look (2026-10-02, "level" agent, renders L01-L04; the user on pebble from 150 m: "WTF?", the point's
    arch "a cave with a cover over it"). Judged against photos of real coast (workspace/level_refs, CC BY-SA, never in
    the repo: Durdle Door, a Cornish sea cave, Cornish cliff tops, Pebble Beach's 7th) through the real export path.
    - The "cover": the point's arch was a 38 m tunnel (7 x 5.5 m) under a 30 m headland, turf to its lip. Arches now
      go through a FIN: where the land along the arch is more than 1.25 x `through` (0.9 x height, >= 4 m), bays are
      cut in from the sea down to its floor on both sides (`cut_neck`, a 2.5D ground edit in Field.H like dolines;
      `neck` m either side), so the tip stands on the arch. Height/span/roof by `_arch_size`: span <= 0.8 x height (8 m
      cap), roof >= max(`roof`, ROOF_SPAN 0.5 x span). The search prefers open sea past both mouths (land standing over
      0.75 of the opening within 60 m; rocks awash don't count). `through_view` (notes/manifest): rays along the opening
      above the water, share that come out clear + what lies beyond each mouth, WARNING < 50%.
    - Roofs: caves lower where the rock over them thins and end where even 1.8 m wouldn't keep max(1.5, 0.5 x span) of
      roof, chambers shrink to fit; notches die out to a nick under a low cliff (the chasm notch had -1.2 m: broke
      through). Cave default 4.5 x 6 (taller than wide: sea caves follow joints); the report flags wider-than-tall.
    - `terrain_ground.py` (colour + layer weight only, pointwise: tiles and LODs agree, tests/test_level_look): a turf
      edge set back ~1.4 m x (0.15-2.6 wandering) from every lip (distance to > 50 deg cells on the tops), shaded just
      under it; rock breaking through within 7 m of lips; no grass in the splash zone (~1.6 m over the sea, beaches stay
      sand); green on ledges below the top; patches at 60 / 15 m, drier on crests and sun-facing slopes, lusher in
      hollows, salt-burnt within ~30 m of the sea (toned down after L01 read straw-yellow: hue 61 vs the photo's 86);
      cover kinds mown (8 m straight mower stripes along each piece's principal axis from its centre: a frame turning
      with the zone put metres of phase into every degree; a darker first cut), rough (tussocks, straw tips), scrub
      (dark grey-green clumps; unkept grass turns to scrub past ~20 deg), sand (wet swash, a wrack line at the high
      water mark, grit), `bunker` covers dug 0.6 m into Field.H with a cut edge and a turf lip. The display grid is
      softened ~1 cell and sampled at a 0.6 m domain warp (cover edges were the grid's staircase: stickers).
      `"ground_character": false` turns it all off.
    - Eye level: the ground maps are 4 texels/m: plaster at 1.7 m. A tiling turf swatch (`grass_swatch`: blades
      splatted on the torus, clumps, dry blades; 2 m, 256/m) laid from above on grass/scrub weights, fading 20-70 m
      (manifest `ground_detail` + recipe; `blender_tiles._grass`). Ground clutter (`terrain_ground.clutter`, from the
      same masks): bushes on scrub clumps, boulders in the splash zone and near lips (clutter.csv for engines), tussocks
      in rough near the eye (renders only); placeholders in `blender_terrain._clutter_proto`.
    - Sea stacks as solid prisms (`Stack`, op add over the heightfield's stack: lobed, ~84 deg sides, a tilted notched
      top, 0.35 m bevel): on 1 m cells the heightfield's 76 deg stacks were rounded loaves. Trees out of the splash zone
      and off faces over 45 deg (a cypress stood on the wave-cut platform).
    - Tile views (`render_tiles`, `look_terrain(tiles=True)`): the sun is terrain_sun's per view ("auto" default; the
      fixed SW sun front-lit the 150 m view flat), the sky's sun_rotation = bearing (it was -bearing), aerial haze (a
      mix toward the horizon's colour by 1 - exp(-d / haze), d = the camera ray's length; the colour is MEASURED per
      view by a 16 px render of the sky alone: a Sky Texture inside a material lost its Vector input in the importer's
      scene and fell back to object coordinates, a pale gradient on every tile, L01's "quilt"), the sites' props as
      stand-ins (baskets, tee pads, the lodge: `blender_terrain.props`), trees, clutter.
    - Arch placement also rewards height (6 m / height) and daylight (3 per blocked mouth): pebble's arch went from a
      3.9 x 4.9 m hole on a spur to 5.7 x 7.1 m through a 6 m fin (bays cut from 30 m of land), 83% see-through.
    - Clutter shapes: tussocks are blades turned about their ROOT (about their middle they crossed into teepees);
      boulders only where the maps make rock (the shore rule alone put them on beach sand); bushes on 5 m clump noise.
    - Measured (renders vs the Pebble 7th photo): grass hue 61 deg / sat 0.24 at 150 m in L01 (photo rough 86 / 0.46,
      fairway 91-97 / 0.36-0.43); inside the arch's opening 0.28 of the lit rock's luminance. Open: the fairway still
      pale at eye level, bushes perch on cliff tops, the turf lip is colour only (no geometric step), stacks bulky.
  - Eye-level ground (2026-10-02, "eyelevel" agent, renders E04-E0x; the user, after L04: the fairway one pale minty
    green, the beach smooth, boulders low-poly, the turf lip colour only, bushes perched on lips, stacks bulky, the arch
    smooth). Judged against the Pebble 7th photo by measure (HSV of ground pixels by kind from the id pass's world
    points; texture = luminance std / mean in 7 px windows at the photo's 640 px scale).
    - Ground edits finer than the grid (`terrain_ground.Edits`, built in Field.__init__, applied in `Field.column`, so
      the heightmap, the cliff overlay, collision and both bakes agree): the turf's STEP at its ragged edge back from
      every lip (`LIP` turf 0.7 m, riser +-0.35 m in the mesh; the maps bake it crisper, +-max(0.12, 2.5 texels):
      `bf.edit_riser`, `Region.height(riser=)` for the ground maps), and bunkers cut crisp (a signed distance per trap
      at 0.25 m, `signed_distance`; they were H edits at 2 m cells: soft dishes). `zone` (cells) gates the cost. Two
      traps found by the checks: the Region took the bunkers' faces as cliffs (square 4 m pits round every bunker:
      Region reads the slope from `_column`, the grid's own ground), and recomputing the column's slope factor from
      the edits moved every cliff face below a lip ((z - h) s metres under the top: floating pieces, shards, map seams
      lod1 p95 16 deg). The field is just steeper than 1 across a riser now. No overhang: 0.2 m under 0.5 m voxels
      would be shards; the undercut is the colour's `under` and the maps' crisper riser.
    - Mown grass is its own layer `turf` (LAYER_OF mown/lawn/fairway/green), with its own swatch; covers are painted
      per point with the layers' own weights (`Materials._paint`, the bare ground's grid under them, roads over),
      mown pieces cut along the mower's line (a 1 m signed distance, edge +-0.3 m: +-0.12 put the earth layer's weight
      over the LOD 0/2 seam limit), a first cut (`CUT` 2.2 m, kind "cut") taken out of the rough, stripes 7 m with a
      normal-map lean along the mower's way (`STRIPE` tilt 0.25 rad, tone +-16%, edges softened to 2.5 texels) and
      mottling at 3 / 0.8 m. Maps-only relief (`Ground.relief` -> `Materials.relief`, tilted into the baked normals in
      `bake_texels(texel=)`): tussock clumps 1.2 m, clumps 2.6 m, scrub lumps; each octave fades where it's under 3-5
      texels, and cliff tiles count their texel 2.5x (`RELIEF_CHART`: their charts' texel grids differ across a
      border). Swatches per kind (`SWATCHES`: turf short and dense, long grass clumpy with straw, sand ripples / grit /
      pebbles via `sand_swatch`), manifest `ground_detail.swatches`, each with its fade (turf 30-110 m).
    - Colours: the defaults and pebble's were too pale for the renderer (albedo v 0.48 rendered 0.58-0.72 under the
      hazy sky). mown [0.20, 0.40, 0.13], rough [0.30, 0.43, 0.17]; less straw/salt on rough; sand darker. Most of
      the "pale minty" was the light: `render_tiles(light="clear")` / `look_terrain(light="clear")` (LIGHTS: Nishita
      dust 0.02, sun 3.2 W, sky 0.08, exposure -0.35) put the fairway at h 98 s 0.39 v 0.46 vs the photo's 98-100 /
      0.36-0.39 / 0.38-0.54. `grade=` sets an AgX look ("Punchy" changed almost nothing).
    - Clutter (`terrain_ground.clutter`, rows [x, y, z, kind, scale, yaw, squash]; clutter.csv gains `squash`): bushes
      never within `CLUTTER_LIP.keep` 1.8 m of the turf's edge and squashed/broader out to 7 m (wind-shorn), only
      where the maps paint grass; tall grass (`tallgrass`, 0.3 m grid within 28 m of each eye, thinning out); boulders
      in clusters, only on rock (weight > 0.55-0.8), sunk 0.12 x scale; trees kept `TREE_LIP` 4 m (cypress 1.5) in
      from the turf's edge (the export drops them, noted). Render protos (`blender_terrain._clutter_variant`, 4
      variants each, picked per instance, scale/yaw/squash from point attributes): blade tufts (curved strips, green
      root to straw tips on a few), sage bushes (lumps with a leafy Voronoi bump), boulders faceted by noise, wet and
      darker near the sea. No bush or boulder within 2.5 m of an eye.
    - Stacks (`Stack`): the heightfield's stack is a slim core (`terrain_sea.STACK_CORE` 0.45) and the solid stack
      replaces it (`clip`: the ground cleared in a cylinder over the plinth; crossing surfaces in its notch made
      shards): lobes changing up the stack (`twist` 6 m), beds standing out / sitting back +-0.2 r handing over in 1 m,
      a waterline notch, 10 deg lean, a broken top. Thin fins and stacks take little relief (`Field.thin`), so their
      beds show in colour instead (`THIN_TONE`): the arch's fin still reads smooth in geometry.
    - Regression numbers and open items: see the Overboard card "Whole-level look".
  - Thin rock, lips, routes, sea and sky (2026-10-02, "terrain7" agent, renders T0x in workspace/terrain3d_renders).
    - Thin rock keeps its relief: `Field.thin` (grey opening) no longer cuts the relief's weight (`Field.relief_w`;
      `Field.steep` keeps the cut for the cliff Region, fallen blocks and the facet-delta removal). `_local_thickness`:
      per thin piece (labelled, padded 2 r_open), per ~1 m height level, the Hildebrand-Ruegsegger local thickness of
      {H > z} (largest disc covering the cell, via an EDT per radius: disc dilations cost R^2 per cell), 2 cells into
      the air, smoothed; `Field.thin_at(p)` -> (half-thickness, t), trilinear. The relief is soft-clamped there
      (`thin_cap`: THIN_RELIEF 0.35 x hw x tanh(R / that)), so it can't carve through or cut a top off. Near caves and
      notches (THIN_VOID 8 m, not arches) the old rule stays: full relief over a sea-cave mouth cut a roof piece free
      4 m up (`floating` caught it), and capping by the slab between face and void instead folded cave walls into
      shards. Thin rock also gets `strata` (interbedded 1-3 m beds, about half soft and set back up to 1 m, eased over
      +-0.5 m, wandering along the strike) in geometry AND colour (Materials: soft darker/warmer, hard paler,
      THIN_STRATA tone). Honest read: relief on pebble is ~0.5 m rms whatever the rule, invisible at 30-60 m; the fin
      reads layered only through the colour bands. Durdle Door's crisp many-bedded look is still far: accepted (the
      main session) as a limit of the 0.5 m voxel; thin rock would need finer voxels (beds < 2 voxels mesh as shards).
    - The pale flat triangles at lips were the cliff mesh's "buried" split: a face whose CENTRE was > 0.3 m off the
      visible front went to the plain matte (COLOR_0) primitive, and big faces across the turf step have their centre
      off it with every corner on it. Now buried = centre off and not all corners on the front (requiring every corner
      off promoted the back's edge faces round caves into the visible prim: shards and map seams).
    - Routes are worn ground only off mown turf (`Materials._route`, gated by the mown + first-cut kinds).
    - `light="clear"`: `sky_sat`/`sky_value` (Hue/Saturation on camera and glossy rays only: the light the sky casts
      is unchanged), `sky_horizon_tint` (Nishita's low sky is near white; multiplied toward blue up to ~20 deg),
      `water` / `water_roughness` (a deep blue body, IOR 1.33), `haze_scale` 3. Hole 7 at noon (`skysea.py`-style, from
      the id pass): sky top s 0.45 (photo 0.44), low sky s 0.02 -> 0.15 (0.33), far sea s 0.12 -> 0.25 (0.49), near sea
      0.44; AgX's highlight desaturation limits the rest.
    - The fairway's soft blotches under a high sun (hole 7 at noon) were the baked ROUGHNESS: `terrain_bake` multiplied
      every layer's roughness by a ~1 m fbm grain (0.85-1.2: turf 0.77-1.0), and a high sun shows that as sheen
      patches. Full grain on rock/wet rock only, +-3% elsewhere. Found by channel: base colour and clay were clean, the
      turf detail off changed nothing (`render_tiles` channel views had been ignored under the detail recipe: fixed;
      `grass=False` leaves the turf detail out). The turf detail's two samplings are chosen by an 8 m mask now, not
      averaged (recipe text updated).
    - The pale band at the horizon: the sea was an 8 km plane under an 8 km camera clip; now 200 km / 250 km.
    - Regression (cold, loaded machine): pebble 363 s, 0 failures, floating 0, shards LOD 0/1/2 0.0066/0.026/0.30%,
      Khronos 1040 files 0/0; alps 3x3 165 s, 0 failures, Khronos 72 files 0/0; test_fieldjit (bit-identical),
      test_swatch, test_level_look (+ thin rock, routes), test_tooling pass. Margin: pebble's cliff-map `lod1` normal
      p95 is 14.2 deg against a 15 limit (main 12.6; grading mown ground smooth took it to 14.95: dropped). The points
      over 15 deg sit twice as often near the turf's edge (26% vs 13% of border points) and not on thin rock: likely the
      faces across the turf step now baked as visible. Watch it.
    - Bushes: `blender_terrain._scrub` (stems forking from a crown, ~600 small leaf clusters over a lumpy shell with
      gaps); lumps read as stones, big clusters as crumpled paper. Tussocks 20-70 m out are more and bigger
      (`terrain_ground.CLUTTER_MID`).
  - Incremental export, build cache, decimation tail (2026-10-01, "incremental" agent; the user: exports take long).
    - `terrain_incremental.py`: an edit re-exports only the tiles it can reach; the rest of the export dir is left
      untouched. INVARIANT: an incremental export equals a cold one byte for byte (manifest timing/profile aside); test
      with a cold export of the same spec and a file-by-file compare. Nothing is decided from the spec: `Fingerprint`
      walks what the workers read (the export's field, base Field, Materials + T.cover, Region, DetailProjection, swatch
      entry, cfg, code digest); arrays on a known grid (T's cells [iy, ix], the region lattice [ix, iy], `_gridded`
      splines via `f.frame`) are cropped per tile to its box + MARGIN 24 m (+3 cells), volumes count where their reach
      box (incl. the cliff shell's void box) meets it, everything else is GLOBAL (a change: cold, the log names the
      member, e.g. a site edit changes `materials.rock_ref` and every tile's grain: erosion and global percentiles make
      heightfield edits global). An object type the walk can't hash turns incremental off. Later stages chain keys:
      dense (field key + its canonical border rows' CP/CN and their order: welds keep the lowest row), each border
      collapse (dense key + which rows the LOD keeps; failures stored as positions in the tile's rows), each tile's LODs
      (dense + keep masks, skirt depth/dir, CN/CW/CC at its rows as `pos` finds them, density). The parent's global
      steps (border vertices, chains, keep sets, skirts, density) always run in full, as cold: a neighbour whose shared
      chain moved gets a new key by itself. A reused stage's work files are made again only if a later stage needs them
      (`_job_dense_full`, `_job_prep_tile`). State: <out>/_incremental/state.pkl (deleted at the start, written before the
      checks); `export.tiles incremental: false` or HIFIPUSHIE_TILES_COLD=1 force cold. Files nothing names any more are
      removed at the end (top-level GLBs, maps/, heightmaps/, splats/).
    - Bugs it found (cold exports were not functions of their inputs): bake pieces were sized by the pool's worker
      count, which follows free memory (a few texels' facet lookups moved: exports differed run to run; now n/16);
      `terrain_bake._bary` clipped a sliver triangle's gutter weights without renormalising, so gutter texels were
      baked at a fraction of their position, hundreds of metres away (pebble tile 10,3 read the arch at x 220; now the
      triangle's nearest point); map_seams iterated a set of channel names (key order in seam_check.json by hash seed).
    - Checks: `map_seams` decodes each tile LOD's maps once for all its borders across a fork pool (was once per
      border, serial: 80% of the checks), `floating`'s clearances per tile; both kept in `inc.Memo`
      (<out>/_incremental/checks.pkl) by their files' bytes. Swatch kept by seed + code (`_swatch`).
    - `terrain_cache.py`: built terrains pickled (zlib 1) in ~/.cache/hifipushie/terrain (HIFIPUSHIE_TERRAIN_CACHE,
      cap HIFIPUSHIE_TERRAIN_CACHE_GB 1.5, LRU), keyed by the spec minus THREE_D (caves, volumes, export, views: the
      build never sees them, cached or not, so a cave edit reuses the build), kinds.json and `codehash.digest("terrain")`
      (`codehash.py`: sources of the package modules a root imports, statically, incl. lazy imports; package *.json;
      numeric library versions). terrain.load and terrain_tools.build go through it. alps 128 MB pickled, 39 MB stored.
    - Decimation tail: a coarse LOD's dense-mesh fallback (a failed border collapse on the previous LOD's mesh, or a
      budget it can't reach) reaches PRE 32 x its budget in one pyfqmr pass first, then the same budget search with the
      dense mesh's tolerance (`_decimate(pre=)`). Replayed (HIFIPUSHIE_DECIMATE_DUMP) on the alps block's 12 fallbacks:
      85 -> 37 s, faces <= before in every case, summed error p99 6.2 -> 5.7 m; 4x/8x were faster but further off.
  - First consumer export (2026-10-07, "tiles" agent, branch worktree-agent-aa0a9fde6c2eee6d8; pushieworld's slice_a,
    512 m of sheer coast with a sea cave: /home/joe/dev/pushieworld/docs/hifipushie-notes.md 19-30; our copy is terrain
    `tl_slice_a`; scratch DURABLE in /mnt/data/hifipushie/tiles: run.sh <script> (this worktree's code on the main
    workspace), exp.py <terrain | spec.json> <tag> ['<cfg json>'] (export into out/<tag>, summary + heaviest tiles),
    diag1.py <terrain> i j (one tile's marching cubes: triangles by depth, visible / buried, open edges; 60 s, no
    heavy slot), diag2.py (the dense mesh's own error), dec.py (pyfqmr at several counts), shards.py <tag> <lod>
    (where shard faces are), recheck.py <tag> (the seam check alone on an export), queue.sh (slice, pebble, alps one
    after another), tests.sh, val.mjs <dir> (Khronos over a directory), man.py <manifest> (heaviest tiles)).
    The failure: tile (4,1) at 495,898 / 495,622 / 495,475 triangles against 12000 / 3000 / 800 (three more tiles
    at 100-313k), 748 s for that tile, 44 open edges at z -94.9, a traceback instead of a report.
    - ROOT CAUSE (not the cave): the cliff shell's back was `thick` behind the COLUMN's own plane, (z - h) x cos(slope)
      > -thick. On an even slope that is a shell `thick` thick; under a sheer face's columns (84 deg sea cliffs on
      0.64 m cells: cos 0.04-0.1) it is thick / cos = 50-100 m straight down: a buried sheet thinner than a voxel under
      every cliff, and behind the face a slab only as thick as the face is wide in plan. `_tile_mc` sized the lattice as
      ground - zpad / max(cos, 0.15) (88 m), which cut the sheet open (the open edges). Tile (4,1)'s marching cubes:
      439k triangles, 262k of them more than 10 m under their column's ground, none of those visible. pyfqmr folds a
      sub-voxel two-sided sheet into fins at any count, `valid` rejects every candidate, `_decimate` hands back the
      dense mesh after 5 aggressiveness retries per count on 500k faces (the 200 s a LOD). Capping the sheet's depth
      alone was not enough (238k triangles, and pyfqmr still non-manifold above ~1,300): the slab behind the face had
      to go too.
    - FIX: `Region.back` = the ground eroded by a ball of radius `thick` (ndimage.grey_erosion with a spherical
      structure, smoothed 0.7 cell; a terrain-frame grid, so the incremental fingerprint windows it), read like the
      ground (`back_at` -> height, slope factor); the shell is {front < 0} and {z above the back}. Identical on an
      even slope. `CliffField.zlow` (the lattice's bottom) is that back - 1 m. (4,1): 233k marching-cubes triangles,
      zmin -7.8, LODs 11,996 / 2,989 / 633, 12.5 s.
    - `_decimate`'s error on a cliff shell is measured on faces with every corner on the visible rock, by
      `field.front` (the buried back's field values are not metres: the dense mesh's own p99 was 0.59 "m", and that
      was the tolerance: once decimation worked, LOD 0 of the cave tile came out at 1,132 triangles).
    - Budgets fail loudly: `budget_check` -> manifest `budget_check.over` (tile, lod, triangles, budget, why), an
      "OVER BUDGET" log line and a check failure per tile LOD over `OVER_BUDGET` 2 x its budget. Collision:
      `collision_budget` (default 2 x its LOD's budget): `_collision_mesh` decimates for collision alone when the LOD
      is heavier; tiles[].collision_triangles. tiles[].seconds; the summary lists the slowest tiles over 60 s.
    - Failed checks are a report: `TilesCheckFailed(RuntimeError)` carries the result; `summary(result)` leads with
      "CHECKS FAILED (n). The export is COMPLETE on disk ..." and each failure with its tiles (shards: most-affected
      tiles; map seams: the worst borders and the limit); `export_terrain` and terrain_run.py return / print that.
      manifest seam_check.failed repeats the list.
    - Tried and taken back: border vertices on a crease taking a normal from a 1-voxel stencil (72 of slice_a's 77
      LOD 0 shard faces have a border vertex: border normals are never split, and one side's exact normal at a sheer
      lip is square to the other side's faces). It made shards WORSE (slice_a LOD 0 0.012 -> 0.043%, pebble 0.005 ->
      0.05%) and the lod1 map seams too. The idea may be right, the wide stencil is not.
    - Small ones: heightmap .npy in C order (`.T` had saved fortran_order True: a plain reader got the tile
      transposed); the buried primitive's material is `terrain_buried` (Godot drops extras and saw a second skirt);
      guide + manifest: holes PNGs are heightmaps/holes_<i>_<j>.png and only for tiles with holes, texel_density
      default [8, 4, 2], primitive roles / materials, the two collision files. Report: a spec with `caves` /
      `volumes` says "3D rock: ... built in the mesh tiles only" instead of CAN'T BUILD YET; a cover LIST is named
      by type (meadow, conifer; was cover_1..6: file names of exported masks change with it); the "no coast" error
      gives the sea level and each edge's lowest ground; a route to a cove says to route to a site at it; a hollow
      behind sea cliffs says the raised cliff tops dam it (slice_a: top 18.8 m where the tilt alone gives 3.3).
    - tests/test_tiles.py (a 128 m synthetic sheer coast, "cell" 0.64, 32 m tiles; ~60 s, no heavy slot): shell
      depth and closed, budget holds from the dense mesh, budget_check, a failing export comes back as a report with
      its files on disk, C-order heightmap.
    - Results (cold, loaded machine). slice_a: 161-230 s wall (was 1050), every tile within budget (LOD 0 per tile
      2,514-12,000, LOD 1 561-3,000, LOD 2 147-800; the cave tile 11,996 / 2,989 / 633), 0 open edges, 0 floating, 3.9
      GB. It still FAILS three checks, now as a report, none of them the curtain: LOD 0 shards 0.012% (limit 0.01;
      77 faces, 72 with a border vertex, most in tiles 7,1 / 4,1), cliff-map normals across borders at LOD 1 p95
      17.1 deg (limit 15; worst borders 2,3|3,3 37, 5,0|5,1 29), LOD 0 vs LOD 2 weights1 p95 0.284 (limit 0.25).
      Pebble (examples/pebble_disc.json, 208 tiles): 245 s, shards 0.005 / 0.023 / 0.198%, floating 0, Khronos 1044
      files 0 / 0, but the LOD 1 map-normal seam is p95 15.55 against the limit of 15 (main: 14.2, already noted as
      thin margin): it FAILS by that. Alps 3x3: 133 s, 0 failures, shards 0 / 0.003 / 0.004%, Khronos 72 files 0 / 0.
      test_fieldjit, test_level_look, test_swatch, test_tooling, test_tiles pass.
    - OPEN, in order: (1) the LOD 1 map-normal seam (pebble 15.55, slice_a 17.1): find what the worst borders have in
      common (recheck.py prints them; a few borders at 30-60 deg carry the p95: likely a cliff piece's edge texels at
      4 texels/m, or the two tiles' charts across a crease), fix or re-set the limit with main; (2) shards at border
      vertices on sheer lips (a per-face split that both tiles make alike, or a crease-aware border normal that is
      not a wide stencil); (3) weights1 across LOD 0 / LOD 2 on slice_a; (4) the Khronos validator needs an
      externalResourceFunction for the detail swatches' uris (val.mjs has it; without, IO_ERROR per image);
      (5) a time estimate before the export (tiles x cliff area) was asked by the consumer, not built.

  - Terrain styles (2026-10-07, "terrainstyle" agent, branch `worktree-agent-aaa51cb5f5cb72005` (delivery 1 merged as main 1e54176); consumer brief:
    /home/joe/dev/pushieworld/docs/hifipushie-notes.md 18, 58-59; renders `workspace/terrain3d_renders/ts_*`; scratch
    DURABLE in /mnt/data/hifipushie/terrainstyle/: run.sh <script>, sheet.py <png> [styles] [layers] (swatch sheet +
    strips, no terrain), mk_slice.py (terrain `ts_slice_a` = tl_slice_a + zones dumpling_downs west / painted_east
    east + styles blobby / anime; writes the styles alone into ts_slice_a_styles/), exp.py (tiles export into out/),
    prev.py <terrain> <tag> x y r '<views>' (preview_tiles + styled renders), rend.py (renders of an existing export,
    textured styles | baked), diffield.py / diff2.py / diff3.py (which Field grids differ outside a styled zone)).
    - `terrain_style.py` + `terrain_styles/<name>.json` over `_base.json` (realistic, blobby, anime, cartoon, pixar):
      spec `"styles": {style: zone | [addresses] | {"in", "band", "sheet"}}`, everywhere else realistic; zones are a
      PARTITION (a later style wins overlaps; realistic = no zone), weights = smoothstep over each style's band of the
      signed distance to its own piece, normalised (two adjacent zones meet 50/50, no realistic between them). Layer
      textures = op stacks (blotch, strokes, bands, ripples, dots, grain, cracks, facets, pillow: periodic on the torus,
      tone -1..1 x albedo with warm / cool tints, height m), mean = the layer colour (the terrain's realistic colour turned
      by the sheet's saturation / value = the plant style's numbers). Written PNGs are cached by their inputs + this
      module's code ($HIFIPUSHIE_STYLE_CACHE): a cached write is byte-identical (test). `write` / `export_styles` /
      manifest `styles` (contract 1, order, styles[].layers[l] files / size / colour / roughness / seasons tint_linear,
      snow numbers, tiles[].styles, maps sd + weights, recipe); in every tiles export of a spec with styles, or alone:
      `export_terrain(name, styles_only=True)` (seconds, updates manifest.json). `look_terrain(styles=True)`: swatch,
      season and transition sheets; with tiles=True the views with the recipe (`render_tiles(textured="styles")`,
      `blender_tiles._styled`). "styles" is in terrain_cache.THREE_D (the 2.5D build never sees it).
    - Rock shape in the field (`Field.styles` from `terrain_style.rock_styles`, weights on the terrain grid with the
      sheet's `rock.band_m`, default 10 m): `relief` multipliers on the realistic rock numbers (`rock_variant`), `pillow`
      (`pillow_carve`: 3D jittered cells, grooves smoothstep^2, C1), `soften_m` (Gaussian on Field.H in the zone, also
      takes the heightfield's facet_delta out there), `fallen`, `micro`. `_styled_relief` mixes realistic's and each
      style's relief by weight. INVARIANT kept: with no rock-shaping style the field is the old code path; with one, the
      realistic zone is bit-identical (test_rock_shape_by_zone) because `_structure_grain` (a GLOBAL percentile) and
      `_local_thickness` (thin pieces span zones; per-piece height levels) read the UNSOFTENED ground. Any new global
      statistic in Field must do the same.
    - First delivery: /mnt/data/hifipushie/terrainstyle/ts_slice_a_styles/ (materials/<style>/..., styles/, styles.json,
      swatches.png, seasons.png); full export with styles (OLD geometry: before the rock shapes) out/ts_slice_a: same 3
      known check failures as main (LOD 0 shards 0.012%, ...).
    - Read so far: textures tile (wrap seam <= 1.4 on every layer); blobby = flat soft fields (good), its rock texture is
      nearly blank (a first "pillow" texture read as flagstone paving: pillows belong in geometry); anime grass reads as
      painted dabs, anime rock as crisp painted bands; cartoon tufts are blobs, not ink ticks; pixar blades too subtle.
      ts_06_top_border (styled recipe, old geometry): flatter and paler than the baked look, faint contour-like lines on
      the blobby grass slopes (not the bump: still there without it; likely the turf-lip risers' geometry, which the
      baked colour hides: not isolated).
    - Styled GEOMETRY seen once (ts_04_*: preview_tiles, 9 tiles round [240, 90], one LOD, no checks): blobby cliffs are
      rounded pillow lumps (read as melted / pillowy, not yet "pebble-smooth"), anime cliffs carry strong painted strata
      with bedding ledges, the two meet at the zone line as different rock (the brief allows it). NOT RUN YET (the heavy
      slot was held for another session): a full ts_slice_a export with styled geometry and its seam / shard / floating
      checks, and the pebble / alps 3x3 regressions (no styles: the field code path is unchanged when no style shapes
      rock, so they should be byte-identical; verify).
    - Round 2 (consumer notes 71-75, Godot): CONTRACT 2 = soft layers always top-projected (side planes at v = world
      height turned their tone patches into ~0.5-1 m terraces up slopes: the "contour lines"), rock triplanar with
      `v_jitter_m` (strata wander along the strike; anime rock 12 m, 3 m jitter: its 8 m repeat up a cliff). `tileable`
      compares the seam with ALL neighbouring rows' mean step + one 8-bit level (one row beside it: a pebble on the
      seam read 4.04 for cartoon sand; flat blobby swatches read 1.7 on 1e-4 steps); `bands` are shifted half a band
      off the wrap row (an edge on it was a real seam line). Blobby rock by measure (rockform.py: horizontal sections
      of the south cliffs x 20-120, band-passed 0.5-8 m): pillows 3.5 m / soften 1.5 -> 6 m, stretch 1.8 (cells taller
      than wide: seams run up the face), depth 1.0, round 0.5, soften 3: undercut share 0.078 -> 0.001 (unstyled
      0.041), convex share 0.512 -> 0.534, lobes / 10 m 1.33 -> 1.22. NOT yet rendered.
    - Open, in order: (1) those exports + checks; (2) the tufts op for cartoon (done) vs dab size of pixar blades (too
      subtle); (3) blobby rock = rounder, fewer, bigger pillows (size 3.5 -> 6, depth 0.8 -> 1.0?) and pebble-smooth
      fallen boulders (fallen 0 today: none); (4) the shader recipe as a Godot .gdshader (consumer wish 5); (5) snow by
      height / hollows (numbers only today).

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
- Open (read of vg_36, 2026-10-06; superseded by Vegetation 2 above for pine, spruce, willows): pine still an umbrella with a pole trunk and ribbon-like needle cards; spruce a
  good cone but bare wood shows through low down; weeping willow a mushroom (dome envelope over a stalk of curtains);
  white_willow thin after the shadow change; birch good at range, bark marks not judged close; oak the best.
  Not done: wet smear, snow on ground/limbs, wind measured by displacement, 8k pine set re-run. Earlier: low LODs need bough-sized cluster cards (20k oak = a few big clumps); spruce close-ups are feather cards;
  weeping willow is a ragged column, not a dome; snow doesn't lie on the ground; wind clip's difference image is
  muddied by alpha dithering; collision mesh 2.5k triangles on a birch; stages 3 (small plants, palm), 5 (styles) and
  terrain integration not started.

## One human mesh (2026-10-06, "onemesh" agent, branch worktree-agent-aac6bb85823bc8809; renders `workspace/human_renders/om_*`)

The user: "we seem to always be fighting the makehuman/GAN mesh combination ... So we had one mesh?", then a stretch
goal (the same topology driving stylised humans: feature animation, cartoon, low-poly, anime, by macro sliders fitted
to references), then two requirements on the interface: sliders are what a SOLVER sets ("sliders are always
ambiguous"), and guard rails against "blind measurements while completely ignoring the integrity of the rest of the
model".

- Research (Phase 0): nothing open replaces GNM + MakeHuman. Anny (NAVER, Apache-2.0 code, MakeHuman's CC0 assets,
  WHO-calibrated ages) IS MakeHuman's mesh + macros, i.e. what makehuman.py + anthro.py already are, with MakeHuman's
  faces; MHR (Meta, Apache-2.0, scan-based, 7 LODs, 72 FACS shapes) has no eyes / teeth / mouth, PCA identity and no
  children; SMPL-X / STAR / SUPR / FLAME non-commercial; MetaHuman Epic-only; GNM still head only (a body is on its
  roadmap: the body half here stays swappable). MPFB's `faceunits01` (CC0, 52 ARKit shapes on MakeHuman's head) is a
  reference for our face shapes. Decision (with the user): fuse GNM's head topology onto MakeHuman's body, once.
- The asset: `src/hifipushie/human_mesh.npz` (2.1 MB, in the package), built by `spikes/onemesh/make_asset.py`
  (deterministic, prints the arrays' sha256; `register.py` = make_field's registration returning the correspondence;
  `sheet.py` = the hand-check sheets; `wire.py` / `meshview.py` = a PIL clay / wire viewer, no Blender).
  MakeHuman's body below a neck loop C (42 vertices; one loop above `base._neck_loops`' top one: that one lies on the
  trapezius), GNM's skin above its neck ring 13 (110 vertices) + sock + eyes + teeth + tongue, three bridge rows
  110 -> 82 -> 58 -> 42. Row units: plain quads and 3-edges-onto-1 reductions through two new vertices, spread evenly,
  palindromic from the front centre (mirror symmetry), phases searched for 3-5 edges per vertex. Dead ends, in order:
  two rows 110 -> 56 -> 42 (6-edge and 2-edge vertices); 4-edges-onto-2 units round ONE vertex (the middle fine vertex
  is a 180 degree corner of a quad: 36 "folded" quads); Laplacian relaxation (rows collapsed unevenly); placing the new
  loops by the turn about a vertical axis, by arc length, by arc length pinned at the sides (each sheared or folded
  where C climbs the neck's side: the rows join vertices BY INDEX, so the parameter must be the index). Now: no folded
  quad, bridge aspect median 2.3 / p90 3.2 / worst ~4 (A and C are not parallel: the gap is 1 cm at the sides, 3 cm
  front and back; an artist would tilt the cut). `edits.json` beside the script = hand corrections (moved vertices,
  spun edges; `--obj` / `--edits-from` round trip through Blender), not yet used with a real edit.
- The design that made it simple: every GNM skin vertex and bridge vertex is BOUND to a point of MakeHuman's
  reference surface (triangle + barycentric; registration residual 0.17 mm rms). `onemesh.bound(params)`: any
  MakeHuman body (growth, sex, weight, bust: whatever makehuman.body takes) carries the head = a similarity (the
  head's size) + the remainder smoothed over GNM's mesh, held hard round the stitch; eyes / teeth / tongue rigid with
  a scale from the skin beside them. Ring A lies within 0.2 mm of the body at every age; the bound head within 0.2 mm
  mean / 0.5 mm p95 of the body's own head (follow_body: 2.5 / 6-9 mm). No per-age delta arrays, no head scale.
- `base.gnm_head` runs unchanged and one hook (`head["bound"]` -> `onemesh.hook`) lays everything it made, as a
  DIFFERENCE from GNM's template (identity, expression, regions, pose, eye size, planes; then pushes / simplify in
  world), on the bound head, faded to 0 over 7 rings above the stitch. So landmarks, eye seating, lip zip, GnmFace's
  carry keep working. `onemesh.head_desc`: the seed stripped of its own age / sex / weight and `features` solved by
  headfit.follow on a pseudo base; `dimorphism` (0.8) from head_fields on the head only; `toward`.
- Wiring (4 guarded branches in base.py; old paths bit-identical, checked by hashing the built base of the golfer, two
  grafted humans and the template against main's code): `base.source` -> `onemesh.template` (fused quads at this
  body's shape: "fid" = asset index, "n_mh", "n_body", "chin_lm", "chin_mh"), `base.head_of` -> `onemesh.head`
  (posed by the same skeleton warp as the body), `base.surface`: one quad mesh -> Catmull-Clark -> IMLS, no tube /
  cross-fade / seam weights, "graft" None, "src" = arange. `rig_template._one_mesh`: the asset's weights by index
  (MakeHuman's hand-made ones; through the binding on the head; 139 bones folded as before), the arm's side handed to
  Neck within GRAFT_REACH above the stitch; rig3's head rule runs on top as for any base with lm_* joints.
  `humans.spec(source="human")` / `human(..., source="human")`.
- `humanfit.py` + tools `measure_human`, `fit_human`, `nudge_human`, `human_reference`, `guide(topic="human")`:
  named measures (body cm via anthro.measure; face mm from the 68 landmarks + eye centres, `FACE`; ratios "a/b");
  `solve` = minimal-change Gauss-Newton (landmarks are LINEAR in GNM's identity components: headfit's LB tables, so
  the Jacobian is analytic; body macros by finite differences), every measure not asked for held, far landmarks
  held, ridge toward the current state, components clipped at 2.6 sigma, and the step CUT BACK where an unasked face
  measure would move > 2x its tolerance (`COLLATERAL`); `nudge` (one landmark, mirror together, the rest a Gaussian
  push in shape.push_more, reported as "the sliders can't do this"); `fit_views` (cameras + identity jointly on named
  2D points, multi-view); `side_effects` (all measures before -> after, UNINTENDED, displacement outside the asked
  region); `integrity` (faces folded BY THE EDIT, edge stretch per region against the same body with a plain head,
  lids over eyeballs, lips crossed, sigma). A broken result is not saved unless forced. Lessons: comparing folds
  against the plain head called every open lid broken (compare against the state before the edit); a zipped mouth's
  topology depends on the shape (integrity unzips both); a centre landmark a hair off x = 0 got its push twice (the
  mirror rule): pinned with an offset; one tiny lip face turns with any change (limit 6 faces).
  Measured: nose_width +4 mm met with 2.6% of the mesh moved > 1 mm away from it; "eye_width x3" comes back at
  +3.5 mm, held at 31% of the step; a synthetic two-view fit of another seed: 0.3 px, 3D landmarks 3.3 -> < 1.5 mm.
- Tests: `tests/test_onemesh.py` (asset topology / symmetry / bridge, the stitch at 1-78 y, determinism, identity
  fades at the stitch, old paths never call onemesh, measures vs the grafted path, weights by index),
  `tests/test_humanfit.py` (measures, a met measure, adversarial requests, nudge, fit-back from images).
- Later the same day: GNM's lower neck rings (13..21) are SLID along their own columns on MakeHuman's surface so ring A
  ends 21 mm above C all round (it was 1 cm at the sides, 3 cm front and back); the rows are still skewed at the
  neck's side (A's and C's vertices are spaced differently round the neck, and rows join by index): bridge aspect
  median 2.3 / p90 3.3 / worst ~5, no folded quad, no gap (the pale slivers in om_02_neck's three-quarter back view
  were the PIL viewer culling warped quads at the silhouette: with back faces drawn the surface is closed; min quad
  area 6 mm2). An artist's hand pass through edits.json is still the fix, and edits.json is still unexercised.
  Image fits and solves hold the skull (`_skull_basis`: headfit's cranium and far dense points; it moved 16 mm
  unseen before). Fit replies carry the whole DRESSED figure before | after (`_human_figure`, two looks, ~1-3 min).
- Style, round 0 (`humanstyle.py`, `base.style.human`, `human(style=)`, sheets `styles/human_feature|cartoon|anime|
  lowpoly.json`; scratch sheets only, adult clay): head sliders are ops on GNM's vertices inside `onemesh.hook`
  (head_size about the neck's top, cranium, eye_spacing / eye_height as Gaussian moves of the orbits, nose toward the
  face, jaw / chin as a narrowing of the lower face, cheeks along normals, mouth, exaggerate = the identity x a
  factor), faded at the stitch; body sliders (legs, arms, torso, shoulders, hips, hands, feet, limbs, waist, chest)
  are joint targets + girths through `retopo._skeleton_warp` inside `onemesh.template` (the head rides: `head_rest`,
  `_carried`), so rig, weights, landmarks and face shapes stay. RANGES clamp each slider. What round 0 showed: a
  short ramp for `cranium` made a ledge at the brows (now from the eye line up over 2 interoculars); jaw + chin at
  full strength made the chin a line (capped at 62%); `face_flat` toward a plane collapses lids and lips (range cut
  to 0.25: an anime face needs its features on a smooth proxy and its own eye part); girth on the neck -> head bone
  squeezes the HEAD (no `neck` slider); `nose` leaves the nostrils as a dark pit; integrity now reads stretch against
  the head's own scale. The four sheets are FIRST GUESSES: not fitted to any reference, not seen dressed, not judged.
- HANDOVER (onemesh agent, context nearly full, 2026-10-06). Branch worktree-agent-aac6bb85823bc8809; tests
  test_onemesh.py / test_humanfit.py pass at the last asset (sha c040e681...); main merged in at f5e7b3c.
  Scratch (worktree `scratchpad/`, untracked): t3.py (one clothed person through the tool), hf1/hf2/hf3.py (fit
  exercises through the tools), st1.py <png> [labels] (each style slider on an adult, clay, PIL: seconds), neck.py /
  neckb.py / worst.py / flip2.py / chk.py (bridge views and numbers), oldhash.py + `orig/` (old paths bit-identical
  against main's code: re-extract with git archive), lineup log. Line-up panels: /mnt/data/hifipushie/onemesh/lineup;
  re-lay with COMPOSE=1 spikes/onemesh/lineup.py <that dir>.
  Open, in the order I would take it:
  1. Proof still owed: rig sheets on a one-mesh adult (arm raise 60, head turn 33, nod; `rig(name, pose=...)`), one
     export through export_asset (topology = the base's own quads via retopo.base_quads, which already skips
     graft_head for this source) + Khronos + rig audit, a face-shape sheet (GnmFace reads head["carry"]; carry has
     "fade" per GNM vertex and subdivide 0: faceshapes must multiply deltas by fade and not assume one subdivision:
     UNTESTED and likely needs two lines there).
  2. Guard rails not built: functional checks as a pre-export gate (blink, jawOpen, rig pose), self-intersection
     (lips / teeth; only lid landmarks vs the eyeball now), warnings that persist (each tool call re-runs integrity,
     nothing is stored), plausibility for body sliders, outline / mask fits (stylised references are read by
     silhouette), MediaPipe Face Landmarker + a 478 -> 68 table as the default detector (Apache-2.0, ~4 MB;
     Depth Anything V2 SMALL only is Apache; the anime detector is MIT but drags mmdet / mmpose; Marigold's licence
     unverified).
  3. Style rounds against references (the user's stretch goal): fetch CC / permissive sheets into
     workspace/human_refs/, landmarks -> human_reference for the face, outline fits for the body, tune the sheets,
     send reference | ours | sliders. Missing sliders the rounds will want: neck thickness / length in head space,
     an anime eye PART (bowl + iris disc, option of the same mesh), face projection onto a proxy, feature simplify
     per region, per-style custom normals and the toon look / outline recipe in the export, low-poly as un-subdivided
     levels with flat shading. A 1.45x eye already stretches lid edges ~2.3x against the head's scale (integrity
     warns from 1.8x): a 3x anime eye will need the alternative eye part.
  4. Template: the neck's side rows by hand (edits.json) or a hand-drawn GNM loop; thin GNM's neck for LOD1+; UV
     repack; eyes / teeth / tongue / sock of the asset are unused by the field (blobs + the kit interior as before).
  5. `like`, `neck`, follow_body's strength are ignored on this source; humanfit's body solves take minutes (finite
     differences on MakeHuman builds); head_sheet is flat-shaded.
- Proof + Garrett, round 1 (2026-10-07/08, "onemesh2" agent, branch `worktree-agent-abebc7b0353b5a6fe`; renders
  `workspace/human_renders/om2_*`, line-up re-rendered `om_10_lineup_*`; scratch DURABLE in /mnt/data/hifipushie/onemesh2/:
  run.sh <script> (worktree code on the main workspace), run_orig.sh + orig/ + oldhash.py (old paths bit-identical vs
  main 23b8b9e), exp.py (export), sheets.py (rig poses through rig(glb=); "-" = look build), closes.py (rest / jawOpen /
  blink / smile close-ups of a GLB), glbz.py + zview.py (z-buffered numpy views of a GLB's or a mesh's triangles, back
  faces red: what showed the mouth's faults when Blender's clay hid them), idx1.py (face shapes by index on retopo.wrap's
  quads without an export: unevenness, contact-ring gap, mouth crops; env RAW / NOMEET / NOSOCK / CC / LC), blinkglb.py
  (lid jag + unevenness from a GLB's own targets), torn.py (where a quality report's folds / turned faces are, by GNM
  group), facem.py (humanfit's face measures for ANY base, old path too), g_try.py / g_fit.py / dense_fit.py (Garrett's
  fits), proof.py + seatlib.py (regen's: s0urc3's seated pose, two GLBs, same cameras), bodym.py, mk_garrett.py,
  variant.py / setbase.py / setkey.py (spec patches), tests.sh).
  - Fixed: `humanstyle` head_size pivoted on a bounding-box corner (the fade's 0.4-0.6 band is empty: levels 0.39 / 0.61):
    the face slid 10 mm sideways and 2 cm forward. `onemesh.VERSION` is in store's build key and base.surface's key
    (bump it for one-mesh field changes; old paths keep their keys).
  - Phase 1 read: rig on a one-mesh adult is MakeHuman's own (head turn, arm, knee clean; nod: the known nape bump;
    audit 8 BAD of 51). Decimated export works (Khronos 0/0) but its blink is ragged (no face focus on the test adult).
  - Own quads (parts.body.topology "wrap") is now THE path for face shapes on the one mesh: `retopo.base_quads` returns
    `gnm` (each vertex's GNM id, into topology_<p>.npz), does not snap GNM's interior surfaces (non-exterior skin) or
    ears onto the field (they folded: TORN at both eyes, 60 spots on Garrett's ears), and adds GNM's mouth sock
    (`_with_mouth_sock`: placed as the skin, carried by the skin's post-placement moves, tucked in by SOCK_TUCK so it
    can't stand out through the lips' corners). asset attaches `gnm_index` to the low poly when its vertices are still
    the topology's; `faceshapes.apply` then passes it: GnmFace takes GNM's offsets BY INDEX (`_by_index`), no lid seal,
    the neutral closes the lips on GNM's contact ring (`_lip_rings`, `_lips_meet`, smooth in x; taken back by a shape in
    proportion to how far it parts the lips) and at the corners (`_corners_meet`, kept). The kit's slit isn't meshed on
    this path (`voxels`); give `interior.slit` ~0.0003 so the field has no gash for the bake. mouth_gap may be left out
    on the one mesh. `asset.mesh_quality(designed=)` leaves the lid margins, lips, interior and sock out of TORN; GNM
    head faces are never dropped as hidden. Adult: jawOpen unevenness 0.05 (projection on the same mesh: 3.19), blink
    0.03 (v23 0.15). Test `test_face_shapes_by_index_on_own_quads`.
  - Garrett: `workspace/om_garrett` (garrett_v20 copy, clothes out; `om2_g23` = the same on the old path). head_size
    1.12 (v23's head scale: interocular 69.5 mm), fit_human to v23's 17 measures, then dense_fit.py (both are GNM rows:
    identity by ridge LS on every exterior skin vertex, face weight 1 / cranium 0.3 / ears 0, then an RBF warp in
    GNM's frame, base.head.warp): face 3.21 -> 0.55 mm mean, 1.09 p95; head 2.85 / 10.6 (cranium under hair). Then own
    quads + mouth_gap 0.003 + interior.slit 0.0003, skin.only eyes. Export /mnt/data/hifipushie/onemesh2/exp_garrett3
    (40k, Khronos 0/0, no TORN, shapes <= 0.13, seated clean, audit 7 BAD vs v23's 9). Stature +2.9 cm (head grows
    from the neck's top): body.height 1.771 would give it back (not done).
  - Round 2 (same agent): the bridge is five rows (COUNTS 110-94-78-66-54-42, SHEAR 0.85: median aspect 2.36 ->
    1.71, worst corner cos 0.18 -> 0.31; the toddler's ring of pits at ring A gone; wider IMLS kernels there made it
    WORSE: speckle, reverted). Asset rebuilt: every one-mesh model's topology changed. Garrett v15: body.height 1.7715
    + head_size 1.138 (stature 180.6, interocular 69.8), dense fit again (cranium weight 1, lips 0.3: face 0.68 /
    1.30 mm, head 1.45 / 7.7); export exp_garrett5 (Khronos 0/0, no TORN, height range +-7.6: interior texels keep the
    low poly's surface in the bake). Lip corners: the sock tucked in behind the corners (SOCK_TUCK), inner rolls pushed
    by the outer skin's normal. Hair: `hair._measure` (one mesh only) skips pockets in the head (POCKET: GNM's ear canal
    rooted his nape locks 4 cm in). A groom regrow on Garrett grows tiers over / buries his hand locks: don't; the
    band of bare volume at his front hairline needs a "re-seat hand locks on a changed scalp" step (hair thread).
  - Reference pass 1 (concept_v8 front crop + concept_v6 desk painting at -45): detect.py (MediaPipe Face Landmarker
    from /mnt/data/hifipushie/facerefs_venv, MP68 table) -> hrefs.py (human_reference, drop lists) -> refsheet.py
    (reference | models through the fitted cameras | blend | landmarks). Copy `om2_gref` (om_garrett untouched):
    front 6.8 -> 3.3 mm, desk 7.3 -> 3.9 mm reprojection; sheet human_renders/om2_r1_pass1.png. Couldn't: jaw
    contour (MediaPipe's != GNM's: +21 mm jaw, dropped), iris vs eyeball centre in 3/4 (dropped), hooded lids (lids x3.2
    BROKEN: dropped), neck_circ measured at the chin's height reads -9 cm when the chin moves (measure bug), no ear /
    hairline / crown evidence. Next: an outline fit (silhouette chamfer through the fitted cameras), pass 2.
  - Reference pass 2 (2026-10-08; scratch pass3.py om_garrett om2_gref3 1, sheet human_renders/om2_r2_pass2.png =
    reference | before | pass 2 | blend | landmarks, model `om2_gref3`; om_garrett untouched apart from its
    human_refs.json, which holds the cameras the sheet uses). Order: points (identity; eye centres, lid corners, lower
    lids back in; no jaw, no upper lids) -> `fit_hood` (upper lids) -> `fit_outline` (front view only, 5 rounds).
    - `humanfit.fit_outline`: the head's silhouette through the fitted camera (vertices whose faces turn front to
      back, `_silhouette`), each outline point's miss along its normal turned into a move in the image plane at that
      vertex's depth (capped `OUTLINE_STEP` 4 mm a round), then into GNM's frame and solved as an RBF warp appended to
      base.head.warp; brows / eyes / nose / lips landmarks and skin far from the targets held (`OUTLINE_HOLD`).
      Mirrored targets by default (`symmetric`): one view's outline warped only its own jaw (a lump). Putting the
      outline into fit_views' identity solve folded lids and lips: dropped. Front: silhouette miss 8.3 -> 0.8 mm,
      widths at eight levels (temple .. chin, MediaPipe oval pairs over the photo's pupil distance) within 1-2.5% of
      the photo. The DESK painting's outline is not used: its camera is the weak fit and with it the jaw came out 8%
      wide on both sides.
    - `base.head.shape.hood` (m | {amount, forward, reach}; `base._hood`): the fold between upper lid and brow comes
      down (and 0.4 of that forward), the lid margin with it by the falloff, gated off at the corners' height (lower
      lid and eyeball seat stay), landmarks ride. 3 mm: upper lid landmarks -1.2 mm, eye height 8.9 -> 7.7, 0 folds,
      lid stretch slightly LOWER. `humanfit.fit_hood`: one number, linear, [0, HOOD_MAX 5 mm], halved until integrity
      holds. Garrett asks 4.0 mm (upper-lid rms 1.28 -> 0.93 px).
    - neck_circ: one level (`NECK_AT` 0.35 of neck joint -> body chin) on body + bridge vertices only
      (`humanfit._neck_girth`; anthro.measure unchanged): 31.9 cm before and after any face fit.
    - Left: the points step with lid corners + lower lids reads lids x3.2 BROKEN by itself (x2.7 warning after the
      hood); the model's pupils are 8% closer than the photo's at matching face width (69 mm already: widening
      them fights plausibility; the photo's eye centres or MediaPipe's oval are suspect); a bald clay head under the
      hair's silhouette (no crown / hairline evidence); asymmetric pictures are made symmetric by design.
    Tests: test_humanfit test_neck_girth_ignores_the_face, test_hooded_lids_fitted_from_a_picture,
    test_outline_fit_is_symmetric_and_holds_features.
  - Reference pass 3 (2026-10-08; the coordinator on pass 2: "matches by measure but bloated and jowly, pear-shaped";
    scratch pass4.py om_garrett om2_gref4 <hollow mm> 1, sheet human_renders/om2_r3_pass3.png = per view a clay row
    (reference | before | pass 2 | pass 3 | blend | landmarks) and a LIT row (key from the upper left, smooth normals:
    refsheet3.py), model `om2_gref4`; NOT applied to om_garrett).
    - Measure first: `humanfit.cheek_hollow` = horizontal sections from the nose's base to the mouth's corners, the
      OUTER cheek's contour (from 0.4 of the way nose wing -> jaw contour, `HOLLOW_FROM`: nearer the nose the deepest
      point is the nasolabial fold, 3-4 mm on every head) against its convex hull. before 0.3, pass 2 0.35, pass 3
      2.2 / 2.6 mm. (A vertical section at fixed x read the muzzle's side, and a section through the jaw's underside
      read every face as a 12 mm bulge: both dropped.) The points step (identity) is what made the cheeks full: on a
      vertical profile -3 -> -8 mm, the outline only -8 -> -10.7.
    - `fit_outline(structure=True)` (default): outline targets on GNM's cheek regions count `STRUCTURE_SOFT` 0.25 and
      the cheeks' front (cheek regions, normal forward) is HELD (`STRUCTURE_HOLD`), so the warp widens the head's sides
      (zygoma, jaw angles) instead of filling cheeks; ear vertices are left out of the silhouette (`skip_ears`). Per
      view `outline_axis: "y"` (heights only: the desk painting's near-side jaw / cheekbone heights, weight 0.7; its
      miss 9.9 -> 4.2 mm) and `outline_weight`. Widths still within 2.5% of the photo at all eight levels.
    - `base.head.shape.hollow` (m | {amount, radius, at, share}): a dent under the cheekbone, centred where a ray from
      the jaw/mouth landmarks' mean, 37 deg out from straight ahead, meets the cheek (the mean of two landmarks across
      a convex cheek is INSIDE it: the first try dented half its amount at the face's side; the frontmost point dented
      the lips' corner). 5 mm on a plain head: hollow 0 -> ~2 mm both sides, no folds. Pass 3 used 2.5 mm.
    - MediaPipe's oval on the front photo (overlay oval_front.png in scratch): runs on the face's edge from the ear's
      root down; its top (temples, 127 / 356, and the forehead) is the hairline: those points are left out now.
    - Honest read of om2_r3: in the lit rows pass 3 has shading under the cheekbones on both views and reads closer
      to the photo than pass 2; but the lower face is still broad and soft, the jaw corners rounded (no bony angle),
      a lump at the subject's left jaw in the front view, and the bald clay head reads small against the hair's
      outline. Next: a jaw-angle control (bony corner + the under-jaw tucked), the points step held off the cheeks.
  - Reference pass 4 (2026-10-08; scratch pass5.py om_garrett om2_gref5 2.5 4 1, sheet human_renders/om2_r4_pass4.png:
    per view clay | lit | lit WITH the groom's volume (hair.cap_mesh mass=True on each model's own scalp: a stand-in
    for the locks), columns before | pass 3 | pass 4; model `om2_gref5`; NOT applied to om_garrett).
    - `fit_views(hold_cheeks=True)` (default): the cheeks' fronts held by `_cheek_basis` (GNM cheek-region vertices
      facing forward, d/d identity), `HOLD_CHEEK` 0.25 / mm. Points step: cheek hollow 0.26 -> 0.23 (pass 3's
      points step: -> full), points rms 3.35 -> 3.63 mm. The outline then widens the jaw more (jaw_width 136.7).
    - `base.head.shape.jaw_angle` (m | {amount, tuck, radius, tuck_radius}): a bump at the jaw's angle, which on the
      bound head lies ~33 mm behind and 20 mm under GNM's lm 3 (GNM's jaw-contour landmarks are on the cheek's side;
      measured: section at lm 3's x, the jaw's underside drops to the neck at y ~ -45 mm), plus the under-jaw (under
      lm 5-6) tucked in, snapped onto the surface in its own x. W-level pushes in gnm_head act on the BOUND head
      (onemesh.hook returns it before placement), so world offsets measured on the final head are valid there.
    - The front view's "left-jaw lump" is not asymmetry: the head is symmetric to 3.6 mm at the jaw (asym.py; same
      before any fit). Straight on (frontal.py) it is both jaw corners standing out past the neck; the fitted
      camera's roll (-7 deg) and pitch (15 deg) show one of them.
    - The "8% pupils" is a definition: MediaPipe's eye points are the irises; ours the eyeballs' centres. The outer
      eye corners are 6% WIDER on the model than the photo (80 vs 75 px). Real miss found: the MOUTH is 15% narrow
      (lm48-54 38.8 vs 45.9 px); the fit took mouth_width 56 -> 52.5 mm.
    - Read: inside the hair stand-in, pass 4 is a pear again: the groom's volume is thin at the temples (it was
      groomed on v23's head) and the jaw now carries the outline's width. The photo's hair outline is clearly wider
      than its jaw. Next: the cranium / temples and the groom's sides against the HAIR outline (not the face oval),
      the mouth's width, then the jaw's width re-judged.
  - Reference pass 5 (2026-10-08; scratch pass6.py om2_gref5 om2_gref6 57 1, sheet human_renders/om2_r5_pass5.png:
    v23 likeness | pass 4 | pass 5, the hair rows with his REAL locks; model `om2_gref6`; NOT applied).
    - `hair.lock_meshes(sc, locks)`: the locks as numpy lens tubes (lock_extents' construction, outer + cupped inner
      face) for quick renders and silhouettes without Blender. His 624 locks are all hand locks in [az, el, h]: they
      re-seat on any head's scalp by themselves (lock_world); no re-seat step was needed (round 1's trouble was the
      scalp rays entering the ear canal, fixed then).
    - The photo's head outline (head + hair against its plain background, scratch hairfit.py) vs the model with his
      locks, levels from the top of the hair to the ears' top: the bare cranium is about right at the temples' skin;
      the HAIR is 15-23 mm per side thinner than the photo's (his groom: volume.sides 6 mm).
    - `hair.lift(spec, sc, {region: m})`: the whole groom fuller by region (lock points' h + groom.volume by the
      volume's own region weights), eased in from the hairline over `LIFT_RAMP` 3 cm (lifted at the line it stood off
      the temples as a shelf). Fitted: sides +22 mm, top -1.4: widths within 3 mm at every level, but the outline sits
      ~11 mm to his left (the photo's sweep is the other way round from the groom's parting side).
    - Mouth: solve mouth_width 62 folded 7 lip faces (BROKEN; `solve` reports, it doesn't refuse: pass6.py saved it
      once, re-run since); 59 squeezes the lip corners past 0.25; 57 is the most that holds (mouthtry.py).
    - Read: with the lift the hair matches the photo's outline and reads as a stiff helmet with flared sides: lock
      shapes made for 6 mm of side volume, pushed out 22 mm. A fuller cut needs regrooming the sides (the hair
      thread's tools), not a lift. The face in pass 4/5 is broader and squarer than v23; v23 keeps the long lean face
      the director approved. Tests tests/test_hair_lift.py.
  - Reference pass 6 = APPLIED (2026-10-08; the coordinator: "v23 is the one that reads as the photo's man"):
    v23 (om_garrett v15) + base.head.shape hood 0.0035, hollow 0.005 (measured hollow 0.27 -> 1.95 / 2.24 mm),
    jaw_angle 0.0025, mouth 56.0 -> 56.5 mm by solve (57 squeezed v23's already-broken lip corners 0.24 -> 0.22:
    refused); no outline warp, no hair lift. om2_gref7 -> om_garrett v16 (scratch pass7.py, applybase.py).
    Cameras for the sheets fitted to v23's own landmarks with no identity (camfit.py; 4.6 / 5.9 mm rms).
    Sheet human_renders/om2_r6_pass6.png (v23 | pass 6, front + desk, clay / lit / his locks). Export
    /mnt/data/hifipushie/onemesh2/exp_garrett6 (30k / 2048, rig + face shapes, Khronos 0 / 0, body quality 16 folded
    edges / 11 turned (v23's export: 13 / 11), unevenness <= 0.13, height range +-6.7 mm); blink vs v23's export
    (om2_r6_blink_v23_vs_pass6.png): same clean closed line, lid jag p95 0.95 / 0.88 (v23 0.91 / 0.85).
  - humanfit's fits (solve, nudge, fit_views, fit_outline, fit_hood) REFUSE a result the edit broke: the input
    comes back with rep["refused"] (`_guarded`), unless force=True. A region already broken in the input (v23's lip
    corners squeezed x0.24 against the plain head) counts only if it got `GUARD_WORSE` 8% worse (`_newly_broken`).
    A 3 cm chin nudge is now refused (test_nudge updated: forced, it still makes its correction layer).
  - Open: the head's 46 mm leak onto shoulder skin at Head 33 (rig thread); own quads cost a fixed ~40.7k body
    triangles; dense_fit as a tool (a GNM head as the target of human_reference).

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
