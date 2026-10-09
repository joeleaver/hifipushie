# hifipushie notes: refstudy

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

## Reference modelling study (2026-10-08, "refstudy" agent, branch `worktree-agent-a0066266ffbf99948`)

Joe, after ~10 passes on Garrett: "we're not getting there ... figure out what works and what doesn't". A study on
heads whose 3D shape is KNOWN, then a prototype. Code: `spikes/refstudy/` (rs.py = GNM-frame fast lane: heads, numba
render, detector with depth, scoring by region; subjects.py = the truth set; calib.py = where the detector's 478
points land on GNM; fitlib.py = one least-squares fitter where every method is a choice of evidence / noise / prior;
table.py, exp2.py = the method tables; real.py <subject> [staged] = the REAL tools on one-mesh truth models;
mpdepth.py, macros.py, garrett.py, reads.py, pic.py). Scratch DURABLE in /mnt/data/hifipushie/refstudy/ (run.sh
<script>: capped, ONE BLAS thread; out/*.log, out/table.json, table2.json; truth/; calib.npz). Sheets
`workspace/human_renders/rs_*`.
- SET BLAS TO ONE THREAD under load: OPENBLAS_NUM_THREADS=1 made these fits 50x faster at load 110 (57 s -> 1 s);
  the package's default of 4 spins.
- Truth set: 6 GNM seeds (170 components, sigma 1, picked for big nose / square jaw / receding chin / long / broad /
  plain) + 4 MakeHuman-field heads (NOT in GNM's basis) + half seeds; pictures front / three-quarter / profile / other
  three-quarter, unknown pose, lens 50-85 (one 28), a squint + smile in 4 fronts, clay or tinted. Score = mean 3D
  vertex distance by region after a similarity alignment on the face; "profile" = fore-aft rms of the mid-line.
- Numbers (face mm, in-model S / out-of-model O; front + three-quarter): mean head 3.61 / 3.05; exact landmarks MAP
  1.16 / 2.04 (the out-of-model 2.0 face, 3.6-3.8 jaw is the identity basis's reach); the same clean points +-1.5 mm
  with today's weights 2.49 / 2.83, as a MAP 1.27 / 2.00; detector's 68 through the MP68 table, today's weights
  4.71 / 4.31; detector's 478 at calibrated places, MAP 2.50 / 2.41; + outline 3.40 / 2.95 (2.30 with the TRUE lens);
  + a per-picture expression solve 2.69 (worse, also on the pictures that have an expression); + a noisy character
  read 2.21 / 2.14 (jaw 4.16 -> 3.00, profile 2.59 -> 2.09); the read ALONE, no fit, 2.62; front picture only + read
  2.19 (= two pictures + read); front only = front + 3/4 = + the other 3/4 (2.48 / 2.50 / 2.47: a second detector
  view adds nothing); + a true profile with clicked points and its traced contour: profile 2.59 -> 1.87, chin 3.39
  -> 2.48, nose 2.67 -> 1.96; 21 clicked right-definition points +-1.5 mm in two views alone 2.18; detector + clicks +
  read 1.91; + clicked jaw line + profile 1.85 (profile 1.45); macros known exactly 1.66 (profile 1.27); the lens
  given or guessed 60 mm +-35%: 2.42 (points hardly see the lens). Jaw 1.8-4.2, cranium 4-10, ears 4-8, neck 7-14 mm
  in the BEST rows: no picture evidence reaches them.
- REAL tools on one-mesh truth models (4 subjects, likeness's own render, forced): fresh head 4.78 -> fit_views
  6.66 (2.9 sigma rms, INTEGRITY BROKEN) -> + fit_outline 6.83; staged checklist fit from fresh 4.5-4.8 (a no-op
  in 3D: its pins veto most stages; 16-26 min); humanfit_map 3.18 -> + read 2.96 (4-10 s, 0.4 sigma, sound).
- Causes, ranked: (1) point DEFINITIONS: MediaPipe's points read as GNM's 68 are 9-12 mm off on the jaw contour, 8 on
  the brows, 3 at nose / mouth (noise only 1-2.5 mm); it finds 1 profile in 36; (2) the PRIOR: today's weights trust
  a point to ~0.9 mm and let the identity go to ~10 sigma; GNM's components are in standard deviations, so 1 per
  sigma + honest point sigma is the conditional mean ("what the front predicts for the profile"); (3) under-constraint
  no weighting fixes; (4) outlines (nearest silhouette vertex) trade skull size against perspective: harmful without
  the lens; (5) MediaPipe's own depth is WORSE than the mean head's (z residual 2.6 vs 2.0 mm, correlation with a
  head's true depth deviations 0.10): dead. Licences: FLAME-based reconstructors (DECA / EMOCA / MICA; Pixel3DMM CC
  BY-NC; DenseMarks weights) are non-commercial; 3DDFA_V2's code is MIT, its BFM separate; Microsoft's dense
  landmarks (700 points with uncertainty + model prior, the design this converges on, as GNM's own paper describes)
  has no public code. Not checked: XR Blocks' MediaPipe <-> GNM table, TRELLIS as a skull prior, photo / EEVEE
  calibration (the table is from numba renders; it held on likeness's renderer).
- `humanmacro.py` (prototype, tests/test_humanmacro.py): 37 artist macros as MEASURES on GNM's head (jaw_square,
  jaw_width, jaw_angle, chin_projection / width / height / cleft, under_chin, nose_length / projection / width /
  upturn, bridge, brow_ridge, eye_depth / width / height / spacing / tilt, lips, cheek_fullness, forehead_slope,
  cranium, neck_width, ears, head_size) calibrated on 2500 sampled heads (`table()`, cached): each is near linear in
  the identity (r2 >= 0.975), its DIRECTION = the conditional mean (one unit = one population sigma; what goes with it
  moves too), `held=True` = the others held; `read(c | V)` (a head in sigmas), `apply`, `solve`, `prior_rows` (a read
  as evidence), `soundness`. All monotone and sound to +-2..6 sigma. WEAK (the space barely holds it: a shape op):
  chin_cleft (sd 0.22 mm). A head rebuilt from its 37 macros alone is 0.98 mm from itself (mean head 2.64): macros
  are a sufficient parameterisation (a macro-only fit = the 120-component MAP). What goes with what: eye_depth /
  bridge / brow_ridge r 0.9; nose_projection vs upturn -0.84; a square jaw brings cheek fullness (+0.44) and a full
  under-chin: say the negatives in a read ("under_chin": +0.8) or it reads as fat. The readout diagnoses heads:
  om_garrett v15 / v16 = face_width -2.6, nose_upturn -2.55 (hooked), nose_projection +2.6, chin_height +2.9 at 1.4
  sigma rms: a long narrow beak-nosed face, the opposite of "chunky, square jaw, cute nose".
- `humanfit_map.py` + `mp478_gnm.npz` (the calibrated table: per view class front / left / right, vertex triples +
  weights + scatter per MediaPipe point; 306 usable front, 131-148 turned): `fit(base, views, read=)`; MCP
  `human_reference(..., read=, method="map")` is the default now (`method="points"` = the old fit_views). A view with
  its image is detected again (its lm0..lm67 ignored); clicked named points +-1.5 mm; lens prior 70 mm +-40%; a turned
  view's side is taken from the picture, not from the hint's sign (Garrett's desk painting is stored as -45 and is
  the OTHER class: read as the wrong side it fitted at 12 mm and looked like "not one projection"; right, it fits at
  1.6 mm together with the photo); a view missing by > 5 mm rms is dropped from the identity and named.
- Garrett (models rs_garrett_map / _read / _read2 / _read3 from lk_garrett v1's fresh head; sheets
  rs_10_garrett_reference_vs_fits.png, rs_11_garrett_six_views_*.png): both references fit at 1.3 / 1.6 mm (pass 6 and
  v23: 2.9 / 2.5 on the same evidence) at 0.23-0.31 sigma. READ: the build and proportions are the photo's (broad
  lower face, short nose) in every view, but it is a SOFT, young, generic head: the posterior mean. Two blind readers:
  chunky 6/6 views, broad / square chin 4/4, snub nose in both profiles; soft jaw and weak chin in both profiles, flat
  brow, no cleft; "kept 21-22 of 62" against the stored reference read (pass 6: 35, v21: 33), though that reference
  mixes Joe's words with a reader's "long, gaunt, rugged". Not a likeness yet: it is the base the structure ops
  (jawline L, chin, brow ridge, hollow, hood, cleft) should be laid on, as small residuals AFTER the MAP.
- Found on the way: humanfit's integrity calls plain sigma-1 identities BROKEN at the lids ("x3.4 against the plain
  head") and so refused a correct MAP result on one truth subject; the guard's lid rule is too strict (onemesh2's).
- What to ask an image generator for: ONE neutral front picture, long lens, even light, + a TRUE profile (the only
  second view that pays: chin, nose, profile), hair off the forehead and ears; a three-quarter adds nothing to the
  detector. Then: ~20 clicks, a read with negatives, a traced jaw line.
- Stop doing: fitting the detector's 68 as GNM landmarks; outline warps without a known lens; a per-picture
  expression solve; local shape ops before the identity is settled; judging by mm tolerances of 1-2 mm on detector
  measures (the detector's own scatter is 1-2.5 mm front, 2-4.4 turned, on top of 3-12 mm of definition bias).
- Round 2 (same day, the coordinator's list; scripts exp3.py, clicks.py, garrett2.py, dbg_lids.py, dbg_chin.py):
  - "Why soft": restoring the norm does NOT sharpen. The fitted deviation x1.5: face 2.50 -> 2.37 (with a read 2.18
    -> 1.95 in-model, 2.22 -> 2.19 out); x2 no better than x1; x3 (the norm of a real head) 3.7 mm, worse than the
    mean; a draw from the posterior 2.76. So at most a mild x1.5; character has to come from evidence.
  - The CLICK TEST failed its promise: four fresh LLM readers clicking 21 named points on a gridded 2.5x crop (clay
    and tinted, two with an expression): median 1.6-2.6 mm, mean 2.1-3.7, worst 7-17; by point: mouth corners 1.0,
    eye corners 1.5-2.5, pupils 1.6, lips 1.5-2.5, nasion 3.8, nose tip 2.9, chin bottom 6.8, nostril wings 6-7 (their
    "outermost wing" is not GNM's lm 31 / 35). Front picture, face mm: detector MAP 2.51 | real clicks alone 3.29 |
    detector + clicks 2.40 | + read 2.06 | detector + read WITHOUT clicks 2.11. LLM clicks add nothing over the
    read; the "+-1.5 mm" rows above are a ceiling for a careful person with calibrated definitions, not for this.
  - Structure on the MAP head (Garrett; models rs_garrett_s1 = + pass 6's shape / pose, rs_garrett_s2 = + v22's;
    sheet rs_12_garrett_map_plus_structure.png, six views rs_13_*): pass 6's planes / hollow / hood / pushes give
    hooded lids and an older face but its pose frown and pushes read grumpy and heavy; v22's jawline L / chin / ears
    on this wider skull make a lumpy jowl with a notch. The evidence's residual rises 1.31 -> 1.8 -> 2.05 mm. Controls
    tuned on the narrow head do NOT transplant: structure must be refitted on the new skull, one op at a time. Not
    done (nor the truth-set "residual" row for the O subjects, nor 3 readers per head).
  - `humanfit.SLIVER` / `SLIVER_SQUEEZE` (integrity): a stretched edge counts when it ends >= 1.5 mm, a squeezed one
    when it was >= 1.1 mm, a folded face when its longest edge is >= 1.5 mm. Plain sigma-1 truth identities read
    "lids BROKEN x3.4" on 0.25 -> 0.9 mm lid edges (5 of 6 truth heads; now 1 of 6: S5, 40 lid faces folded). Side
    effect: the unforced 3 cm chin nudge is no longer refused (its refusal rested on those slivers; forced it is
    still BROKEN; test_humanfit changed to say so). Open: a size guard on nudge's correction layer.
  - `likeness_brief.reference_brief`: shots ordered and annotated with what each is worth to the fit (`worth`,
    `STUDY`): neutral long-lens front, TRUE profile, a read in words, three-quarter only for judging.
- Round 3, the point-placing test as a measurement (Joe: "what about testing how well the agent places the points
  itself"; clicks.py, clicks2.py, clicks3.py; pictures + answers in /mnt/data/hifipushie/refstudy/clicks/; placers =
  fresh sub-agents with a gridded crop and one sentence per point; 16 placer runs):
  - FRONT (4 pictures, 6 placements): placers agree with EACH OTHER to 0.35 mm (median sd between two placers on the
    same picture, max 1.7): the error is definition, not noise. Scatter about each point's bias 0.6-0.7 mm for inner
    eye corners, subnasale, nostril wings, mouth corners, lip seam; bias: wings 7 mm above GNM's lm 31 / 35, nasion
    and nose tip 3.3-3.6 mm low (no feature on the mid-line from the front), lip seam 2.3; the chin's lowest point
    6 +- 9 mm: not placeable. With the other pictures' per-point bias taken out a held-out picture's points are off by
    1.0-1.4 mm median. A zoomed refine round (21 tiles at 6x with a fine grid) does NOT help (median 2.2 -> 2.5 mm).
    And front clicks hardly matter to the fit even calibrated: detector 2.51 -> + placed (bias out) 2.42; with a read
    2.06 -> 1.99. DROP front clicks.
  - PROFILE (6 pictures, 9 points; the detector finds no profiles): eye corner 0.7, mouth corner 0.6, nose tip 1.2,
    subnasale 1.4, nasion 1.7, lower lip 2.1, lip seam 2.7, upper lip's red 4.4, chin bottom 6.4 (rms mm incl. bias).
    Fit, front detector + profile: 2.54 -> 2.31 face, mid-line profile 2.73 -> 2.06, nose 2.74 -> 1.94 with REAL
    clicks (bias out) = the simulated +-1.5 mm row (2.32 / 2.02 / 2.24); the CHIN does not improve (3.31 -> 3.55;
    simulated 2.51) because its point can't be placed: it needs the traced chin / jaw line (polylines by real placers:
    NOT tested). So "the view that pays" holds with real clicks for profile and nose; keep profile clicks, sized by
    `humanfit_map.CLICK_SIGMAS` (per point, front / profile, from these numbers).
  - Not tested: definition cards with diagrams as a separate arm, polylines, skinned / hair / stubble pictures,
    three-quarter views, tokens (a placer run is ~15 s and one picture).
- Open, in order: structure ops fitted as residuals after the MAP (what closes the out-of-model 3.6 mm jaw); clicks
  as a tool (a gridded crop + named points; an LLM clicking to +-1.5 mm is untested); measured macros from pictures
  instead of said ones (the ceiling: 1.66 mm); a GNM-space dense landmark detector trained on our own renders (exact
  definitions: 2.5 -> ~1.3 mm; a synthetic-data training job); photo calibration of the table; the read's sd per
  author; `humanfit_map` in fit_likeness's first stage.

## Reference modelling study 2 (2026-10-08/09, "refstudy2" agent, branch `worktree-agent-ae4b2050b31cc1395`)

Takes over from refstudy. Scripts `spikes/refstudy2/` (structure.py = the step driver: `mk <dst>` builds the steps of
steps.json ({dst: {src, patch of base.head, macros (identity, held), idscale}}), prints the evidence residual through
both references (this head's own best cameras, identity not free), integrity against src, plausibility, and writes
the six-view sheet; `rd <model>...` stores $D2/reads/<model>_<n>.json and prints the score table; score.py = the
readers' picks per descriptor against Joe's read (WANT x2 for his words, AVOID); sheet.py = the judging sheet
(reference | models, lit, his locks on each model's own scalp, six views under it; "om16" = a copy of om_garrett
v16); litrender.py, hairmesh.py (onemesh2's), t1.py). Scratch DURABLE /mnt/data/hifipushie/refstudy2/ (run.sh
<script>: capped, one BLAS thread; reader_prompt.txt + read_form.txt = what a blind reader gets; reads/; out/six_*).
The sandbox refuses JSON on the command line and heredocs: steps go in steps.json, scripts in files. Don't name a
script struct.py (it shadows the stdlib's).
- B, STRUCTURE ON THE MAP HEAD (Garrett; sheet human_renders/rs2_01_structure_on_map.png; models rs2_g0 = read3 with
  the deviation x1.5, ..., rs2_h = final). Blind reads: 3 fresh readers per head, six-view sheet + form only.
  - READER NOISE: the score of three readers swings about +-1.5 between heads that differ by a gentle op: planes 2.3
    alone +2.4, hood 1.75 mm +0.6, hollow 2.5 mm +2.0 against the base's +0.4, and all three TOGETHER -0.1. Gentle
    planes / hood / hollow are below what this protocol can see. Stable across all 18 of those reads: chunky 0.6-0.9,
    square jaw ~0, soft jaw 0.4-0.8, strong chin 0, weak chin 0.25, cleft 0. So only big steps were read after that.
  - Table (score; evidence residual front / desk mm; verdict):
    rs2_g0 base +0.43; 1.31 / 1.87 | planes 2.3 +2.44; +0.02 / +0.05; kept by eye (noise) | hood +0.64, hollow +2.01,
    all three -0.14: NOT kept (unproven; "heavy" rose 0.10 -> 0.48) | planes 2.6 (2 readers) +0.14: no | brow push
    2 mm, cheekbone push 2 mm: built, unread (usage limit), not kept | shape.jawline (corner 36 mm under the lobe, no
    tuck): REJECTED by eye: a jowl pouch with a crease in three-quarter and both profiles = rs_12's lump, residual
    unchanged, integrity ok (the checks can't see it) | shape.chin project 5 + under 8: REJECTED by eye: a button
    chin with a hook under it | NEW shape.lean 5 / 2 mm alone +1.14 (soft jaw 0.47, no lump) | + lean 7 / 3 + identity
    macros chin_projection +1.5, jaw_angle +2 (held) = rs2_e +3.25; 1.43 / 2.03: KEPT (square 0.28, soft 0.28) |
    macro nose_upturn +1: REJECTED, +0.30 mm front and a component past 2.6 sigma | + cleft (3 mm deep, 4 wide, lobes
    2) + brow_ridge +1 + nose_upturn +0.5 = rs2_g +5.70; 1.58 / 2.08: KEPT (square 0.53, soft 0.07, heavy brow 0.66,
    deep-set 0.63, rugged 0.34; cleft still 0.00, snub 0.36 -> 0.16 "broad blunt nose") | + cleft 4.5 / 5 / lobes 3 /
    20 long, chin_projection +0.75, nose_tip up 8 round 0.5 = rs2_h +7.80; 1.75 / 2.26: KEPT (square jaw 0.64, cleft
    0.22, strong chin 0.42, weak 0, soft 0.02, snub 0.30, chunky 0.87).
  - The rule "residual may rise 0.3 per step" let the SUM drift: +0.44 / +0.39 mm from g0 to h, two identity
    components past 2.6 sigma. h still fits the pictures better than pass 6 (2.88 / 2.5).
  - What was wrong in KIND: (1) bone as local Gaussian bumps (shape.chin.project, pushes): use the identity's HELD
    macro directions (humanmacro.apply(held=True)); (2) shape.jawline moves the jaw LINE down on a face whose soft
    tissue is full: the tissue goes with it as a pouch. On a wide skull the jaw reads when the tissue under the border
    is thinned: new `base.head.shape.lean` {under_jaw, jowl, submental, radius, smooth} (base._lean; border + chin
    held, bands measured from the jaw contour, moved along the normals, smoothed; base.VERSION 105); (3) the cleft
    was a 2.8 mm scratch: `chin.cleft_width` + `cleft_lobes` (two pads). Test
    test_humanfit::test_lean_thins_under_the_jaw_and_keeps_the_border. Guide: human_guide.md "Structure after a MAP fit".
  - BLUNT READ of rs2_h: every reader now says "square-jawed, broad chin, heavy brow, deep-set hooded eyes, rugged
    bruiser, stern scowl, grim downturned mouth", some "cleft". That is Joe's square jaw / cleft / chunky, but NOT
    "handsome" and not "cute nose" (readers: short broad fleshy nose). Beside the photo the head is too wide and
    round in the lower face and too heavy in the neck, the mouth's corners turn down (the photo's set mouth fitted
    into the identity: every read since g0 says "grim downturned mouth"), the brow strokes scowl, and the groom sits
    low on this head's forehead. The lit sheet has no eyeballs (the template mesh).
  - NOT DONE in B: no squint / frown pose render; hood / hollow / under-eye never proven either way; cheekbone, brow
    push unread; the mouth's downturn; nose (a "cute" nose costs evidence in the identity: the front picture's
    nostril points hold it); the face's width against the photo (the MAP + read made it broad because the read said
    so: read3's jaw_width +1, cheekbone_width +0.8, neck +1: try the read without widths).
- THE REFIT (the coordinator on rs2_01: "h is a bruiser, pass 6 too gaunt: the man is between"; sheet
  human_renders/rs2_02_refit_between.png = reference | pass 6 | rs2_h | rs2_m3 | rs2_m3 with the photo's pose | 50%
  blend, eyeballs in the lit tiles; garrett3.py measure / fit; models rs2_m0 (MAP) .. rs2_m3, rs2_m3_posed):
  - Widths from the PICTURE, two ways. (a) widths.py, the outline at a few levels as silhouette evidence in the fit
    (runs of edge pixels at nose base / mouth / jaw / neck, sigma 1.5-3 mm, lens unknown): WORSE on the truth set
    in every variant (face 2.48 -> 2.7-3.0 mm, jaw 4.1 -> 4.4-5.0, width macros worse): the nearest-silhouette-vertex
    row trades skull size against perspective, as the full outline did. Don't. (b) measured.py (item C): width MACROS
    regressed from scale-free features (detector points + outline widths over the interocular), given to the MAP as
    evidence with their own sigma: works (below). On Garrett's photo (mask = colour distance from the backdrop; only
    the levels 0.6 / 0.75 of eye line -> chin are usable: lower, the jacket's collar is the edge, so NO neck width;
    higher, ears and hair): jaw_width +1.7 +-0.8, chin_width +1.7 +-0.85, face_length +1.3 +-0.6, face_width +0.8,
    cheekbone +0.4. The "measuremodels" agent measured the same photo independently (rows against 300 GNM heads):
    lower jaw +2.1 sigma, jaw at the mouth +0.8, face length +0.6: wide LOW in the face, not wide all over. So the
    jaw's width was the picture's, the bruiser was the neck (+1 said), the brow, the scowl.
  - Read = shape words only (garrett3.SHAPE_READ: jaw_square, jaw_angle, chin_projection, under_chin, nose short /
    slightly up / straight bridge, brow_ridge 0, eye_depth 0); no widths, neck or cheek words.
  - Expression out of the identity: the MAP is fitted with the photo's squint / frown / set mouth as `head.pose`
    ({lid_upper 1.3 mm, brow_inner -1.5, brow_outer -1.2, smile -1.5}), the saved head is that identity without it.
    Fit 1.35 / 1.84 mm at 0.32 sigma; deviation x1.25.
  - Structure on it: planes 2.3 + lean 6 / 2.5, held macros chin_projection +1.2, jaw_angle +2, cleft 4 / 5 / lobes
    3 / 18 mm, nose_tip up 5 round 0.5. Residual SUM over the steps +0.09 / +0.17 mm (cap 0.3), 0.56 sigma, nothing
    past 2.6.
  - Reads (opus x3, same scale as the table): rs2_m3 +3.78, between g0 +0.43 and h +7.80 as asked: heavy brow 0.76
    -> 0.12, rugged 0.53 -> 0.12, square jaw 0.38, soft jaw 0.22, weak chin 0.20, cleft 0.15, chunky 0.84; still
    "stocky, thick-necked, full cheeks, stern mouth" from all three. (score.WANT still counts heavy brow / deep-set /
    rugged as wanted, from the old reference read: under "handsome" they should not; compare descriptors, not totals.)
  - Cheaper readers: haiku x3 on g0 / h / m3 = -0.21 / +1.92 / +1.43 (opus +0.43 / +7.80 / +3.78): the same ORDER
    but far fewer picks (no cleft, no chin, no nose descriptor from any haiku reader): too coarse for single ops.
    The model flag does NOT cut tokens: every sub-agent inherits ~315k of context whatever its model.
  - BLUNT: in the 50% blend rs2_m3's face lies inside the photo's (the photo's ears and hair stand outside it): it
    is not too wide. It still reads round, young and soft: big open eyes (base head `eyes` 1.05 + the lid-opening
    expression regions every Garrett copy carries), a smooth clay skin, a low hair cap on this forehead, a thick
    neck (unmeasurable in the photo: prior). The posed variant hardly differs from the neutral one. Not him yet.
- C, MEASURED MACROS (measured.py; 1200 sampled heads, one front render each with random pose / lens / light / look,
  a third with an expression; features: the detector's 478 points Procrustes-aligned on the irises, outline widths at
  17 levels over the interocular, luminance at the points over its mean; PCA + ridge per macro; logs
  $D2/out/measured_train.log, measured_truth.log; model $D2/measured_model.pkl):
  - Held-out rms in population sigmas (1 = knows nothing), points | + outline | + shading | all: mean 0.68 | 0.63 |
    0.56 | 0.53. Best: brow_height 0.26, bridge_height 0.32, brow_ridge 0.33, face_length 0.34, eye_depth 0.36,
    jaw_width 0.37, nose_length / width 0.38, lip_projection 0.39, chin_height 0.40, chin_width 0.44. SHADING is
    what gives the depth macros (bridge 0.57 -> 0.33, brow_ridge 0.62 -> 0.35, eye_depth 0.61 -> 0.36, nose
    projection 0.69 -> 0.47); the OUTLINE gives neck 0.84 -> 0.50, ear_out 0.90 -> 0.51, jaw_width 0.52 -> 0.41.
    A picture cannot measure (> 0.7): jaw_angle, jaw_square 0.68, forehead_slope, bridge_hump, ear_size, chin_cleft
    0.94; weak: chin_projection 0.59, nose_upturn 0.62, under_chin 0.59 (profile things: a read or a profile).
  - On the 10 truth heads (never seen; extreme by design, sd 1.27): measured 0.80 mean, the MAP fit's own macros
    1.05, a simulated said read 0.96. The said read still wins on chin_width, nose_upturn, eye_spacing, nose_width.
  - Fit rows, front picture only, face mm S / O: detector MAP 2.48 / 2.51; + said read 2.17 / 2.11; + MEASURED macros
    1.94 / 2.15 (profile 2.51 -> 1.49, chin 3.44 -> 2.33, nose 2.61 -> 1.72 in-model); + measured (sigma x2) + said
    2.05 / 2.06; exact macros 1.64 / 2.13. So measured macros replace a said read in-model and equal it out-of-model;
    together they add little.
  - CAVEAT: the shading features know only our render's shader (random light, clay or tinted skin): on a photo
    (stubble, hair, real light) they are untested and NOT used on Garrett; the outline features need a mask and
    levels free of ears, hair and collar. Not wired into humanfit_map (a script): the next step is `human_reference`
    measuring width macros itself when a view has a plain backdrop.
- D so far: `humanfit.nudge` size guards (NUDGE_CORR 0.35 x radius for the correction bump, NUDGE_MAX 12 mm for the
  move, unless forced; the 3 cm chin nudge is refused again: the sliders alone took 24.5 mm of it inside 2.6 sigma).
  XR Blocks' MediaPipe <-> GNM correspondence (xr_compare.py; google/xrblocks FaceCorrespondence.js, Apache-2.0, 473
  points, 166 flagged skull-fixed) against our front table: 301 of our 306 usable points are in it; their GNM vertex
  vs our calibrated surface point: median 1.6 mm (1.8 on the skull-fixed ones), p90 3.7; ours sit 0.9 mm higher and
  0.7 mm further forward on average; disagreements > 6 mm: the irises (mp468-476: they use the corneal apex, we the
  iris on the eyeball), mp206 / mp426 (57 mm: mirrored left / right in one of the tables: CHECK before trusting those
  two), a few lid points. Their own note matches ours: points sit ~0.7 mm off vertices and slide in turned views.
- ROUND 3 (the coordinator on rs2_02: "the right skeleton of the answer; we compare smooth clay with a textured
  photo of a 50-year-old"; garrett4.py; models rs2_n0 / rs2_n3 / rs2_n4; sheets human_renders/rs2_03_projection_test.png
  (pass 6 | rs2_h | rs2_m3), rs2_04_projection_n4.png):
  - THE PROJECTION TEST (`likeness_read.project_reference`, MCP `project_reference`, proj.py): the reference photo
    projected onto the head through its fitted camera as an unlit texture, seen from the six views (source visibility
    by the source camera's depth + a grazing cut; unseen skin = dim clay). Wearing the photo, rs2_m3 and rs2_h read as
    the man in front, the other three-quarter and low angle, and stay a plausible same man turned to the desk view
    and in profile; on pass 6 the photo's ears and hair edge land on the cheeks (the face too narrow). So the
    clay's "young, round, soft" was mostly the clay. No test yet (it is a render path): add one on a synthetic head.
  - Eyes: `eyes` 1.0, the lid-opening expression regions at HALF. With them out and the squint posed, fit_hood said
    "the picture's upper lids are HIGHER than the hood-free face's" (-7.5 mm asked; at half -4.1): GNM's lids rest
    low and the stored 68 lid points are the detector's (definition bias): NO hood from fit_hood on this head. brow
    height measured on the photo -0.86 +-0.47 (low), in the MAP (got -0.34); eye_depth is only measurable with
    shading (0.36), points alone 0.61: not usable on a photo.
  - Neck: humanfit's neck_circ is read on the BODY's neck (body + bridge vertices): 31.9 cm on every Garrett copy
    whatever the identity does. The head's own neck_width macro was +0.25 on the refit (the bruiser's read had asked
    +1): set to 0. The "thick neck" every reader still says is the body's 31.9 cm neck under a bald clay head.
  - Age: headfit._body_axes()[:, 1] (MakeHuman's age move in GNM's components) is an ORTHONORMAL direction: x1 of it
    moves no macro by more than 0.1 sigma; as applied (x0.8 + lip_fullness -0.5 + hollow 2 mm / 30 mm radius) it is
    close to nothing. A real age control needs the field's own magnitude (headfit.shape_delta(age) through
    head_fields) or soft-tissue ops (nasolabial fold, pre-jowl sulcus, upper-lid skin): NOT built.
  - Reads of rs2_n4 (opus x3): all three say age ~50 (45-55) and "handsome / regular: no" ("dour, heavy-lidded,
    grim downturned mouth, thick neck, big domed skull"); score +1.97 (m3 +3.78: square jaw 0.38 -> 0.17, soft jaw
    0.22 -> 0.51; inside the +-1.5 reader noise or the price of smaller heavy-lidded eyes; not separated).
- HANDOVER (refstudy2, context full, 2026-10-09). Branch worktree-agent-ae4b2050b31cc1395. Tests: see
  $D2/out/tests.log (tests.sh runs test_humanmacro / test_humanfit / test_likeness through run.sh). Best head so far by
  the coordinator's eye: rs2_m3 (workspace; refs + cameras in its human_refs.json); rs2_n4 = the eyes / neck variant.
  To rebuild: garrett3.py measure, fit (-> rs2_m0), structure.py mk rs2_m1 rs2_m2 rs2_m3; garrett4.py (-> rs2_n*).
  Open, in the coordinator's order: (1) the grim downturned mouth and scowl still in every read although the fit is
  made with a pose: the pose is set by hand (pass 6's numbers): solve it from the detector's blendshapes, or lift
  the mouth corners in the neutral head; (2) age as real ops (above); (3) the FAIR render: skinned (garrett_v20's
  skin spec), strand hair or locks, soft frontal light, through the fitted cameras; the lit sheet's hair cap sits low
  on these foreheads (the groom was made on v23's head); (4) measured macros into human_reference behind a flag
  ("renders only" for the shading features; the outline needs a plain backdrop and collar-free levels); (5) mp206 /
  mp426, 57 mm apart from XR Blocks' table: render a truth head, see which side the detector's 206 / 426 land (a
  left / right swap in OUR table would be a real bug); (6) A2 (traced polylines by real placers), skinned / EEVEE
  calibration of the 478 table; (7) score.py's WANT still rewards heavy brow / deep-set / rugged.

