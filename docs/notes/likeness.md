# hifipushie notes: likeness

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

## Likeness checklist (2026-10-08, "likeness" agent, branch worktree-agent-a2afc4d19c40fa784; needs onemesh2's branch on main first: it is merged in here)

The user: "a checklist of facial features to specifically look for and match from references ... it works better if
it knows where to focus"; then (via the coordinator) the same list must drive the FIRST fit, in stages. Guide
`guide(topic="likeness")` = `likeness_guide.md` (FISWG / ASTM E3149 component list, likeness artists' big-to-small
order, Farkas' anthropometry, sources). Renders `workspace/human_renders/lk_*`; scratch DURABLE in
/mnt/data/hifipushie/likeness/ (run.sh <script> = this worktree's code on the main workspace, t2.py <model> (sheet +
report), stages.py <model> [stage..] (sheet, plan, before, stages saved, after), cmpsheet.py out.png label=model[@v]
... (photo | models through each camera + an item table), mk_fresh.py (model `lk_garrett`: om_garrett v8's body,
seed head)).
- `likeness.json` = the checklist as data: 49 items in 8 stages (proportions, widths, eyes, brows, nose, mouth,
  chin_jaw, ears), each with `look` (a sentence to act on), views, a measure (kinds dist / width / ratio / tilt / level
  / arch / angle / bow / judge on MediaPipe's 478 indices), unit, tol, control, optional `solve` (the humanfit
  measure a stage asks), reliability notes. Keep items in stage order (a test checks it). Don't json.dump it (format).
- `likeness.py`: every measure is a 2D quantity in the reference picture, mm at the face's depth through the
  picture's FITTED camera (human_refs.json), on the face's own axes (nasion 168 -> menton 152). Both sides use the
  SAME reader: MediaPipe Face Landmarker (venv $HIFIPUSHIE_MEDIAPIPE, default /mnt/data/hifipushie/facerefs_venv;
  subprocess, results cached by image bytes in <HOME>/_cache/likeness) on the photo's face crop and on a numba
  clay render of the model through that camera (`render`: eyeballs with iris discs, brows as strokes through the
  model's brow landmarks: paint isn't in clay). Without the detector, points of the 68 fall back to the stored /
  projected landmarks (`Side.pt`); the rest say "needs the detector". `compare` also reads every measure on the
  landmarks alone (photo's stored 68, model's GNM 68): the table's "lm miss", '!' where the readings differ by more
  than the tolerance = the miss depends on the definition. `focus_sheet` / `panel`: photo | model at the same crop and
  camera, red photo points, blue model points (width items draw the level line on both).
- `measure_reference(name)` -> <model>/likeness_targets.json (value, view, tol, confidence high / medium / low (tol
  under ~1.2 px) / judge / unmeasurable + why). `stage_plan`, `fit_stage(name, stage)` (one stage: fit_outline for
  widths; humanfit.solve on the stage's front-view misses mapped by `solve`, earlier stages' solve measures pinned
  "+0"; fit_hood in eyes; ears none), `fit_likeness` (stages in order, each saved). MCP tools `likeness(name,
  targets=)`, `fit_likeness(name, stage)`. Tests `tests/test_likeness.py` (synthetic face with known values).
- Gotchas found: a UV sphere wound inward rendered the eyeball's inside (white eyes, no iris: the detector read the
  eyes 3 mm too narrow); stored reference points leave the jaw contour out (lm0-16), so the landmark frame falls back
  to nasion -> mouth; "eye line from nasion" is meaningless (nasion IS at eye level): replaced by the mouth line.
- Fresh Garrett staged fit (lk_garrett v1 seed head -> v6; 7 stages ~2 min, all INTEGRITY ok, nose / chin_jaw /
  ears had nothing wired to move): beyond tolerance 39 (seed) -> 25 (staged), om_garrett's hand passes 28
  (`lk_02_staged_vs_hand.png` + table in the log). Read: the numbers beat the hand passes, the face does NOT: the
  staged head is soft and generic beside om_garrett's planes and hollows, because the checklist measures distances,
  not shape (cheek planes, hollows, folds are judge items). Pins hold solver measures, not checklist items: the brows
  stage moved the middle third (reported as "EARLIER STAGES MADE WORSE").
- Gaps (no control): canthal tilt, eye shape, brow arch / slant, nose length to tip / projection / nasolabial angle /
  bridge, mouth-corner tilt, lip ratio, lower third / mouth line (ratios), jaw angle height, chin shape, ears.

