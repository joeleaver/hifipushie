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
