# The artist block-in: a person's head from pictures (THE DEFAULT for modelling humans)

A portrait sculptor doesn't fit numbers to a photo. They start from a head of the right kind, put it beside the
pictures, squint, name the single biggest difference in masses and planes, change ONE thing a little, and keep the
change only if the whole head now reads closer. The block-in tools give you exactly that loop on a one-mesh human
(`human(..., source="human")`): you are the artist, the tools are the turntable, the light, the calipers and the
log. It is the first stage for every person modelled from references; likeness / fit_likeness detail, skin, hair
and clothes come after it.

Why not a solver: a fit to landmarks and outlines got the outline right and the person wrong (older, more male, the
wrong mass inside the outline) because outlines and points don't see the front planes of the face, and a local
slider tweak at a time made faces uglier. Whole-face directions learnt from the population keep the face a face; your
eye catches what the points miss; the target table catches what your eye misses.

## The loop

1. **Start from a base of the right kind**: `block_in_start(name, refs, sex=...)`. The person's body (MakeHuman's
   age / weight / height from `refs`, a one-mesh human whose pictures are fitted by `human_reference`), the head's
   local layers OFF (sliders, warp, folds, pose, shape), the identity = GNM's sampler CLASS MEAN for the sex (and an
   ethnicity class only if you know it), `gnm_base` by age (0.5 young: a soft adult face; 0 from 50: MakeHuman's own
   aged head reads older and leaner, which an older person needs). Never start from a previous fit: it carries that
   fit's mistakes. The reply is the first sheet and table.
2. **Look** (`block_in_look`, also returned by every step): per picture photo | clay under THE PHOTO'S OWN fitted light
   (hair cap: bald clay reads male; the person's own brows, SEATED on the surface: the front picture's detector brow
   band painted where it lands on the skin, so in 3/4 and profile they foreshorten and the far brow hides behind the
   bridge (2D-pasted brows stuck out past the silhouette and hooked over the nose); a presentable light iris: dark
   iris caps dominate a clay read; the shadow side lifted to a display fill: a painted light left half a 3/4 black)
   | 50 % overlay | outline difference (photo red, clay green) | squinted photo |
   squinted clay. Registered at the eyes and nasion only (a 2D shift): like a tracing over a photo, never registered
   on the outline it is meant to judge.
