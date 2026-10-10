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
