# The GNM model atlas (facesliders, 2026-10-09)

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