3. **Squint and name the single BIGGEST difference** in sculptor's terms: masses and planes, not features. Profile
   convexity, the muzzle (how far mouth and teeth stand forward), the jaw line and its angle, chin mass, nose mass and
   angle, face length vs width, the cheek planes (front vs side, where they turn), the bridge, how deep the eyes sit.
   Check the sex and age read (bald clay is a weak sex judge; the hair cap helps).
   **Then look the phrase up in the DRIVING MANUAL** (guide topic `gnm_driving`, or `gnm_controls(phrase="...")`):
   what you see -> the GNM control, its sign, mm per unit, what to hold and what it drags (tested: drivers passed
   8 / 42 synthetic pairs without it, 19 / 42 with it). E.g. the muzzle forward in profile = `pc:upper_lip_region0`,
   not lip_projection; pupils further apart = `mm:pupils_apart`, not eye_spacing; the whole nose further out =
   `pc:nose_region0`; a halo all round = `head_size` at 1-1.5 sd.
   **MEASURE FIRST: `face_ruler(name)`** reads the 23 millimetre measures off the pictures themselves (skin outlines
   and iris centres through the fitted cameras) against the model: picture - model per measure, largest first, the
   reader's error, and the `mm:` move that closes each. Start every block-in from that table and run it again after
   each step (it re-reads the pictures against the moved model). Tested on 14 fresh synthetic pairs: Claude drivers
   with this ruler passed 11 (by eye 3, with a ruler that needed the target's mesh 7); its 8 largest gaps applied
   without looking passed 11, with the camera fitted from the model's landmarks as on a photo 11 of 13. Where a driver
   disagreed with a row, the row was right every time it was checked (under_chin, nose_length, the vault, a brow move
   rejected for a frown the target had). Your eye judges whether the face reads closer; the ruler says how much.
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
   **If the difference is something you can MEASURE** (a width, a height, how far a point stands forward in profile:
   the 23 measures of `gnm_controls(query="mm")`), measure it in mm on the sheet and use the `mm:` move: closing the
   8 largest of those gaps (in population sd) passed 30 / 42 pairs, more than the best 10 phrase moves (27 / 42).
   **3b. THE JOINT STEP FIRST: `block_in_solve(name, cameras="free" | "trust" | "refit")`** (2026-10-11). ONE solve
   over every reference view at once, under GNM's prior on the WHOLE identity (centred on the block-in's start head, so
   repeated calls settle), with each camera partly free. It applies the solved change as a step and keeps the cameras
   it ended on. Run it from block_in_start's head BEFORE any hand move, 3-4 calls until its |dc| falls under ~2-3.
   The lids and the lips are INSIDE this solve: there is no separate eye-opening or lip-border step to run after it
   (the old separate steps were undone by later moves: lips 0.2 -> 1.8 mm).
   - WHAT IT READS, per view (the reply lists the counts):
     OUTLINES: the head's bare-skin silhouette (profile line, far cheek / brow / jaw in a 3/4, jaw and ears from the
     front). In front of a plain backdrop from the picture's own pixels; on a painting, a dark or busy backdrop or
     where that finds under 40 samples, from a FACE PARSER (`parse="auto"`, the default; "on" / "off" force it):
     skin / hair / clothes per pixel, so hair, collars and backgrounds are not the head (0.2-0.5 mm on dressed
     renders over a painted backdrop; the plain reader got 2-27 samples there, the parser ~100 a view).
     ANCHORS: the detector's landmarks as weak anchors, DIFFERENTIAL (`anchors="differential"`, the default): the
     detector on the picture minus the same detector on our own render through that camera, as the table compares
     them, so the detector's definition bias does not go into the face ("absolute" = the old comparison with the
     mesh's true landmarks: on two paintings it forced components to 3.9 sd). BOTH iris centres of a 3/4 are in
     (they pin its yaw). The detector's CHIN points (`chin_points="auto"`): in when the set has NO side view (nothing
     else reads the chin from the front), LEFT OUT when it has one (a camera turned 60 deg or more: its outline
     reads the chin's height and projection to 0.3 mm). The detector's chin on a picture is not its chin on our clay
     render of the same head (2.6 +-1.1 mm higher, 2.4 mm aside on dressed renders of 8 known heads; the eyes agree
     to 0.1), and against a side view's outline it left the chins of known heads 3.9 mm short on average and their
     lower faces WORSE than the class mean they started from (3.4 mm rms against 3.0; without the points 2.15). The
     table's chin_height / lower_third rows are those detector points: with a side view expect them 2-4 mm out
     and do not chase them.
     EYES: iris centres (front), the limbus in the turned views (eye depth), the LID MARGINS at seven columns and
     both canthi in the eye's own frame (needs a 30 px iris: a small or painted face gives none, and says so).
     LIPS: the front picture's traced vermilion borders.
   - CAMERAS. The freedom (shift, scale, roll, yaw, pitch) is on each camera's WHOLE move since the block-in
     started, whatever the number of calls (it used to be per call: four trusted calls walked as far as one free
     one and over-rotated Tess's 3/4 and profile 3.5-4 deg). So use ONE setting on every call: `"trust"` when the
     references' cameras are good (measured, or fitted on an earlier accepted head of the same person and the start
     head is close to it), `"free"` for cameras fitted on the class mean. `"refit"`, first call only: the cameras
     were fitted on ANOTHER head (block_in_start(cameras="keep") from an old model onto a class mean: Garrett's 3/4
     outline was 9 mm off): they are laid on this head first (head held), and that is the new start. That is the
     usual case right after block_in_start, so START WITH "refit", then "free": Tess from her class mean, four calls:
     refit + free = table 25 / 26, nothing down-weighted; all "trust" = 16 / 26 with the 3/4 and profile cameras
     stuck at their limits, the face 5 % long and the reads down-weighted x1.7-2.2; all "free" = 17 / 26. Check a solved
     head: iris span and face length, model / picture, ~1.00 in the front and the 3/4 (spikes/reruns/eyespan.py).
   - NOTHING IS FORCED, by construction: if the most likely head has a component past 3 sd, every read is
     down-weighted until none has, and the reply says INCONSISTENT PICTURES x<factor>; a group of reads the best head
     leaves scattered (a 20 px mouth's lip borders) gets its own scatter as its sigma and is named. Two paintings of
     one person are two drawings: expect a factor of 1.5-2.5 there and a compromise head; photos of one sitting
     give 1.0. A weak solve (under ~120 outline reads) is carried by the anchors and the prior: where nothing was
     read you get the class mean's face.
   - Tess from the class mean (three studio photos): |c| 5.4 -> ~11, largest component under 2.7 sd, eyes 3/3, lip
     borders ~0.3 mm with no separate eye or lips step: about ten hand rounds' worth in minutes.
   - It does NOT see the surface inside the silhouette (cheek volume), the lid's fold, the nose's planes: hand steps
     for what you (or the user) see, after the solve. Two interior reads were built and FAILED validation on renders
     of known heads, so they are off: lambertian shading, and a learned normal estimator (docs/notes/gnm_atlas.md
     "## refread"). Do not force a fold from a class-mean head (lid_read fold="crisp" cost |dc| 20 there;
     fold="none" = the opening only).
   - WHAT WAS READ, AND WHAT MOVED WITHOUT A READ (2026-10-12, `solve_report`; in every reply). The solve's own
     posterior calls everything "read": ~600 reads pin GNM's 170 global components, and every measure is a function
     of those, so a cheek 30 mm inside every silhouette comes back with a tight error bar. That is the prior's
     correlations, not a measurement. The reply therefore uses a DIRECT read per measure (gnm_mm's 27, the chin set,
     the shape words): does any read LOOK at the measure's own points along the measure's own direction, if the
     surface were free to move locally (0 = nothing looks, 1 = pinned)? Three lists:
     `MOVED WITH NO READ` (left the start head by > 0.7 sd or 2 mm on a read under 0.25: an invention; check it by
     eye, or put it back with a `mm:` / macro step), `MOVED FAR ON A WEAK READ` (over 1.2 sd on a read under 0.6: a
     3/4's foreshortened depth through detector points; Garrett's eye depth from two paintings: read 0.52, moved 7.3
     mm, 4-5 mm of it wrong), `unread` (left near the start head's). Treat the first two as INFERRED when you
     report a head. The direct read is a heuristic about geometry: it does not know a read is biased.
   - THE CHIN AND JAW (the audit behind it; Joe: "makes me wonder if we're measuring enough things there"): a side
     view reads the chin's projection, height and the chin-lip groove (direct read 0.8-0.95). NOTHING reads the
     chin's own WIDTH or the jaw's lower edge between its angle and the chin from a front, a 23 deg and a 72 deg
     view: they end on the neck's skin, no silhouette (the jaw's width AT ITS ANGLES is read: the front outline runs
     down to them). Judge heads by SHAPE: every camera's scale is free, so a solved head's absolute
     size is not read (known heads come back 1-8 % large; compare after a similarity fit: spikes/chinread/bt.py).
     What the "chinread" audit found on 8 known heads (dressed renders through the good Garrett set's cameras):
     (1) the old solve made the lower face WORSE than the class mean it started from (3.4 mm rms against 3.0; chin
     3.9 mm short, chin / jaw / gonial width +3.7 / +3.4 / +3.7 mm) and the cause was the detector's chin points
     (above): without them 2.15 mm, the chin's length within 1.5, the widths' bias gone (+1.1 / +0.1 / +0.3).
     (2) What remains is unread, not biased: a chin 5 mm wider or narrower with the jaw held comes back 10-20 %
     of the way; chin and jaw together 45-90 % (the jaw's angles are on the front outline). (3) FOUR reads were
     built for the rest and did NOT validate, so they are off: solvereads' luminance step and detector jaw line;
     the jaw's shading RAMP against our own render under the fitted light (null 2.4-3.1 mm rms; a width moves it
     0.4-0.9 mm); the jaw in front of CLOTH from the parser's skin / cloth maps (3/4: median 0.2-0.4 mm but outliers
     to rms 1.7, front fails; and real sets rarely have a collar behind the jaw). A TIE of the unread widths to
     their expectation given the read measures (options `chin={"tie": ..}` of blockin.solve_step) did not beat
     leaving them free either. (4) On the good Garrett set the solve's broad, square lower face is what outlines
     + GNM's population give (his jaw IS wide at its angles: a narrower one leaves the front outline 2-6 mm inside
     the picture's); the rounded chin ball between his marionette grooves is RELIEF inside the silhouette, which
     no read sees. So: after the solve compare the front and 3/4 BLENDS and the lit clay at the chin, set
     chin_width / jaw_square by eye with `mm:` / macro steps if the blend supports it, and leave grooves and
     jowls to the skin's folds. Do not ask for tilted views to fix it: a view from 15 deg above or below made the
     known head worse (lower face 1.4 -> 2.8 / 2.0 mm); a true 45 deg 3/4 and a true 90 deg side are what to ask for.
   - STEADIER REPEATS: the down-weighting factor is the smallest that fits (it moved in x1.3 steps), is carried
     across calls and comes down at most 15 % a call; each view keeps ONE outline reader for the whole block-in; a
     step that turns back on the last call's step (cosine under -0.2: the see-saw at |dc| ~2-2.6) is halved and
     marked DAMPED. Stop when |dc| is under ~2, or at the first DAMPED step.
   - VIEW SANITY: the reply warns when a view's stated kind disagrees with its fitted camera by over 15 deg ("given
     as a profile (yaw 90) but its fitted camera is turned 72 deg: NO TRUE SIDE VIEW"): depth measures then ride on
     that one camera's angle and are INFERRED. The readers still go by the STATED kind (tried by camera: Tess's
     "profile" stands at 67 deg, became a second 3/4 and the solve fell apart).
   - Options, both OFF by default because their validation did not support them (docs/notes/gnm_atlas.md
     "## solvereads"): `hold="auto"` holds every measure no read looks at at the start head's value (better on one
     known head, worse on the other); `expression="view" | "shared"` estimates each picture's expression (eight GNM
     prototypes: frown, brows raised, squint, lips pressed, corners down, smile, mouth left / right) as a nuisance
     on the interior reads: on known heads it did not lower the identity's error, and on neutral pictures it made
     it worse. When EVERY picture shows the same expression (Garrett's frown and squint), geometry cannot tell it
     from identity: the solve bakes it in. Say so when you report such a head.
   - On a loaded machine set OPENBLAS_NUM_THREADS=1 for scripts that call the solve: its many small solves stall
     in thread contention (0.3 s against 200 s for one call's down-weighting search with load 60).
   - JUDGE the result on the judging sheet (spikes/refread/rsheet.py: reference | best: 50 % blend, the reference
     pictures projected as its skin, own dressing | the rest), not on a dressed render in an unrelated dressing:
     look at the blend before calling a feature wrong. Face-ID scores do not judge shape (they read the projected
     texture).
4. **One small step** (0.3-0.7 sd; a big mass difference 1-2 sd, see the manual's step sizes):
   `block_in_step(name, {direction: amount}, seen=..., why=...)`. Each step writes
   a NEW model (default: the next number), so every round stays comparable; `seen` and `why` go in the log.
   - FREE `"chin_height": 0.5`: the population's conditional mean per +1 sd: the face stays whole. Try first for
     masses and proportions.
   - HELD `"chin_height!": 0.5`: that one macro, every other macro held (a pseudo-inverse column). For a single
     feature, or to put back a neighbour a free step dragged. Costs more |c| per unit (more unusual faces).
   - GAPS `"nd:radix_width": 1`: vocabulary the macros lacked, filled with data-backed coupled directions (below).
   - `sex`, `eth0..2`: the sampler's sex axis (+1 = female mean -> male mean) and ethnicity contrasts.
   - BASE keys, SET: `head_scale` (base.style.human.head_size: the head's UNIFORM size about the neck, x the body's
     own head; 1 = the body's), `gnm_base`, `dimorphism`, `weight`, `eye_size` (base.head.eyes: the eye AND its
     orbit scaled about the eye centre), `eye_radius` (base.head.eye_radius, m: an OVERRIDE of GNM's eyeball by
     an absolute ball of ours, seated by a search; 0 drops it). THE DEFAULT (2026-10-12) IS GNM'S OWN EYEBALL: its
     14.6 mm scleral sphere at its eye joint x the head's scale, which GNM's lids are shaped on; block_in_start
     drops a refs model's eye_radius (every head made 2026-10-10 .. 12 carries 0.012: on those the lids stand
     ~0.5 mm further off the ball). Do not shrink the ball to fix an iris: the iris is its own quantity:
   - GNM's OTHER identity components, SET: `iris_mm` (the iris' diameter in mm at the model: solves the identity's
     `eyes_000`, GNM's limbus, sd ~0.4 mm of radius; `brow_read` / `eye_ruler`'s IRIS line gives the picture's),
     `id:eyes_001` (the cornea's prominence, sd; only from a profile close-up), `id:teeth_NNN` (GNM's 80 teeth
     components, sd; only from a picture that shows the teeth); expression components SET: `ex:pupils_000` (the
     pupil: -1 = 0.33 of the iris, 0 = 0.5, +1 = 0.67), `ex:tongue_NNN`. They are the same identity / expression
     vectors as the head's 170 + the eye / lower-face regions: every step and solve keeps them.
   - DESIGNED age / soft-tissue ops, SET: `shape:<op>`: faceslide's age sliders in their units (`age_nasolabial`
     +1 = a 2 mm fold, `age_prejowl`, `age_cheek_flat`, `age_lid_fold`, `face_planes`, `face_lean`, `cheek_hollow`
     +1 = 4 mm) and headage's ops without a slider (`eye_bag`, `lip_bow`, `lip_roll` in m, `lips_thin` a share).
     Hand-authored, NOT learnt from people: the reply and the log flag them DESIGNED. Place them by eye, zoomed in
     (focus=cheeks / mouth) under the raking light against the pictures; the cheeks rows (nasolabial_fold,
     cheek_hollow: shading contrast, photo minus clay) should close. Garrett: age_nasolabial 0.5 closed the fold's
     gap 22 -> 19 % (front) and 28 -> 20 % (3/4).
   - LOCAL residuals, SET: `local:<faceslide slider>` (base.head.sliders), for what no identity direction draws;
     the reply warns past 2.5 x the slider's population sd beyond GNM (ICT: nose_radix_width 0.09, nose_tip_width
     0.18, nose_dorsum_width 0.12).
   - LIDS, SET: `lid_upper`, `lid_lower` (metres, -0.001 = 1 mm up): by measure, see 7.
   - SCULPT, the GNM way (THE standard fix for a feature no macro reaches, before any local): `"sculpt:<zone>": mm`
     moves a named zone (its mean normal, + out of the face) by the LEAST-COST identity change over all 170 comps with
     every macro HELD (the face's measured proportions stay) and a locality penalty on the skin > 6 mm away;
     `relief:<zone>` moves it against its 5 mm surround (- deepens a groove: alar crease, nasolabial, lid fold).
     Options after `|`: `hold=<zone>+<zone>` (zones kept still), `free=<macro>+..` (macros let go), `loc=<w>`. Zones:
     `gnm_controls(zones=True)`. Garrett's narrow bridge: `"sculpt:bridge_walls|hold=dorsum": -1.0` = walls 0.746 ->
     0.590 at |dc| 3.5 (the designed local nose_dorsum_width -0.8 gave 0.670); -2.0 reaches his concept's 0.504. A
     sculpt of 1 mm usually costs |dc| 2.5-4: big next to a macro step, but it moves a real face's |c| (~13), not away.
   - MILLIMETRES: `"mm:<measure>": mm` moves one measure you can see (pupils_apart, eyes_forward, eyes_height,
     brows_over_eyes, forehead_forward, tip_forward, subnasale_forward, upper / lower_lip_forward, chin_forward,
     philtrum_length, chin_length, nose_length, the widths, skull_top / back, under_chin, and the orbit's
     brow_ridge_forward, side_rim_forward, under_eye_forward, brow_hollow: 27) by that many mm with every
     other measure held in mm, the lids kept on the ball and the profile line kept (gnm_mm; |dc| 0.3-1.7 per mm).
     Every forward measure is taken against the NASION (subnasale_forward was against the eyes until 2026-10-11). Use it FIRST for anything you can measure (manual
     section 0a): take the largest gaps in population sd first; several mm: moves in one step add up exactly. The
     forward measures are a chain (subnasale -> upper lip -> lower lip -> chin): a link carries what is below it. The
     eyes set further apart is `mm:pupils_apart` (eye_spacing moves only the inner corners; head_size! scales the head).
   - RAW CONTROLS: `"gnm:<control>": amount`: any identity-space control of the atlas (`head_042`, `z:05` a sampler
     latent, `label:sex`, `pc:nose_region3`): see `gnm_controls`.
5. **Keep it only if the whole face reads closer AND no target went out.** The reply has the read (the moved macro,
   before -> after, and the largest coupled moves), the target table's delta (items that went out, came in or moved
   by half a tolerance) and the new sheet. Otherwise step again from the earlier model: that is the revert (the log
   marks the abandoned step). Free moves drag neighbours; the table catches it; put the neighbour back with a held
   step (length -> philtrum, lips -> chin, bridge / eye depth -> narrower eyes, chin height -> chin width).
