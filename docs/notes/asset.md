# hifipushie notes: asset

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

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

