# hifipushie notes: base

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

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