6. **The table after every step** (five groups: head shape, jaw and chin, eye placement, nose, mouth: likeness items
   read the same way on the picture and on the model through its fitted camera, with tolerances). `flag` items are
   shown, not counted (jaw_angle_height reads the detector's guess at the jaw contour, not the gonion; alar_width and mouth_over_alar read MediaPipe's alar points, which sit on the cheek past the alae: judge the alae by eye in focus=nose). A SIZE line
   appears when the long lengths are all off the same way: that is a uniform scale (the camera's distance or the head's
   size), not shape: refit the camera (`block_in_step(..., cameras=[i])`) or set `head_scale`, never chase it with
   head_size / eye_spacing identity steps.
7. **The EYE STEP: the lid as ONE structure, after the orbit** (Joe: "we shouldn't really ever use our 'fix'
   [lidfold]"; "We are treating the crease as if it's different from the eyelid but it's not"). ORDER: the ORBIT is
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
      the turn put on the picture's fold line (per column), the margins of 1 held. Default `fold="crisp"` (RECIPE A,
      Joe 2026-10-11: "as good as it has to get"; gnm_fold.fold): a DESIGNED lid (no donor head) fitted with the
      brows held 0.3 mm and the mm measures held (the hollow under the brow is left free: the fold IS that). Tess
      scratch: turn 16 -> 44 deg on her line (the donor solve: 24), brow ring 0.7 mm down, measures within 0.35 mm,
      eye ruler and brow_read rows still pass; the price is |dc| ~15-17 and ~0.6 mm rms over the rest of the face
      (rows near their tolerance can go out: read the step's table). `fold="donor"` (or `donor=`): the older solve
      toward a donor head's lid (GNM sample #376): softer (24 deg), |dc| ~6. A picture with no fold line (hooded): no
      lid solve, the visible platform is the opening's target. A genuinely HOODED / deep-set eye is not a lid
      feature in GNM: it is the brow and drape coming down over a deeper eye: `block_in_step(name, {"hooding": x})`
      (per unit ~+0.6 mm of overhang, brow -2.4 mm, eyes 1.8 mm deeper; an ORBIT move: do it before the eye step
      and read the orbit rows / brow_read again). Wrong for an open lid with a platform (Tess);
   3. the EYEBALL GUARD: our ball is seated on six lid landmarks, not the lid's surface, so a lid lying on the ball can
      let it through (a patch of the ball's colour on the lid). The step measures the lid's stand-off from the ball on
      the shipped head and lifts the designed platform until it clears by 0.25 mm; the report gives the numbers.
   The report: the opening's rows (picture | model), the lid's structure before / after / donor (platform's stand-off
   from the ball, the turn in degrees and its height, the wall, the drape), |dc|, the guard. Tess (er_s4 -> the lid
   solve): platform 1.6 -> 1.4 mm off the ball, turn 17 -> 25 deg at her 4.7 mm line, wall 29 -> 40 deg, |dc| 4.4, the
   platform lifted 0.4 mm for the ball, margins within 0.05 mm. Honest limits (gnm_atlas "## eyelid"): GNM's largest
   turn on a platform as tall as hers is ~25 deg and NO GNM head has skin over skin (an overhang), so her thin dark
   fold line is not reached by geometry, and by decision (Joe, 2026-10-11) it is LEFT ALONE: no painted fold line, no
   crease make-up, no liner, no extra layer. Judge the lid's FORM under a raking light (focus=eyes) and dressed; do
   not judge it by the line's darkness.
   `match="pose"` is the older lid_upper / lid_lower offsets. Eye size and "almond" shape are mostly lids and seating:
   an identity step for eye height made eyes read NARROWER.
7a. **Measure the eye with the RULER, never by eye** (Joe, on a matched photo / render sheet: "I notice some
   measurement errors": our eye was 3 mm short at the nose side and 1.3 mm too open at the top, and four agents had
   called it matched). `eye_ruler(name)` reads the front picture by its EDGES (the iris as a circle through the limbus;
   the lid margins at 7 columns; the canthi; the fold line; the brow's edge) and the model's mesh through the same
   camera, in mm from each eye's iris centre, with a tolerance per row (the reader's measured error) and the move that
   closes each starred row. Why not the detector: MediaPipe's iris centre sits ~1 mm LOW (it follows the visible part
   of the iris), its iris is 9-22 % small, its lid points are 1-1.5 mm out, and GNM's lm68 eye corners are not the
   visible opening's ends (the inner one is the canthal pocket's tip, 1.9 mm past where the eyeball shows). The eye
   step (`lid_read(match=True)`) now solves for the ruler's margins and corners in mm when the picture's iris is at
   least 30 px across. Three things the ruler found that are NOT the solve's to fix:
   - the EYEBALL: GNM's lids are shaped on its own ball (14.6 mm on a full-size head), and that ball is the default:
     leave `eye_radius` unset. A ball shrunk to make the drawn iris right (0.0101 on Tess) leaves the corners empty
     (1.2-1.4 mm of socket lining at the outer end) and the eye reads short. The iris has its own size: GNM's limbus
     (`block_in_step {"iris_mm": mm}`; `skin.eyes.iris_size` overrides the drawn iris only).
   - the CARUNCLE: `skin.eyes.caruncle: 1` paints the inner corner's pocket wet dark red from GNM's inner-corner
     landmark to the eyeball. Unpainted, the pocket is skin-coloured and the eye ends ~2 mm early at the nose side.
   - the LASH LINE: a photographed lash line is a thin dark line; lashes 9 mm long and 0.15 mm thick (the defaults)
     read as a fringe. `base.lashes.upper` length / thickness / count.
