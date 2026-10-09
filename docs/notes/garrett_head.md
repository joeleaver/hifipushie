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


## Likeness loop (2026-10-09, "likeloop" agent, branch `worktree-agent-acaab377fb132321d`, garrett4's branch merged in)

One question per round: does Garrett's head look like the front photo? Scratch DURABLE /mnt/data/hifipushie/likeloop/
(run.sh, try.py <model> <tag> <ops.json> [save] (ops: nudge / held macros / solve / set paths; matched pair in out/),
mkd.py <dst> <head model> [patch] (= g4_garrett's skin + the head + h7_garrett's groom), shot.py from garrett4 with
D3=likeloop, calib.py, fid.py, view.py / small.py (crops to look at once), deliver.sh). Models: `ll_garrett` (head,
g4_a + rounds 1-3, 5), `ll_d0` (start dressed = g4_a), `ll_d2` (end dressed). Sheets `human_renders/ll_*_pair.png`,
`ll_summary.png` (photo | start | end, dressed over clay).
- HARNESS: `likeness_pair.matched(name, base)` / `sheet()` (src; photo crop and the clay render through the photo's
  fitted camera, NOT refitted, lit by the photo's fitted light; photo | model | 50/50, canthal lines, a flicker GIF,
  20 checklist rows by the same detector; ~7 s, no Blender). `faceid.py` (asset pack `faceid`: YuNet + SFace (Apache)
  + ArcFace w600k_r50 (InsightFace, non-commercial: measuring only); runs in the detector venv; tests/test_faceid.py).
- FACE-ID CALIBRATION (cosine, sface / arcface): photo vs altered copies (blur, brightness, 4 deg turn, grey, 1/6
  size) 0.91-0.97; vs Garrett's desk painting (same man, painted, turned) 0.36 / 0.26; vs 8 unrelated photos -0.13..0.09;
  clay vs clay of OTHER people 0.47-0.79 (renders cluster); photo vs ANY render, clay or procedural skin, his or a
  stranger's: -0.16..+0.11 (his start -0.04 / -0.01). Only the photo-as-albedo renders reach "same person" (g4 s5
  front_tex 0.40 / 0.33, three-quarter 0.30 / 0.25), and that is the photo's texture talking. VERDICT: the score
  can't see our geometry across the render / photo domain gap; per round it stayed in noise (clay: r0 -0.04/-0.01,
  r1 +0.03/+0.01, r2 +0.04/-0.03, r3 +0.02/-0.03, r5 +0.03/-0.05; dressed d0 -0.02/-0.09, d2 -0.01/-0.08). Don't
  steer by it; it would need a render that crosses the gap (photoreal skin, hair) before it means anything.
- R1 EYE ROTATION. Like with like (same detector, same camera): canthal tilt photo -0.45 deg, g4_a +3.38 (outer
  corners up). Why the checklist didn't catch it: it was never run on the g3 / g4 heads (garrett3 / garrett4 checked
  opening, width, brows by lidcmp / silw), and lk_garrett's correction (-2.3 mm eye_outer nudge) lived in another
  lineage: g3's MAP refit made the identity again. The miss (3.8 deg) IS beyond the 2 deg tolerance. Also: GNM's own
  3D landmark macro eye_tilt reads -3.2 sigma (DOWN) on the same head: the 3D landmark corners and the detector's
  visible corners disagree by several degrees, so a fit on landmarks can't hold this item. Fix: humanfit.nudge
  eye_outer.L z -2.0 mm (mirrored): -0.51 deg. Eyes read level and tired instead of alert. KEPT.
- R2 WIDE / SQUARE / PUFFY. Measured first: every width (temple 153.6 / 151.3, cheekbone 165.4 / 164.1, mouth level,
  jaw 135.4 / 134.7, chin), face index, jaw taper are within tolerance (garrett4 fixed them): the "wide" read is the
  SHAPE inside the outline: macros jaw_square +1.07 sigma, jaw_angle +2.48 sigma (a very square gonial corner).
  Held macros jaw_square -1.5, jaw_angle -1.8, cheek_fullness -1.5, chin_height -0.6 (-> -0.35 / 0.96 / -1.6 / 1.41
  sigma, max 2.46 sigma, fewer flipped triangles): a slightly tapering lower jaw, widths still in tolerance (mouth
  level +2.5 mm, 0.8 tol). Small visible change at this size; KEPT. shape.cheek_flat / hollow / prejowl changes
  were invisible (r2a / r2b) and not kept. Still: the dark under-jaw border + a neck as wide as the jaw.
