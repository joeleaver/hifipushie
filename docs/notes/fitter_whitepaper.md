# Idea for later: an image -> GNM fitter, reviewed by an LLM (white-paper candidate)

Status: idea only, parked 2026-10-10 by Joe ("a nice idea for later ... it might be a really nice white-paper project").
Pick up after the coherent face model work (gnm_atlas.md: faces4 / faces5, the GNM audit gnm_audit.md) has shown what
evidence GNM needs to be driven well.

## The idea
Look at a picture of a person and fit a standard mesh (GNM: identity + habitual / per-picture expression) to it.
Two cooperating parts, each doing what it is good at:
- A trained DENSE-LANDMARK network for the numbers: hundreds of points over the whole face (lid margins, crease,
  nostrils, lip borders, contour), each with an uncertainty, on photos and on our renders alike. The fit is a solve
  of GNM's parameters (+ camera, light) to those points under the joint prior. This also fixes our measurement problem
  (2026-10-10: likeness.json's 85 items are sparse 2D ratios and miss most of lids / nose / lips / depth).
- An LLM / VLM (Claude, as today) for JUDGEMENT: which evidence to trust (hair over a cheek, a squint is expression not
  identity, lighting hides a crease), artefacts, naming what is still wrong in feature terms, steering the solve. It
  works best given focused crops and a checklist. It is poor at sub-mm measurement: never the measuring instrument.
  Fine-tune our own VLM only if Claude's judgement turns out to be the bottleneck (so far the measurements were).
Detectors / face-ID models are precise and cheap but blind to "why", trained to ignore expression, and fail across
style gaps (clay vs painting: ArcFace / SFace -0.16..+0.11 on Garrett's concept).

## Prior art to cite / compare
- Wood et al., "Fake It Till You Make It: Face analysis in the wild using synthetic data alone" (Microsoft, ICCV 2021)
  and the follow-up on 3D face reconstruction with dense landmarks (ECCV 2022, ~700 landmarks with uncertainty, fitted
  to their model). Closest template: synthetic renders from the face model give perfect, unlimited, licence-clean labels.
- Image -> 3DMM regressors on FLAME (non-commercial: comparison only): DECA, EMOCA, MICA, SMIRK; 3DDFA.
- Check whether Google ships a GNM fitter (the GNM audit should say).

## Our version
1. Sample identity + habitual / transient expression from the joint prior (faces5 M3), plus skin, hair, eyes, light,
   camera, occluders.
2. Render with our own pipeline (realism where it matters for transfer; a cheap renderer for the bulk).
3. Train the dense-landmark network (with per-point uncertainty) on those renders; validate on real photos (Face
   Research Lab London Set, CC BY 4.0, photos stay on /mnt/data).
4. Fit = solve to the network's points (+ silhouette / shading terms where useful) under the prior; Claude reviews
   with crops and steers.
Novel angles for a paper: the LLM-as-reviewer loop (evidence triage, identity vs expression, feature-level
critique), habitual expression as part of identity, perceptual (identity-weighted) error measures, licence-clean
pipeline end to end.

## Rough cost (estimates, not quotes)
- Data: 100k-300k synthetic faces at ~256 px. Full Blender renders take a few s each -> roughly 100-300 h local; a
  simpler renderer or rented machines cut that a lot.
- Training a standard image network: ~10-50 GPU-hours on one rented GPU (tens to a couple hundred dollars).
- Adapting an existing VLM (LoRA) if ever needed: ~tens of GPU-hours.
- First version plausibly a few hundred dollars and a week or two elapsed; the main risk is synthetic-to-real transfer.

## Landscape check (2026-10-10, "gnmcontrols" agent; gnm_atlas.md "## gnmcontrols")
Nobody publishes a photo -> GNM route beyond sparse-landmark ridge fits: no identity-embedding route, no learned
regressor; Google hasn't released its own fitting code or the ~600 dense landmarks its fitting uses.
- rethink-studios/ComfyUI-GNM "GNM Extract Identity From Photo" (Apache-2.0, 01fefbc, "fitting not yet finalized"): a ridge
  fit on MediaPipe points mapped to iBUG-68 through a wrong table (eyes get nose points, brows get cheek points), the
  ridge at ~10x the data term: it returns roughly GNM's mean.
- google/xrblocks samples/avatar_lab/gnm (Apache-2.0, from edualvarado/gnm-webcam-puppet): MediaPipe -> GNM vertex
  correspondence fitted differentially against a reference cloud (cancels MediaPipe's depth bias), 24 leading comps,
  ridge, 4 alternations: the best public recipe, a generic face.
- Also checked: gnm-maya (68-point weak perspective), headSize-gnm, soylab-edu/ComfyUI-GNM (GPL, samplers only).
On Tess (block-in target table): our block-in 26/26, published recipes and our old MAP fit 20-23/26, GNM's mean 22/26.
So a dense-landmark network trained on our own synthetic GNM renders (above) would be the first of its kind in the open,
which strengthens the white-paper case.

## The paper's section 4.2 against what we do (2026-10-12, coordinator; Joe asked whether we followed through)
GNM Head paper, arXiv 2607.23687v1, 4.2 "3D Face Reconstruction":
- Shared method: optimisation to DENSE 2D landmarks (~600 from a detector, Chandran et al. 2023 / 2024; after Wood et
  al. 2022, Hewitt et al. 2024). Variables: identity, expression, JOINT ROTATIONS, root translation, camera
  intrinsics. Energy = landmarks + L2 prior (identity, expression) + ANATOMICAL penalty (skin against eyeballs, teeth,
  tongue, gums) + temporal smoothness (video). Weights as Wood et al. 2022. Fitting code and detector NOT released.
- 4.2.1 single view, synthetic: 2,000 images, ~7,000 GROUND-TRUTH surface landmarks: GNM 1.68 mm mean vs FLAME 2.17.
- 4.2.2 MULTI-VIEW captures (synchronised studio video, extreme expressions): ONE identity shared over all frames;
  expression, joint rotations and root translation PER FRAME. Qualitative.
- 4.2.3 IN THE WILD single images: the INNER-MOUTH landmarks (teeth, tongue, gums) ANCHOR the fit; jaw opening,
  tongue, asymmetric eye movement recovered. Qualitative.
Where we stand:
- 4.2.2: half. We share identity over views and free the cameras, but each view is a RIGID head: no per-view
  expression (built by solvereads, failed validation: nothing independent reads it), no per-view joint rotations
  (jaw, eyeballs / gaze, neck). And our reference sets are 2-4 neutral stills; the paper's strategy is MANY frames
  with VARIED expressions, which is what separates identity from expression.
- 4.2.3: not at all. We threw GNM's mouth away until today (gnmnative brings it back), have no inner-mouth reads,
  and Tess's `tess_head_front_smile.png` (asked for in her brief, delivered) was never used for identity.
What to do, in order (nothing started; Joe to say):
1. After gnmnative: per-view JOINTS in the solve (jaw rotation, eyeball rotation from the iris reads, neck) and the
   anatomical penalty: both need no new detector.
2. TEETH as anchors without a dense network: teeth are high-contrast and rigid to the skull; the upper incisors'
   edges / midline / occlusal line from a parsed mouth region in a smile or open-mouth picture, differential against
   our render. Teeth are also a METRIC anchor (their size varies little), like the iris: that would pin the head's
   SIZE, which chinread found unread (heads 1-8 % large).
3. Reference briefs: add a smile showing teeth, jaw open, eyes closed and eyes wide to the neutral set (shared
   identity + per-view expression then has something to separate), or a short turn-table / talking video.
4. The dense-landmark network on our own synthetic GNM renders (this file's idea): the read that makes per-view
   expression identifiable and reads interior relief (chin ball, cheeks). Data generation can now run on the other
   machines through the offload route.

## Backup: DAD-3DHeads (Joe, 2026-10-12)
Joe: "Let's keep it as a backup plan. I've applied for the gate." DAD-3DHeads (CVPR 2022, arXiv 2204.03688;
huggingface.co/datasets/t-martyniuk/DAD-3DHeadsDataset; github.com/PinataFarms/DAD-3DHeads + DAD-3DNet): real
in-the-wild photos with a per-image head mesh and camera, attribute buckets, ~40 GB. CC BY-NC-SA 4.0, gated,
"non-commercial research and educational purposes only", no passing on. Joe applied for access himself. STATUS: a
BACKUP, not in use. Nobody downloads or uses it until Joe says access is granted AND says what it may be used for
(most likely: evaluation of sim-to-real transfer only, never training anything we ship). The primary plan stays our
own synthetic GNM renders (denselm).

## denselm (2026-10-12, "denselm" agent, branch `worktree-agent-a2e75a7e571826c88`; Joe: "Ok, that's a big chunk of work. Let's go for it.")
Our own dense-landmark network, trained only on synthetic renders of GNM heads from our own pipeline. This round is
SCOPE + PILOT. Scratch DURABLE in /mnt/data/hifipushie/denselm: run.sh <script> (capped, this worktree's src, its own
workspace ws/; WS=main for main's), submit.sh <batch> <ram> <timeout> "<gen.py args>".. (offload jobs, one dressing
each), data/ (samples), out/ (sheets, logs); code: src/hifipushie/denselm.py (the landmark set, inference),
spikes/denselm (gen.py + blender_gen.py: the generator; job_gen.py; train.py + net.py; peek.py / augpeek.py).

### State
STATE (2026-10-12, end of the round): VERDICT: YES, the direction pays, for closed-mouth faces; the full run is
worth doing AFTER gnmnative (teeth / open mouths) and with three fixes to the data (wider identities, cheaper
samples, real hair / clothes). A pilot trained on 4,800 of our own renders (18 dressings, 89 GPU-minutes) puts 570
GNM vertices + 18 eye points on a picture with its own honest sigma: 1.8 mm mean on unseen synthetic people; on
the known-head benchmark 1.4 mm median from the front (MediaPipe's 68: 4.0; ours on the same 68: 1.4), 2.0 mm on
a 72 deg view MediaPipe cannot read; on Tess's photos, Garrett's paintings and the held-out Garrett photos the
points lie on the features (eye, lid, nose, lips, chin outline; tiles judged one by one). In the joint solve it
takes the six known heads from 2.18 to 1.46 mm face rms (lower face 2.54 -> 1.80) and fixes the head's SIZE (6 %
-> 1.9 %). What it does NOT do: read the chin's own width (answers with the average chin; it made one broad-jawed
benchmark head worse), open mouths (never seen one: lower lip 4-6 mm wrong on a smile with teeth), make the
per-view expression term work. Code: denselm.py (set + inference), face_ruler `dense` (OFF by default),
spikes/denselm (generator, trainer, job runners, evaluation). Tests: tests/test_denselm.py (4) + face_ruler /
refread suites pass (17).
NEXT (in order): (1) Joe's go / no-go on the full run and its options ("### The full-run plan"); (2) judge the
dense solves of Tess / good Garrett on the judging sheet before `DENSE` becomes a default; per-region sigma scale
for chin / jaw from the benchmark so the unread width cannot pull; (3) after gnmnative: landmark set v2 (teeth,
tongue, gums, GNM's eyeball), open-mouth expressions in gen.py (`open=1`), then the wider identity sampler;
(4) generator speed (2 mm stage mesh, 4-6 TAA samples, chunk = n); (5) the reference brief's expression shots
become usable for the per-view expression term only with (3).

### What the literature actually did (primary sources read 2026-10-12; "not stated" = the paper does not say)
- Wood et al. 2021, "Fake It Till You Make It" (ICCV; arXiv 2109.15102): 100,000 images at 512 px, Cycles, 48 h on
  150 M60 GPUs (~4 GPU-minutes an image; costed $7,200). Identity: a generative model from 511 scans; expression: a
  library of 27,000 parameter sets fitted to annotated images; 200 texture sets (8K); strand hair: 512 scalp styles,
  162 brows, 142 beards, 42 lashes; 30 upper-body outfits, 36 headwear, 7 facewear, 11 eyewear; 448 HDRIs as light AND
  background; camera placed at random round the head, focal length and depth of field varied. Network: ResNet-34,
  DIRECT regression from a 256 px ROI, MSE, no sigma; 68 landmarks for the benchmark, a dense variant with 679.
  Augmentation: rotation, perspective warp, blur, brightness / contrast, noise, grey. 300W NME common / challenging:
  3.09 / 4.86 synthetic-only vs 3.37 / 5.77 the same network on real data. Ablations (common / challenging / failure
  rate at 10 %): no augmentation 4.25 / 7.87 / 4.00; appearance augmentation only 3.93 / 6.80 / 1.83; NO HAIR OR
  CLOTHING 3.36 / 5.37 / 2.17 (full: 0.50); no clothing 3.20 / 5.09 / 1.00. "Label adaptation" (a small MLP from
  their labels to 300W's human labels) is only for scoring against human annotation: 5.61 / 8.43 without it; a fit
  does not need it. Learning curve: improves with image count, "starting to plateau at 100,000" (no numbers).
- Wood et al. 2022, "3D face reconstruction with dense landmarks" (ECCV; arXiv 2204.02776; project page
  microsoft.github.io/DenseLandmarks, Joe's pointer): 703 landmarks offline (the whole head incl. ears, EYEBALLS,
  TEETH), 320 real-time; how they are chosen on the mesh is not stated. Networks: ResNet-101 (offline), MobileNetV2
  (real-time: 4.1 ms a frame for the landmarks on one CPU thread, the page's "> 150 FPS"); direct regression, the
  last layer gives 3 numbers a landmark: x, y, log sigma. Loss = sum_i lambda_i [ log(sigma_i^2) + |mu_i - x_i|^2 /
  (2 sigma_i^2) ] (Gaussian NLL; coordinates normalised to [-1, 1]; sigma is never supervised itself; lambda not
  stated). 100k synthetic images (the 2021 pipeline + expression-dependent wrinkles, more hair / clothes), AdamW,
  batch 128, 300 epochs; input size "S x S" not stated; ROI from a sparse-landmark CNN (offline) or eyes + mouth
  alignment (real-time; fails on profiles). No visibility flag: an occluded landmark gets a large sigma and so
  little weight. THE FIT: E = E_landmarks + E_identity + E_expression + E_joints + E_temporal + E_intersect with
  E_landmarks = sum |x - mu|^2 / (2 sigma^2) over frames, cameras, landmarks (THE ONLY DATA TERM); identity = a GMM
  prior from scans; expression and joints L2; intersect = eyelid vertices inside the eyeball sphere + skin inside
  the teeth's convex hull; L-BFGS (offline) / Levenberg-Marquardt (real-time); focal length optimised when monocular.
  Numeric weights: not stated. Accuracy: 300W 3.03 / 4.80 with the NLL vs 3.30 / 5.12 with L2 only; NoW (median mm)
  1.02 single view, 0.81 multi-view (DECA 1.09). LANDMARK COUNT (NoW validation, median / mean mm): 68 -> 1.10 /
  1.38; 320 -> 1.00 / 1.24; 703 -> 0.95 / 1.17; 703 WITHOUT sigma -> 1.02 / 1.26. So going dense buys ~14 %, the
  sigma another ~7 %. No code, weights or dense labels released (github.com/microsoft/DenseLandmarks: 404).
- Hewitt et al. 2024, "Look Ma, no markers" (SIGGRAPH Asia; arXiv 2410.11520): face 744 landmarks (incl. 16 limbus
  points per eye, 12 teeth, 9 tongue), body 1428, 141 a hand; HRNet-w48 (ImageNet-pretrained) + a 2-layer MLP head,
  256 px input, the same NLL; ~100k images each (SynthFace / SynthBody / SynthHand), AdamW 1e-4 cosine, batch 256
  on 4 A100s, 300 epochs (face). Augmentation: ROI rotation / scale / translation, motion blur, brightness, contrast,
  hue / saturation, JPEG, grey, ISO noise. Fit as 2022 + a camera prior; uniform weights instead of sigma: body
  error 51.0 -> 67.4 mm. NoW 0.89 single / 0.70 multi-view. Released: the DATASETS only, non-commercial, with 70
  sparse landmarks (not the 744); no model, no weights. The eyelid-fold paper (arXiv 2410.13760, same group):
  nothing released.
- Chandran et al. 2023, "Continuous Landmark Detection with 3D Queries" (CVPR; Disney): an image encoder (ConvNeXt
  / MobileNetV3) + an MLP / transformer that takes a 3D QUERY POINT on a canonical face and returns its 2D position
  + a confidence (the same NLL): any landmark set at test time. Trained mostly on REAL studio data: 100k multi-view
  images with ~50,000 dense landmarks each from 3D reconstructions, + 300W, + FaceSynthetics, + skull / jaw / teeth
  / eye sets. Dense queries work only with dense training labels (a 70-landmark model fails when queried densely).
  Single-view fit error: 68 landmarks 2.88 mm, 500 -> 2.63, 50K -> 2.34. Chandran et al. 2024 ("Infinite 3D
  Landmarks", CGF): + a learned spatial transformer for the crop, 3D canonical offsets + pose + focal length
  predicted, 37k studio images with 47k landmarks + FaceSynthetics; 256 px; 46 fps on a 3090. No code released.
  (This is the detector the GNM paper cites: Disney-style, trained on proprietary studio captures.)
- GNM Head (arXiv 2607.23687, 4.2): E = w_lan E_lan + w_prior E_prior + w_anat E_anat + w_temp E_temp; ~600 dense
  landmarks from the detector above; weights and E_anat's formula deferred to Wood 2022; no per-region breakdown of
  the 600 and no description of where they sit on the mesh; the Discussion says the landmarks will be released.
  Synthetic single view, ~7,000 ground-truth landmarks: 1.68 mm mean (FLAME 2.17).
- What exists to reuse: NOTHING shippable. FaceSynthetics (100k images, 512 px, 70 landmarks + segmentation): the
  "Research Use of Data Agreement": non-commercial, and models trained on it are "Results" barred from commercial
  offerings: not downloaded, not used. MediaPipe Face Mesh V2 (478 points, Apache 2.0): trained on real phone
  pictures with z from synthetic data: what we use today, biased on our dressed renders (chinread). Real landmark
  sets are tiny and sparse by comparison (300-W 3,129 training images x 68 points, research only).
- dense3dfacelandmarks (Basak et al. 2023, arXiv 2308.15170; github.com/shubhajitbasak/dense3dfacelandmarks; Joe's
  pointer). (1) LICENCE: the code is MIT, the checkpoint is NOT usable in anything we ship: trained on 300W-LP
  (300-W's terms: "Commercial use (i.e., use in training commercial algorithms) is not allowed") with labels that
  are Basel Face Model 2009 fits ("internal, non-commercial research, evaluation or testing purposes only").
  Evaluation only; the coordinator's reading is confirmed. (2) LABELS: 520 vertices of BFM's 43,867-vertex template; the "ground truth" is
  3DDFA's 3DMM fit to sparse landmarks (and 300W-LP's large poses are synthesised by warping): a model's guess at the
  interior, no teeth / eyeballs / tongue, no uncertainty output (Wing + MSE); never evaluated on dense points, and on
  the 68 it is slightly WORSE than its teacher PRNet (AFLW2000-3D NME 3.77 vs 3.62). (3) USE: architecture
  reference only (timm mobilenetv2_100, direct regression of 520 x 3 from 256 px, 4.2 M parameters: the same shape as
  ours minus sigma). As a baseline it cannot answer the benchmark's question: its points live on BFM's topology, so
  only its 68 standard landmarks have a GNM correspondence, and those are what MediaPipe already gives us; its
  inference script is not turnkey (hard-coded paths, GPU assumed, imshow). NOT run; nothing built on it.
- DAD-3DHeads (Martyniuk et al., CVPR 2022, arXiv 2204.03688; Joe's pointer; facts as the coordinator read them off
  the dataset page, the paper itself not re-read here): the OTHER route to dense labels: REAL in-the-wild photos, a
  head mesh fitted per image by annotators (per-image vertices + model-view / projection matrices; attributes for
  pose, expression, occlusion, age, quality), with the DAD-3DNet model. LICENCE: CC BY-NC-SA 4.0, gated,
  "non-commercial research and educational purposes only", no passing on: NOT requested, NOT downloaded, its weights
  never in anything we ship. What it gives us without touching the data: (a) the honest alternative to synthetic
  labels costs an annotation campaign and still ends on someone else's topology; (b) its benchmark's SHAPE is the
  template for ours: pose error, landmark error on visible vs occluded points, each by attribute bucket (pose,
  expression, occlusion, quality): `train.py`'s report already splits visible / hidden and by region; pose and
  expression buckets are to add.

### Our design
- THE LANDMARK SET (src/hifipushie/denselm.py `landmarks()`, version 1): 570 GNM skin vertices + 18 eyeball points
  = 588 (the per-region counts below are from a first draft of 595; now: scalp + neck 122, cheeks 88, nose 58,
  forehead 55, orbit 52, lips 41, mouth region 40, ears 34, chin 31, brows 29, lid margins 20). Skin: farthest-point sampling on GNM's template restricted to `skin_exterior` vertices the one human mesh
  carries, with a density per region (lid margins x 3.2, lips x 3, orbit / nose x 2, lip region x 1.9, chin x 1.8,
  brows x 1.6, face x 1.25, ears x 1, scalp and neck x 0.55), on the LEFT half + mid-line and mirrored (so a mirror
  permutation exists for flip augmentation and test-time flips), seeded with the 68 standard landmarks' vertices
  (so the old 68 are a subset: like-for-like comparison with MediaPipe / the block-in's points). Per region: scalp +
  neck 132, cheeks 86, nose 64, forehead 58, orbit 52, lips 44, mouth region 40, chin 34, ears 34, brows 31, lid
  margins 20. Eyeball: per eye the iris centre + 8 limbus points, from the model's eyeball (centre, gaze, radius,
  iris size). AFTER gnmnative (GNM's own components from one evaluation): the limbus / cornea from GNM's eye, upper
  and lower teeth (incisal edges, canine tips, gum line), tongue tip / mid-line, gums: ~60-90 more, as extra
  entries of the same list (`extra`), version 2: the network's head just grows.
- VISIBILITY: predict everything, no flag (Wood 2022): a hidden landmark's sigma comes out large, and the fit
  weights by 1 / sigma^2. The generator still records true visibility (ray casts) for evaluation.
- THE NETWORK (spikes/denselm/net.py): a plain ResNet-18 (our own 60 lines: no torchvision, NO pretrained weights:
  ImageNet's terms are research-only, and "synthetic data alone" stays literally true), 256 px face crop in, 613 x
  (x, y, log sigma) out by direct regression, Gaussian NLL exactly as Wood 2022. 11.5 M parameters. (Wood's
  real-time net is MobileNetV2, the offline one ResNet-101; ResNet-34 is the candidate for the full run.)
  The CROP: 1.5 x the extent of the 68 standard landmarks, square, upright; at training time jittered (scale x
  0.8-1.35, shift +-12 %, rotation +-25 deg); at inference from any face box, then ONCE more from the network's
  own 68 (a self-consistent second pass), so no other detector is needed in the loop.
- INTO face_ruler: ONE MORE OBSERVATION TYPE "dense", per landmark the 2D residual (predicted - the model's
  projected vertex), with the network's OWN sigma per landmark (converted to mm at the view's scale, floored), the
  Jacobian = the vertex's own move (as the anchors). ABSOLUTE, not differential, and that is the point of training
  on our own renders: the differential trick exists because MediaPipe's idea of a landmark is not our vertex (and
  its face on a dressed picture is not its face on clay: the 2.6 mm chin bias). Our network's landmark IS the
  vertex's projection by construction; a differential read would need a dressed render of the current model every
  Gauss-Newton round (~1 min each) and would cancel nothing we cannot measure directly: the synthetic held-out bias
  per landmark is known exactly and, if non-zero on real pictures, shows up in the benchmark. Its errors are
  correlated between neighbours (one network, one crop): the per-view sigma floor and solve(adapt=True) handle
  that as they do for the anchors. BUILT: face_ruler `_dense_obs` / `dense_predict`, reference_views(dense=) with
  the module default `DENSE = False` (a pilot network: off), DENSE_SIG_SCALE 2, floor 0.5 mm, landmarks the
  network gives more than 3 mm of sigma are left out; type "dense" may be explained by a per-view expression
  (EXPR_TYPES). tests/test_denselm.py (4: the set, the limbus points, the crop, the observation against a known
  identity change with a made-up reading).

### The synthetic data pipeline (spikes/denselm/gen.py + blender_gen.py; measured 2026-10-12)
- THE CHEAP PATH, found: ONE dressed head stage per PERSON'S SKIN ("dressing": sex, age, weight, tone, features,
  stubble, brows, make-up, lips, iris, folds, hair; a class-mean head; `stage.ensure`, the same stage the judging
  sheets use), then every sample RE-POSES that scene inside one Blender process: each skin vertex of the stage's
  ~400k-vertex mesh is bound once (BVH, 1.5-3.6 s) to its closest point on the one mesh's skin triangles and carried
  by that point's displacement for a NEW identity + expression (`humanfit.state` of the changed base: 0.1-0.35 s,
  4 processes); the eyeballs move rigidly with their centres and turn for gaze; lashes, the hair's underlayer and
  the hair locks' control points ride the same binding. The paint lives in vertex attributes (wpos / wnrm / hp*),
  so it rides along and the 600-node skin material is compiled once (50-90 s, the first render). The stage mesh
  lies on the one mesh to 0.04-0.05 mm (median), so a label = the vertex itself.
- LABELS: the landmark's pixel through Blender's own camera (world_to_camera_view) and its visibility by a ray
  cast against the evaluated scene (skin, eyeballs, lashes, hair); + identity (170), expression (383), gaze,
  camera, light per sample in meta.npz. Pictures are RGBA with a transparent ground: backgrounds, "clothes" (the
  bare bust below a neckline recoloured as cloth) and every degradation are laid at TRAINING time (train.py).
- WHAT IS VARIED: see gen.py's docstring (identity: semantic sampler by sex / ethnicity + N(0, a^2) on the 170
  components; expression: 35 % neutral, else 1-2 sampler classes + latent noise, both eyes closed on 12 %; gaze;
  yaw to +-100, pitch +-30, roll; 30-200 mm with the matching distance, off-axis crops; a key sun + fill + rim,
  plain worlds or Blender's 8 bundled CC0 studio HDRIs; exposure; three view transforms). Hair: the hair tools'
  curve locks on 55 % of dressings (combed short / medium, loose bob .. long, loose with a fringe, cropped; the
  "locks" style: stylised planks, not strands), a painted scalp shadow on some of the rest, bald otherwise.
- NOT IN THE PILOT (stated, not hidden): (1) OPEN MOUTHS. The stage's lips are one fused surface (no teeth, no
  mouth bag): the sampler's lip-parting classes (surprise, happy, smile_wide, funneler, stretch_face, snarl,
  disgust, blow, tongue_center) stretch a lip-coloured membrane across the opening (probe sheet
  /mnt/data/hifipushie/denselm/out/probe.png), so they are left out (`open=0`): closed-mouth expressions only.
  Smiles with teeth and jaw-open pictures are OUT OF DISTRIBUTION for the pilot: after gnmnative. (2) glasses,
  headwear, hands, distractor faces, real clothes, photo backgrounds, beards as geometry (stubble is paint).
  (3) strand hair. (4) children. (5) large identity steps bend the hair locks (they ride the nearest skin point).
- COST, measured (320 px, EEVEE with ray tracing + fast GI as the stage's looks):
  | | this laptop (890M iGPU, shared) | NICO-TOP (RTX 3070 Ti) |
  |---|---|---|
  | stage sync (per dressing) | 96-150 s (+ 20-40 s with hair) | 107-164 s |
  | first render (shader compile) | 18-39 s | 47-90 s |
  | render, 16 TAA samples | 1.9-2.0 s | 0.89 s (0.60 without ray tracing; fast GI off: no further gain) |
  | render, 8 TAA samples | - | 0.50 s (hair, 16 samples: 1.13 s) |
  | re-pose in Blender / labels (ray casts) | 0.2 s / 0.4-0.5 s | 0.10-0.12 s / 0.17-0.26 s |
  | new identity + expression (controller, 4 procs) | 0.1-0.25 s a sample | 0.15 s |
  So on NICO-TOP at 8 samples: ~0.95 s a sample marginal (bald; ~1.2 with hair) + ~200-250 s per dressing; at 300
  samples a dressing: ~1.7 s a sample all in. Under the 2 s target; NOT "well under". THE BOTTLENECK is EEVEE
  itself, and it is per TAA sample (~0.05 s each at 320 px on a 3070 Ti): the 400k-vertex head with the 600-node
  skin shader and 2-3 shadowed suns is redrawn per sample; pixels are not the cost (320 px). The next gains, in
  order: fewer vertices (the stage is meshed at 1 mm / 0.5 mm at eyes and mouth for close-ups; a 256 px training
  crop needs ~2 mm: ~4x fewer vertices), 4-6 TAA samples (the training crop is downscaled and degraded anyway),
  labels by a z-buffer instead of ray casts (0.2 s), more samples per dressing. Round trip overhead of the offload
  route: ~10 s a job once the environment exists (a new commit: ~2-4 min once per machine).
  The laptop is 2-4x slower per render AND its GPU slot is shared with the other agents (one test waited 8 min
  for it): bulk rendering belongs on NICO-TOP (and enterprise when installed: CPU only? then EEVEE needs a GPU).
- IN PRODUCTION (the pilot's 18 dressings x 300 samples, 2026-10-12 afternoon, both machines SHARED with other
  agents' jobs), all in per sample: NICO-TOP bald 1.7 / 2.3 s, with hair 1.9-4.0 s (mean of 8 dressings 2.9 s);
  this laptop bald 1.9-3.2 s (one outlier 7.4), with hair 3.2-3.3 s (mean 2.9 s). So ~1,200 samples an hour per
  machine as things were, ~2,100 an hour on an idle 3070 Ti. Lessons: `chunk` must equal `n` (a second Blender
  start per dressing pays the 50-90 s shader compile again: dl-A ran chunk 250 on n 300); locally the render must
  NOT take the exclusive GPU claim (resources.heavy(gpu=True) waits for every other agent's stage shot, which
  take no claim themselves: one chunk waited 8 min; now off, DL_GPU_CLAIM=1 brings it back); `pgrep -f` in a wait
  loop matches the waiting shell itself (two of my queues hung or killed themselves that way).
- NICO-TOP INCIDENT (15:52, from the coordinator / oxidegen): its second NVMe threw a controller error seconds
  after the first TRAINING job (dl-p1: a 686 MB job folder fetched and written, to be followed by a multi-GB
  torch install) started; every job after it died ("its machine went quiet mid-job, 3 times over"). Coincidence
  or load is oxidegen's to settle; no data of ours was lost (4 cancelled render jobs, re-renderable by seed). After
  Joe's reboot the training ran there (below). What the staged restart taught about TRAINING jobs on the offload
  route (all in spikes/denselm/remote_train.sh + job_train.py now): a job cannot write uv's cache (build the torch
  venv in the bundle's SETUP step, in the machine's cache: `dl_torch_v2`); PyPI's newest torch (CUDA 13 libraries)
  finds no GPU on NICO-TOP's driver: install from the cu124 index only; torch's DataLoader hands batches over in
  /dev/shm, which the sandbox closes: the job hung at its first batch until batches went as numpy through the
  workers' pipes; upload the data slim (slim.py: JPEG + alpha, 690 -> 200 MB for 5,400 samples).

### The pilot (2026-10-12; model /mnt/data/hifipushie/denselm/models/p1/hm18/model.pt, 48 MB TorchScript, NOT in git,
### not yet an asset pack: a pilot; HIFIPUSHIE_DENSELM points denselm.predict / face_ruler at it)
- DATA: 18 dressings x 300 = 5,400 samples (8 rendered on NICO-TOP, 10 on this laptop; 6 men / 12 women; white 6,
  black 5, asian 5, middle eastern 2; 9 with hair: combed 5, loose 3, fringe 1; 9 bald), 320 px. 16 dressings
  (4,800) train, 2 (600) held out whole. A sixth of the "one overnight" I planned: the afternoon went to machine
  contention (both GPUs shared; ~1,200 samples an hour each) and the NICO-TOP outage.
- TRAINING, what it took (three findings, each cost an hour): (1) from scratch under the FULL augmentation the
  network sits at the mean face (train error = the targets' own spread, 40 px, for 240+ steps; flat ~25 px on
  the validation crops for 25 epochs on 1,800 samples); the same network overfits 64 clean samples to 4.9 px in
  240 steps, and with the augmentation RAMPED IN (strength 0 -> 1 over the first quarter) it learns: `ramp`.
  (2) the plain Gaussian NLL lets sigma grow to the error and the pull on the position falls with 1 / sigma^2:
  beta-NLL (Seitzer et al. 2022, beta 0.5; same optimum) was my answer and the pilot model was trained with it;
  WRONG as a default: once the augmentation is ramped in, the plain NLL is 11 % better (dl-p2 below): the
  trainer's default is the plain NLL again.
  (3) a heat-map head (integral regression: 32 x 32 soft-argmax per landmark + a global offset + log sigma;
  `net.NetHM`, 12.7 M parameters, ~0.1 s on two CPU threads) beside Wood's direct regressor (`net.Net`): the pilot
  is the heat-map one; the direct-vs-heat-map and plain-NLL comparisons are job dl-p2 (below, when it lands).
  Run: hm18, 200 epochs, batch 128, AdamW 1.5e-3 one-cycle, EMA; 89 min on NICO-TOP's 3070 Ti (27 s an epoch:
  ~180 img/s, bound by the augmentation in 10 CPU workers, not by the GPU). On this laptop's CPU: ~13-20 img/s.
- (a) HELD-OUT SYNTHETIC (600 samples of 2 unseen dressings, clean crops; error at the face, visible landmarks):
  mean 1.82 mm (2.16 px of 256), median 1.49 mm; hidden landmarks 3.13 px. By region (mean mm): lid margins 1.13,
  nose 1.21, orbit 1.30, brows 1.37, forehead 1.76, lips 1.81, mouth region 1.80, cheeks 1.99, chin 2.16, ears
  2.18, eyeball points 2.34, scalp / neck 2.84. SIGMA IS HONEST: mean d^2 / (2 sigma^2) = 1.07 visible, 1.03 hidden
  (1 = exact); 42 % of visible landmarks inside 1 sigma (39 % expected), 85 % inside 2 (86 %). Learning along
  the run (validation mean mm): epoch 16: 4.1, 48: 3.0, 96: 2.3, 128: 2.0, 199: 1.82: still falling slowly at the
  end. The 30-epoch run of the same data: 3.35 mm.
- (c1) THE KNOWN-HEAD BENCHMARK'S PICTURES (spikes/denselm/bench_lm.py: chinread's 11 dressed heads x 3 cameras: a
  body, dressing, light and cameras no training sample has; the same renderer), against the truth's own vertices:
  | view | ours, dense (sure = sigma < 2 mm) | ours, the 68 | MediaPipe, its 68 | calibration |
  |---|---|---|---|---|
  | front | median 1.40 mm, mean 1.65, p90 3.2 (93 % sure) | 1.36 (inner 1.19, jaw line 1.86, chin 3.0) | 4.00 (inner 2.79, jaw 12.7, chin 3.6) | 1.12 |
  | 23 deg | 1.67 / 1.92 / 3.5 (86 %) | 1.88 (inner 1.82, jaw 2.30) | 4.09 (inner 2.93, jaw 13.5) | 1.36 |
  | 72 deg | 2.02 / 2.22 / 3.8 (45 % sure: the far side is rightly unsure) | 2.68 | finds no face | 1.21 |
  Front, median mm per region: lids 0.70, nose 0.85, brows 0.83, orbit 0.89, forehead 1.35, mouth 1.38, lips 1.49,
  chin 2.05, cheeks 2.08. So on our own renderer the pilot is 2-3x closer to the true vertices than MediaPipe on
  the points both have, reads the side view MediaPipe cannot, and knows where it is unsure. BIASES it has: the
  chin region +1.5 mm low (front) and STRETCHED (x 1.06-1.17 vertically); the lips +1.0 mm (front) / +2.0 mm (3/4)
  to one side; and the CHIN'S WIDTH IS STILL NOT READ (widthbias.py: on the two narrow-chinned heads the chin
  region's landmarks come out 13-16 % too wide, on the wide ones right: where the skin has no feature the network
  answers with the average chin; every other region's width is within 3 %).
- (b) SIM-TO-REAL, by eye, one feature a tile (spikes/denselm/real.py; tiles /mnt/data/hifipushie/denselm/out/
  real_p1/<subject>_<view>_<feature>.png: picture | ours | MediaPipe, the 68 ringed in both; sheets for Joe
  workspace/human_renders/dl_p1_tess_1/2, dl_p1_garrett_paintings, dl_p1_garrett_good_1..3). BLUNT READS:
  - Tess front, EYE: our six lid points lie on her lid margins and both corners; the iris points on the iris;
    brow points on the brow's upper edge. As good as MediaPipe's here.
  - Tess front, MOUTH: corners right, the upper border right, the mouth line right; our LOWER border sits ~1.5 mm
    inside the lip (MediaPipe's is on it).
  - Tess front, CHIN / JAW: our "jaw line" 68 lie 6-8 mm ABOVE the visible chin edge, MediaPipe's on it: that is
    the DEFINITION, not an error: ours are the mesh's own landmark vertices (on the benchmark: 1.9 mm from the
    truth, MediaPipe's 12.7), MediaPipe's slide to the silhouette. A row of our chin points follows the chin's
    lower border. The chin's interior points are yellow (1-2 mm sigma), none green.
  - Tess PROFILE (a real 76 deg photo): lips, mouth corner, the chin's front and underside all on her profile
    line; the far side's points red (unsure), as they should be. MediaPipe's points there are a guess.
  - Garrett's PAINTING, front (a 126 px face, painterly): eyes, nose line (it leans, as painted), mouth on the
    features. It transfers to the painting.
  - The good Garrett set, front chin: lips right through the stubble; the chin's lower border followed.
  - Tess SMILE (teeth) and Garrett jaw_open: WRONG at the mouth, as predicted: the network has never seen an open
    mouth and "closes" it: the lower lip's points sit on the teeth, 4-6 mm high; it does say so (red / yellow).
    Upper face unaffected. This is the data gap (no teeth / mouth bag until gnmnative), not a transfer failure.
  Numbers on the real pictures (NOT against a truth: against the accepted fitted models, which were solved with
  MediaPipe's points): our 68 lie CLOSER to the fitted model than MediaPipe's own do: Tess front 1.7 mm (inner
  1.5) vs 3.4 (2.1); 3/4 1.8 vs 2.6; Garrett's paintings 2.9 / 3.2 vs 4.4 / 4.6; good Garrett front 2.4 vs 4.4.
  Our own sigma on real pictures is what it is on synthetic ones (lids / nose 0.8-1.1 mm, chin 1.4-1.9): the
  network is not alarmed by real skin.
- (c2) THE SOLVE WITH THE DENSE OBSERVATION (face_ruler DENSE on; dchain.py = chinread's chain, 3 calls from the
  male class mean; chinread's six known heads c d e f g h; bt.py: SHAPE errors after a similarity fit):
  | run | size error | face rms mm | lower face | chin | jaw body | jaw angle | abs. face rms (size in) | measures' rms |
  |---|---|---|---|---|---|---|---|---|
  | start (class mean) | 2.9 % | 2.62 | 3.13 | 2.42 | 2.94 | 4.17 | - | - |
  | N: today's solve | 6.0 % | 2.18 | 2.54 | 2.09 | 2.64 | 2.90 | 4.20 | 0.80 sd |
  | D: + dense | 1.9 % | 1.46 | 1.80 | 1.43 | 1.94 | 2.04 | 1.86 | 0.47 sd |
  | E: dense, NO MediaPipe anchors | 1.4 % | 1.51 | 1.82 | 1.45 | 1.98 | 2.01 | 1.74 | 0.46 sd |
  Face better on 5 of 6 heads, lower face on 5 of 6 (head g, the narrowest chin, worse: 2.87 -> 3.32). Per measure
  (RMS error mm, N -> D): chin_length 1.7 -> 1.0, chin_forward 1.2 -> 0.5, eyes_forward 3.1 -> 2.0, gonial_width
  2.4 -> 1.7, cheekbone_width 1.5 -> 1.2, jaw_width 2.7 -> 2.6, CHIN_WIDTH 4.0 -> 4.2 (unread, as above),
  mouth_width 0.7 -> 1.2 (worse: the lips' side bias). The HEAD'S SIZE is read now (6 % -> 1.9 % / 1.4 %:
  chinread's "heads come back 1-8 % large"): hundreds of landmarks through a perspective camera fix the distance
  the outlines left free. The solve settles (|dc| 9.4, 2.2, 1.3 on head c). MediaPipe's anchors add nothing once
  the dense reads are in (E = D).
  BUT on solvereads' other benchmark (sx: two identities, a = gg_A06's, b = garrett_a1's; face rms after 3 calls,
  abs.): a_x 1.63 -> 2.38 (jaw / chin 2.1 -> 4.5), a_n 2.01 -> 2.55, b_x 4.24 -> 3.55. Head a (a broad square jaw,
  jaw_square +1.8 sd) gets WORSE with the dense reads: the same average-chin answer, now pulling a correct outline
  solve off. So the dense read helps where the outline solve was poor and can hurt where it was already right:
  the chin / jaw landmarks need either honest (larger) sigmas there or better data (below).
  TRIED: leaving the chin / cheek / jaw-line / neck landmarks OUT of the solve (DL_REGIONS = lids, lips, orbit,
  brows, nose, mouth, forehead, ears): WORSE everywhere (the six heads' abs. face rms 2.72 against 1.86 with all
  of them; a_x 3.13 against 2.38): the lower-face landmarks carry the gain, and they are not what hurts head a.
  So the fix is not to drop them; what does hurt head a is not found yet (NEXT: who.py's split of the step by
  read group, with the dense reads in).
- PER-VIEW EXPRESSION (solvereads' failed term, expression="view", with the dense reads; face rms): a_x 1.92
  (term, no dense) -> 2.68 (term + dense); b_x 3.86 -> 3.26; a_n (the null) 2.59 -> 2.25. NO: it does not make the
  term work. The reason solvereads gave stands: when every picture shows the same expression, no landmark set
  separates it from identity; the dense read becomes useful for expression only with reference sets that VARY it
  (the brief's smile / jaw-open / eyes-closed shots), and those need the open-mouth training data first.
- ON THE REAL SETS (from each class-mean start, 4 calls, dense on; not scoreable, the accepted heads are no
  truth): Tess: |c| 11.3 (11.2 without), nothing forced, NO inconsistency flag (relax x1.0: her photos and the
  dense reads agree), table 20 / 26 (22), the profile camera 75.9 -> 68.7 deg; the solved head is 3.8 mm rms from
  tess_a1. Good Garrett: |c| 12.3 -> 9.8, table 15 -> 19 / 26, but every sigma raised x3.4 (the pictures' frown /
  squint against a neutral head, now read by 2,800 points), the "profile" camera 95.7 -> 66.2 deg (the picture IS
  a ~70 deg view: the dense reads see the turn the outline could not; tour tiles out/tour/dl_G_r?04/chin_jaw_v2:
  the overlay is one face with them, a doubled jaw line without); chin_width +8.0 (was +7.6: the slab stays).
  Paintings: settles, x1.5. Not judged on a judging sheet yet (no time): that is NEXT before any default changes.
- LEARNING CURVE and head comparison (job dl-p2, the same 2 held-out dressings, every run the SAME number of
  optimiser steps = 60 epochs of the full set; validation mean on visible landmarks):
  | run | training samples (dressings) | px of 256 | mm | sigma honesty (1 = exact) |
  |---|---|---|---|---|
  | heat-map head | 1,200 (4) | 4.11 | 3.41 | 1.73 (too sure: it has memorised 4 skins) |
  | heat-map head | 2,400 (8) | 3.70 | 3.10 | 1.23 |
  | heat-map head | 4,800 (16) | 3.04 | 2.58 | 0.83 |
  | DIRECT regression (Wood's head), ResNet-18 | 4,800 | 3.51 | 2.97 | 0.62 |
  | heat-map head, PLAIN NLL (beta 0) | 4,800 | 2.71 | 2.29 | 0.96 |
  (the pilot model = heat-map, beta 0.5, 4,800, 3.3x the steps: 2.16 px / 1.82 mm, 1.07.) So: each doubling of
  the data still buys 10-18 % at fixed steps (no plateau in sight at 4,800; the literature's is at ~100,000), more
  steps buy another 29 %, the heat-map head beats direct regression by 13 % at this size, and the plain NLL
  beats beta-NLL by 11 %: a plain-NLL rerun of the 200-epoch pilot is the cheapest next gain (89 GPU-minutes).

### The full-run plan (numbers from the pilot; nothing started; nothing billed without Joe's yes)
- HOW MANY SAMPLES: the literature's size is 100,000 images x 300 epochs (Wood 2021 / 2022, Hewitt 2024: "starting
  to plateau at 100,000"). Our curve at equal steps: 2,400 -> 4,800 samples takes the held-out error from 3.70 to
  3.06 px (-17 % per doubling, and the run that trains 3.3x longer on 4,800 reaches 2.16 px): we are far from the
  plateau in both data and steps. Proposal: TWO STAGES, deciding after the first: stage 1 = 30,000 samples of 100
  dressings (6x the pilot), stage 2 = 100,000 of ~300 if stage 1's benchmark numbers still fall.
- BEFORE the big render (code, a few agent-days; each is a measured gap of the pilot): (1) gnmnative merged:
  teeth, tongue, gums, GNM's eyeball as landmarks (set v2) and OPEN MOUTHS in the data (today 9 of the sampler's
  20 expression classes are left out); (2) WIDER IDENTITIES: the pilot draws the semantic sampler + a little
  noise (|c| ~7); the solve meets heads at |c| 11-13 with jaws at 2 sd: mix in GNM's own N(0, 1) prior and
  measure-space moves (chin / jaw width +-2 sd) so the unusual chin is in the data; (3) CHEAPER SAMPLES: the
  stage meshed at 2 mm (now 1 mm / 0.5 mm: ~400k vertices redrawn per TAA sample), 4-6 TAA samples, chunk = n,
  500 samples a dressing, labels from a z-buffer: target 0.6-0.8 s a sample on a 3070 Ti (measured today: 1.7 s
  idle, 2.9 s shared); (4) VARIETY the literature found to matter (Wood 2021: no hair / clothing = 4x the failure
  rate): strand or card hair instead of lock planks, beards, glasses, headwear, a collar / garment from the cloth
  tools, CC0 photo backdrops (Poly Haven HDRIs are CC0), hands / occluders; (5) the chin: more hard and raking
  light in the mix (relief is what tells a chin's width) and per-region sigma calibration from the benchmark.
- RENDER HOURS (all in, incl. the stage build per dressing):
  | | per sample | 30,000 | 100,000 |
  |---|---|---|---|
  | NICO-TOP as today, shared (measured) | 2.9 s | 24 h | 81 h |
  | NICO-TOP idle (measured, 16 -> 8 samples) | 1.7 s | 14 h | 47 h |
  | NICO-TOP after (3) (target, not measured) | 0.7 s | 6 h | 19 h |
  | this laptop, shared (measured) | 2.9 s | 24 h | 81 h (not advised: two other agents live here) |
  | enterprise (32 CPUs, no GPU known) | - | stage builds only (the CPU third of the cost), if the pipeline is split into build jobs and render jobs |
  | a rented 4090-class box through oxidegen (est., untested: EEVEE needs EGL there; 16+ vCPUs for the builds) | ~0.5-0.7 s | 4-6 h | 14-20 h |
- TRAINING HOURS: the pilot's trainer does ~180 samples a second on NICO-TOP (bound by the augmentation on 10 CPU
  workers, not by the GPU). 30,000 x 100 epochs = 3 M samples = 4.6 h; 100,000 x 150 epochs = 15 M = 23 h (8-10 h
  once the augmentation runs on the GPU or on 16+ workers). A ResNet-34 head-to-head costs the same again.
  On a rented 4090 with 32 vCPUs: ~600-1,000 samples a second: 4-7 h for the 100k run.
- STORAGE: 123 kB a sample as RGBA PNG at 320 px: 30k = 3.7 GB, 100k = 12.3 GB on /mnt/data/hifipushie/denselm
  (slim JPEG + alpha for uploads: 39 kB: 3.9 GB for 100k); stages are deleted after their render (190 MB each).
- COST OPTIONS: (A) local only (NICO-TOP + enterprise for builds): $0; 30k in ~1-2 days elapsed, 100k in ~4-6
  days as the machines are shared (2 days after (3)); the GPU is single and also the sculpt runner's. (B) rented
  through oxidegen (`where: "rented"`, one 4090-class box, oxidegen's cap $1.25 / h, typical $0.4-0.7): 100k
  render 14-20 h + training 4-7 h + slack x2 = 40-55 box-hours = $20-70; elapsed ~1.5 days; needs Joe's yes and
  a first unbilled smoke test of EEVEE on such a box. (C) mixed: render locally over a few nights, rent only the
  training (5-15 h: $3-20).
- WHAT IS RISKY: (1) the chin / jaw width: unread by the pilot and able to hurt a good outline solve; more data
  may not fix what a picture does not show; mitigations above, and the dense read should enter the solve with
  per-region sigmas, not as "truth". (2) SIM-TO-REAL IS UNMEASURED: every number above is on our own renderer;
  on real pictures I have tiles and agreement with fitted models, no ground truth. (3) open mouths depend on
  gnmnative. (4) the benchmark flatters us (same renderer, same skin system). (5) one shared GPU that failed
  once today. (6) EEVEE skin is not a photograph; the literature's renders are path-traced with scanned textures.
- WHAT I NEED FROM JOE: (a) go / no-go, and stage 1 only or both; (b) local-only (A) or a rented box (B / C) with a
  budget cap; (c) whether enterprise has a GPU, and its install; (d) A REAL-IMAGE EVALUATION SET: worth asking for,
  evaluation only, never training: without one, sim-to-real stays "by eye". Options: DAD-3DHeads' validation
  split (CC BY-NC-SA, gated: his decision; it would give landmark error on real photos by pose / expression /
  occlusion bucket, though on its own head topology (FLAME's, as far as I know: not re-checked): only the 68 map to ours), or better and ours: 3-5 people captured
  properly (a phone photogrammetry / multi-view session with a neutral and four expressions each), fitted
  offline, as a private ground-truth set; (e) whether an ImageNet-pretrained backbone is acceptable (Hewitt 2024
  uses one; faster and better from little data; ImageNet's terms are research-only for the images, the weights'
  status is the usual grey area): the pilot is from scratch and I would stay there unless he says otherwise.

## denselm stage 1 (2026-10-13; Joe's GO through the coordinator: stage 1 only, ~30,000 samples, our own machines,
## nothing rented; stage 2 NOT approved. Branch `worktree-agent-a2e75a7e571826c88`, main 94516bf merged in. Scratch as
## the pilot's + data_s1/ (the set), s1_nico.sh / s1_local.sh (render queues), out/sc_<tag>.txt (region tables))
STATE / NEXT: PARKED 2026-10-13; see "### STAGE 1 RESULT" near this section's end.

### What stage 1 must fix (the coordinator's list, from solvecams + heldoutnative with the pilot in the solve)
(1) a featureless jaw answered with the AVERAGE jaw (widths +3.5 mm on known heads, +5-7 on a narrow one); (2) a true
90 deg profile read as ~75-87; (3) front pitch +2-4 deg on male heads and under hair; (4) cameras sent to 2.7-3.4 m to
explain the width bias; (5) true-profile lids 4 mm off; (6) open mouths wrong; (7) dark skin under a hard top light weak.

### The generator (spikes/denselm/gen2.py; blender_gen.py binds teeth / tongue to their own GNM surfaces)
- GNM-NATIVE heads (attach "native": GNM's own head, eyeballs, teeth, tongue, mouth bag). The stage is built with the
  JAW HALF OPEN (jawOpen 0.55), so lips, teeth, tongue and bag are separate surfaces, and every sample re-poses it,
  closed mouths included (probe sheet out/p2probe.png, mouths out/p2mouth.png: the cavity and the teeth are there;
  the teeth are coarse and dull: 0.8 mm voxel, a flat colour).
- LANDMARK SET v2 (denselm.landmarks_v2, 623): the pilot's 570 skin vertices UNCHANGED and first, + per eye GNM's
  pupil centre and 8 iris-rim vertices (18), the upper / lower teeth's front arc (14 + 13), the tongue's upper front
  (8). A network's row count says which set it has (denselm.predict / by_count); face_ruler reads the skin rows as before.
- IDENTITY (a): c = class mean (the sample's sex x one of GNM's 4 ethnicity classes) + s z, z ~ N(0, I) over the 170
  head components, s ~ U(0.75, 1.0) (GNM's prior is s = 1; the pilot's samples had |c| ~7, these ~11-14); the
  deviation's part in the subspace of jaw / gonial / chin / cheekbone / skull width, lower-face height, chin length,
  nose length, skull top is x 1.5; 12 % of samples: one of those measures set to +-2..3 population sd; 15 %: s ~
  U(0.2, 0.5) (near the class means); components clipped at +-4.5. Teeth components ~ N(0, 0.8^2). Bodies 18-78
  years, both sexes (per dressing).
- VIEWS (b): yaw 55 % U(-110, 110) + 45 % N(0, 30); pitch N(0, 14) in +-35; roll N(0, 8); camera DISTANCE
  log-uniform 0.3-3 m, the lens that frames a 0.25-0.37 m crop there, off-axis crops on half; distance / yaw / pitch
  in meta.npz. The network gets ONE MORE OUTPUT ROW: log distance (+ its sigma).
- EXPRESSIONS (c): ARKit-named shapes solved on GNM's basis once (arkit_expr.npz, 41 shapes) + the sampler's
  classes: lower face 40 % neutral, 15 % smile with teeth, 7 % closed smile, 13 % jaw open, 10 % speech-like, 8 %
  other closed, 7 % a sampler class; upper face 50 % neutral, 10 % eyes closed, 8 % wide, 10 % squint, 10 % brows
  down, 10 % brows up, 2 % wink.
- APPEARANCE (d): tones Fitzpatrick 1-6 by class as the pilot; 15 % of samples under a HARD TOP light (a 1-5 deg sun
  at 60-88 deg elevation, a dark room); hair on 60 % of dressings (loose 36 %, loose + fringe 22 %, combed 27 %, crop
  15 %; loose hair may hang over cheeks and jaw: `face` 0..1), stubble / beard shadow on 60 % of men (amount to 1.4);
  training-time: backgrounds, clothes recolour, phone damage (noise, JPEG 25-95, downscale, blur) + NEW radial lens
  distortion (k +-0.12 on 25 %) and motion blur (15 %). NOT in: glasses (a stage geometry of their own: not cheap),
  strand hair (lock planks, as the pilot), real garments.
- CHEAPER (f), measured on 200 samples at 320 px:
  | | pilot | stage 1, this laptop | stage 1, NICO-TOP |
  |---|---|---|---|
  | all in, per sample | 2.9 s | 0.86 s (n 200), 0.94 s (n 300 with hair) | 1.08 s (n 300) |
  | Blender: render / re-pose / labels | 1.2-1.5 / 0.2 / 0.35 s | 0.25 / 0.07 / 0.07 s | 0.48 / 0.08 / 0.06 s |
  | stage build per dressing | 100-290 s | 90-140 s | ~120 s |
  What bought it: the stage meshed at 2 mm (eyes / mouth 1 mm, teeth 0.8 mm: 125k vertices against 400k), 6 TAA
  samples, one Blender start per dressing, and the POSE: humanfit.state takes 2 s a head on a native head (the
  neck is re-fitted per identity; 0.87 s a sample on 4 processes = the first run's largest cost), so each sample is
  posed from GNM's own bases at the stage's placement (0.01 s; against the exact build: face 0.13-0.24 mm rms, teeth
  0.1 mm, eyeballs 0.00 after a rigid move: the exact build also re-seats the head on the neck by 1-12 mm, a rigid
  move a picture cannot show; the head's move fades to 0 over the rings above the neck stitch, the body stands).

### The baseline to beat: the pilot at the truth on solvecams' heads (spikes/denselm/sc_table.py; out/sc_pilot.txt)
rms per axis, mm (bias x, y): FRONT (20 pictures, plain): lids 0.55, eyes 0.67, lips 0.93, brows 1.02, mouth 1.02,
chin 1.17, nose 1.20 (y +1.0), cheeks 1.55, forehead 1.91, ears 3.5, scalp / neck 5.0. 3/4 (8): lids 0.89, eyes
0.82, lips 1.00, mouth 1.10, nose 1.19, chin 1.61 (x +1.3), forehead 1.70, cheeks 2.27, ears 3.3. 72 deg (4): lips
0.95, nose 1.17, mouth 1.17, chin 1.37, lids 1.53, eyes 1.70, brows 1.92, cheeks 2.36, forehead 2.53. TRUE PROFILE
(4): lips 1.29, nose 1.52, chin 1.68, mouth 1.82, lids 2.83, eyes 2.99, brows 3.09, cheeks 3.49, forehead 3.84
(= solvecams' DENSE_REGION_SIG). Under the hard top light on dark skin (head e) the front nose is 1.49 (y +1.8) and
the chin y -1.7; with hair (head g) front ears 5.5 / scalp 8.7 (y -5.6 / -9.7: it puts them where a bald head's
are), cheeks 2.2, forehead 2.1. Its sigma there is too small by x1.5-3 (honesty 2.3-15 on forehead / ears / scalp).
WIDTH (front; lower-face width error, chin's x scale): a +0.0 mm / 1.00, b (narrow) +0.9 / 1.08, c (wide) +4.8 /
1.03, d +0.7 / 1.03, e -1.8 / 0.99, g (hair) +4.7 / 1.00. CAMERA its landmarks imply on the true head: front pitch
+1.6 deg (rms 1.9), true profile yaw +2.4 (rms 2.6) and distance +48 % (front distance is not determined by them:
-23 % .. unbounded).

### Landmark set v3 and the generator's second half (2026-10-13, after the coordinator's lips / nose finding)
The pilot's lip and nose-base points sat off the features on real phone portraits while MediaPipe's sat on them (Joe:
"mediapipe did a much better job, on the points that it did land"); my pilot line "MediaPipe's anchors add nothing once
the dense reads are in" was measured on our own renders only and DOES NOT CARRY to photos.
- denselm.landmarks_v3 (756; `current()`): v2 unchanged and first, + upper / lower vermilion border (the lip groups'
  edge against the skin: 18 + 18), the lip seam (the contact ring's two halves: 36), the nose's lower third (47: every
  exterior nose vertex below the tip's level by farthest-point picks: alar rims and grooves, nostril openings,
  columella, subnasale), the philtrum (14). Regions lip_border_upper / lip_border_lower / lip_seam / nose_base / philtrum.
- NO RE-RENDER: relabel.py recomputes a dressing's labels from its stored identity / teeth / expression / camera
  (gen2.make_poser + the Blender camera's formula; the old landmarks recomputed the same way land within 0.05 px of
  their stored pixels on all 37 dressings; a new landmark's visibility = its nearest old skin landmark's).
- Generator from dressing 37 on: 20 % of samples at phone distance 0.25-0.5 m; closed smiles mostly slight and lopsided
  (11 %); pressed / pursed / rolled / asymmetric mouths (10 %); nostril flare (8 %); lip colour strength 0.2-1.7.

### The 10k checkpoint (36 dressings = 10,800 samples; hm18, plain NLL, 60 epochs, 40 GPU-minutes; models/s10k/hm18)
- THE RUN WAS UNSTABLE: the plain NLL blew up several times (epoch losses +26, +160, +78; validation 6.6 -> 14 px at
  epoch 25, 5.5 at the end). Final run: a floor on sigma (0.5 px), gradient clip 2, beta-NLL 0.5, a lower peak rate.
  Held-out synthetic (3 dressings of the new, hard distribution): median 2.9 mm, mean 5.3 (front 3.9, 3/4 5.7, side
  5.9, rear 12.0); calibration 1.4 visible / 0.96 hidden.
- RENDERS, at the truth on solvecams' heads (rms per axis mm, pilot -> 10k; out/sc_pilot.txt, sc_s10k.txt; sc_cmp.py):
  front: lids 0.55 -> 0.60, eyes 0.67 -> 0.61, brows 1.02 -> 0.73, nose 1.20 -> 0.72, lips 0.93 -> 0.77, mouth 1.02 ->
  0.88, chin 1.17 -> 1.22, cheeks 1.55 -> 1.68, forehead 1.91 -> 1.64. 3/4: lids 0.89 -> 0.54, nose 1.19 -> 0.63,
  chin 1.61 -> 1.29, cheeks 2.27 -> 1.55. TRUE PROFILE: lids 2.83 -> 1.52, eyes 2.99 -> 1.97, brows 3.09 -> 2.15,
  cheeks 3.49 -> 2.59, forehead 3.84 -> 2.79; chin WORSE 1.68 -> 2.28. Dark skin under the hard top light (head e,
  front): nose 1.49 -> 0.57, chin 1.32 -> 0.62, cheeks 1.82 -> 0.90. Hair (head g, front): ears 5.5 -> 2.4, scalp
  8.7 -> 4.7, cheeks 2.2 -> 1.2; lids 0.50 -> 0.81, eyes 0.89 -> 1.22 worse. New regions front / 3/4: upper border
  0.75 / 0.70, lower 0.73 / 0.72, seam 0.81 / 0.77, nose base 0.71 / 0.59, philtrum 0.59 / 0.53. Its sigma is now too
  LARGE at the truth (honesty 0.2-0.8; the pilot's was too small: 1.5-15 on forehead / ears / scalp).
  Camera its landmarks imply on the true head: front pitch +1.6 -> -0.9 deg, true-profile yaw +2.4 -> -0.1.
  On the points both detectors have (front, mean error): lips outer 0.90 (pilot 1.21; MediaPipe 3.17), nose base 0.89
  (1.25; 3.39), mouth width +1.0 mm (pilot +2.2; MediaPipe -2.4). RENDERS CANNOT SETTLE ours against MediaPipe.
- REAL PHOTOS WITH SCAN TRUTH (spikes/denselm/real_gt.py + /mnt/data/hifipushie/denselm/real_gt.sh: the groundtruth
  agent's HSRD-100 sets (CC BY 4.0), two heads x six rig views; the same truth, visibility test and per-view 2D
  similarity as readmix's gmix.py, whose pilot row it reproduces; out/realgt_<tag>.txt). FRONT, per-axis rms mm RAW /
  after the similarity, pilot -> 10k [MediaPipe, readmix]:
  | region | pilot | 10k | MediaPipe |
  |---|---|---|---|
  | lids | 2.74 / 2.09 | 2.33 / 1.98 | eye contour 1.05 / 0.80 |
  | orbit | 2.96 / 2.34 | 2.07 / 1.78 | 1.84 / 1.59 |
  | nose | 2.07 / 1.53 | 1.28 / 1.08 (nose base 1.35 / 1.20) | 1.77 / 1.32 (alar 1.69 / 1.26) |
  | lips | 1.90 / 1.81 | 1.65 / 1.47 (borders 1.47 / 1.27, 1.49 / 1.42; seam 1.81 / 1.73) | 1.57 / 1.43 (border 1.74 / 1.59; seam 1.54 / 1.35) |
  | chin | 4.14 / 2.29 | 3.19 / 2.42 | 3.03 / 1.90 |
  | cheeks | 3.26 / 2.36 | 2.00 / 1.99 | 2.48 / 2.06 |
  | forehead | 3.75 / 2.78 | 2.75 / 2.39 | - |
  Mouth width (commissures), ours - truth: pilot +4.7 .. +6.0 mm, 10k +3.7 .. +4.4 (MediaPipe -3.0 .. +1.1); alar
  width +2.7 .. +5.0 (pilot +3.9 .. +6.6; MediaPipe +1.5 .. +6.5: the truth's alae may be narrow). Honesty after the
  similarity 0.5-1.0, lids 1.5. So: 15-40 % better than the pilot on real photos, level with MediaPipe on lips and
  cheeks, better on the nose, TWICE AS BAD ON THE LIDS, 4 mm wide at the mouth corners; and x2-3 worse than the same
  regions on our renders: THE SIM-TO-REAL GAP IS THE LARGEST ERROR, largest at the eyes.
  LOOKED AT (Tess front, out/real_s10k/tess_front_mouth.png, _eye.png): the mouth line, both borders and the nose base
  lie on her features (the lower border was 1.5 mm inside with the pilot); her inner canthus is ~1.5 mm too lateral
  (MediaPipe's is on it).
- IN THE SOLVE (solvecams' acceptance chains, set A, heads a-d, starts fitted / true / distance x2, dense on;
  /mnt/data/hifipushie/denselm/sc_suite.sh, letter s; out/suite_s.txt): face 1.11 (the pilot's suite d: 1.28), lower
  face 1.69 (1.79), jaw spread between starts 0.2-0.6 mm (1.1-2.7). Jaw width error: a -0.4 .. -1.7 (pilot +0.8 ..
  +1.9), b narrow +2.0 .. +2.2 (+5.1 .. +6.9), c wide -3.7 .. -5.4 (+1.8 .. +4.6), d -3.5 .. -4.6 (+1.3 .. +3.9): the
  one-sided +3.5 mm is gone, SHRINKAGE is left. Front pitch a, b within +0.5 deg (pilot +1.2 .. +3.1), c, d -1.0 ..
  -2.6; front distance c +24 .. +63 %.
- WHY THE WIDTH IS BIASED (widthval.py, 302 held-out synthetic near-frontal samples): the lower face's width as placed
  falls 1.1 % per +10 mm of true jaw width (6+ mm narrower than GNM's mean: +3.2 % = +4.1 mm; 6+ mm wider: -0.9 %),
  + 1.2 % on female dressings, + 0.4 % per e-fold of distance: the regressor's shrinkage toward the average jaw
  (~15 % of the deviation) where the picture does not pin it; not a labelling slide. What remains after better
  training belongs in the solve (the outline is the width read).
- THE DISTANCE OUTPUT: monotone but compressed (0.37 / 0.78 / 1.83 m read as 0.9 / 1.2 / 1.5 m; held-out log-slope
  0.17, median error 45 %): its loss was 1 row of 757 in a mean (x30 in the final run), and a face-normalised crop
  shows distance only as perspective: a near / far read at best, the metric distance is the solve's.

### Width shrinkage: toward the pooled mean or the class mean? (widthval.py + widthval_rows.py; /mnt/data/hifipushie/denselm/widthval.sh)
- MEASURE FIXED: the first widthval read the lower face's x-scale ABSOLUTE in the crop; on the s30k held-out dressings
  (N_s1033..39, 736 near-frontal samples, never trained on by s10k or s30k) the inner face (eyes, nose, mouth) is itself
  placed 5 % narrow, so the absolute number mixes a whole-face scale error into "width". Now: lower-face scale RELATIVE
  to the inner face's, robust (Huber IRLS) regression, medians per bin, a bootstrap sd.
- s10k on that set: median relative width error +0.3 % (robust sd 3.4 %); -0.91 % per +10 mm of true jaw width (true
  jaw 6+ mm narrower than GNM's mean: +1.7 % = +2.2 mm; 6+ mm wider: -0.8 % = -1.0 mm); per e-fold of distance -1.25 %.
- POOLED OR CLASS: the generator drew identities round 8 class means (sex x ancestry, eth_means; their jaw widths span
  6.6 mm, mostly by sex). Splitting the true jaw into (class mean - pooled mean) + (jaw - class mean): the slope on the
  within-class part is -0.92 % / 10 mm (bootstrap sd 0.09), on the class means' offset +1.5 (sd 0.65). Shrinkage to the
  POOLED mean would make both -0.92; they differ by ~3.8 sd. So the network shrinks toward the mean of the class it
  reads from the face (sex shows), not toward the pooled average; the nominal class label is right for ~95 % (sex) /
  ~60 % (ancestry) of heads, which only attenuates the second slope. Consequence: the remedy is not class-balancing;
  it is what the network can see of the jaw edge (and the solve owning width through the outline).

### Real photos, HSRD's HELD-OUT PEOPLE (spikes/denselm/real_hsrd.py; /mnt/data/hifipushie/denselm/real_hsrd.sh)
The groundtruth agent's labelled set (hsrdset.py; "dl3" labels = OUR v3 set projected from its GNM fit to each scan,
P.good = visible + on measured skin within 1.5 mm). Held out by subject (its split, fixed): HSR0023 (m 62), HSR0027
(f 41), HSR0102 (f 22): 6 poses, 108 photos (up to 6 per pose x view class; rear skipped), turned upright by the head's
roll (a late-bound closure first applied the wrong turn: 12-58 mm "errors"; fixed, and the crop checked by eye on one
photo). Studio flash, 2.0-2.4 m, 90-166 mm lenses, neutral faces, no beards. Per-axis rms mm RAW / AFTER the
detector's own 2D similarity [honesty], pilot -> s10k:
| region | front | 3/4 | profile |
|---|---|---|---|
| lids | 3.69 / 2.30 [1.6] -> 2.44 / 1.88 [1.0] | 3.13 / 2.48 -> 2.80 / 2.35 | 3.55 / 2.14 -> 3.44 / 2.05 |
| eyes | 4.79 / 3.16 -> 3.31 / 2.53 [1.5] | 3.94 / 3.12 -> 3.73 / 2.95 | 5.89 / 2.89 -> 4.59 / 2.75 |
| nose | 3.64 / 2.07 -> 2.40 / 1.52 [0.9] (nose base 2.21 / 1.49) | 3.41 / 2.31 -> 2.58 / 1.68 | 4.26 / 2.30 -> 3.45 / 2.02 |
| lips | 3.27 / 2.36 -> 2.25 / 1.86 [0.8] (borders 2.13 / 1.79, 2.19 / 1.99; seam 2.05 / 1.66) | 2.81 / 2.12 -> 2.80 / 1.98 | 4.33 / 2.48 -> 3.35 / 2.21 |
| mouth | 3.78 / 2.42 -> 2.42 / 1.99 | 2.83 / 2.27 -> 2.70 / 2.09 | 4.91 / 2.81 -> 3.86 / 2.41 |
| chin | 6.32 / 4.31 -> 3.91 / 3.00 [0.5] | 4.25 / 3.42 -> 3.33 / 2.83 | 7.29 / 5.12 -> 6.02 / 4.23 |
| cheeks | 6.42 / 4.57 -> 4.67 / 3.97 [1.5] | 5.58 / 4.80 -> 5.07 / 4.55 | 9.83 / 7.24 -> 6.66 / 5.43 |
| forehead | 5.56 / 4.51 -> 4.49 / 4.20 | 4.28 / 3.87 -> 4.70 / 4.23 | 9.54 / 5.64 -> 8.15 / 5.12 |
Front mouth width (ours - truth, 36 photos): pilot median +2.1 mm (-19 .. +8) -> s10k -0.8 (-11 .. +3); alar width
+2.9 -> +0.1. Distance read 1.1-2.0 m for a true 2.0-2.4 m (always short: the training's distances are log-uniform
0.25-3 m and phone-heavy). Honesty (s10k) 0.5-1.5: the sigmas are of the right size on real photos except cheeks /
eyes / brows (too small by ~1.2x) and chin (too large). Smooth-skin rows (cheeks, forehead) carry the labels' own
1-3 mm slide along the surface (the groundtruth agent's caveat): read edges (lids, nose, lips, mouth) first.
READ: s10k is 20-35 % better than the pilot on the inner face of people it never saw; on the edges it sits at 1.5-2.0
mm after the similarity, against 0.6-0.9 mm on our own renders: THE SIM-TO-REAL GAP IS STILL x2-3.

### STAGE 1 RESULT (2026-10-13 evening; report 3). The line is PARKED after this (Joe: likeness now comes from eyes / mouth / folds / textures)
Weights: models/s30k/hm18/model.pt (27,600 samples, 60 epochs, soft sigma floor, beta-NLL 0.5, lr 7e-4) and
models/s10k/hm18/model.pt (10,800 samples, plain NLL). Neither is in git. RECOMMENDED for the solve: s10k (below).
1. REAL PHOTOS, HSRD's held-out people (HSR0023, HSR0027, HSR0102; 9 poses, the SAME 161 photos for every row:
   real_hsrd.sh <tag> <weights> heldout 6 photos=s30k_e36; MediaPipe: mp_hsrd.py on the same photos, scored on readmix's
   MediaPipe -> GNM points by the same GNM regions; it found no face on 44, mostly profiles). FRONT, per-axis rms mm
   after the detector's own 2D similarity (raw in brackets):
   | region | s30k | s10k | pilot (108-photo subset) | MediaPipe |
   |---|---|---|---|---|
   | lids | 2.37 (3.07) | 2.11 (2.60) | 2.30 | 1.88 (2.41) |
   | eyes | 3.17 | 2.73 | 3.16 | 2.29 |
   | nose | 2.17 (4.81) | 1.99 (3.86) | 2.07 | 1.73 (2.39) |
   | nose base | 2.20 | 2.01 | - | - |
   | lips | 2.77 (5.10) | 2.46 (4.08) | 2.36 | 1.73 (2.10) |
   | lip seam | 2.52 | 2.17 | - | - |
   | mouth | 2.96 | 2.75 | 2.42 | 2.39 |
   | chin | 4.09 | 3.38 | 4.31 | 2.98 |
   | cheeks | 5.07 | 4.75 | 4.57 | 4.13 |
   3/4 and profile go the same way (s30k 5-20 % worse than s10k in every inner region). Mouth width (front, median):
   s30k -2.4 mm, s10k -1.7, MediaPipe -0.7. Honesty 0.6-1.3 for both (sigmas about right on real photos).
   VERDICT: s30k is WORSE than s10k on real photos, and both are behind MediaPipe on lids, eyes, nose and lips (by
   0.2-0.9 mm). Three times the synthetic data bought 0.0 on renders' held-out (3.1 vs 2.9 mm; different held-out sets)
   and lost 5-20 % on real faces: more of the same synthetic look fits the synthetic look better. (Confound: s30k also
   changed the loss (soft floor, beta 0.5) and the rate; a clean split would need one more run: not worth it now.)
2. WIDTH SHRINKAGE (widthval.sh; s30k's 7 held-out dressings, 736 near-frontal samples, relative to the inner face,
   robust): s10k -0.92 % per +10 mm of true jaw (sd 0.09); s30k -1.34 (sd 0.09): STRONGER, not weaker (narrow jaws
   +4.4 mm with s30k, +2.2 with s10k). Toward which mean: within-class slope -1.34 vs class-mean slope -0.13 (sd 0.64)
   for s30k; -0.92 vs +1.5 for s10k: the network shrinks toward the CLASS mean it reads off the face, not the pooled
   mean of the four sampled classes. Remedy is the solve (the outline owns width; the dense lower-face sigmas floored),
   not class balancing.
3. DISTANCE HEAD: held-out synthetic log-slope 0.25 (s10k) -> 0.52 (s30k), median error 60 -> 41 %; on the HSRD photos
   (true 1.6-2.4 m) it reads 0.65-2.6 m (s30k) / 1.1-2.0 m (s10k): still a near / far cue at best; the solve's distance
   prior must stay in charge.
4. IN THE SOLVE, against the SCAN'S SURFACE (gch.sh = the groundtruth agent's gchain.py with our src, 4 block_in_solve
   calls from readmix's pooled start rm_<k>_Lpooled00, cameras free; hsurf.sh = readmix's hsurf.py: mean |d| mm
   (signed), the solved identity with the scan's own expression; one chain each: differences under ~0.2 mm are noise):
   | head | dense | lips | nose | chin | cheeks | FACE |
   |---|---|---|---|---|---|---|
   | h23 (m 62) | start | 0.80 | 1.52 | 1.55 | 1.64 | 1.46 |
   | h23 | off | 1.07 | 1.05 | 1.19 | 1.18 | 1.20 |
   | h23 | on, s10k | 0.81 | 0.98 | 1.00 | 0.86 | 1.09 |
   | h23 | on, s30k | 0.89 | 1.05 | 1.14 | 0.87 | 1.21 |
   | h102 (f 22) | start | 3.54 | 1.61 | 2.02 | 1.42 | 1.91 |
   | h102 | off | 2.73 | 1.06 | 3.16 | 1.57 | 1.54 |
   | h102 | on, s10k | 1.58 | 0.69 | 1.12 | 1.26 | 1.05 |
   | h102 | on, s30k | 1.34 | 0.57 | 2.15 | 0.96 | 0.86 |
   Dense ON helps both heads with s10k (face 1.20 -> 1.09, 1.54 -> 1.05; h102's chin 3.16 -> 1.12); s30k is better
   on h102 (0.86) and no help on h23 (1.21). (Off = main's reads: identical to readmix's "main's reads" rows: the
   chain is deterministic.) For scale: two scans of one person disagree 1-4 mm vertex to vertex; surface numbers have
   no such floor. Records: out/hsurf_*.json, logs/h*_*.log; models dl_h23_* / dl_h102_* in main's workspace.
5. THE REALISM GAP, recommendation (do not render more of the same look; stage 2 as specified would not help):
   (a) FIRST, cheap: train / calibrate on what is real and licence-clean NOW: the HSRD TRAIN-split people (7 subjects,
   20 poses, ~230 head photos with v3 labels, CC BY 4.0, already pulled by the groundtruth agent) as a small real term
   mixed into fine-tuning (5-10 % of batches, labels weighted by the set's own quality, edges only: lids, nose, lips,
   mouth), scored on the held-out three. Cost: ~0.5 day agent work + 1 GPU-hour on NICO-TOP; no download. Risk: it
   learns this studio (white cyc, flash, 2.2 m): read the held-out numbers per region before believing it.
   (b) SECOND: real skin on synthetic heads: the projskin agent's de-lit, atlas-space skin (any GNM head shares the
   atlas, so one de-lit texture dresses every identity) from the HSRD train-split scans' 16k textures + Tess; 10-20
   skins, jittered in tone, replacing the procedural skin on ~1/3 of new samples (~10k samples = 5-6 h on our two
   machines) + a fine-tune of s10k (1-2 GPU-hours). Cost ~1-1.5 days agent work; needs the coordinator to arrange the
   groundtruth agent's scan textures (no new download). This attacks the lids / lip edges directly (real lash lines,
   lid margins, vermilion edges), where the gap is largest.
   (c) Stronger randomisation alone (sensor noise, JPEG, sharpening, flash, long lenses): cheap but s30k says more
   variation of our own look does not transfer by itself; only as part of (b).
   And meanwhile: MediaPipe is the better reader on real photos for lids / eyes / lips / nose; the dense network's
   value is the jaw / chin / profile, where MediaPipe has nothing (and the solve gains: section 4).
STATE: PARKED (2026-10-13). Branch merge-ready: main ac3e191 merged in; tests one per process through bin/slot with
HIFIPUSHIE_ASSETS set: test_denselm 7, test_toolsets 8, test_face_ruler 4, test_readmix 12, test_solvecams 3: all
passed, 0 skipped. Nothing running.
NEXT (if the line is resumed): (a) then (b) above, scored first on real_hsrd.sh (held-out three, photos=s30k_e36) and
hsurf on h23 / h102 / h27; set HIFIPUSHIE_DENSELM to s10k where dense is used.

### RESTART (stage 1; read this first). FINAL STATE: PARKED, see "### STAGE 1 RESULT" above; the training below is DONE
(models/s30k DONE 17:44). Earlier state (2026-10-13 14:55): rendering STOPPED (data_s1/STOP_NICO + STOP_LOCAL exist; no queue running). The stage-1 set is
COMPLETE for training: /mnt/data/hifipushie/denselm/data_s1/ = 92 dressings x 300 = 27,600 samples, all labelled with set
v3 (756 columns; checked: none incomplete, none on an older set). Final training run `s30k` on NICO-TOP in resumable
segments (below; status in models/s30k/STATUS). FIRST TRY DIVERGED (models/s30k_diverged1: lr 1e-3; epoch losses
-0.36 .. 2.5 then 148 at epoch 9, 53 / 52 / 47 in segment 2; held-out median 5.5 mm at epoch 5 -> 14.1 at 12; cancelled
15:29). CAUSE: the sigma floor was a hard clamp in the loss: no gradient below it, so a landmark whose sigma sank under
it could never raise it and its d^2 / sigma^2 term (thousands on a hard sample) dominated. FIX (net.soft_floor, in the
network so loss / evaluation / export agree): sigma^2 = exp(2 ls) + exp(2 * -5.5); + a SPIKE GUARD in train.py (a batch
whose loss is over the running loss + 8 mean deviations is not stepped on; counted per epoch as "skipped"); peak lr
7e-4. Second try started ~15:35; ~25 min a segment (93-110 s an epoch on 25,500 train / 2,100 val samples = 7 held-out
dressings N_s1033..39, + the 1.2 GB transfer) -> DONE expected ~17:45.
  Progress (models/s30k/STATUS): e0 back 15:57 (held-out median 8.0 mm: worse than epoch 5's 4.5 at the peak rate,
  as s10k did mid-run), e12 back 16:23 (4.2 mm, calibration 1.09), e24 submitted 16:23.
  Side runs done while it trains: real_hsrd s10k on the TRAIN-split people (230 photos: raw 4-9 mm, 1.7-2.2 after the
  similarity on the inner face; not a score: those people stay for calibration / fine-tuning); s10k in the solve on
  heads e (dark skin, hard top light) and g (hair): face 1.27-1.29 / 1.15-1.19, lower face 1.52-1.64 / 1.23-1.32,
  jaw width e -3.5 .. -4.7 (narrow read; its class-mean start -5.2), g -0.5 .. +0.2; front pitch e -2.5, g +2.4 deg;
  jaw spread 0.7 mm (out/suite_s_eg.txt). The 10k model is models/s10k/hm18/model.pt. Stage 2 NOT approved,
nothing rented or billed; HSRD is the groundtruth agent's (read-only, do not download more).
NEXT, in order: (1) watch s30k to DONE (or resume it); if a segment's "skipped" climbs or the held-out median rises
two segments running, stop (cancel the batch) and say so: do not loop; (2) evaluation with REAL-PHOTO numbers first: real_gt.sh s30k,
then sc_table + sc_cmp against s10k / pilot, held-out synthetic per bin (models/s30k/hm18/val.json), widthval.py (the
shrinkage slope before / after; done for s10k, see the section above: rerun widthval.sh s30k), the distance
head (widthval prints its log-slope; realgt prints distance read vs true), sc_suite (letter t), Tess tiles; (3) the
notes; (4) report 3 to the coordinator: real-photo numbers leading, width shrinkage, distance head, the realism-gap
recommendation with cost (projskin de-lit skin; HSRD subjects held out whole as validation, maybe fine-tuning;
stronger randomisation).

THE TRAINING JOB (spikes/denselm/train_seg.sh; the copy that runs: /mnt/data/hifipushie/denselm/train_seg.sh):
- A DRIVER on THIS laptop (setsid nohup: outlives the agent's shell) submits one compute job per segment of 12 epochs
  through the oxidegen bundle route in direct mode (the laptop serves the 1.2 GB data tar (data_s1_slim) and receives the outputs: the
  driver must stay alive while a segment runs). Each segment's job ends with models/s30k/hm18/state.pth (weights, EMA,
  AdamW, OneCycle schedule, scaler, epoch, log; also written every 3 epochs inside the job) + model.pt / weights.pth /
  val.json of the EMA so far. COPYING BACK IS AUTOMATIC: the driver unpacks each segment's outputs into
  /mnt/data/hifipushie/denselm/models/s30k/ (and keeps model_e<k>.pt per segment).
- START / RESUME = the same one line (resumes from the last state.pth the driver has; data list, args and code commit
  are fixed at the first call in models/s30k/run.txt, dirs.txt, commit.txt; a lock stops two drivers):
  /mnt/data/hifipushie/denselm/start_s30k.sh   (= this line; the tool refuses it typed directly in this worktree:)
  setsid nohup /mnt/data/hifipushie/denselm/train_seg.sh s30k 60 12 "name=hm18 arch=hm18 bs=128 lr=1e-3 workers=11 val=0.08 beta=0.5 ramp=0.25 dist_weight=30 clip=2.0" >> /mnt/data/hifipushie/denselm/out/train_s30k.log 2>&1 < /dev/null &
- CHECK: `cat /mnt/data/hifipushie/denselm/models/s30k/STATUS` (one line per segment submitted / back / FAILED; a DONE
  file at the end); live epochs: `grep -o 'step: {"epoch[^}]*' /mnt/data/hifipushie/denselm/out/train_s30k.log | tail -3`;
  driver alive: `pgrep -af "[t]rain_seg.sh"`; batches on the fleet: `OXIDEGEN_TOKEN=$(cat ~/.config/oxidegen/hifipushie-cloth-token)
  python3 /home/joe/dev/oxidegen/scripts/bundle/bundle_client.py list` (batch names dl-s30ke<epoch>-HHMMSS; `status <batch>`).
  DIED = a FAILED file, or no driver process and no DONE: run the START line again (a dead segment loses at most its
  own 12 epochs). A job that dies near its start: tell the coordinator the exact time, do not loop resubmits. A hung
  segment: `bundle_client.py cancel <batch>`; the driver then records FAILED; rerun.
- The machine: NICO-TOP (GPU), reached only through the bundle route (no ssh). Shared with S0urc3 and other agents: one
  training job at a time, no render batches beside it.
- EVALUATION (on this laptop; W = /mnt/data/hifipushie/denselm/models/s30k/hm18/model.pt):
  REAL PHOTOS FIRST, HSRD's HELD-OUT PEOPLE: /mnt/data/hifipushie/denselm/real_hsrd.sh s30k W  (-> out/realhsrd_s30k.txt;
  beside realhsrd_s10k / realhsrd_pilot: same photos, ~100 of them over the five held-out poses)
  width: /mnt/data/hifipushie/denselm/widthval.sh s30k W   (beside out/widthval_s10k.txt)
  real photos: /mnt/data/hifipushie/denselm/real_gt.sh s30k W   (-> out/realgt_s30k.txt; beside realgt_s10k / realgt_pilot)
  renders at the truth: HIFIPUSHIE_DENSELM=W WS=main /mnt/data/hifipushie/denselm/run.sh spikes/denselm/sc_table.py s30k; then run.sh spikes/denselm/sc_cmp.py s10k s30k
  width / distance: /mnt/data/hifipushie/normals_venv/bin/python spikes/denselm/widthval.py W /mnt/data/hifipushie/denselm/data_s1 <val dressings = the last 8 % of models/s30k/dirs.txt>
  solve: /mnt/data/hifipushie/denselm/sc_suite.sh t W "a b c d e g" "fit tru dx"
  Tess tiles: HIFIPUSHIE_DENSELM=W WS=main /mnt/data/hifipushie/denselm/run.sh spikes/denselm/real.py s30k tess
- VENV / TORCH: on NICO-TOP the torch venv is $OXIDEGEN_CACHE/dl_torch_v2, built by the bundle's SETUP step
  (remote_train.sh): uv venv py3.12 + numpy pillow + torch from https://download.pytorch.org/whl/cu124 ONLY. Locally the
  torch venv is /mnt/data/hifipushie/normals_venv (HIFIPUSHIE_NORMALS_VENV; denselm.predict runs through it).

WHAT A FRESH AGENT WOULD GET WRONG:
- Torch from PyPI (CUDA 13 wheels): NICO-TOP's driver has no CUDA 13 -> cuda False, CPU training. Use cu124 (dl_torch_v2).
- A venv made INSIDE a job: the sandbox cannot write uv's cache or the machine cache -> build it in the bundle setup.
- DataLoader workers hang in the sandbox (/dev/shm not writable) -> train.py's numpy `collate`; keep it.
- remote.sh / remote_train.sh ship an archive of a COMMIT (HP_REF, else HEAD): uncommitted code does not travel.
- Big job folders: the 690 MB raw set coincided with NICO-TOP's NVMe failure; ship data_s1_slim (JPEG + alpha, slim.py).
- Plain NLL blows up on this data (loss spikes, val 6.6 -> 14 px): sigma floor (net.gnll clamp), clip 2, beta 0.5.
- The distance row is 1 of 757 in the loss mean: dist_weight 30 or it learns nothing.
- Label sets by column count: 588 = v1, 623 = v2, 756 = v3 (denselm.by_count); old-set dressings are relabelled with
  relabel.py (no render), never mixed in.
- Shell: version-control commands combined with cd / heredocs / loops are refused in this worktree (plain commands
  only); `pgrep -f pattern` matches its own shell (use "[t]rain_seg.sh"); foreground sleeps are blocked (until-loops).
- Do not open: the held-out Garrett photos, refs_lt19 / the wife's sets, out/real_fam/.