7b2. **Brows and iris before a dressed eye is judged** (Joe on a dressed sheet: "the eyebrows sit on top the crease ...
   so I can't really judge"): `brow_read(name)` gives the brow hair's miss against the picture and the iris line
   (picture limbus vs drawn iris, mm at the model). If the iris is off by more than 5 %, step `iris_mm` to the
   picture's (GNM's limbus component; do not shrink the ball: 7a); then `brow_read(name, match=True)` places the hair
   from the picture. Compare dressed renders with the
   picture ONLY through the picture's fitted camera and the same pixel crop (never an "11.7 mm iris" scale: the
   detector's iris points under-read our renders by 19 % and a photo by 6 %).
7c. **The LIPS STEP: the lip line the way GNM is built** (Joe: "still don't have her lip line"). A block-in's rest mouth
   is closed by GNM's OWN lower-face expression (`head.lip_close`, set by block_in_start: the least change that puts
   the contact ring's halves together corner to corner, re-solved on every head), never the seal: `lip_seal`'s
   membrane dragged the whole vermilion and halved the border's turn (24 -> 11 deg on Tess), the lips read as a flat
   painted pad. A closed mouth's field leaves GNM's crossed inner rolls out (the seam is one line, no pale band or
   dark corner holes). `lip_read(name)` reads the picture (the vermilion borders traced on the a* edge, the seam, the
   Cupid's bow) beside the model through the front camera. The vermilion BORDERS are already inside `block_in_solve`
   (3b; 0.2-0.5 mm after a settled solve): read `lip_read(name)` first and run the step only for what the solve does
   not do (the seam, the bow, the closing expression). `lip_read(name, match=True)` is the step: identity + GNM
   lower-face expression for the borders (0.35 mm), the seam (0.4), the bow (0.1 mm) and the neutral closed, the 68
   landmarks off the mouth held; it ships head.expression, lip_close / lip_seal / mouth_gap cleared. Judge with
   focus=mouth AND dressed (the lips' paint follows GNM's own vermilion edges). Tess (gd_T12): borders 1.96 / 3.80 ->
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

A sheet every 3-4 rounds for the person you report to; read it yourself first, bluntly.

## The feature pass: ZOOM IN, step, ZOOM OUT (Joe: "focus more on each feature, then zoom back out after each change")

After the whole-face block-in (outline, size, masses and planes right), go feature by feature, big to small: jaw and
chin, cheeks, nose, eyes (with brows and lids), mouth, ears; then the whole face again; repeat the pass while it
pays. Each round:
1. ZOOM IN: `block_in_look(name, focus=<feature>)`: per view the feature's crop at full resolution, photo beside
   clay through the same camera, REGISTERED AT THAT FEATURE'S OWN LANDMARKS (a 2D shift: an offset elsewhere doesn't
   hide its shape), overlay, the feature's own detector contours (photo red, clay green), the clay under a RAKING
   light (forms, not tone), the feature's squint, and its own checklist rows (every likeness item of that feature;
   the lids' margins for eyes). Name its single biggest difference in that feature's own vocabulary (a nose: dorsum
   line, tip width / projection / rotation, alar flare, columella, nostril show; eyes: lid margins, canthal tilt,
   fold, how deep the ball sits; mouth: vermilion heights, bow, corners, width, projection).
