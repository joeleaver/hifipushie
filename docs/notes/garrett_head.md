# hifipushie notes: garrett_head

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

## Garrett's head, dressed (2026-10-09, "garrett3" agent, branch `worktree-agent-a134642c7a6403455`)

Takes over from refstudy2. Scripts `spikes/garrett3/` (stage.py = the DRESSED head stage `_g3_<model>[_posed][_tex0]`:
skin_look's head crop + the groom, renders through fitted cameras (humanfit camera + pixel crop -> frame with lens
shift) or the six views, hair by the hair_look job; mk.py <dst> <src head> = src + the skin description (tone
measured on the photo, age 52, stubble, brows, eyes) instead of the hand paint; sheet1.py = the judging sheet
(reference | skinned + groom | blend, six views); sheet4.py = with / without the reference texture; refit.py = the
MAP + structure again with a pose from a file; lidcmp.py = analysis by synthesis + patches tried in memory;
posecal.py, lidbias.py, mp206.py, tex.py, mk_measured.py, memdbg.py). Scratch DURABLE /mnt/data/hifipushie/garrett3/
(run.sh <script>, go1.sh / go2.sh <head model> = both sheets, tests.sh, p*.json patches, shape_c.json, out/). Models:
g3_b (refit, detector pose), g3_c (+ age ops), g3_f (final head: + eyes / mouth by like-with-like), `g3_garrett` =
g3_f + skin description + groom (the candidate). Sheets `workspace/human_renders/g3_01_dressed_head.png`,
`g3_04_reference_texture.png`.
- A 1 mm head stage of a one-mesh body was a 1e9-cell grid (12 GB: killed): `scene._frame` now bounds a part's grid
  by region (intersect) primitives that come after every add (skin_look's crop box). Stage sync ~95-160 s, a sheet
  (8 renders, 2 lights) ~4 min once synced. `blender_scene.render` takes `"transparent": true`.
- ANALYSIS BY SYNTHESIS (lidcmp.py; guide section): the SAME detector on the photo and on the model's render through
  the fitted camera. rs2_m3 against the photo: eye opening 10.9 vs 7.8 mm, eye width 33.6 vs 30 mm, brows 1.4 mm
  high. With `eyes` 0.9, the lid-opening expression regions OUT, held macros eye_height -1, eye_width -0.8: opening
  7.6 / 7.5 (photo 7.8 / 7.2), brows +-0.1 mm, and the detector's own scores on the NEUTRAL head equal the photo's
  (browDown 0.53 / 0.47 vs 0.63 / 0.57, eyeSquint 0.62 / 0.49 vs 0.68 / 0.53): the photo's "frown and squint" are
  the man's face. No pose is kept (g3_f/pose.json = {}).
  - fit_hood's "the picture's upper lids are HIGHER" was not the lid points' definition bias (lidbias.py: the
    detector's upper-lid points sit 0.6-0.9 mm UNDER GNM's landmarks, lower-lid 1.5 mm over: its opening reads
    2-2.5 mm small, which would say "lower"); like with like the photo's lids are LOWER and the eyes smaller.
  - Pose from blendshape scores (posecal.py, 600 renders with known poses): cv rms / sampled sd: smile 0.80,
    lid_upper 0.83, mouth_width 0.92, brows 0.97, lid_lower 1.1: the scores can't tell a pose from an identity on
    our renders. The photo has NO mouthFrown score (0.0; press 0.17 / 0.07): the hand pose's "smile -1.5 mm" was
    unsupported. Mouth corners by the same detector: photo -0.4 mm, rs2_m3 -0.4, a refit without the mouth pose
    -1.4; lifted by the identity alone (humanfit.nudge 1.5 mm, its bump dropped): -0.8.
  - LIMIT: like with like fails where the photo's texture differs from clay: the detector's lower-lip height read
    10.8 mm on the photo (stubble shadow under the lip) vs 6.4-9.0 on renders; lip_fullness +1.4 "matched" it and
    looked wrong (duck lips): reverted. Trust it for eyes and brows, not for lips.
  - A camera-only refit of the turned painting on the changed head came back ~15 deg more frontal at the same 2 mm
    residual: sheets use the cameras stored with the MAP fit (REFIT=1 refits).
