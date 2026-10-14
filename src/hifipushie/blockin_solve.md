# Block-in: the joint solve in detail (`block_in_solve`)

Read guide(topic="block_in") first: the loop, the stage-0 description and the self-review.

1. **Start from a base of the right kind**: `block_in_start(name, refs, sex=...)`. The person's body (MakeHuman's
   age / weight / height from `refs`, a one-mesh human whose pictures are fitted by `human_reference`), the identity =
   GNM's sampler CLASS MEAN for the sex (and an ethnicity class only if you know it), on a **GNM-NATIVE head**: GNM's true base (`gnm_base` 1, `dimorphism` 0, `eyes` 1, no head style sliders), GNM's
   own eyeball / mouth / teeth / tongue, at GNM's own size with the body fitted to it (`base.head.attach: "native"`,
   guide topic human_shape). **Nothing of ours is on its surface**: the head's local layers are off (sliders, warp, folds,
   pose, shape) and the refs model's sculpt `strokes`, `skin.folds` and painted wrinkle relief (`skin.wrinkles`) are
   NOT carried; the reply lists what was DROPPED and what was LEFT (skin tone, zones, paint layers, micro relief).
   `carry=True` keeps them, `attach="body"` gives the old body-carried head (with `gnm_base` by age): both are the
   old behaviour, asked for explicitly. The cameras of a refs model whose head stood at another size or place are
   CARRIED onto the new head (same view, same yaw) and the first `block_in_solve` lays them on it. Never start from a
   previous fit: it carries that fit's mistakes. The reply is the first sheet and table.
   On a native head `head_scale`, `gnm_base`, `dimorphism` and `eye_size` steps are REFUSED with the reason (they do
   nothing there); an older model becomes native with `block_in_step(name, {"attach": "native"})` (a step of its own:
   the head switched, the cameras carried, the dead keys dropped and named).
   **MEASURE FIRST: `face_ruler(name)`** reads the 23 millimetre measures off the pictures themselves (skin outlines
   and iris centres through the fitted cameras) against the model: picture - model per measure, largest first, the
   reader's error, and the `mm:` move that closes each. Start every block-in from that table and run it again after
   each step (it re-reads the pictures against the moved model). Tested on 14 fresh synthetic pairs: Claude drivers
   with this ruler passed 11 (by eye 3, with a ruler that needed the target's mesh 7); its 8 largest gaps applied
   without looking passed 11, with the camera fitted from the model's landmarks as on a photo 11 of 13. Where a driver
   disagreed with a row, the row was right every time it was checked (under_chin, nose_length, the vault, a brow move
   rejected for a frown the target had). Your eye judges whether the face reads closer; the ruler says how much.
   **If the difference is something you can MEASURE** (a width, a height, how far a point stands forward in profile:
   the 23 measures of `gnm_controls(query="mm")`), measure it in mm on the sheet and use the `mm:` move: closing the
   8 largest of those gaps (in population sd) passed 30 / 42 pairs, more than the best 10 phrase moves (27 / 42).
   **3b. THE JOINT STEP FIRST: `block_in_solve(name, cameras="free" | "trust" | "refit")`**. ONE solve
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
   - CAMERAS. Each camera is under a PRIOR, never a clip: seven freedoms a view (shift x / y, scale,
     roll, yaw, pitch, DISTANCE), the prior on its WHOLE move since the block-in started, whatever the number of calls;
     only one round's step is limited. Every call begins with a cameras-first round (the head held, distance held).
     `"free"` (the default; cameras fitted by block_in_start): front +-3 mm, 4 % scale, 3 deg yaw, 6 deg pitch, 15 %
     distance (3/4: 8 deg yaw, 12 %; profile: 10 deg yaw, 8 %): wide on purpose, because block_in_start's fit is off by
     ~4.6 deg of front pitch and has no idea of the distance, and 5 deg of front pitch is 7 mm of jaw width. `"trust"`:
     a third of those widths (measured cameras, or carried from an accepted head). `"refit"`, first call only: cameras
     fitted on ANOTHER head are laid on this one first and that is the new start (the solve switches to it by itself
     when block_in_start carried or refitted them, and says so). Use one setting on every call. The reply has a CAMERA
     line per view (turn / pitch / distance at the call's start -> end, the whole move against its prior) and FAR FROM
     ITS START when a camera stands past 1.5 sd of it: check that picture's stated angle.
     DISTANCE is the one thing a picture does not say, and the reply has a DISTANCE line per front / 3-4 view.
     KNOWN LENS (`lens_mm` on the view = the 35 mm equivalent on the picture's DIAGONAL, f / diagonal x 43.27, the
     convention of EXIF and of every lens the reply prints; a head CROPPED from a larger photo: add `"frame": [w, h]`,
     the uncropped frame in the crop's pixels; or the file's EXIF FocalLengthIn35mmFilm x DigitalZoomRatio; a picture
     cropped after capture without a frame is refused with a warning, a resize is fine): block_in_start's fit stands
     at that lens and the solve holds the camera's distance to +-7 % of it on its whole move, with the dense landmarks
     too. On two scanned heads through the rig's cameras the distance then comes out to 1 % where the head's size is
     the class mean's, and off by the head's own size error otherwise (a head 6 % large: 7-9 % near): the size hold's
     +-5 % is in the distance. NO LENS: the start stands at
     a 70 mm portrait (a view flagged `"generated": true`: 105 mm, what our generated head shots behave like) and the
     distance is free under the prior above; the DISTANCE line says NOT KNOWN, what a 20 % error costs at that
     distance, and whether a side view is there to pin the face's depth. WHAT A DISTANCE ERROR COSTS (a 20 % error,
     mm of apparent width; geometry, `face_ruler.distance_cost`):
       camera at   nose vs the ears' plane   cheekbone width   jaw width   nose's own width
       0.3 m       x1.50                     4.0               2.4         0.3
       0.5 m       x1.28                     2.8               1.6         0.2
       1.0 m       x1.14                     1.6               0.9         0.1
       2.0 m       x1.07                     0.8               0.5         0.0
     So beyond ~1.5 m it hardly matters, and under 0.6 m (a phone at arm's length) the reply warns STRONG PERSPECTIVE:
     keep the original file with its EXIF, or retake from 1.5-2 m with 2-3x zoom. The nose's WIDTH does not depend on
     it (it lies near the eyes' plane): a wide nose is not a distance fault.
   - NOTHING IS FORCED, as a BOUND: no identity component may end past 3 sd. Components that would are HELD AT the
     bound and the rest solved again; no read is down-weighted for it and nothing is carried between calls (the old
     "INCONSISTENT PICTURES x<factor>" inflation is gone: one component at 3.11 sd used to cost every read x15). The
     reply says AT THE BOUND: <n> component(s) and DISAGREE: the read groups (type, picture) the solved head and cameras
     still miss by more than 2 of their own sigmas, with their mm: that read, that picture's camera, or a shape GNM does
     not reach. A group of reads the best head leaves scattered (a 20 px mouth's lip borders) still gets its own scatter
     as its sigma and is named (NOISIER than assumed).
   - WHICH DETECTOR READS WHAT (measured on photographs of scanned heads through the rig's cameras). `detector="mesh"` (the default): MediaPipe's face mesh as ABSOLUTE reads through a learned
     correspondence to GNM's surface, only the features it is good at: eye contours (0.9 mm front, 1.0 to ~35 deg),
     mouth corners (1.1), the lip seam (1.4) and the vermilion border (1.5), the nasal bridge; its points err together
     (a view's reads count as 16). NOT its nose wings / nostrils / tip (it draws a more average nose: alar width +2.4
     and +5.5 mm on the two scanned heads), not its face oval (a generic jaw: 4 mm), not its brows. These are ADDED to the
     differential anchors (dropping the anchors where the mesh is read cost a scanned head 1.7 mm of mouth width);
     `detector="anchors"` = the 68 differential anchors only. `dense="on"` adds our own dense landmark network (a pilot trained on our
     renders): on real faces it is a COARSE read (1.4-2.8 mm after its own placement, lids 2.1, chin 2.3: its sigmas
     say so now); it helps pose, large turns and a head with few outlines, it does not read fine features.
   - THE NOSE'S WIDTH is read from its WINGS (default): from a front or shallow 3/4 picture (under 25 deg)
     each ala's outer edge is an occluding contour of the model; the picture's steepest fall in brightness going outward
     from it (the groove's shadow beside the wing) is read against it, one read a side, its bias measured at the truth on
     five scanned heads (+0.3 mm). On three held-out scanned heads the solved alar width came from +1.1..+1.7 mm wide to
     +0.4..+0.7. Neither face detector reads it: both draw a more average, wider nose. The nostril openings
     (face_ruler.NOSTRIL) stay off (one head's validation).
   - HAIR OVER THE FACE'S EDGE (`hair_edge="on"`, the default). An outline is read only where the figure's edge is bare
     skin. With loose hair down both sides a front picture gives NO outline (the reply lists OUTLINE READS per view and
     warns NO OUTLINE for a view under 20): the face's widths there are GNM's average, not a measurement. Where the
     parser shows skin ending against HAIR, that boundary is read ONE-SIDED: the face reaches at least that far, so it
     pulls only where it lies outside the model.
   - A weak solve (under ~120 outline reads in all, or a view with none) is carried by the anchors and the prior:
     where nothing was read you get the class mean's face.
   - A head from the class mean (three studio photos): |c| 5.4 -> ~11, largest component under 2.7 sd, eyes 3/3, lip
     borders ~0.3 mm with no separate eye or lips step: about ten hand rounds' worth in minutes.
   - It does NOT see the surface inside the silhouette (cheek volume), the lid's fold, the nose's planes: hand steps
     for what you (or the user) see, after the solve. Two interior reads were built and FAILED validation on renders
     of known heads, so they are off: lambertian shading, and a learned normal estimator. Do not force a fold from a class-mean head (lid_read fold="crisp" cost |dc| 20 there;
     fold="none" = the opening only).
   - WHAT WAS READ, AND WHAT MOVED WITHOUT A READ (`solve_report`; in every reply). The solve's own
     posterior calls everything "read": ~600 reads pin GNM's 170 global components, and every measure is a function
     of those, so a cheek 30 mm inside every silhouette comes back with a tight error bar. That is the prior's
     correlations, not a measurement. The reply therefore uses a DIRECT read per measure (gnm_mm's 27, the chin set,
     the shape words): does any read LOOK at the measure's own points along the measure's own direction, if the
     surface were free to move locally (0 = nothing looks, 1 = pinned)? Three lists:
     `MOVED WITH NO READ` (left the start head by > 0.7 sd or 2 mm on a read under 0.25: an invention; check it by
     eye, or put it back with a `mm:` / macro step), `MOVED FAR ON A WEAK READ` (over 1.2 sd on a read under 0.6: a
     3/4's foreshortened depth through detector points; e.g. an eye depth from two paintings: read 0.52, moved 7.3
     mm, 4-5 mm of it wrong), `unread` (left near the start head's). Treat the first two as INFERRED when you
     report a head. The direct read is a heuristic about geometry: it does not know a read is biased.
   - THE CHIN AND JAW : a side
     view reads the chin's projection, height and the chin-lip groove (direct read 0.8-0.95). NOTHING reads the
     chin's own WIDTH or the jaw's lower edge between its angle and the chin from a front, a 23 deg and a 72 deg
     view: they end on the neck's skin, no silhouette (the jaw's width AT ITS ANGLES is read: the front outline runs
     down to them). Judge heads by SHAPE: every camera's scale is free, so a solved head's absolute
     size is not read (known heads come back 1-8 % large; compare after a similarity fit: ).
     What the "chinread" audit found on 8 known heads (dressed renders through a good photo set's cameras):
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
     leaving them free either. (4) On a good photo set a broad, square lower face from the solve is what outlines
     + GNM's population give (a jaw that IS wide at its angles: a narrower one leaves the front outline 2-6 mm inside
     the picture's); a rounded chin ball between marionette grooves is RELIEF inside the silhouette, which
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
     that one camera's angle and are INFERRED. The readers still go by the STATED kind (tried by camera: a "profile" at 67 deg
     became a second 3/4 and the solve fell apart).
   - Options, both OFF by default because their validation did not support them: `hold="auto"` holds every measure no read looks at at the start head's value (better on one
     known head, worse on the other); `expression="view" | "shared"` estimates each picture's expression (eight GNM
     prototypes: frown, brows raised, squint, lips pressed, corners down, smile, mouth left / right) as a nuisance
     on the interior reads: on known heads it did not lower the identity's error, and on neutral pictures it made
     it worse. When EVERY picture shows the same expression (a frown and squint in every picture), geometry cannot tell it
     from identity: the solve bakes it in. Say so when you report such a head.
   - On a loaded machine set OPENBLAS_NUM_THREADS=1 for scripts that call the solve: its many small solves stall
     in thread contention (0.3 s against 200 s for one call's down-weighting search with load 60).
   - JUDGE the result on the judging sheet (: reference | best: 50 % blend, the reference
     pictures projected as its skin, own dressing | the rest), not on a dressed render in an unrelated dressing:
     look at the blend before calling a feature wrong. Face-ID scores do not judge shape (they read the projected
     texture).