2. ONE step aimed at it: a held macro (`name!`), a gap direction, a lid move: `block_in_step(..., feature=<feature>)`
   returns the feature's before | after crops and its rows, then the whole-face sheet.
3. ZOOM OUT: look at the whole-face sheet + full table. Keep the step only if the FEATURE got closer AND the whole
   face reads closer or equal (no target out). Log the zoom-out read: `block_in_look(new, read="...", keep=True|False)`.
   Not kept: step again from the earlier model.
A feature that no direction can reach is a vocabulary gap (below), not a reason for a big step. First ask the atlas
which GNM controls move it (`gnm_controls(query="bridge walls")`), then SCULPT it (macros held), and only then a local.

## Coupling you will meet (free directions)

| step | drags |
|---|---|
| face_length | the philtrum (gets longer before the chin does) |
| philtrum (free) | the chin (shorter) |
| lip_projection | the chin's height |
| chin_height (free) | chin width |
| bridge_height, eye_depth | interocular distance (eyes narrower) |
| orbital_rim (nd) | a heavy brow and deep eyes come with it (the male pattern): hold them or the face reads older |

## Filling a vocabulary gap

When no direction expresses a difference you see: write a reader for it on GNM heads, measure it over ~2000 sampled
heads, and look at R2 (is it linear in the identity?), its sd (does the population vary it?) and its couplings. Add
it as a coupled direction (conditional mean within sex). R2 high and sd visible: a new direction (`nd:` table in
`blockin_data.npz`, built by faces6 newdirs.py). Low R2 or a tiny sd: a real capability gap: a small LOCAL residual is
justified. A coupling against what you see (a defined orbital rim pulling in a heavy brow) means the look lives
elsewhere (lids, skin) or needs a held variant (`nd:orbital_rim|hold_brow_ridge_eye_depth`).

Filled so far: gonial_height, orbital_rim, lower_orbit (also humanmacro macros), radix_width (R2 0.90, sd ~0.6 mm:
GNM barely varies it; ICT adds ~0.13 mm beyond GNM: a near-invisible gap, `local:nose_radix_width`), tip_width (R2
0.94, sd 1.3 mm: comes with wide alae, full forward lips and a low bridge; `nd:tip_width|held` keeps those), and held
variants `orbital_rim|hold_brow_ridge_eye_depth`, `gonial_height|hold_face_length_chin_height`.

