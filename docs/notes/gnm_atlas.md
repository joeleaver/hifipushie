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
