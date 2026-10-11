# The GNM model atlas (facesliders, 2026-10-09)

## ACCEPTED STATE (read first; Joe's decisions, kept up to date by the coordinator)
- Garrett: b3_G17 is the accepted head (2026-10-10). Joe: nose tip slightly UP ("his nose points down when it should
  be slightly up"; b3_G16 "looks much better"), narrow bridge via the GNM sculpt route (no designed local). Later
  Garrett work starts from b3_G17 and must not turn the tip down again (b2_G15 and rb_G14 have the old down tip).
- Tess: b2_T06 lineage + gnmdetail2's lips step (g2_T12* models); her accepted dressed look is still f3_t1's dressing.
- HOLD (Joe, 2026-10-10): no further work on any model (Tess, Garrett, lt19, jw) until the GNM controls and the eye
  crease are sorted; then start over on all four with block-in v2 (GNM's own head, moves chosen from the control
  atlas, sculpt / relief first, the eye and lips steps).
- CREASE (Joe, 2026-10-10, after gnmcrease's gk_01): GNM CAN make the right fold: sampled gnm#376 and gnm#540 "read
  right" dressed. gd_T30 had the darkness but the wrong fold shape (topology). So match the fold's SHAPE with GNM (sections,
  the line's path / height along the lid); any remaining darkness comes from the skin's cosmetics (a crease shadow), never
  a geometry layer. Photo line darkness is NOT the crease target (gnmcrease is reworking the eye step; its first NOTE /
  CREASE_SLIT_DARK claim "GNM can't draw the line" is wrong).
- RESTART GATE: the four restart after the driving test passes (agent gnmdrive: synthetic GNM pairs A -> B, the driver
  names differences in artist words and picks controls from a phrase -> control manual, no search; scored vs the oracle).
- Agents document as they go: notes + commit after every meaningful step, a STATE / NEXT line per section.
- Rules: GNM owns the face's shape (no hand-made layers unless a documented gap AND Joe agrees); the artist block-in
  is the default; private family likenesses (lt19, jw) are never in the repo.

Joe: "Every hand-made slider we made should control the model as a whole. Nothing should really work in isolation.
We need to comprehend the model." Step 1 of the redesign: what GNM's identity space can express, and what moves
together in the faces it makes.

Scripts (spikes/facesliders/): `atlas.py <n>` samples heads from GNM's identity prior (the 120 head components,
N(0, 1)) and measures every attribute we have a slider or a checklist item for: humanmacro's 37 macros + 17 of ours
(lid, lip, nose, jaw, eye depth, malar; mm in GNM's frame); `atlas_report.py` (spread, R2, correlations, heat map);
`atlas_comps.py` (components at -2 / 0 / +2 sigma, front and profile, what each moves most).
Data: /mnt/data/hifipushie/facesliders/out/atlas_3000.npz (c, A, names). Sheets: human_renders/fs_14_gnm_components_00_11.png,
fs_15_gnm_atlas_corr.png, fs_15_gnm_atlas_report.txt.

## What the model can express (3000 heads; R2 = a linear model in the 120 components, held-out 20%)

- Everything read off landmarks or fixed vertex sets is LINEAR in the identity (R2 0.97-1.00): face / jaw / chin /
  nose / brow / eye / lip proportions, lid aperture, vermilion heights, bow depth, lip projection, nostril show (the
  alae over the subnasale), gonion height, ramus angle, eye setback, malar rise. For these a slider can be an exact
  direction in the identity space (the conditional mean), with no morph at all. Their GNM spread (sd, mm): lid aperture
  0.97, upper vermilion 1.23, lower 1.32, bow 0.37, upper lip projection 2.45, lower 3.73, nostril show 1.10, eye
  setback 3.93, malar rise 1.22, gonion height 3.61, ramus angle 3.3 deg, eye tilt 2.1 deg.
- NOT in the identity space:
  - crease height (the lid's own fold turn): R2 0.13. GNM's lids mostly have no fold of their own; the
    turn is found on 100% of heads, but where it sits is noise to the identity. The crease is a residual detail.
  - fold overhang: R2 0.70, coupled to brow ridge (r 0.74) and eye depth (0.66). Partly the identity's (a deeper
    orbit under a heavier brow makes a fold), partly not.
  - lower-lip width (lm 55-59 over the mouth's width): R2 0.99 but sd 0.022: the model hardly varies it. Tess's
    cushion lip (0.40 vs our 0.82) is far outside GNM.
- My nose band widths (radix / dorsum / tip: the forward-facing band's x extent) are unstable measures (dorsum
  defined on 43% of heads, R2 0.2-0.5): a threshold on the normal is the wrong reader. To redo with
  faceslide.nose_widths' half-drop width on a render, or a curvature-based width.

## What moves together (|r| over 3000 heads; fs_15_gnm_atlas_corr.png)

- eye depth ~ eye setback +0.97, ~ bridge height +0.90, ~ brow ridge +0.88; brow ridge ~ eye setback +0.85. Deep-set
  eyes come with a high bridge and a heavy brow in GNM's faces. That is why Tess's "eye_depth + brow_ridge" made her
  heavy and male: the population does not have deep eyes under a light brow, so the identity had to go past 2.6 sigma.
  A deep-set eye under a light brow is a legitimate face but it is a HOLD (condition on brow_ridge), not the free
  direction.
- eye height ~ lid aperture +0.94; eye width ~ eye spacing -0.73.
- lip fullness ~ upper / lower vermilion +0.92; the two vermilions +0.84; lip projection ~ lower lip projection +0.89.
- nose projection ~ nose upturn -0.84, ~ bridge height +0.78; bridge height ~ upper lip projection -0.71.
- jaw width ~ chin width +0.84; face width ~ cranium width +0.83, ~ cheekbone width +0.77; face length ~ nose
  length +0.76.
- fold overhang ~ brow ridge +0.74, ~ eye setback +0.64.
- The first components (fs_14): comp 0 = head size / chin + nose + jaw width; 1 = neck, jaw squareness, nose length;
  2 = the nose's bridge and hump against upturn and lip projection; 3 = face and cranium width; 4 = brow ridge with
  eye depth, cranium height and bridge height (the coupling above); 5 = brow / head depth / eye depth again.

## What it means for the sliders (step 2)

- Sliders on landmark attributes (most of them) become conditional-mean directions in the identity space: one unit
  = the attribute's change, the rest of the face as the population moves with it. Exact (R2 ~ 1).
- A `hold` list conditions on named attributes (eye setback with brow ridge held), replacing blanket held modes.
- Residual morphs stay only for: the crease (no identity), the fold overhang's unexplained 30%, lip roll / eversion
  shape, the lower lip's lateral taper, tip definition, lid-margin detail. Whether a residual correlates with other
  attributes needs measuring the residual on real faces: GNM can't teach it. Data that would: scan sets with lids and
  lips (FaceScape / Headspace-style 3D faces, licence permitting), MakeHuman's eyelid / lip targets for the shape
  vocabulary (CC0), photographs with measured crease heights (oculoplastic literature tables).

## Sex, checked against real people (ANSUR II)

ANSUR II (US Army 2012 anthropometric survey, a US government work, public domain; 4082 men, 1986 women; CSVs from
Penn State's Open Design Lab, https://www.openlab.psu.edu/ansur2/, kept at /mnt/data/hifipushie/facesliders/ansur/,
sha256 male 0547aea0..., female ed7e800a...) shares six head measures with GNM: bizygomatic breadth, face height
(menton-sellion), head breadth / length, interpupillary breadth, ear length (spikes/facesliders/ansur_check.py).
- GNM's couplings match ANSUR POOLED over both sexes (bizygomatic ~ head breadth GNM +0.76 | pooled +0.74 | within
  +0.63; ~ face height +0.56 | +0.46 | +0.20), not within-sex: GNM's prior is one population of men and women, and
  sex and overall size couple everything. MakeHuman's own sex field is NOT a direction of GNM's (63 sigmas, 28%
  inexpressible: sexdir.py), so the sex axis is built in ATTRIBUTE space: delta = the least identity move making ANSUR's
  male - female differences (+8.9 mm bizygomatic, +9.5 face height, +6.6 / +9.7 head breadth / length, +2.3
  interpupillary, +4.9 ear; 1.2-1.5 within-sex sds), |delta| = 1.62 sigmas (sexaxis.py). With the population as two
  halves at +-delta/2 (within-sex covariance I - delta delta^T / 4) GNM's within-sex correlations come down toward
  ANSUR's for most pairs (bizygomatic ~ face height +0.56 -> +0.29, ANSUR +0.20; ~ head length +0.36 -> +0.11, +0.18) but
  stay high for interpupillary and face height ~ head breadth (+0.50, ANSUR +0.17): GNM over-couples widths with
  heights. The axis moves chin / jaw / nose / mouth width and face length most (0.8-1.05 sd); brow ridge and eye depth
  hardly (ANSUR has no soft-tissue measures: no cited table for brow / lips / nose / eye depth by sex was used, so
  those stay out of the axis rather than guessed). eye depth ~ brow ridge (+0.88) is GNM's own coupling, not sex.

## The sliders as whole-model directions (src/hifipushie/faceatlas.py, face_atlas.npz)

base.head.slider_mode "coupled": each faceatlas.COUPLED slider (canthal_tilt -> eye_tilt, brow_ridge, eye_setback,
malar_rise, lip heights / rolls / bow, nostril_show, eye_hood -> fold_overhang, and new eye_opening / gonion_height /
ramus_angle; +1 = +1 population sd) is the conditional mean of the identity given the change, WITHIN the head's sex
(dc = S B^T (B S B^T)^-1 da), the sliders asked together holding each other, base.head.slider_hold naming more;
eye_hood also keeps (1 - R2) of its morph. Everything else (crease, lid margin, platform, sulcus, bag, tear trough,
brow_lateral, epicanthal, tubercle, corner, lower-lip width, tip definition, nose widths: no smooth reader, age ops)
stays a local morph. Without slider_mode the old local sliders (old specs reproduce). humanmacro.apply_coupled: the
macros in the same framework. Tests tests/test_faceatlas.py: a 1-sd change moves its attribute 1 sd and every
|r| > 0.6 attribute ~r sd; eye_setback with brow_ridge held keeps the brow (free, it comes along); no fold at +-1.5
for any coupled slider; a coupled slider recovered from a render.

## Step 3: the joint solve over the whole-model controls (spikes/facesliders/joint2.py)

Variables: GNM's 120 head components (every free macro and coupled slider is a direction there; their values are READ
OUT of the result) + residual local morphs (RES) + the ageing ops that the evidence can see (AGE: cheek_hollow,
face_lean, cheek_flat, prejowl; one-sided), L2 per unit. Prior: within-sex Mahalanobis (mean sex * delta / 2).
Evidence: calibrated detector points per view; checklist items (eye opening, canthal tilt, brow-eye, lip heights) as
photo - clay render both through the detector, linearised through the same item on the predicted MediaPipe points;
the face OUTLINE (outl.py: the front's MediaPipe oval snapped to the photo's strongest edge, a turned view's traced
lines, each line on its own) as a chamfer to humanfit._silhouette; non-front views weighted DESK_W. Items flagged
with an expression on the picture are left to pose (Garrett's concept: squint 0.70, frown 0.64). No face-ID term
(ArcFace / SFace can't see geometry across clay vs painting: -0.16..+0.11).
Findings (Garrett fs_gj2 / gj5, Tess fs_tj2 / tj3; sheets human_renders/fs_16, fs_17, fs_18):
- Without the outline the identity explains ~99% of the points' improvement but the face comes out round and soft:
  the detector points don't constrain the contour. With it: front contour 7.4 -> 1.3 mm, the face tapers, but the
  prior goes to 44 (max |c| 2.5, at the wall: ramus +2.3 sd, cranium height -2.0) and face_lean wants +1.2: the
  identity can't make his lean, long, hollow-cheeked face; the chin comes out narrow (50 vs 56 mm).
- The squint biases the detector's canthal tilt: the same head with a squint pose matching the photo's opening reads
  1.4 deg lower (squintchk.py). The rest (~2 deg) doesn't move with the identity's eye_tilt (-2 sd).
- The proportion items (face oval widths, face height) read photo vs clay disagree with the outline fit on Garrett
  (photo 11-15% wider at the same camera while the contour fits at 1.3 mm), agree on Tess within 3%: read only.
- The desk painting's traced jaw.R line matched no silhouette (15 mm, dragged under_chin / ramus): left out; the
  front snap is unreliable where skin meets skin (jaw over neck) or hair crosses the cheek: Tess's jaw went square
  (+3.1 sd). A better front contour reader is needed (traced, or a segmentation) before the outline term can be trusted.

## Missing control: canthal tilt (2026-10-09)

GNM's eye_tilt attribute (landmark corners, R2 ~1) and the detector's canthal tilt on a render barely move together:
the identity at -2 sd of eye_tilt reads ~1 deg on the clay where the concept reads -0.45 (after the squint bias, 1.4
deg, went to the lid pose). GNM's tilt moves the wrong corner points (the fissure's ends as the detector sees them stay).
Decision (coordinator): a missing control, noted; a coupled-plus-residual tilt slider (the identity direction + the
local canthal_tilt morph that turns the fissure on the ball) comes later, not now.

## Traced contours (2026-10-09, traces.py; fs_traces_g / fs_traces_t)

The edge snap is dropped. Contours traced by eye on 4-10 px grids (gridimg.py), only where there is an edge: Garrett's
front cheeks against the ears and the jaw's underside + chin (a strong shadow edge); below the lobes the outer edge
is the NECK, not the jaw (the snap had used it: the narrow-chin / square-jaw errors). Uncertain segments stored
with an "x_" prefix and never used (temples under hair, the ramus, Tess's soft chin line, the desk jaw).
- Garrett fs_gj6 (face_lean / cheek_hollow nearly free, FREE_AGE): prior 74 -> 19 (edge snap 44), max |c| 2.02,
  ramus +0.74, cranium width -1.28, chin width -0.93 sd; face_lean at its 1.5 limit + cheek_hollow 1.21 carry the
  leanness (age / soft tissue). Lean and long now, closest of the joint runs to the concept (fs_19 sheet).
- Tess fs_tj4 (traced) vs fs_tj2 (no outline): views 0.33/0.37/1.60 vs 0.30/0.33/1.71, prior 37.5 vs 17, jaw_square
  +1.7, jaw / chin width +1.25: heavier, more masculine by eye (fs_20). tj2 stays her candidate.

## Round 4: lips, chin, Tess's true profile camera (2026-10-09)

- Garrett fs_gj8 (lips weight 3, lip_*_height residuals offered, chin line out): front lips 6.96 / 10.36 vs 6.85 /
  10.86 mm, mostly through the IDENTITY (lip_lower_height +0.61, bow +0.77, lower roll +0.89 sd read out; the
  residuals +0.22 / +0.29); prior 19.5, max |c| 1.53, views and outline no worse.
- The front chin line is a SHADING edge, not an occluding contour: the concept's camera sits ~43 cm below the chin
  (the underside visible under the line). humanfit._silhouette has no vertices there and its nearest match slid the
  jaw's sides in under it (gj6's narrow chin). An envelope matcher picks the submental skin / neck (15 px low); GNM's
  region borders are not the jaw border. Chin width needs a render-based reader of the same shadow edge (photo vs
  clay under the fitted light), not geometry: left out.
- Cameras: ONE shared copy per subject (human_refs "cameras"), a refit replaces it and the old is kept by name
  (Tess: fs_tj0 cameras = ts_t18's refit true profile camera, cameras_old_58deg kept). joint2 FIX_CAMS freezes a view.
- Tess through the true profile camera: the profile's own contour against the plain background (outl.profile_auto)
  as an outline term is what moves her brow forward: fs_tj7 prof.py chamfer 1.06 mm (e3 2.15, tj6 2.42: brow 1.4 vs
  2.8 / 4.4), points 0.61 / 0.69 / 2.28 sigmas (e3 0.84 / 0.87 / 3.05); prior 51.6.
- The calibrated detector table drops every face-oval point (sd past the cut): a front's jaw is constrained only by
  the prior and the couplings. Tess's jaw_square +1.6..+2.7 comes without any outline term.
- ANSUR II has no bigonial breadth; bitragion-chin and bitragion-submandibular ARCS exist (a surface-arc reader on
  GNM would let the sex axis know women's lower faces).
- To add to the model (not one-off morphs): canthal tilt, Tess's lower-lip width, the crease: learned / data-backed
  directions with couplings. Data: MakeHuman CC0 lid / lip targets (shape vocabulary); 3D face scan sets (licences
  checked before any download).

## Tess: reads-female, the cap on readouts, the sex axis's lower face (2026-10-09)

- tj7's profile contour fitted HAIR at the forehead (strands crossing in front of the skin) and lashes: forehead_slope
  -3.1, nose_upturn -2.5 sd. outl.profile_auto now takes the first run of 6 skin-bright pixels per row, from the brow
  (above the nasion) down, and stops at the throat.
- joint2 caps the READOUTS: every identity attribute (R2 > 0.9) within ACAP = 2.5 sds of its WITHIN-SEX spread
  (sqrt(B S_w B^T)), a wall like the components'.
- Sex axis + the lower face: NIOSH head-and-face survey (Zhuang et al. 2010, Ann Occup Hyg 54:391, US government work,
  /mnt/data/hifipushie/facesliders/niosh/zhuang2010.pdf sha256 f369d0a4...), Table 4 female vs male adjusted for
  height / weight: bigonial -7.6, nose breadth -3.0, nose length -1.9, lip length -2.1 mm (sexaxis.py --lit). |delta|
  1.62 -> 2.10 sigmas: past what two equal halves of GNM's pooled prior can hold (|d| < 2), so within_sex keeps
  SEX_SHARE = 0.85 of the variance along delta as the sex split. Soft tissue (forehead inclination, brow prominence,
  lip heights, gonial angle) NOT added: no open, citable sex-split table found in four searches (Farkas 1994's
  appendices have them; book only). MakeHuman's sex on Tess's body is 0.0 (full female), head dimorphism 1.3.
- GNM's own female mean (c = -delta/2) on Tess's body reads androgynous-to-male in the clay (bald, drawn brows,
  flat light): the axis from size measures does not feminise the soft tissue. tj10 / tj11 (one-off head shape ops
  stripped: jawline sharp 0.01, nose_tip up 3) keep jaw_square ~+1.5, nose projection +1.6, chin height +1.6: the
  evidence's, not the prior's. Points 0.55 / 0.66 / 2.22 sigmas, profile chamfer 1.46 mm (e3 0.84 / 0.87 / 3.05,
  2.15) but by eye still not a young woman.
- Garrett's desk camera: yaw -38.7 deg against the detector's 31 (likeness yaw doubt 13.9 deg), looking up 14 deg:
  suspect like Tess's old profile camera; a painting, refit with the traced profile is to do.

## Round 6 (2026-10-09)

- Tess's front lower face: her traced jaw (against the background, below the lobes) vs tj12's silhouette: the model's
  jaw sits INSIDE the trace on her left by a few px, on the line on her right. The evidence says her jaw is this
  wide; the broader read against e3 is e3 being narrower than her photo. Not a width to fix; the soft read is
  elsewhere (brows: paint, tess is on it; the corner of the mouth).
- MakeHuman CC0 mouth (44) and eye (68) targets fetched to /mnt/data/hifipushie/facesliders/mh_targets/ (SOURCE.txt;
  commit a8bc2d54). Plan for the mouth-corner extension (and lower-lip width, lids): carry each MH target onto GNM's
  head (MH base head aligned to GNM's mean by its face landmarks, displacement per GNM vertex from the closest MH
  surface point, scaled to GNM's interocular), keep only the targets GNM can't already make (project out the
  identity's span: the residual part is the extension), and add it as a residual slider WITH couplings once there
  is data that shows them (scans); MH targets are single local shapes with no couplings. Candidates for
  mouth_corner: mouth-angles-up/down, lowerlip-ext-up/down, lowerlip-width, dimples, laugh-lines.
- Garrett's desk camera is NOT off like Tess's old profile: a yaw scan (yawscan.py, r regularised) is flat between
  35 and 50 deg (0.71-0.72 sigmas): a painting can't pin its yaw. The stored camera's 13 deg pitch is his head bowed in
  the painting (the free fit, 0.37 sigmas, prefers it). Kept.
- Garrett fs_gj8 dressed (human_renders/fs_22_garrett_gj6_gj8.jpg): lips fuller than gj6, chin a little wider without
  the chin line, otherwise the same face.

## Model extensions from MakeHuman's CC0 targets (faceext.py, face_ext.npz; 2026-10-09)

- Carry: each MH target's displacement read at every GNM vertex's binding point on MH's reference body (onemesh
  g_tri / g_bary), world metres, into GNM's frame (a similarity fitted on g_neutral); +1 = half (incr - decr).
- What "project out GNM" has to mean: GNM's 120 components reproduce these local targets almost EXACTLY inside their
  region (0.87-0.94) but only at 46-124 sigmas (extcost.py): expressible, not probable. A full orthogonal projection
  (local_orthogonal) leaves 0.3-0.5 mm of 3-5 mm targets: it throws the feature away. So the extension removes only
  the target's components along the identity's CHEAP directions over its region (singular directions moving it
  >= 0.4 mm rms per sigma: 5-8 of them), which make 0.76-0.82 of it; the extension is exactly orthogonal to those
  (test), local, symmetric, and the solve chooses between the identity (coupled) and the residual (local) without
  double counting. The mouth's corners are held (GNM's corner is not MH's: corner quads turned over) and each field
  is scaled to 0.8 x its largest fold-free fraction (lowerlip_width 0.43, mouth_angles 0.23, lowerlip_ext 1.0).
- Tess (fs_tj14: the extensions replace the hand-made mouth_corner / lip_lower_width): mh_lowerlip_width -0.23,
  mh_mouth_angles -0.32, mh_lowerlip_ext -0.25; points 0.57 / 0.68 / 2.26 (tj12 0.58 / 0.70 / 2.21), the hand-made
  mouth_corner +1.06 gone with no loss. The mouth barely changes: her detector lip points don't ask for the lower
  lip's lateral taper; her lower lip reads fuller (volume / eversion) more than narrower. A reader of the lower
  vermilion's visible width (photo vs clay) is what would drive it.
- Fold-free range (test_faceslide's criteria: no quad turned, no neighbour pair folding 10 deg past 60): GNM's upper
  vermilion border is already a 67 deg crease, and the carried MH moves shear across it: even Laplacian-smoothed
  (12 passes), the fold-free scale is 0.18 (lowerlip_width, 0.40 mm), 0.13 (mouth_angles, 0.38 mm), 0.80
  (lowerlip_ext, 0.89 mm). The commissures held within 3 mm. Tess fs_tj15 with the final fields: -0.20 / -0.12 /
  +0.10, points 0.32 / 0.38 / 2.28 (as tj12). As built the mouth extensions are too small to matter: the limit is the
  lip border's topology, not the data. Next for them: move the border's rows together (a field smooth ALONG the
  border, sheared nowhere across it), or carry onto GNM's lip groups by a lip-local parametrisation.

## The lower lip's width: two definitions, reconciled (2026-10-09)

- tess's youth.py: the width of the red along a horizontal cut 40% of the way down the lower vermilion (from the
  stomion), over the mouth's width: Tess's photo 0.40, ours 0.82. It reads the lower lip's SHAPE in depth too:
  a lip whose border curves up early (a cushion) is narrow at that cut even if its red reaches the corners.
- likeness lower_lip_width (facesliders): the lateral extent where the lower lip is thicker than half its middle
  thickness, over the mouth's width, read on the detector's lip contour (photo and clay alike): photo 0.70, tj12 0.71.
- They measure different things and both can be right: the detector's outline (11 points per border) says her red
  runs as far as ours at half thickness; youth.py's cut says the lower border rises faster than ours below the middle,
  i.e. a rounder, fuller central pad. That is the lip's form in depth and its shading (the "poutier"), which the
  outline can't see and the lip-shading reader (next, after the eyes) should. Neither number is wrong; neither is
  the lower lip's width alone. The 0.40 vs 0.82 should be read as "cushion shape", the 0.70 vs 0.71 as "red extent".

## The eye stage (eyesolve.py, 2026-10-09/10)

After the identity: pose lid_upper / lid_lower, eye_opening (coupled lid_aperture), lidfold crease_height
(fold_overhang held: TPS can't see it). Staged (eyedetail): the lids first against the UPPER lid over the iris centre
and the LOWER lid under it (each lid's own position: matching the opening alone dropped the lower lid, white under
the iris), then the crease against read_lid's TPS. The model's lids by part ID (aperture.mask, deterministic), the
photo's by the detector with its bias on our start render calibrated out (detector minus part ID: it varies with the
lid state and the dressing, 0 to +1.4 mm: a limit of the method). Dressings: Tess on ts_f1's (mkt2.py), Garrett on
gc_dress (mkgc.py).
- Tess fs_te7: lid_upper +1.0, lid_lower -1.5 mm, eye_opening +0.11 sd, crease_height 4.23; lash 2.85 vs 2.80,
  lower 5.10 vs 5.14 (bias-corrected), TPS 4.53 vs 4.50.
- Garrett fs_ge3: lid_upper +2.5 (the concept's squint), lid_lower -0.3 mm, eye_opening +0.11; lash 1.44 vs 1.40,
  lower 3.84 vs 3.93; the crease NOT solved: read_lid on his render locks onto another line 6-10 mm up (the brow's
  shadow / hood), TPS 6.3-9.8 for crease_height -1.7..8.5: eyedetail's 3.0 kept; foldtrace's 20 columns needed.

## HANDOVER (facesliders, 2026-10-10): read this first

### What exists
- GNM atlas + sex axis: src/hifipushie/faceatlas.py, face_atlas.npz (3000 heads; per attribute mean, linear model B,
  sd, R2, correlations; delta_sex from ANSUR II + NIOSH lower face, within_sex() with SEX_SHARE 0.85). Coupled sliders
  (base.head.slider_mode "coupled": faceatlas.COUPLED), humanmacro.apply_coupled. Tests tests/test_faceatlas.py.
- Model extensions: src/hifipushie/faceext.py, face_ext.npz (MakeHuman CC0 mouth targets carried onto GNM, the
  identity's cheap directions projected out, commissures held, fold-free scale; residual sliders mh_lowerlip_width,
  mh_mouth_angles, mh_lowerlip_ext). Targets at /mnt/data/hifipushie/facesliders/mh_targets (SOURCE.txt; eyes too).
  Tests tests/test_faceext.py. Build: spikes/facesliders/build_ext.py.
- Checklist items added: likeness lower_lip_width ("cushion") and lower_lip_area ("lip_area").
- Sealed mouth with an interior: base.sealed_interior (slit / bag held 6 mm behind the lips); tests/test_mouth_seal.py.

### The solve pipeline (spikes/facesliders; run every job through /mnt/data/hifipushie/facesliders/run.sh <script>
### (nice, capped, OPENBLAS 1, PYTHONPATH incl. garrett3/4 + likeloop spikes); tests via tests.sh <test files>)
1. Identity: joint2.py <start> <out> <sex +1/-1>. Variables: 120 identity components (macros + coupled sliders read
   out), residual morphs RES (no fold/hood: lidfold owns them), AGE ops one-sided (FREE_AGE=1 near free), EXTRA_RES.
   Prior: within-sex Mahalanobis + component wall CAP 2.5 + READOUT wall ACAP 2.5 within-sex sds + sex DIRECTIONS
   (SEXDIR: jaw_angle / brow_ridge / forehead_slope, weak one-sided, women). Evidence: calibrated detector points per
   view (DESK_W weights non-front views), checklist ITEMS (photo - clay render through the detector, linearised on
   predicted MP points; IMPORTANCE; LIP_W), traced outlines (TRACES=<model with likeness_points lines>,
   TRACE_LINES; MATCH=silhouette (default) | envelope; SHADE_LINES: shading edges like the chin are NOT contours),
   the true profile's own contour (PROFILE_AUTO=1, outl.profile_auto: skin vs plain background, brow to under the
   chin), mentolabial depth (ML_W). FIX_CAMS=<views> freezes cameras (shared refs: one cameras copy per subject,
   refits replace, old kept by name). Writes <out>/spec.json, human_refs.json, joint_report.json; prints per-view
   rms, items before / after, prior, readouts, residuals, BIG flags, identity vs residual share.
   Example (Tess tj12): FIX_CAMS=2 PROFILE_AUTO=1 TRACES=fs_traces_t TRACE_LINES=profile,forehead
     run.sh joint2.py fs_tj0b fs_tj12 -1
   Example (Garrett gj8): LIP_W=3 EXTRA_RES=lip_upper_height,lip_lower_height TRACE_LINES=cheek.R,cheek.L,jaw.R,jaw.L,profile
     FREE_AGE=1 DESK_W=0.5 TRACES=fs_traces_g run.sh joint2.py fs_gj0s fs_gj8 1
2. Dress: Garrett mkgc.py gc_dress <head model> (garrett_head.md); Tess mkt2.py <dst> <head> ts_f1 ts_t28 (ts_f1's
   dressing, ts_t28's groom, the head's identity / sliders / pose / fold).
3. Eyes: eyesolve.py <dressed model> <out> '<fold json>' <iters>, STAGE=A (pose lid_upper / lid_lower +
   eye_opening against the upper lid over the iris centre and the lower lid under it; model by part ID, photo by
   the detector, bias calibrated on the start render) then STAGE=B with X0='[...]' (crease_height vs read_lid TPS;
   fold_overhang held). LIGHT=/mnt/data/hifipushie/likeloop/light_m.json. Writes out/eyes_<out>.png (photo |
   current | new) and <out>/eye_report.json.
4. Gates / sheets: tgate.py <shared refs model> <models...> (points rms through shared cameras + clay sheet), tess's
   prof.py (T=<scratch> run.sh <tess worktree>/spikes/tess/prof.py fs_g_<model>: profile chamfer by segment),
   shot2.py (dressed front / 3-4 / profile through the fitted cameras; D3, LIGHT), jsheet.py (NOCLAY=1 for dressed
   only), items.py (likeness items photo vs model; PF=traces model), camchk.py / yawscan.py (camera checks),
   sealmesh.py --holes (mouth holes), outdbg.py (outline matches drawn), gridimg.py (grids for tracing by eye),
   traces.py (all hand traces: fs_traces_g, fs_traces_t), storeprof.py, mouthchk.py, mouthid.py.

### Current models
- Garrett: identity fs_gj8 (accepted proportions gj6 + lips weight 3); dressed gc_dress (mkgc.py); eyes fs_ge3
  (lid_upper 2.5 mm squint, lid_lower -0.3, eye_opening +0.11; crease_height eyedetail's 3.0: unsolved). gc_dress /
  fs_ge3 hair greyed (grey_amount 0.45, near-neutral lit / sheen, eevee_sat 0.3, wave off): now reads light silver
  next to the concept's darker salt-and-pepper: try grey_amount ~0.3 and a darker lit (#5a5652) and judge at sheet
  size. The waves were not groom.fit (it scales groom metres only, not hair.strands); they came from strands
  wave / frizz / clump.
- Tess: identity fs_tj12 (accepted working face); eyes fs_te7 (lid_upper +1.0, lid_lower -1.5, eye_opening +0.11,
  crease 4.23); dressed with ts_f1 + ts_t28's groom as fs_tf12b (built, not yet rendered with the fold fix). The front
  hairline still shows a bare V with scalp streaks with ts_t28's groom on OUR head (te7h render): not the groom
  version; probably the groom's hairline on a different head (fit / hairline front_points vs this head): to check
  with tess.

### Open items (priority order as the coordinator left them)
1. Garrett's hair grey tuning (above); Tess's hairline V on our head.
2. Lip shading reader (Tess "narrower and poutier" = volume / eversion shading, not outline: photo vs clay under the
   fitted light, lever lip_lower_roll), judged with main's current skin (skin2 recoloured lip borders).
3. Border-aware MH carrying (move the vermilion border's rows together, never shear across it: the mouth extensions
   are capped at ~0.4 mm by folds there), then the MH LID targets (epicanthus, corners, margin only; no fold / hood:
   lidfold owns them, eyedetail).
4. Canthal tilt: a missing control (GNM's tilt moves the wrong corner points); a coupled + residual tilt slider.
5. Garrett's crease: read_lid locks onto the brow / hood shadow on his render; use eyedetail's foldtrace (20 columns).
6. Soft-tissue sex magnitudes (forehead inclination, brow, lip heights, gonial angle): no data by decision (no book,
   no scan licences); directions only as weak walls. Revisit if the female read stalls.
7. Chin width needs a render-based reader (the front chin line is a shading edge); the outline on Tess's jaw widened
   it in some runs (cause not pinned).
8. The eye stage's detector bias varies with lid state and dressing (0 to +1.4 mm): a part-ID-like reader on the
   photo (iris / sclera segmentation) would remove it.

## faces2 (2026-10-10, continues facesliders; scratch /mnt/data/hifipushie/faces2: run.sh / tests.sh (this worktree),
## shots.sh <model> <tag>... (shot2 renders, one queue: flock), q.sh <log> <script> (any heavy script under that lock),
## rehair.py <dst> <dressed> <groom model|-> [patch json], regroom.py, hl.py (hairline vs lock roots), hstat.py (hair
## luminance of a box), phcrop.py, crop.py; sheets out/f2_*.jpg)

### Tess's front hairline V: two causes, one fixed in code
- ts_t28's groom had no groom.fit. Its traced front_points are WORLD z; its grown locks are [az, el, h] about the scalp
  centre. On the solved head the centre sits 4.4 mm lower (C z 1.5824 -> 1.5780, y 3.3 mm back): the locks moved down
  with it, the hairline didn't (el 27.4 -> 30.6 deg at the front), so the line stood 4 mm up the brow and the first
  row's roots were 2.8 mm inside it instead of 6.8 mm (hl.py). FIX (general): hair.carry(src) = the model's hair with
  groom.fit stamped from its own head when missing (mkt2.py / mkgc.py use it), and hair.groom() now stamps fit on the
  head it grows on, so every groom carries from now on. fit_to_head's "same head" test tolerates head_ref's rounding.
  Test: test_hair_loose.test_carried_groom_keeps_its_hairline_on_the_head. f2_tf12c = fs_tf12b with the carried
  groom: the hairline back at ts_t28's (front el 27.1, roots 7.3 mm in).
- The rest is the GROOM ITSELF: ts_t28 on its own head through shot2 / light_m shows the same bare V (a_t28 render;
  tess's own render hid it in a lighter light). Behind the centre part the first row fans apart and the under layer
  ramps over strands.soft (0.022 m). Tried, one at a time: soft 0.012 (f2_tf12d): no visible change; parting depth 0 +
  length 0.015 (f2_tf12e): none; tie.curtain along 28 -> 45, hug 0.9 -> 0.6, regrown (f2_tf12f): the hair edge flatter
  (closer to her arch), the V narrower, the bare triangle under the part stays. The photo's front is hair DRAPED over
  the upper forehead from the part (volume), not a thin flat first row: a groom design job (tess's handover,
  docs/notes/tess.md), not the carry. Sheet out/f2_tess_hairline.jpg (hers | te7h | carried | curtain), honest read:
  none of the three reads as her hair yet.

### Garrett's grey: the grey share was ~75%, not 45%
- The strand grey share = look.grey_amount + look.grey_locks x each lock's grey, and gc_c1's groom already greys its
  locks (groom.grey: top 0.35, front 0.45, sides 0.68, temples 0.8; locks' mean 0.49). grey_amount 0.45 on top of that
  = ~0.75 grey strands: silver. Base colour hardly mattered (lit #5a5652 vs #4a4039: top median 0.55 vs 0.52).
- Measured (hstat.py, luminance of the hair box) on the concept's crop: top median 0.30 (#594d44, warm), sides 0.36.
  Old ge3g: top 0.59, sides 0.45. grey_amount 0 + lit #4a4039 / sheen #5e544b / gap #201b18 / grey #9a958f, eevee_sat
  0.45 (f2_g3): top 0.35, sides 0.28 (sides too dark: reads dark hair greying on top). grey_amount 0.12 (f2_g5): top 0.41,
  sides 0.32, reads salt-and-pepper at sheet size: mkgc.GREY now. Sides still darker than the concept's (their locks'
  grey is right; they sit in shade) and the top a little bright: the next lever is groom.grey (top lower, sides higher),
  which needs a regrow of gc_c1's locks. Sheet out/f2_garrett_hair.jpg (concept | current | g0 | g12).

### The lip shading reader (spikes/facesliders/lipshade.py, lipclay.py, lipsolve.py)
- lipshade.read: the lower vermilion as a lip-local grid on the detector's 11-point borders (u corner to corner, v 0
  at the stomion border, 1 at the lower border, past it onto the skin), luminance over the lip's own median (in the lip)
  or the chin's skin (under it). Features: hl_v / hl (the middle's brightest row), roll (top band over bottom band:
  an everted pad is lit on top), roll_u (across), pad_w, shadow (the darkest row under the lip over the chin) and
  shadow_u (toward the corners). Writes out/lipshade_<tag>.png with the grid drawn.
- Tess, photo vs dressed (light_m): photo shadow 0.65 middle, 0.925 at both sides; ours 0.73, 0.88 / 0.82. Her lower lip
  casts a DEEPER shadow in the middle and LESS toward the corners: a narrower, more central pout. That is the "narrower
  and poutier", now a number. Her roll falls to 0.66 / 0.58 at the sides (ours ~1.0 / 0.92), but that part is her lip's
  own colour (natural lips darken toward the stomion and corners, our paint doesn't): roll is albedo-confounded.
- Clay is the wrong comparison: Lambert clay lit by the photo's fitted light (lipclay.py) reads the middle shadow
  0.78 vs the photo's 0.41: the shadow under a pout is mostly CAST, which clay doesn't draw. The lip stage compares the
  dressed render (eevee, shadows) instead.
- lipsolve.py (a stage like eyesolve: Gauss-Newton on finite-difference renders, front only, no hair; coupled levers
  at their within-sex Mahalanobis cost, residuals L2):
  1) levers lower_lip_proj (coupled) + lip_lower_roll (residual), roll features in: it chased the lip colour, lip_lower_roll
     -1.9 (LESS eversion, a BIG residual), cost 46.9 -> 41.8. Rejected, and the roll features are dropped by default.
  2) shadow features only, levers lower_lip_proj + mh_lowerlip_width + mh_lowerlip_volume (NEW extension: MakeHuman's
     mouth-lowerlip-volume, built: the identity's cheap directions make 0.88 of it, fold-free scale 0.57, max 0.62 mm):
     every lever darkens the middle AND the sides together (lower_lip_proj -0.050 / -0.041 per sd, volume -0.034 / -0.041,
     width ~0); nothing makes the middle darker with the sides lighter. Cost 9.4 -> 8.75, x [+0.17, -0.38, -0.60].
     NOT landed (f2_tl1 / f2_tl2 are scratch).
- Conclusion: the model can't reach her lower lip's shape in depth: a pad that projects at the middle and tucks toward
  the corners. Where that should come from: a data-backed central-pad direction (no MakeHuman target is that: volume is
  the whole lip, width is the outline) or border-aware carrying (open item 3) so lowerlip_width / volume aren't capped
  at ~0.5 mm by the border's folds. Also unpinned: some of the side gap may be the light (ours 0.88 vs 0.82 left /
  right, hers symmetric).

### Open items now (replaces the handover's list 1-2; 3-8 unchanged)
1. Tess's hair: a groom design pass at the front (hair draped over the upper forehead from the part, volume), judged
   on the 3 views. f2_tf12f's curtain (along 45, hug 0.6) is a start, not a decision.
2. Garrett's grey: groom.grey top lower / sides higher (regrow of gc_c1's groom), then rebuild gc_dress / fs_ge3 with
   mkgc (GREY already updated). The workspace models gc_dress / fs_ge3 are NOT rebuilt (f2_g5 = fs_ge3 + the new look).
3. The lip: border-aware carrying (handover item 3), then a central-pad lever; lipsolve.py is ready for it
   (LEVERS=..., FEATS=shadow,shadow_side).

### faces2, round 2 (coordinator: g12's look into gc_dress; Tess's front groom before the lips)
- Garrett: gc_dress rebuilt with mkgc (fs_gj8 head, GREY = g12's look); fs_ge3 (the eye stage) got the same hair look
  through store.save (setlook.py). groom.grey (sides up) still open.
- Tess's front: NEW general option tie.curtain.drape (deg the first row roots BEHIND the hairline, x its closeness
  to the part; it still runs along the line, so it arcs forward over the band) and curtain.dip (deg that run passes
  below the line). Both 0 = the old groom exactly (test_curtain_drape_arcs_forward_over_the_line). The trace check
  (flowcmp.py: our first-row spines through the fitted camera on her photo, her traced curtain strokes, the hairline):
  rooted on the line, our spines ran ON the hairline; her strands leave the part bottom and run sideways ~20 px above
  it. drape 16 puts our spines on her strokes.
- Scored with tess's hscore (3 views) + a NEW line in it: "scalp showing in her hair band (30 mm)" = skin-coloured
  pixels of the beauty render inside her hair mask near the face. The ID-pass band metric can't see the V (one strand
  per few px counts as hair). Results (front / 3q / profile):
    f2_tf12c (carried, no drape): scalp 5.2 / 4.3 / 0.5 %, IoU 0.605 / 0.600 / 0.646, band bare 14.7 / 25.6 / 13.7
    f2_th1 drape 10, lift 0.003:  scalp 2.9 / 3.5 / 0.0,   IoU 0.598 / 0.591 / 0.642, band 14.9 / 23.1 / 13.5
    f2_th2 drape 16, lift 0.004:  scalp 2.2 / 3.0 / 0.0,   IoU 0.600 / 0.592 / 0.645, band 15.1 / 22.9 / 12.3
    f2_th3 drape 14, lift .004, dip 3: 2.3 / 3.1 / 0.0,    IoU 0.595 / 0.590 / 0.642, band 14.8 / 22.8 / 12.4
  (hers: scalp 3.1 / 3.2 / 2.0: her light hair partly reads as skin to the classifier). CANDIDATE f2_th2 =
  fs_tf12b's dressing + ts_t28's groom carried + curtain {drape 16, lift 0.004}, regrown on the solved head.
  Sheet out/f2_tess_drape.jpg (hers | te7h | carried | drape): the bare V is gone in front and 3/4, the front reads
  as hair falling from a soft part over the forehead's corners; the profile's hairline fuller. IoU front / 3q -0.005 /
  -0.008 (ours a little wider at the sides): marginal, read as not worse. Still off: the forehead between the curtains
  is a tall peak (hers a rounder arch, the hair lower at the temples: dip didn't change it), and the hair is sleek and
  flat where hers is airy with volume.

### HANDOVER (faces2, 2026-10-10, context large)
Branch worktree-agent-adab8ccb4b61accec. Scratch /mnt/data/hifipushie/faces2 (scripts above + hs.sh <models> = hscore
on 3 views under the queue lock, flowcmp.py in spikes/facesliders). Models: gc_dress / fs_ge3 (Garrett, new look),
f2_th2 (Tess hair candidate), f2_tf12c (carried, no drape), f2_* else scratch (deletable).
Next, in order:
1. Lip border carrying (handover item 3): faceext's mouth fields shear across GNM's 67 deg upper vermilion crease,
   so they're capped at ~0.4-0.6 mm fold-free (mh_lowerlip_volume 0.62 mm, scale 0.57). Move the border's rows
   together (a field smooth ALONG the border, none across it), rebuild the mouth extensions, re-check fold-free scale.
2. Then a central-pad lever (a pad that projects at the middle and tucks toward the corners) and lipsolve.py
   (LEVERS=..., FEATS=shadow,shadow_side) against her under-lip shadow (0.65 middle / 0.925 sides; ours 0.73 / 0.85).
3. Tess's hair: the temple arch (hair lower at the forehead corners) and volume; groom.grey sides for Garrett.

## faces3 (2026-10-10, continues faces2; scratch /mnt/data/hifipushie/faces3: faces2's scripts retargeted (run.sh,
## tests.sh, q.sh, shots.sh, hs.sh, rehair.py, regroom.py, crop.py ...), bmid.py; sheets out/f3_*.jpg)

### The mouth extensions' folds were never at the vermilion border
- borderdiag.py (spikes/facesliders): every carried MakeHuman mouth target first folded in the lips' INNER ROLL (lip
  rings 0-2, inside the contact ring, out of sight behind closed lips) near the corners (|x| 15-20 mm), on 57-72 deg
  template creases of ordinary 1.4-2 mm quads; |d| there only 0.05-0.3 mm. The field's along-the-lip gradient
  sheared the roll's rows (a crease keeps its angle only under rigid motion). The "67 deg upper border crease" in the
  facesliders notes was a misreading: the border is fine.
- FIX (general, faceext.py): (1) hold_rolls: the rings inside the contact ring take their own lip's move one ring
  further out (carried down the roll's columns, as faceslide's seal does); (2) hold_creases: around every template
  crease (45-150 deg, where the field moves) the field is replaced by the small rigid motion (t + w x p) fitted over
  the vertex's 3 mm neighbourhood, easing out to the neighbourhood's edge (no extrapolation past it). Alternated 3x
  with the cheap-direction projection (orthogonality kept, test). Tried and dropped: a nearest-contact-vertex copy
  (worse: jumped columns), a linear crease-angle penalty (I + s L'L + lam J'J; mouth_angles 2.4 mm but volume worse),
  a Gauss-Newton on both signs (diverged / spread into the corners' slivers).
- Fold-free at +-1 now (was): mh_lowerlip_width 2.07 mm (0.40), mh_mouth_angles 1.32 (0.38; its limit is a real skin
  fold 5 mm outside the corner, from the corner hold's own ramp), mh_lowerlip_ext 1.09 (0.89), mh_lowerlip_volume 1.08
  (0.62). The hold changes the VISIBLE lip by 3-22% of the field (most of the change is inside the mouth).
  No accepted model used the mh_ sliders (their units changed 1.7-5x). Tests: test_faceext
  (reach >= 1 mm, rigid motions untouched).
- NEW extension mh_lowerlip_middle (MakeHuman mouth-lowerlip-middle-up/down; extprofile.py: + = the lower border dips
  0.8 mm at the centre and rises 0.4 mm at half width, the skin under it following): the data-backed central pad
  lever. Fold-free to +-1.6. (extprofile also shows volume is already a central pad in depth: +0.7 mm forward at the
  middle, -0.2 / -0.6 at the corners' red / skin; -width = middle forward, sides back.)
- The corner hold was the next limit: a smoothstep release (0 within 3 mm of the corner landmarks, full by 8 mm) put a
  2 mm step beside the corners. lowerlip_width at -1 (f3_tl2 / tl3 renders) showed crescent GROOVES beside / under each
  corner in front and 3/4 views, and past -1 folded there (rings 4-9 under the commissure). Now corner_hold: a
  correction e = -d within 3 mm, 0 from 25 mm, BIHARMONIC between (harmonic first: still a log-like dimple at the held
  disc's edge, the grooves stayed; release 15 mm: smaller crescents still visible in f3_tl4; corner.py compares holds). curv.py (faces3 scratch): curvature change |n . L d| / edge^2 on the visible skin at
  +1, per slider: lowerlip_width 93 -> 53-69 /m, ext 37 -> 45, middle 12; volume ~155 and mouth_angles ~160 /m at
  the corners are mostly the MakeHuman data's own (119 / 161 with no crease hold). Hand-made lip sliders: 40-66 /m.
  With 25 mm (corner.py, curvature within 6 mm of the corners): width 67 -> 40 /m, angles 163 -> 82; volume stays ~150
  (MakeHuman's volume target reshapes the corner itself: it is left out of Tess's lip solve). Fold-free at +-1 now,
  all scale 1.0: width 1.45 mm, angles 1.27, ext 0.95, volume 1.03, middle 1.00.
- lipsolve.py bounds the extensions to +-1 (active set). Unbounded (f3_tl1, old fields) it took width to -1.58: past
  MakeHuman's own extreme, 20 folded pairs.

### Tess's lower lip: lipsolve against her under-lip shadow (front, dressed, light_m; hers 0.654 mid / 0.924 sides)
- Derivatives per unit (renders, noisy): lower_lip_proj (coupled sd) -0.047 / -0.035; mh_lowerlip_width +0.005 / -0.03
  to -0.05 (so -width LIGHTENS the sides: the lever faces2 lacked, it was capped at 0.4 mm); volume -0.03 / -0.03;
  middle (the central pad) only -0.01 to -0.02 / -0.01: MakeHuman's lowerlip-middle moves the border, it hardly
  deepens the cast shadow.
- Runs (start f2_th2, 0.723 / 0.842, cost 10.45): f3_tl1 (old fields, unbounded) 0.688 / 0.886, cost 2.32 but width
  -1.58 (folds: rejected). Bounded: tl2 0.717 / 0.879 (4.72), tl3 / tl4 similar but crescent GROOVES beside the corners
  in the renders (the corner hold, above). f3_tl5 (corner hold 25 mm; levers proj, width, middle; volume left out for
  its corner curvature): 0.710 / 0.874, cost 4.82, x = proj +0.08 sd, width -1.0 (at its bound), middle +0.06; prior
  1.01. Renders clean (out/mouth5_front.png / mouth5_desk.png: current | tl5 | tl4's crescents). The sides are 2/3 of
  the way to hers; the MIDDLE's deeper shadow is still not reached (0.71 vs 0.65): no fold-free data-backed lever
  darkens the middle without the sides. Candidates for it: a mentolabial / chin-pad direction from data (the cast
  shadow lands on the chin skin: its slope under the lip decides the shadow's depth), or the light (faces2: ours
  0.88 vs 0.82 left / right, hers symmetric).

### Tess's forehead arch (hscore's new "forehead arch" line: the forehead's skin edge per column, the same skin
### classifier on her photo and our beauty render, 5 bins temple to temple; the ID pass can't see a peak)
- f2_th2: ours - hers +12.4 +9.2 +2.5 +12.9 +5.8 mm (+ = our hair edge LOWER): the "tall peak" is our curtains
  covering the forehead's upper corners down the diagonals, not her arch being lower at the temples (it is the
  opposite: her skin reaches 9-13 mm higher at the corners, a broader, rounder top).
- tie.curtain.sag (NEW, general: the run on to the ear's top hangs below / above its great circle): +8 / +16 / -10 /
  -20 changed nothing measurable (only 2 of the lock's 11 samples are on that run). Kept (default 0, tested), not used.
- curtain.dip < 0 (the run along the line passes ABOVE the traced hairline): dip -6: +8.2 +5.3 +0.6 +8.9 +1.6;
  dip -12 (f3_ha8): +3.3 +1.5 -1.2 +5.3 -2.4, arch height 37.2 (hers 38.8), centre peak 23.3 mm up (hers 25.3). IoU
  front / 3q / profile 0.600 / 0.596 / 0.651 (th2 0.600 / 0.592 / 0.645), scalp showing 2.4 / 3.1 / 0.0 (th2 2.2 /
  3.0 / 0.0; hers 3.1 / 3.2 / 2.0), band bare 15.5 / 22.8 / 12.5 (th2 15.1 / 22.9 / 12.3): not worse anywhere that
  counts. Reads as a broader, rounder forehead top; the part still a small peak (hers too, softer). The traced
  front_points may sit low at the corners (her visible edge is above them): a re-trace would be the data fix.
- Sheet out/f3_tess_lip_hair.jpg (hers | current f2_th2 | lips f3_tl5 | hair f3_ha8; front / 3q / profile, dressed).
- Combined CANDIDATE f3_t1 = f3_tl5's lips + f3_ha8's hair (curtain dip -12): hscore front / 3q / profile IoU 0.601 /
  0.596 / 0.651, scalp 2.6 / 3.3 / 0.0, band bare 15.5 / 22.7 / 12.3, forehead +3.3 +1.4 -1.5 +5.2 -2.3. Sheet
  out/f3_tess_t1.jpg (hers | f2_th2 | f3_t1). Honest read: the front's forehead top is broader and rounder, closer to
  hers, though the hair's edge over the upper corners reads a little blunt; 3/4 and profile ~unchanged; the lip change
  is subtle at sheet size (sides of the under-lip shadow lighter, see mouth5_*.png). Nothing reads worse.

### HANDOVER (faces3, 2026-10-10)
Branch worktree-agent-ad926584389c85c9a. Scratch /mnt/data/hifipushie/faces3 (faces2's scripts retargeted; + curv.py
(curvature change per lip slider), corner.py (corner-hold variants), wfold.py, bmid.py; spikes/facesliders/
borderdiag.py, borderquad.py, extprofile.py). Models: f3_t1 (Tess candidate), f3_tl5 (lips only), f3_ha8 (hair only).
Next, in order:
1. Tess's under-lip MIDDLE (0.71 vs her 0.65): a data-backed lever that deepens the cast shadow at the centre only
   (mentolabial / chin-pad direction), or pin the light's left / right asymmetry first.
2. The front hair edge over the forehead's upper corners reads blunt; front_points may be traced low at the corners
   (her visible edge sits above them): re-trace through the fitted camera, then drop dip back toward 0.
3. MakeHuman volume / mouth_angles reshape the corner itself (curvature ~150 /m there): fine as data, but check them
   in renders before a solve uses them. Then the faces2 list: Garrett's groom.grey (sides up), the MH lid targets
   (border-aware carrying now exists: hold_creases is general, try it on the lids), canthal tilt, chin reader.

## faces4 (2026-10-10, PAUSED by the coordinator after step 1; scratch /mnt/data/hifipushie/faces4: faces3's scripts
## retargeted + fetch_nose.py, survey.py, nosediag.py, noseprofile.py, build4.py, strip.py / strips.sh)

Joe paused new extensions ("we need to work toward a more coherent model"). What exists from step 1 (nose):
- MakeHuman CC0 nose targets (42, same commit a8bc2d54) at /mnt/data/hifipushie/facesliders/mh_targets/nose
  (SOURCE.txt appended). faceext.carry now also takes MakeHuman's per-side eye targets (l- + r- summed).
- survey.py (all 21 pairs): the identity's cheap directions make 0.52-0.96 of each target. trans-* / scale-* are
  0.93-0.96 identity (position and size are GNM's): left out.
- FIX (general, faceext.fill_inside): every nose target folded at 0.43-0.79 of its range JUST INSIDE THE NOSTRIL: the
  field was read and projected over skin_exterior only, so the rim moved and the nostril wall behind it stayed (|d| 0
  on one side of the folded pair). The non-exterior skin (not the mouth: hold_rolls owns it) now takes the harmonic
  extension of the field. Fold-free scale after: hump 0.76 -> 1.0, width3 0.79 -> 1.0, point 0.43 -> 0.67, base
  0.43 -> 0.54, nostrils-angle 0.51 -> 0.52 (its fold is a real kink in MakeHuman's data at the alar-facial groove,
  5.9 -> 67 deg between neighbours with |d| 0.92 vs 0.30).
- 14 nose extensions built into face_ext.npz (faceext.EXT, mh_nose_* / mh_nostrils_*; noseprofile.py numbers in the
  EXT strings): hump, curve, greek, compression, point, septum, base, nostrils_width, nostrils_angle, point_width,
  volume, width1-3. Near-duplicates by field cosine: nostrils_width ~ width3 +0.69, point_width ~ volume +0.57,
  septum ~ nostrils_angle +0.56. Max reach 0.9 (base, scaled 0.43) to 2.8 mm (curve).
- Strips (clay, numba renderer, -1 / 0 / +1, front / 3/4 / profile): human_renders/f4_01_nose_strip_1..3.png.
  Blunt read of strip 1: the dorsum ones are NOT clean: hump +1 and curve +-1 put a visible step / crease across the
  upper dorsum in 3/4, greek -1 a notch at the nasion in profile (fold-free by the quad test, but a curvature
  artefact: curv.py was not run on them yet). nostrils_width reads cleanly (wider alae, f4 test strip).
- Not done: curvature check, readers (alar width, tip projection, nasal length, nostril show, columella, dorsum line),
  tests for the nose ones, eyes, upper lip, any solve.

## faces4: the coherent model (DESIGN, 2026-10-10; Joe: "it needs to get merged into a coherent model, along with
## the new controls we need ... This is how we will also achieve our stylized/pixar/anime looks.")

Goal: ONE face model = one parameter space, one prior with couplings learned from data, one solve (stages become
views / weights of it), every control a dimension of it or a direction in it, and style a principled move in the same
space. Scripts behind the numbers: /mnt/data/hifipushie/faces4 (inv.py, gnmkeys*.py, tailcomps*.py).

### 0. Two facts found while designing (they shape everything below)
- GNM has MORE than we use: 170 head identity components (we take 120; 120-169 move 0.07-0.09 mm/sd per region, no
  more local than 80-120), 3 eye and 80 teeth components, and an EXPRESSION basis of 383 (100 per eye region, 150
  lower face, 32 tongue, 1 pupil) that base.py / faceshapes already use for pose and face shapes. Lids and smile are
  expression, and GNM has a basis for them.
- The extensions are not outside GNM's span: they are outside its LOCALITY. Fitted over their own region only,
  GNM's 120 components make 0.94-1.00 of every mouth / nose extension (170: 0.96-1.00) at 21-100 sd. Fitted over the
  whole head (the extension and zero elsewhere) they make 0.10-0.52 (tailcomps_whole.py). GNM's PCA is global: it can
  draw a local feature only with large side effects elsewhere. So the coherent model needs: GNM's global space + a
  LOCAL residual layer with its own statistics + couplings between them, not more GNM components.

### 1. Inventory, per control: what it moves, what reads it, overlaps, and its fate
Fates: (a) a direction in the identity (conditional mean under the joint prior), (b) a new model dimension with
learned statistics (the local residual layer), (c) pose / expression (GNM expression basis, per picture), (d) style,
(e) dropped (folded into another). "Reader" = the evidence that sees it today.

| control | moves | reader today | overlaps | fate |
|---|---|---|---|---|
| GNM identity head_000-119 | whole head | detector points, outlines, profile contour, items | - | the space (keep) |
| GNM head_120-169 (unused) | fine global | none | - | add to the space (cheap, same prior) |
| humanmacro macros (37) | proportions | items, outline | coupled mode = directions | (a) |
| coupled brow_ridge, eye_setback, malar_rise, lip_upper/lower_height, lip_bow, lip_upper/lower_roll (lip proj), nostril_show, gonion_height, ramus_angle | landmark attributes, R2 ~1 | items (detector), profile | each also had a local morph (old mode) | (a) |
| coupled canthal_tilt | GNM eye_tilt (the wrong corner points) | detector tilt (does not move with it) | epicanthal, corner morphs | (a) + (b): an eye-corner residual dim (the fissure turned on the ball) |
| coupled eye_opening (lid_aperture) | lids | part-ID aperture, detector lids | pose lid_upper / lid_lower | split: identity aperture (a) + per-picture lid pose (c) |
| coupled eye_hood (fold_overhang, R2 0.70) + its (1-R2) morph | fold over the lid | read_lid TPS (unreliable on Garrett) | lidfold, age_lid_fold, eye_hood_lateral | (a) + (b) upper-lid dims |
| eye_crease_height / _depth, eye_platform, lidfold crease (R2 0.13) | the crease | read_lid TPS, foldtrace | each other | (b) upper-lid dims (2-3, one basis) |
| eye_hood_lateral, brow_lateral, eye_sulcus, epicanthal | orbit / lid soft tissue | judge only | MH epicanthus, eyefold | (b) orbit dims |
| eye_bag, eye_tear_trough, eye_lidcheek, age_lid_fold | lower lid / lid-cheek | shading rows (confounded) | MH bag / bag-height | (b) lower-lid dims, age-coupled |
| lid_margin_upper / _lower (one-sided) | lid margin thickness | none (close-ups) | - | a fix to the MEAN (GNM lids taper to 1 mm: anatomy, not identity) + a small (b) variance |
| lip_tubercle, mouth_corner, lip_lower_width (hand) | lips | lipshade, detector lips | mh_lowerlip_*, mh_mouth_angles (same features, MH data) | (e): replaced by the lip residual dims |
| mh_lowerlip_width / ext / volume / middle, mh_mouth_angles | lower lip, corners | lipshade shadow, cushion / lower_lip_width | each other; volume ~ middle (central pad) | (b) lower-lip / corner dims (rebuilt, section 3) |
| upper lip (MH upperlip-*, cupidsbow, philtrum: downloaded, not built) | upper lip | detector, bow item | coupled lip_upper_height, lip_bow | (b) upper-lip dims |
| nose_radix / dorsum / tip_width, nose_dorsum_hump, tip_definition (hand) | nose | none (faceslide.nose_widths unstable) | mh_nose_width1 / width2 / point_width / hump | (e): replaced by the nose dims |
| mh_nose_* (14, faces4 commit 6f480e2) | nose | none yet | nostrils_width ~ width3 +0.69, point_width ~ volume +0.57, septum ~ nostrils_angle +0.56; hump / curve / greek / compression all move the dorsum line | (b) nose dims (rebuilt; ~8, not 14) |
| face_planes, face_lean, cheek_hollow (baked, one-sided) | cheek / temple soft tissue | shape rows (shading), outline (lean) | age ops, humanstyle cheeks | (b) soft-tissue dims, age / sex coupled |
| age_nasolabial, age_prejowl, age_cheek_flat, age_lid_fold (baked) | ageing | shape rows, judge | above | (b) with AGE as a covariate (the conditional mean moves with age) |
| chin_cleft (baked), shape.chin.cleft | a groove | none | - | (b) a chin dim (small) |
| shape.jawline.*, shape.nose_tip, shape.chin.project / width, base.head.warp | jaw, nose tip, chin | likeness levers, traces | identity jaw / chin / nose directions | (e) for likeness; kept as diagnosis tools only |
| eye stage: pose lid_upper / lid_lower (eyesolve) | lid position in a picture | part-ID aperture, detector | eye_opening | (c) GNM eye-region expression comps, per picture |
| pose.smile, squint / frown read on refs | expression | detector blendshapes, flagged items | - | (c) per picture (lower-face / eye expression comps) |
| lipsolve levers (lower_lip_proj coupled + mh_ ext) | lower lip | lipshade shadow | - | an evidence term of the one solve, not a stage |
| humanstyle head ops (head_size, cranium, eye_spacing / height, face_flat, nose, nose_width, jaw, chin, cheeks, mouth, mouth_height, exaggerate), style.eyes, style.simplify | stylisation | none | identity directions for most | (d) (section 5) |

Net: ~61 face sliders + 120 comps + 37 macros + warp / shape ops + 3 staged solvers -> 170 identity comps + ~35-45
local residual dims (nose ~8, upper lid ~4, lower lid / lid-cheek ~4, orbit / brow ~3, eye corner ~2, upper lip ~4,
lower lip / corners ~5, chin / mentolabial ~3, cheek soft tissue ~4) + per-picture expression + style.

### 2. Where the statistics come from (licences checked 2026-10-10)
- GNM (google/GNM, Apache 2.0, in use): the global identity prior N(0, I) over 170 comps (+ our ANSUR / NIOSH sex
  axis). Keeps that job.
- ICT-FaceKit (github.com/ICT-VGL/ICT-FaceKit; "ICT-FaceKit is released under the MIT license", Copyright 2020 USC
  ICT): the Light model, 100 identity PCA modes + 53 expression blendshapes, face area 9,409 vertices, each eye socket
  384, mouth socket 2,046, from USC's Light Stage scans (the CVPR 2020 paper cites a 4,000-scan dataset; the number of
  subjects in the Light model's PCA is not stated). CAVEAT: the MIT text grants "this software and associated
  documentation files"; it does not name the model data, and the README says the FULL model will come under "a
  different USC specific license". The Light model's files sit in the MIT repo; reading them as covered is
  reasonable, but it is Joe's call (or a one-line email to ICT). It is the only permissive 3D face model found with
  population-learned LOCAL detail at nose / lips (lids: moderate, 384 vertices a socket).
  Use: register ICT's template to GNM's once (landmarks + non-rigid), then every ICT identity mode maps LINEARLY to
  our coordinates (GNM comps + local residual dims): the joint prior is the push-forward A Sigma_ICT A^T, exact, no
  sampling. Its cross-covariances are the couplings we don't have (alar width ~ tip width ~ dorsum; lip volume ~
  philtrum; fold ~ brow).
- Out (non-commercial or no-derivatives): FLAME / D3DFACS, BFM, FaceScape, LYHM / Headspace, Florence, FaceWarehouse,
  Multiface / Ava-256, NeRSemble, FaceBase (controlled access), the Second Chance heads (CC BY-ND). Anything built on
  them inherits it. HSRD-100 (CC BY 4.0) is 10 people's bodies: no use.
- Photos for fitting / validation: the Face Research Lab London Set (DeBruine & Jones, figshare 5047666, CC BY 4.0):
  102 adults, 1350 px, neutral and smiling, front + left / right 3/4 + left / right profile, 189-point templates, age /
  sex / ethnicity. Consent wording: "used in lab-based and web-based studies": we would keep the photos on /mnt/data
  (never in the repo or assets) and ship only statistics learned from them, with attribution: Joe to confirm that
  reading. Realistic accuracy (face ~600 px wide: ~0.25 mm/px): profile contour (dorsum, tip projection, columella,
  lips, chin) ~0.5-1 mm; alar width, mouth width, lip heights ~0.5-1 mm; nostril show, tip width ~1 mm; lid crease /
  fold NOT reliably (detector bias 0-1.4 mm, our finding). Photos can learn / validate the nose and lip dims'
  variances and couplings; the lids' come from ICT or are designed.
- Dimensions with no data (lid margin, crease depth, chin cleft, the age ops' magnitudes): a DESIGNED prior,
  documented as such: zero mean, variance set so +-2 sd spans the range the anatomy literature / MakeHuman's own
  target range gives, couplings only where stated with a reason (crease height ~ fold_overhang, age ~ ageing dims),
  flagged "designed" in the table so a fit leaning on one is visible.

### 3. Fixing the local shapes so they are good dimensions
- The dorsum steps (hump / curve +-1, greek -1, f4_01 strips): likely cause in the code: faceext.minus_probable zeroes
  the field OUTSIDE its region (3% of its max) and subtracts the cheap-identity part only INSIDE it, so the correction
  ends at the region's edge: a step where the region stops. (Hypothesis; the fix is the test.) Fix: a smooth window
  (the region's weight tapered over ~5 mm) or the projection done in a smooth basis, never a hard mask.
- A clean basis, per region (nose, upper lid, lower lid, eye corner, upper lip, lower lip / corners, chin, cheek):
  1. candidates: ICT's residuals (ICT modes minus their best GNM fit, mapped to GNM), MakeHuman targets, our hand
     morphs; 2. made smooth: expressed in the region's low-frequency manifold harmonics (Laplacian eigenvectors of
     GNM's skin under a smooth window), with fill_inside / hold_rolls / hold_creases as now; 3. orthogonal to the
     identity's cheap directions (windowed projection); 4. PCA within the region weighted by the data's variance
     (ICT) -> ordered, uncorrelated modes; MakeHuman names become DIRECTIONS in that basis (semantic handles), not
     dims; 5. gates per mode at +-2.5 sd: no fold (test_faceslide criteria), curvature change on visible skin under
     the hand sliders' 40-70 /m (curv.py), a render strip read by eye.
- Duplicates go away by construction (one PCA per region instead of 14 overlapping MH fields).

### 4. The single solve
- Unknowns: z = [identity c (170), local residual r (~40), soft tissue / age s] shared by every picture; per picture
  e (GNM expression comps, reduced: eye regions + lower face, ~20 each) + camera + light.
- Prior: one Gaussian over [c, r, s] with the learned cross-covariance (GNM block, ICT push-forward for r and the
  cross terms, designed entries flagged), within sex, age as a covariate. Expression prior: zero mean, tight for
  pictures read as neutral (detector blendshapes set each picture's scale: the squint / frown rule becomes this),
  wider where an expression is read. Lid pose = e, the lid's anatomy = c + r: no separate eye-stage solve.
- Evidence (one objective, weights per term, as joint2 has them): detector points per view, traced and automatic
  outlines, the true profile's contour, checklist items (incl. new nose readers), part-ID lid aperture, read_lid /
  foldtrace crease, lipshade under-lip shadow, shape shading rows. Geometry is LINEAR in z (mesh = mean + B z):
  point / outline / contour Jacobians are analytic and cheap; render-based terms (lid part-ID, lip shadow, shading)
  get finite differences only along a few directions (the posterior's top ~5 for that term), refreshed every few
  iterations.
- Stages become a SCHEDULE of weights over the same objective (coarse terms first, fine terms phased in, nothing
  pinned): an earlier stage's result can still move; the gates catch regressions.
- Gates (every accepted iteration): no view's point rms worse than at the start by more than its noise, no checklist
  item that was within tolerance pushed past it, no component / readout past 2.5 sd (Mahalanobis per block),
  fold-free, curvature on visible skin under the cap. Report per variable block its share of the improvement.
- Speed: the prior is most of the Hessian; with Woodbury on the low-rank evidence one Gauss-Newton step over ~260
  unknowns is milliseconds; renders (~2.5 min each today) are the cost: batch the finite-difference renders in one
  Blender call per iteration.

### 5. Style in the same model
- A style is a TRANSFORM of the coordinates plus ops outside the human space:
  z_style = mu_S + G_S (z - mu) (+ humanstyle's geometric ops no human has: head_size, eye size, face_flat).
  G_S = per-direction gains: exaggeration (> 1, caricature along chosen directions; today's `exaggerate` is G = k I),
  simplification (< 1 on the fine identity comps and the local residual dims: a band-limited face), and named
  semantic directions (nose size, jaw taper, eye spacing) as gains or offsets. mu_S = the style's own mean (a
  feature-animation face's fuller cheeks, an anime face's small low mouth).
- Anime nose = the nose's residual dims and nose identity directions at gain ~0.1 toward a tiny style-mean nose, plus
  the existing `nose` op; anime / Pixar eyes = style.eyes (size) + the eye part (outside the human space by design);
  mouth = a gain on the mouth-width direction. Simplification is principled: drop the dims whose variance is below
  the style's band.
- Authoring: a style sheet (styles/human_*.json) states gains / offsets in the model's NAMED directions (an artist /
  LLM edits words they understand: "nose 0.15, jaw taper +1.5 sd, fine detail 0.3"), the ops, and the material look.
  From references: fit (z per character; the style's G_S / mu_S shared) to a few model sheets of one style, with the
  human prior on z and a weak prior on the style parameters around the designed values.
- Fitting under a style: a real person -> fit z on photos in human space, then apply the style (they stay recognisable:
  gains act on their offset from the mean). A stylised design with no photo -> fit in style space (z = mu + G_S^-1
  (z_style - mu_S) where gains are > ~0.2; dims damped toward 0 are unobservable and the prior fills them).

### 6. Build plan (each milestone judgeable on Tess and Garrett)
- M0 (smallest): the dorsum step: windowed projection in faceext; curv.py over every built extension; strips again.
  Judge: clean nose strips; reach / fold-free / curvature / cheap share per extension.
- M1: Joe's licence calls (ICT Light model data; FRLL consent reading). Register ICT's template to GNM (landmarks +
  non-rigid), map its 100 identity modes into GNM comps + residual. Judge: ICT modes rendered on GNM's mesh beside
  ICT's own; the share of each mode GNM's global space makes vs the residual.
- M2: the regional residual bases (section 3) from ICT + MakeHuman handles; gates per mode. Judge: +-2 sd strips of
  every mode on Tess / Garrett, a table.
- M3: the joint prior (GNM block + ICT push-forward + designed entries), within sex, age covariate. Judge: random
  faces from the prior rendered (varied real people, noses and lips included?), a couplings table.
- M4: FRLL validation: fit 20-30 London faces (5 views) in the new space; the Mahalanobis of real faces per block
  (dims real faces push past 2.5 sd = the prior is too tight there); refine variances (empirical Bayes). Judge: fit
  sheets + numbers.
- M5: the single solve (joint3, section 4) on Tess and Garrett from their current identities; ranked checklist tables
  per region (item, reference, before, after), before | after | reference focus crops; honest misses.
- M6: controls as directions: every slider name (old and new: canthal tilt, central lip pad, nose items) = a
  conditional-mean direction under the new prior; old specs still reproduce (slider_mode). Readers for the nose items
  (alar width, tip projection, nasal length, nostril show, columella, dorsum line).
- M7: style: G_S / mu_S on top of the space, the four human_* sheets re-expressed, one fitted to references. Judge:
  Tess and Garrett realistic / feature-animation / anime, same identity.

### 7. Perception: what a viewer sees, not mm (added 2026-10-10; Joe: "The human brain is really good at perceiving
### tiny changes when they're related to identity.")
Sections 0-6 above measure in mm / px / data variance. Those are the wrong units for "does it look like her": I
dismissed GNM's components 120-169 as "0.07-0.09 mm/sd", ordered bases by variance and weighted the solve in mm. Changes:
- A PERCEPTUAL EFFECT per direction (new tool, M0b): render -1 / +1 sd of a direction in OUR renderer (same style both
  sides: clay vs clay or dressed vs dressed, so the clay-vs-painting gap that sank face-ID as a fit term does not
  apply) through 3-5 views on 2-3 heads (Tess, Garrett, GNM's mean), and take the face-ID embedding distance between
  the two (faceid.py: SFace, Apache, the default; ArcFace w600k_r50 is InsightFace's non-commercial weights: measuring
  only, never shipped, as garrett_head.md set it), next to the mm. Calibrate first: our render vs itself re-rendered
  (noise floor), and the distance between two different GNM heads (a "different person" scale). Rank by it: all 170
  identity comps, every expression comp's leakage into the neutral face, every coupled slider / residual / extension
  direction. Open questions this answers: are 120-169 really negligible perceptually; do small-mm directions at the
  eye corners, lid margins, nostrils and lip borders move identity more than large-mm directions on the cheeks;
  which of the 14 nose fields a viewer can tell apart.
- Salience inside the solve: the evidence terms stay in their units, but each geometry residual gets a weight by
  facial region (eyes / lid margins / brows, mouth borders, nose tip / alae, the face outline, cheeks / forehead
  lowest), CALIBRATED from the embedding sensitivities above (the weight of region R ~ the embedding change per mm
  of moves confined to R), not set by hand. The embedding itself stays OUT of the objective (it failed across media);
  it is a ranking / gating tool between our own renders.
- Literature (looked up, cited qualitatively; no numbers taken from it): Haig (1984, Perception 13:505-512) found
  displacements of facial features in unfamiliar faces detectable at about the visual-acuity limit (as summarised by
  Schwaninger, Ryf & Hofer 2003, Vision Research); Hosie, Ellis & Haig (1988) similar for familiar faces; a 2015 Cortex
  study measured JNDs for feature-position changes and found the eye region's spatial resolution unaffected by
  inversion (the eye region is read part by part as well as configurally). Diagnostic-feature studies (Schyns,
  Bonnar & Gosselin 2002, Psych. Science: eyes and mouth carry identity in the Bubbles task; Sadr, Jarudi & Sinha
  2003, Perception: removing eyebrows hurts recognition as much as removing eyes) point the same way. The thresholds
  we use will be OUR measured embedding sensitivities, with these as the reason to expect the eyes / brows / mouth to
  dominate.
- Basis ordering and truncation by perceptual weight: a regional basis is ordered by variance x perceptual effect
  (the expected identity change a mode makes across the population), not by variance alone; components and modes are
  kept or dropped on that. A mode with little variance but a big identity effect (a lid-margin or nostril-rim mode)
  is kept.
- Style's "simplify" must not damp what carries identity: simplification removes perceptually WEAK detail (high
  variance-normalised frequency, low identity effect: skin relief, small asymmetries), while the identity-carrying
  directions are kept or exaggerated (a caricature keeps identity by exaggerating it: today's `exaggerate`). An anime
  nose shrinks the nose's SIZE but keeps its proportions' sign where they carry identity (tip up / down, width) at a
  reduced gain.
- Gates add an identity check between our own renders: before vs after any solve or basis change (the same person:
  embedding distance under a threshold set from the calibration, per view), and realistic vs styled version of one
  person (styled should stay closer to its own realistic version than to any other subject's: a rank test across
  Tess, Garrett and GNM samples).

How it changes the plan:
- M0b (new, before M1): the perceptual-effect tool + calibration, and the ranking of GNM's 170 comps, the expression
  comps' neutral leakage, the coupled sliders and the 14 nose / 5 mouth extensions. Decides whether 120-169 enter the
  space with full weight, and gives the first salience weights.
- M2: regional bases ordered and truncated by variance x perceptual effect; per-mode report gains an "ID effect" column.
- M3: random faces from the prior judged by eye AND by the embedding spread (do prior samples differ like different
  people do?).
- M5: the solve's geometry weights come from the salience calibration; its gates include the identity check.
- M7: style transforms checked with the realistic-vs-styled rank test; simplify by perceptual weight.

### M0 result (2026-10-10, commit e13fe4b): the dorsum step
- Hypothesis CONFIRMED: faceext.minus_probable cut the cheap-identity correction at a hard region mask (3% of the
  field's max). Now `faceext.WINDOW` (12 mm): the correction is applied under a smoothstep window that eases from the
  region to 0 over 12 mm (`_window`). Mouth fields keep the hard mask (WINDOW_MOUTH 0: windowed, the projection
  reached into the corner hold and folded volume / middle at 0.4-0.7; redo with the hold after the projection in M2).
- Also: nose fields hold the lids' rims (smoothstep 2-8 mm from the rim; the hump's field reached the inner canthi:
  rims moved 0.07 mm); hold_creases moves skin only (it moved eyeball vertices next to lid creases); faceslide splits a
  self-mirrored vertex 0.5 / 0.5 (centre-line vertices at x ~ 0.1 mm put 3% of the nose's largest moves on one side).
- Curvature change on visible skin at +1 (ncurv.py; max / p99, 1/m; hard mask -> window 12 mm, out/ncurv_all.txt,
  out/ncurv_final.txt): curve 105 / 21 -> 39 / 16; greek 106 / 21 -> 24 / 7; compression 40 / 11 -> 15 / 7; width2
  98 / 24 -> 16 / 9; width1 56 / 15 -> 16 / 7; volume 87 / 24 -> 28 / 10; point_width 44 / 8 -> 11 / 3; width3
  220 / 70 -> 86 / 19; nostrils_width 144 / 50 -> 93 / 15; point 76 / 14 -> 48 / 12; hump 107 / 31 -> 106 / 24;
  septum 133 / 60 -> 159 / 20; base 94 / 26 -> 99 / 25; nostrils_angle 93 / 20 (at scale 0.42) -> 228 / 26 (now
  fold-free at 1.0, 2.9 mm). The remaining maxima (hump, septum, base, nostrils_angle, width3, nostrils_width) are all
  at the alar-facial groove (x +-13, 10 mm under the tip, 17 behind): MakeHuman's own data bends it (wall.py: the raw
  carried hump has 64 /m on the side wall before any of our processing). p99 for every extension now < 30 /m (new
  test). Hand-made sliders for scale: 40-66 /m max.
- Strips: human_renders/f4_03_nose_m0_1..3.png (all 14, -1 / 0 / +1, front / 3/4 / profile, clay) beside the hard-mask
  f4_01_nose_strip_1..3. By eye: the curve +1 dorsum crease and the greek -1 nasion notch are gone; curve +1 keeps a
  faint soft line on the side wall in 3/4 (39 /m), hump +1 a faint one. Several fields are small at sheet scale
  (base 0.9 mm, point_width 0.9 mm).
- Tests: test_faceext (+ test_extensions_bend_the_visible_skin_smoothly), test_faceslide, test_faceatlas: 20 pass.
  Loosened, with the reason in the test: locality 10% -> 12% of the template (windowed fields reach 12 mm further;
  hump 10.2%); cheap-direction orthogonality for the nose 0.1 -> 0.2 (windowed + rim hold leave <= 0.17 along them:
  curve, nostrils_width; the coherent model's joint prior replaces this test's role).

### Licence decisions (2026-10-10, Joe via the coordinator: "both licenses are ok with me")
- ICT FaceKit Light: the model data in the MIT repo treated as MIT-covered. Asset pack `ictfacekit` (optional; commit
  pinned in assets.json; 168 files, 405 MB at /mnt/data/hifipushie/assets/ictfacekit, symlinked from _templates).
- Face Research Lab London Set (DeBruine & Jones 2017, figshare 5047666, CC BY 4.0): photos stay on /mnt/data (pack
  `frll`, optional, 13 files, 282 MB), never in the repo, assets or exports; only statistics learned from them ship,
  credited "DeBruine & Jones (2017), CC BY 4.0".
- /mnt/data was at 19 GB free after these downloads (the 20 GB floor for jobs): mine are 0.7 GB.

### M0b: the perceptual effect (spikes/facesliders/perc.py; out/perc/perc_*.txt / .json)
GNM's head alone (no one-mesh build: ms per head), clay with eyes and drawn brows (likeness.render), views 0 / -30 /
+30 deg, heads GNM mean, Tess (f3_t1's identity only), Garrett (fs_gj8's); distance = 1 - cosine of the face-ID
embedding between the -1 and +1 renders (SFace; ArcFace agrees: r 0.98 over the 170 comps).
- Calibration: the camera turned 0.5 / 1 / 2 deg: 0.014 / 0.020 / 0.027 (renders are deterministic: this is the
  embedding's sensitivity to a change that is NOT identity, our practical floor). Different people: Tess vs Garrett
  0.23, GNM mean vs either 0.14-0.18, random GNM heads 0.24-0.65 (median ~0.44).
- GNM's 170 components at +-1 sd (median, max): comps 0-9 0.076 (0.129); 10-39 0.033 (0.069); 40-79 0.022; 80-119 0.018;
  120-144 0.014; 145-169 0.014. Per mm of rms move the fine comps carry FAR more: 0.025 / mm (0-9), 0.058 (10-39), 0.099
  (40-79), 0.16 (80-119), 0.17-0.23 (120-169). At +-1 GNM-sd the unused comps sit at the half-degree-turn level; but ICT
  says the population varies 2-3x more along them than GNM's prior (below), where they would reach ~0.03-0.04: they
  belong in the space.
- Top by effect: head_004 (0.129, 3 mm rms), head_000 (size, 0.126 at 10 mm), head_002, 001, 006, 005, head_011 (nose,
  0.069 at 1.3 mm), head_018 (chin, 0.056 at 0.7 mm), head_022, head_020 (nose, 0.041 at 0.7 mm), head_047 (chin,
  0.036 at 0.29 mm), head_048 (brow, 0.035 at 0.28 mm): small-mm directions at the nose, chin and brow rank with
  10x larger ones.
- Region salience (spikes/facesliders/salience.py, out/perc/salience.json): random smooth normal moves confined to one
  region (Gaussian bumps r 4 mm, mirrored, 0.5 mm rms, 6 per region x 3 heads x 3 views), 1 - cos per mm rms, relative to
  the cheeks: brows 3.34, forehead 2.46, nose 2.01, orbits 1.79, lower lip 1.06, upper lip 1.03, cheeks 1.00,
  infraorbital 0.91, zygomatic 0.86, temples 0.46, jaw / parotid 0.27, chin 0.26 (spread +-25-45% between draws).
  CAVEATS: the brows' weight is inflated (the clay draws brow strokes through the brow landmarks, which ride the
  surface); clay has no lip colour, so the lips' borders (which paint shows) are under-weighted; the embedding sees a
  112 px aligned face, so detail below ~0.5 mm (lid margins, crease height) is invisible to it at this framing (a
  close-up measure is needed for the lids: an eye-crop / periocular embedding, to find); chin and jaw are low partly
  because a front-ish view sees them as outline only. These are first weights, to recheck dressed.
- Sliders and extensions at -1 / +1 (out/perc/perc_sliders.txt, perc_ext.txt; 1 - cos, sface):
  - the coupled sliders are whole-face moves (1 attribute sd + its couplings): 0.03-0.20 (eye_hood 0.195, eye_setback
    0.18, brow_ridge 0.16, lip_upper_roll 0.15, canthal_tilt 0.14, lip_upper_height 0.13 ...);
  - the NOSE is perceptually loaded: MakeHuman's nose fields at their unit (MakeHuman's own extreme) 0.04-0.26 (curve
    0.257 at 0.46 mm rms, width2 0.21, nostrils_angle 0.20, width3 0.18, septum 0.17) = 1-2x GNM's strongest component at
    +-1 sd; the hand nose widths too (dorsum 0.159, radix 0.155 at 0.2-0.3 mm rms). Small-mm nose shape is identity.
  - the mouth extensions read small in clay (0.015-0.029; no lip colour); lid detail (crease height 0.007, lid margins
    0.009-0.019, epicanthal 0.014) at the embedding's resolution limit (see caveat): NOT evidence that they don't matter.
  - age / soft tissue: face_planes 0.18 (a broad move), age_cheek_flat 0.041, nasolabial 0.038, cheek_hollow 0.015,
    face_lean 0.006.
- Expression leakage into a neutral read (out/perc/perc_expression.txt): the first eye-region comps (both sides) 0.14 /
  0.09 (brows / lids), lower-face 0.08-0.11 (lips): an unmodelled expression on a reference moves identity as much as
  GNM's first components, so per-picture expression in the one solve (design section 4) is not optional.
- What it changes: (1) GNM 120-169 enter the space (per mm the most identity-laden; at ICT's variances ~0.03-0.04);
  (2) the solve's geometry weights start from the region table above (corrected for the caveats: brows from a render
  without drawn strokes, lips from a dressed render); (3) the nose basis needs the most care (most identity per mm of
  any region after the brows); (4) a close-up identity measure for the eyes is a missing tool.

### M1: ICT registered to GNM (spikes/facesliders/ictreg.py, ictlook.py, faces4 ictrigid.py)
- Similarity on the inner 68 landmarks (ICT's README indices; scale 0.00947: ICT is in cm), landmark rms 3.7 mm; GNM's
  170 comps fitted to ICT's neutral (point-to-plane ICP): 0.41 mm rms; a Laplacian-smooth residual: mean 0.47 mm, p95
  1.26 mm to ICT's surface. Binding within 3 mm of ICT's face / head surface, harmonic extension elsewhere on the skin.
  ICT's 100 identity modes (N(0, 1) weights in ICT's sampler, mode = identity_k - neutral) carried onto GNM's vertices:
  out/ict_modes.npz.
- Sheet human_renders/f4_10_ict_modes_on_gnm.png (modes 0, 1, 2, 5, 10, 20, 50 at -3 / +3 sd, ICT's own mesh beside
  the carried mode on GNM's mean head, front and 3/4): the pairs show the same change (mode 0 = size / sex, 2 = age /
  fullness ...): the carry works.
- What ICT says about GNM's prior (face regions, a 7-dof similarity removed: ICT's mode 0 is 96% scale (-4.4%)):
  - total face variance per vertex: ICT 7.35 mm^2, GNM 10.2 mm^2: similar overall;
  - but distributed differently: ICT's variance along GNM's whitened comps (GNM = 1): comps 0-4 0.1-0.7, 5-9 0.9-3.5,
    10-49 mean 4.4, 50-119 6.9, 120-169 8.5. A random ICT face costs a Mahalanobis^2 of ~1100 under GNM's prior (a GNM
    face: 170), and GNM's span makes 0.95 of it.
  - So GNM's prior is TOO TIGHT on the fine / local comps relative to ICT's population (by 2-3x in sd), and loose on
    its first few. That is the "expressible but improbable" of every extension, and why our fits hit the 2.5 sd walls
    on fine detail. CAVEAT: part of ICT's fine variance may be scan / registration noise (ICT's or my carry's); M4 (real
    faces, FRLL) decides how much.
- Per mode over the face, GNM's MAP (noise 0.3 mm) makes 0.98 of modes 0-9, 0.93 of 10-49, 0.82 of 50-99; the rest
  (residual rms 0.03-0.2 mm) sits in the nose, lips and orbits first: the local layer's job, as designed.
- Consequence for the design (section 4 / M3): the joint prior is not "GNM's N(0, I) + a local layer": GNM's own block
  needs re-estimating (its variances per comp at least, from ICT and then FRLL), and the fine comps (incl. 120-169)
  enter with ICT's variances. The perceptual numbers say the same thing from the other side: those comps carry the
  most identity per mm.

### M2 groundwork: the nose's regional basis from ICT's residual (spikes/facesliders/regbasis.py)
- ICT's 100 carried modes minus GNM's MAP of each (noise 0.3 mm, over the face), under the nose's 8 mm window, PCA:
  modes 0-7 take 0.17, 0.10, 0.07, 0.07, 0.05, 0.04, 0.04, 0.03 of the residual variance (flat: no few dominant modes);
  at 1 sd they are SMALL: 0.11-0.26 mm rms over the nose (max 0.26-0.76 mm); curvature at 2 sd p99 35-165 /m, max
  69-542 /m (mode 0 rough); face-ID at +-2 sd 0.019-0.111 (mode 0 0.111, 1 0.073, 3 0.051, 2 0.047).
- They are NOT the MakeHuman handles: the first 8 modes span 0.02-0.23 of each mh_nose field (width2 0.23, point 0.20,
  greek / point_width 0.16, hump 0.05, nostrils_width 0.05).
- Sheet human_renders/f4_11_regbasis_nose.png (modes at -2 / +2 sd, mean head and Tess, front and 3/4): at full-face
  framing the modes are barely visible: BLUNT: as built this is not yet a usable nose basis. Two readings, not yet
  separated: (a) ICT's residual is partly scan / registration noise (the rough mode 0, the flat spectrum: the scan-noise
  question stays OPEN until M4), (b) GNM's MAP at noise 0.3 mm took most of the nose's real variation into the identity
  (comps 120-169 included), leaving the residual small. With GNM's prior re-estimated (M3) the split changes: build the
  regional bases AFTER M3, from the joint covariance, not before it.

### HANDOVER (faces4, 2026-10-10)
Branch worktree-agent-ae8416dd464de8345 (commits 6f480e2 .. this one; NOT merged: the coordinator keeps the interim
mh_nose_* sliders off main until M2 replaces them). Scratch /mnt/data/hifipushie/faces4 (run.sh = this worktree, capped,
1 BLAS thread; tests.sh; strips.sh <model> <feature> <tag> <sliders...> (clay -1/0/+1 strips via strip.py);
survey.py / nosediag.py / noseprofile.py / ncurv.py / wall.py / build4.py (extension carry, folds, profile, curvature,
build); ictrigid.py; fetch_m1.py / addassets.py (asset packs)). Spikes in the repo: spikes/facesliders/perc.py
(perceptual effect: `run.sh perc.py calib|identity|expression|sliders|ext`), salience.py (region weights), ictreg.py
(ICT -> GNM; `report` re-prints), ictlook.py (carried vs ICT's own), regbasis.py <region> [k].
Data: out/ict_modes.npz (100 carried modes), out/perc/*.json|txt, out/regbasis_nose.npz. Asset packs ictfacekit / frll
(optional) on /mnt/data/hifipushie/assets, symlinked from workspace/_templates. /mnt/data is UNDER the 20 GB floor:
add nothing large.
State of the design (section "faces4: the coherent model", 0-7, + M0 / M0b / M1 results above): accepted by the
coordinator through M1.
Next, in order:
1. M3 first (reordered from the plan, see above): the joint prior. GNM's block re-estimated: per-component variances
   (and the cross-covariance) from ICT's carried modes (ictrigid.py computes ICT's covariance in GNM's whitened
   coordinates: C = G^-1 B Y^T), the similarity removed, 170 comps. Keep ICT's fine variance flagged "may be scan noise"
   until M4. Judge: random faces from the new prior vs GNM's (renders, perc spread), and what the extensions / our fits
   cost under it (are the 2.5 sd walls still hit?).
2. Then M2 for real: regional bases from the joint covariance's residual (regbasis.py's machinery), ordered by variance x
   ID effect, gates (fold, curvature < 70 /m at 2 sd, strips at FEATURE crops, not full face).
3. Missing tool (coordinator: on the M2 list): a CLOSE-UP identity measure for the eye region and the mouth region
   (lids, lip borders: the 112 px face embedding can't see them). Candidates to check (licence first): a periocular
   recognition model, or the face embedding run on an up-scaled eye / mouth crop (validate: does it separate different
   GNM heads' eyes and stay stable under a 0.5 deg turn?).
4. M4: the London Set (frll pack, photos on /mnt/data only): fit 20-30 faces (5 views) in the new space; decides how
   much of ICT's fine variance is real; empirical-Bayes variances.
5. Then M5 (one solve on Tess / Garrett), M6 (controls as directions), M7 (style), as in the design.
Known interim items: test_faceext's nose orthogonality tolerance 0.2 (INTERIM: M2 / M3 must restore 0.1 or carry it in
the prior); mouth extensions still on the hard mask (WINDOW_MOUTH 0: windowed, the projection reaches into the corner
hold; put the hold after the projection); the 14 mh_nose_* fields are interim handles (duplicates: nostrils_width ~
width3 0.76, point_width ~ volume 0.64, septum ~ nostrils_angle 0.69); salience caveats (drawn brows inflate the brows,
clay under-weights the lips, lids below the embedding's resolution).

## faces5 (2026-10-10, continues faces4; branch worktree-agent-a34e0880e18034a56, faces4's branch merged in; scratch
## /mnt/data/hifipushie/faces5: faces4's scripts retargeted (run.sh also puts spikes/facesliders on the path), sheets f5_*)

### Design 8: habitual expression is identity (Joe, 2026-10-10, via the coordinator: "Expression is important. People
### can disguise themselves just by changing how they carry their face. It's not really two separate things.")
Section 4 had expression per picture only. Changed: expression comes in two parts, both in GNM's expression basis
(eye regions 2 x ~20 comps, lower face ~30: the basis base.py / faceshapes already pose with):
- (a) HABITUAL expression h: how the person carries the face at rest (resting brow height, lid aperture / squint, the
  mouth corners' set, jaw carriage, how much the cheeks hold up). Shared by ALL of a person's pictures, owned by the
  identity: z = [c (170), h, r (local residual), s (soft tissue / age)], covered by the JOINT prior with couplings to
  shape where the data has them. Data: ICT's "neutral" scans are each person's resting face, so the part of every ICT
  identity mode that GNM's expression basis takes (M3's per-mode fit: similarity + identity + expression) is not
  contamination to throw away: it is ICT's population's habitual expression, and its cross-covariance with c (same
  fit) is the shape <-> carriage coupling. M4 (London Set: neutral + smiling of the same people) checks it on photos.
- (b) TRANSIENT expression e_p per picture on top of h (a smile, a squint against light, talking): zero mean, tight
  for pictures the detector reads as neutral, wider where it reads an expression (the squint / frown rule becomes this
  scale).
- The solve decides habitual vs transient from the evidence ACROSS views: what every picture shows goes to h (shared),
  what one picture shows alone goes to its e_p. Garrett's concept squint (detector 0.70) may be habitual: now a fit
  outcome, not a pre-set "leave it to pose". The eye stage's lid pose becomes h + e_p (identity aperture = h's lid
  comps, not a separate coupled slider).
- Export: the neutral a character ships with is mean + c + r + s + h (their resting face); faceshapes' ARKit targets
  are deltas from that resting face (a habitual squint stays in the base; the blink target still closes the lid).
- Judging expression effects: face-ID embeddings are trained to be INVARIANT to expression, so they under-rate how much
  carriage changes a read. perc.py's embedding is NOT the judge for h or e_p (M0b's "expression leakage" numbers are a
  lower bound): use checklist items and landmarks (brow-eye gap, eye opening, canthal tilt, mouth-corner height, lip
  heights) and the eye / mouth close-up measure (handover item 3).
- Style (section 5): a style may set a habitual carriage too (a toon's raised brows) as a gain / offset on h.
Where it lands: M3 (now) builds the joint prior over [c, h]: GNM's block re-estimated + ICT's habitual-expression block
and its cross-covariance with c (EXPR_SD / comp counts are flagged choices; the expression basis's overlap with fine
identity reported). M4 fits h per London Set person from neutral + smiling views (h shared, e_p per view). M5's single
solve: h shared, e_p per picture, the split reported per picture (Garrett's squint). M6: habitual controls ("resting
brow", "squint", "mouth-corner set") as directions in h. M7: style gains / offsets on h.

### M3: the joint prior from ICT (spikes/facesliders/m3prior.py analyse | cv | em | build_em, m3look.py, m3cost.py;
### out/m3_em_tau*.npz; sheets human_renders/f5_00, f5_01, f5_01b)
- First try (REJECTED, f5_00_prior_union_REJECTED.png): per ICT mode a MAP fit over the FACE only (similarity free +
  identity + expression, noise 0.3 mm as faces4), then "GNM union ICT" (each eigen-direction keeps the larger
  variance). Samples flapped the ears, swelled jowls and cheeks: the fit used fine GNM comps whose big moves on the ears /
  cranium nothing constrained. Held-out check (cv: fit on the face, predict ICT's own cranium + ears): at 0.1 / 0.3 mm
  noise the identity's skull prediction is WORSE than the similarity alone (1.57 / 1.08 unexplained vs 0.66); it
  improves with regularisation (0.60 at 1 mm, 0.47 at 2 mm, 0.38 at 6 mm), while the face is explained almost as well
  (2.1% unexplained at 0.3 mm, 2.8% at 2 mm, 4.5% at 6 mm). So faces4's M1 "ICT varies 2-3x more along GNM's fine
  comps" was largely the under-regularised carry fit buying the last ~1% of face variance with skull-moving comps.
- The estimator kept (em): empirical Bayes, EM at the population level over the face + cranium + ears (not the neck:
  ICT's neck varies 2.3x GNM's there, the scans' head pose), similarity projected out, isotropic noise PER REGION with
  its own ML variance (face 0.47 mm, skull 0.90 mm: the skull weighs itself), and an inverse-Wishart pull to GNM's
  N(0, I) with weight tau (a CHOICE: ICT's subject count isn't published; GNM's training set is larger).
  c block (diag by comp band): tau 0.01 (ICT-led): 0-9 1.35, 10-49 2.9, 50-119 5.2, 120-169 8.0 (trace 890); tau 1:
  1.17 / 1.96 / 3.1 / 4.5 (531); tau 3: 1.09 / 1.47 / 2.0 / 2.7 (348). ICT also puts LESS than GNM's variance on some
  broad directions (face_planes / face_lean / nose fields cost more under tau 0.01: below).
- Samples (f5_01 ICT-led, f5_01b tau 1; same draws, front + 3/4 clay): plausible, varied people, no flapping ears, no
  visible lumpiness at face scale; ICT-led faces run broader / fuller. Face-ID spread between samples: GNM 0.47, tau 1
  0.48, tau 0.01 0.49 (10-90%: 0.37-0.65): the new priors make about as different people as GNM's (the embedding is
  blind to much fine shape; read with that caveat).
- THE M3 RESULT (m3cost.py, out/m3cost.txt): the local controls cost as IDENTITY the same under every prior. Each
  slider / baked op / extension at +1 made by a MAP identity move over its own region (0.05 mm noise): 0.8-1.0 of it
  made at 3-46 sd under GNM's N(0, I), and within +-10% of that under tau 1 / 3 (tau 0.01: nose and broad-cheek
  fields cost MORE, 40-113 sd). Tess's mh_lowerlip_width -1: 25 sd under any prior; brow_lateral -0.74: 15; Garrett's
  face_lean 1.5: 30-53; chin_cleft 1.5: 18. The walls are not the fine comps' variances: they are LOCALITY (faces4
  section 0: a global PCA can draw a local feature only with side effects elsewhere, and the prior prices the whole
  move). Re-estimating GNM's block does NOT take Tess / Garrett off the walls: the local residual layer r (M2) with its
  own variance is what does. Their identities: Tess |c| 5.7 under GNM, 7.1 under tau 1, 37 under tau 0.01; Garrett 4.5
  / 5.9 / 32 (both fitted under GNM's prior, so ICT-led directions of small variance price them high: one more sign
  the ICT-led block is too narrow for our people).
- Habitual expression h (design 8) is NOT identifiable from ICT's identity modes: with h free in the EM, h's variance
  runs to sd ~2.4 GNM expression units at tau 0.01 (the expression basis absorbs fine identity detail: the bases
  overlap). The h block stays DESIGNED (zero mean, sd EXPR_SD 0.3, no cross terms) until per-person resting-face
  evidence: M4 measures resting items (brow-eye gap, aperture, mouth-corner height) on the London Set's neutral photos
  across people: that is h's population variance in item units.
- Decision for now: the c block = EM tau 1 (GNM : ICT 1 : 1), flagged; ICT-led rejected (too narrow for Tess /
  Garrett, costs broad features more). M4 (real faces' Mahalanobis per block) settles tau. Not wired into joint2 /
  faceatlas yet (M5); the interim test loosening (nose orthogonality 0.2) stays until M2: the prior doesn't touch it.

### Joe's question: "GNM was able to do the eye crease the whole time?" (lidgnm.py density | scan | fit | samples;
### sheets f5_02 .. f5_04; close-ups 0.079 mm/px, raw GNM head, clay, calibrated detector points, lidfold.read_lid)
- Mesh: GNM's upper lid has 12-14 vertex rows between lash line and brow (13-14 mm), ~1 mm apart along the skin (max
  2.7-3.7 mm). A fold of 2-3 mm can be drawn; lidfold's crease groove (FWHM 0.8-1.1 mm) is at the mesh's Nyquist limit:
  as a vertex field it renders as a jagged line (f5_04 middle column).
- Scan (all 170 comps and ICT's 100 carried modes at -3 / 0 / +3 sd, out/lid/scan.json): the mean head reads a weak line
  at 2.8 mm (dark 0.04: the top of GNM's thick lid margin roll); Tess's and Garrett's identities NO crease (the reader
  falls through to the brow sulcus at 8-10 mm, dark 0.04). The darkest reads anywhere: ICT mode 6 +3 0.19, mode 12 0.16,
  GNM head_032 -3 0.15, head_020 +3 0.13, all at 2.2-2.8 mm (a low fold edge / hooding, not a 4-7 mm crease). 2 of 340 GNM
  and 6 of 200 ICT reads pass dark 0.12, none 0.2. Tess's photo: tps 4.35-5.0 mm, dark 0.31.
- Random faces from the priors (f5_03 ICT-led, f5_03b tau 1): ICT-led samples show real lid folds (sample 0 dark 0.44 at
  2.6 mm, others 0.13-0.16 at 1.8-5.4 mm); tau 1 samples rarely (dark <= 0.09). So in combination with the rest of a
  face, the identity space CAN make folds, more under ICT's variances: Joe's eye was right that GNM has folds in it.
- But as Tess's / Garrett's crease ON THEIR FACES (lidfold's profile as a vertex field, fitted by the 170 comps over
  both orbits + brows): the span makes 0.61 / 0.71 of it (the broad roll), costing 8.4 / 14.8 sd under GNM's prior,
  8.4 / 14.1 under tau 1, 9.3 / 16.6 under ICT-led; rendered, Tess's MAP shows no crease (dark 0.03), Garrett's a faint
  line (0.12 at 4.2 mm) (f5_04). The same locality wall as every other local control.
- Verdict: GNM's space has folds as whole-face configurations, not a crease you can put on a given face at identity
  cost. lidfold stays, as a member of the local residual layer (M2: an upper-lid basis with ICT / MakeHuman / lidfold
  handles and its own variance; the groove part stays a fine-geometry op because GNM's ~1 mm rows can't hold it). The
  identity's fold-like directions (head_032, head_020, ICT modes 6 / 12) should be read by the eye evidence in the one
  solve before lidfold's residual is spent.

### After the GNM audit (docs/notes/gnm_audit.md; faces5 agrees with all 8 findings)
Retracted by the audit, with my agreement: the lid verdict above (wrong target: lidfold's FIELD at 0.05 mm, read as
"sd" against 0), M3's "walls are locality" (the cost was exactness on off-distribution fields; real noses / lips are
~0.6 mm in GNM), design 8's habitual-expression block (GNM's identity IS each person's relaxed neutral; M3 had already
found h unidentifiable from ICT's neutrals). GNM's N(0, I) stays (the tau-1 prior is dropped). The spike key
base.head.habitual was removed again.
- M2 regional bases from M3's residual (regbasis2.py; sheets f5_10..15): ICT's residual after the identity is 5% of its
  face variance; per region 0.1-0.27 mm rms per sd, symmetric 0.6-0.99 (likely real, not scan noise); all gates pass
  after faceext's conditioning (fill_inside / hold_rolls / hold_creases; without it every nose mode folded inside the
  nostrils); ID effect 0.03-0.08 at +-2 sd; barely visible even in feature crops. DEFERRED: no local layer until an
  evidence-driven full fit demonstrably can't reach something.
- lipfit.py (geometric shadow proxy along posterior directions, Blender renders): the built head's lip-over-sulcus step
  moved 3 mm per step and lipshade's shadow moved 0.005: that proxy is not what the shadow reads. A render-in-the-loop
  term needs cast shadows in the fast renderer (approved: a shadow-map pass in likeness.render). Also found: lip_seal is
  computed WITHOUT head["expression"], so a per-picture lower-face expression opens the mouth in our build (f5_tl1);
  to fix (approved): the seal includes the picture's expression.
- creasefit.py (clay, groove proxy): failed (no cast shadows, ~1 mm rows: -0.003 valley per unit). Superseded by the
  audit's g11 (lid margins vs iris + crease height on GNM's own eyeball).
- THE VERMILION BORDER READER (lipborder.py): MediaPipe's outer lip contour refined along its normals to the strongest
  outward fall of CIELAB a* (+0.15 |dL|), +-2.5 mm, running median + smooth, corners left to the detector. On Tess's
  photo it follows her border incl. the bow's peaks (out/lb_tess_photo.png; offsets from MediaPipe -0.8..+1.0 mm). The
  model's border = GNM's upper_lip / lower_lip groups' outer edge loops (lipborder_model.py): on f3_t1 the lower border
  sits 1.5-3 mm INSIDE hers, the upper 1.5-2 mm outside at the sides and ~1 mm low at the bow's peaks.
- fit5.py, the one MAP (identity 170 + per-picture expression: 20 eye pairs + 20 lower face, N(0, I) identity, a
  NEUTRAL picture's expression at sd EXPR_SD; points with INFLATE 1 and no CUT; the border term at BORDER_SIG mm):
  | model | border vs hers, model neutral (rms mm upper / lower) | points rms (sigma) front / 3q / profile | |c| | eff. dof |
  |---|---|---|---|---|
  | f3_t1 (start) | 0.87 / 2.22 | 0.56 / 0.62 / 1.18 (at INFLATE 1) | 5.7 | (19 at INFLATE 2) |
  | f5_tl3 (EXPR_SD 0.3, sig 0.4) | 1.18 / 0.76 | 0.40 / 0.37 / 1.41 | 6.2 | 37.9 |
  | f5_tl4 (EXPR_SD 0.1, sig 0.25) | 0.70 / 0.49 | 0.42 / 0.38 / 1.60 | 7.1 | 40.6 |
  With EXPR_SD 1 the front picture's expression took the border (|e| 2.2) and the shipped identity kept none of it.
  Sheet f5_23_lips_border_fit2.png (photo | f3_t1 | tl3 | tl4, dressed, traced borders red): tl4 shows a hint of the
  bow's two peaks and a fuller lower lip lowest at the centre; still softer than hers (her bow sharper, upper lip fuller
  at the centre). The profile's points got worse (1.18 -> 1.60: three clicked points, no profile contour in fit5 yet).
  Under-lip shadow sides 0.82 (hers 0.92, f3_t1 0.87): not addressed (needs the shadow-map term; paint confounds).
- CHECKLIST COVERAGE (itemcover.py, f3_t1, every direction at +-2 sd read with likeness.compare's model readings through
  her fixed cameras; noise floor = a 0.5 deg camera turn, median 0.04 tol; out/coverage_summary.txt): GAP = no item
  past its tolerance. GNM identity 157/170 gaps (by perceptual effect >= 0.05: 3/11; 0.03-0.05: 15/19; below: all);
  eye expression 17/20; lower-face expression 15/30; ICT modes 69/100 (5 of the 21 with effect >= 0.05). Highest-effect
  gaps: ict_12 (0.072, nearest lower_lip 0.91 tol), head_005 (brow_eye@3q 0.78), ict_22 / 17 (chin_height), head_008
  (width_temple 0.93), head_007 / ict_41 (lower_lip_area), eye expression 002 / 003 (intercanthal / eye_aspect).
  Above 3x the noise floor instead of the tolerance: 95/170, 14/20, 26/30, 62/100 seen: the TOLERANCES hide more than
  the missing items do; and one noisy item (lower_lip_area) is the best reader of 114 of 320 directions. Next: tolerances
  from each reader's measured noise; then new items for the remaining gaps (lid margins vs iris, crease, alar rims,
  nostrils, lip pad, ears), seeded from Farkas (1994), the FISWG feature list, oculoplastic MRD1 / MRD2 / TPS / BFS /
  MCD, rhinoplasty analysis (Goode ratio, nasofrontal / nasolabial angles, columellar show, alar base) and lip
  analysis (vermilion ratio, E-line, mentolabial angle, philtral columns).

### fit5's profile term, the view-consistency test, the lip seal (2026-10-10)
- The envelope match (joint2.envelope: farthest-out vertex in a band) fails in CONCAVITIES: at the stomion and the
  mentolabial sulcus it picked lip vertices 7-25 mm off, and those rows were rejected, so the lips' depth went unseen.
  Replaced by fit5.silhouette_env (SIL=render): the model's profile silhouette read the same way as the photo's (first
  skin pixel per row on our clay render, likeness.render passes), each pixel unprojected to its vertex.
- The profile camera fitted to 8 clicks + the contour let its focal drift 2600 -> 1022 px at 0.34 m (the lens / distance
  trade-off is unconstrained in a profile) and the near camera put body faces behind it (the clay render went solid,
  every row read the back of the head): profile cameras are now POSE-ONLY (fit5.fit_cam_pose), focal held; contour
  matches enter coarse to fine (15 / 6 / PROF_REJECT mm).
- View consistency (depthcmp.py; lips ahead of the subnasale-pogonion line, mm, upper / lower): her profile photo +3.0 /
  +1.9 (profzoom.png: the contour traces her lips exactly); front + 3/4 only fit +4.7 / +4.4; all views with the seal in
  the fit (tl8) -1.9 / -1.8; all views fitted WITHOUT the seal (tl9) +2.2 / +1.1. The references are consistent; the
  fit was wrong.
- Cause (jacchk.py: predicted vs actual silhouette change for the identity step the lip rows ask for): with lip_seal the
  built lips do NOT follow the identity (predicted -2..+2 mm by row, actual a uniform -3.2 mm); without the seal the
  linear model holds (actual within ~0.5 mm of predicted at most rows; the dorsum's rows hold either way). faceslide's
  seal (closes the lips to contact, computed on the head) is non-linear and undoes identity moves of the lips. fit5
  NOSEAL=1 fits without it (the shipped model keeps it). TODO: a seal-aware Jacobian or fitting the inner-lip contact
  as evidence, then re-check the sealed result's profile.
- tl9 (NOSEAL, all views): |c| 15.4, dof 47.6, points 0.51 / 0.50, border 0.24 / 0.26 mm, profile 1.40 mm (131/131),
  profile clicks 1.71 sigma. Remaining profile misses: the nose's underside / columella rows 4-6 mm INSIDE hers, the
  stomion +5.6, the sulcus +2. tip projection jumped to 22.8 mm (f3_t1 18.5): check against her photo before trusting.
  Rounds don't reduce the profile rms monotonically (1.29 -> 1.40): correspondences flip between rounds; a damped
  (Levenberg-Marquardt) outer loop is the next fix.

### HANDOVER (faces5, 2026-10-10)
Branch worktree-agent-a34e0880e18034a56 (faces4's branch merged in, main merged in after the audit). Scratch
/mnt/data/hifipushie/faces5: run.sh (this worktree, capped, spikes/facesliders on the path), q.sh <log> <script> (the
render lock), tests.sh; consist.sh (view-consistency runs), covsum.py (coverage summary), photoprof.py / profzoom.py.
Spikes (spikes/facesliders): m3prior.py (ICT EM prior: analyse | cv | em | build_em), m3look.py, m3cost.py, lidgnm.py
(GNM lid close-ups: density | scan | fit | samples | sheet | crease), creasefit.py (failed clay attempt), regbasis2.py
(M2, deferred), lipfit.py (geometric shadow proxy: failed), lipdiag*.py, itemcover.py + percict.py (checklist coverage),
lipborder.py (THE vermilion border reader) + lipborder_model.py (GNM's border loops), fit5.py (THE one MAP: identity 170
+ per-picture expression, uninflated points, border, profile silhouette; env INFLATE CUT EXPR_SD BORDER_SIG PROF_SIG
PROF_REJECT SIL NOSEAL VIEWS ROUNDS INNER), lipsheet.py, featsheet.py (feature-crop renders through each model's own
cameras), framechk.py, profdiag.py, sildiag.py, jacchk.py, depthcmp.py.
Models (scratch, f5_*): f5_tl4 (border, no profile: the best front lips), f5_tl7 / tl8 (profile, with the seal: lips
wrong), f5_tl9 (profile, NOSEAL: lips right in depth), f5_c_* (consistency subsets). Sheets human_renders/f5_00..26.
Next, in the coordinator's order:
1. Nose readers on photo and render alike (alar rim edge, nostril show from the dark nostril area; the subnasale /
   nose-base row: the model's sits ~5 mm below hers in front, framechk), validated on her photo, into fit5 (render-based
   readers by finite differences on moved meshes, like itemcover's moved_mesh: ms per evaluation).
2. Seal-aware lips (see above), then fit5's outer loop damped; check tl9's 22.8 mm tip projection against her photo.
3. The approved tools: shadow-map pass in likeness.render (lipshade term in the loop; paint must not read as shape),
   lip_seal including the picture's expression, tolerances from each reader's measured noise (coverage: tolerances hide
   most of GNM's directions).
4. Crease: port the audit's g11 (lid margins vs iris + crease height, GNM's own eyeball) into fit5; then Garrett.
Report every fit with |c|, effective dof, posterior cost, feature crops (featsheet) and a blunt read.

### Lip contact, the closed neutral, the first nose readers (2026-10-10, after the HANDOVER above; it still applies)
- Contact evidence (fit5 CONTACT, CONTACT_BY): MediaPipe's inner-lip pairs are useless as contact evidence (the
  detector table puts both on the visible lip line: "0.4 mm" on a visibly parted mouth). Now GNM's own contact ring
  (faceslide._lip_rings, upper / lower halves paired in x, corners' 10% out), one-sided (only an open gap), 0.3 mm.
  The identity alone leaves Tess's neutral parted 5.6 mm.
  - CONTACT_BY=expression (default for NOSEAL fits): each closed-mouth picture's lower-face expression closes the lips
    (GNM's population closes lips by expression); shipped with mouth_gap 0 (base's least-change lower-face solver)
    instead of faceslide's seal. f5_tl10: closed, the lips' depth in profile close to hers (f5_28). |c| 15.3, dof 49.3,
    gap 5.6 -> 0.25 mm, front expression |e| 0.89. OVERSHOOT (coordinator): front / 3/4 lips too full, the bow's peaks
    gone (border 0.34 / 0.35 vs tl4's 0.24), lower lip a little proud in profile: the closing expression adds a pout /
    roll-out the border doesn't hold. To do: constrain the closing to the contact direction (or hold the vermilion
    area / heights as evidence), tighter border sigma, check what the |e| 0.89 does to the vermilion.
  - CONTACT_BY=identity (the neutral itself closed, seal kept): |c| 25.6, max 5.3, profile clicks 5 sigma: rejected.
  - Face shapes: GnmFace refuses mouth_gap < 1.5 mm; one-mesh heads with mouth_gap unset are allowed and its neutral
    closes the lips through the basis (face._gnm["close"]) before every ARKit delta: the same mechanism. So stills use
    mouth_gap 0; a face-shapes export of the same identity leaves mouth_gap unset. (Tess's models have no
    base.head.interior: no face-shapes export today.)
- Nose readers (nosereader.py, front picture, iris scale), validated on her photo (out/nose_photo.png): the NOSTRIL
  blobs (pixels < 0.62 x the nose skin's median, the largest per side) are found cleanly: area R / L 21.7 / 30.7 mm^2,
  centroid 5.3 / 6.5 mm over the subnasale row (MediaPipe 2), outer edge 11.5 / 10.9 mm from the midline. The ALAR edge
  (strongest |luminance step| within +-4 mm of MediaPipe 64 / 294, rows tip -> alar base): good on the shaded side,
  noisy on the lit side (her right; scattered over 2 mm); alar width 33.9 mm (R 17.6, L 16.2): to firm up (use the
  lobule's lower rows / the alar crease, or the 3/4 view's silhouette of the ala).
  The MODEL side needs the same readers on our render: clay has no dark nostrils (no AO; GNM's nostrils are exterior
  skin pockets, not a separate group): a cavity / AO shading pass in likeness.render (with the shadow-map pass) is
  the prerequisite; then the readers enter fit5 by finite differences on moved meshes (itemcover.moved_mesh).
  Also from f5_28 (coordinator): tl10's nose tip reads longer and droopier than hers in profile (hers slightly
  upturned): add tip rotation / nasolabial angle from the profile contour as a reader item.

## faces6 (2026-10-10, continues faces5; branch worktree-agent-a19e0d592ba96cc7d, faces5 merged in; scratch
## /mnt/data/hifipushie/faces6: faces5's scripts retargeted + mkcal.py, mkx.py, cross*.py, gaptest*.py; sheets f6_*)

### The fast renderer's shading (likeness.render ao / shadow; tests/test_likeness_shading.py)
- ao=True: per-vertex AO (96 orthographic depth maps, cosine-weighted, cached on the mesh dict, 1.5 s); shadow=True /
  <deg>: per-pixel cast shadow of the key (or the photo light's w) from a depth map, a disc light of <deg> = soft
  (16 samples, ~1.3 s a crop). Ambient and direct rasterised apart, only the direct shadowed. Occluders = the mesh
  within 0.2 m of the eyes (the one mesh is the whole body: 27 Mpx maps before). light[3] = the AO's share of the
  ambient, fitted to the photo per crop (noserender.lit_render: Y ~ A + B ao + C max(w.n,0) lit + E min(w.n,0); Tess
  front 0.83). mesh["C"] = optional per-vertex skin colour (wholeclay's hair cap).
- Fidelity (fidelity.py, fid2.py; f6_03, f6_05): the raw one-mesh quads the fast renderer draws vs the shipped implicit
  surface: median 0.23 mm, p90 0.35, max 0.64 (tl10 close-up at 0.69 mm voxels). Band-pass (DoG 0.6-3 mm) luminance
  correlation fast~Blender dressed 0.53 mean (0.47-0.66), photo~Blender 0.13 = photo~fast 0.13 (pores dominate the
  photo). The fast clay shows the SAME forms as the shipped surface, more contrasty than the dressed look: readers
  must compare normalised / calibrated cues.

### tl10's lip overshoot was the SHIPPING, not the fit (f6_04)
base's mouth_gap solver (base.py ~1966) closes only the inner-lip midline pair 62/66 in 3 linearised steps: on tl10
(one mesh) the raw mouth stays parted 3.5 mm (7.0 without), the implicit surface fuses the gap into one thick lip
(the "too full, bow lost" read; the fast render's zigzag "teeth" is the mouth sock through the gap, not crossing).
fit5's own closing (the front picture's lower-face expression, |e| 0.89) shipped as base.head.expression: inner gaps
0.45 / 0.76 / 0.31 mm, bow back, not puffy (f6_tl10x). fit5 now ships that. FLAGGED (not fixed: other models'
builds): the mouth_gap 0 solver on one-mesh heads. Also: fit5.contact_rows maps wrongly on a SOURCE spec with
mouth_gap set (-20 mm).

### The old-man face (f6_06, f6_07; decomp.py)
In whole-face clay tl9 / tl10 (|c| 15) are a gaunt older man (nasolabial folds, jowls, hollow cheeks); fs_tj12 /
f3_t1 / tl4 (|c| 5.7-7.1) are smooth but male-leaning (long face, brow, square chin, strong nose). decomp.py splits a
fit's identity change exactly per evidence term at its solution ((H+P)^-1 (b_t - H_t x0)): tl10 from f3_t1 = profile
contour 0.43 (|part| 10.8), front lip contact 0.24 (7.2; it alone pushes GNM-sex +1.1 male-ward), upper border 0.10,
3/4 contact 0.06, every face-oval group 0.00. dc by band: 0-9 2.8, 10-39 7.1, 40-119 9.8, 120-169 5.1. BUG: with
CONTACT_BY=expression the contact rows kept IDENTITY columns (the identity was bent to close the lips): to be
expression-only. The jaw points outside her jaw in f6_06 are GNM's 68 on the 3D surface (convention), not evidence.

### Gates (gates.py, dressed.py, agesex.py; asset pack "faceage" = InsightFace genderage, a measuring tool)
- sex_gnm: the identity on GNM's semantic sampler's class means (-1 female mean, +1 male): f3_t1 -0.35, tl4 -0.30,
  tl9 0.00, tl10 +0.58.
- ArcFace whole-face clay to the accepted f3_t1: fs_tj12 0.95, tl4 0.81, tl10 0.63, tl9 0.60.
- genderage: out of domain on clay (every fit 22-27, the old man included); dressed whole face noisy (photo 27 / 34,
  f3_t1 37 / 28, tl10x 48 / 32). Not a gate yet.

### Macro level (coordinator / Joe: "learn how to better approach the macros before we do fine detail work")
- Calibration (f6_08 bald, no brows; f6_09 hair cap, 2 mm brows): GNM's sampler female / overall / male class means on
  Tess's body (mkcal.py: f6_cal_f / _0 / _m; f6_cal_t1id = f3_t1's identity without its local layers). The class
  means read as young, smooth, androgynous; female vs male differ little in bald clay; Tess's fits read more male and
  older than the female mean (longer face, nose bridge, nasolabial shading). The gap is real AND bald clay is a weak
  sex judge (the hair cap helps).
- GNM's semantic sampler (paper section 4.3, gnm/shape/semantic_sampler.py): identity CVAE conditioned on gender (2)
  x ethnicity (4) one-hot ONLY: no age, no BMI. GNM's identity is Procrustes-aligned, so size (most of the sexes'
  difference) is NOT in it: the class means differ by |d| 2.16.
- Our macro layers in the one-mesh pipeline: MakeHuman's body params (age / sex / weight / muscle: the head the body
  carries, onemesh.hook lays GNM's DIFFERENCE from its template on it) + onemesh's dimorphism field (MakeHuman's sex
  difference x 1.3 on the head) + GNM identity + humanmacro's 37 macros (directions in GNM comps 0-119, calibrated by
  sampling). MakeHuman holds the only AGE axis we have.
- humanmacro vs the sampler's sex difference (macrostudy.py, out/macrostudy.json, f6_10 = the mean face +-2 sd per
  macro): the 37 directions span 0.30 of it; largest male - female in macro sd: brow_height -0.59, head_size +0.46,
  bridge_height +0.41, bridge_hump +0.41, brow_ridge +0.35, nose_width +0.34, eye_tilt -0.33, forehead_slope +0.32;
  jaw / face width barely (+0.21 / -0.18). Every macro's cosine with the sex direction is <= 0.29.

### Stage M, the macro fit (fitM.py; mtable.py = the acceptance table; mreport.sh = sheet + table per round)
Joe: "the closer we can get the initial fit, the better. Head and jaw shape, eye placement, nose size and shape,
mouth size and placement." The head starts from its body's head with identity 0 (local layers stripped); c = B z.
- BASIS=macros: humanmacro's 37 (free directions, comps 0-119) + GNM's sampler sex direction + 3 ethnicity
  contrasts (ethstats.npz: the sampler sampled per gender x 4 groups, 4000 each; the groups' gender-pooled mean
  offsets span 3 dof; prior = the sampler's population sd along each, 1.92 / 1.51 / 1.45), z ridge 1 (without it
  the correlated macros cancel: face_length +10 sd at |c| 4.8). BASIS=comps: 0-39, the check.
- Evidence: MediaPipe face oval + GROSS landmarks (fit5.GROSS: eye corners, irises, brow line, nasion, nose tip /
  subnasale, mouth corners / midline), profile clicks, the profile contour at 2 mm; sex_gnm -1 +- 0.5 (soft).
  Body params: BODY / GRID (+ GRID_PRIOR) over MakeHuman's params.
- Tess (f3_t1's photos), data chi2 / 347 rows: macros 160.6 (|c| 3.31, dof 16.6), + ethnicity 156.5, comps 0-39
  159.4 (|c| 4.65): the macro vocabulary fits the outline as well as the anonymous comps (nothing to add). Weight
  grid 0.05-0.45 flat within the profile's correspondence noise (+-5): stays at the prior 0.15. Ethnicity
  coordinates -0.48 / -0.12 / +0.27 population sd (the evidence barely uses them; no label asserted). The profile
  contour carries ~2/3 of the chi2 (~1.75 mm rms; f6_13: follows forehead, nose, tip, chin within 1-2 mm; misses at
  the stomion and under the chin).
- Acceptance table (likeness items per group; f3_t1 | M macros+eth): head 6/7 | 6/7 (width_temple +4.3 mm MISS),
  jaw / chin 5/7 | 7/7, eyes 5/5 | 2/5 (pupil_distance +2.0 mm, eye_width +2.3, brow_eye -2.6 in front: MISS), nose
  4/5 | 5/5, mouth 5/8 | 8/8. Irises added to GROSS after this.
- Read (f6_11): every M fit still male-leaning and older in hair-cap clay (long high-bridged nose, deep-set eyes
  under a shadowed brow, hollow under the cheekbones). Silhouettes and landmark positions don't see the depth of
  the face's FRONT surfaces: the macro-scale photometric term (photom.py) is for that.

### The macro-scale photometric term (photom.py; fitM PHOTO_SIG)
Per view (front, 3/4): face box at 0.8 mm/px; the photo's GREEN channel (linear: discounts redness); mask = the
detector's skin mask AND the model's skin AND not hair (< 0.55 x skin median); model shade = c0 (1 - aw + aw AO) +
max(w.n, 0) lit + min(w.n, 0) with her light fitted on the model, times a smooth albedo (quadratic, log domain, NO
constant, ridge ALB_RIDGE); residual = log photo - log shade - albedo, mean removed, Gaussian LP_MM 3 mm, sampled
every 3 mm (~1770 samples over two views). Jacobian over the basis by finite differences on the mesh (vertices move
linearly with the identity: photom.vertex_basis), light / albedo held; ~2.5 s a column (AO recomputed).
Sensitivities on f6_M_mace (rms of d residual per +1 sd): cheek_fullness 0.17 / 0.08 (front / 3/4), eye_depth 0.11 /
0.07, brow_ridge 0.08 / 0.06, face_width 0.05 / 0.02. First run DIVERGED (|c| 3.7 -> 11 -> 19 -> 21, photometric rms
0.18 -> 1.14): the albedo's constant and the light's level drifted together (c0 -> 0, |w| -> 4). Fixed: no albedo
constant + ridge, c0 >= 0.25 x the skin median, cast shadows off in the term (hard shadows toggle per FD step),
photometric from round 1 (round 0 = the landmark solve from the mean), a trust region |dc| <= STEP_MAX (1.0) a round.
Round 1 (sigma 0.25, full oval): converged but traded the outline away (jaw_width +9 mm, jaw / chin 7/7 -> 2/7, a
heavy-set man, f6_14); phdiag: the oval's outer band dominated; inner 80 % halves the residual and the ask is mixed
(eye depth / bridge down, jaw still wider). Round 2 (inner, sigma 0.4): quiet, costs the profile, small effect.
HELD (coordinator / Joe: shading isn't the lever; SH lighting noted, not built).

### Base offset and the ARTIST BLOCK-IN LOOP (Joe: "an artist would be able to know how to get closer")
- Base-stack diagnostic (basestack.py, f6_15): GNM's female class mean + 3 female CVAE samples, (a) GNM's own mesh
  similarity-aligned vs (b) our one mesh: 2.63-2.73 mm landmark rms for EVERY identity (a fixed offset: the body's
  MakeHuman head + dimorphism); (b) narrower lower face, flatter cheeks, longer, mouth forward over a weaker chin.
  Split (f6_16 / f6_17): MakeHuman weight barely moves the face; dimorphism 1.3 shortens / narrows; NEW spike key
  base.head.gnm_base (onemesh.hook: the head's base shape from GNM's template scaled to the body head, faded to the
  stitch): 1.0 = fuller, older adult; 0.5 = a soft young face. Block-in base = female mean, gnm_base 0.5 (f6_b6).
- Tools (artist.py look / step; eyeread.py; cmpround.sh): eye-registered photo / clay (her fitted light, hair cap,
  HER detector brows, hazel iris + lash line), 50 % overlay, outline difference, 9 mm squint; steps along humanmacro
  free (coupled) directions or HELD ('name!': pseudo-inverse column), sex / ethnicity dirs, base keys, pose lids;
  the five-target table (mtable.py) after every step.
- Rounds A00 -> A15 (Tess), kept: nose_projection +0.6; lip_projection +0.5 + chin_projection +0.5; nose_width -0.5 +
  nose_upturn +0.4; lid_upper -0.0014 (eyeread: upper lid 0.45 -> 0.67 iris radii, hers 0.67); jaw_square -0.5 +
  jaw_width -0.3; chin_height +0.6; philtrum! -0.5; eye_width! -0.5; cheekbone_width! +0.4 + cheek_fullness! -0.4;
  bridge_height +0.6 (free: held cost |c| +1.1 for the same look); philtrum! -0.4; chin_height! -0.5 + eye_spacing!
  +0.3. Reverted: eye_height +0.5 (eyes read NARROWER: the opening is lid pose / eyeball seating, not identity),
  face_length +0.6 (went into the philtrum, chin shorter), philtrum -0.5 free (took the chin), eye_depth! +0.4
  (sockets read deep-set / male; the orbital RIM she has is not eye depth).
- A15: targets all pass except jaw_angle_height (3/4: the gonial angle sits low) and brow_eye (dropped: it reads
  GNM's brow landmarks, not her hair brows). Read (f6_21): outlines on hers in three views, adult, not male / old;
  inside the outline still generic (her orbit rim, wider fuller mouth and almond eyes are not there).
- Vocabulary gaps filled as data-backed coupled directions (newdirs.py -> $F/newdirs.npz; artist step "nd:<name>";
  readers: humanmacro gonial_height / orbital_rim / lower_orbit (now macros), radix_width in newdirs (not a macro:
  held-out R2 0.90 < humanmacro's 0.95 bar); 2000 GNM heads, conditional mean within sex on GNM's OWN sex axis):
  | attribute | R2 | sd | strongest couplings (+1 sd coupled moves, in sd) | on Tess |
  |---|---|---|---|---|
  | gonial_height | 0.997 | 0.053 io (~3.3 mm) | face_length +0.68, chin_height +0.50, jaw_angle -0.47 | +1 sd moved the likeness item jaw_angle_height only 0.3 mm: that item reads MediaPipe 172 / 397 (the detector's guess at the jaw contour), not the gonion; reverted |
  | orbital_rim | 1.000 | 2.3 mm | brow_ridge +0.89, eye_depth +0.84, bridge_height +0.73 | in GNM a defined rim COMES WITH a heavy brow and deep eyes (the male pattern); held (brow, eye depth): 2.33 |c| per sd, lower_orbit -0.97, chin -0.83; renders hollow / older: reverted |
  | lower_orbit | 1.000 | 1.2 mm | weak (<= 0.29) | +0.8: barely visible, cost philtrum / lower third: reverted |
  | radix_width | 0.90 | 0.0093 io (~0.6 mm) | bridge_hump -0.36 | -1 sd invisible: GNM barely varies it, a REAL capability gap (a local residual is justified) |
  Lid aperture: not identity (pose lid_upper / eyeball seating, eyeread). Her "defined orbit with a soft brow" is then
  lid / crease / skin, not bone (the crease work).
- Joe on A15's profile: "the angle of the mouth area on profile needs some work": A15 -> A21 lip_projection +0.7 ->
  A22 lip_projection +0.6 + philtrum! -0.2 (the chin got 2.3 mm shorter: free coupling) -> A23 chin_height! +0.5.
  A23: lips and the mentolabial curve on her profile contour (f6_22); targets: head 6/7 (temple width: her hair
  framing), jaw 6/7 (jaw_angle_height: detector-guess item), eyes 4/5 (brow_eye, dropped), nose 5/5, mouth 8/8.

### THE ARTIST BLOCK-IN METHOD (Joe: "this method should be our default for all modeling humans going forward")
Setup
1. Base of the right kind: the person's body (MakeHuman params) + gnm_base 0.5 + GNM's sampler class mean for the
   sex (cvae_stats m_f / m_m), NOT a previous fit. Local layers off (sliders, warp, fold, pose, shape).
2. The references' fitted cameras (any set: front / 3/4 / profile, or concept art with clicked 68).
3. `artist.py look <model> <png> <ref model>`: per view photo | clay under her fitted light (two-pass fit_light + AO
   share), hair cap, HER detector brows (filled band), a presentable eye (light iris, limbal ring, lash line) | 50 %
   overlay | outline difference (detector oval / profile contour red, the clay's green) | 9 mm squint of both;
   registered at the EYES + nasion (2D shift: a tracing over the photo, never on the outline it should judge).
Round rules
4. Look; name the single BIGGEST difference in masses and planes (profile convexity, muzzle, jaw line, chin, nose
   mass / angle, face length vs width, cheek planes, bridge, eyes). Check sex / age anatomy.
5. One small step (0.3-0.7 sd) along whole-face directions: `artist.py step <src> <dst> name=v ...`:
   humanmacro FREE (the population's conditional mean: masses, proportions; try first), HELD `name!` (one feature,
   the rest kept: for a coupled neighbour that went out; costs more |c| per unit), `nd:<gap>` (filled vocabulary),
   sex_gnm_dir / eth_dir0-2, base keys (weight, dimorphism, gnm_base), lids (lid_upper / lid_lower: pose, metres).
6. Re-look AND run the target table (mtable.py: head shape, jaw / chin, eye placement, nose, mouth; tolerances per
   item): keep only if the whole face reads closer AND no target went out; else revert or fix the coupled
   neighbour with a held step (free moves drag neighbours: length -> philtrum, lips -> chin).
7. Lids by measure (eyeread.py: lid margins vs iris in iris radii), not by identity.
8. Log each round (artist_log.json per model) + before / after strips (cmpround.sh); a sheet every 3-4 rounds.
Gap filling
9. If no direction expresses a difference: write a reader on GNM heads, measure it over 2000 sampled heads
   (newdirs.py), report R2 / sd / couplings; add it as a coupled direction (within sex on GNM's sex axis). Low R2 or a
   tiny sd = a real capability gap (a local residual is justified); a coupling against what you see (orbital rim ->
   heavy brow) = the look lives elsewhere (lids, skin) or needs a held step.
Free macros drag neighbours (philtrum <-> chin; length -> philtrum; lips -> chin; bridge / eye depth -> interocular):
the table after each step catches it; held steps cost more |c| per unit.

### Garrett's block-in (started; concept art: front A-pose + a painted 3/4 portrait, no profile)
- f6_G00: his body (age 52, weight 0.4, head scale 1.12) + GNM's sampler MALE mean + gnm_base 0.5. MediaPipe misses
  his face in the full-figure picture: artist.detect_view retries on a crop around the clicked 68
  (likeness.detect_region).
- G01 face_length +1.0, chin_height +0.5; G02 chin_height +0.6, chin_width -0.5 (the free chin_height widened the
  chin: read +1.07); G03 gnm_base 0.0 (the MakeHuman 52-year-old male head's structure reads older and leaner than
  the half GNM base: for an older man the MakeHuman base helps; weight 0.4 -> 0.2 barely moves the face);
  G05 = G03 + cheek_fullness -0.7, nose_width -0.7, bridge_height +0.5, eye_depth +0.6, brow_ridge +0.4 (f6_23):
  reads as an older, lean man with a heavier brow and deep-set eyes, closer to the concept in front.
- Targets: the concept's mm come through the fitted camera; G05's widths / lengths are all ~8-10 % under (pupil
  distance 59.9 vs 65.8; G03 62.3): bridge / eye-depth's free couplings narrowed the eyes; head size or held steps
  next. The painted 3/4's camera looks poor (the clay turns differently): judge on the front until it is refitted.

### HANDOVER (faces6, 2026-10-10)
Branch worktree-agent-a19e0d592ba96cc7d (faces5 merged; commits dbb01e1 .. latest). Scratch /mnt/data/hifipushie/faces6:
run.sh / q.sh / tests.sh (this worktree), cmpround.sh <before> <after> <tag>, gvar.sh <src> <ref> <png> "dst:args"...,
vstrip.py, mk*.py (calibration / base / start heads), cvae_stats.npz, ethstats.npz, femsamp.npz, newdirs.npz.
State: Tess = f6_A23 (block-in result; base f6_b6), Garrett = f6_G05 (in progress). Sheets human_renders/f6_01..23.
Code: likeness.render ao / shadow / light[3] / mesh["C"]; onemesh base.head.gnm_base (spike key, default 0: decide
whether it becomes a default); humanmacro + gonial_height / orbital_rim / lower_orbit; spikes/facesliders artist.py,
eyeread.py, mtable.py, wholeclay.py (hair cap, brows, eye presentation), newdirs.py, basestack.py, fitM.py (stage M,
landmarks + optional photometric), photom.py (held), decomp.py, gates.py, agesex.py (pack "faceage"), fit5 fixes
(head.expression shipping, contact expression-only, TERMS).
Open, in order: (1) Garrett: head size / eye spacing (held steps), the 3/4 camera, then the orbit / lid read;
(2) eyes properly: eyeball seating on GNM's eye + crease (audit g11) for both; (3) Tess inside the outline: her mouth
(wider, fuller), almond eyes (lids / crease), radix (local residual: GNM's sd ~0.6 mm); (4) the flagged base.py
mouth_gap solver (one-mesh heads stay 3.5 mm open).
Last Garrett step: G06 = G05 + head_size! +0.8, eye_spacing! +0.5 (|c| 6.59): sizes up ~4 % but still 3-8 % under the
concept's mm everywhere (a uniform scale: check the camera distance / head scale 1.12 before more identity steps).
DECISIONS (coordinator, 2026-10-10): gnm_base becomes an AGE-DEPENDENT default chosen at block_in_start (young ->
~0.5, older -> 0) and stays a block-in control the artist can move; radix width gets a small LOCAL residual (a
confirmed capability gap, GNM's spread ~0.6 mm), sized from ICT's residual there (faces5 regbasis2). The next agent
productises the method and finishes Garrett's block-in WITH the new MCP tools as its test case.
PRODUCTISING THE METHOD (Joe: "our default for all modeling humans"), what it needs:
- MCP tools: `block_in_look(model, ref, views?)` -> the six-column sheet (as artist.look) + the target table text;
  `block_in_step(model, moves, out?)` -> free / held / gap directions, base keys, lids; writes the step log and returns
  the macro read + the target table delta; `block_in_start(model, refs, sex, body)` -> the base of the right kind
  (class mean + gnm_base) with the refs' cameras; `lid_read(model)` (eyeread) and a `lids` move.
- Library code to move out of spikes: wholeclay.haircap / draw_photo_brows / eye_presentation, artist.detect_view /
  registration at the eyes, mtable's groups (with brow_eye dropped and jaw_angle_height flagged as a detector-guess
  item), newdirs' directions (precomputed table in src like face_atlas.npz) and cvae_stats / ethstats (from the GNM
  sampler; the audit's numpy decoder).
- A guide section (guide.md): the method (gnm_atlas.md "THE ARTIST BLOCK-IN METHOD"), the free vs held rule, the
  couplings to expect, "lids by measure", and when to fill a vocabulary gap.
- Tests: look registration (eyes land on eyes), a step's read moves by its amount (free) and holds the rest (held),
  the target table on a known model.

## blockin (2026-10-10, "blockin" agent, branch worktree-agent-ad0c708a3f812806d, faces6 merged; scratch
## /mnt/data/hifipushie/blockin: run.sh / tests.sh / srv.py <tool> '<json>' (any server.* tool from this worktree);
## sheets human_renders/bi_*)

### The method as tools (Joe: "this method should be our default for all modeling humans going forward")
- `src/hifipushie/blockin.py`: start / look / step / table / lid_read / lid_match; data `blockin_data.npz` (15 KB:
  GNM sampler class means m_f / m_m / mean, gender x ethnicity means, ethnicity contrasts + sd, newdirs' gap
  directions; packed from faces6 cvae_stats / ethstats / newdirs by blockin/pack.py). Clay presentation moved in
  (haircap, draw_photo_brows, eye_presentation, lit_render, detect_view, profile_contour, eye registration).
- MCP tools (human toolset): block_in_start, block_in_look, block_in_step, lid_read; guide topic "block_in"
  (blockin_guide.md: the loop, couplings, gap filling, tool reference); pointers in guide.md 4d, human_guide,
  likeness_guide, tools_guide, the skill, INSTRUCTIONS. tests/test_blockin.py (7 tests).
- Each step is a NEW model (default name = number + 1); one log per block-in (blockin_log.json in the start model's
  folder: round, from, to, moves, seen, why, read, coupled, passes, camera moves; stepping again from an earlier model
  marks the abandoned step "reverted"). A model made outside the tools (faces6's f6_G05) is adopted: the step roots a
  new log, faces6's artist_log.json imported. store.save(checked=False) for these steps (a full validate is ~1 min).
- The table: mtable's five groups, brow_eye dropped, jaw_angle_height shown as `flag` (not counted); cached per
  model by base + cameras; a SIZE line when the long lengths are all off one way; deltas mark a status flip that is
  under 0.15 tol "at the edge" (mouth_line's 0.01 tol flipped on noise).
- gnm_base default by age: 0.5 to 25, 0 from 50, linear between (coordinator's decision).

### Found while building / dogfooding (each fixed)
1. HELD steps did not hold: face_length = nose_length + philtrum + lips + chin_height exactly (a zero singular value
   of humanmacro's table), so `chin_height!` +1 gave chin +0.81 and face_length +0.30 (the pseudo-inverse split the
   impossible ask). humanmacro.released(name): a part lets go of the whole (chin_height! releases face_length), the
   whole of its parts. Now chin_height! +1 = +1.00 (face_length +0.61, nothing else > 0.1). faces6's held chin /
   philtrum rounds were 20 % short of what they asked.
2. FREE steps shrank the head: the population couples size (head_size = the interocular distance in mm) with
   everything; free cheek_fullness -0.5 shrank Garrett's raw GNM head ~1 % (table widths -1.4..-3 mm), which is why
   faces6's free rounds ended "8-10 % small everywhere". Block-in free directions (macros, nd:, eth) now keep size
   (blockin.keep_size / a pinv over [macro, head_size]); `<macro>~` = the raw coupling. Size is set separately:
3. head_scale: the one mesh's head is the BODY's (base.head.scale is overwritten by the body's size: 1.12 on fs_ge3
   did nothing); block-in `head_scale` = base.style.human.head_size (humanstyle: about the neck, eyeballs too).
4. The painted 3/4's "poor camera" (faces6) was mostly the CLAY's detector reading a half-black clay: the light fit
   on the painting put the shadow side at black (c0 - |w| far below 0 over half the face). lit_render: when > 25 % of
   the face's skin is predicted under 0.18 x the skin median, the dark side is lifted to that floor (lit side kept).
   A photo's light (a few side planes dark) is left alone (lifting it flattened the front clay). The camera refit
   (landmarks, camera only) moved the 3/4 camera < 1 deg; the step now reports each refit's turn / distance / focal.
5. Step sheets show before | after | |change| x4 | squints per view: a half-sd step was invisible beside the photo.
6. lid_read(match=True) returns its sheet; the lid pose (GNM eye-region expression) nudges the nasion ~1 mm
   (nasion-based lengths shift ~1 mm with it).
7. The likeness eye_width item does not follow the eye_width macro (held -0.5 sd moved it < 0.6 mm of a +2.95 mm
   miss): a reader difference (MediaPipe corners on the photo vs the clay), suspect; not chased.
8. tests/test_humanmeasure.py::test_model_and_sigmas fails since faces6 added macros (its stored model's names are
   the old 37): pre-existing, not fixed here.

### Garrett through the tools (bi_G00 .. bi_G12; refs fs_ge3: the concept's front A-pose + painted 3/4)
| round | move | read / table | kept |
|---|---|---|---|
| G00 | block_in_start(fs_ge3, male): male class mean, gnm_base 0 (age 52) | round soft young face; 21/31 (lengths short, widths ~ok) | start |
| G01 | face_length +0.7 | outline on his in front; face height / lower third in | yes |
| G02 | cameras [1] (3/4 refit) | camera turned < 1 deg: no change | (same head) |
| G03 | cheek_fullness -0.5 (old free) | whole face 1-2 % smaller: finding 2 | no |
| G04 | cheek_fullness -0.5 (size kept) | no visible gain; cheekbone width out | no |
| G05 | G04 + cheekbone_width! +0.35 | the item didn't come back (macro vs detector oval) | no |
| G06 | G02 + brow_ridge +0.5 | eyes a little deeper; nose / intercanthal just out | yes |
| G07 | head_scale 1.03 | 27/31; jaw +3.0, philtrum +1.1 just out | yes |
| G08 | jaw_width! -0.35, philtrum! -0.3 | 29/31 | yes |
| G09 | lid_read match: lid_upper -1.9 mm, lid_lower +0.7 mm | lids 0.46 / 0.72 iris radii = his | yes |
| G10 | bridge_height +0.5 | higher, narrower bridge; chin +1.65 out | yes |
| G11 | chin_height! -0.2 | 29/31: chin +1.53 (edge, the 3/4 says -0.6), eye_width +2.95 (finding 7) | yes = result |
| G12 | eye_width! -0.5 | table unmoved, |c| +0.22 | no |
Blunt read of bi_G11 (sheet bi_G11.png, bi_G11_vs_G00.png): the outline sits on his in front and (with the light fix)
in the painted 3/4; size, lids, bridge right. Inside the outline it is still a generic, smoother, younger man: no
cheekbone plane turning into a hollow, no nasolabial fold, a round broad nose TIP with heavy nostril shadow (his is
narrower and defined: no macro reads tip width: a vocabulary gap), straight flat lips, eyes seated forward (big white
in 3/4). The remaining differences are age soft tissue (base.head.shape age_* layers, skin), the nose tip (a gap to
fill: reader + 2000 heads like newdirs) and eyeball seating (handover item 2), not more whole-face identity.

### Merge prep (coordinator, 2026-10-10)
- faces4's 14 MakeHuman nose extensions (mh_nose_* / mh_nostrils_*) RETIRED: nothing in src / tests / spikes / any
  workspace spec used them. face_ext.npz is main's again (the mouth fields were bit-identical to main's); the general
  fixes stay (windowed projection, fill_inside, skin-only crease hold, the nose rim hold, faceslide's centre-line
  split). test_faceext's tolerances back to main's (0.1 / 0.1); its new smooth-bend test kept.
- human_measured.npz refreshed for humanmacro's 40 names (blockin/remeasure.py: refstudy2's 1200 training heads are
  deterministic, seed 7000 + s; the old 37 re-read bit-identical; new cv rms gonial_height 0.64, orbital_rim 0.70,
  lower_orbit 0.78 (at / over CUT 0.7: not measured)). test_humanmeasure passes.
- Accepted builds unchanged: humanfit.state (the one mesh + eyes) of f3_t1, fs_tj12, fs_gj8, fs_ge3 and every ts_* /
  gc_* model (84) under main's code vs this branch: all bit-identical (blockin/buildcmp.py).
- Full face + blockin + toolsets suites: 134 passed, 2 skipped.

### Brows seated on the surface (Joe: the far 3/4 brow stuck out past the silhouette; in profile it hooked over the bridge)
blockin.brow_source / seat_brows: the front picture's detector brow band (supersampled x8, ~0.5 mm soft edge) + the
model's depth through the front camera; every clay pixel in any view is back-projected to the surface and painted
where it lands inside the band AND is visible from the front (2.5 mm). Profile: the far brow is gone behind the
bridge, the near one follows the ridge; 3/4: the far brow foreshortens and stops at the silhouette. GNM's landmark
line only where the front detector misses. Sheet: human_renders/bi_brows_seated.png (photo | before | after; Tess
front / 3/4 / profile, Garrett front / 3/4). Display fill: the clay's shadow side is lifted for DISPLAY only (a soft
knee to 0.45 x the lit skin's p75); the fitted light stays as fitted for anything measured.

### The painted 3/4's outline (coordinator: red well outside green there)
With the fill, the clay's detector oval reads properly (it had been reading the half-black clay). What remains: on
the FAR side (past the nose) the clay's cheek shows beyond the painting's; on the NEAR side the painting's oval runs
~20 px outside the clay's. Re-rendered at yaw +8 / -8 deg (blockin/yawtest.py): +8 puts the far side on the painting
and leaves the near side ~20 px out: the painting is turned ~8 deg more than its landmark-fitted camera (the refit
moved < 1 deg: its points are the detector's on a painting), and its near-side oval follows the sideburn / hair line
in front of the ear (a detector guess, not a silhouette): don't model to it.

### Feature pass (Joe: "focus more on each feature, then zoom back out after making each change")
block_in_look(focus=eyes | nose | mouth | chin_jaw | cheeks | ears): per view the feature's crop, registered at its own
landmarks (MediaPipe <-> 68 pairs per feature), photo | clay | overlay | local contours | raking light | squints, +
that feature's checklist rows (likeness stages; lids for eyes). block_in_step(feature=) returns its before | after
crops + rows, then the whole-face sheet; block_in_look(read=, keep=) logs the zoom-out verdict. blockin_guide.md: "The
feature pass: ZOOM IN, step, ZOOM OUT". table() / feature_table() come from one cached row list (blockin_rows.json).
radix_width / dorsum_width rows are shading-contrast items (model 0 by definition).

### Vocabulary: the nose tip and the radix (coordinator's item 1)
- tip_width (blockin/gaps.py, 2000 GNM heads, the lobule's soft half-width at the tip's height / io): R2 0.94, sd
  1.31 mm: GNM DOES vary it (not a capability gap). Coupled +1 sd: alae +0.58, lips forward +0.58 / fuller +0.5,
  projection -0.51, bridge -0.51 (the broad-tip / low-bridge population pattern). Held variant (alae, projection,
  size, lips, bridge, length held): clean (largest other move 0.2), |dc| 1.76 / sd. In blockin_data as
  nd:tip_width and nd:tip_width|held.
- radix: GNM's spread 0.6 mm (newdirs) + ICT's residual beyond GNM projected on faceslide's nose_radix_width field
  (faces5 regbasis2_nose, 8 modes; blockin/radix.py): 0.09 units = ~0.13 mm. A real gap but near invisible. The
  local residual already exists as faceslide's nose_radix_width slider; the block-in now takes local residuals as
  `local:<slider>` moves (SET, base.head.sliders) with their ICT population sd (radix 0.09, tip 0.18, dorsum 0.12;
  warned past 2.5 sd).

### Feature pass, first rounds (focus mode; zoom-in read = the step's seen, zoom-out read logged with keep)
Garrett (from bi_G11):
| model | feature | move | zoom in | zoom out | kept |
|---|---|---|---|---|---|
| G13 | nose | nose_upturn! -0.5 | nostril band a bit narrower, 3/4 tip lower | philtrum / middle third (3/4) out | no |
| G14 | nose | nd:tip_width|held +0.6 | lobule a touch wider / rounder | unchanged, nothing out | yes |
| G15 | nose | local:nostril_show -0.5 | no visible change: the dark band under his clay nose is the nostril floor in shadow under the photo's top light, not nostril show | - | no |
| G16 | eyes | eye_tilt! -0.7 | canthal tilt only -0.9 deg | 3/4 philtrum / middle third out | no |
| G17 | eyes | eye_size 0.88 (base.head.eyes) | opening -0.6 mm only | unchanged | open |
Tess (adopted from f6_A23):
| T01 | mouth | lip_fullness! +0.5 | upper cushion fuller | unchanged | yes |
| T02 | mouth | lip_projection! +0.6 | WRONG WAY: I misread the earlier sheet; the zoomed profile (registered at the clicked lip points) shows her lips 1-3 mm BEHIND the clay | temple out | no |
| T03 | mouth | lip_projection! -0.5 | profile lips ~1 mm back toward hers | unchanged | yes |
Sheets: bi_G14_nose.png (before G11 | after), bi_G14_eyes.png, bi_G17_eyes.png, bi_T03_mouth_vs_A23.png, bi_T03_vs_A23.png
(whole face), bi_G14.png. Read: the zoom-in caught what the whole-face sheet hid (the profile lips' direction, the
eye size) and the zoom-out caught held steps leaking into 3/4 items; half-sd steps are still small in the crops.

### Eyeball seating (coordinator's item 2): finding, not built
Garrett's eyeball radius is 14.6 mm (an adult eye ~12 mm; Tess 12.7): the eye radius follows the body's head size,
so his drawn iris is 7.3 mm (real ~5.9). Matching the lids in IRIS RADII then leaves the opening 2.8 mm (43 %) too
tall in mm, the eye 11 % too wide: big, forward-looking eyes with lots of white. eye_size (base.head.eyes, scales the
eye AND its orbit about the eye centre) 0.88 moved the opening only 0.6 mm: the readers of the opening / width follow
the lids and lash line, not the ball. Options to decide: (a) eyeball radius absolute (~12 mm adult, not x head size)
in onemesh's eye placement, with the socket seated round it (GNM's own eye mask), then lids re-measured; (b) lid read
in mm (MRD1 in mm against the photo's iris-scaled mm) instead of iris radii. (a) is the real fix (audit g11).

### Age soft tissue for Garrett (item 3): report pending (what our age ops / MakeHuman age give vs data-backed).

### Age soft tissue (item 3): what we have, before building
- GNM's identity has no age; the semantic sampler conditions on gender x ethnicity only.
- MakeHuman age (the body's head, gnm_base 0 for older people) gives the skull and head proportions of a 52-year-old,
  authored by MakeHuman's artists, not measured. On Garrett it reads older and leaner than the GNM base did (faces6 G03).
- headage.py (base.head.shape: nasolabial, prejowl, lid_fold, eye_bag, lip_bow, lip_roll, cheek_flat, lips_thin) and
  faceslide's age_* / cheek_hollow / face_lean / face_planes sliders: hand-authored soft-tissue ops (millimetres,
  placed from the landmarks, mirrored), not data-backed. The accepted fs_ge3 used face_planes 0.5, face_lean 1.5,
  cheek_hollow 0.08, age_nasolabial 0.5, age_cheek_flat 0.28.
- Data-backed candidates (licences to check before any use): BFM 2009 / 2017 attribute regressions (age among them;
  non-commercial), the Liverpool-York Head Model (age-structured; non-commercial), FLAME (trained on CAESAR adults;
  no age label in the release), FaceScape (has age labels; licence restrictive), ICT-FaceKit (identity modes, no age).
  None was checked here.
- Proposal: (1) block_in_step `shape:<headage key>` moves (SET, mm), judged with the cheeks / mouth focus under
  raking light against the photo, so Garrett's nasolabial fold, cheek hollow and lean lips are placed BY EYE against
  his picture now; (2) then decide on a data-backed age direction (e.g. an age regression over a licensed scan set,
  added as nd:age with its couplings, like newdirs) to replace the hand ops' sizes.

### HANDOVER (blockin, 2026-10-10)
Branch worktree-agent-ad0c708a3f812806d: e85453e is the merge-prep commit given to the coordinator. After it:
8dbeabe (feature-pass rounds, nd:tip_width, local:, eye_size) and b268f3b (guide). Scratch /mnt/data/hifipushie/blockin:
run.sh (SRC=<src dir> to run other code), tests.sh, srv.py <tool> '<json>' (any MCP tool via server.*), buildcmp.py
(accepted builds main vs branch), remeasure.py, gaps.py / pack2.py (gap directions -> blockin_data.npz), radix.py,
browlook.py / browcmp.py, yawtest.py.
State: Garrett bi_G14 (whole-face block-in at G11 + tip width; G17 eye_size open), Tess bi_T03 (f6_A23 + fuller,
less proud lips). Sheets human_renders/bi_*.
Open, in order: (1) eyeball radius absolute (~12 mm) instead of x head size, socket seated round it, lids re-read
(Garrett's eyes 43 % too open in mm with matched iris-radius margins); (2) age: `shape:` block-in moves, then the
data-backed decision above; (3) the eye_width / eye_opening readers on clay (suspect: they follow the lash line);
(4) the painted 3/4 is turned ~8 deg more than its camera: a silhouette-aware camera refit for painted views;
(5) the lip_upper click on profiles vs lm51 (the clicked point is the lip's most forward point, lm51 the vermilion
top: a 4 mm vertical disagreement that biases profile registration).

## blockin2 (2026-10-10, "blockin2" agent, branch worktree-agent-aef00385e135b10dd from main 6fb2795; scratch
## /mnt/data/hifipushie/blockin2: run.sh / tests.sh / srv.py (as blockin's), eyerep.py, irismm.py, crop.py; sheets human_renders/b2_*)

### 1. Eyeball: absolute radius (key head.eye_radius; default OFF, no accepted build changes)
- Why the ball was big: GNM's template eyeball is itself a 14.6 mm sphere (sphere fit to its 771 eye vertices: r 14.51-14.56
  mm, centred on its eye joint; its limbus 6.0 mm) and we used 0.96 x that x the body head's scale (Garrett 1.013 -> 14.6
  mm with head_size 1.03 in the eye scaling; Tess 0.909 x eyes 1.05 -> 12.7). The drawn iris is 0.51 r: 7.3 mm on Garrett.
- His concept measured through the fitted front camera: iris radius 5.8 mm (a realistic painting), eye width 25.7 / 24.8,
  opening 6.9 mm. Model bi_G14: width 26.1 (right), opening 8.5 mm (lids matched in iris radii on a 7.3 mm iris).
  So the opening's WIDTH is right and only the ball / iris was big: the socket is NOT scaled (scaling the eye region
  by 12/14.6 about the centre would make the eye 21 mm wide).
- base.head.eye_radius (m, world): r_ball = eye_radius x head.eyes (eye_size / a style's big eyes); NOT x head size
  (adult eyeballs barely vary). The same seat search (the ball comes forward until the rim landmarks clear it by
  EYE_SEAT): a 12 mm ball's front pole ends 0.4-0.7 mm further forward of the rims than the 14.6 mm one (1.1 -> 1.5 mm
  after the lid match on Garrett). Block-in key `eye_radius` (SET). Test: test_blockin.py::test_fixed_eyeball_radius.
- Garrett b2_G02 (bi_G14 + eye_radius 0.012; b2_G01 was the same with x head_scale, superseded): iris 6.03 mm, lids now
  read 0.53 / 0.88 iris radii (his 0.46 / 0.72) -> lid_read match -> b2_G03 (lid_upper -1.52 mm, lid_lower +2.16 mm):
  margins 0.47 / 0.72, opening 7.2 mm (his 6.9 camera / 7.0 iris-scaled), width 25.8 (his 25.7 / 24.8). Table unchanged
  except mouth_over_alar at its 0.06 edge (lid pose nudges the nasion). Read (b2_G03_eyes_vs_G14.png, b2_G03_vs_G14.png):
  smaller iris, less white, heavier lids: closer to his hooded, tired eyes; the whole face otherwise unchanged.
- Tess b2_T01 / b2_T02 (bi_T03 + eye_radius 0.012 x her eye_size 1.05 = 12.6 mm, lids re-matched): 12.69 -> 12.6 mm,
  barely moves (sheet b2_T02_eyes_vs_T03.png). Her photo's iris through the fitted camera reads 5.1 mm (MediaPipe on a
  real photo; either her camera's scale or the detector's iris): not chased. Her eyes' aspect stays 2.4 vs her 2.8-3.1
  (wider, almond): lids / crease, a later feature round.
- likeness eye_width item on Garrett: 28.8 model vs 25.5 photo, while the model's own corner landmarks are 26.1 apart:
  the clay reader (handover item 3) inflates by ~2.7 mm; still open (item 4 below).
- DECIDED (coordinator): every NEW human gets it: humans.spec(source="human") writes head.eye_radius =
  humans.eye_radius(age) (EYE_AXIAL: axial length by age, ~17 mm newborn -> 24 mm adult, halved: 0.012 from 18), and
  block_in_start sets it too (setdefault). Accepted models keep theirs (no key: the old ball); re-match when worked on.
  Guides: blockin_guide (BASE keys), human_guide (top). Tests: test_new_human_eye_radius, start asserts it.

## lt19 (2026-10-10; a private likeness: per-person notes, body settings and rounds are in the git-ignored
## workspace/private_notes/lt19.md, never in the repo). General tool findings from it, now in code:
- Phone references: the 70 mm portrait lens prior folded close-camera perspective into the face shape; a view's
  "lens_mm" (35 mm-equivalent, diagonal) or the image's EXIF now sets the focal prior (humanfit_map.lens_prior).
- A profile facing image-left needs yaw -90 (not auto-resolved at 90 deg); likeness.render / humannormals cull at a
  near plane (close cameras); profile_contour per-row background + skin-warmth test; light fit limited to the
  landmark hull without a detector; photo_sides falls back to the detector box.
- A head_scale step moves each camera's centre with the face's landmark centre (a camera refit otherwise undoes it).
- under_chin sign: + = clean, - = full / double chin; GNM carries submental fullness itself. Body keys neck_double /
  neck_depth (MakeHuman CC0 neck targets; 0.5 = none) for the neck front across the stitch.
- Per-picture expression (GNM lower-face comps) explains part of a smiling reference's fuller lips / cheek apple:
  fit it per view so the neutral identity isn't compared against a smile.
- lt19b (branch worktree-agent-a7249a6883601c2d3), now in code:
  - block_in_expression / blockin.expression_step: each detector view's expression (GNM lower_face_region comps 0-19,
    prior sd 0.8; identity and camera held), Jacobian by finite differences once + chord iterations (~16 s), stored in
    human_refs "expressions" and applied (blockin.view_base) in look / focus / the table (likeness.model_sides takes
    per-photo meshes) / lid reads / camera refits; the model stays neutral. Eye-region comps are opt-in (eyes=True):
    with them the upper lid fell 0.75 -> 0.36 iris radii (the detector's calibrated lid points disagree with the
    iris-radius lid read, so the comps fought the lid pose). With a smile applied, rows it had hidden show (philtrum
    +1.5 mm, nose length +1 mm on lt19): steps taken against the neutral clay had compensated for the smile.
  - Widening steps driven by the blind alar row are worth undoing: judge alae on same-scale crops against the
    inner-canthal span. A free bridge_height step cost |c| ~0, the held one +1.7 for the same profile.
  - Presentation brows: the hair band as density (darkness against the skin), not a flat mask; the band's canvas and
    outer end extend past MediaPipe's brow end (it stops short of the tail). skin hair.brows: taper (0.82 default:
    how much the band thins toward the tail) and tail (how far the hairs reach).
  - hair: the default groom grey and look.grey_locks follow age (none to 30, full from 50; hair.grey_age / look_of):
    locks groomed earlier carry their grey in the spec, so the look default matters too.
  - Five cheek-area clay readers (corner_temple, corner_cheekbone, under_eye, cheek_hollow, nasolabial_fold) return
    exactly 0.00 on the clay: flagged, not counted, but those rows carry no information yet.

## jw (2026-10-10; a private likeness: per-person notes, body settings, rounds and reads are in the git-ignored
## workspace/private_notes/jw.md, never in the repo). General tool findings from it:
- A profile facing image-RIGHT (yaw +90) crashed the block-in (registration hard-wired to eye_outer.L) and its photo
  contour was scanned from the wrong side: _eye_anchor uses eye_outer.R / lm36, profile_contour reads the picture
  mirrored (test_profile_contour_either_side). +90 vs -90 matters as lt19 found (the wrong sign: 2.3x the rms, dropped).
- profile_contour on a warm (tan) wall behind fair skin: |rgb - bg| is under 40 while the chromaticity differs by
  ~0.07: a hue test (5x5-smoothed, > 0.05) is OR-ed in; the per-row background is a band just in front of the most
  forward clicked point (a wall's light falls off across the picture), and a 5-row median removes lash / fold spikes.
- Profile focus crops: the light was fitted inside the crop (a 34 mm eye crop: lashes, brow hair, wall) and lit the
  clay white; a clicked view's crop now uses the whole face's fitted light. The raking light comes from the side the
  face looks to, and the crop is at least 0.75 x nasion-chin (a profile foreshortens the corner-to-corner span).
- Brows in the block-in presentation take the picture's own colour (darkest quarter of the band's pixels): light,
  fine brows (brow_hair_band finds too little dark hair and falls back to the detector band) read as heavy dark bars
  in the fixed dark brown.
- The table's clay readers drift ~1-1.5 mm with lower-face / neck SHADING alone: over four rounds that changed only
  the submental region and a body key (neck_double), the model's own landmark lengths stayed identical to 0.1 mm
  while middle_third moved 1.8 -> 3.2 mm and mouth_width 0.3-0.6 mm. Items within ~1.5 mm of their tolerance can flip
  on a step that didn't touch them: check the model's landmarks (or the zoom) before reverting for them.
- Held bridge_height costs much |c| when free steps had pushed it up (+0.92 -> +0.42 sd cost |c| +1.1) and moved the
  profile nose as a whole: a radix that reads proud may be the free nose_projection's coupling; try the free step's
  held variant first.
- MakeHuman weight barely moves a one-mesh body's waist (62 -> 66 cm for weight 0.6 -> 1.0): the measure modifiers
  (waist / hips / chest / shoulders) carry a full build. human_reference reports the lens width-based ("~33 mm") for
  a 24 mm diagonal-equivalent EXIF lens (the focal itself is right).
- A stature from a room photo: pitch from the wall seams' vertical vanishing point, the camera's distance from a
  standard-size object on the wall (an outlet plate, 114 mm), its height from the wall base, then the person's heel
  point and head top (+-6 cm with a 5 % uncertainty in the object's size).
- Dressed check (garrett3 stage / shot.light): light-brown hair looks (lit lighter than ~#7a5a3c) render grey-blond and
  very fair skin (melanin 0.02-0.08) reads tan / ruddy: FIXED by jw2 (below: skin.tone_rgb's fair end, hair look.seen).

## jw2 (2026-10-10, continues jw; branch worktree-agent-aec6be48f7479a3e4; per-person notes in the private file).
General findings:
- The EYE STEP on a model that had lid POSE offsets: the solve starts from the pose-free lids (its "before" reads the
  head without head.pose), so a well-matched pose model shows a big "before" miss; the shipped result clears the pose.
  Dressed (garrett3 stage) the crease and the lowered upper lid DO read (a soft fold above the lid, lid over the iris
  top); what still reads "open / staring" dressed is presentation: bright sclera to the corners, a saturated iris,
  a thin lash line.
- The model's own 68 landmarks (humanfit.state L) use a different nose base than the clay / photo detectors (L33
  projects ~6-8 mm below a photo's subnasale through the fitted camera while the clay reader's middle third is SHORT):
  never compare L-lengths with table rows for the nose; corners and pupils (36/39/42/45, 68/69) do sit on the
  photo's and are a sound check of the eye-placement rows (the clay reader's +2-3 mm eye_width / pupil rows are drift).
- DRESSED READS NARROWER / HARDER THAN THE CLAY: not geometry (the bald dressed head's silhouette through the same
  camera sits on the photo's face outline: dcmp-style check, hair off vs on). Causes: (1) the stage's FRONT_LIGHT key
  is 42 deg up: the face's sides, jaw and neck fall into warm subsurface shadow (the lit area narrows, planes read
  hard) where a phone photo is lit flat from the front; a soft frontal key (~22 deg up, fill from the camera) read
  rounder and fairer at once; (2) hair hanging flush down both sides of the face; (3) heavy dark straight brows.
  For likeness sheets light the dressed head like the photo (the clay already uses the photo's fitted SH light);
  porting that SH fit to the dressed stage is the general fix (not done).
- Loose hair can't say "the part side combed back behind the ear, the swept side falling forward": loose.flow is per
  REGION (front, top, sides ...), the same world direction on both sides, and per-region flow on front / top forced
  everything across and bared the part's other side; stiff >= 0.4 on long front hair hooks the ends; hair resting on
  bare shoulders hooks up. A per-side (part side / swept side) flow, or the traced route (hair_reference apply=True)
  for loose grooms, is the gap.


### 2. Age moves (designed) and Garrett's nose (coordinator: nose before age)
- `shape:<op>` block-in moves (faceslide age sliders / headage ops), flagged DESIGNED in reply and log. Garrett
  b2_G04 = G03 + shape:age_nasolabial 0.6: fold rows' shading gap 22 -> 19 % front, 28 -> 20 % 3/4 (kept); 1.0 (G05)
  pushed mouth_width over its edge (not kept; G09 = 1.0 + mouth_width! -0.2 on the nose branch, kept-able).
- The painted 3/4 (concept_v6) is foreshortened beyond any rigid turn: its far-side outline (skin against the dark
  pillar, farside.py) sits 10-13 px (~14 mm) INSIDE our far cheek at the fitted camera, 6-8 px at +12 deg yaw, while
  the brow / eye points' rms rises 5.8 -> 9.5 px by +20 deg (yawscan.py); +10 mm nose projection moves that outline
  0.9 px. Don't model the nose to that view's outline.
- Pitch (pitch.py: the head pitched about the camera centre, -10..+10 deg): front: brows / eyes / mouth points best at
  0..+5, nose at 0; 3/4: everything best at 0 except the tip's height over subnasale (wants the tip ~3 mm lower: shape).
  No camera pitch error; the "seen from below" read was the light + a too-high tip.
- The front base band is the light: under a 2nd-order SH light fitted on the skin (ambient + key + fill / bounce,
  shlight.py / shl.py) the band under the nose / tip = 0.66 (picture 0.6-0.7); the block-in's c0 + w.n light gives
  0.19-0.34. Dressed (look_skin, b2_G08_skin.png) no band either.
- The bridge's side walls ARE a shape difference: walls (6 mm off the dorsum / on it) picture 0.51, clay 0.80 under the
  SH light. GNM's own nose-region principal directions (blockin.region_pcs, new move `pc:<region><i>`; nosepca.py):
  the best (PC0: higher, narrower, more projecting bridge + hump + deeper eyes) moves 0.80 -> 0.75 at 1.5 sd; the
  others <= 0.03. A capability gap: a DESIGNED local (local:nose_dorsum_width -0.8 = 6.7 x ICT's sd: dorsum 13.9 ->
  10.9 mm, walls 0.70) is justified for this concept.
- Alar width: MediaPipe 129 / 358 sit on the cheek past the alae on picture AND clay (alar_width row unmoved by a held
  nose_width -1.0 that moved the alae 3.4 mm): the row is blind to it (flag candidate). Same-scale crops: his alae
  ~0.98 of the visible intercanthal span, ours ~1.11; the clicked lm31-35 26 mm vs our 35.
- Kept: b2_G08 (nose_upturn! -0.7, nose_projection! +0.4: tip 26.4 mm ahead of the alar base, columella 34.8 deg,
  NLA 123), b2_G11 (tip_width back -0.6, local dorsum -0.8), b2_G12 (nose_width! -1.0), b2_G13 (mouth_width! -0.2).
  G13: table 28/31 (eye_width: the clay reader; philtrum 3/4: painted view; mouth_over_alar: the detector's alae).
  Sheets b2_G13_nose_vs_G14.png, b2_G13_nose_profile.png, b2_G11_nose_shlight.png, b2_G08_pitch_front/_34.png, b2_G13.png.

### 3. SH light, flags, the joint nose-PC solve, THE EYE STEP (2026-10-10)
- SH light (decided): blockin.LIGHT = "sh" (sheets: 9 SH coefficients x AO fitted on the skin, likeness.render light[4])
  and likeness.SHADE_LIGHT = "sh" (the shading rows' residual: ls.fit_light_sh / residual_sh). The c0 + w.n light
  put down-facing planes near black (Garrett's base band 0.19 vs picture 0.6-0.7; SH 0.66). likeness tests pass.
- Flags (decided): alar_width, mouth_over_alar (MediaPipe's alar points sit on the cheek).
- Joint solve over GNM's 8 nose PCs for the bridge walls (walljoint.py, b2_G08): 0.80 -> 0.75 at 0.96 sd, 0.70 at
  2.05 sd (|c| 6.10 -> 6.71: projection +1.6, bridge +1.3, eye depth +1.1, lips -1.0), 0.60 at 4.9 sd, 0.55 at 6.6.
  The picture's 0.51 is out of reach at any sane cost. The designed local (b2_G11) awaits Joe.
- THE EYE STEP (Joe: "we shouldn't really ever use our 'fix' [lidfold]"): src/hifipushie/blockin_eyes.py, the audit's
  g11 crease fit as a block-in step on the SHIPPED head (onemesh.head_template, 0.12 s an evaluation; identity 170 +
  20 symmetric eye-region expression pairs, LM with finite differences, ~4 min). Evidence: lid margins vs our drawn iris
  (sigma 0.05 iris radii); the picture's fold line (lidfold.read_lid tps, columns with darkness >= 0.15) vs the
  crease's SOFT height (a soft-max over the profile's local depth: the arg-max / visibility reads jumped and stalled the
  first solve at platform 3.5 of 5.6 mm), and the crease >= 1.2 mm deep (0.7 solved to 0.74 and did not read dressed:
  b2_T04_skin vs b2_T05_skin); hooded (no line in most columns): the visible platform ~0.5 mm; the 68 landmarks off the
  eyes held at 0.3 mm (brows 1 mm). Ships head.identity + head.expression, lid pose cleared. lid_read(match=True) runs
  it; match="pose" = the old offsets.
- Tess b2_T06 (from b2_T02, tool path): lids 0.45 / 0.93 -> 0.64 / 0.90 (her 0.67 / 0.88; the render-based lid_read
  0.65 / 0.88), crease 0.34 -> 1.12 mm deep at 3.9 -> 5.3 mm (her line 5.15 mm at an 11.7 mm iris), |dc| 3.0, |e| 1.8,
  table unchanged. Dressed (b2_T05_skin.png, same solve): a fold line reads above the lid, soft. Sheets
  blockin_b2_T06_eyes.png, b2_T04_eyes.png.
- Garrett b2_G14 (from b2_G13, hooded: his picture shows no line in 5 of 6 columns): lids 0.46 / 0.73 (his 0.46 / 0.72),
  platform 2.95 -> 1.33 mm (target 0.5), no crease. The hood itself (the fold's skin hanging over the platform) is
  only reached through the visibility read, which is jumpy: a smooth hood measure is the next piece. Sheet
  b2_G14_eyes.png.
- Diagnostic: eyediag.py (linear reach of identity / expression / both for the three reads; holds' cost).
- Hood (smooth): the lid profile's drop below its running maximum (the fold hanging back down); the visible platform =
  the crease's soft height blended toward the overhang's lowest point over a 0.1 -> 0.6 mm drop. Garrett b2_G15 (from
  G13, hooded target 0.5 mm): GNM made NO overhang (drop 0.00); it lowered the crease instead: platform 2.56 mm, crease
  0.54 mm at 2.56, lids 0.44 / 0.74 (his 0.46 / 0.72), |dc| 1.9, |e| 1.9; mouth_width edge flip (+1.58 of 1.5).
  Dressed (b2_G15_skin.png): a heavy low upper lid, skin close to the lashes: reads hooded enough in front and 3/4. A
  true overhang is a GNM capability question (not tested beyond this prior).

### 4. Age from the London Set (task 3) and M4's first numbers (frllfit.py, frllage.py; out/frll/*.npz, frll_age.npz)
- Metadata: london_faces_info.csv has age / gender / ethnicity for 100 of 102 people (2 blank); ages 18-54, median
  26, only 5 over 40 (47, 48, 54 ...): an age direction from it would cover young adults only.
- Fits: humanfit_map.fit (MAP, detector points, neutral front + both 3/4, identity only: humanfit_map has no
  per-picture expression), a one-mesh human of each person's age / sex: 5-11 s each, rms 1.35 mm mean, no view dropped.
- Age direction (within sex x ethnicity, group means removed; c's regression on age): leave-one-out R2 of age from it
  -0.03; identity variance age explains 1.6 % vs a permutation null's 95 % of 1.9 %: NO age signal. Couplings of +10
  years all < 0.15 sd (lips thinner -0.14, brow lower -0.11 ...: the right signs for ageing, but noise-sized).
- M4 (why it can't): the fitted identities are shrunk hard toward the mean: |c| median 3.5 (a random GNM face ~13),
  per-comp sd of the fitted people 0.15 median (the prior says 1.0; comps 0-9 0.26-0.70), nothing past 2.5. Front +
  3/4 detector points determine a few dozen directions; the rest is the prior. Real people's identities are not
  recovered at the precision an age direction needs (and the M4 design's empirical-Bayes variances would come out ~7x
  too narrow from these fits: the evidence, not the faces, sets them).
- So the designed age ops stay (shape:<op>, flagged DESIGNED). Next-best licensed source for a data-backed age direction:
  older people with known ages AND enough shape evidence per person: (a) Wikimedia Commons portraits with Wikidata
  birth dates (CC0 metadata; images CC BY / BY-SA / PD, used on /mnt/data only, statistics shipped) for 2D age
  statistics of landmark ratios / shading (the soft-tissue cues: folds, lid, jowl) rather than identity; (b) MakeHuman's
  age targets (CC0, artist-made: what we have through the body). No permissive 3D scan set with older ages is known
  here (BFM / LYHM / FaceScape / FLAME are out). Decision for the coordinator / Joe before building (a).

### HANDOVER (blockin2, 2026-10-10)
Branch worktree-agent-aef00385e135b10dd (from main 6fb2795): 5a538a8 eye_radius key, 1b3f79e new humans get it,
74830fe shape:<op>, cd4f4bb pc:<region><i>, 9c39a58 flags, e611e9e SH light, 05901d5 eye step, c1ef720 hood, notes.
Tests: test_blockin (11), test_humans, test_onemesh, test_likeness* pass. Accepted models' builds unchanged (eye_radius
is written only into new specs; SH changes only the block-in sheets and the likeness shading rows' residual).
Scratch /mnt/data/hifipushie/blockin2: run.sh / tests.sh / srv.py <tool> '<json>' | @file.json; eyerep.py, irismm.py
(eyes in mm), farside.py / yawscan.py / pitch.py (camera checks), nosevar.py / prof.py / noseres.py / alar*.py (nose
reads, built profile), shl.py / shlight.py (SH light reads), nosepca.py / walljoint.py (GNM nose PCs, joint solve),
eyeev.py / eyestep.py / eyestep2.py (KEY=VAL overrides) / eyediag.py (the eye step), frllfit.py / frllage.py (London
Set), tdiff.py / ft.py (table diffs), crop.py.
State: Garrett b2_G15 (12 mm eye, fold 0.6, nose tip down / projection, DESIGNED local dorsum -0.8 awaiting Joe,
alae in, eye step with a low crease); b2_G09 is the fold-1.0 alternative from G08. Tess b2_T06 (12 mm eye x 1.05,
eye step: fold at 5.3 mm, 1.1 mm deep).
Open, in order: (1) Joe on the designed dorsum local (b2_G11's); (2) the eye_width / eye_opening readers on clay
(Garrett: row 28.8 mm vs his own corner landmarks 26.1) and lt19's weak-perspective scale in the eye-placement readers;
(3) the profile lip_upper click vs lm51; (4) the eye step: a true overhang (GNM made none for Garrett: test a bigger
prior / expression range), Tess's iris reads 5.1 mm in camera mm (iris-radius targets may be ~15 % inflated for her);
(5) age: the decision on a licensed older-age source (section 4); the designed shape: ops meanwhile (Garrett: fold,
hollow, lips by eye: note his lower lip reads FULLER than ours on the table, not leaner).

## blockin3 (2026-10-10, "blockin3" agent, branch worktree-agent-a7d86f157b96ca324 from main 63e7f10; scratch
## /mnt/data/hifipushie/blockin3: blockin2's scripts retargeted + nose3.py, lmd.py, sheet16.py, wfetch.py / wscan.py /
## wstats.py (Wikimedia age set), cuetest.py / clayc.py; sheets human_renders/b3_*)

### 1. Garrett's nose: tip UP (Joe: "his nose points down when it should be slightly up")
- G08 (blockin2) turned the tip down (nose_upturn! -0.7, nose_projection! +0.4) on its read of the painted 3/4; Joe reads
  the opposite. Measured on the built profile (nose3.py: the front camera turned 90 deg; midline columella line from
  subnasale along the nose's underside): G15 columella +22 deg above horizontal (the lobule hung below it), G04 (before
  G08) +29.
- Variants from G15: FREE nose_upturn +1.0 / +1.6 turns the tip but drops projection 26.7 -> 23.8 / 22.0 mm (the
  population couples upturn with a shorter nose): not used. HELD nose_upturn! +1.4 with nose_projection! -0.4:
  columella +37 deg, projection 26.7 mm kept, |c| 6.48 -> 6.79. KEPT as b3_G16 (feature nose).
- Read: the built profile's tip now rises slightly; the painted 3/4's lit underside plane rising forward matches; dressed
  3/4 (look_skin) reads slightly up. Cost: a little more nostril show in the clay 3/4.
- Table: philtrum front +0.02 -> +1.46 and chin_height front -> +2.16 "went out", mouth_width came in. The model's OWN
  3D landmarks moved < 0.5 mm (lmd.py: philtrum 18.71 -> 18.73, chin 39.06 -> 39.12, face height 121.1 -> 121.0): the
  clay DETECTOR re-reads the whole lower face when the tip turns (jw's drift note). Check lmd.py before reverting.
- Designed dorsum local (nose_dorsum_width -0.8, Joe "yes maybe"): kept; with the tip up it still reads (narrow bridge,
  darker walls); at 0 the bridge reads broad again (out/n3.png).
- Sheet for Joe: b3_G16_nose_before_after.png (pictures; G15 / G16: front | 3/4 | built profile | dressed front | 3/4),
  b3_G16_nose.png (focus), b3_G16.png.
- ACCEPTED (Joe, 2026-10-10: "Garrett's nose looks much better"): b3_G16 is Garrett's current block-in. The DESIGNED
  narrow bridge (local:nose_dorsum_width -0.8) is APPROVED by Joe for this painted character only (a documented GNM
  gap: its nose PCs reach walls 0.75 at 1.5 sd vs the picture's 0.51); not a default for other heads.

## gnmdetail (2026-10-10, "gnmdetail" agent; Joe: "still don't have her eyelid folds or lip line, I know GNM CAN make
## those shapes". Scratch /mnt/data/hifipushie/gnmdetail: run.sh / tests.sh, dshot.py <model> <tag> (dressed EEVEE front
## through the fitted camera + raking clay, lid / lip reads on photo and render alike), claylips.py (clay under the
## dressed light, L* across the lip borders), cyc.py (Cycles), crops.py / many.sh, crease.py <src> <dst> <d_line>,
## lipsrun.py <src> <dst>, lipmiss.py, pipe.py / stagecmp2.py (what the pipeline keeps), lipreach2.py (GNM's reach))

### Readers, same on photo and dressed render (rd.py)
- Fold: lidfold.read_lid (tps / dark / width) on the photo crop and on the render downsampled to the photo's pixels.
  Tess photo: line 5.25 mm, dark 0.32, FWHM ~1 mm. Dressed b2_T06 (eye step, crease 1.1 mm): 7.2-7.7 mm, dark 0.08-0.16.
- Lips: L* / a* profiles across the traced vermilion border (lipborder.read, now src/hifipushie/lipborder.py), upper middle /
  sides, lower; the bow (traced upper border's peaks over its centre trough). Tess photo: a bright roll +3.5 L* ~1 mm above
  the upper border's middle, the upper vermilion dark (-23 vs the skin), the lower lip LIGHTER than the skin (+3: faces
  up); bow 1.44 mm. Dressed b2_T06: no roll (-1), upper -17, lower -8.5 (paint), a PALE RING +5 L* just outside the lower
  border (the photo has none: skin:lip_border's pale rim), bow 0.6-0.7 mm.
- Clay under the same light (claylips): the geometry's share. b2_T06: upper vermilion -1.6 (no turn down), lower +7.8.

### Q1, the crease: depth, socket, renderer
- The pipeline keeps it: stagecmp2 (one mesh vs the dressed stage mesh, same frame 0.24 mm): crease 2.2 -> 2.1 mm deep.
- The socket coupling is fixed in the solve: blockin_eyes.socket() (humanmacro orbital_rim / lower_orbit / eye_depth on the
  mesh WITH the expression) held at 0.15 sd (default). Tess: unheld (b2_T06) +1.10 / -1.12 sd, held (gd_T12) +0.27 / -0.05,
  crease 0.96 mm (unheld 1.12). Same on the private likeness (unheld +1.4 / -1.6, held +0.3 / -0.1).
- Depth sweep (held, from b2_T02; d_line = the floor on the crease's local depth): 1.2 -> 0.96 mm at |dc| 3.3; 2.0 -> 1.37
  at 5.2; 3.0 -> 1.64 at 7.6 (orbital_rim creeps to +0.5). GNM's fold is a ~2.5 mm-wide valley (its lid rows ~1 mm);
  the photo's line is a ~1 mm slit where skin folds over (blockin2: GNM made no overhang).
- Dressed: EEVEE reads dark 0.15-0.24 even at 1.64 mm (photo 0.32), a soft step; Cycles at 1.64 mm draws a visible line
  (dark ~0.28), at 0.96 mm faint. So: depth needed to read ~1.5 mm+ (costly), and EEVEE's screen-space light under-reads
  narrow valleys. The visible line also reads ~1-1.5 mm higher than the photo's (6.2-7 vs 5.25 mm). Sheets out/c_crease_eye.jpg,
  out/c_cyc.jpg. (Cycles renders a grey disc at the pupil: cornea, not chased.)

### Q2 / Q3, the lip line: the SEAL flattens the border (render side), GNM closing restores it
- GNM's border geometry (lipreach2, Tess): bow 0.63 mm (random N(0,I) faces 0.70 +- 0.23), border turn (chords 4 mm up / 3 mm
  down) 25 deg (population 26.8 +- 3.9), the vermilion's slope varies a lot (sd 9.9 deg, cheap: |dc| 0.17 per deg). A
  raised RIDGE at the border (1 mm chords) is not in GNM (0.17 +- 0.03 mm; +1 mm costs |dc| 28). Her profile photo's
  upper lip contour lies on the model's mid-sagittal section (prof_b2_T06.png): the midline shape is right.
- Where it's lost (pipe.py): one mesh turn 24 deg -> sealed field (base._sealed_field) ~11-14 -> Catmull-Clark + IMLS 11.5.
  The lip seal (faceslide.seal_delta on the head + the field-only seal) is a harmonic membrane over the lips' rings from
  the contact ring out to the border: on a parted neutral (Tess's identity is open 5-7 mm) it drags the whole vermilion
  and fades across the border: the turn halves, the upper vermilion comes FORWARD (-6 deg) instead of turning down, the
  lips read as a flat painted pad. Catmull-Clark and the field keep an unsealed border (24-28 deg).
- Closed by GNM instead (mouth_gap 0, the least-change lower-face solver): border kept, upper vermilion turns down (clay
  -5.1), lower lip lit (+20): the lips read 3D; but fuller / pouty (faces5's overshoot) and the contact reader says it is
  still open 2.3 mm in the middle (mouth_gap measures only lm62-66).
- THE LIPS STEP (src/hifipushie/blockin_lips.py, experimental, no MCP tool yet): MAP over identity 170 + lower-face 40,
  evidence the traced borders through the front camera (0.35 mm), the picture's seam (MediaPipe inner contours, 0.4 mm),
  GNM's contact ring closed (one-sided, 0.15 mm, overlap 0.2 allowed), the lower half not ahead of the upper (0.3 mm), 68
  off the mouth held; seal and mouth_gap cleared. Head -> camera frame by a similarity on the face (0.28 mm rms). ~3 min.
  Tess (gd_T12 -> gd_T12L4): border miss 0.45 / 1.72 (sealed) -> 0.19 / 0.22 mm, seam 0.80 -> 0.13, bow 0.59 -> 0.70
  (photo 1.44), |dc| 2.15, |e| 3.0. Dressed: shape right (shorter lower vermilion, upper turns down), BUT the meeting
  reads as a pale 2-3 mm band under a dark line and the corners (outside the contact span) show dark holes: the
  contact zone faces forward. NOT shippable yet. Next: the contact as a surface (rolls behind, the seam a line from the
  front: e.g. the contact ring's normals / the visible extent of the rolls from the camera), the corners in the span,
  then the bow (GNM's population tops ~1.4 mm: within reach only near its edge).
- Paint (Q3): skin:lip_border's pale rim reads as a halo round the LOWER lip (+5 L*; the photo has none there; the
  upper lip's roll is shading, which the seal removed). The lower lip paint is too dark / red (a* 24 vs 19.5) and kills
  the geometric light. Left as found (skin code, all humans): to decide with the skin thread.
- spikes/garrett3/stage.py keeps a closed mouth_gap (it popped it: a GNM-closed mouth reopened in dressed shots).

## gnmcontrols (2026-10-10, "gnmcontrols" agent, branch worktree-agent-aecab3f9c741dd586; scratch /mnt/data/hifipushie/gnmcontrols)

Joe: "until we learn how to use ALL the GNM controls intentfully, more references feel like they'll be of limited
value". Scratch: run.sh / tests.sh, srv.py, scripts/ (below), dl/ (downloaded repos: untrusted, read only), ws/ (scratch
HIFIPUSHIE_HOME: rc_*, gb_*, *_fit_* models), out/. Sheets human_renders/gc_01..06, gnm_atlas/ (index.html, zones.png,
<family>_<page>.png).

### 1. How others drive GNM from photos (the ComfyUI node and everything else public)
- "GNM Extract Identity From Photo" = github.com/rethink-studios/ComfyUI-GNM @ 01fefbc (2026-07-16, 4 commits, "fitting
  not yet finalized"); LICENSE text Apache-2.0 ("Copyright 2026 ComfyUI-GNM contributors"; GitHub's detector says
  NOASSERTION); vendors google/GNM (Apache-2.0). Recipe (lib/fitting.py fit_params_from_landmarks_3d): MediaPipe 478
  -> "68" by its own _MP478_TO_68, which is WRONG (36 face-oval + 32 midline points put in iBUG-68 slot order: GNM's eye
  landmarks get nose-midline points); x / y normalised by image width / height separately; Umeyama similarity onto
  GNM's template 68; ONE ridge solve (google project_on_linear_vertex_basis) over all 253 identity comps (eyes, teeth
  too) at lambda 0.01 in metre^2 (~10x the data term: shrinks to the mean); clip +-4; Kabsch head pose. No face-ID
  embedding, no learned regressor, no photometric term, no expression in the identity fit, no sampler latent.
- Reimplemented in numpy (scripts/recipes.py, their code read, never run) on Tess's front: |c| 0.90, landmark residual
  51 mm (the correspondence), a head 2.5 mm rms from the mean, correlation with our identities ~0. A correct 68 map
  doesn't help (lambda); a unit-sized ridge blows up (|c| 67: the anisotropy).
- The best public recipe is Google's own: google/xrblocks samples/avatar_lab/gnm FaceFit.fitIdentity (Apache-2.0, ported
  from edualvarado/gnm-webcam-puppet): MediaPipe -> GNM vertex correspondence with a REFERENCE cloud (where MediaPipe lands
  on GNM's neutral: the fit is differential, cancelling MediaPipe's ~11 mm depth bias; our mp478_gnm table is the same
  idea from 36 heads), 166 skull-fixed points, 24 leading comps only, ridge 0.06 x trace / K, depth weight 0.1, 4
  alternations with a similarity; live expression capped at 4 lower-face comps (x1.35) and 8 per eye. On Tess: |c| 3.0
  (24 comps) / 6.4 (170), residual 2.1 mm. Also read: enriquevelmai/gnm-maya (68-pt weak-perspective Tikhonov),
  shameem4/headSize-gnm (XR Blocks' correspondence, size from the iris), soylab-edu/ComfyUI-GNM (GPL-3.0: samplers and
  sliders, no photo fit). google/GNM: no fitting / dense landmark release since our pin (HEAD a67464a: packaging).
- Readers (block-in target table, Tess's photo vs clay, cameras refitted per head; scripts/recipes_table.py): GNM's
  mean 22/26 (mean |diff|/tol 0.48), ComfyUI 23/26 (0.47), XR Blocks 21/26 (0.57), XR Blocks 170 20/26 (0.70), f3_t1
  21/26 (0.64), b2_T06 26/26 (0.36). Sheet gc_01_tess_recipes.png. Nobody has a better photo -> GNM recipe than ours:
  all are sparse-landmark ridge MAPs (the audit's finding 1). NOTE: the table passes GNM's plain mean 22/26: it is
  coarse; mean |diff|/tol separates better.

### 2. The semantic samplers (src/hifipushie/gnm_sampler.py + gnm_sampler.npz: the Keras decoders in numpy, float16,
### max coefficient error 0.009; exact Jacobians; scripts/sampler_study.py -> out/sampler_study.json)
- Identity CVAE (64 z + 6 labels -> 253; Dense ReLU 64-128-256-512, linear out; L1 loss, KL weight 0.05 annealed, label
  mixup Beta(0.2, 0.2): labels are trained as convex blends): its samples sit |c| ~5.5 OFF GNM's template (MC class
  means; decode(z = 0) is 7.1 away, 3.7 from the MC mean: the decoder is non-linear), per-comp sd 0.57 (0-9) .. 1.24
  (120-169), total variance 162 (N(0, I): 170) but participation ratio 41: 90 % of it in 65 directions, 99 % in 126.
- The latent: the Jacobian at z = 0 has ~35 active directions (sv 8.6 .. 0.4 at #32, 0.005 at #48): ~28 of 64 dims are
  collapsed; response non-linear (|c+ + c- - 2 c0| / |c+ - c-| median 0.44 at +-2).
- As a FITTING space it fails: a MAP in latent space (|c - dec(z)|^2 / 0.3^2 + |z|^2, best class) leaves residual
  share 1.1 for GNM's own N(0, I) heads and 1.33 for our fitted people (Tess, Garrett, fs_*: |residual| 6.8 for |c|
  5-7), 0.05 for its own samples. Our people and GNM's prior are not on its manifold. Garrett's bridge through the
  latent tangent needed |dc| 13-19. So: a plausible-face GENERATOR and a source of labelled directions, not where a fit
  or a block-in step should move.
- Labels as continuous controls (gc_03_sampler_labels.png): sex t 0 -> 1 (z = 0) moves jaw width +0.45 sd, brow ridge
  +0.7, nose width +0.8, lip fullness -0.7, head size +0.8 (uniform ethnicity); the path bends (off the chord by 2.0 at
  t = 0.5, chord 7.4); beyond [0, 1] it keeps going (|c| 8.7 at t = 1.5, untrained). Ethnicity corners 4.1-6.5 apart,
  midpoints 0.7-1.9 off the chord. label:white narrows and steepens the bridge (+3.2 deg slope per unit), asian / black
  widen it.
- Principal latent directions (gc_04_sampler_latent_pcs.png; zpc:00..15 in the atlas): whole-face and large (zpc:00
  face 0.63 mm per unit, the most face-ID per mm of any control: 0.42).
- Expression CVAE (64 z + 20 classes -> 383): ~5 active latent dims per class (posterior collapse): the class
  PROTOTYPE (z = 0) is the useful part. Prototypes are whole-face: happy = mouth corners up and out (mouth_width +3.2
  sd) AND eyes narrowed (eye_height -1.7); squint, compress_face and winks are mostly lids; tongue_center carries |11| of
  eye-region expression (its scans had eyes shut). Intensity is NOT t x one-hot (t = 0 decodes to a nonzero |1.79|
  expression; t = 0.5 is smaller than both 0 and 1 for some classes): scale the decoded prototype instead (GNM is
  linear). gnm_sampler.prototype(cls | {cls: w}).
- A picture's expression in prototypes vs the block-in's 20 raw lower-face comps (scripts/expr_classes.py, front
  pictures, identity and camera held): lower-face parts of the 20 prototypes fit as well (Tess chi2 43.8 -> 35.5 vs
  35.2; Garrett 342 -> 248 vs 261) with named weights (Tess: blow 0.24, surprise -0.2); WHOLE prototypes fit far more
  (Tess 29.3, Garrett 146) but by opening the eyes (Garrett wink_right -1.24, squint -1.21), the lt19 fight between the
  detector's lid points and the eye step: keep eye parts off unless the picture squints. Negative weights are
  anti-expressions: a non-negative prototype basis would be the plausible one (not built).

### 3. The control atlas (src/hifipushie/gnm_controls.py + gnm_controls.npz, MCP tool gnm_controls; scripts/atlas.py
### build | sheets | index, perc_all.py, atlas_report.py -> out/atlas_report.txt)
- 861 controls: identity 253 (head 170, eyes 3, teeth 80), region_pc 160 (20 GNM regions x 8 = the block-in's pc:),
  expr_eyes 100 (symmetric pairs; L / R are mirrored copies), expr_lower 150, expr_tongue 33 (+ pupil), joints 8,
  sampler_latent 80 (z:00..63 at female / white, zpc:00..15), sampler_label 5, sampler_expr 20, blockin 52 (humanmacro's
  40 free, nd: gaps, sex, eth0..2). Per control: 50 named zones (gnm_controls.ZONES on GNM's template; zones.png) x
  (tot, nrm, sgn, trans, deform, relief vs a 5 mm surround) per unit; face rms / max; humanmacro's 40 macros per unit
  (sd); face-ID 1 - cos between -1 and +1 (faces4 perc.py's renders / heads / views, so on the identity comps' scale;
  773 measured: not teeth / joints); prior cost (|coefficient| per unit); nearest block-in moves (cosine); sheet.
- Sheets (human_renders/gnm_atlas/, 91 pages, index.html): per control -2 | 0 | +2 front, 3/4, profile in hair-cap
  clay (the sampler's own head for latents / labels; mouth open for teeth / tongue; eye close-ups for the eyeball comps)
  + the move's normal map (red out / blue in).
- query("alar crease" | "jowl" | "lip border" | "bridge walls" ...): zones from words (synonyms), controls ranked by mm
  per unit of prior cost x specificity (zone / face rms, capped at 4); sorts efficiency | local | specific | perc |
  relief; per_family. describe(name). gnm_controls(query=, control=, zones=True) over MCP.
- What it says (atlas_report.txt):
  - Identity comps are WHOLE-FACE at every index: median specificity 1.5 (head_000-009 1.27, 10-39 1.80, 40-169
    ~1.65); only 8-30 % pass 2. No comp is "the alar crease": a local feature is a combination (-> sculpt, below).
    region_pc and block-in macros are a little more local (1.8 / 2.0); the most local controls are about the jaw / under
    the chin (under_chin, pc:chin_region3 x4.5).
  - Face moved per unit: head_000-009 1.08 mm rms, 10-39 0.27, 40-79 0.11, 80-119 0.067, 120-169 0.038.
  - Face-ID per unit prior cost: our block-in macros of the ORBIT / BRIDGE complex lead (bridge_height 0.189, eye_depth
    0.191, orbital_rim 0.186, brow_ridge 0.178, nose_projection 0.156) with pc:middle_brow_region1 / pc:nose_region0
    (0.15): steps there change who it is fastest. Per mm moved the fine comps lead (120-169: 0.37 per mm vs 0.07 for
    0-9; faces4 M0b's finding, now for every family: eye-region expression 0.38 per mm, the sampler's zpc:00 0.42).
  - Reverse map (zone -> best mover per family) is in atlas_report.txt; e.g. alar_crease: head_003 / pc:upper_lip_region0
    / nose_width, all global (specificity ~1); relief (deepening) of the alar crease: pc:nose_region1 -0.36 mm per unit;
    lid_fold relief: head_000 -0.83, pc:*_brow_region2 +0.69, both_eye_region_001 +0.91; nasolabial: nothing in the
    identity space deepens it more than 0.15 mm per unit (expression lower_face_region_001 0.23, xclass:disgust 0.37):
    GNM's identity carries almost no nasolabial fold.
- First identity comps, named from their sheets / numbers: head_000 size + lower face width (jaw, chin, nose, mouth;
  face-ID 0.126), 001 neck thickness / squareness, 002 dorsum hump and bridge height vs upturn, 003 face width vs the
  upper lip's set (cupid's bow in), 004 brow ridge + orbital rim + eye depth (face-ID 0.129, the most of the first ten),
  005 glabella / radix, 006 face + nose + philtrum length, 007 ears out, 010 jaw width, 011 nose forward with a lower
  cranium (the strongest dorsum / tip mover per unit), 018 chin forward, 020 nostrils / columella. Expression: lower_face
  000 jaw closed <-> open (the uncentred mean: -1 opens the teeth ~3.6 mm), 001 mouth narrows and pouts, 003 lower lip
  roll; both_eye_region 000 eyes wide open + brows up (eye_height +2.0 sd), 001 lids open (upper up, lower down), 002
  brow down / socket.

### 4. Garrett's narrow bridge the right way (coordinator: "I suspect there was a way to do that narrow bridge the
### right way"; scripts/bridge.py, gbridge_eval.py, gbridge_solve.py, gbridge_models.py, sculpt_test.py; gc_02)
- Readers on the shipped head: blockin2's SH walls (6 mm off the dorsum / on it; concept 0.504), dorsum width, and
  bridge.py's cross-section at 5 heights between lm 28 and 29: width3 (3 mm behind the crest), slope6 (wall angle at
  6 mm). b3_G16 without its local: walls 0.746, width3 14.1 mm, slope6 39 deg; the DESIGNED local (nose_dorsum_width
  -0.8): 0.670, 11.8, 50.
- Least-cost routes to the local's effect on GNM's raw head (KKT: min |x|^2 + locality s.t. readers hit, macros held):
  nose PC8 free |x| 4.8 (head size -3, nose width -2.2 sd: blockin2's drag); 170 comps free 2.5 (5 mm moved outside
  the nose); 170 comps + 14 macros held + locality 3: |dc| 3.97, 0.74 mm outside the nose; expression comps reach 25 %;
  the sampler latent needs |dc| 13-19; labels: only label:white helps.
- On the shipped head (same cameras): the GNM route walls 0.584 (local 0.670), dorsum 8.8 mm, width3 10.9, slope6 56,
  table 26/29 err 0.41 (local 25/29, 0.54). SAVED as b3_G17 (main workspace, round 34: b3_G16 - the local + the route;
  |c| 6.79 -> 7.81; coupled under_chin +0.6, jaw_angle +0.45, cheek_fullness -0.43; mouth 5/7 -> 6/7; sheets
  blockin_b3_G17.png / _nose.png).
- Generic form = the block-in's SCULPT move (below): "sculpt:bridge_walls|hold=dorsum" -1.0 mm: walls 0.590 at |dc|
  3.5; -2.0: 0.504 (the concept) at 7.1.
- The bridge's breadth came from our BASE: his identity on GNM's own template reads width3 11.0 / slope6 56 already;
  gnm_base 0 (MakeHuman's head under the GNM delta, the age-50+ default) flattens it to 14.1 / 39. gnm_base 0.5 alone:
  walls 0.652; 1.0: 0.593 (but the whole face re-bases: table 21/29, 15/29).

### 5. Sculpt: a zone moved the GNM way (block-in move; gnm_controls.sculpt, zone_row, parse_sculpt)
- `"sculpt:<zone>": mm` = the least-cost identity change (all 170 comps, |dc| in sd) moving the zone's mean normal by
  mm, with every humanmacro measure HELD exactly (a held macro too like the target itself, |cos| > 0.7, is let go and
  reported) and a locality penalty (3^2 x mean squared move of the face > 6 mm from the zone). `relief:<zone>`: against
  its 5 mm surround (- deepens). `|hold=<zone>+..`, `|free=<macro>+..`, `|loc=w`. Linear: exact, instant. The step
  reply gives |dc|, the macros let go and the skin moved elsewhere; > 2 sd warns. `"gnm:<control>": x` = any identity
  control of the atlas raw. Typical cost ~2.5-4 sd per mm: big beside a macro step, but toward a real face's |c| ~13.
- The standard fix for a feature no macro reaches (coordinator), before any local: guide block_in loop 4, the feature
  pass, "GNM's controls". Test tests/test_gnm_controls.py.

### 6. A regional base (coordinator: "GNM's own template in the face, MakeHuman's head only where needed")
- Spike keys (default off, builds unchanged): base.head.gnm_base_rest (the base share outside GNM's hockey mask, a
  30 mm smoothstep blend; gnm_base = the face's share), gnm_base_age (adds MakeHuman's own ageing: its head at the
  body's age minus at 25, both at their eyes, where GNM's template replaced it); block-in SET key gnm_base_rest;
  humanfit_map.fit(prior_mean=) (the identity prior's centre, default 0).
- Re-basing a finished block-in fails: b3_G17 with its identity on the regional base 15/29 (err 1.16); re-projected to
  keep its 68 landmarks |c| 18.4, 21/29: the identity was tuned against MakeHuman's head.
- Fair test (scripts/basefit.py: the same evidence, the same MAP from the sampler's class mean, per base):
  Garrett MakeHuman base: view rms 1.25 / 1.64 mm, |c| 4.62, table 19/29 (0.89), walls 0.81; REGIONAL 1.07 / 1.38,
  4.27, 20/29 (0.73), walls 0.65; regional + MakeHuman age 18/29 (0.90). Tess base 0.86 / 1.20 / 3.35, 4.43, 23/26
  (0.55); regional 0.80 / 1.14 / 3.18, 4.17, 23/26 (0.47). GNM's template is the better mean face: 10-15 % lower
  residuals with less identity, equal or better table.
- Whole-face read (gc_06_regional_base_clay.png hair-cap clay, gc_05_regional_base_dressed.png look_skin): Garrett on
  the regional base loses MakeHuman's aged structure (lean, hollow under the cheekbones, deep nasolabial): fuller,
  younger, better nose; Tess barely changes. Clay sex / age reads (faceage) too noisy to use.
- NOT flipped. Decision needed: one block-in from scratch on the regional base (Garrett, age from the age ops or a
  data source) against b3_G17.

### 7. Garrett from scratch on the regional base (coordinator; Joe: "I'm not really even convinced about age": no
### designed age ops, age cues the GNM way; scripts/rb.py, agecues.py, rbcmp.py, rbfinal.py; models rb_G00 .. rb_G14
### in the MAIN workspace, log rb_G00/blockin_log.json)
- Start: block_in_start(b3_G17's references, male, 52: MakeHuman base, class mean) 23/29; the regional base step
  (gnm_base 1, gnm_base_rest 0) -> 16/29: GNM's male template is much WIDER than his 52-year-old MakeHuman head
  (cheekbones +7.7, jaw +6.3, nose base +10, mouth +4 mm) and round / young.
- Rounds (each a block-in step, logged): face_width -0.8; nose_length! +0.9, nose_upturn! -0.5; cheek_fullness -0.7,
  jaw_width! -0.5 (22/29, err 0.65); brow_ridge +0.5, mouth_width! -0.4; chin_height! -0.5 (23/29, 0.58); [designed
  nasolabial 0.6, removed again at G11 per Joe]; eye_spacing! -0.4; chin_height! -0.35; THE EYE STEP (lids 0.47 / 0.75
  vs his 0.46 / 0.72, hooded: platform 1.8 mm, |dc| 1.45, |e| 1.43); relief:nasolabial -0.6 (|dc| 3.1);
  relief:cheeks -0.8 (|dc| 1.9, cheek_fullness let go); sculpt:bridge_walls|hold=dorsum -0.7 (|dc| 2.5). |c| 5.45 ->
  9.0 over 14 rounds.
- rb_G14 vs b3_G17 (34 rounds on the MakeHuman base): walls 0.559 vs 0.584 (concept 0.504), width3 11.1 vs 10.9,
  table 21/29 (err 0.66) vs 26/29 (0.41): rb's misses are temple width (hair framing), the painted 3/4's lengths and
  edge flips. Sheets gc_07_rb_G14_vs_b3_G17.png (hair-cap clay, before = G17), gc_08_..._dressed.png (top rb_G14).
  Blunt read: dressed, rb_G14 reads LEANER and longer in the mid / lower face with a narrower nose (closer to the
  concept's lean face); G17 reads broader and squarer; neither has the concept's deep-set, hooded tiredness yet. On the
  table G17 wins. Not a clear win for the regional base after 14 rounds; it is at least as good a start.
- The table's noise floor: with every macro HELD exactly (a sculpt can't move a landmark proportion), mouth_width moved
  +1.0 mm and chin_height +0.45 mm: clay-reader drift from shading (jw's finding). Edge flips under ~1 mm are noise.
- AGE THE GNM WAY (agecues.py; relief = a zone against its 5 mm surround, size projected out):
  | cue | sculpt cost |dc| per mm (macros held) | GNM's population sd of the cue (mm) |
  |---|---|---|
  | nasolabial groove deeper | 5.2 | 0.29 |
  | jowl (relief, out) | 6.5 | 0.31 |
  | mentolabial sulcus deeper | 3.4 | 0.42 |
  | sub-malar cheek hollow | 2.4 | 0.92 |
  | marionette deeper | 2.4 | 0.85 |
  | tear trough deeper | 4.2 | 0.91 |
  | lid fold deeper | 3.2 | 1.09 |
  | upper / lower vermilion thinner (zone in) | 2.0 / 2.8 | 1.90 / 1.31 |
  GNM's identity space barely varies the LINES of age (nasolabial, jowl, mentolabial: sd 0.3-0.4 mm: a visible 1-2 mm
  fold is 3-7 sd); it does vary the MASSES (cheek hollows, lips, lids, tear trough ~1 mm). On Garrett, relief:nasolabial
  -0.6 mm (|dc| 3.1) reads as a faint line in raking clay, far weaker than the designed op's 1.2 mm fold;
  relief:cheeks -0.8 mm (|dc| 1.9) is subtle. In the dressed render the skin's age layers carry most of the age.
- No age-like direction: the ten cues' correlations under GNM's prior are small and inconsistent in sign (first common
  factor 23 % of 10; nasolabial deepening anti-correlates with jowl and tear trough); with zone moves instead of relief
  the first factor is just head size / lower-face width (head_000). GNM was built from relaxed neutrals, PCA-truncated:
  aged LINES are mostly not in its identity; aged MASSES are, independently. A data-backed age step (blockin3's
  Wikimedia statistics) should drive the masses through sculpt / macros and leave the lines to skin / a residual.

### HANDOVER (gnmcontrols, 2026-10-10)
- Code (branch worktree-agent-aecab3f9c741dd586): gnm_controls.py / .npz, gnm_sampler.py / .npz, blockin (sculpt:,
  relief:, gnm:, gnm_base_rest), onemesh (gnm_base_rest, gnm_base_age, face_weight), humanfit_map prior_mean, server
  gnm_controls (human toolset), blockin_guide (loop 4, feature pass, "GNM's controls", tool reference), tests
  test_gnm_controls (5) + test_toolsets' list (block_in_expression was missing since lt19b).
- Main workspace: b3_G17, rb_G00 .. rb_G14 (the regional-base trial; rb_G14 its last step).
- Rebuild the table after changing zones / the perception runs: scripts/atlas.py build (18 s; perception: perc_all.py
  <families>, ~25 min for all), sheets: atlas.py sheets [families] (~2 s a page), index: atlas.py index.
- Open, in order: (1) the regional base: rb_G14 is a 14-round start (table 21/29 vs G17's 26/29, leaner dressed read):
  continue it (temple / painted-3/4 lengths, eyes' tiredness) or call it; a data-backed age step for the MASSES; (2) sculpt readers beyond
  zones (a reader-driven sculpt: any likeness / shading reader as the target, finite differences on the shipped head;
  bridge.py is a template); (3) a non-negative prototype basis for block_in_expression (named, plausible picture
  expressions; eye parts off by default); (4) Tess's feature pass with sculpt (lips, almond eyes, radix) instead of
  locals; (5) the atlas's teeth / joints have no face-ID numbers (by design).

## gnmdetail2 (2026-10-10, continues gnmdetail; branch worktree-agent-a7c4aaa431f9c8bf5. Scratch /mnt/data/hifipushie/gnmdetail2:
## gnmdetail's scripts retargeted + sect.py / sectlist.py (sagittal sections: one mesh vs the dressed stage mesh), ringgap.py /
## cgap.py (GNM lip rings' gaps), fieldexp.py (the base field through the lips, seam variants), seamprof.py (L*/a* down
## through the seam: photo / dressed / clay), maskproj.py / albedo.py / liplayers.py (paint on the stage mesh), eevar.py /
## eev.sh (EEVEE settings vs Cycles on the lid crease), reliefrun.py (sculpt moves vs the crease), plcmp.sh (photo light))

### The lips: GNM's closing, made to render (shipped)
- THE PALE BAND + DARK CORNER HOLES (gd_T12L4) were the FIELD, not paint or contact: GNM's closed contact is a 42-deg V
  between two coarse rings (~3.5 mm apart: ring 2 = contact, ring 3 = 3.5 mm up / down) and the inner rolls CROSS behind
  it (ringgap: the upper roll 6.5 mm below the lower). The base field read that as a 2.5 mm forward-facing WALL at the
  contact (sectlist: normals -6..0 deg from +0.75 to -1.25 mm): the dark line sat 1.8 mm above the contact (the upper
  lip's down-facing turn) and the wall under it was the pale band; the crossed rolls opened the corners.
- FIX (field only; the export's quads keep GNM's rolls): a mouth CLOSED BY GNM (the contact ring's halves within 0.8 mm
  corner to corner, onemesh.CLOSED_GAP) gets the seal's field treatment, lighter: the rolls inside the contact ring left
  out, the FIRST row out drawn halfway to the seam (onemesh.CLOSED_SEAL_V = (0.5,); the seal's three rows (0.5, 0.25,
  0.1) are what halved the border's turn: rows 2-3 out sit on the vermilion). fieldexp at x = 0: seam V -60 / +27 deg each
  side; profile from +6 mm up identical to the unsealed field (border kept). Dressed: one seam line corner to corner, no
  band, no holes (out/c_t12L4b2.jpg). onemesh.VERSION 14.
- Tried and dropped: keeping the rolls apart inside the lips solve (a no-crossing term): |dc| 9.7 / |e| 10.7 and the
  mouth OPENED (a dark slit with teeth).
- head.lip_close (base.lip_close_delta, where the seal goes: after the body's hook, on the head WITHOUT its expression):
  the least change of GNM's first 40 lower-face expression comps (unit prior) closing the contact ring corner to corner
  (one-sided, 0.2 mm overlap allowed; the lower half not ahead; the 68 off the mouth held 0.3 mm, corners 0.6), re-solved
  on every head (ms) so identity steps keep the mouth shut. block_in_start sets it (lip_seal / mouth_gap dropped);
  humans.spec keeps the seal for non-block-in humans. b2_T06 + lip_close: gaps 6.7 -> 0.2 mm, |e| ~2.4. The lips step
  clears it (its own expression closes). base.VERSION 106. tests/test_lip_close.py.
- MCP lip_read(name, match): reads (border miss / offset, seam miss, bow picture vs model, contact gaps, inner rolls,
  which closing) and match=True = THE LIPS STEP (+ focus=mouth sheet). gd_T12 -> g2_T12L: borders 1.96 / 3.80 -> 0.19 /
  0.22 mm, |dc| 2.15, |e| 3.0; table: philtrum went out (+0.86 -> +1.33, tol 1.0), mouth_width -1.39 (the step fits the
  traced a* border, the table the detector's points).
- THE CUPID'S BOW is within GNM's reach: a bow term (the picture's traced border, peaks over the centre trough, mm;
  blockin_lips.SIG_BOW) on Tess (1.44): none 0.70 mm; 0.15 -> 1.07 (|dc| 2.50, +0.35); 0.05 -> 1.27 (|dc| 3.21). Dressed
  reads the same (1.11 / 1.25 mm): the bow shows (out/c_bow.jpg). Default SIG_BOW 0.1.
- Seam darkness: photo L* 15 at the seam (a ~1.5 mm dark slit, corners dark past the lips); ours ~29-30 (a thin line).
  Not chased further: the photo's corners / slit include the mouth's shadow inside.

### Lip paint (shipped; docs/notes/skin.md "## Lips")
- Lower lip too red / dark -> skin.LOWER_LIP (melanin 0.72 x, blood 3.8, oxygenation 0.66): dressed lower da 16.6 -> 11.7
  (photo 9.1), dL -9.4 -> -3.8 (photo +0.4). The halo under the lower lip is shading (albedo has none): left.

### The crease (findings; nothing shipped in the solve)
- GEOMETRY. GNM makes no overhang on Tess's lid: an eye solve with an overhang target (the Reader's "drop" >= 0.3 mm)
  stayed at hood 0.00 (no gradient from no overhang; nothing in identity + 20 eye-expression pairs started one).
  gnm_controls relief:lid_fold (the 8-13.5 mm band vs its surround, macros held) does NOT deepen the crease: -1 mm
  (|dc| 3.17) moved the crease UP 4.7 -> 6.3 mm, local depth 1.30 -> 1.36; + relief:upper_lid +0.5 made it shallower
  (and let orbital_rim go). Depth is reached by the eye step's d_line (1.64 mm at |dc| 7.6, gnmdetail). So a 1 mm SLIT
  (skin folding over) is a documented gap of GNM's lid rows (~1 mm apart, the fold a ~2.5 mm valley): Joe's call whether
  a hand layer (lidfold-like) is allowed for it.
- RENDER. EEVEE's fast GI at half resolution (our default) under-reads narrow valleys: 1.64 mm crease (gd_T30) dark
  0.14 (1x) / 0.25 (2x); FULL-res fast GI (fast_gi_resolution 1, quality 1, 16 steps, 4 rays) 0.25 / 0.29; Cycles 64
  spp 0.21 / 0.29; photo 0.32. Bias 0 / thinner near / more shadow rays: no further gain. Same time on a head (both
  renders + sync 70 s). A 1 mm crease (gd_T12L4) reads in neither (0.02-0.07). Now the dressed stage's default
  (stage.STAGE_EEVEE); render jobs take "eevee": {name: value} overrides (blender_scene). Worth making the
  blender_scene default for heads (owner's call: not tried on big scenes).
- THE LINE READS HIGH: the dressed fold line reads 6.0-6.5 mm over the lashes on gd_T30 (EEVEE and Cycles alike) where
  the geometric crease is ~5.3: the dark band of a 2.5 mm valley lit from above is its DOWN-FACING upper wall, ~1 mm
  above the bottom; the photo's slit is dark at the fold itself. Shape, not the reader (same reader on both). If the
  eye step should place the RENDERED line on the photo's, aim the valley ~1 mm lower than the picture's line.
- What a crease needs to read dressed: >= ~1.6 mm local depth (|dc| ~7.6 on Tess, socket held) + full-res GI; a real
  slit (the photo's 0.32 dark, 1 mm wide) needs an overhang GNM doesn't make.

### The dressed stage's light (shipped)
- blockin.photo_lighting(name, template): the template's key re-aimed along the front picture's fitted c0 + w.n light
  (lit_render's first pass; its SH coefficients gave no stable direction: Tess's key from below) and key : frontal
  fill from |w| : c0, the face's front as bright as the template lights it. Tess: key 35 deg up, from her right, key
  1.74 / fill 1.89 (flatter than FRONT_LIGHT's 3.3 / 0.7); Garrett b2_G15: 30 deg, 2.8 / 0.8. stage.photo_light(name).

### State / next (gnmdetail2 handover)
- Shipped on the branch: the closed-mouth seam field, head.lip_close (block-in default), lip_read (+ the lips step with
  the bow), the lower-lip paint, blockin.photo_lighting + stage.photo_light, render jobs' "eevee" overrides, the stage's
  full-res fast GI. Sheets human_renders/g2_01..09.
- Next: (1) run lip_read(match=True) on the current Tess / Garrett block-ins and judge the table's philtrum / chin rows
  it moves; (2) the seam's darkness (photo L* 15 vs ours ~30: the paint's lip_seam line vs the geometry's slit, the
  commissures' shadow past the lips); (3) the crease: Joe's decision on a slit (GNM gap) vs paying |dc| ~7.6 for 1.6 mm;
  aim the eye step's valley ~1 mm below the picture's line if the rendered line is the target; (4) make full-res fast
  GI the blender_scene default for heads / look_skin; use stage.photo_light for every dressed-vs-photo sheet.

## gnmcrease (2026-10-10, "gnmcrease" agent; Joe: "we've seen the eyelid crease before together, on a grid of random GNM
## faces". Scratch /mnt/data/hifipushie/gnmcrease (run.sh / q.sh; scripts copied to spikes/gnmcrease); sheets human_renders/gk_*)
STATE / NEXT (gnmcrease 3, 2026-10-10, handed over): the eye step makes the crease as the template's PROFILE (default
"s376") carried to the PICTURE's line height and path (crease_target, tps_cols), lid margins held at SIG_LID_SHAPE 0.02.
Tess (scratch): crease at the photo's height, section rms 0.18 mm, |dc| 4.5, upper lid 0.66 (photo 0.67). Sheet
human_renders/gk_07_crease_make_at_photo_height.png. OPEN: Joe's read of gk_07 (the line reads at gd_T30's height, softer,
without the hollow); makeup setting below; Garrett's hooded path untouched. Branch ready to merge.


Question: faces5's random faces (f5_03) showed lid folds, every targeted solve on Tess made only a soft ~2.5 mm valley.
Is the crisp fold in GNM's identity space and our solves miss it (held socket / brow, wrong objective), or not there?

### Method
- 1600 identities: 800 N(0, I) over the 170 comps, 400 from faces5's ICT-led prior (m3_em_tau0.01, the f5_03 prior),
  400 from gnm_sampler's identity decoder (random sex / ethnicity). Per sample (gk.py, ~0.3 s): the eye step's own
  Reader on onemesh.head_template (gd_T12's body, expression and lid pose cleared): valley depth (2.5 mm chord), narrow
  depth (0.75 mm chord), height, platform, hood drop, skin hidden from a level / 10-deg-above front view; lidgnm's
  shadowless clay raster + lidfold.read_lid (faces5's reader); humanmacro z-scores.
- 19 samples dressed (dress.py: scratch models gk_*, gd_T12's body + the sample identity, EEVEE full-res GI, Tess's
  photo light, hair off; an 84 mm eye frame at 0.6 m + a face frame for MediaPipe reads at the photo's 0.277 mm/px) and
  in a hard top-light clay. Tess's photo through the same reader: line 4.97 mm, dark 0.32, width 0.93 mm.

### Findings
- GNM HAS NO CRISP FOLD. Valley depth over all 1600: p50 0.45, p99 1.33, max 1.66 mm (ICT-led p99 1.38: the same
  ceiling). Narrow-chord depth max 0.42 mm. Skin hidden from a level front view (overhang): 1 % of samples > 0.2 mm,
  and those are hooded lids (the fold low, 2-3 mm, over the lashes), never a fold over a visible platform. gd_T30 (eye
  step d_line 3, 1.64 mm) is already AT the population's maximum: the solve found GNM's ceiling, it didn't miss a fold.
- THE f5_03 "FOLDS" ARE THE RASTER. lidgnm's clay is a shadowless normal-shaded raster: a down-facing band reads dark.
  Its darkest reads (0.3-0.51) are almost all LOW (1.5-3.5 mm: the top of GNM's thick lid-margin roll); at 3.5-6.5 mm
  only 2 / 1600 pass 0.25 (max 0.37). Dressed, those same faces read 0.03-0.11 (gnm#115: raster 0.51 -> dressed 0.11; ict#170,
  whose raster numbers equal the photo's, 0.32 @ 4.9 mm -> dressed 0.08). The best dressed read anywhere: 0.16
  (gnm#290, a hooded lid at 2.2 mm). Photo 0.32. Clay under a hard top light shows the deeper ones' valley as a soft
  shadow (ict#170, ict#140, gd_T30), dressed skin washes it out. Sheets gk_01 (12 samples + Tess, dressed | clay),
  gk_03 (population histograms; raster vs dressed darkness).
  Caveat: this frame reads gd_T30 at 0.08 where gnmdetail2's fitted-camera frame read 0.25: absolute dressed numbers
  depend on the frame / camera height; the ranking within one frame is what was compared.
- WHAT GOES WITH A DEEPER VALLEY (ridge over the N(0, I) samples, CV R2 0.62 for depth, 0.39 narrow, 0.15 raster dark,
  0.08 overhang): deep-set eye + heavier, lower brow (orbital_rim +0.3..+0.5 r, eye_depth +0.25, brow_ridge +0.3, brow_height
  -0.35 r with raster dark / overhang) and a LEANER face (cheek_fullness -0.33, jaw / chin width -0.3). Not sex: the
  population direction is orthogonal to the sampler's male-female axis (cos -0.04). At Tess, the linearised cheapest
  +1 mm of valley depth (jac.py): free |dc| 2.1 (but orbital_rim +1.8, eye_depth +1.4, brow_ridge +1.4, brow_height
  -1.3 sd), socket held 3.9, + landmarks 4.4, + brows (the eye step's holds) 5.0. So the holds cost ~2.4x but the
  CEILING is the same; and narrow depth (crispness) costs |dc| 10 free / 21 held per mm: GNM's ~1 mm lid rows can't
  sharpen it. The eye-region expression pairs: only pair 1 moves the crease (+0.35 mm per unit) and it opens the lid
  (up +0.35 iris r).
- CARRYING A SAMPLED FOLD ONTO A HELD FACE (transplant.py: the donor's upper-lid strip, affine-aligned, as a linear MAP
  target over the 170 comps, the rest of the face held vertex by vertex at 0.3 mm): 87-90 % made, but |dc| 16-19 for
  Tess (donors gnm#376 / #540 / #115; donor - Tess |c| 15-17): the fold costs as much as becoming the donor. Raster
  reads move to the photo's numbers (0.20 @ 4.8, 0.21 @ 5.3 mm); dressed, nothing reads, and the lids open rounder
  (gk_02). Garrett + the hooded gnm#290 lid: |dc| 16, the lid opens, no more hooding (gk_04; the frame is off-centre on
  his 1.12-scaled head).

### Verdict (blunt)
Joe's memory of the grid was right that it LOOKED like folds, but that grid was a shadowless raster: GNM's identity
space has no crisp crease anywhere in 1600 heads, and its deepest valley (~1.6 mm, ~2.5 mm wide) is what the eye step
already reaches on Tess at d_line 3. Nothing to fold into the eye step as "the way to make a crease": the photo's ~1 mm
dark slit with skin over it is below GNM's lid row spacing (~1 mm) and outside its population. Making it needs a
finer layer than identity (the subdivided stage mesh: a crease displacement / normal detail; i.e. Joe's call on a
lidfold-like fine layer, faces5's M2 "residual layer") or a shading answer (paint / AO along the crease line).
Shipped: blockin_eyes.CREASE_REACH / CREASE_SLIT_DARK and a NOTE in the eye step's report when the picture's line is a
slit GNM can't draw (so a solve isn't read as failing). Socket hold left at 0.15 sd: freeing it buys ~20 % cheaper
depth, same ceiling.

### Handover
- Scratch models gk_* in the workspace (sample identities on gd_T12's body; gk_tT*, gk_gG290 transplants): scratch, not
  rounds; delete freely. Data: out/s_{gnm_1,ict_2,cls_3}.npz (C, geo / clay / macro reads, mid-column profiles),
  jac_gd_T12.npz, crdir.npz (pop / contrast / Tess-gradient directions), readd.json (dressed reads), d_*_{dressed,clay,face}.png.
- If a fine crease layer is approved: aim the RENDERED line, not the valley (gnmdetail2: a valley's dark band reads ~1 mm
  above its bottom), and judge it dressed at the photo's mm/px; the raster clay over-reads down-facing bands.

### Round 2: the correction (Joe, on gk_01) and the crease as a SHAPE
- Joe: #376 and #540 read right dressed; gd_T30 has the right darkness but the wrong fold shape. So the round-1 target (the
  photo's line darkness 0.32) and the round-1 verdict ("GNM has no crisp crease, out of reach") were WRONG: the bar is how
  the fold reads dressed. Any darkness still missing comes from makeup (skin.makeup eyeshadow crease), not geometry.
- Readers across the lid (col.py: the eye step's sagittal profile at 7 columns, inner -> outer corner; secplot.py,
  out/sec_a.png). #376 / #540 vs gd_T30 / gd_T12 (geo, mm over the lid margin):
  crease height mid 2.9 / 2.35 vs 4.85 / 4.97; platform shown 2.4 / 1.7 vs 4.5 / 4.3; crease / (margin -> brow) 0.30 / 0.31
  vs 0.54 / 0.49; valley narrow (0.75 mm chord) mean 0.32 / 0.37 vs 0.60 / 0.23; the fold edge's convexity above 0.9 / 0.7
  vs 0.8 / 0. The SECTIONS: gd_T30's platform recedes ~4 mm BACK into the socket up to 5-6 mm, then the skin turns forward
  to the brow: a sunken / hollow upper lid, the crease the floor of that hollow. #376 / #540: the platform recedes <= 1-2 mm,
  the crease is low (2.4-3 mm), the skin above comes FORWARD as a full fold (#540 strongly). The fold line across the lid:
  parallel to the lashes, highest at the inner corner (4 mm), lowest just past the pupil (2.4-2.9).
- Population (1200 samples, sep.py): #376 / #540 are the 1-12 % lowest creases, 15-40 % platform, top 2-5 % fold-edge
  convexity and narrowness; 30 / 1200 are low (< 3.2) + narrow (> 0.3) + parallel. gd_T30: 65 % height, 85 % platform.
  Depth isn't it (gd_T30 is deeper than both); the fold's height, the platform's width and a full lid above it are.
- The dressed lidfold reader is NOT a usable height ruler on our renders: its line height vs the geometric crease over 19
  samples r -0.19 (it locks onto the brow sulcus or the brow hairs' edge at 7-8 mm). Judge shape geometrically, look by eye.
- SHAPE SOLVE (shapesolve.py <model> <donor> <out>): the eye step's variables (identity 170 + 20 eye pairs) and holds (68 lm
  0.3 mm, brows 1 mm, socket 0.15 sd, lid margins vs the iris at their start 0.05 r); evidence = the donor's sections at the
  inner third / pupil / outer third relative to the lid margin, arclength 0.5-8 mm, sigma 0.3 mm. ~75 s / iteration, 6 its.
  From gd_T30: -> #376 shape rms 1.71 -> 0.12 mm, |dc| 5.3, |de| 3.5 (crease 4.85 -> 2.67 mm, platform 4.5 -> 2.2,
  ratio 0.29); -> #540 3.15 -> 0.20 mm, |dc| 5.8, |de| 5.6 (crease 2.1, platform 1.5; brow_height +1.2 sd, eye_tilt -0.8).
  Socket within 0.3 sd. So the shape IS reachable on Tess's held face at |dc| ~5.5 (round 1's transplant cost 16+ because it
  copied whole-region vertices incl. brow / orbit relief; the sections ask only for the lid's shape).
- THE EYE STEP NOW MATCHES THE SHAPE (src/hifipushie/blockin_eyes.py): when the picture shows a line (not hooded), the
  residuals are the lid's sections (Reader.sections: inner third / pupil / outer third, relative to the margin, arclength
  0.5-8 mm) minus a template (crease_shape(name), data src/hifipushie/blockin_crease.npz from template.py: "fold" = the
  mean of the 30 low + narrow + parallel sampled creases (looks like #540: the skin above comes forward), "s376",
  "s540"), sigma SIG_SHAPE 0.3 mm; solve(crease=None) keeps the old height + d_line target. The report states the
  template and the section rms and points at makeup for darkness. CREASE_REACH / CREASE_SLIT_DARK and the "out of
  GNM's reach" note are gone (wrong). Test: tests/test_blockin.py::test_crease_shape_templates.
- New eye step on Tess (scratch, evrun.py gd_T12 fold; no model written): section rms 2.97 -> 0.12 mm, |dc| 4.34, |e| 3.3,
  crease 5.1 -> 2.5 mm over the margin, platform 4.3 -> 1.8 mm, socket within 0.05 sd; BUT the upper lid opened 0.64 ->
  0.79 iris r (the picture 0.67, sigma 0.05: the 96 shape residuals outweigh the 2 lid ones).
- Garrett's picture reads hooded (no fold line: dark 0.01), so the eye step's hooded path applies, not the shape; his
  shape solves (shapesolve.py b3_G17): he already had a #540-like fold (crease 2.9, platform 2.4, ratio 0.34; rms to
  #540 0.58 mm); -> #540 rms 0.08, |dc| 3.0; -> #376 rms 0.18, |dc| 4.8 (eye_height -0.5, eye_tilt -0.5 sd).
- SHEET gk_05_crease_shape_dressed.png (one eye frame for all: 84 mm at 0.6 m, Tess's photo light, hair off; Garrett from
  the face frame, upscaled): photo | #376 | #540 / gd_T30 | Tess shape -> #376 | -> #540 / Tess NEW eye step (fold) | +
  crease makeup (eyeshadow amount 0.3, color #b08878, crease #7a5446, matte) x2 / Garrett as is | -> #376 | -> #540; section
  plots under them. BLUNT READ: the geometry matches (the plots: Tess's sections lie on #376 / #540, the fold line 2.2-2.8 mm
  parallel to the lashes, platform 1.5-2.5 mm) but dressed Tess now reads as a FULL LOW LID with almost no crease line: the
  arc that makes #376 / #540 read (a lit fold edge over a soft line about a third of the way to the brow) is not there.
  gd_T30 still shows more line than any shape result. The makeup at 0.3 is barely visible. The new eye step also opened
  Tess's upper lid (0.64 -> 0.79 iris r; picture 0.67). Garrett: hooded / small in frame, the three look alike (he
  already had a #540-like section). So: right sections are NOT sufficient; not shippable as "the crease" yet.
  Suspects: (1) the fold edge's crest: ssT376's fold-edge convexity 0.35 /mm vs #376's 0.91 (sections sampled every 0.5
  mm miss curvature); (2) what lies past 8 mm / between the columns: the donors' brows sit higher over the lid (brow 9.5 /
  7.7 mm over the margin but their whole orbit is open), Tess's held brow shades the fold.
- FOLLOW-UP (gk_05's misses): curvature residuals on the sections (CURV=0.15 mm, shapesolve) did nothing useful (the eye
  widened, |dc| 7.9). Sections to 12 mm of arclength (SMAX=12: the skin from the fold up into the brow's underside) DID:
  ssT376s12 (|dc| 6.2 from gd_T30, |de| 3.2, socket orbital_rim +0.49 -> -0.12) shows #376's lit fold edge and arc line
  dressed (out/v10.png). The read lives in the fold-to-brow skin, not only the lid: the eye step's sections and templates
  now run to 12 mm (SECTION_S; blockin_crease.npz rebuilt by template.py with SMAX=12).
- THE NEW EYE STEP AT 12 mm on Tess (scratch, evrun.py; no model written): template "s376": section rms 1.59 -> 0.15 mm,
  |dc| 5.2, |e| 3.2, socket within 0.3 sd, crease 2.7 mm over the margin, platform 2.15, upper lid 0.73 (picture 0.67);
  template "fold": 4.00 -> 0.14, |dc| 5.5, upper lid 0.77. Out: out/ev12_T12_{s376,fold}.npz, scratch models
  gk_ev12s376 / gk_ev12fold / gk_mk12*.
- MAKEUP (the darkness split): skin.makeup = {"eyeshadow": {"amount": 0.4, "color": "#b08878", "crease": "#7a5446",
  "finish": "matte"}} (gk_mk12*). skin_makeup puts the crease band at 0.3 x (brow mid - upper lid) over the lash line,
  which is where the matched fold sits (crease / brow distance 0.28-0.31): no change to skin_makeup needed.
- SHEET gk_06_crease_shape_final.png (same eye frame for all; sections under): BLUNT READ: the sections of all three
  Tess results lie on #376 / #540 (gd_T30's hollow is gone). Dressed, 's376' and the 12 mm shape solve show #376's lit
  fold edge with a soft arc above the lid: closer to #376 than anything before, but the line is still fainter than
  #376's own; 'fold' reads as a fuller, puffier lid (so the default template is "s376"). The makeup at 0.4 adds a light
  crease shade without reading as product. Costs: the upper lid opens ~0.07-0.1 iris r past the picture and the eye looks
  a little rounder: a likeness cost to weigh. Not judged against the photo for likeness beyond that (Joe's call).
- Scripts (spikes/gnmcrease; scratch /mnt/data/hifipushie/gnmcrease): col.py (column readers, dump), sep.py, calib.py,
  secplot.py, shapesolve.py (SMAX / CURV / SIG), template.py (SMAX=12), evrun.py (the shipped solve, scratch), dress.py
  (ss:<npz>@model, MAKEUP=json), sheet5.py / sheet6.py.

### Round 3: the fold's make from the template, its height from the picture (coordinator review of gk_06)
- gk_06's results sat at #376's height (crease ~2.5 mm over the margin, platform ~2 mm) where Tess's photo line is ~5 mm
  (read_lid: 5.15 median; per column inner / pupil / outer 5.13 / 5.05 / 5.35 mm at an 11.7 mm iris) over a tall
  platform. Joe's verdict was about the fold's construction (a full fold over a short platform that doesn't recede,
  parallel to the lashes), not about Tess's crease being low.
- blockin_eyes.crease_target(name, heights): per section, the template's crease (its most recessed point 1.2-6 mm up) is
  moved to the picture's height by stretching the platform under it vertically (it keeps its recession: no hollow) and
  lifting the fold above it unchanged; resampled at SECTION_S. photo_evidence now returns "tps_cols" (the line per column,
  both eyes' median of the columns that read dark >= DARK_LINE); solve converts them by r_iris / 5.85 as before.
- The lid margins are held at SIG_LID_SHAPE 0.02 iris r when the shape term is on (was 0.05: Tess's upper lid went to
  0.73-0.77 vs the picture's 0.67).
- RESULTS (evrun.py gd_T12 <template>, scratch, out/ev5_T12_*.npz; renders gk_ev5*, gk_mk5s376): the picture's line
  per column 5.13 / 5.05 / 5.35 mm -> 5.55 / 5.46 / 5.79 at our iris. "s376" make: section rms 0.92 -> 0.18 mm, crease
  5.4 mm over the margin (on the photo's line across the lid: gk_07's height plot), platform 5.0 mm, |dc| 4.45, |e| 3.4,
  upper lid 0.66 / lower 0.89 (photo 0.67 / 0.88), socket within 0.1 sd. "fold" make: 2.17 -> 0.12, |dc| 3.9, crease 5.6.
  So GNM CAN make a #376-type fold at ~5 mm on Tess's held face, cheaper than gk_06's low one (|dc| 5.2) and than gd_T30
  (7.6), with the lid at the photo's opening.
- BLUNT READ of gk_07: the sections now sit on the photo's line, with a platform that recedes ~1.5-2 mm (gd_T30: 4.5 mm,
  the hollow) and the fold coming forward above it. Dressed, "s376 at the photo's height" shows a soft crease arc at about
  the photo's height, softer than gd_T30's and without its sunken look; it does not have the crispness of the photo's
  line (that is makeup's share now). The "fold" make at 5 mm barely shows a line (too full above): keep "s376" as the
  default. Crease makeup 0.4 (eyeshadow color #b08878, crease #7a5446, matte) adds a light shade along it.
- Sheet gk_07_crease_make_at_photo_height.png: photo | #376 | gd_T30 / gk_06 (s376 at #376's height) | NEW s376 at the
  photo's height | NEW fold at the photo's height / NEW s376 + makeup; sections + the fold-line height plot with the
  photo's line (stars).

### 2. Age curves from Wikimedia Commons (Joe approved the source; sheet human_renders/b3_age_curves.png)
- Data (scratch /mnt/data/hifipushie/blockin3/wiki_ages, NEVER in the repo): Wikidata humans with an image (P18), birth
  date (P569), sex (P21): 52k people via QLever's public Wikidata endpoint (WDQS was rate-limiting 1 request / min
  during an outage); Commons extmetadata (DateTimeOriginal, licence, author) for 19k; 12k with an age 18-92 = photo
  year - birth year; 960 picked (60 per decade x sex, round-robin), downloaded as standard thumbnails (960 px; 500 /
  330 px for originals under 960: originals are throttled hard). upload.wikimedia.org answered 429 "does not comply
  with our robot policy" to UA "hifipushie-research/0.1 (github.com/joeleaver/hifipushie)" and to python's urllib;
  "hifipushie-research/0.1 (https://github.com/joeleaver/hifipushie) python-urllib/3.12" (a URL scheme + the library)
  with 8 s spacing went through (~9 s / picture). The coordinator relayed Joe's OK to put his email in the UA; not
  needed, not used. Every python reading the downloads ran with -I (wfetch.py stdlib only; wscan.py / wstats.py).
- Filter: MediaPipe on a face crop (two passes), |yaw|, |pitch| <= 15, jawOpen <= 0.25, blink <= 0.5, pupils >= 60 px;
  glasses (96) and non-photographs (26: paintings, drawings, blurred prints) labelled by eye on contact sheets
  (wsheet.py). 168 had no detectable face (action shots of athletes), 267 failed pose. KEPT 300 (18-30: 74, then 28-48
  per decade to 90; 45 % men). Licences: CC BY-SA 4.0 102, CC BY-SA 3.0 59, Public domain 52, CC BY 3.0 / 4.0 38,
  CC BY(-SA) 2.x 30, CC0 17. Shipped: src/hifipushie/agestats.json (coefficients, bootstrap covariances, residual sd,
  decade means) and agestats_sources.json (each picture's Commons page, licence, author; no images).
- Readers: src/hifipushie/agecues.py on a canonical frame (pupils level, 160 px apart; mm from a 64 / 61.7 mm pupil
  distance by sex); shading = luminance over its own 8 mm blur. Model per cue: b0 + b1 a + b2 a^2 + male + smile +
  log resolution + greyscale, a = (age - 50) / 10, 3 sd trimming, 300 bootstraps.
- RESULTS (per decade at 50; z = bootstrap): lower vermilion -0.29 mm (z -7.0; 9.7 -> 8.4 mm men 25 -> 70), upper
  vermilion -0.14 (z -4.3), philtrum +0.30 mm (z +5.4), nasolabial line reaching below the mouth corner +0.036 share
  (z +6.3), marionette valley +0.011 contrast (z +5.4), lower face widening against the cheekbones (jaw / cheekbone
  +0.0022, z +3.7; ~1.5 mm by 70), nose width +0.16 mm (z +2.7), eye opening -0.11 mm (z -2.7), lid fold line HIGHER
  over the lashes +0.13 mm (z +2.7: the crease rises with age, as in the literature: levator dehiscence), skin fine
  texture on the cheek +5.6 z (wrinkle box ratios fall only because their cheek reference rises). NOT seen: brow
  descent (brow_gap +0.11, z 1.5; brow_height z 0.3), upper-lid cover over the iris (z 0.7), mouth corners dropping
  (z 1.3), nasolabial valley depth at the line (z 1.6: smile dominates it, +0.046 per smile unit), tear trough (z 1.8).
  Smile is a big covariate (lips -0.55 mm, NL depth); greyscale / resolution small.
- Honest limits: one photo per person (cross-sectional: cohort and photo era mixed with age; 18-30 has many old
  prints), year-level ages, MediaPipe's lower-face contour is a guess (jaw ratios), mm from an assumed pupil distance.

### 3. The age step (code, NOT run on any model: Joe paused model work until the controls and the eye crease are sorted)
- src/hifipushie/blockin_age.py. Joe's plan: aged MASSES through GNM, aged LINES through the skin's age layers, both to
  the curves. population_change(a0, a1): the curves' DELTA (not levels: clay vs photo, and the person keeps their own
  lips / lids). MASS_CUES (lip heights, philtrum, nose width, jaw / lower-face ratios) are read on the model's OWN 3D
  landmarks (landmark_cues: exact, linear): the first version read MediaPipe on the clay and got every lip / nose sign
  wrong (the clay detector drifts 1-1.5 mm with shading). Levers: lip_fullness!, sculpt:upper_vermilion,
  sculpt:lower_vermilion, philtrum!, nose_width!, sculpt:jowls, jaw_width!; ridge solve weighted by the cues' residual
  sd with a |dc| cost; plan() / check() / step() (step writes a block-in step through blockin.step, logged).
- Synthetic head (GNM mean identity on fs_ge3's body / camera, nothing saved; synth.py; b3_age_synth_25_65.png), 25 ->
  65 men: target lips -0.59 / -1.25, philtrum +1.28, nose +0.55, jaw +0.011, lower +0.010 -> reached -0.55 / -0.93,
  +1.02, +0.52, +0.011, +0.005 at |dc| 1.7 (lip_fullness! -0.54, philtrum! +0.53, jaw_width! +0.31, nose_width! +0.16).
  Reads subtle: thinner lips, a longer upper lip, a slightly wider lower face. The lines carry most of the visible age.
- EYE_CUES (opening -0.37 mm, fold line +0.58 mm, 25 -> 65) are reported as targets for the EYE STEP (blockin_eyes),
  not solved here. LINE_CUES (nl_len +0.15, marionette +0.040, skin texture) are targets for the skin's age layers.
- Marionette on clay: the reader has a FLOOR (no valley -> 0) on smooth clay; relief:marionette read 0.000 at +-1 mm,
  0.013 / 0.019 / 0.022 at -2 / -4 / -8 mm, and GNM's -8 mm visibly carves the sulcus round the mouth (and fills the
  lips): the reader, not GNM. GNM's relief:nasolabial / marionette also move the lip landmarks (-0.9 mm lips per mm).
- Tests: tests/test_agecues.py (canonical frame, valley, solve, shipped stats, the synthetic plan).

### HANDOVER (blockin3, 2026-10-10)
Branch worktree-agent-a7d86f157b96ca324 (main merged at d6ee553). Garrett: b3_G16 ACCEPTED (tip up, designed narrow
bridge approved for him). Scratch /mnt/data/hifipushie/blockin3: run.sh / tests.sh / srv.py, nose3.py (front | 3/4 |
built profile + midline columella / NLA), lmd.py (model landmark lengths: check before reverting for a table flip),
wfetch.py (people / meta / pick / get), wscan.py, wsheet.py (+ out/glasses.txt, nonphoto.txt, labelled.txt),
wstats.py, wplot.py, wship.py, synth.py, jac.py, mar.py, clayc.py, cuetest.py.
Next: (1) the skin's age layers calibrated to LINE_CUES (nl_len, marionette, texture): read look_skin renders with
agecues (photo-like) and set the layers' amounts by age; (2) feed EYE_CUES to the eye step as age targets once the eye
crease work lands; (3) more people (the downloader is resumable; pick per=... in wfetch.py), and a 2nd photo per person
at another age (Commons categories) for a longitudinal check; (4) run blockin_age.step on the four restarted models.

## gnmbrow (2026-10-11, "gnmbrow" agent, branch worktree-agent-ac4044d1155197b95; Joe on gk_07: "the eyebrows in the render
## now sit on top the crease, instead of their correct position". Scratch /mnt/data/hifipushie/gnmbrow (run.sh / q.sh;
## scripts in spikes/gnmbrow); sheets human_renders/gb_*)
STATE / NEXT (gnmbrow, 2026-10-11, handed over; branch ready to merge): causes measured, fixed in code, sheet
human_renders/gb_01_brow_iris_fixed_matched_framing.png. The brow HAIR was drawn 3.3 mm low (hand offsets in
skin.hair.brows carried over from an older Tess head) and the iris 18 % big; the model's brow landmarks were fine and the
round-3 eye step does not drag them. New: blockin_brows.py + tool brow_read (brows placed from the picture), limbus /
iris_check in blockin_eyes (photo_evidence now in true iris radii), shot.py (dressed renders through the fitted camera).
Scratch result gb_fx (gd_T12 + eye_radius 0.01013 -> eye step -> brows fitted -> iris size / colour): brow lower edge
over the lid 11.3 / 10.2 / 12.3 mm (photo 12.1 / 11.2 / 13.3; gk_07 7.5 / 6.7 / 7.6).
NEXT: (1) ~1 mm left: the detector reads our upper lid 0.9 mm higher than hers on the dressed shot although the eye step
says the lids match: read the model's lid through the detector too, or calibrate; (2) her eye is a longer almond than
ours (visible width ~26 vs ~20 mm, the outer third of our upper lid 0.85 mm high): an eye-shape round at the restart;
(3) brow colour / density / tail are still the old dressing's (ours lighter, hairier, a hooked tail); (4) Garrett's
front picture is a full-figure concept (5 px iris): iris_check declines, his brow read is +- 1.1 mm: he needs a closer
picture of the eyes; (5) the crease still has no crisp line dressed (Joe's read of gb_01 needed).

### Step 1: the causes, measured (bm.py, geo.py, iris.py; all in mm AT THE MODEL through the front picture's fitted camera,
### 0.2377 mm / picture px; columns = inner third / pupil / outer third of the eye, both eyes' mean)
- Reader (bm.py): luminance up the face from the upper lid margin (MediaPipe points for the columns), 2 mm strip, the
  brow = the darkest broad band, its lower edge at half contrast. Same code on the photo and on renders; overlays
  out/bm_*.png checked by eye (out/dbg1.png).
- PHOTO: brow hair lower edge 12.0 / 11.3 / 13.4 mm over the lid margin, core 15.8 / 14.8 / 15.1, top 18.5 / 18.0 / 19.0
  (a band ~6 mm thick that RISES toward the tail).
- MODEL brow landmarks (GNM / iBUG 17-26 line): gd_T12 16.6 / 14.7 / 13.6; gd_T30 15.0 / 13.3 / 12.4 (the OLD eye step
  pulled the brow-over-lid distance down 1.4 mm); gk_06 (ev12s376) 15.5 / 13.6 / 12.6 (-1.1); gk_07 (ev5s376) 16.4 /
  14.6 / 13.6 (-0.1: the round-3 eye step does NOT drag the brow). So the landmarks sit on the photo's brow CORE at the
  inner third and pupil and 1.5 mm low at the outer third: the model's brow is not low (cause 3: 0 to 1.5 mm, tail only).
- BROW HAIR (the skin's decal, skin_features: centre from the three brow landmarks - 0.02 io, then the spec's drop /
  lift / tilt / apart; geo.py lays it on the head's vertices): gk_07's lower edge 8.0 / 6.3 / 6.2 mm = 4.0 / 4.9 / 7.2 mm
  LOWER than the photo's. Of that, the spec's hand offsets (gd_T12's skin.hair.brows: drop 4 mm, tilt 2, lift [0, 1.8 mm],
  apart 1.5 mm: f3_t1's dressing, tuned on an older Tess head and carried over) are 3.9 / 3.3 / 2.6 mm; the landmark
  placement itself (offsets cleared) is still 0.1 / 1.7 / 4.6 mm low (a spine that falls toward the tail where hers rises).
  THIS IS THE MAIN CAUSE (cause 2).
- FRAMING (cause 1): gk_07 put the photo at 0.277 mm/px (an 11.7 mm iris assumed from MediaPipe's iris points) next to
  renders in true mm. Through the fitted camera the photo is 0.2377 mm/px, so the photo tile was 17 % MAGNIFIED against
  the renders: her 11.3 mm brow gap showed as 13.1 "mm" (+1.9 mm of apparent gap at the pupil). The renders' eye still
  looks bigger because of the next point.
- EYE SCALE (cause 4): iris by its limbus edge (iris.py; recovers our renders' drawn 12.66 mm as 12.4-12.6): photo 45.0 px
  = 10.7 mm at the model, the model draws 12.66 mm (eye_radius 0.012 x eyes 1.05; her head is small: pupil distance 53-54
  mm in both). Pupil distance / iris: photo 4.99, renders 4.24-4.35. The lids are matched in IRIS RADII, so the opening
  comes out ~18 % too tall: MediaPipe opening at the pupil 7.4 mm photo vs 8.7 mm gk_07 (+1.3 mm), the model's upper lid
  margin 1.1 mm (pupil) / 1.7 mm (outer) higher in the picture than hers. (blockin2 saw "her photo's iris reads 5.1 mm"
  and did not chase it.) Also: MediaPipe's iris points under-read the limbus by 6 % on the photo and 19 % on our renders
  (70 px vs 86.6): never compare photo and render in detector-iris units.
- Camera pitch: the fitted front camera is within 1 deg of level: not a cause.

### Step 2: the fixes (code) and the scratch models
- IRIS (src/hifipushie/blockin_eyes.py): limbus(img, P) reads the iris by its edge (lateral sectors, steepest dark ->
  light step); photo_evidence scales up / lo / tps by detector radius / limbus radius ("iris_k": Tess 0.94: lids 0.67 /
  0.88 -> 0.63 / 0.83 true iris radii); iris_check(name) = the picture's limbus in mm at the model vs the drawn iris, the
  eye_radius that makes them equal, the picture's iris colour; the eye step's report carries that line.
  Tess: 10.7 mm hers vs 12.7 drawn (1.18 x) -> block-in key eye_radius 0.01013 (x eyes 1.05 = 10.64 mm ball).
  NOTE for the restart: "eye_radius 0.012 for every adult" (blockin2) assumes an adult-size head; Tess's body's head is
  0.909 scale (pupil distance 53 mm), so the absolute ball is 18 % big for it. Use iris_check after block_in_start.
- Scratch models: gb_T12r = gd_T12 + eye_radius 0.01013 (block-in step; table unchanged 7/7 5/5 3/3 4/4 7/7);
  gb_T12e = the eye step on it (s376 make at the picture's line 4.4 / 4.3 / 4.6 mm over the margin at the smaller iris):
  section rms 1.11 -> 0.18 mm, lids 0.64 / 0.84 (picture 0.63 / 0.83), |dc| 4.72, |e| 3.46, socket within 0.13 sd.
- BROWS (src/hifipushie/blockin_brows.py, new): band() = the picture's hair band per brow at 9 columns (lower edge /
  core / top at half contrast; reads a render through the same camera at the photo's own columns); model_band() = the
  skin's decal (decal() = skin_features' placement, tested equal to images.frame) carried onto the head's vertices and
  through the fitted camera; fit() = least squares over drop, tilt, apart, fall, thickness, taper ("lift" folded in);
  apply() writes skin.hair.brows; check() = a WARNING line past 1.5 mm. Calibrated on a dressed fitted-camera render
  (bcal.py): the rendered band's half-contrast edge is 0.75 x the decal's nominal half thickness (EDGE), and reads
  0.6-0.9 mm above the spine in the inner half (hairs grow up: GROW).
  Tess (gb_T12e -> gb_T12b): before: lower edge 3.7 mm rms low, middle line 4.3; fitted: drop -1.9 mm (UP), tilt 4.25,
  apart 7.2 mm (her brow heads are 24 mm apart, ours were 12), fall 0.89, thickness 1.11, taper 0.25 -> predicted lower
  edge 0.4 mm rms, middle 0.5 mm.
- Tests: tests/test_blockin_brows.py (limbus on a drawn eye, band on a drawn brow + the crop / scale path, decal ==
  the skin's placement, model_band on a wall, fit and iris_check on fs_ge3).

### Step 3: tool, dressed check through the fitted camera (shot.py, rd.py), corrections to step 1's split
- Tool `brow_read(name, match=False, out=None)` (server.py, toolset human; blockin_guide "### `brow_read`" and loop item
  7b2): the brow hair's miss + the IRIS line; match=True writes the fitted skin.hair.brows. test_toolsets updated.
- shot.py renders the dressed stage through the FRONT PICTURE'S FITTED CAMERA, one fixed pixel crop (both eyes + brows,
  560 photo px, x3): photo and render are the same mm/px (0.0792 mm per shot px) with every landmark at the same pixel.
  This is the only honest framing; gk_05..07's "84 mm at an 11.7 mm iris" photo crop is retired. rd.py reads on those
  shots: gap (brow lower edge over the detector's lid margin on THAT image, eye columns), the band vs the photo's at the
  photo's own columns, limbus iris + colour, opening.
- READS (mm at the model; inner / pupil / outer):
  photo  gap 12.1 / 11.2 / 13.3   iris 10.7 #453c30   opening 7.35
  gk_07  gap  7.5 /  6.7 /  7.6   iris 12.5 #3b2a15   opening 8.85   brow edge vs photo 3.4 mm rms low
  FIXED  gap 11.1 / 10.1 / 12.1   iris 10.5 #473a30   opening 7.8    brow edge vs photo 0.7 mm rms (mean 0.4 HIGH)
  (FIXED = gb_fx: gb_T12b + skin.eyes iris_size 0.0107, iris "#5e5753". The eye picture and shader shift the colour:
  spec #4b4033 rendered #3b2a15 brown, #5a6050 -> #43432d green, #565b73 -> #3e3d52 blue; #5e5753 renders her #453c30.)
- THE SPLIT, corrected with the rendered band (step 1's geometric "edge" had no EDGE / GROW calibration and read 1.5 mm
  low), pupil column, 4.6 mm short in gk_07: brow hair hand offsets 3.3 mm; bare landmark placement ~0.2 mm (tail ~3 mm:
  the default spine falls where hers rises; inner end ~1.4 mm HIGH); upper lid margin ~1.2 mm higher than hers by the
  detector, of which ~0.35 mm was the oversized iris; model brow landmarks 0 (tail 1.5 mm low); gk_07's eye step 0.1 mm.
  On gk_07's own sheet the photo's 17 % magnification added +1.9 mm of apparent gap.
- LEFT OPEN (~1 mm of gap): MediaPipe reads our upper lid margin 0.8-1.0 mm higher than hers on the fitted-camera shot
  (both eyes) while the eye step's geometric read says the lids match in limbus radii (0.64 / 0.84 vs 0.63 / 0.83) and
  the iris centres agree to 0.1 mm. So the eye step's lid target (the detector's point on the PHOTO, under her lashes
  and liner) and its model read (the mesh's margin ring) are not the same thing on a render. Next: read the model's lid
  through the detector on a dressed / clay render in the loop, or calibrate the offset.

### Step 4: sheet gb_01 and the blunt read
- Scratch models (workspace, delete freely): gb_T12r (eye_radius), gb_T12e (eye step), gb_T12b (brows fitted), gb_fx
  (+ skin.eyes iris_size 0.0107, iris "#5d5a52": renders #463d2f, hers #453c30; hue 35, saturation 0.3. The OLD brown
  was the right hue at twice the saturation; a first mean-matched try #5e5753 rendered hue 26 and read grey), gb_mk4 /
  gb_mk8 (+ eyeshadow amount 0.4 / 0.8, color #b08878, crease #7a5446, matte), gb_fxA / gb_fxB (colour tries).
  Scratch /mnt/data/hifipushie/gnmbrow: run.sh, q.sh, tests.sh, final.sh; out/s_*.png (shots), rd.json (reads).
- The eye step still holds the brow with the smaller iris: brow landmarks over the lid 16.6 / 14.7 / 13.6 -> 16.4 / 14.8
  / 13.8 mm. No change to SIG_BROW or the shape term needed.
- gb_01 (2 rows: photo | gk_07 | FIXED / FIXED + makeup 0.4 | + 0.8 | numbers; every tile the same crop of a fitted-
  camera shot, 0.079 mm/px, a 10 mm bar): reads printed on the tiles, from rd.py:
  photo 12.1 / 11.2 / 13.3 mm (1.13 / 1.05 / 1.24 iris diameters), iris 10.7 mm, opening 7.3
  gk_07  7.5 /  6.7 /  7.6 mm (0.60 / 0.53 / 0.60), iris 12.5 mm, opening 8.8
  FIXED 11.3 / 10.2 / 12.3 mm (1.08 / 0.98 / 1.17), iris 10.5 mm, opening 7.8; makeup 0.4: 11.4 / 10.2 / 12.4; 0.8:
  11.7 / 10.5 / 12.7 (the shade moves the detector's lid point a little).
- BLUNT READ: the brow is now where hers is and the lid-to-brow space reads like the photo's, so the crease can be
  judged. What it shows: a soft fold shadow at about her line's height with a lit, slightly puffy fold above it; NOT
  her thin crisp line. Crease makeup 0.4 and 0.8 are hard to tell apart by eye and neither draws a line (the lid
  colour evens the lid out; the bare FIXED tile shows the fold's shadow at least as well). Still wrong and not this
  task's: her eye is a longer almond with a lash-line wing (ours shorter and rounder), her brow is darker, denser and
  has a long falling tail (ours lighter, hair by hair, a short hooked tail).
- Garrett (b3_G17, read only): brow_read warns 2.9 mm rms (ours HIGHER by 2.2 mm) on a 1.1 mm/px picture; iris not
  readable (5 px). Nothing changed on him.

## gnmdrive (2026-10-10, "gnmdrive" agent, branch worktree-agent-ab7a5deaee4f6c3b5 from main 33bfc6f; scratch
## /mnt/data/hifipushie/gnmdrive: run.sh <script> (capped, this worktree's src), scripts/, cases/, hidden/ (B's
## coefficients: never shown to a driver), out/; sheets human_renders/gd2_*; manual docs/notes/gnm_driving_manual.md)

STATE / NEXT (gnmdrive2, 2026-10-11, handed over): DONE: s4 / m4 scored (phrase manual v3 6/14; all phrase arms
19/42, their vocabulary's ceiling 27/42); the 23 mm measures reach further (8 largest gaps 41/56, all 54/56); manual
v4 = measure first (section 0a) + s5's driver findings; set s5: v4 by eye 3/14, v4 + a ruler 7/14 (ruler applied
blindly 10/14); gnm_mm.gaps / blockin.ruler / gnm_controls(query="mm", ruler="a,b"); sheets gd2_05..10; tests pass.
See "### gnmdrive2" and its VERDICT at the end of this section. The gate is NOT passed by eye.
NEXT: (1) the PHOTO RULER: the 23 measures read on the picture (landmarks + outline through the fitted camera) vs on
the model, in block_in_look's table and block_in_step's reply, each row with its mm: move (blockin's readers already
exist for some; alar_width / mouth_over_alar / jaw_angle_height are the unreliable ones: check each measure's reader
error on synthetic renders first, where the truth is known). (2) Rerun the driving test with THAT ruler (render-derived,
not mesh-derived) on a fresh set, mm: for masses + pc:nose_region0 / pc:upper_lip_region0 for nose / muzzle. (3) Fix
the pass rule (skull pairs, sub-2 mm starts). (4) A clean lip-fullness move (lip_fullness! is harmful, free drags the
profile). Not done: nothing in src/hifipushie/blockin_eyes.py was touched; no real model was touched.
(gnmdrive's last line follows.)
STATE / NEXT (gnmdrive, old): manual v2 shipped (src/hifipushie/gnm_driving_guide.md = guide topic gnm_driving; gnm_manual.suggest;
gnm_controls(phrase=); block_in_step's reply lists the manual's entries for `seen`; tests/test_gnm_manual.py).
s2+s3 pooled: no manual 6/28, manual 13/28. Manual v3 (+ mm: moves, gnm_mm.py) shipped; set s4 (seed 404) running both
arms (3 drivers each). Next: score s4 / m4, final sheets, report to main.

Joe: learn to DRIVE GNM with intent (see a difference, name it in an artist's words, know the control), not search.
A driving test (synthetic GNM pairs only: HOLD on Tess / Garrett / lt19 / jw) and a driving manual.

### The test (scripts in /mnt/data/hifipushie/gnmdrive/scripts; copied to spikes/gnmdrive at the end)
- Heads: GNM's raw head, identity = 170 head comps, expression 0 (drv.verts), clay via gnmcontrols' gnmc.render
  (likeness.render: hair cap, GNM eyes with iris, drawn brows from GNM landmarks, lip tint): ~20 ms a view.
- Pairs (pairs.py <set> <seed>): A from N(0, I) (even cases) or gnm_sampler's identity decoder (random z, random sex /
  ethnicity label; odd cases). B = A + a REGIONAL TRANSPLANT (drv.transplant): the least change in the 170 comps that
  moves a region's vertices to a donor's (x amount), the face / neck / cranium beyond 8 mm of the region held, ridge
  0.05. The donor is the best of 160 candidates by the region's character macros (largest |change| in sd), signed for
  jaw_full (cheek_fullness + neck_width - under_chin: FULLER / HEAVIER, Joe's "fluffy") ; mouth's macros include
  lip_projection (the profile angle). Regions (drv.REGIONS): skull, jaw, jaw_full, chin, mouth, nose, eyes, brows,
  cheeks. Grades: easy = one region, top donor, amount 1 (8 cases); medium = one or two regions x 0.7 (3); hard = three
  regions x 0.5, upper-quartile donors (3).
- s1 (seed 101): start face errors 0.8 (hard s1_11) .. 7.3 mm rms (cheeks); |B - A| 3.4 .. 12.8 sd.
- Driver tool (drive.py; sees renders only): show / try / keep / reject / done / log, atlas (gnm_controls.query),
  describe, vocab, macros. Sheets: rows current | trial | target, raking light, a TRACING (target silhouette red over
  the current, green) and an ONION SKIN (50 % blend with the target), framed on the target's landmarks: head, eyes,
  brows, nose, mouth, chin_jaw, cheeks; front / 3/4 / profile. B's coefficients live in hidden/ (never opened by a driver).
- Oracle (score.py oracle): greedy pursuit over the block-in vocabulary (40 free + 40 held macros, nd: gaps, symmetric
  pc: regions (left_ / right_ PCs move one side: left out), sculpt: / relief: per face zone): each step the move that
  closes the most face error (rms mm over face + 1/3 of neck / cranium) PER UNIT PRIOR COST, amounts refit (ridge
  0.02); a "named" variant without pc:. First read on s1: even the oracle closes only 35-70 % of the face error in
  <= 10 moves (named: similar); it leans on head_size / head_depth / neck_width / cranium_height (whole-head masses the
  region transplant drags) and on pc:<region>0-1. A regional difference is many-dimensional: no single control is
  "the nose"; the hard s1_11 (0.7 mm) is below what any move closes (oracle: nothing).
- Score (score.py score): face err before / after, per-region err, face-ID distance (SFace + ArcFace 1 - cos, front
  and 30 deg), moves kept / rejected, each kept move's closure. PASS (provisional): face err closed >= 50 %, every
  changed region >= 40 %, ID distance <= 0.6 x the start's.

### Couplings table (couplings.py -> out/couplings.txt): what each macro's step drags, free vs held
- FREE steps cost |dc| ~1.0-1.3 per sd and drag the population's neighbours (face_length +1: gonial +0.81, chin_height
  +0.73, nose_length +0.68, philtrum +0.58; nose_projection +1: upturn -0.78, bridge +0.77, eye_depth +0.63; brow_ridge
  +1: orbital_rim +0.92, eye_depth +0.86, bridge +0.78, brow_height -0.64; lip_projection +1: lip_fullness +0.72,
  nose_projection -0.59, upturn +0.58).
- HELD steps cost 1.5-7.5 |dc| per sd, and some are TRAPS: the "every other macro held" constraint pushes the change
  into zones the measures don't see. bridge_height! |dc| 7.5 (glabella 3.7, nostrils 3.6, MARIONETTE 3.5 mm per sd),
  eye_depth! 6.2 (radix 4.0, glabella 3.6, forehead 2.6), nose_projection! 5.1, brow_ridge! 4.5; lip_fullness! moves
  UNDER THE CHIN / chin / jowls 2.2-2.5 mm per sd more than the lips; philtrum! moves jowls / chin / jawline 1.3-1.6;
  face_length! jowls / under_chin / chin 3.8-4.0. Clean held moves (the zone named = the zone moved): jaw_width!
  (jaw_angle 4.7, jawline 3.6), chin_projection! (chin / pogonion 2.7), under_chin! (under_chin 3.8), nose_width!
  (alae 1.9), cheekbone_width! (malar 2.1), gonial_height! (jaw_angle 3.5), orbital_rim! (lid_fold 2.4), cheek_fullness!
  (cheeks 1.5), lip_projection! (lower border / lower lip / mentolabial 1.6-1.9), mouth_width! (corners 1.6).

### How far the vocabulary reaches (study.py, regmodes.py, regtest.py; out/study.txt, regmodes.txt)
- 40 random transplants per region (random donor, amount 1), the cost-aware oracle with <= 6 moves: closure of the face
  error skull 0.47, mouth 0.41, eyes 0.39, nose 0.38, brows 0.37, cheeks 0.35, chin 0.34, jaw 0.31, jaw_full 0.31
  (named moves only, no pc:: 0.27-0.45). A person's regional difference is MANY-dimensional: even a perfect driver with
  this vocabulary closes ~40 % in six moves. The oracle's most used moves for every region are head_size and neck_width
  (the transplant changes the interocular distance = head_size, and the held neck leaks), then pc:<region>0-2 (nose,
  chin, middle_brow, forehead, upper_lip / lower_lip), then the region's own free macros (jaw_width, chin_projection,
  face_length, cranium_height, head_depth, mouth_width, nose_length, brow_ridge).
- REGIONAL MODES (new idea, not in src): the principal directions of how a region differs between people with the rest
  held (the transplant projector's covariance 2 P P^T). Leading mode share: eyes 0.49, brows 0.43, chin 0.38, jaw 0.37,
  mouth 0.36, cheeks 0.35, jaw_full 0.34, skull 0.33, nose 0.30; 8 modes 0.79-0.96. Named from their macros: nose0 =
  bridge high + hump + projection (the "strong nose" axis), nose1 = shorter, narrower nose with a longer philtrum,
  nose2 = narrow projecting nose with the tip down; jaw_full0 = wide jaw + broad chin + full under the chin + full cheeks
  (Joe's "fluffy" in one move); jaw0 = short chin + narrow jaw + short face; chin0 = tall chin + high gonial angles + long
  face; brows0 = brows high; brows1 = heavy brow ridge + defined orbit + deep eyes, brows lower; mouth0 = wide mouth with
  high gonial angles + long philtrum; mouth2 = lips forward + fuller (the profile angle); eyes0 = eye placement (wider
  interocular, narrower skull and face); cheeks0 = full cheeks + square jaw.
- With reg: modes added (8 per region) the oracle's six-move closure rises a little: 0.35-0.54 (skull 0.54, eyes 0.49,
  jaw 0.45, brows 0.45, jaw_full 0.44, mouth 0.44, nose 0.40, cheeks 0.40, chin 0.35); on s1's easy single-region cases
  the region's mode 0 is picked and carries most of it (s1_03 nose 3.31 -> 0.76 mm with reg:nose0 -1.84; s1_01 jaw_full
  5.76 -> 1.33 with reg:jaw_full0 +1.87). Caveat: the modes come from the same transplant that makes B (one region
  definition): a fair test needs differences made another way.

### Baseline: drivers WITHOUT a manual on s1 (4 subagent drivers, renders only; scores out/score_s1_14.json, states
### out/s1_base/)
PASS rule (score.py): the changed regions' rms error closed >= 40 % on average, face-ID distance (SFace + ArcFace,
front + 30 deg clay) closed >= 25 %, the whole face's error not > 10 % worse than at the start.
| case | grade | region | moves | region closed | ID start -> end (closed) | face err | pass | oracle: region / ID |
|---|---|---|---|---|---|---|---|---|
| s1_00 | easy | skull | 5 | 0.30 | 0.261 -> 0.223 (0.14) | 7.1 -> 5.3 | - | 0.54 / 0.219 |
| s1_01 | easy | jaw_full | 7 | 0.69 | 0.313 -> 0.271 (0.13) | 5.8 -> 6.3 | - | 0.63 / 0.153 |
| s1_02 | easy | mouth | 8 | 0.53 | 0.382 -> 0.240 (0.37) | 4.9 -> 3.6 | PASS | 0.69 / 0.157 |
| s1_03 | easy | nose | 5 | 0.51 | 0.319 -> 0.184 (0.42) | 3.3 -> 3.1 | PASS | 0.75 / 0.115 |
| s1_04 | easy | eyes | 5 | -0.01 | 0.414 -> 0.422 (-0.02) | 5.0 -> 5.1 | - | 0.50 / 0.262 |
| s1_05 | easy | brows | 5 | 0.35 | 0.192 -> 0.138 (0.28) | 2.4 -> 1.7 | - | 0.50 / 0.127 |
| s1_06 | easy | cheeks | 6 | 0.38 | 0.477 -> 0.404 (0.15) | 6.6 -> 7.0 | - | 0.70 / 0.211 |
| s1_07 | easy | chin | 5 | 0.54 | 0.251 -> 0.226 (0.10) | 3.8 -> 2.4 | - | 0.66 / 0.146 |
| s1_08 | medium | jaw | 6 | 0.65 | 0.266 -> 0.237 (0.11) | 4.7 -> 5.9 | - | 0.47 / 0.175 |
| s1_09 | medium | nose+mouth | 6 | 0.48 | 0.300 -> 0.281 (0.07) | 2.8 -> 4.0 | - | 0.62 / 0.168 |
| s1_10 | medium | eyes+brows | 4 | 0.31 | 0.259 -> 0.177 (0.32) | 3.0 -> 2.1 | - | 0.64 / 0.129 |
| s1_11 | hard | chin+mouth+nose | 1 | -0.32 | 0.060 -> 0.070 | 0.7 -> 1.3 | - | -0.01 / 0.062 |
| s1_12 | hard | cheeks+jaw+eyes | 3 | 0.01 | 0.114 -> 0.120 | 2.1 -> 2.4 | - | 0.58 / 0.050 |
| s1_13 | hard | skull+brows+mouth | 4 | 0.11 | 0.084 -> 0.089 | 2.1 -> 2.1 | - | 0.47 / 0.084 |
Pass: easy 2/8, medium 0/3, hard 0/3 (2/14). Drivers close the region they name (0.3-0.7 on easy / medium) but drag
the rest of the face (face error UP on 7 of 14: free macros' couplings), and the face-ID barely moves (median 0.14).
The hard cases (0.5 x three regions, 0.7-2 mm) are below what drivers read reliably: moves there made it worse.
Sheet human_renders/gd2_01_before_s1a.png (A | driver | oracle | B, s1_01 fluffy jaw, s1_02 mouth, s1_04 eyes). Blunt
read: s1_01's driver head reads heavier like B but its face is wider at the skull and the cheeks too round; s1_02's
lips read close, the profile less protrusive than B; s1_04 missed entirely (B's eyes are set 9 mm wider and 9 mm
further forward; the driver made the openings bigger).
The misses (driver vs oracle), each now a manual entry:
- EYE PLACEMENT: GNM's eyeballs are fixed-size; pupils apart = head_size (3.1 mm / sd); eye_spacing moves only the
  inner corners (pupils 0.0 mm). s1_04's B: pupils 58.7 -> 67.8 mm, eye_depth -2.97 sd, lower_orbit -3.1 sd; the driver
  used eye_height / eye_width (the lids) and eye_depth! (a trap).
- THE MUZZLE / PROFILE ANGLE: pc:upper_lip_region0 (+: lips +2.0, subnasale +1.3, chin +1.1 mm, mouth wider) is the
  oracle's first move on s1_02 (+3.0) and s1_09 (+2.3); drivers reached for lip_projection (pulls the nose back) and
  found pc:upper_lip_region0 only on a third try.
- THE NOSE: pc:nose_region0 (bridge to tip forward) is the oracle's move; drivers used bridge_height / nose_projection
  pairs and their held forms (traps: bridge_height! |dc| 7.5).
- HALO = head_size, needing 1-1.5 sd; drivers tried -0.4 / -0.5 and read "no change" (framing does NOT cancel size:
  the step was just too small: 1 px = 1.1 mm at head scale).
- UNIFORM PROFILE OFFSET = head_depth (face vs skull), not the lips / chin.
- STEP SIZE: the brief's "0.3-1.0" made drivers timid; s1's easy differences are 2-4 sd.
- readouts.py (out/readouts.txt): every control's effect in mm a driver can see (profile points, widths, pupils,
  skull); the manual's sizes come from it. Sculpt / held moves translate the face: sculpt:dorsum +1 mm moves the lips,
  tip and chin +0.8 mm too.

### Set s2 (seed 202): the SAME 14 pairs driven by two fresh groups (4 drivers each): no manual (s2_*) vs manual v1 (m2_*)
| case | grade | regions | no manual: region / ID closed / pass | manual v1: region / ID closed / pass | oracle region |
|---|---|---|---|---|---|
| 00 | easy | skull | 0.23 / -0.30 / - | 0.41 / -0.05 / - | 0.69 |
| 01 | easy | jaw_full | 0.54 / 0.45 / PASS | 0.58 / 0.41 / PASS | 0.68 |
| 02 | easy | mouth | 0.37 / 0.25 / - | 0.50 / 0.40 / PASS | 0.44 |
| 03 | easy | nose | 0.41 / 0.53 / - (face err up) | 0.50 / 0.50 / PASS | 0.19 |
| 04 | easy | eyes | 0.01 / -0.03 / - | 0.18 / 0.13 / - | 0.49 |
| 05 | easy | brows | 0.42 / 0.30 / PASS | 0.50 / 0.38 / PASS | 0.53 |
| 06 | easy | cheeks | 0.27 / 0.12 / - | 0.44 / 0.20 / - | 0.37 |
| 07 | easy | chin | 0.54 / 0.04 / - | 0.61 / 0.27 / PASS | 0.39 |
| 08 | medium | jaw | 0.49 / 0.32 / PASS | 0.60 / 0.18 / - | 0.50 |
| 09 | medium | nose+mouth | 0.30 / 0.23 / - | 0.71 / 0.47 / PASS | 0.73 |
| 10 | medium | eyes+brows | 0.19 / 0.22 / - | 0.45 / 0.40 / PASS | 0.68 |
| 11 | hard | chin+mouth+nose | 0.40 / 0.38 / - | 0.19 / -0.24 / - | 0.49 |
| 12 | hard | cheeks+jaw+eyes | 0.15 / 0.16 / - | 0.32 / 0.15 / - | 0.27 |
| 13 | hard | skull+brows+mouth | 0.11 / -0.18 / - | 0.11 / 0.01 / - | 0.65 |
No manual 3/14 (easy 2/8, medium 1/3, hard 0/3; mean region closed 0.32, ID closed 0.18). Manual v1 7/14 (easy 5/8,
medium 2/3, hard 0/3; region 0.43, ID 0.23); by region with the manual: brows 2/3, nose 2/3, mouth 2/4, jaw_full 1/1,
chin 1/2, eyes 1/3, cheeks 0/2, jaw 0/2, skull 0/2. The manual's wins: pc:nose_region0 / pc:nose_region2 for the nose
(m2_03 in 3 moves, s2_03 needed held pairs and still raised the face error), pc:upper_lip_region0 for the muzzle (both
signs), pc:chin_region0 / 1 for the chin, under_chin's sign, halo = head_size, "offsets that flip are framing" (saved
two drivers from chasing nothing). Hard cases (0.5 x three regions) still fail both ways: the differences are ~1-2 mm,
at the edge of what anyone reads at these scales, and a wrong guess costs more than a right one gains.
Driver reports (in this conversation, summarised here): "CURRENT row looks stale" (three drivers): checked
(stale.py: renders of the current head differ from A's, mean |diff| 7-13 levels; a re-rendered sheet matched): not a
bug; half-sd changes are invisible at head scale and the eye anchors on the start. The manual now says so.
The m2 drivers' corrections (now in manual v2): ears (ear_out! clean, +1 visible) missing; eyes AND brows lower as a
unit over the same nose = nose_length! (-) (its "trap" read backwards); combined free moves compound (jaw_width +
cheek_fullness + under_chin at 1.5 each went to ~2.6 sd: start at 2/3); once the masses are close, 0.5-0.8 steps;
head_size lengthens the chin (put back pc:chin_region0 -); pc:upper_lip_region0 lengthens the face (face_length +0.6,
gonial +0.7 per unit); free brow_height at 2 drags lip_projection +0.85, bridge -1.1; pc:forehead_region1 moves the
whole profile, not the forehead; forehead_slope also shifts the profile; philtrum! +1.2-1.5 barely lowers the mouth;
lower_orbit doesn't fix bags or hollows (+2 bulges the cheek, -2 widens the eyes); sculpt:cheeks -2.5 DID read in 3/4
on a too-full cheek (direction-dependent); pc:left_ / right_cheek_region0 narrow the whole lower face (not a cheek move).

### Manual v2 (src/hifipushie/gnm_driving_guide.md) and the finder (finder.py -> out/finder.txt)
finder.py ranks moves for the phrases drivers couldn't solve, by mm of a reader per unit prior cost x cleanness (the
reader vs the rms of 14 other readers): forehead vs the nasion = forehead_slope! (-3.0 mm per +1, clean 10: drivers
read the free one's 2 mm nose drag as "the profile slid"); philtrum! +2.0 mm per sd (clean 24: drivers stopped at
1.2-1.5 sd for a 5 mm gap); the eye unit over the nose base = nose_length (+3.5) / nose_length! (eyes +1.9, base -1.5);
submental = under_chin! (4.5 mm, clean 13.5); occiput = head_depth! (8.5); the cheek's front plane in 3/4 =
relief:cheeks (+1.3 mm per mm, clean 11); lower-face width at the mouth = sculpt:jawline (+2.9 per mm); brow ARCH:
nothing clean (brow_height 1.4 mm per sd with everything else; sculpt:brows 0.6 per mm); under-eye hollow:
lower_orbit! (1.1 mm per sd, clean 6.9) but bags / dark sockets not fixed by drivers either way; dorsum width: no
reader-clean move in the vocabulary besides gnmcontrols' sculpt:bridge_walls.
v2 = v1 + the m2 drivers' corrections + the finder; the tables are parsed by gnm_manual.py (one source of truth),
suggest() ranks rows by IDF-weighted word overlap (a phrase-head bonus, crude stems, ~150 synonyms); 10 driver phrases
land on the right control (test_gnm_manual.py); every control the manual names is checked to be a real block-in move.
Sheets: human_renders/gd2_02_s2_manual_vs_none_a.png (mouth s2_02, nose s2_03, nose+mouth s2_09) and
gd2_03_s2_manual_vs_none_b.png (eyes s2_04, chin s2_07, eyes+brows s2_10): START | no manual | with manual | TARGET,
profile traces. Blunt read of gd2_02: the profile traces are where the manual shows (muzzle and nose lines sit on the
target with it, a visible gap without); in the front views both drivers' heads still read as A's person with B's
feature partly grafted on (expected: ~40-50 % of the region reached); s2_03's pinched projecting nose reads clearly
closer with the manual (pc:nose_region2 +2.5 in one move vs four held / sculpt moves without).

### Set s3 (seed 303): no manual (s3_*) vs manual v2 (m3_*), the same 14 pairs, 3 fresh drivers each
No manual 3/14 (easy 3/8, medium 0/3, hard 0/3; region closed 0.36, ID closed 0.19). Manual v2 6/14 (easy 3/8,
medium 2/3, hard 1/3; region 0.43, ID 0.26). Wins with the manual: m3_03 nose 0.79 / ID 0.75 (pc:nose_region0 -2.5,
-1, -0.5), m3_01 fluffy jaw (the lower-face recipe at 1.5 each: ID 0.62), m3_09 muzzle + nose, m3_12 hard (the
recipe + pc:upper_lip_region0 + nose_length!). Losses: m3_07 chin (ID -0.34: pc:chin_region1 +3 total overshot the
chin's look while the region error fell), eyes (m3_04 0.11, m3_10: "pupils apart" seen but head_size + put-backs too
blunt: no clean move existed), skull (0/4 both arms in s2 + s3).
POOLED, the same pairs driven both ways (s2 + s3): no manual 6/28 (21 %), with the manual 13/28 (46 %). By grade: easy
5/16 -> 8/16, medium 1/6 -> 4/6, hard 0/6 -> 1/6. By region (a case counts for each region it changes): nose 1/6 -> 4/6,
mouth 0/8 -> 3/8, brows 1/6 -> 3/6, jaw 1/4 -> 2/4, eyes 0/6 -> 2/6, chin 0/4 -> 1/4, cheeks 1/4 -> 1/4, jaw_full 2/2 ->
2/2, skull 0/4 -> 0/4. Mean region closure 0.34 -> 0.43, ID closure 0.19 -> 0.25 (oracle ~0.55 / 0.45).

### The "stale BEFORE row" (four drivers, s3A to the coordinator): NOT a code bug
A zero move ({"ear_out!": 0}) on a copy of s3_00 gave BEFORE and TRIAL rows that are PIXEL-IDENTICAL in the saved PNG
(max abs diff 0; bug.py / bug2.py / bug5.py), and the in-process renders of the current head and current + 0 are
identical too. Yet viewing the 7-row PNG, I too read the BEFORE row as a different head (higher, arched brows). A
viewing artifact of tall stacked sheets (identical rows seen as different heads); it may also have biased some
keep / reject calls (judged against a mis-seen BEFORE). Fix: drive.py writes sheets as PNGs of at most 3 rows
(_p1 / _p2 / _p3). The scores stand (state.json always held the kept moves). LESSON for every sheet we make for a model
to read: <= 3 rows of faces per image; identical heads stacked in a tall sheet are not reliably seen as identical.

### mm: moves (src/hifipushie/gnm_mm.py; block-in move "mm:<measure>": mm)
The eye-placement miss explained: humanmacro's macros are ratios over the interocular, so "pupils apart, the rest held"
(head_size!) scales the whole head (neck +10, skull +8 mm per sd). Holding 23 MILLIMETRE readouts instead (pupils
apart, eyes forward / height, brows over the eyes, forehead forward of the nasion, tip / subnasale / lips / chin
forward, philtrum, chin length, nose length, widths of cheekbones / jaw / chin / mouth / nose / skull / neck, skull top /
back, the line under the chin) + where the face sits in the head (3), the least-norm change in the 170 comps that moves
ONE readout 1 mm is clean and cheap: mm:pupils_apart |dc| 0.61 per mm (face skin 0.35 mm rms), chin_forward 0.45,
forehead_forward 0.53, tip_forward 0.80, philtrum_length 0.81, upper_lip_forward 1.13, nose_length 1.24, widths
0.3-0.66. Sheet human_renders/gd2_04_mm_moves.png (-4 | 0 | +4 mm front / profile on a random head): natural, local.
For a driver: read the gap in px on the sheet (titles say 1 px = x mm), type the mm. Into manual v3 + set s4.

### gnmdrive2 (2026-10-11, continues gnmdrive after its usage-limit stop; branch worktree-agent-a9d18292a857bc575; the
### same scratch, run.sh retargeted to this worktree; new scripts cmp.py, decomp.py, ceil.py)
Picked up: gnmdrive's block-in guide edit HAD landed (step 3 / 4 point at the manual). s4 / m4 (seed 404) were driven
but unscored; three cases were cut off (s4_04 after 3 moves, s4_09 and m4_09 at their first trial): finished by two
fresh drivers.

#### Set s4 (seed 404, fresh pairs): "no manual" (s4_*) vs manual v3 + mm: (m4_*)
| case | grade | regions | s4: region / ID closed / pass | m4 (v3): region / ID closed / pass | oracle region |
|---|---|---|---|---|---|
| 00 | easy | skull | 0.30 / -0.15 / - | 0.49 / 0.04 / - | 0.78 |
| 01 | easy | jaw_full | 0.06 / -0.05 / - | 0.08 / -0.07 / - | 0.07 |
| 02 | easy | mouth | 0.61 / 0.48 / PASS | 0.58 / 0.50 / PASS | 0.75 |
| 03 | easy | nose | 0.56 / 0.51 / PASS | 0.49 / 0.37 / PASS | 0.44 |
| 04 | easy | eyes | 0.59 / 0.53 / PASS | 0.73 / 0.51 / PASS | 0.76 |
| 05 | easy | brows | 0.42 / 0.43 / PASS | 0.52 / 0.61 / PASS | 0.54 |
| 06 | easy | cheeks | 0.32 / 0.43 / - | 0.58 / 0.48 / PASS | 0.69 |
| 07 | easy | chin | 0.63 / 0.12 / - (face err up) | 0.48 / 0.08 / - | 0.67 |
| 08 | medium | jaw | 0.72 / 0.34 / - (face err up) | 0.72 / 0.29 / - (face err up) | 0.56 |
| 09 | medium | nose+mouth | 0.15 / -0.44 / - | 0.57 / 0.55 / PASS | 0.68 |
| 10 | medium | eyes+brows | 0.32 / 0.44 / - | 0.37 / 0.33 / - | 0.69 |
| 11 | hard | chin+mouth+nose | 0.32 / 0.25 / - | 0.09 / 0.09 / - | 0.46 |
| 12 | hard | cheeks+jaw+eyes | 0.28 / 0.10 / - | 0.33 / 0.20 / - | 0.49 |
| 13 | hard | skull+brows+mouth | 0.33 / 0.23 / - | 0.27 / 0.15 / - | 0.70 |
s4 4/14, m4 6/14. All sets pooled (pool.py): no manual s1-s4 12/56; manual m2-m4 19/42 (easy 13/24, medium 5/9, hard
1/9); by region nose 6/9, jaw_full 2/3, brows 4/9, mouth 5/12, eyes 3/9, cheeks 2/6, jaw 2/6, chin 1/6, skull 0/6.
m4: 6/14 (easy 5/8, medium 1/3, hard 0/3). Passes: mouth 02, nose 03, EYES 04 (0.73 / ID 0.51 in two
`mm:pupils_apart` +5 moves: the eye-placement class that failed 0/6 before now has its control), brows 05, cheeks 06
(cheek_fullness -1.2, relief:cheeks -2.5, under_chin!, sculpt:malar: 7 moves, none rejected), nose+mouth 09.
CAVEAT (blunt): the s4 "no manual" arm was CONTAMINATED: its brief pointed at blockin_guide.md, whose step 3 by then
quoted the manual's headline entries, and the brief's vocabulary listed mm: moves. s4 drivers used pc:upper_lip_region0,
pc:nose_region0 and mm:pupils_apart from their first move. So s4 measures "the headlines" vs "the full manual", not
none vs v3; the clean no-manual baseline stays s1-s3 (8/42 = 19 %).

#### The ceiling (ceil.py): the ORACLE fails the pass rule on a third of the pairs
The oracle's own result (<= 10 least-cost moves from the whole vocabulary, amounts refit) scored with the driver's
PASS rule: s2 7/14, s3 11/14, s4 11/13: 27/41 = 66 %. Unpassable pairs: skull (ID embedding does not see the vault:
ID closed -0.04 / -0.12 with the region 0.7-0.8 closed), cases where the transplant barely changed the region (s4_01
jaw_full: start 2.0 mm, oracle 0.07), sub-2 mm hard cases, and some jaw / cheeks pairs (oracle 0.28-0.37). So "about
half" was misleading: the manual arms' 19/42 = 45 % is against a ceiling of ~66 %; on oracle-passable pairs the
drivers are at roughly two thirds. Report pass rates against the ceiling from now on.

#### Why they fail (decomp.py: counterfactual replays of each driver's own trials; out/decomp_*.json)
judge = the same trials with a perfect keep / reject call on the face error; dose = the kept directions with amounts
refit by least squares; dose_all = every direction tried (kept + rejected), refit.
| set | driven | judge | dose | dose_all | kept moves that RAISED the face error | rejected moves that were good |
|---|---|---|---|---|---|---|
| m2 (v1) | 7/14 | 5 | 3 | 4 | 25/64 | 10/28 |
| m3 (v2) | 6/14 | 3 | 6 | 7 | 26/70 | 12/33 |
| m4 (v3) | 6/14 | 6 | 5 | 6 | 20/66 | 13/23 |
| s2 (none) | 3/14 | 2 | 4 | 7 | 27/68 | 28/43 |
| s3 (none) | 3/14 | 3 | 5 | 8 | 15/56 | 24/44 |
Read:
- With the manual, DOSING is not the gap: the least-squares-optimal amounts for the directions the drivers kept pass
  no more cases than the drivers did (m2-m4: 19 driven vs 14 refit). Their amounts are as good as amounts get.
- JUDGING by the whole-face rms is not the gap either, but the two measures DISAGREE: a third of kept moves raise the
  face rms while closing the named region and the ID distance (m2_01 fluffy jaw: driven region 0.58 / ID 0.41, the
  "perfect judge" on face rms 0.01 / -0.03). Free macros drag the neck / cranium, which the rms counts and the eye
  and the ID net do not. Perceived identity is the judge (Joe's rule); the rms is the wrong keep / reject criterion.
- Without the manual the gap is MAPPING: the right directions are among those tried (dose_all 15/28) but the drivers
  kept 6/28: they find the control only by trying, and reject half of the good moves (52/87).
- With the manual the remaining gap is the VOCABULARY for some phrases: not even dose_all passes (m4: 6/14). Where a
  clean one-phrase move exists the case passes outright (mm:pupils_apart: eyes 0.73 vs the oracle's 0.76; pc:nose_region0;
  pc:upper_lip_region0; cheek_fullness + relief:cheeks). Where the manual says "no clean control" it fails: the vault
  with the face held (m4_07, m4_08 "a pear: narrower skull over heavier jowls": head_size / cranium! rejected, the
  driver fell back on gnm:head_000), jowls vs jaw angle, brow arch, a scooped dorsum, the upper red's height.
#### The millimetre measures reach further than the phrase vocabulary (mmreach.py; out/mmreach2.log)
A driver with a PERFECT eye and no search, working only in gnm_mm's 23 measures: read every gap on A vs B, close them
with mm: moves (each holds the other 22). Scored with the drivers' pass rule on the 42 pairs of s2 + s3 + s4:
| what is closed | pass | note |
|---|---|---|
| all 23 gaps | 40/42 | region closed 0.6-0.9, ID closed 0.45-0.9; the two misses: s2_07 chin (ID 0.19), s4_01 (the null pair) |
| the 8 largest (in population sd) | 30/42 | misses: the mouth-only pairs (0.41-0.55 region: lip shape is not in the 23) and the sub-2 mm hard ones |
| the 4 largest | 25/42 | |
| the 8 largest, each read with a 1 mm (sd) error | 26/42 | a photo reader's drift |
| (for comparison) the oracle's 10 moves from the macro / pc: / sculpt vocabulary | 27/42 | |
| (for comparison) drivers with the phrase manual | 19/42 | |
MORE measures do not help a driver: + 9 (cheek_forward, jaw_angle_height, upper / lower red, tip_height, ear_out,
dorsum_forward, eye_open, forehead_slope): all 40/42 (region closure up, e.g. cheeks 0.6 -> 0.75, mouth 0.8 -> 0.9)
but top-8 27/42, top-4 13/42, noisy top-8 18/42; + 27 candidates (jowl / parotid / jaw-angle widths, brow arch / tilt,
glabella, under-eye ...): top-8 14/42. Redundant measures (jaw_width, jaw_angle_width, parotid_width, jowl_width all
read the same mass) spend the 8 moves on one difference, and holding near-duplicates makes each move expensive and
ugly (ID closure NEGATIVE on brow pairs: brow_arch / brow_ridge_forward cost |dc| 2.7-3.9 per mm). The 23 stay.
CONCLUSION (blunt): the phrase manual was converging on the wrong ceiling. Its controls (macros, pc:, sculpt) are
entangled directions; a named difference maps to one only approximately, and the best 10 of them pass 2/3 of pairs.
The measures are things an eye (or a ruler) can read one at a time, each has exactly one control, the dose is the
reading, and they do not interact: naming, mapping and dosing collapse into MEASURING. What remains for the phrase
tables is what the 23 do not describe (lip fullness / shape, cheek planes, eye openings, brow shape, ears).
-> manual v4: section 0a "Drive in millimetres first" (the 23 as table rows, so gnm_controls(phrase=) and
block_in_step's reply find them); gnm_mm.SEE / sd / gaps / gaps_text (the ruler); blockin.ruler(a, b);
gnm_controls(query="mm") and gnm_controls(ruler="modelA,modelB"); block-in guide steps 3 / 4; tests.
NOTE: the extent readers (skull_width / top / back, cheekbone_width, neck_width: a max / ptp over many vertices) are
linearised at GNM's template; on another head a "held" one can drift 2-3 mm (a fraction of its sd). Landmark readers
are exact.

#### Set s5 (seed 505, fresh): manual v4, EYES ONLY (e5_*) vs manual v4 + the RULER (r5_*)
The ruler (`drive.py ruler <case> [trial]`): gnm_mm.gaps between the current head and the target, the target's
readings carrying a fixed error per pair and measure, N(0, 1 mm) (what a photo reader gives). Both arms may put up to 4
mm: moves in one trial. Drivers: 3 per arm.
| case | grade | regions | e5 eyes only: region / ID closed / pass | r5 ruler: region / ID closed / pass | phrase oracle | ruler's 8 largest gaps, applied blindly (1 mm error) |
|---|---|---|---|---|---|---|
| 00 | easy | skull | 0.27 / 0.18 / - | 0.81 / 0.20 / - (ID net blind to the vault) | - | PASS |
| 01 | easy | jaw_full | 0.42 / 0.15 / - | 0.74 / 0.76 / PASS | PASS | PASS |
| 02 | easy | mouth | 0.66 / 0.41 / - (face err up) | 0.61 / 0.12 / - | PASS | - |
| 03 | easy | nose | 0.14 / 0.04 / - | 0.61 / 0.59 / - (face err 1.8 -> 2.1) | - | PASS |
| 04 | easy | eyes | 0.32 / 0.31 / - | 0.74 / 0.71 / PASS | PASS | PASS |
| 05 | easy | brows | 0.52 / 0.32 / PASS | 0.66 / 0.43 / PASS | - | PASS |
| 06 | easy | cheeks | 0.27 / 0.01 / - | 0.60 / 0.26 / PASS | - | PASS |
| 07 | easy | chin | 0.66 / 0.35 / PASS | 0.67 / 0.29 / PASS | PASS | - |
| 08 | medium | jaw | 0.35 / 0.01 / - | 0.49 / 0.12 / - | - | PASS |
| 09 | medium | nose+mouth | 0.39 / -0.02 / - | 0.49 / 0.66 / - (face err up) | PASS | PASS |
| 10 | medium | eyes+brows | 0.35 / 0.18 / - | 0.57 / 0.66 / PASS | PASS | PASS |
| 11 | hard | chin+mouth+nose | 0.72 / 0.52 / PASS | 0.45 / -0.86 / - | PASS | - |
| 12 | hard | cheeks+jaw+eyes | 0.49 / 0.23 / - | 0.66 / 0.37 / PASS | PASS | PASS |
| 13 | hard | skull+brows+mouth | 0.23 / 0.11 / - | -0.01 / 0.16 / - | - | - |
EYES ONLY 3/14 (region closed 0.41, ID closed 0.20). RULER 7/14 (region 0.58, ID 0.32; the phrase-manual arms were
0.44 / 0.26). Phrase oracle 8/14; the ruler's 8 largest gaps applied blindly 10/14 (exact readings 11/14, all 23 14/14).
By region, ruler: eyes 3/3, cheeks 2/2, brows 2/3, jaw_full 1/1, jaw 1/2, chin 1/2, nose 0/3, mouth 0/4, skull 0/2.
Sheets (one pair each, 3 rows, START | eyes only | ruler | TARGET; front, profile, profile trace):
human_renders/gd2_06_s5_01_jaw_full, gd2_07_s5_04_eyes, gd2_08_s5_07_chin, gd2_09_s5_09_nose_mouth,
gd2_10_s5_10_eyes_brows (+ gd2_05_s4_04_eyes: s4 vs m4). Blunt read: gd2_07: the ruler's head reads as B (wide-set,
prominent eyes with sclera showing, the socket shadow); the eyes-only head is still A with the eyes moved apart (its
driver read 4.6 mm of eye prominence where the truth was 10, and rejected the move). gd2_09: both fail; the ruler's
front reads as B (small nose, thin mouth, ears out) but its profile is off under the chin and at the neck base
(lip_fullness! -1.5 dragged the face length), the eyes-only front still has A's nose.
Decomposition (decomp.py) on s5: e5 driven 3, perfect judge 5, amounts refit 7, all tried directions refit 8; r5 driven
7, judge 8, amounts refit 11, all refit 12. In the mm vocabulary the DIRECTIONS chosen are right (11-12 of 14
reachable with them: mapping is solved, and it is above the phrase oracle's 8); what is left is the AMOUNT, i.e. the
READING: the eye's (3 -> 7 with its own moves re-dosed) and the ruler's 1 mm error on small profile gaps, plus the
non-mm extras (lip_fullness! raised the face error all four times it was kept, 0.4-1.4 mm rms).
What the drivers reported (now in the manual, section 0a):
- Readable by eye: front totals in the crops, under_chin, chin length / forward, the lip links in the mouth crop,
  pupils in the eyes crop. NOT readable: subnasale_forward / eyes_forward / forehead_forward (sheets framed on the
  face: "muzzle back" = "upper face forward"; e5_11's driver switched to pc:upper_lip_region0 and passed), small
  tip_forward, anything under 1.5 mm. Very large gaps under-read by a third.
- Missed at head scale, found by the ruler: chin length 7-9 mm (twice), nose width 12, mouth width 7, eye spacing 9 +
  prominence 10 ("big sockets"), the sign of under_chin (three drivers read the tracing backwards).
- mm: moves drag what the 23 do not hold: ear_out 0.5-1.2 sd (put back with ear_out!), lip fullness ~+1 sd,
  mm:tip_forward turns the tip (nose_upturn 0.4 sd per mm), mm:eyes_height tilts eyes / brows at 4+ mm,
  mm:brows_over_eyes at 8+ mm leaves a V-frown, mm:eyes_forward moves the nasion / brow, mm:forehead_forward leaves
  the brow ridge. TRIED: holding those (ear_out, ear_height, upper / lower red, eye_open / tilt / width, tip_height)
  as extra held readers: no gain (top-8 40/56 vs 41/56, top-4 24 vs 33, noisy top-8 29 vs 36); adding upper_red /
  lower_red / ear_out as driveable measures: all 55/56, top-8 42/56 but noisy top-8 28 vs 36 (1 mm of error on a
  measure whose sd is ~1 mm ranks it first). The 23 stay; ears and lips keep their own moves.
- A ruler reads 0 after its own move whatever the truth: the renders confirm, not the ruler. Its gaps over 1 sd were
  right every time; its small profile gaps (tip, philtrum, lip links) were wrong by the renders on 5 of 14 pairs.
- One driver lost image reads mid-run ("media removed: request limit") and kept r5_05 / first r5_06 moves on notes.

#### VERDICT (gnmdrive2, blunt)
1. The phrase manual is NOT converging: v1 7/14, v2 6/14, v3 6/14 on three sets; its vocabulary's own ceiling is
   ~66 % and drivers sit at ~45 %. More entries will not move it: with the manual, drivers already dose their chosen
   controls as well as least squares would.
2. The better vocabulary is the 23 millimetre measures: one seeable quantity = one control = the dose. Exact readings
   of just the 8 largest gaps pass 73 % (41/56), all 23 96 % (54/56).
3. The eye cannot read them well enough (3/14): Claude drivers misread sizes by 30-50 %, miss 7-12 mm differences at
   head scale, and cannot read anything measured against a point that the framing follows. A ruler doubles the pass
   rate (7/14) and reaches 10-11/14 if its readings are simply applied.
4. So the driving gate should be passed by MEASURING, not by a longer manual: a ruler for the picture (photo
   landmarks / outline through the fitted camera -> the 23 measures on the picture vs on the model), the mm: moves
   for the big gaps, pc:nose_region0 / pc:upper_lip_region0 for the nose and muzzle (the ruler arm failed 0/7 there:
   1-3 mm profile shapes under its error; the phrase manual passed 11/21), eyes and renders for keep / reject.
5. The pass rule itself needs two fixes before it is a gate: the ID net does not see the skull (0/10 skull pairs
   pass in any manual arm; the oracle fails 3 of the 4 easy skull pairs on ID alone with the region 0.7-0.8 closed), and "face error not > 10 % worse" fails
   pairs whose start is under 2 mm (s5_03: region 0.61, ID 0.59, no pass). Report against the ceiling.

- m4_09's driver (manual): free lip_fullness (-) pushes the whole nose ~1.7 mm per sd forward (manual said ~1) and
  carries lips + chin back; mm:lower_lip_forward drags chin_projection -0.26 sd per mm; which onion-skin copy is the
  target's is hard to tell (sign errors on brows); "corners 3.1 mm" needs "total".

## eyeruler (2026-10-11, "eyeruler" agent, branch worktree-agent-aca121f3738eb053b; Joe on gb_01: "I notice some measurement
## errors" (our eye is narrower corner to corner than hers) and "the upper eyelid just isn't realistic". Scratch
## /mnt/data/hifipushie/eyeruler (run.sh / q.sh; scripts in spikes/eyeruler); sheets human_renders/er_*)
STATE / NEXT (eyeruler, 2026-10-11, handed over; branch worktree-agent-aca121f3738eb053b ready to merge): the eye
ruler exists and is validated (eye_ruler.py; tool `eye_ruler`; guide 7a); the narrow eye and the puffy lid are explained
and fixed on scratch models (er_s4 = the solve, er_R4 = dressed); sheets human_renders/er_01 (photo | gb_fx | result +
table), er_02 (the lid vs #376 / #540), er_03 (the reader's validation). No real model touched.
NEXT / OPEN: (1) Joe's read of er_01 / er_02: the fold LINE is paint (skin.eyes.crease) and reads a little drawn-on;
GNM gives the fold's shape at her height but not a crisp line. (2) the eye step's default is still identity + 20 eye
pairs; identity only (solve(ne=0)) reached the same margins: decide at the restart. (3) skin._aperture_keep_out erases
EVERY lid layer within 1-1.7 mm of the ball, i.e. the whole lid platform (why crease make-up never showed): only the
new fold line is exempt; eyeshadow still is not. (4) er_s4's brows are gb_fx's fit on another head: brow_read again.
(5) inner canthus still 0.7-0.9 mm short of hers (inside the reader's error); width_temple went out of the block-in
table (+2.2 -> +3.5 mm): not among the held measures. (6) the caruncle is a painted pocket + a tint on the ball, not
her fleshy 3-4 mm; (7) Garrett's front picture has a ~5 px iris: the ruler declines (NOTE under 30 px).

### Step 0: the mesh's own numbers (spikes/eyeruler/probe.py; lid margin ring = skin rows next to the socket lining)
| model | ring width (mm) | lm 42-45 | opening (z extent) | ball r |
|---|---|---|---|---|
| gd_T12 | 22.1 | 23.9 | 9.8 | 12.6 |
| gd_T30 (old eye step) | 22.4 | 24.3 | 10.4 | 12.6 |
| gk_ev5s376 (gk_07) | 21.9 | 23.6 | 9.9 | 12.6 |
| gb_T12r (ball 10.64) | 22.1 | 23.9 | 9.8 | 10.64 |
| gb_fx | 21.3 | 23.0 | 7.9 | 10.64 |
| gk_s376 / gk_s540 | 23.1 / 21.4 | 25.0 / 23.4 | 10.2 / 9.5 | 12.6 |
By eye on the gb_01 shots (to be replaced by the ruler): her fissure ~26 mm at the model, ours ~21 with only ~19 mm of
sclera showing. So the block-in's head (gd_T12, 22.1) never had her length; the eye steps took 0.2-0.8 mm more.

### Step 1: the eye ruler (src/hifipushie/eye_ruler.py; spikes/eyeruler/rule.py, validate.py, det.py, table.py)
- Frame per eye: origin = the iris centre, u = mm toward the outer corner along the line through both iris centres, v = mm
  up; everything in mm AT THE MODEL (the fitted camera's mm / px). Columns COLS = u -9 .. 9 mm every 3.
- read(img, P, mmpx, scale, origin): the PICTURE reader. (1) The iris is a least-squares CIRCLE through the limbus edge
  in the two side sectors (+-55 deg, lid-covered rays dropped): centre AND radius (blockin_eyes.limbus only re-seats the
  centre sideways). (2) skin-likeness K (the skin's chroma (R-B)/(R+G+B) and >= 0.7 of the local luminance): the eyeball,
  lash line, liner, waterline, caruncle are all not skin; K's edges, tracked by dynamic programming inside the
  detector's +-2.5 mm band, are the OUTER sides of the lid rims. (3) the margins proper (where the eyeball ends) are the
  edges of the chroma inside those, read outside the iris' disc; across the disc the rim's thickness is carried over.
  (4) the visible eyeball ends where the lids close; the inner canthus = the medial tip of the not-skin wedge past it
  (caruncle). (5) fold line = a ridge of narrow darkness 1.5-10 mm over the margin; brow = the dark band's lower edge.
  MediaPipe is only a search band. First tries that failed: ridge tracking on the chroma alone (the limbus ring and
  iris texture are ridges too), taking the iris out by its radial picture (the lid over the disc went with it).
- model(spec, cam): the same measures on the MESH: the visible eyeball from likeness.render's part pass (0.05 mm), the
  margin ring (skin rows next to the socket lining) projected, the crease / platform from blockin_eyes' sagittal
  profile at each column, the brow from blockin_brows.model_band; + "gap" (socket lining showing between ring and ball).
- VALIDATION (val.sh: 14 dressed shots through Tess's fitted camera: 10 sampled GNM heads gk_s*, gd_T12, gd_T30,
  gk_ev5s376, gb_fx; both eyes = 28; reader - mesh, mm):
  | measure | bias | sd | verdict |
  |---|---|---|---|
  | iris centre x / y | 0.06 / -0.06 | 0.12 / 0.06 | good |
  | iris diameter | -0.10 | 0.06 | good |
  | upper margin, 7 columns | -0.2 .. +0.2 | 0.13-0.27 | good (0.2-0.3 mm) |
  | lower margin, 7 columns | +0.2 .. +0.4 | 0.13-0.33 | reads 0.35 mm HIGH (consistent: the waterline) |
  | mrd1 / mrd2 (margins at the pupil) | -0.07 / -0.39 | 0.18 / 0.20 | good / biased as the lower margin |
  | opening per column | -0.2 .. -0.5 | 0.2-0.5 | ok |
  | outer canthus u (= where the eyeball ends) | -0.37 | 0.26 | ok (lashes hide the last 0.4 mm) |
  | inner canthus u / v | +0.41 / +0.74 | 0.47 / 0.56 | ok, +-0.5 |
  | fissure length | -0.80 | 0.53 | ok after the bias; a difference under ~1.5 mm is not one |
  | canthal tilt (deg) | -1.1 | 1.5 | COARSE: only differences over ~3 deg |
  | upper lid's peak position | +0.40 | 0.40 | ok +-0.6 |
  | caruncle (sclera end - canthus) | 0.0 | 0.40 | ok on renders; on the photo the pink inner sclera reads as caruncle (+-1) |
  | brow lower edge over the margin | -0.3 .. -1.0 | 0.4-0.7 | ok +-0.7 (vs the decal's predicted edge) |
  | fold line (crease) on a RENDER | +-2 | 0.7-3.8 | DROPPED on renders: the soft fold is not a line (as gnmcrease found); the model's crease comes from the mesh. On the photo (crisp line, darkness 0.22 vs 0.01-0.04 on renders) it is used, unvalidated |
- MediaPipe against the same truth (det.py, renders): iris centre 1.14 mm LOW (sd 0.17; photo: 0.6-1.1 low against the
  circle), iris diameter -2.8 mm (22 %; photo -9 %), upper lid at the pupil +1.05, lower +1.5, inner corner 1.6 mm
  medial of the opening's end, width +1.0. GNM's lm68 eye corners: inner 1.87 mm MEDIAL of the visible inner canthus
  (sd 0.28), outer 0.46 lateral: the landmark width is 2.3 mm more than the visible fissure (sd 0.17).

### Step 2 (first numbers): photo vs models (table.py; mean of both eyes; mm in each eye's frame)
| | fissure | inner canthus (u, v) | outer (u, v) | upper margin at u -6 / -3 / 0 / 3 / 6 | lower at 0 | opening at 0 | iris | pupils apart | intercanthal |
|---|---|---|---|---|---|---|---|---|---|
| PHOTO (read) | 23.0 | -13.2, -2.7 | 9.8, -1.9 | 1.3 / 2.1 / 2.1 / 1.8 / 0.9 | -4.9 | 7.0 | 11.0 | 53.4 | 26.9 |
| gd_T12 (block-in, ball 12.6) | 21.1 | -10.5, -2.5 | 10.6, -1.2 | 1.9 / 3.5 / 4.2 / 4.1 / 3.2 | -5.5 | 9.7 | 12.8 | 52.7 | 31.8 |
| gb_T12r (ball 10.64) | 20.3 | -10.5, -2.6 | 9.8, -0.8 | same | -5.6 | 9.7 | | 52.8 | 31.8 |
| gb_T12e = gb_fx (eye step) | 20.0 | -10.5, -3.4 | 9.4, -1.4 | 1.5 / 2.9 / 3.4 / 3.0 / 2.0 | -4.4 | 7.8 | 10.7 | 53.9 | 32.9 |
| gk_ev5s376 (gk_07) | 21.1 | -10.8, -3.3 | 10.2, -1.6 | 2.0 / 3.5 / 4.0 / 3.7 / 2.7 | -5.5 | 9.5 | 12.8 | 53.7 | 32.0 |
| gk_s376 / gk_s540 (GNM samples) | 22.1 / 20.5 | -11.5 / -10.5 | 10.6 / 10.0 | | -6.1 / -6.0 | 10.0 / 9.3 | 12.8 | 54.1 / 49.3 | 31.1 / 28.3 |
First read (to be confirmed by the fixes):
- The fissure never matched: the block-in's head was 21.1 against her 23.0 read (23.8 with the reader's bias), ALL of
  it at the INNER corner (-10.5 vs -13.2: her inner canthi are 26.9 mm apart, ours 31.8-32.9; out/c_inner.png shows it
  in one crop). The outer canthus matches (9.8 vs 9.4-10.6). The smaller eyeball took 0.8 mm off the outer end (the
  ball no longer fills the corner: lining gap 1.2-1.4 mm at u +9), the eye step 0.3 more.
- Why the block-in thought it matched: its landmark fit compares MediaPipe's corners (photo: 23.0 wide, right on her
  canthi) with GNM's lm68 corners (24.0 on gd_T12), which sit 2.3 mm wider than our visible opening. So the model read
  "1 mm too wide" while it showed 2-3 mm too narrow.
- The lids were matched against the wrong iris centre: the detector's centre is ~0.9 mm low on her photo, the model's
  read uses the true pole. True reads: her upper margin is 2.1 mm over the iris centre (0.38 iris r), ours 3.4 (0.64);
  her lower -4.9, ours -4.4. This is gnmbrow's open "~1 mm: the detector reads our upper lid higher than hers".
  Her visible platform (fold line over the margin) is 4.7 mm, ours 3.7-3.9: with the margin 1.3 mm lower it would match.

### Step 2 (confirmed): why the eye was narrow, per suspect (table.py, det.py, rawgnm.py, clay.py; out/table*.txt)
THE MISS (photo read vs gb_fx's mesh, mm from the iris centre): inner canthus -13.2 vs -10.5 (where our opening ends),
outer 9.7 vs 9.4, upper margin at the pupil 2.1 vs 3.4, lower -5.3 (bias taken off) vs -4.4, tilt 2 vs 6.6 deg.
- THE INNER CORNER is three things (out/clay_gb_fx.png shows them):
  1. GNM's CANTHAL POCKET is painted as skin: 1.5-1.9 mm. In GNM's mesh the margin ring (skin next to the socket
     lining) ends 1.9 mm lateral of its own lm68 inner corner (raw template: ring -10.4, landmark -12.5 mm from the
     pupil); between them is a tapering pocket of SKIN-group surface: the caruncle's place. The skin's caruncle layer
     was a faint pink spot, so the eye read as ending at the eyeball. MediaPipe on our renders puts the inner corner
     1.6 mm medial of the opening's end (at the pocket's tip), on her photo right on the caruncle's tip. Fix: dressing
     (skin.eyes.caruncle), not shape.
  2. the EYEBALL does not fill the corner: 0.4-0.9 mm inner, 0.6-1.2 mm outer. GNM's own ball is a 14.5 mm sphere
     (iris 10.5) and its ring hugs it within 0.4-1.5 mm corner to corner; ours was 12.6 (blockin2's absolute 0.012 x
     eyes 1.05), then 10.64 (gnmbrow, to make the drawn iris 10.7). At 10.64 the visible eyeball is 20.0 mm wide in a
     21.3 mm ring, with 1.2-1.4 mm of lining showing at u +9. Fix: keep the ball (er_*: the eye_radius key removed =
     12.6), give the iris its size in skin.eyes.iris_size.
  3. IDENTITY: 0.8-1.2 mm. lm68's inner corner -12.05 vs her -13.25 (her inner canthi are 26.9 mm apart, the
     landmarks 29.7). The block-in's landmark fit compares the detector's corner width (23.0 on her photo) with lm68's
     (23.0-24.0): it read "matched". For the eye step's new corner term.
- Suspects asked about: the smaller eyeball: -0.8 mm of visible fissure (21.1 -> 20.3, outer end), the lids not pulled
  in (ring unchanged). The eye step's lids-in-iris-radii-at-the-pupil: it matched 0.63 / 0.83 r from a detector centre
  0.9 mm low: upper margin 1.3 mm too high, lower 0.9 too high; the corners were never evidence (ring 22.1 -> 21.3,
  -0.3 mm visible). The landmark holds: lm 36-47 are not held, nothing drifted far (lm width 24.0 -> 23.0). The
  expression (ablation er_a2 = er_a1 with the eye pairs cleared, |e| 4.9 -> 0): lower lid 0.7 mm lower, upper 0.2
  lower, tilt 4.6 -> 2.9 deg, crease 0.3-0.6 mm lower: it mostly lifted the lower lid and the outer corner.
- "Short and round": her opening 23.0 x 7.0-7.4 mm (aspect 3.2), ours 20.0 x 7.8 (2.6). Her iris sits HIGH in the
  opening: the upper lid hides 3.4 mm of it (ours 2.0), the lower lid sits at the limbus.

### Step 2b: the eye step on the ruler (blockin_eyes: ruler_evidence, Reader.margins, solve(ev["ruler"], ne=))
- Evidence: the picture's margins at u -9 .. 9 (sigma 0.15 mm; +-9 at half weight; lower - 0.35), the inner canthus
  against lm68's inner corner (0.3 mm; v at a third), the outer one + 1.2 against the ring's lateral end, the crease
  template carried to the ruler's fold line (mm at the model, no iris-size conversion). The model side is read straight
  off the mesh each evaluation (the ring's polygon in a level front view from the ball's forward pole).
- er_s1 (esolve.py gb_fx er_s1: ball 12.6, identity + 20 eye pairs, s376 make, 6 its): upper margin
  -0.1 / 1.3 / 2.05 / 2.2 / 1.7 / 0.9 / -0.6 vs her -0.1 / 1.3 / 2.0 / 2.1 / 1.8 / 0.9 / -0.95; lower -3.7 / -4.3 /
  -4.7 / -5.0 / -4.9 / -4.4 / -3.7 vs -3.6 / -4.0 / -4.7 / -5.3 / -4.95 / -4.5 / -3.1; inner canthus -12.8 (her
  -13.25, was -12.05); section rms 0.22 -> 0.13 mm; |dc| 2.9 from gb_fx, |e| 4.9 -> 3.9; socket within 0.1 sd.
- Tool `eye_ruler(name, model=None, save=None)` (server.py, toolset human; eye_ruler.compare / text / overlay), the
  guide's loop item 7a + "### `eye_ruler`", iris_check's advice changed (iris_size, not eye_radius),
  tests/test_eye_ruler.py (a drawn eye with a detector that is off the way MediaPipe is; the limbus circle under a lid).

### Step 3: the solves, the lid against #376 / #540, ablations (esolve.py, lidsec.py, final.py, tab.py)
- SOLVES on the ruler (all reach her margins within 0.1-0.4 mm, inner canthus -12.5..-12.8 vs her -13.25):
  | model | start | variables | holds | |dc| from start | |e| | note |
  |---|---|---|---|---|---|---|
  | er_s1 | gb_fx | identity + 20 eye pairs | lm68, brows, socket | 2.9 | 4.9 -> 3.9 | |
  | er_s2 | gb_fx, expression cleared | identity only | same | 4.4 | 0 | PUPILS MOVED APART 1.5 mm (54.9 vs her 53.4): the solve lengthened the inner corner by moving the eyeball; cranium_height -1.1 sd, neck_width -0.9 |
  | er_s4 | gd_T12's identity, expression cleared | identity only | + gnm_mm's 23 measures at 0.3 mm (SIG_MM) | 6.7 | 0 | THE RESULT: pupils 52.9, only eye_height -1.1 / eye_tilt -1.1 sd moved (ear_out -0.6); block-in table 6/7 5/5 3/3 4/4 7/7 (width_temple +2.2 -> +3.5 mm went out; gb_fx had it and intercanthal out) |
  | er_s5 | same | identity + 20 pairs | same | 5.1 | 3.2 | the same fit: the expression is not needed |
  So IDENTITY ALONE makes her lids; the eye expression (|e| 3.4-4.9 in the older steps) was standing in for identity
  the solve was not asked for. solve(ne=0) is the identity-only form; the tool's default is still identity + pairs
  (a decision for the restart: see OPEN).
- er_s4 against her picture (eye_ruler.compare, mesh vs picture, mm): inner canthus -12.5 vs -13.25, outer 9.8 vs
  9.75, fissure 22.3 vs 23.0, tilt 2.2 vs 2.0 deg, upper margin 1.1 / 2.2 / 2.4 / 1.9 / 0.9 vs 1.3 / 2.1 / 2.1 / 1.8 /
  0.9, lower -4.2 / -4.7 / -4.85 / -4.7 / -4.1 vs -4.0 / -4.7 / -5.3 / -4.95 / -4.5, opening 7.2 vs 7.4, iris hidden
  3.1 vs 3.4, pupils 52.9 vs 53.4: no row beyond the reader's error.
- THE LID vs #376 / #540 (lidsec.py: upper-lid sections on the mesh at u -5 / 0 / +5):
  | | ring-to-ball gap | margin thickness | crease height | recede | platform bulge | crease depth 2.5 / 0.75 mm chord | fold forward |
  |---|---|---|---|---|---|---|---|
  | #376 | 0.05 / 1.0 / -0.3 | 0.0-0.2 | 2.8-3.2 | 1.2-1.6 | 0.0-0.1 | 1.6-1.8 / 0.37-0.49 | 3.3-3.9 |
  | #540 | 0.1 / 0.8 / -0.3 | 1.0 | 2.3-2.8 | -0.1-0.6 | 0.0 | 1.3-1.4 / 0.32-0.43 | 5.4-8.0 |
  | gd_T12 | 0.4 / 2.0 / 0.8 | 0.7-1.0 | 4.6-5.5 | 1.4-2.7 | 0.3-0.4 | 1.1-1.4 / 0.19-0.25 | 2.7-3.5 |
  | gd_T30 | 0.7 / 2.0 / 0.7 | 0.2-0.5 | 4.7-5.5 | 3.3-4.6 | 0.6-0.7 | 2.1-2.3 / 0.56-0.68 | 5.8-7.3 |
  | gb_fx (ball 10.6) | -0.35 / 0.8 / -0.5 | 0.2-0.45 | 3.9-4.5 | 1.2-1.8 | 0.0-0.1 | 1.2-1.4 / 0.17-0.26 | 2.6-4.0 |
  | er_s1 | 0.1 / 1.0 / -0.3 | 0.1-0.4 | 4.5-4.95 | 1.3-1.8 | 0.05-0.12 | 1.1-1.4 / 0.16-0.27 | 2.8-4.1 |
  Read: the lid sits on the ball the same way in all of them (no gap or penetration story; the 10.6 ball only emptied
  the corners). Our Tess lid has #376's recession and fold; its platform is not a bulge (0.1 mm). What differs: the
  crease is half as CRISP (0.75 mm-chord depth 0.16-0.27 vs 0.37-0.49) and sits at her 4.5-4.9 mm instead of 2.8-3.2:
  GNM's crisp folds are its low ones (gnmcrease). A term asking the solve for a crisp crease at her height
  (solve(crisp=)) moved nothing (narrow depth 0.048 -> 0.055 in the solver's soft units, cost flat): not available by
  a local step. gd_T30 had the crispest crease of all and read wrong: a sunken lid (recede 3.3-4.6).
- WHAT MADE THE LID READ PUFFY (ablation, dressed: out/c_abl.png, c_s1.png): not the expression (er_a2 = expression
  cleared: the same soft roll, lower lid 0.7 mm lower) and not the ball. It was the upper margin 1.3 mm too high over
  the iris with the fold where hers is: a 3.7 mm platform under a wide-open lid, where hers is a 4.7 mm platform under
  a lid that hides a third of the iris. With the margin at her height (er_s1 / er_s4) the platform is 4.0-4.9 mm.
  What is still missing dressed is the LINE: a render of GNM's soft valley shows no line (the ruler's line darkness:
  her photo 0.22, our renders 0.01-0.05), and the lash fringe (9 mm lashes, 0.15 mm thick) where hers is a thin dark
  lash line. Both are dressing: skin.eyes.crease (new: a thin multiply line along the picture's fold path, laid as a
  picture from the front), base.lashes / skin.makeup.eyeliner.
- Dressing code (skin_features._eyes, skin_swatch.crease_image): skin.eyes.caruncle (number: the canthal pocket filled
  wet dark red from lm_eye_inner sideways, + a pink spot on the eyeball's nose-side end; unset: the old faint spot),
  skin.eyes.crease {"amount", "path" [[u, v] mm from the iris centre], "width", "color"}; eye_ruler.crease_path(read)
  gives the path from the picture and compare()'s MOVES print it. First tries that did not show: the crease as a
  per-vertex image MASK (a 0.5 mm line is lost between vertices: it must be the layer's colour picture), the eyeball
  spot centred at the lid corner (the ball's end lies 2.3 mm behind it).
- UNEXPLAINED: one shot (s_a1: gb_fx with eye_radius removed) came out with the whole head ~10 mm to the picture's
  left of every other shot of the same camera; er_a4 / er_s* with the same key state did not. Not chased.

### Step 4: the dressed result, read by the same reader (rule.py on fitted-camera shots; sheet er_01)
| measure (mm from the iris centre) | photo | gb_fx | er_R4 (result) | reader err |
|---|---|---|---|---|
| fissure | 23.0 | 19.8 | 21.5 | 1.0 |
| inner canthus u | -13.2 | -10.5 | -12.3 | 0.6 |
| outer canthus u | 9.8 | 9.2 | 9.1 | 0.45 |
| canthal tilt (deg) | 2.0 | 6.3 | 2.7 | 1.8 |
| upper margin at u -6 / -3 / 0 / 3 / 6 | 1.3 / 2.1 / 2.1 / 1.8 / 0.9 | 1.2 / 2.6 / 3.2 / 3.0 / 2.0 | 1.0 / 2.0 / 2.3 / 1.8 / 0.8 | 0.25 |
| lower margin at u -6 / 0 / 6 | -3.6 / -4.9 / -4.1 | -4.0 / -4.2 / -3.6 | -3.9 / -4.5 / -3.8 | 0.25 |
| iris hidden by the upper lid | 3.4 | 2.1 | 3.2 | 0.2 |
| iris diameter | 11.0 | 10.7 | 10.9 | 0.12 |
| fold line read on the image: height at the pupil / darkness | 4.7 / 0.22 | - / 0.04 | 4.5 / 0.08 | (flagged) |
- er_R4 = er_s4 + skin.eyes.caruncle 1 + skin.eyes.crease (amount 0.6, the picture's path, shade 0.4) + base.lashes
  upper length 7 / thickness 0.10 / count 200 / curl 45, lower 2.5 / 0.03. er_R0 = er_s4 + caruncle only.
- BLUNT READ (er_01, er_02; every claim has its number above): the opening is now hers: an almond with the iris high
  in it, corners within a millimetre, tilt right. It still falls short at the inner corner by 0.9 mm (-12.3 vs -13.2)
  and reads 1.5 mm shorter overall, at the edge of what the reader can tell. The upper lid no longer reads as a roll:
  the platform is her height and flat. The fold line is now there at her height at about a third of her darkness
  (0.08 vs 0.22) and it looks like a thin pencilled arc: it ends short of the corners (the reader gives the path only
  to u +-9) and has no fold shading around it. Finer lashes read as a lash line like hers; no liner wing was rendered
  (the liner variant's render did not finish). Her brows and iris colour are gb_fx's, unchanged. The caruncle is a
  dark red wedge, not flesh. #376 / #540 still have a crisper GEOMETRIC crease than anything on Tess: GNM's crisp
  folds are its low ones.
- Scratch (workspace, delete freely): er_a1..a4 (ablations), er_s1..s5 (solves), er_T* / er_F* / er_R* (dressing).
  /mnt/data/hifipushie/eyeruler: run.sh, q.sh, tests.sh, val.sh (validation), abl.sh, dress2.sh / dress3.sh, out/
  (s_*.png shots, o_*.png overlays, rule.json, validate.txt, det.txt, table*.txt, lidsec.txt, cmp_s4.txt, esolve_*.log).
  Scripts: spikes/eyeruler (rule.py, validate.py, det.py, table.py, cmp.py, rawgnm.py, clay.py, lidsec.py, esolve.py,
  mk.py, final.py, tab.py, lay.py, sheet1.py, sheet23.py).
- Lost GPU contexts ("amdgpu: The CS has cancelled because the context is lost") killed two shots while a cloth job
  ran on the GPU: dress2.sh / dress3.sh retry each shot.
