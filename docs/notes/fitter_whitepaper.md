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