## What goes wrong

- Big steps (> 1 sd): one move then explains three differences and you can't tell which one was right.
- Chasing a uniform size with identity steps (head_size!, eye_spacing!): the table's SIZE line; check camera and
  head_scale first.
- Judging on the outline overlay alone: the outline is the easy part. The planes inside it (cheeks, muzzle, orbit)
  are what makes the person; squint.
- Fixing eyes with identity: lids are pose (lid_read).
- A painted or stylised picture's light is not one light, and its camera may fit badly (the clay turns differently
  from the painting): judge shape on the photographic views first; refit that view's camera.

## GNM's controls (the atlas: gnm_controls)

Every way to move GNM's head, measured (gnmcontrols, 2026-10-10): 170 identity comps + eyes 3 + teeth 80, the region
principal directions (pc:), 100 symmetric eye-region and 150 lower-face expression comps + tongue / pupil, the joints,
the identity sampler's 64 latents (+ 16 principal latent directions) and its labels (sex, 4 ethnicities), the
expression sampler's 20 class prototypes, and our block-in moves. For each: where it acts (50 named zones: alar_crease,
vermilion borders, jowls, lid_fold, bridge_walls ...), mm per unit of prior cost, how local it is, the macros it drags,
its face-ID effect, the nearest block-in move, and its sheet (workspace/human_renders/gnm_atlas/<family>_<page>.png:
-2 | 0 | +2 front / 3/4 / profile in hair-cap clay + the move's map; index.html lists them all).
What it taught (use it when choosing a step):
- GNM's identity comps are WHOLE-FACE: median specificity 1.5 (the moved zone vs the face's rms), at any index; no
  single comp is "the alar crease". A local feature is a COMBINATION: that is what sculpt solves for.
- Per unit of prior cost the most identity-laden moves are the ORBIT / BRIDGE complex (bridge_height, eye_depth,
  orbital_rim, brow_ridge, nose_projection: face-ID 0.15-0.19 per sd): steps there change who it is fastest.
- Per mm moved, the fine comps (120-169: 0.04 mm per unit) are 5x as identity-laden as the first ten.
- The identity sampler's latent space is a GENERATOR, not a fitting space: our people and GNM's own N(0, I) heads
  are not on its 64-d manifold (residual > |c|); its labels are clean whole-face directions (label:sex, label:white
  narrows and steepens the bridge, label:asian / black widen it).
- The expression sampler's 20 class prototypes are data-backed whole-face expressions (eyes and mouth together: happy
  squints the eyes): the vocabulary for a picture's expression.

## Tool reference

### `gnm_controls`
gnm_controls(query="", control="", families=None, top=12, sort="score", per_family=0, sign=0, zones=False, phrase="", ruler=""): the atlas.
- query="mm": the 23 millimetre measures (`mm:<measure>` moves): what + looks like, the view to read it in, its
  population sd. ruler="modelA,modelB": the RULER between two models' GNM identities (B - A in mm and sd, largest
  first, each row with the `mm:` move that closes it): e.g. an earlier round, or a head you liked, as the target.
- phrase: a DIFFERENCE you see, in an artist's words ("the muzzle stands forward in profile", "pupils further apart",
  "double chin", "eyes and brows sit lower over the nose") -> the driving manual's best entries (guide topic
  gnm_driving: the control, its sign, mm per unit, what to hold, what it drags, the phrases it is confused with).
  Start here when you have named a difference; block_in_step's reply also lists them for its `seen` text.
- query: a feature in words ("alar crease", "jowl", "lip border", "bridge walls", "lid crease", "tear trough") or a
  zone name -> the controls that move it, ranked by sort: score (mm per unit of prior cost x specificity, capped at 4:
  the cheapest, most local movers; default), efficiency, local (mm per unit), specific, perc (face-ID), relief (the
  zone against its surround: deepening / softening a line). sign +1 / -1 keeps controls whose + moves it out / in
  (with relief: rises / sinks). per_family=k: the best k of each family instead of one ranking.
- control: one control described: its zones, macros, face-ID, nearest block-in move, sheet.
- zones=True: the zone list.
Each row: control | family | local mm per unit | mm per unit prior cost (its |coefficient| per unit) | specificity |
relief | out / in | face rms | face-ID | macros dragged (sd per unit) | nearest block-in moves | sheet. Act on it with
block_in_step: `"gnm:<control>": amount` (identity controls) or `"sculpt:<zone>": mm` (a combination, macros held).

### `block_in_start`
block_in_start(name, refs, sex=None, age=None, body=None, gnm_base=None, ethnicity=None, cameras="keep",
replace=False, save=None): the block-in's first model.
- refs: a one-mesh human whose pictures are fitted (`human_reference` wrote its human_refs.json: views + cameras):
  its body is taken (body = keys merged over it, e.g. {"weight": 0.3}); or a views list ([{"image", "size", "yaw",
  "points"}] as human_reference) with age / sex / body for a new body, cameras fitted on the new head.
- sex: "male" | "female" | 0..1 (default the body's): the base is that sex's class mean in GNM's semantic sampler.
- age: overrides the body's age; gnm_base: default by age (0.5 to 25, 0 from 50, linear between).
- ethnicity: one of GNM's sampler classes (middle_eastern, asian, white, black) for that class mean; omit it unless
  you know it (eth0..2 steps can move along the contrasts later).
- cameras: "keep" the refs model's fitted cameras (they were fitted on another head: fine for a start), "refit" them
  on the new head (camera only).
- name must be new (replace=True overwrites); the log (blockin_log.json) lives in this model's folder and every
  later step appends to it. save: the sheet's path (default workspace/human_renders/blockin_<name>.png).
Returns the first sheet and target table. The rest mouth is closed by GNM's expression (head.lip_close; lip_seal and
mouth_gap dropped), see 7c.

### `block_in_look`
block_in_look(name, views=None, table=True, save=None, before=None, focus=None, read="", keep=None): the sheet (see
the loop, 2) of any block-in
model, rows per view (views = indices), crops fixed at the start head's frame so rounds compare; table=False skips
the target table. before = another model (any earlier round): under each view a row photo | before | after | the
change (|after - before| x4, dark = moved) | squint before | squint after. block_in_step's sheet always has it.
The text gives each view's eye-registration shift (pixels: a large one means the camera misplaces the head).
- focus: one of eyes, nose, mouth, chin_jaw, cheeks, ears: the ZOOM-IN sheet (see the feature pass): rows per view
  (the ear only in turned views) photo | clay | overlay | local contours | raking light | squint photo | squint clay;
  with before = another model a second row photo | before | after | change | raking before | raking after. The text
  is that feature's checklist rows (+ the lid read for eyes). Default save workspace/human_renders/blockin_<name>_<feature>.png.