- R3 NOSE. Detector: alar width 45.1 vs photo 46.9 (ours NARROWER), length right: what read "wide bulbous" was the
  tip: shape.nose_tip up 5 / round 0.5 showed the nostrils from the front and balled the tip. nose_tip {up 0, round 0}
  + held nose_width -0.6, nose_projection +0.5, nose_upturn -0.5: tip hangs, wings tuck, nostrils hidden. KEPT.
- R4 FOREHEAD WRINKLES (dressed, procedural skin): skin.wrinkles had no "forehead" key, so age 52 x detail 1.8 gave
  deep bands over the whole forehead. forehead 0.2, glabella 1.4 -> 0.7, nasolabial 1.0 -> 0.45. KEPT (smooth
  forehead like his).
- R5 EXPRESSION (scowl): the scowl was the brows (thickness 1.3, drop 2 mm, arch 0.4 = a level dark bar pressed on
  the eyes) and the nasolabial SHAPE (headage depth 2 mm + bulge). brows thickness 1.0, density 0.9, drop 0.5 mm,
  arch 1.0; shape.nasolabial depth 1 mm, bulge 0. KEPT: reads less angry.
- STILL DIFFERS (blunt, ll_summary): hair7's groom renders BLONDE / ginger with the merged code (h7_garrett's spec has
  hair7's uncommitted `swoop` key: stripped by mkd.py); skin pink and clean vs his grey-olive stubbled skin; eyes
  green, bright sclera, wide (his are dark and hooded: the upper lid's outer third hangs over the corner; we have no
  hood that does that); mouth a thin downturned slit (his fuller lower lip, softer corners); lower face still fuller
  than his flat planes; ears: his stand out more (ear_out -0.19 sigma: not touched).
- (likeloop, rounds 6+) Merged main 04ad344. test_likeness_texture: the worktree's 4/4 failures were ENV (no
  workspace/ in a worktree: set HIFIPUSHIE_HOME / HIFIPUSHIE_ASSETS, likeloop/tests.sh); main's real failure was the
  code: `harmonise` ramped the hand-over over all of BLEND from the edge, so where the alpha was still fading in the
  picture kept 60%+ of its own low frequencies (a seam). Now fully ours across EDGE_FADE, back to the picture's over
  the rest of BLEND. test_faceid / test_likeness_texture / test_skin / test_hair_loose: 24 passed.
- NOSE (Joe: "his nose IS turned up"; R3 was wrong). Like with like on the desk painting (lk_garrett5's traces,
  nose.py): base line photo +0.6..1.3 deg (rising); R3's head -4.2, R2 -3.2, shape.nose_tip up 5 -2.5, up 10 +0.65
  (match), tip height in 3/4 0.41 vs 0.46; tip RADIUS photo 8.4 mm vs ours 4.2-4.9 at up 0-5, 10.0 at up 10: his tip
  is the bigger, rounder one in profile, so "bulbous" isn't the tip's size there. Front alar width photo 46.8: R3's
  narrowing (45.1) not supported: undone (nose_width +0.6, nose_upturn +0.5 held back). Kept: nose_tip {up 10,
  round 0}. Cost: front nose length 47.2 vs 49.9 (-1.4 tol). ll_6_pair.png.
