# hifipushie notes: measuremodels

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

## Measurement models (2026-10-09, "measuremodels" agent, branch `measuremodels`)

Joe: "are we still looking at measurement models and trying some out?" Until now only MediaPipe had been tried. A
licence-checked survey, then trials on the refstudy truth set re-rendered SKINNED. Code `spikes/measuremodels/` (mm.py
= ground truth per picture; mkset.py + bl_skin.py = the set; score_geo.py = a dense model in its own terms; dense.py =
depth / normals as calibrated evidence; score_mesh.py + tmesh.py = generated meshes; fits.py / fits2.py = the method
table (fitlib's MAP); widths.py, lens.py, macro_table.py, garrett_fit.py, pics.py; remote/ = inference scripts).
Scratch DURABLE in /mnt/data/hifipushie/measuremodels/ (run.sh <script>; gpu.sh / rjob.sh = the rented box; survey.md
= the survey with a source per licence claim; set/ = pictures; pred/<model>/ = outputs; out/fits.json = every row with
its fitted identity; trellis/ = Oxidegen's meshes as arrays). Sheets `workspace/human_renders/mm_01_normals.png`,
`mm_02_trellis.png`, `mm_03_garrett_trellis.png`. Module that came out: `src/hifipushie/humannormals.py`.
- The set: the 10 truth heads through their own cameras + 20 other heads (calibration: front / tq / profile / tq2),
  Blender EEVEE: subsurface skin in 8 tones, lips, brows, irises, pores, stubble on some, a hair stand-in on some, sun
  + sky, coloured backgrounds. They read as CG busts, NOT photographs: every number below is "on renders". The
  baseline holds there: detector 478 + prior, front + tq: face 2.53 / 2.34 mm (S in-model / O out) with the clay
  table, 2.45 / 2.39 with the table recalibrated on skinned renders (`calib_skin.npz`; the two tables' definitions
  differ by 1.0 mm median); + read 2.13 / 2.20; mean head 3.61 / 3.05. MediaPipe finds 0 of 20 skinned profiles.
  A looser scatter cut (4 mm instead of 2.5) is a free 0.1 mm (2.36 / 2.33, chin 3.73 -> 3.39): worth taking.
- A second score: distance from each fitted vertex to the TRUE SURFACE (fits.surf_score). Vertices slide along a skull
  or a jaw without the shape being wrong, and dense evidence can't stop that: judge dense methods by it. Mean head
  1.75 / 1.66 face, detector MAP 1.28 / 1.40, + read 1.10 / 1.17, the basis's reach 0.24 / 0.80.
- "Does it see THIS head" = correlation and gain of (model - mean head) against (truth - mean head). Every model
  exaggerates or mutes: use it through a gain calibrated on other heads, with what it leaves as sigma, or not at all.
- SURVEY (licences of code AND weights; details + URLs in survey.md). Usable commercially: DAViD (Microsoft, MIT,
  synthetic data only, ONNX), MoGe-2 / MoGe-3 (MIT), Depth Anything V2 Small and DA3 Small / Base / Mono-L / Metric-L
  (Apache; the larger ones CC-BY-NC), MapAnything-apache, VGGT-1B-Commercial (gated), Marigold v1-1 (OpenRAIL++-M),
  MediaPipe (+ selfie multiclass), BiRefNet (MIT), SAM 2.1, BlazeEar / Ear_Landmarker (Apache; labels seeded from an
  iBUG-trained model), TRELLIS.2 (MIT model; nvdiffrast in its texture path is NVIDIA non-commercial; DINOv3's licence
  unverified), Hi3DGen, TripoSG. NOT usable: Depth Pro (Apple research licence), Sapiens v1, DSINE, UniDepth, DUSt3R /
  MASt3R / Pi3, every FLAME / Basel reconstructor (DECA, EMOCA, MICA, SMIRK, Pixel3DMM, 3DDFA), InsightFace packs,
  OpenFace, dlib-68, YOLO (AGPL). UNCLEAR: Sapiens2 (no non-commercial clause, but forbids "biometric processing" and
  lets Meta audit: a legal read before any use beyond a bench test), face-alignment / SPIGA / RTMPose (research-only
  training data), StableNormal / Lotus, Hunyuan3D (excludes EU / UK / Korea). No profile-landmark model with a clean
  licence exists; Microsoft's 703 dense landmarks: no release.
- TRIED, in the fit (face mm vertex S / O | to the true surface S / O; front + tq unless said):
  baseline 2.45 / 2.39 | 1.28 / 1.40.
  - DAViD NORMALS, calibrated per vertex (gain ~0.5, sigma x4): 2.21 / 2.13 | 1.08 / 1.09; profile 2.33 -> 2.07 / 3.07
    -> 2.74; chin 3.73 -> 2.65; jaw 4.12 -> 3.65 / 4.40 -> 3.83 (surface 2.41 -> 1.76 / 2.79 -> 1.72); front only 2.33 /
    2.14; + read 2.06 / 2.03 | 1.02 / 1.04 (read alone 2.13-2.20 / 2.12-2.20: the simulated reader's noise is seeded
    by Python's hash, rows with a read move +-0.05 between runs). Stable for sigma x3..x6; at x1 it overfits (0.7-0.85
    sigma rms) and gets worse. Macros it sharpens (error in sigmas): jaw_width 0.92 -> 0.77, chin_projection 1.30 ->
    0.92, under_chin 0.94 -> 0.76, bridge_height r 0.75 -> 0.97, brow_ridge r 0.63 -> 0.84, eye_depth r 0.38 -> 0.78,
    cheek_fullness r 0.64 -> 0.87, lip_projection 0.92 -> 0.61. In its own terms: angle to the true normal chin 5.8
    deg (mean head 9.0), cheeks 6.4 (7.7), jaw from tq 4.0 (5.6). = ABOUT ONE CHARACTER READ, measured, and it adds to
    one. Nothing on cranium / ears / neck. 14 s a picture on a 128-core CPU box; ONNX.
  - Sapiens2 normals (1B; FLAGGED licence, run as an upper bound only): 1.92 / 2.19 | 0.90 / 1.01; raw angles chin
    4.5, brow 3.7, cheeks 4.2, nose 5.4 deg, correlations 0.8-0.9 at gain 0.7-0.95. What better normals would buy:
    another ~0.15 mm of surface. Do not ship.
  - MoGe-2: normals weaker than DAViD's (2.45 / 2.16), depth worse than the mean head's (3.7 vs 2.2 mm rms on the
    face). Marigold normals: as MoGe's (14.3 deg on the face vs DAViD 11.4, mean head 10.8). Not wired.
  - DEPTH from any model (MoGe-2, DAViD, Depth Anything V2 Small, MapAnything two-view) is DEAD as evidence: per
    feature it correlates (nose tip from a front picture: DAViD 0.86, MoGe 0.7-0.9 at gain 0.5; brow 0.7-0.8; chin
    0.3) but the field carries low-frequency warp: dense depth rows 2.9-3.5 mm (harmful), a few feature depths 2.4-2.5
    (nothing). MapAnything-apache on front + tq pairs of these busts: 9-12 mm depth error (untextured CG: maybe
    unfair, but nothing to build on).
  - MoGe's LENS: 0.81 x true front (0.69 turned), scatter x1.27, correlation 0.74 over 35-105 mm. A better prior than
    70 mm +-40% for anything that needs one (points don't).
  - XR Blocks' MediaPipe <-> GNM table is THIRD-PARTY (ported from edualvarado/gnm-webcam-puppet, nearest vertices,
    "tuned on synthetic faces"): no real-photo provenance. Its vertices agree with our front table to 1.4 mm median
    (p90 3.8, a few 13-57 mm). Fits: front only 2.56 / 2.49 (ours 2.51 / 2.40), front + tq 2.99 / 2.79 (one table for
    all views), with its reference-cloud offsets 3.17 / 2.78. Keep ours.
  - WIDTHS from a front picture (widths.py: any matte cut at rows set by the detector's points, in pupil distances):
    the mask is not the problem (0.5%); a silhouette can give face_length (r 0.91 with the true macro), chin_height
    0.73, jaw_width 0.71, chin_width 0.7; NOT cheekbone / face width (ears, hair) or neck (collar). refstudy2 found
    silhouette rows in the fit hurt; as regressed macros they help. Garrett: lower jaw row +2.1 sigma, mouth row +0.8.
- GENERATED MESHES (TRELLIS.2-4B through Oxidegen's mesh_reference; one picture -> one mesh; +Y up, +Z front, scale
  per image; 25 meshes, 10 of the first batch died on Oxidegen's watchdog and were rerun). In their own terms (ICP on
  the TRUE face; surface offset mm, mesh vs mean head; correlation of deviations): from a FRONT picture face 1.64 vs
  1.78 (0.70), jaw 1.46 vs 2.94 (0.91), cheeks 1.54 vs 1.95 (0.79), chin 2.60 vs 3.52 (0.73), cranium 4.6 vs 5.1
  (0.53; bald heads only), neck 6.2 vs 7.2 (0.87), ears 3.1 vs 3.6; features: nose tip 2.9 vs 4.8 (0.81), cheekbone
  1.2 vs 3.4 (0.95), neck side 7.1 vs 11.4 (0.94), chin 4.4 vs 5.5 (0.67). From a THREE-QUARTER picture better:
  chin 1.7 vs 5.4 (0.95), jaw angle 1.7 vs 3.3 (0.87), brow 1.15 vs 2.15 (0.92), neck side 4.8 vs 11.4 (0.97). From a
  profile (3): the profile it was shown, to ~1 mm, and a plausible invented front. Gains 0.5-0.8: it exaggerates.
  It sculpts invented detail (folds, wrinkles, hair strands) and reads a hair stand-in as hair.
  IN THE FIT it does NOT pay like its own terms promise: dense point-to-surface rows (20 rounds of re-registration:
  4 rounds do not converge; ears left out; gains and sigmas per region) front + mesh: vertex 2.68 / 2.36, surface
  1.33 / 1.24 (baseline front only 1.38 both), jaw surface 2.2 -> 1.9; without gains or tighter it HURTS (2.9-3.5).
  Read at features with leave-one-out gains: 2.27 / 2.62. With normals + read: no better than normals + read. With
  the mesh laid on the TRUE head (not available) the O heads' surface jaw goes 2.8 -> 1.7: registration to an
  unknown head is half the loss; a PERFECT surface through the same pipeline gives only 1.2 / 2.1 vertex, 0.45 / 0.75
  surface. The one thing only the mesh measures: neck_width (macro error 1.61 -> 0.76 sigma, r 0.42 -> 0.88). So:
  not evidence for the face; a measured NECK, a second opinion on jaw / chin from a three-quarter picture, and a
  synthesised profile for a person or an LLM to look at (mm_02, mm_03). Costs a GPU job ($0.03-0.08, 1-5 min).
- `humannormals.py` (+ `david_normals_gnm.npz`, tests/test_humannormals.py): `predict(image)` (DAViD ONNX in its own
  venv, $HIFIPUSHIE_DAVID, default /mnt/data/hifipushie/measuremodels/david; cached), `rows(normal, V, IB, c, cam,
  cls, hide=, only=)` -> (A, y, info) linear evidence about the current head, identical to the study's rows. NOT yet
  called by humanfit_map (garrett3 owns it; the 3-line hook is in the module's docstring terms: H += A.T @ A, b +=
  A.T @ y once per round for a view with normals). Hair must be masked (`hide`). Calibrated on RENDERS only.
- Garrett (study fast lane, GNM frame; out/garrett_fits.json): points vs + the front photo's normals: brow_ridge +1.5
  -> +0.7, eye_depth +1.4 -> +0.9, chin_height +1.3 -> +1.0; stable: eye_height -1.4 (hooded), philtrum +1.2, thin lips
  -0.9, mouth_width +0.7, nose_projection +0.7. On the desk PAINTING DAViD's normals are brush strokes: front only.
  His two meshes are low in detail (the head is a small part of a suited bust) but read as him; against the fitted
  head the front mesh says chin -7 mm / jaw -5..-8 (smaller) and neck +12; the desk mesh nose +5: they disagree with
  each other beyond their own noise on a truth head: look at them (mm_03), don't fit them.
- Not run: ear models (BlazeEar / Ear_Landmarker), MoGe-3, DA3, Hi3DGen, a second TRELLIS seed (repeatability by
  region), DAViD on PHOTOGRAPHS (the calibration's real test), a hair matte from selfie-multiclass feeding `hide`.
- Dead ends, so nobody re-tries: monocular or two-view DEPTH as fit evidence (any model); dense generated-mesh rows
  without gains; the XR Blocks table for turned views; MapAnything on untextured busts; Marigold / MoGe normals where
  DAViD's exist; silhouette widths for cheekbones or neck.

### Measurement models, photographs (2026-10-09, same agent; Joe on mm_01: "visually, the Marigold model looks amazing", DAViD "noisy / framed")

Does the render calibration transfer to photographs? Scripts in spikes/measuremodels/: photo.py (head | crops | photo |
renders | pairs | depth | sheet: a model's normals against a head fitted WITHOUT normals, g3_f through its human_refs
camera, with the crop's off-axis view taken out; the calibration's own quantities gain / corr / left with the same code
on photo, renders and scan), lps.py (prep | render | stats | gains | depth | sheet) + bl_scan.py, lps_fit.py,
david_local.py, remote/run_marigold.py <src> <out> v11|lcm. Sheets human_renders/mm_04_photo_normals.png,
mm_05_scan_normals.png. Scratch as before (/mnt/data/hifipushie/measuremodels: lps/, out/photo_all.txt, pred/).
- A head with TRUTH and real skin: Lee Perry-Smith's scan (Infinite-Realities, CC BY 3.0; from three.js's examples:
  17.7k triangles, photographed albedo, its normal map), path-traced in Cycles (SSS), 3 views x 2 lights, truth = its
  shading normals rendered through the same cameras; laid on GNM's mean head by tmesh.align for regions. NOT a
  photograph and ONE head (eyes closed), but real pores, stubble, brows and a real face's relief. glTF's v is flipped
  against Blender's (the first render had lips on the chin).
- Normals on the scan, trusted regions (forehead, cheeks, nose), deg from truth after one global rotation | gain | corr
  of deviations from the mean head; the same on our skinned renders' 10 truth fronts in brackets:
  DAViD 8.1 | 0.81 | 0.80 (8.0 | 0.50 | 0.56); Marigold v1-1 10.3 | 0.65 | 0.72 (9.6 | 0.33 | 0.40); Marigold LCM 11.6 |
  0.63 | 0.66 (10.6 | 0.30 | 0.36); MoGe-2 12.7 | 0.59 | 0.60 (9.6 | 0.37 | 0.45); mean head 13.7 (8.2). DAViD wins in
  6 of 6 pictures. Every model reads real skin much better than our plastic renders (Marigold most: Joe's eye was
  right that the render numbers under-rated it), so the render gains are ~1.6-2x too LOW for real skin: the
  render-calibrated DAViD normal is 9.5 deg from truth, raw 8.1. Marigold carries a ~5 deg global tilt (raw 11.4).
- End to end on the scan (lps_fit.py: detector points front + three-quarter, then + calibrated normals; the fitted
  head's distance to the scan's surface, face mm rms): mean head 2.81, points 2.25, + DAViD 1.88, gains x1.6 1.63,
  x2 1.55; + Marigold 2.29 (x2 2.16), + LCM x2 2.55, + MoGe-2 normals 2.53. On our renders (truth set, D1b): Marigold
  2.53 / 2.19 against DAViD 2.21 / 2.13 and the baseline 2.45 / 2.39.
- Garrett's front picture (no truth; itself a generated image, 0.78 px/mm on the face): (a) DAViD on a tight crop at
  768 or 384 = the wide crop (trusted regions 16.8 / 16.6 / 17.3 deg from g3_f, corr 0.30 / 0.31 / 0.27; forehead
  noise 1.7-2.1 deg against Marigold 1.8-2.5, MoGe-2 0.8, the head's own 1.0): the "noise and frame" in mm_01 was
  DAViD's output OUTSIDE its foreground mask, which that sheet did not apply. (c) against g3_f no model beats the mean
  head (13.4 deg; DAViD 17, Marigold 18-19, MoGe-2 16.7, Sapiens2 15.7; corr 0.14-0.34): g3_f is not good enough to
  judge normals by. Model against model (corr of deviations, photo | renders): Marigold - Sapiens2 0.72 | 0.42,
  MoGe-2 - Sapiens2 0.71 | 0.55, DAViD - Sapiens2 0.60 | 0.62, DAViD - Marigold 0.56-0.61 | 0.62: the photo-trained
  models converge on a photo, DAViD is where it was.
- Depth again (Joe asked): MoGe-2 on Garrett's photo against g3_f 5.8 mm rms on the face after scale + shift (the mean
  head 3.8), corr 0.0 (forehead 0.54); on the scan with truth 4.5 mm (mean head 2.4), corr 0.10; DAViD's depth on the
  scan 3.5 mm, corr 0.50 (forehead / brow 0.9). Renders had said 3.7 / 0.30 and 2.7 / 0.43. Depth is no better on
  real skin: still worse than the mean head. No.
- `humannormals`: `model=` "david" (default) | "marigold" (v1-1: CreativeML OpenRAIL++-M, use restrictions travel
  with the weights) | "marigold_lcm" (LCM v0-1, Apache-2.0) in predict / calibration / rows (calibration files
  <model>_normals_gnm.npz; Marigold runs from a venv at $HIFIPUSHIE_MARIGOLD, not installed), and `gain_scale`
  (PHOTO_GAIN 1.6 for photographs of real skin). VERDICT: wire DAViD for photographs, gains x1.6, its mask applied;
  Marigold is the prettier picture and the worse measurement everywhere we have truth.
- Not done: real photographs with 3D truth (NoW, FaceScape, H3DS are research-only and behind forms; none fetched),
  more than one scanned head, the hook in humanfit_map (garrett4's), a photo-domain re-calibration (gains per vertex
  from scans rather than one multiplier).

