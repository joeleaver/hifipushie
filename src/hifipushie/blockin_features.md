# Block-in: the orbit, eyes, brows, lips and expression

Read guide(topic="block_in") first: the loop, the stage-0 description and the self-review.

   **3a. THE ORBIT, near the START (eye depth is a big mass: decide it before any lid work).** The same table opens
   with the ORBIT rows, as a side view shows them, model -> picture +- the reader's error: the corneal apex behind the
   nasion, the brow ridge ahead of the cornea, the cornea ahead of the orbit's side rim (what an exophthalmometer
   reads) and of the cheek under the eye, the brow's height over the pupil, the hollow under the brow. Their moves:
   `mm:eyes_forward` (the EYE UNIT: ball, lids, socket lining forward inside rims, bridge and muzzle that stay; |dc|
   1.65 per mm, ~0.75 mm on the shipped head per mm asked; the reference cameras follow the face, the step says so),
   `mm:brow_ridge_forward`, `mm:side_rim_forward`, `mm:under_eye_forward`, `mm:brow_hollow`, `mm:brows_over_eyes`.
   How they are read: the profile's outline (nasion, brow), the LIMBUS of the near eye in the 3/4 and the profile
   (edge read, 0.05-0.1 mm on renders), the front irises; each camera's YAW is a freedom of the solve (in a profile 1
   degree of yaw moves the eye 0.5 mm along the picture and leaves the profile line alone).
   BE HONEST ABOUT WHAT IT CAN SAY (8 known heads, dressed pictures): with the cameras KNOWN eye depth reads to 0.6-0.8
   mm from front + profile; from front + 3/4 alone it does NOT read (5.6 mm: a 3/4 does not show the nasion's depth);
   through FITTED cameras (a photo) 2.7-3.6 mm, because the outline pins a profile camera's yaw only to ~3 degrees.
   So on photos an orbit row usually says NOT READ unless the gap is over ~5 mm; the eye step then reports ORBIT:
   UNREAD. Do not move eye depth on a row inside its error; what makes it readable is a profile whose camera is
   known (a measured turntable angle, or a generated reference with a stated yaw), not more staring. From the FRONT
   alone depth has no proxy: the front-only read is the population's guess (+- 5.4 mm on a 4.0 mm sd).
7. **The EYE STEP: the lid as ONE structure, after the orbit**. ORDER: the ORBIT is
   set first (3a: eye depth and the brow over the eye are big masses; the lid is the sheet that hangs between the brow
   and the ball), then `lid_read(name, match=True)`. (The lid MARGINS and canthi are already inside `block_in_solve`
   (3b): after a settled solve the opening is right, and this step is for the FOLD's form; run with fold="none" it
   only repeats the solve's margin reads without the solve's other reads to hold them.) The step reads the orbit rows itself and says ORBIT: UNREAD / OFF
   / read at the top of its report; do not polish a lid on an orbit that is OFF. What the step does (blockin_eyes.py,
   blockin_lid.py), IDENTITY ONLY: in GNM the open-eye fold is an identity feature; its eye-region expression only
   shears the whole lid-to-brow sheet and never forms a fold (`expression=True` adds the expression pairs for a real
   POSE, a squint, nothing else):
   1. the OPENING: the identity for the picture's lid margins and corners in mm (the eye ruler's rows, 7a), with every
      millimetre measure (incl. the orbit's), the socket readings and the landmarks off the eyes held;
   2. the LID: margin, platform lying on the ball, ONE turn, the drape to the brow, solved on GNM's own lid rings,
      the turn put on the picture's fold line (per column), the margins of 1 held. Default `fold="crisp"` (RECIPE A, gnm_fold.fold): a DESIGNED lid (no donor head) fitted with the
      brows held 0.3 mm and the mm measures held (the hollow under the brow is left free: the fold IS that). On one
      head: turn 16 -> 44 deg on its line (the donor solve: 24), brow ring 0.7 mm down, measures within 0.35 mm,
      eye ruler and brow_read rows still pass; the price is |dc| ~15-17 and ~0.6 mm rms over the rest of the face
      (rows near their tolerance can go out: read the step's table). `fold="donor"` (or `donor=`): the older solve
      toward a donor head's lid (GNM sample #376): softer (24 deg), |dc| ~6. A picture with no fold line (hooded): no
      lid solve, the visible platform is the opening's target. A genuinely HOODED / deep-set eye is not a lid
      feature in GNM: it is the brow and drape coming down over a deeper eye: `block_in_step(name, {"hooding": x})`
      (per unit ~+0.6 mm of overhang, brow -2.4 mm, eyes 1.8 mm deeper; an ORBIT move: do it before the eye step
      and read the orbit rows / brow_read again). Wrong for an open lid with a platform;
   3. the EYEBALL GUARD: our ball is seated on six lid landmarks, not the lid's surface, so a lid lying on the ball can
      let it through (a patch of the ball's colour on the lid). The step measures the lid's stand-off from the ball on
      the shipped head and lifts the designed platform until it clears by 0.25 mm; the report gives the numbers.
   The report: the opening's rows (picture | model), the lid's structure before / after / donor (platform's stand-off
   from the ball, the turn in degrees and its height, the wall, the drape), |dc|, the guard. One head (the lid
   solve): platform 1.6 -> 1.4 mm off the ball, turn 17 -> 25 deg at her 4.7 mm line, wall 29 -> 40 deg, |dc| 4.4, the
   platform lifted 0.4 mm for the ball, margins within 0.05 mm. Honest limits: GNM's largest
   turn on a platform as tall as hers is ~25 deg and NO GNM head has skin over skin (an overhang), so her thin dark
   fold line is not reached by geometry, and by decision it is LEFT ALONE: no painted fold line, no
   crease make-up, no liner, no extra layer. Judge the lid's FORM under a raking light (focus=eyes) and dressed; do
   not judge it by the line's darkness.
   `match="pose"` is the older lid_upper / lid_lower offsets. Eye size and "almond" shape are mostly lids and seating:
   an identity step for eye height made eyes read NARROWER.
7a. **Measure the eye with the RULER, never by eye**. `eye_ruler(name)` reads the front picture by its EDGES (the iris as a circle through the limbus;
   the lid margins at 7 columns; the canthi; the fold line; the brow's edge) and the model's mesh through the same
   camera, in mm from each eye's iris centre, with a tolerance per row (the reader's measured error) and the move that
   closes each starred row. Why not the detector: MediaPipe's iris centre sits ~1 mm LOW (it follows the visible part
   of the iris), its iris is 9-22 % small, its lid points are 1-1.5 mm out, and GNM's lm68 eye corners are not the
   visible opening's ends (the inner one is the canthal pocket's tip, 1.9 mm past where the eyeball shows). The eye
   step (`lid_read(match=True)`) now solves for the ruler's margins and corners in mm when the picture's iris is at
   least 30 px across. Three things the ruler found that are NOT the solve's to fix:
   - the EYEBALL: GNM's lids are shaped on its own ball (14.6 mm on a full-size head), and that ball is the default:
     leave `eye_radius` unset. A ball shrunk to make the drawn iris right (e.g. 0.0101) leaves the corners empty
     (1.2-1.4 mm of socket lining at the outer end) and the eye reads short. The iris has its own size: GNM's limbus
     (`block_in_step {"iris_mm": mm}`; `skin.eyes.iris_size` overrides the drawn iris only).
   - the CARUNCLE: `skin.eyes.caruncle: 1` paints the inner corner's pocket wet dark red from GNM's inner-corner
     landmark to the eyeball. Unpainted, the pocket is skin-coloured and the eye ends ~2 mm early at the nose side.
   - the LASH LINE: a photographed lash line is a thin dark line; lashes 9 mm long and 0.15 mm thick (the defaults)
     read as a fringe. `base.lashes.upper` length / thickness / count.
7b2. **Brows and iris before a dressed eye is judged**: `brow_read(name)` gives the brow hair's miss against the picture and the iris line
   (picture limbus vs drawn iris, mm at the model). If the iris is off by more than 5 %, step `iris_mm` to the
   picture's (GNM's limbus component; do not shrink the ball: 7a); then `brow_read(name, match=True)` places the hair
   from the picture. Compare dressed renders with the
   picture ONLY through the picture's fitted camera and the same pixel crop (never an "11.7 mm iris" scale: the
   detector's iris points under-read our renders by 19 % and a photo by 6 %).