- read / keep: log your ZOOM-OUT verdict on the step that made `name` (the log keeps both reads: the step's `seen`
  is the zoom-in read).

### `block_in_step`
block_in_step(name, moves, out=None, seen="", why="", cameras=None, look=True, save=None, feature=None): one round.
- feature: the feature this step is for (a feature pass round): the reply also carries its focus sheet (before |
  after) and its own rows, and the log records the feature's pass count before -> after.
- moves: {direction: amount}: macros free / held (`name!`), `nd:<gap>`, `sex`, `eth0..2`, `pc:<region><i>`,
  `gnm:<control>` add (amount in sd); `sculpt:<zone>` / `relief:<zone>` add the least-cost GNM move per mm (macros
  held; the reply gives its |dc|, the macros let go and the skin moved elsewhere);
  `head_scale`, `gnm_base`, `dimorphism`, `weight`, `lid_upper`, `lid_lower` are SET. An unknown name lists the
  vocabulary.
- out: the new model's name (default: name with its number + 1, or name_01); an existing name is refused.
- seen: the biggest difference you named; why: why this move answers it. Both logged.
- cameras: view indices whose camera to refit on the result head (camera only, the head held), e.g. a painted view
  whose camera fitted poorly, or after a head_scale change.
- look=False returns the text only. Reply: |c| before -> after, the moved macro's read, the largest coupled moves,
  the target pass counts before -> after, the items that changed, and the new sheet (with before | after | change
  rows: a half-sd step is hard to see beside the photo alone) + table.

### `block_in_expression`
block_in_expression(name, out=None, views=None, clear=False, seen="", why="", look=True, save=None): a round that
changes no shape: a new model (out) whose references carry each picture's fitted expression (views: default every
view with a detector, |yaw| < 70; a profile's few clicks can't separate expression from shape). Reply: per view chi2
before -> after on the detector points, |e| and the largest comps, then the table delta and a sheet before (neutral)
| after (with the expression). Stored in human_refs.json "expressions" (one {GNM expression comp: value} per view,
{} = neutral); blockin.view_base(base, refs, vi) gives the head as that picture shows it.