- EYES (Joe: "focus on the eyes"). `likeness_eyes.py`: per-eye measures by the same detector on the photo and on the
  DRESSED render through the photo's camera (eyes.py; shot.py's big render mapped to photo pixels): open, width,
  aspect, iris_r, cover (upper lid over the iris top), white_below, brow_gap (brow's lower edge -> lid), brow_height,
  brow_tilt, canthal_tilt. Sheets ll_eyes_0..7.png (photo | start | previous | new, 2x row, table).
  Photo: open 7.39, width 28.6, iris_r 6.52, cover 3.46 (27% of the iris), white_below -2.2, brow_gap 12.1, brow_h
  21.0, brow_tilt -12.5, canthal -0.45. Start (g4): 7.43 / 29.2 / 6.43 / 2.83 / -2.6 / 12.5 / 21.5 / -9.3 / +3.6.
  End (e7): 6.53 / 28.4 / 6.36 / 3.35 / -2.84 / 13.5 / 21.8 / -11.5 / -0.2.
  - New general controls (tests/test_headage.py): shape.hood `lateral` 0..1 (fold weight ramps to the outer corner,
    centre shifts out, the lower-lid gate drops past the outer corner so the fold can hang over it; 0 = the old hood
    to the bit) and `extent`; headage `eye_bag` {amount, crease, height} (a bag under the lower lid + the lid-cheek
    crease, margin held).
  - Kept (ll_garrett / dressed ll_e7): hood {0.0012, lateral 1}, eye_bag {0.0012, crease 0.6}, nudges lid_lower -1.0,
    lid_upper -0.6, eye_outer -0.7 mm, head.eyes 0.9 -> 1.0 (iris and width back to his: 0.9 was garrett3's way to a
    lower opening, the hood does that now); skin: brows drop 4 mm, arch 0.3, thickness 1.2; iris #4a5156 (grey),
    sclera #a39a90 (dull); under_eye wrinkles 0.6 tried (crepey stripes, not a bag): back to 0.25.
  - Findings: the detector can't see a hood's fold (no crease point): opening / cover matched while the lids still
    read open; judge the fold by eye. Clay and dressed disagree on the lower lid by ~1.3 mm (white_below clay -1.8,
    dressed -3.0) and lower-lid nudges move the clay but NOT the dressed reading: the dressed opening stays ~0.9 mm
    short from a lower lid sitting high on the iris (cause not found: lid-margin paint / tear line?). Eye depth in 3/4
    (prof_brow_ridge, painting): photo 10.7 mm vs ours 6.0, but tol 8.5 (painting not one projection) and neither
    features.brow_ridge nor macros brow_ridge / eye_depth move it the right way (eye_depth +1 doubled the forehead
    slope): unmeasurable here. skin.eyes.iris_size 0.0125 changed nothing measurable.
  - STILL DIFFERS (eyes): his sockets sit in shadow under the brow (ours bright, flat lid skin); his brows are
    straighter and their inner heads lower; a dark dot at our brow's inner end (garrett4's known brow-image clip);
    the dressed lower lid high. NOT DONE: mouth / Cupid's bow (queued after the eyes). Hair: hair7's base.json still
    renders ginger with main 04ad344 (its swoop "body" / "lay" keys are newer than main's hair.py: stripped in mkd.py).
- (likeloop, eyes under MATCHED LIGHT, e8-e14; sheets ll_eyes_8..14.png, ll_eyes_layers.png, ll_14_dressed_pair.jpg)
  - LIGHT (lightfit.py: likeness_shape.fit_light on the photo and on each render over one skin mask and one set of
    normals): the photo's light comes from [-0.17, -0.88, 0.45] (26 deg up, hardness 0.82); garrett4's light.json key
    was 43 deg up. light_m.json = that key direction, world 0.22: refit on our render [-0.16, -0.85, 0.51], 0.87.
    Socket luminance / cheek (photo | ours e14): upper lid 0.81 | 0.65, the fold under the brow 1.13 | 0.47,
    under-eye 0.82 | 0.75: his orbits are NOT darker than ours under the fitted light (the fold is lit; the "deep in
    shadow" read is the low-res photo's dark lash line + iris): socket deepening NOT done (the measure says no).
  - Detector readings move ~1 mm with light alone (eye width 28.4 -> 26.9, nasion point 2.6 mm): compare only under
    matched light; vertical rows are referenced to the lips' seam (the nasion drifts).
  - LOWER LID HIGH in the skinned render (not in clay): split by experiment, one change each: stage rendered flat (no
    paint: shotf.py) opening 8.46, lower lid 80.9 above the seam (photo 80.5); painted 6.3-6.5 / 82.0. Not the
    waterline (new skin.eyes "waterline" 0..1: off changed nothing), not the lash lines (0.55 -> 0.25: nothing), not
    veins / tear line (nothing), not the gaze (straight; the camera is 9 deg BELOW the eyes, which would lower his
    irises, the other way). MY dull sclera (#a39a90, round E2) was 0.75 mm of it: the reader (and an eye) takes a
    dark sclera for lid. The rest moved with geometry once the sclera was light again: lid_lower nudge -0.8 mm.
  - GATE: opening >= 7.2 mm. Kept (e14, ll_garrett + dressed ll_e14): sclera #c4bcb2, waterline 0 (kept off: no
    effect, cleaner), lid_lower -0.8 mm, eye_outer -0.5 mm, brow_inner -1.5 mm (nudges), brows arch 0 / drop 5 mm /
    soft 0.5 / thickness 1.1, skin.detail 1.8 -> 1.3 (the forehead's crumpled-paper relief), zones eyelids 2.2 /
    under_eye 1.8. e14 vs photo: open 7.35 / 7.39, aspect 0.27 / 0.26, cover 3.24 / 3.46, white below -2.16 / -2.20,
    brow gap 11.6 / 12.1, brow height 19.8 / 21.0, brow tilt -9.9 / -12.5, canthal +0.5 / -0.45, upper lid 88.3 /
    87.9 and lower lid 80.9 / 80.5 mm above the seam, pupil 85.7 / 84.8 mm above the seam (ours ~0.9 mm high).
  - Still: his upper lid shows a lit warm shelf under a dark fold line (hood); ours a smooth plane. Hair: h7_garrett
    is edited live (per-lock `swoop` keys newer than main): mkd.py drops lock keys not in hair.LOCK_KEYS; it still
    renders blond-ginger here.
- (likeloop e15-e16, form round; ll_eyes_15/16.png, ll_16_dressed_pair.jpg) shape.hood `crease` / `crease_at` /
  `crease_width` (a groove pressed back along the fold's lower edge, lateral-weighted; test in test_headage.py):
  crease 1.8 mm at 0.35 shows a dark line over a lit lid shelf on one eye, faint on the other. Brows: drop 5 mm put
  the brow hair ON the lid (no shelf at all, e15): back to 3 mm; darker #544c45, thickness 1.3, arch 0.4, brow.L
  nudged -1.5 mm: brow_tilt only -9.5 (photo -12.5: the paint's slope follows its landmarks, the nudge hardly turns
  it). Lashes amount 1.0, colour #1c1612: still a faint line, not his dark frame (the lash zone is narrow at this
  size; no width option). Wrinkles back: glabella 1.4, forehead 0.5, crows feet 0.45, under-eye 0.25 (0.4 = crepey
  stripes), skin.detail 1.3. e16: open 7.48, cover 3.01, brow gap 11.6, canthal +1.1.
- SKIN TONE by skinm.py under the matched light (L/a/b, photo | ours): forehead 75/10/18 | 78/12/20, cheeks 62/13/22,
  54/11/20 | 78/12/20, 71/12/20, upper lip 54/8/15 | 74/11/20, chin 53/7/16 | 64/10/17. Ours is ~2 a and b warmer
  and, mostly, 15-20 L BRIGHTER from the cheeks down: his lower face is darkened by stubble / beard shadow. skin.tone
  (melanin 0.04 -> 0.06, blood 0.15 -> 0.10) and stubble 1.2 -> 1.5 / shadow 0.65 -> 0.85 moved none of these by
  more than 1: g4_garrett's own broad `_pre` tone layers set the colour, not skin.tone. Next: those layers.
- HAIR: a snapshot of h7_garrett's hair (likeloop/hair_snapshot.json) + hair7/base.json. main 0dc8f94's hair.py
  still rejects the per-lock key `swoop` (11 of 641 locks: "hair lock 'l211': unknown keys ['swoop']"): dropped from
  the snapshot. It renders blond-brown because base.json's own look says so: grey_amount 0.0, grey "#c6a684" (tan),
  lit "#664126": not a dropped key.
- CUPID'S BOW (likeloop; `likeness_lips.py`, REGION=lips eyes.py; sheets ll_lips_0/1.png). Like with like under the
  matched light (photo | e16 dressed | clay): bow width 16.6 | 17.9 | 17.1 mm, bow DEPTH (peaks 37/267 over the dip 0)
  1.97 | 1.88 | 1.72, bow angle 153 | 156 | 157 deg, tubercle (13 below the 82-312 line) 0.42 | 0.30 | 0.19, upper
  lip 6.8 | 6.5 | 5.9, lower 10.8 | 9.3 | 8.0 (stubble shadow under his lip: garrett3's caveat), width 58.6 | 60.6.
  The photo's mouth is ~45 px wide: depth and tubercle agree within 1 px. What reads as "no bow" on ours is CONTRAST:
  his upper vermilion is a dark red M (lip L60 a14 against the skin round the mouth L54 a8: +6 a), ours a pale band
  (L76 a12 against L74 a11: +1 a) with no stubble shadow round it. New general control headage `lip_bow` {depth,
  tubercle} (test_headage): l1 = depth 0.8 mm + tubercle 0.6 mm moved the detector's bow by < 0.1 mm (sub-pixel
  here) and skin.lips blood 0.9 -> 1.1 / melanin 2.6 -> 3.4 moved the lips' colour by < 1 L / a: the lips layers
  (T(blood = 6 x ...)) look saturated. Next: why skin.lips doesn't move the colour, then the stubble shadow round
  the mouth (his lower face is 15-20 L darker than ours).
- (likeloop e17-e18, "western fold"; ll_eyes_17/18.png, ll_eyes_18_zoom.jpg (each eye, 2 mm ticks up from the
  photo's lid margin), ll_eyes_18_threequarter.jpg) The hood's `crease` now follows the lid margin's arch corner to
  corner (a parabola through the corners and the mid margin) at crease_at x lid->brow above it, even across the lid
  (`crease_lateral` 0 default; the hood itself stays outer-third). crease 2.5 mm, crease_at 0.45, width 1.2 mm: a
  supratarsal crease on BOTH eyes with a lit platform under it; brows lifted (drop 2 mm, thickness 1.1) off the
  fold (at 3-5 mm drop the brow hair covered the fold: the "monolid" read). crease.py (luminance up the lid at three
  places): the photo's crease is at the edge of resolution (1.3 mm a pixel; a plateau 3.5-4.5 mm on his left eye);
  ours 4-6 mm, deeper than his. Inner corners: caruncle and medial canthus visible on ours, no epicanthal skin.
  e18 vs photo: open 7.56 / 7.39, cover 2.77 / 3.46, brow gap 13.3 / 12.1, canthal +1.5 / -0.45. The three-quarter
  render doesn't line up with the painting (its camera is the loose fit noted before): judged only that the
  crease shows turned.
- LIPS (l2; ll_lips_2.png, ll_lips_2_dressed_pair.jpg). New headage `lip_roll` {upper, lower} (volume: the vermilion
  rolled forward, peak high on the upper lip, mid on the lower, tucked corners; test). Kept: mouth_width macro -1
  held (1.1 -> 0.1 sigma), lip_roll upper 1.5 / lower 1.2 mm. Front, dressed (photo | e18 | l2): width 58.6 | 60.9 |
  59.0, lower lip 10.8 | 9.3 | 10.2, upper 6.8 | 7.0 | 7.0, bow depth 1.97 | 1.94 | 1.95, corner tilt -1.1 | -1.5 |
  -1.3 (level: the "downturned" read is the long seam into the cheeks, shorter now). Painting (E-line): his lips
  -2.1 mm, ours -0.8: ours do NOT project less there (loose fit, tol 3).
  LIP COLOUR IS STUCK: skin.lips blood 5 / melanin 8 (ll_lips_test_extreme_colour.jpg) leaves the upper vermilion
  as pale as blood 0.9 (lipprof.py: a 12-13 where his is 17-21) and the lower lip within 3 L. Not the stubble shadow
  (shadow 0: everything 3-5 L brighter, lips no redder), and the landmark ring of the lip_upper zone is valid (lipslm.py:
  inner 1 mm, peaks 7 mm above the corners). Next: why the lips_upper `_pre` layer doesn't show (its mask on this
  mesh, or a later layer: g4's over_lip_seam / lip_border).
