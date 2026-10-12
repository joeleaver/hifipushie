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

## denselm (2026-10-12, "denselm" agent, branch `worktree-agent-a2e75a7e571826c88`; Joe: "Ok, that's a big chunk of work. Let's go for it.")
Our own dense-landmark network, trained only on synthetic renders of GNM heads from our own pipeline. This round is
SCOPE + PILOT. Scratch DURABLE in /mnt/data/hifipushie/denselm: run.sh <script> (capped, this worktree's src, its own
workspace ws/; WS=main for main's), submit.sh <batch> <ram> <timeout> "<gen.py args>".. (offload jobs, one dressing
each), data/ (samples), out/ (sheets, logs); code: src/hifipushie/denselm.py (the landmark set, inference),
spikes/denselm (gen.py + blender_gen.py: the generator; job_gen.py; train.py + net.py; peek.py / augpeek.py).

### State
STATE / NEXT: design written; generator built and running (local + NICO-TOP); pilot data / training / evaluation
below as they land.

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
- THE LANDMARK SET (src/hifipushie/denselm.py `landmarks()`, version 1): 595 GNM skin vertices + 18 eyeball points
  = 613. Skin: farthest-point sampling on GNM's template restricted to `skin_exterior` vertices the one human mesh
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
  that as they do for the anchors.