### `block_in_solve`
ONE JOINT STEP: face_ruler's solve over every reference view (skin outlines, irises, limbus, lid margins, lip borders, detector anchors; GNM's prior on the whole identity; cameras partly free) applied whole as a block-in step, the solve's cameras kept. Use it FIRST from block_in_start's head, 3-4 calls until |dc| < 2, instead of closing measures one at a time. cameras: "free" | "trust" (measured cameras: a third of the freedom) | "refit" (cameras fitted on ANOTHER head: laid on this one first; first call only); the freedom is on the cameras' whole move since the start, so keep one setting. anchors: "differential" (the detector on the picture minus the detector on our render) | "absolute" | "none". chin_points: "auto" (default: the detector's chin points are left out when the set has a side view, 60 deg or more: its outline reads the chin; kept when it has none) | "on" | "off". parse: "auto" (outlines from the face parser where the plain-background reader finds too few: paintings, dark or busy backdrops) | "on" | "off". Nothing is forced: no component passes 3 sd; pictures that disagree are down-weighted and SAID so (the factor is carried across calls). The reply lists what MOVED WITH NO READ, what moved far on a weak read and what is unread (solve_report's direct read: treat those as inferred), warns when a view's stated kind disagrees with its fitted camera, and marks a DAMPED step (it turned back on the last call's). hold: "none" (default) | "auto" (every measure no read looks at stays at the start head's value). expression: "none" (default) | "view" | "shared" (the pictures' expression as a nuisance; did not validate). It does not see the surface inside the silhouette (cheeks), nor the chin's own width and the jaw's lower edge from front / shallow views (unread, not pushed: section 3b). Parameters: name, out (new model name), share (fraction of the step), seen (what you saw, logged), save (sheet path), cameras, anchors, chin_points, parse, hold, expression. See section 3b.

### `lid_read`
lid_read(name, match=False, out=None, seen="", save=None, expression=False, donor=None, fold=None): the picture's lid margins
against the iris (MediaPipe iris and lids, in iris radii: upper MRD1-like, lower MRD2-like, the opening's aspect) and
the model's (its front render, the visible eyeball through the iris centre): a quick look, biased (the detector's iris
centre is ~1 mm low); the numbers to trust are `eye_ruler(name)`'s. match=True: the EYE STEP (loop, 7), IDENTITY ONLY:
the orbit check (ORBIT: UNREAD / OFF / read: set the orbit first), the opening solved for the RULER's margins (7
columns, mm) and canthi (the detector's two lid points in iris radii only when the picture's iris is under 30 px), the
lid as one structure on GNM's lid rings (fold="crisp", the default: recipe A, a designed crisp fold on the picture's
fold line, brows and measures held; fold="donor" / donor="s376" | "s540" | a block-in model's name: toward that lid)
with the eyeball guard; a new block-in step (out, seen as block_in_step); returns the focus=eyes sheet (before | after) and the report.
expression=True adds GNM's eye-region expression to the opening's solve: only for a real pose (a squint). ~5 min.
match="pose": the older lid pose offsets (lid_upper / lid_lower, metres).

### `eye_ruler`
eye_ruler(name, model=None, save=None): the front picture's eyes against the model's mesh, in mm at the model (the
fitted camera's mm / px), each eye in its own frame: origin = the iris centre, u toward the outer corner along the line
through both iris centres, v up; both eyes' mean. Rows: iris diameter (limbus circle), pupils apart, inner canthus (the
caruncle's tip; model = GNM's lm68 inner corner), outer canthus (where the visible eyeball ends), fissure length,
canthal tilt, the upper and lower margins at u -6 / -3 / 0 / 3 / 6, the opening at the pupil, mm of iris the upper lid
hides, where the upper lid peaks, the caruncle showing, the fold line / visible lid platform over the margin, the brow
hair's lower edge over the margin. diff = model - picture; * = beyond the tolerance (2 x the reader's rms error on 14
dressed fitted-camera renders of known GNM heads: iris 0.12 mm, margins 0.25, corners 0.45-0.63, fissure 1.0, tilt
1.8 deg, peak 0.6, brow 0.7). The lower margin's picture read has 0.35 mm taken off (it reads the waterline's top).
Not trustworthy: the fold line on a RENDER (a soft fold is not a line: +-3 mm; the model's crease is read from the
mesh instead) and on a photo whose line is fainter than 0.08; anything on a picture whose iris is under 30 px (a
NOTE says so). model=<other>: that model against `name`'s picture and camera (same refs). The returned image is the
picture's two eyes (nose side left) with its read drawn (green margins, red canthi, yellow limbus, cyan fold line,
magenta brow edge) and the model's margin ring / margins / inner-corner landmark in blue, laid over by iris centre.
MOVES name the tools: `lid_read(match=True)` (the eye step solves these margins and corners), `iris_mm` (GNM's limbus),
`mm:pupils_apart`, `skin.eyes.caruncle`, `brow_read(match=True)`. Python: eye_ruler.read(img, P, mmpx) on any picture
(a dressed render through the same camera reads the same way), eye_ruler.model(spec, cam), eye_ruler.compare(name).

### `face_ruler`
face_ruler(name, save=None): the block-in model against ALL its reference pictures, in millimetres. First the ORBIT
rows (loop 3a: eye depth as a side view shows it, each with its error; the cameras' solved yaw / pitch and which
limbus was read are in the notes under the table), then gnm_mm's 27
measures (the orbit's four rims and hollow, and pupils apart, eyes forward / height, brows over the eyes, forehead forward, nose tip / base forward, nose
length / width, upper / lower lip and chin forward, philtrum and chin length, cheekbone / jaw / chin / mouth / skull /
neck width, the vault's top and back, the line under the chin). Each row: picture - model (GNM's mm and population
sd), +- the reader's error, the move `"mm:<measure>": gap` for `block_in_step`, the view it shows in. Largest (in sd)
first. Rows inside the error say so; rows marked NOT READ are measures these pictures do not show (their number is
the population's guess from what was read: do not act on it).
How it reads (face_ruler.py): no detector landmarks and no eye. (1) Each picture's SKIN OUTLINE against a plain
background (the profile's forehead-nose-lips-chin-throat line, the 3/4's far brow / cheek / jaw, the front's jaw and
neck where hair does not cover them; hair, cloth and loose strands are left out: skin just inside the edge is required)
compared with the model's own silhouette through the same fitted camera, at 1.5 mm steps along it. (2) The iris
centres on the front picture (eye_ruler's limbus circle) against the model's. (3) One solve for the GNM identity
change that explains all of it under GNM's own population prior, each picture's camera left free by 2 mm / 5 % / 1.2 deg
(a camera fitted from the model's landmarks is that far off, measured) and refined between rounds; the 23 measures are
read off the solved change. So a row is not a caliper reading but the most likely value given every outline at once.
Errors (validated on pictures of known GNM heads; reader - mesh truth, rms mm): camera known: profile chain (tip, nose
base, lips, chin forward) 0.1-0.3, eyes 0.05-0.3, brows 0.2, philtrum / chin / nose length 0.2-0.6, mouth width 0.3,
nose width 0.9 (never seen directly: inferred), widths 1-1.8, skull 0.2-0.5 (1-1.8 under hair). Camera FITTED from
the model (a photo's case): profile chain 0.1-0.6, eyes forward / height 0.5-0.9, pupils 1.2, lengths 0.5-1.0, widths
2-3.6 and skull 1-3 (a fitted camera's scale is free: absolute size is the least known thing in a photo). The one
mesh takes the head's size from the body, so a uniform size gap is not in the table: `head_scale` is its own key.
On a BLOCK-IN model (the one mesh; dressed pictures of 8 known heads through real fitted cameras, hair masked, size
taken out): tip / upper lip / chin forward 0.4-0.6, pupils 0.8, under_chin 0.9, lengths 0.8-1.7, brows / eyes height /
forehead 1.1-1.2, eyes_forward 2.8 and subnasale_forward 2.0 (weak: 1.4-1.9x), widths and skull 2.3-5; NOT readable
there: neck_width, nose_width, lower_lip_forward, mouth_width (the table marks them). The table's +- is never under
these. Gaps are in GNM's mm = the `mm:` dose (the one mesh makes ~0.88 of GNM's move).
Limits: plain backgrounds only (no outline otherwise: the table says how many reads each picture gave); lips,
nostrils, brows' shape are not read on photos (eye_ruler / lip_read / brow_read do those); a non-neutral expression
moves the lips and chin rows. The returned image is the pictures with the model's outline (green, through the
refined cameras), the reads (yellow) and the iris centres (magenta picture, cyan model): check that yellow sits on
skin edges only. Python: face_ruler.compare(name); on any pictures face_ruler.read(head, views) with head =
gnm_head(c) or model_head(spec); clay pictures of GNM heads also read pupils, lip edges and brow tops by colour.

### `brow_read`
brow_read(name, match=False, out=None): the DRESSED brows (the skin's hair picture, skin.hair.brows) against the front
picture's brow hair, through its fitted camera, in mm at the model: the hair band's lower edge and middle line at 9
columns across each brow (half contrast against the skin; + = ours lower, toward the eye), a WARNING past 1.5 mm; and
the IRIS line: the picture's limbus diameter in mm at the model against the drawn iris (GNM's limbus for the identity,
or skin.eyes.iris_size), the `iris_mm` step that makes them equal (its eyes_000 in sd), the picture's iris colour. match=True fits skin.hair.brows' placement (drop, tilt, apart, fall, thickness,
taper; "lift" folded in) to the picture's band and writes it (out: another model; default in place). Paint only.
Why: GNM's brow landmarks are the ridge's, not the hair's; brows set by eye on one head travel with the dressing onto
the next and end up on the lid's fold (Tess: 4-7 mm low). Run it after the eye step, before judging a dressed eye.
An iris 1.18 x too big (where the lids are matched in iris radii: a picture under 30 px of iris) opens the eye 1.18 x
too tall and crowds the brow: step `iris_mm` to the picture's, then run the eye step again.

### `lip_read`
lip_read(name, match=False, out=None, seen="", save=None): the front picture's lips (the vermilion borders traced on
the a* edge from MediaPipe's outer lip contour, the seam between MediaPipe's inner contours, the Cupid's bow: peaks over
the centre trough, mm) against the model through the front camera (with the picture's fitted expression): border miss
upper / lower (rms mm, and the mean offset, + = the model's outside), seam miss, bow picture / model, the neutral's
contact gaps (max / median / min mm), the inner rolls' smallest gap (- = crossing: normal for GNM's closing, the
field leaves them out) and how the mouth is closed (lip_close / seal / mouth_gap / expression). match=True: the LIPS
STEP (loop, 7c), a new block-in step (out, seen as block_in_step); returns the focus=mouth sheet (before | after) and
the solve's report. ~3 min.