- Rounds 2-3 (same day; guide rewritten; scratch adds r2.sh / r3.sh (fresh `lk_garrett2` staged + comparison),
  t4.py (shape rows + light-fit debug strips), t5.py (shape rows per model), t6.py <model> <stage> (a stage's rows +
  panels, no fit), t7.py (jaw pair), t8.py (brief + check), grid.py (a gridded crop to place points by eye),
  trace_desk.py (MY by-eye trace of the desk painting's near jaw: a stand-in for onemesh2's), cmpsheet.py with
  POINTS=<model whose likeness_points to use>, final2.py (om_garrett's report without writing in its folder)).
  - `likeness_shape.py`. Shape items (kind "shape", stage "structure" after widths): `measures3d(st)` = the model's own
    mm (cheek_hollow / nasolabial_fold / under_eye = hull deficits of sections, corner_temple / _cheekbone / _jaw =
    base.plane_measures' corner radius, brow_ridge ahead of the cornea); against the photo by SHADING: `fit_light`
    (luminance = c0 + w . n on the face's skin over the MODEL's normals, robust) -> `residual` ((photo - predicted) /
    median: a ratio blew up where the prediction neared 0) -> a region disk minus a reference disk (regions in the
    json from detector points + mm offsets on the face's axes, mirrored). Tol 8%, FRONT views only scored. It ranks
    the heads the right way on the planes: cheekbone corner om -8% (3D 15.6 mm) / seed +17.5% (37.3) / and the lever
    lands shape.planes at 2.85 from the photo alone (om_garrett was hand-set to 2.6). Hollow, under-eye and brow ridge
    are confounded (stubble, brows, lids): don't trust their percent. Panels of shape / jaw / judge rows show the model
    lit by the fitted light (`render(light=)`).
  - The jaw's L (kind "jaw": jaw_ramus, jaw_gonial, jaw_border, jaw_gonion_lobe, jaw_gonion_mouth, jaw_neck_step) from
    a trace: `likeness_points.json` ({format, views: [{image, points, lines, by}]}; `likeness_shape.set_points /
    load_points`, MCP `likeness_points`; format sent to onemesh2). `jaw_measures` splits the polyline at its corner
    (two line fits); the model's side = `model_jaw`: across each traced point the render's depth edge, else the
    fastest turn of its normals, a running median along the trace. On Garrett's desk painting (my trace: ramus 25 deg,
    gonial 136): om_garrett after onemesh2's jaw work 27 / 134, the seed 17 / 125, the staged fit 60 / 141 with the
    angle 62 mm under the mouth line (one diagonal). The model contour is NOISY (a neck step read 7-27 mm on the same
    head between runs): fine to rank heads, not to pin.
  - Inferred: `_allowed` lets a profile item be read from a three-quarter view when no profile exists (tol x
    `INFER_TOL` 1.5, '~'); new profile items chin_projection, lip_projection (E-line), forehead_slope (judge).
  - Turned cameras refitted per model (`_refit`, `likeness_shape.refit_camera`: the detector's 468 non-oval points on
    the photo vs the model's surface under the same points of its render, unprojected by the depth pass); `cam` column
    = the residual at the item's points, half of it added to the tolerance.
  - Coverage (`coverage_text`, leads the table; `picture_notes`: view + the detector's head yaw, lens from the fitted
    focal, expression from blendshapes, light hardness and how badly one light fits, ears / forehead skin-coloured or
    not). Garrett's refs: front has a squint 0.70 and a frown 0.55-0.66 (a generated face: the "hooded eyes" are
    partly an expression), the desk painting's fitted lens is 12-18 mm (a loose fit, not a wide lens).
  - Staged fit: `LEVERS` (item -> 1-D secant on shape.hollow / planes / jaw_angle / under_eye, features.brow_ridge,
    pose.smile, nudges eye_outer z, nose_tip z / y), `_undone` pins = EARLIER STAGES' CHECKLIST ITEMS re-measured, but
    only steady ones (detector items in front views): pinning shading / jaw / turned-view rows vetoed every later
    stage in the first run. A solve that undoes a pin is retried at half, else not taken; a vetoed lever try still
    feeds the secant. Canthal tilt +5.1 -> +0.5 deg by a -2.3 mm nudge of the outer corners.
  - Fresh Garrett again (`lk_garrett2`, sheet lk_05_staged2_vs_hand.png, table /mnt/data/hifipushie/likeness/
    cmp_r2.log; ~6 min): beyond tolerance seed 38 -> staged 21; om_garrett (latest, mid-edit by onemesh2) 29, its
    misses now mostly proportions the hand passes chose (lower / middle third 1.71 vs 1.44, temples -12 mm, mouth -6).
    READ: the staged head is still the softer one: planes are in, but no hollow (the shading said none was needed:
    stubble hides it), no jaw L (no control draws one), no brow ridge. The list now SEES the jaw and the planes; the
    controls to draw a ramus / lower border / fold don't exist.
  - `likeness_brief.py`: `reference_brief(kind, subject)` (clothlist's format: cloth_reference.reference_brief) and
    `check_references(views, name)`; MCP `reference_brief`, `check_references`. Not tested on generated sets.
  - Round 4 (2026-10-08; Joe on lk_05: the nose soft, the chin weak "even though the profile could have been traced in
    that 3/4 view"; sheet human_renders/lk_06_profile_contour_fit.png; scratch p1.py (contours + key points overlay),
    p2.py (yaw cross-check), p3.py (contour rows + panels), pf.py src dst out (the fit on a copy + the desk row),
    trace_profile.py (my trace), refs_check.py, mem.sh):
    - `likeness_profile.py`: a turned view's far-side contour (`likeness_points` line "profile", `snap_edge` onto the
      background edge) and the nose's own edge (line "nose", by hand) against the model's (`model_outline` from the
      render's depth pass; `vertex_envelope` of `nose_ids`), one frame (inner eye corners -> mouth corners: nasion ->
      chin moved with the fit), `keypoints` (brow peak, orbit, mouth-height point, chin corner = furthest out of the
      chord mouth -> under-jaw, lips only where a notch exists), `measures`, `shift` (camera offset over the bony
      upper face), `targets` (fit_region targets at the vertices that make the contour). 12 checklist items of kind
      "contour" (`replaces` = the inferred item they supersede on that picture).
    - `likeness.fit_profile` (MCP fit_likeness stage "profile"; inside stages nose / chin_jaw): fit_region on
      nose_region / chin_region + lower_lip_region, `_front_holds` (the part's landmarks held in the FRONT picture's
      plane: free, the subnasale went 3 mm down), ONE camera through the rounds (compare refits turned cameras per
      model: the camera followed the nose), judged on the contour's rms (judged on the items' score it stopped after
      one round with a scooped bridge). lk_garrett2 -> lk_garrett3: nose contour rms 7.1 -> 1.8 mm (2.1 sigma), chin
      9.9 -> 1.2 mm; nose gap to the cheek line 15.7 -> 7.6 (photo 5.8), chin -43.8 -> -35.0 (photo -39.1: 4 mm past).
      Side effects on the front view: philtrum 0.2 -> 2.4 tolerances, lower third 1.4 -> 2.3.
    - The painting is not one projection: detector head yaw 31, fitted camera 45, the nose drawn as if turned more
      (tip - columella base 16 mm in the picture). The model's far cheek at the mouth's height stands 9 mm outside the
      painting's (prof_cheek_line): the soft lower face, no control wired to the contour but shape.hollow.
    - Expression rule (`EXPR_BIAS`, `EXPR_LEVERS`, `expression_bias`): an expression read on a reference (squint 0.70,
      frown 0.64 on Garrett's front) marks its items in the table and sends them to pose levers in the staged fit.
      Jaw: `shape.jawline.*` levers (nested lever paths), the model's jaw line from its own landmarks 2..8.
    - Nose base (Joe: the painting's base line, wing base -> under the tip, rises; ours hangs like a beak): hand point
      `alar_base.R` / `.L`; nose key point "under" (the contour 3 mm back from the tip going down: the tip's most
      forward point hid a hanging underside); items prof_nose_base (deg, + rising), prof_tip_height, prof_tip_radius,
      prof_columella, `rank` 2 (sorted above their bare miss / tol), levers on `shape.nose_tip`. Garrett staged: -1.9
      deg vs the painting's +3.1 (hand points +-1.5 px = +-2.4 mm: the miss is the size of the reading's error);
      shape.nose_tip moves it 0.1 deg per degree and breaks integrity at 16: NOT a sufficient lever (scratch nt.py).
    - NOT validated: the jawline levers (structure stage on lk_garrett3: misses got worse or unmeasured, nothing
      taken) and the landmark jaw line itself: on a head without `shape.jawline`, lm 2..8 are GNM's diagonal, not the
      visible border (ramus 41 deg where the render search read 17.5).
    - Round 5 (same day, onemesh2's ddf1a63 merged: nose_tip pivots on the alar bases): shape.nose_tip now moves the
      base line ~0.5 deg per degree (lk_garrett5: -5.1 -> +1.3 at 14 deg, painting +2.4). Profile fit: holds =
      60 region vertices x3 in the front picture's plane (`_front_holds`), pins = every front-view item when run
      alone (`_undone(first, c, 99)`), gain 0.7, components capped at 1.6 sigma, part "cheek" (cheek regions, far
      cheek contour sn..sto: rms 4.2 -> 1.2 mm in 3 rounds; structure stage). `yaw_doubt` (detector head yaw vs the
      fitted camera > 6 deg): "NOT ONE PROJECTION" in the coverage line, depth items' tolerance + 0.5 mm / deg
      (Garrett's painting: +7 mm, so those rows pass trivially: the shape rows, bridge / tip / fold / base, don't).
      Sheet lk_07_profile_fit_round2.png (lk_garrett2 -> lk_garrett5): tamer than lk_06; the chin took one round
      (-44 -> -41, painting -36), the second was refused by a front pin (lower lip). Jawline lever NOT re-run.
    - Stage 0, the CHARACTER READ (`likeness_read.py`, likeness.json `descriptors`: 32 gestalt words, each with
      bands on checklist items (FIRST VALUES, uncalibrated), `opposite`s and its control or GAP; MCP `character_read`):
      `form()`, `set_read(name, tag, read, view)` (<model>/likeness_read.json), `bands`, `apply_prior(cmp, read)`
      (unmeasured rows take the band; measured photo / model values outside it flagged), `render_views` (reference
      cameras + both profiles, the other three-quarter, low angle), `diff(name, tag)`; `likeness.report` leads with
      it. Reads are made by FRESH agents (Agent tool: form + pictures only; blind ones get only the render sheet).
      Garrett (stored on lk_garrett5; sheets + diff in /mnt/data/hifipushie/likeness/read/): reference read = lean,
      long face, square jaw, strong broad chin, straight nose, heavy brow, deep-set hooded eyes, rugged (the reader
      said LEAN where Joe said chunky). om_garrett current (v21): kept 33 of 72 descriptor-views; "chunky" in all six
      views, soft jaw in five, weak chin + flat brow in both profiles. Pass 6 (v16): 46 of 72; lean kept, soft jaw +
      weak chin in both profiles and the three-quarter.
      Round 6: reads carry an author (`set_read(author="user" | "llm")`, `reference_by`); `effective` = the user's
      win, the reader's stay unless an `opposite` of the user's; `questions(name)` lists the disagreements for the
      user (Joe: chunky / square jaw / cleft chin / cute nose vs the reader's lean / straight nose / no cleft seen).
      `NOT_JUDGEABLE` (face shape in a profile, chin projection from the front...) leaves those out of a view's
      count. `agreement(name, tags)`: three blind readers of pass 6 agreed on gaunt, heavy brow, deep-set, hooded,
      straight nose, lean (5/6), square jaw (3/4); UNRELIABLE on that head: strong chin (0/2), narrow jaw (0/3),
      broad nose (1/3). `likeness.report` renders the six-view sheet by default (`<focus>_views.png`). onemesh2's
      581dc3e wired: levers shape.chin.project (prof_chin), shape.chin.width, shape.nose_tip.round (tip radius),
      nose_tip as {"up", "round"} (`BARE`); cleft = shape.chin.cleft by hand (no item measures a groove).
      lk_garrett5 after them (lk_08 six views) is a LEVER TEST BED, not a likeness: crumpled cheeks from the cheek
      region fit, a blob nose, no visible cleft at 2 mm. NOT done: stubble / hair stand-ins on the read renders.
      Known: a view that can't show a descriptor (face shape in a
      profile) counts as "missing"; not blind-tested for repeatability; no stubble stand-in; bands uncalibrated.
    - Memory (capped, /usr/bin/time): staged fit 1.85 GB peak / 15:50, three-model comparison 1.2 GB, report 1.07 GB.
  - Open: a jaw control (ramus / border / neck step), a fold control; shading with albedo handled (a stubble mask, or
    the side-light shot from the brief); ears; the jaw contour finder's noise; `human(..., refs=)`; photo scale uses
    the first model's mm/px in cmpsheet (photo column shifts 1-2% between runs with different models).