- `headage.py` (base.head.shape nasolabial / prejowl / lid_fold / cheek_flat / lips_thin; tests/test_headage.py;
  bit-identical when unset; the nasolabial crease runs on skin.LINES' own line). On Garrett: nasolabial 2 mm (bulge
  0.3), cheek_flat 2, prejowl 1.5 / 1, lid_fold 2, hollow 2.5 / 26 mm (4 mm read as a bruise under frontal light),
  held macro cheek_fullness -0.8. base.VERSION not bumped (new keys change the spec's hash).
- `likeness_texture.py` + MCP `texture_from_reference` (tests/test_likeness_texture.py): the fitted picture as an
  orthographic RGBA decal along its camera's axis (exact: each texel's surface point projected through the
  perspective camera), de-lit by one fitted light, masked (facing, visibility, ears, under the jaw's border, hair
  above the brows by colour, not-skin off the features), tone-matched to the skin description, laid as paint
  layer "ref_texture_<view>" ("color": "image"). Garrett's front photo: 42% of the head's texels along the
  camera, 1.33 mm a pixel. With it the head reads as the man from the front AND turned (g3_04); without it the
  procedural skin reads as a waxy stranger of the right proportions. The painting as a second view lands brush
  strokes and lamp colour on the skin: not used.
- `humanmeasure.py` + `human_measured.npz` (spikes/garrett3/mk_measured.py; tests/test_humanmeasure.py):
  `human_reference(measure=True)` / `humanfit_map.fit(measure=True)`: macros regressed from the detector's points
  join the read (renders only). The LOW outline levels (0.6 / 0.75) add nothing in cv (jaw_width 0.52 with or
  without): points only is the default.
- mp206 / mp426 (mp206.py, 6 truth renders): no left / right swap. The detector puts 206 at x -30.1 mm and 426 at
  +30.0; our table says -29.5 / +29.2 (0.8-1.0 mm from truth); XR Blocks' vertices have the same x and lie 57 mm
  away in depth / height (another surface): their table's fault at those two points.
- `base.pose_expression` caches its constant landmark matrix (0.5e9 multiplies a call: 20 s -> ms).
- BLUNT READ of g3_01 (procedural skin): proportions and eyes are the photo's; it still reads as a heavier, waxier
  man: flat orange-pink skin without the photo's planes, brows as drawn bars, lips thin and set, stubble as grey
  patches, the groom a dark solid cap with a hard hairline. Of g3_04 (the photo as albedo): reads as him.
- Round 2 start (the coordinator on g3_01 / g3_04: "lower face heavy, chin big, eyes small and close, mid-face
  short": checked like with like, lidcmp.py's face / heights / ratios rows, g3_f against the photo): every width
  +5..6.5 mm (cheek 170.3 vs 165.1, jaw 155.7 vs 150.0, chin 101.1 vs 96.0) while pupils are 1.4 mm CLOSER: the face
  is ~3-4% too wide for its eyes at every level, not heavy low down (jaw / cheek 91.4 vs 90.8%); nasion -> chin
  4.5 mm SHORT (subnasale -> lip seam -1.7, seam -> chin -2.9): the chin is short, not long; height / cheek width
  80.8 vs 86.0. Tried (patches p9-p11, nothing adopted): `head.narrow` 0.97 fixes the cheek width but scales the eyes
  with it (pupils -4.3 mm); eye_spacing macro +2 moves NOTHING (the one mesh's eye spacing is the body's);
  chin_height +1..1.5 barely moves seam -> chin; macros face_width -1.2, cheekbone -1, jaw_width -1, chin_width -1.5,
  jaw_square -0.5, face_length +0.8, philtrum +0.5, chin_height +1.5 (saved as `g3_g`, EXPERIMENTAL) overshoot the
  widths (cheek -3, jaw -4.6 mm), shorten the nose 3.7 mm and put a component past 2.6 sigma: about HALF of that
  with nose_length held is the next try. The candidate stays g3_f / g3_garrett.
- HANDOVER (garrett3, context full, 2026-10-09). The coordinator's order for the next agent: (1a) the texture layer
  through an export bake (image decals already bake through Cycles: untested with this layer; the painting only as
  low-frequency tone); (1b) the skin description's own look against the photo with skin_measure (zones, stubble as
  dots over a blue-grey shadow, brows as hairs at the photo's thickness, vermilion edge, specular break-up); (2)
  the widths / heights above, the under-chin line; (3) hair5's cut on g3_garrett in the sheets (told: model
  g3_garrett); (4) measuremodels' humannormals rows in humanfit_map._fit (its message gives the call: once per
  outer round, front photo only, hair hidden); (5) 3 blind readers on the textured head, then the export. To redo
  the sheets: /mnt/data/hifipushie/garrett3/go2.sh <head model>.
- NOT DONE: blind readers (none run); the neck (body's 31.9 cm); the desk painting's own lighting match; nose
  untouched (like-with-like: width -0.1 mm, length -0.2 mm against the photo: already right); under-chin line;
  the texture layer through an export bake; measuremodels' normals as evidence (humannormals, branch
  `measuremodels`: proposal received, not wired).

