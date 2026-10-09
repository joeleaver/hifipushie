# hifipushie notes: faceshapes

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

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

