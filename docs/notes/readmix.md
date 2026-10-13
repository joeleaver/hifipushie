# readmix (2026-10-13, "readmix" agent, branch `readmix`, worktree .claude/worktrees/readmix, from main 94516bf)
The joint solve (face_ruler.compare / blockin.solve_step / MCP block_in_solve) should use the BEST read for each part of
the face on real photographs. Joe, on two real-photo heads solved with the dense landmarks on: profile line "pretty
amazingly close"; the NOSE a little too wide and too rounded on both; one LIP SHAPE wrong although the lips were well
defined in the photo; "the major things we're missing for identity are the eye details"; and on the detector overlays:
"mediapipe did a much better job, on the points that it did land".
Scratch DURABLE in /mnt/data/hifipushie/readmix: env.sh, run.sh <script> (light slot), heavy.sh <gb> <script> (capped;
the script takes resources.heavy), corr/ (the correspondence's data), gt/ (its OWN groundtruth root: work / pics / lps /
hsrd100 are links into the groundtruth agent's data, read-only; out/ is ours), out/, logs/. Scripts spikes/readmix.
Models rm_* (main's workspace). The groundtruth agent's scripts (spikes/groundtruth on branch groundtruth) are run from
its worktree through PYTHONPATH with THIS worktree's src (rchain.py sets readmix's switches first).

STATE (2026-10-13, in progress): see the steps below.
NEXT: -

## How things are run
- `/mnt/data/hifipushie/readmix/run.sh spikes/readmix/<script>.py ..` (a light slot); MediaPipe's own venv for mpdet.py.
- The four light slots were full for most of the day (groundtruth's chains, denselm's generator): every job here queued.

## Step 1: MediaPipe's mesh -> GNM's surface (the correspondence; spikes/readmix/mpdet.py, mpcorr.py; src/hifipushie/mp_gnm.json)
- DATA: denselm's gen2 sets (/mnt/data/hifipushie/denselm/data_s1: 31 dressings, GNM-NATIVE heads, 320 px renders, sampled
  identity / ARKit-named expression / camera / light; labels for 570 skin landmarks, identity + expression + camera per sample).
  MediaPipe (mpdet.py, its own venv, x2.4 upscaled on grey): a face on ~70 % of the pictures (yaw runs to +-100).
- EVERY GNM face vertex's pixel per sample (mpcorr.py proj; 6,060 samples, |yaw| <= 90, 220 a dressing): GNM's formula
  (T + c IB + e EB) + the stage's lip closing (lip_close is a combination of the first 40 lower-face expression components:
  fitted to the sample's stored lip / mouth / chin landmarks) + a similarity + a thin-plate warp of the rest on the 570
  stored landmarks; camera by DLT from the same landmarks (1e-4 px). LEAVE-OUT error (fitted on every other landmark):
  0.05 mm lips + mouth, 0.50 nose, 0.55 lids + orbit, 0.56 all. TRIED: re-evaluating each head through humanfit.state (3 s
  a sample: 5 h); gen.py's sets in data/ (body-carried heads: 1.5-3 mm off GNM's formula, leave-out 1.5 mm): not used.
- PER MEDIAPIPE POINT (468: all but the irises; mpcorr.py learn): the candidate vertex (4,598 face-skin vertices) with the
  least Huber-mean distance over the 2,400 near-frontal samples (|yaw| < 20, |pitch| < 15), refined to a barycentric point
  in its best incident triangle; then bias (median, x / y mm in the picture) and scatter (MAD) per yaw bin (-90 -55 -35 -15
  15 35 55 90). Stored: GNM triangle ids + weights, set, region, the bins; provenance in the file.