7c. **The LIPS STEP: the lip line the way GNM is built**. A block-in's rest mouth
   is closed by GNM's OWN lower-face expression (`head.lip_close`, set by block_in_start: the least change that puts
   the contact ring's halves together corner to corner, re-solved on every head), never the seal: `lip_seal`'s
   membrane dragged the whole vermilion and halved the border's turn (24 -> 11 deg on one head), the lips read as a flat
   painted pad. A closed mouth's field leaves GNM's crossed inner rolls out (the seam is one line, no pale band or
   dark corner holes). `lip_read(name)` reads the picture (the vermilion borders traced on the a* edge, the seam, the
   Cupid's bow) beside the model through the front camera. The vermilion BORDERS are already inside `block_in_solve`
   (3b; 0.2-0.5 mm after a settled solve): read `lip_read(name)` first and run the step only for what the solve does
   not do (the seam, the bow, the closing expression). `lip_read(name, match=True)` is the step: identity + GNM
   lower-face expression for the borders (0.35 mm), the seam (0.4), the bow (0.1 mm) and the neutral closed, the 68
   landmarks off the mouth held; it ships head.expression, lip_close / lip_seal / mouth_gap cleared. Judge with
   focus=mouth AND dressed (the lips' paint follows GNM's own vermilion edges). One head: borders 1.96 / 3.80 ->
   0.20 / 0.22 mm, bow 0.51 -> ~1.2 mm (her 1.44), |dc| ~2.8, |e| ~3.3. It may push philtrum / chin_height in the table
   (the step fits the traced a* border, the table the detector's points): judge both.
7b. **The picture's own expression** (`block_in_expression(name)`): GNM's identity is the RELAXED neutral; a picture
   that smiles (fuller lips, lifted corners, a cheek apple) or squints is compared against that neutral, and the smile
   leaks into mouth / cheek identity steps. The tool fits each detector picture's expression on the current head
   (identity and camera held; GNM lower-face expression comps, small prior; eyes=True adds eye-region comps, which can fight the lid pose) and stores it per view in the
   references; every later look / focus / table / lid read / camera refit draws the clay WITH that picture's
   (lower-face) expression on top of the head's own (the eye step's eye-region expression); the model itself stays neutral. Fit it once the big forms are in (on the class mean it would soak up
   identity: block_in_start(expression=True) only for pictures you know are neutral-ish), and refit after big
   identity moves (the reply's chi2 says how much the expression explains). clear=True drops them.
8. **Judge in whole-face hair-cap clay under both lights** (the photo's light in the sheet; `look` / `look_skin` for
   the clay key and the dressed head) **before any fine detail.** A block-in is done when the outline sits on the
   pictures in every view, the table passes (or every miss is explained: a painted view, a detector guess), and the
   squinted clay reads as the same person: age, sex, mass. Then likeness / fit_likeness for features, then skin.
