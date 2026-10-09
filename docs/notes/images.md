# hifipushie notes: images

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

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