- SCATTER ON THE RENDERS (per axis, mm; includes the 320 px pictures' ~1 mm pixel and every expression):
| group | n | frontal sd mm (median over points) | worst | 15-35 deg rms | 35-55 deg rms |
| brow_l | 10 | 1.49 | 1.87 | 2.01 | 3.27 |
| brow_r | 10 | 1.51 | 1.77 | 2.06 | 3.08 |
| brows | 8 | 1.77 | 2.31 | 2.79 | 3.97 |
| cheeks | 65 | 2.29 | 3.21 | 3.38 | 4.85 |
| chin | 5 | 2.64 | 2.86 | 3.90 | 4.55 |
| eye_l | 16 | 1.14 | 1.22 | 1.69 | 2.61 |
| eye_r | 16 | 1.07 | 1.23 | 1.65 | 2.64 |
| eyes | 71 | 1.32 | 1.99 | 2.18 | 3.56 |
| forehead | 17 | 2.40 | 3.05 | 3.78 | 6.11 |
| lip_inner | 20 | 1.43 | 1.58 | 2.02 | 2.86 |
| lip_outer | 20 | 1.36 | 1.59 | 1.96 | 2.80 |
| lips | 40 | 1.35 | 1.44 | 1.91 | 2.74 |
| mouth | 34 | 1.86 | 2.59 | 2.55 | 3.27 |
| nose | 100 | 1.58 | 1.93 | 2.51 | 3.29 |
| oval | 36 | 3.12 | 4.13 | 4.71 | 6.85 |
- EFFECTIVE N (participation ratio of the residuals' covariance, near-frontal): the whole inner face's 864 reads = 16.4
  independent ones; lips 80 -> 5.9; eyes 64 -> 5.5; nose 200 -> 4.8; oval 72 -> 6.8. MediaPipe regresses one low-dimensional
  mesh: its points err together. mpread.NEFF = 16 a view.
- THE BLENDSHAPE SCORES against the expression each render carries (mpcorr.py expr; /mnt/data/hifipushie/readmix/logs/expr.log):
  mouthSmile is a usable expression read (front: true = 1.03 x score + 0.13, corr 0.82, residual sd 0.21; the score on
  pictures WITHOUT a smile: median 0.000, p90 0.018, p98 0.128), jawOpen (corr 0.77) and eyeBlink (0.83) too; eyeSquint is
  NOT (corr 0.21; a neutral face reads 0.41 median), mouthFrown / mouthPress no (0.09 / 0.15), browDown weak (0.44).

## Step 2: both detectors on photographs of scanned heads (spikes/readmix/gmix.py; COMPUTED; tiles LOOKED AT where said)
Truth = groundtruth's Part 1 direct fit (GNM identity + expression fitted to the scan in 3D: 0.4-0.6 mm on the face)
projected through the rig's calibrated cameras (its gt_<k>_T sets: front, front pitched (fu), 19-23, 44, 60-72, 88-90 deg;
3,500 px / m). Two HSRD-100 heads (h40, h112). Each cell: per-axis rms mm of the detector's point minus the truth's, RAW /
AFTER the detector's own 2D similarity per view (shift, scale, turn fitted on its inner-face points: the solve's cameras are
free, so the second number is what a read's sigma should be), n = reads over both heads. "mp" = MediaPipe through the
correspondence, by FEATURE; "mp_region" = the same by GNM region (like for like with the dense network's regions);
"dense" = the pilot network (hm18), the landmarks the solve would use.
CAVEATS: (1) a surface fit pins a vertex across the surface, not along it: on smooth skin (cheeks, forehead) the truth
itself slides 1-2 mm; (2) the vermilion border is a COLOUR edge the 3D fit never saw: LOOKED AT (out/nose_h40_f_mouth.png):
the truth's upper border lies ~1.5 mm ABOVE the photo's lip edge and MediaPipe's border points lie ON the edge, so its real
border error is under the table's; (3) two heads.

### per-axis rms mm against the projected scan fit, heads h40, h112 (n reads): raw / after the detector's own 2D similarity per view

| feature | detector | front | q23 | q45 | s72 | s90 |
|---|---|---|---|---|---|---|
| alar / nostril base | mp | 1.70 / 1.22 n134 | 2.24 / 1.55 n72 | 2.13 / 1.62 n58 | 1.88 / 2.32 n25 | - |
| brow line | mp | 2.16 / 1.67 n79 | 2.50 / 1.88 n38 | 3.15 / 2.53 n34 | 3.49 / 2.31 n15 | - |
| brow region | mp | 2.90 / 2.38 n30 | 2.51 / 1.82 n14 | 3.93 / 2.61 n12 | 4.70 / 3.67 n6 | - |
| brow region | mp_region | 2.39 / 1.89 n109 | 2.50 / 1.86 n52 | 3.37 / 2.55 n46 | 3.88 / 2.77 n21 | - |
| brow region | dense | 2.48 / 2.06 n115 | 1.94 / 1.82 n56 | 1.98 / 1.87 n47 | 2.30 / 2.41 n40 | 3.29 / 1.70 n17 |
| cheeks | mp | 2.48 / 2.06 n251 | 2.59 / 1.96 n121 | 4.75 / 3.02 n76 | 5.88 / 4.44 n32 | - |
| cheeks | mp_region | 2.48 / 2.06 n251 | 2.59 / 1.96 n121 | 4.75 / 3.02 n76 | 5.88 / 4.44 n32 | - |
| cheeks | dense | 3.26 / 2.36 n242 | 2.84 / 2.02 n128 | 3.35 / 2.62 n81 | 3.33 / 2.90 n50 | 3.87 / 3.44 n35 |
| chin | mp | 3.03 / 1.90 n20 | 2.77 / 1.85 n10 | 2.97 / 1.86 n8 | 2.17 / 3.48 n3 | - |
| chin | mp_region | 3.03 / 1.90 n20 | 2.77 / 1.85 n10 | 2.97 / 1.86 n8 | 2.17 / 3.48 n3 | - |
| chin | dense | 4.14 / 2.29 n86 | 3.38 / 1.33 n54 | 3.49 / 1.93 n32 | 0.82 / 1.17 n13 | 4.47 / 4.56 n6 |
| commissures | mp | 0.89 / 1.14 n15 | 1.97 / 1.26 n8 | 1.97 / 1.89 n6 | 2.16 / 1.93 n2 | - |
| eye contour | mp | 1.07 / 0.77 n28 | 0.85 / 0.94 n14 | 1.52 / 1.61 n13 | 3.61 / 2.94 n8 | - |
| face oval | mp | 4.57 / 3.71 n108 | 4.20 / 3.19 n52 | 6.35 / 4.07 n44 | 9.49 / 7.60 n20 | - |
| forehead | mp | 4.06 / 3.27 n57 | 3.73 / 2.86 n24 | 6.23 / 3.23 n20 | 8.88 / 6.27 n9 | - |
| forehead | mp_region | 4.06 / 3.27 n57 | 3.73 / 2.86 n24 | 6.23 / 3.23 n20 | 8.88 / 6.27 n9 | - |
| forehead | dense | 3.75 / 2.78 n180 | 2.91 / 2.54 n78 | 2.69 / 2.34 n65 | 3.07 / 2.50 n48 | 3.76 / 2.74 n20 |
| lids | mp_region | - | - | 1.67 / 1.49 n7 | 4.38 / 3.52 n5 | - |
| lids | dense | 2.74 / 2.09 n19 | 1.84 / 1.56 n12 | 2.79 / 3.18 n13 | 1.85 / 1.91 n11 | 2.25 / 1.09 n3 |
| lip seam | mp | 1.53 / 1.34 n68 | 1.83 / 1.49 n34 | 1.59 / 1.58 n29 | 1.64 / 1.83 n11 | - |
| lip surface | mp | 1.55 / 1.42 n160 | 1.78 / 1.56 n80 | 1.62 / 1.49 n68 | 1.76 / 1.78 n25 | - |
| lip surface | mp_region | 1.57 / 1.43 n315 | 1.82 / 1.58 n158 | 1.62 / 1.50 n133 | 1.79 / 1.82 n50 | - |
| lip surface | dense | 1.90 / 1.81 n136 | 2.37 / 1.80 n67 | 2.32 / 1.63 n56 | 1.48 / 1.34 n33 | 2.00 / 1.21 n17 |
| nasal bridge | mp | 1.92 / 1.45 n64 | 1.50 / 0.84 n26 | 1.81 / 1.62 n20 | 0.83 / 1.85 n10 | - |
| nose (all) | mp_region | 1.74 / 1.28 n303 | 2.03 / 1.33 n138 | 2.00 / 1.50 n112 | 1.58 / 2.17 n51 | - |
| nose (all) | dense | 2.07 / 1.53 n181 | 2.31 / 1.71 n82 | 2.77 / 1.84 n65 | 3.63 / 2.09 n60 | 2.71 / 1.97 n47 |
| nose other | mp | 1.32 / 0.88 n23 | 1.50 / 0.64 n6 | 2.18 / 0.81 n6 | 1.15 / 1.78 n3 | - |
| nose tip / dorsum | mp | 1.75 / 1.33 n82 | 2.01 / 1.21 n34 | 1.80 / 1.22 n28 | 1.48 / 2.17 n13 | - |
| orbit | mp | 1.89 / 1.65 n282 | 1.89 / 1.43 n134 | 3.55 / 1.73 n103 | 4.37 / 2.59 n43 | - |
| orbit | mp_region | 1.84 / 1.59 n309 | 1.82 / 1.39 n148 | 3.46 / 1.73 n109 | 4.25 / 2.53 n46 | - |
| orbit | dense | 2.96 / 2.34 n208 | 2.18 / 1.80 n102 | 2.66 / 2.55 n74 | 2.55 / 1.99 n56 | 2.94 / 1.95 n33 |
| round the mouth | mp | 2.19 / 1.45 n136 | 2.05 / 1.29 n68 | 2.39 / 1.70 n58 | 1.75 / 2.12 n21 | - |
| round the mouth | mp_region | 2.19 / 1.45 n136 | 2.05 / 1.29 n68 | 2.39 / 1.70 n58 | 1.75 / 2.12 n21 | - |
| round the mouth | dense | 2.13 / 1.43 n160 | 2.14 / 1.33 n80 | 2.51 / 2.12 n65 | 1.86 / 1.67 n33 | 2.25 / 1.85 n19 |
| vermilion border | mp | 1.74 / 1.59 n72 | 1.86 / 1.75 n36 | 1.55 / 1.34 n30 | 1.91 / 1.89 n12 | - |


### signed widths, MediaPipe through the correspondence minus the truth, mm (per head and view)

- h40 f: mouth width (61-291): -0.16 (truth 53.5)
- h40 f: alar width (129-358): +5.52 (truth 39.1)
- h40 f: nostril base (98-327): +4.07 (truth 31.3)
- h40 f: alar wings (64-294): +3.48 (truth 37.2)
- h40 q23: mouth width (61-291): +0.66 (truth 49.9)
- h40 q23: alar width (129-358): +6.97 (truth 36.8)
- h40 q23: nostril base (98-327): +6.18 (truth 29.3)
- h40 q23: alar wings (64-294): +5.66 (truth 34.9)
- h40 fu: mouth width (61-291): -2.99 (truth 50.4)
- h40 fu: alar width (129-358): +6.50 (truth 36.6)
- h40 fu: nostril base (98-327): +5.91 (truth 29.4)
- h40 fu: alar wings (64-294): +5.47 (truth 35.0)
- h112 f: mouth width (61-291): +0.15 (truth 46.6)
- h112 f: alar width (129-358): +2.35 (truth 36.2)
- h112 f: nostril base (98-327): +4.61 (truth 27.4)
- h112 f: alar wings (64-294): +3.10 (truth 32.6)
- h112 q23: mouth width (61-291): +3.65 (truth 41.8)
- h112 q23: alar width (129-358): +1.78 (truth 32.6)
- h112 q23: nostril base (98-327): +3.92 (truth 24.4)
- h112 q23: alar wings (64-294): +2.43 (truth 29.3)
- h112 fu: mouth width (61-291): +1.11 (truth 45.9)
- h112 fu: alar width (129-358): +1.51 (truth 35.4)
- h112 fu: nostril base (98-327): +3.69 (truth 27.0)
- h112 fu: alar wings (64-294): +2.31 (truth 32.1)

WHAT IT SAYS
- EYE CONTOURS: MediaPipe 0.8-1.1 mm to ~25 deg; the dense network's lids 1.6-2.7 (its region sigma was 0.5).
- LIPS: MediaPipe's corners 0.9-1.1 front, seam 1.3-1.5, border 1.6-1.7 (see caveat 2); dense 1.8-1.9. Mouth WIDTH from
  MediaPipe's corners: -0.2 / +0.2 mm front.
- NOSE: per point MediaPipe looks fine (1.2-1.7), but it is BIASED: alar width +5.5 / +2.4 mm, nostril base +4.1 / +4.6
  front. LOOKED AT (out/nose_h40_f_nose.png: the fitted GNM nose mesh drawn on the photo lies on the alae and nostrils; the
  detector's alar points sit 2-3 mm outside the wings on the cheek and its tip / columella / subnasale ~2 mm low): MediaPipe
  draws a more average, wider nose. Its alar / nostril / tip points are NOT read (mpread.MIX).
- JAW / CHIN / CHEEKS / FOREHEAD: nobody is good (2-4 mm raw, 1.9-3.3 after the similarity; part of it caveat 1).
- THE DENSE NETWORK ON REAL FACES is 1.4-2.8 mm after its own similarity everywhere, 2-4 raw: 2-5 x its region sigmas
  (set on our renders: lids 0.5 -> 2.1-2.7 real, chin 1.1 -> 2.3-4.1, lips 0.8 -> 1.8-1.9, nose 1.2 -> 1.5-2.1, cheeks 1.8 ->
  2.4-3.3, forehead 2.0 -> 2.8-3.8). FOR THE TRAINING RUN (denselm): this is the sim-to-real gap of a network trained on
  our renders only; face_ruler.DENSE_REGION_SIG now carries the larger of the two measurements per region.
- LIPS, FORM AND BORDER ARE TWO THINGS (for the projskin line, via the coordinator): geometry does not know where the
  lip's colour edge is: a scan-fitted GNM puts its vermilion border ~1.5 mm off the photo's. The solve should fit the lip's
  FORM (seam, corners, volume from the profile); the border is a paint line to be placed from the picture's own traced edge.

## The mix (src/hifipushie/mpread.py MIX; face_ruler.DENSE_REGION_SIG)
| read | front (< 15 deg) | shallow 3/4 (< 35) | 3/4 (< 55) | beyond |
|---|---|---|---|---|
| MediaPipe eye contour | 0.9 | 1.0 | - | - |
| MediaPipe mouth corners | 1.1 | 1.4 | - | - |
| MediaPipe lip seam | 1.4 | 1.5 | 1.6 | - |
| MediaPipe vermilion border | 1.5 | 1.7 | - | - |
| MediaPipe nasal bridge | 1.5 | 1.5 | - | - |
| MediaPipe alar / nostril / tip, oval, brows, chin, cheeks, forehead | not read | | | |
Sigma x sqrt(n / 16) (NEFF) and a 0.6 px floor. Where these are read the same detector's differential inner anchors (17-67)
are left out (the same evidence). Dense: every region at max(render, real-photo) error, NEFF 80 as before. The traced lip
borders (0.3 mm) and lid margins (0.2-0.4 mm) stay the fine reads of the front picture.

## The nose (the coordinator's order after the gate: find the CAUSE of the wide nose before building a read)
Before, on main's code (groundtruth's chains, records copied to gt/out/chains): nose_width (the nostril sills, landmarks
31-35; solved - scan fit, after a similarity) per call:
| head, chain | start (class mean) | calls 1 .. 8 | front camera's distance error |
|---|---|---|---|
| h40, free | +4.7 | 6.2 5.1 4.5 4.5 4.0 3.6 3.6 3.9 | -74 -> -60 % |
| h40, free + dense | +4.7 | 5.6 5.5 5.4 5.2 5.2 5.2 5.0 5.0 | -74 -> +11 % |
| h40, TRUE cameras at the start, front pitched 8 deg | +4.7 | 6.3 5.2 4.8 4.3 3.8 3.7 3.3 3.3 | 0 -> +12 % |
| h112, free | +3.0 | 2.3 2.5 2.8 3.1 3.5 3.2 3.0 2.7 | -69 -> -58 % |
| h112, free + dense | +3.0 | 2.9 2.8 2.9 2.8 2.7 2.8 2.9 2.8 | -69 -> -34 % |
| h112, TRUE cameras, pitched start | +3.0 | 0.9 1.0 1.2 1.6 2.0 2.0 2.1 2.1 | 0 -> +3 % |
| h112, every camera FROZEN at the truth (rm_h112_tc, 4 calls) | +3.0 | 3.2 .. 3.2 | 0 |
| h112, true start, only the DISTANCE frozen (rm_h112_td) | +3.0 | 2.6 .. 2.2 | 0 |
(h40 with the true cameras as the start and nothing moved is REFUSED by block_in_solve's stale-camera check: the class
mean through the true cameras stands at x0.90 the pictures' points.)
1. CAMERA DISTANCE IS NOT THE CAUSE. With the front camera at its true distance (frozen, or within 3-12 %) the nose is
   +2.1 .. +3.3 mm wide; at -60 % it is +2.7 .. +3.9; at +42 % (groundtruth's told-lens sets, below) +2.0 .. +3.5.
2. NOTHING READS IT: THIS IS THE CAUSE. The class mean's nose is 3.0 / 4.7 mm wider than these two people's, and the solve
   leaves it there (h40: 4.7 -> 3.3-5.0 after eight calls) while the mouth's width, which IS read (corners, lip borders),
   goes from +3.8 to 0.0-1.4. No outline shows the wings from the front, the differential anchors compare MediaPipe with
   MediaPipe (both draw an average nose), the dense network's nose points sit 1.5-2.1 mm off on a real face and answer
   with the average, and MediaPipe's own alar points are 2.4-5.5 mm wide (step 2). solve_report already said so: nose_width
   under MOVED WITH NO READ / unread.
3. THE PROFILE: not examined beyond this: the tip's projection and the profile line come from the side outline (0.3 mm
   reads) and Joe judged the profile "pretty amazingly close"; the fault is the front's width and the tip's roundness.
ALSO FOUND: groundtruth's told-lens sets (gt_<k>_AL00) tell `lens_mm` = f / WIDTH x 36; humanfit_map.lens_prior counts the
35 mm equivalent on the frame's DIAGONAL (f / diag x 43.27). On these 1152 x 1536 crops that is a lens 39 % too long:
those chains START +28 .. +40 % far and (rightly, for a told lens) stay there. rm_<k>_L00 (spikes/readmix/mkl.py) are the
same starts with the lens told in the pipeline's convention (h40 185-188 mm, h112 166-196 mm).

### The nostril read (face_ruler._nostril_obs; type "nostril"; ON by default; spikes/readmix/nostril_eval.py)
- WHAT: in a view turned under 30 deg, each nostril's dark opening in the picture (the component nearest the model's rim,
  at half the depth between the opening's darkest and the skin round it; 3-160 mm2; refused when the darkest part is not
  under 0.55 x the skin: hidden under the tip, a flat light) against the model's nostril RIM (GNM's exterior nose skin
  bordering the nostril's interior: fixed vertices): its LATERAL end and its MEDIAL end along the line through both
  openings, sigma 0.8 / 1.2 mm. Four reads a view; the picture is read once per call.
- AT THE TRUTH (the scan-fitted head through the rig's cameras; a read should be 0): h40 front: right lateral -1.4,
  left lateral +0.9 (a 1 mm sideways shift the camera's shift takes; the openings' OUTER WIDTH picture - truth: -0.55 mm),
  medial -1.9 / +2.3; h40 at 19 deg: the near nostril -1.7 / -0.5. h112 (front, pitched, 24 deg): NOT READ, rightly: LOOKED
  AT (out/nostril_sheet0.png): her tip hides the openings from the front: brown slits, no dark opening. The Lee Perry-Smith
  renders: NOT READ (the scan's texture is lit flat: its nostrils are light). So: validated on ONE head's two views
  (width to 0.6 mm); it refuses where there is nothing to read; it is silent on a nose like h112's.
- NOT BUILT (NEXT): the wing's outer edge (the alar-facial groove) as a shading edge: visible on every tile looked at,
  including the two heads the nostril read cannot do; the profile-matching machinery of face_ruler._ramp_obs (picture
  against the lit model across a contour) is the place to start. The nose's silhouette in a 3/4 against the cheek.

## Iris colour (step 7; skin_read._iris_rel / iris_colour; "eyeballs" is in skin_from_reference's default groups now)
- WHY IT FAILED BEFORE (Tess: grey-green -> orange-brown): (a) the change was clipped per CHANNEL to 0.5 .. 2 (from the
  default brown a grey-green iris needs x1.5 / 4.5 / 11: the clip made orange); (b) the picture's iris and sclera were taken
  at the MODEL's eyeball pixels: its opening is not the picture's, so lid skin got into the ring (a warm cast: orange-brown
  whatever the start); (c) the sclera's MEDIAN lies in lid and lash shadow (luminance 0.08 / 0.16 / 0.25 at 20 / 50 / 80 %).
- NOW: the picture's own limbus (blockin_eyes.limbus), the ring's middle tones on its lateral rays, the sclera's bright
  fifth just outside it on the same rays; ours from the render's eyeball pixels; front and 3/4 views with an iris of 10 px
  radius; the change limited as a whole (hue kept); the second round takes a secant step (our eye picture answers a colour
  change with 35-80 % of it per channel). "NOT READ" is said when no view qualifies.
- TESS (a fork of sc_TN06, the iris set back to the default brown; two rounds; tess_a1 only read): #5a3a1e -> #503e24 ->
  #4d3e2e. LOOKED AT (out/iris_tess2.png, the picture's eyes beside ours): no longer orange, the ring's median colour
  agrees with the picture's (#584839 against #4a3f30), darker and less saturated than the default; but her iris is HAZEL
  (a grey-green rim round an amber centre) and ours is one muted brown: a single iris colour cannot say that. Verdict: it
  now sets a defensible colour instead of leaving the default; it does not make her eyes green. NEXT: two zones (rim /
  collarette) in skin.eyes, read the same way.
