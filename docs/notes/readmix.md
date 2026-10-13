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

STATE 2026-10-14 late: TALL LIPS done (LIP_PHOTO_BIAS on: "## TALL LIPS"); expression pass waits. Earlier: (end of the resumed round; branch readmix): ALAR read ON (held-out alar width error 1.5 -> 0.5 mm); the
1.65 mm nose-base correction OFF (overshot on held-out); fallback blend GIVEN-only (block_in_start ethnicity= class |
{class: weight}); expression="lower" built, OFF (not safe: one held-out head broke). Tables: "## Held-out HSRD subjects",
"## The alar-edge read and the fallback classes", "## Per-picture expression". NEXT: lip-border read bias (+3-8 mm lip
heights on every held-out head, main's reads too); expression evidence from a second picture; more held-out heads (the
HSRD pull) and chain repeats before trusting single-chain differences under ~1 mm.

RESUMED (2026-10-14, the coordinator's scoped job: the FALLBACK BLEND, then the alar-edge read; the 1.65 mm nose
correction scored on subjects it was NOT calibrated on). Held-out HSRD subjects (groundtruth's fixed split: HSR0023 m 62,
HSR0027 f 41, HSR0102 f 22) made solve-ready by spikes/readmix/hmk.py <pose> <k> classes=..: rm_<k>_T (truth = the
pose's Part 1 fit, set A = front ~15 deg / ~45 / ~85, the rig's true cameras, pictures in /mnt/data/hifipushie/readmix/pics),
rm_<k>_L<class>00 (block_in_start, lens told on the diagonal, start = pooled | blend (ORACLE: the simplex blend nearest the
true identity, for measuring only) | white | black). k = h23 / h27 / h102. Landmark check LOOKED AT (out/heldout_check.png).
Queue: q8.txt via ./q8run.sh (resumable: skips a chain whose log has 5 SHAPE lines; 4 calls each); logs logs/h<k>_*.log.
Score: ./run.sh spikes/readmix/hscore.py <k> after=rm_<k>_A nb0=rm_<k>_A0 before=rm_<k>_B blend=rm_<k>_Cb ...
QUEUES (each resumable, waits for the one before): q8run.sh (held-out: after / nose-bias off / before / fallback classes),
q9run.sh (alar=1 on the held-out), q10run.sh (expression="lower" leak test: gt_exs_A00 smiling vs sc_a_A00 neutral, off / lower,
nosebias=0 on these renders; and held-out h23 / h102 must not acquire an expression). Logs logs/<first word of the line>.log.
ALAR read (face_ruler._alar_obs, OFF until its chains are read): at the truth the steepest fall outward lies +0.29 mm (sd 1.46,
16 sides) outside the wing's true contour on five TRAIN subjects (gt_h40_T gt_h112_T rm_h42_T rm_h81_T rm_h28_T) -> ALAR_BIAS
0.3; on the three HELD-OUT +0.15 (sd 0.76, 6 sides). LOOKED AT out/alar_rm_h23_T_f.png: the contour hugs the wings.
EXPRESSION: MediaPipe's mouthSmile cannot gate a slight smile (the smiling benchmark front, happy x0.3 dressed: 0.024;
neutral 0.001; one held-out "neutral" subject scores 0.48 (her scan fit carries a lower-face expression)).
BUILT: blockin.class_blend + block_in_start(ethnicity = class | {class: weight}) (simplex only; tested), the solve's reply
line "FALLBACK: ... GIVEN | INFERRED". NOT built: the blend SOLVED as 3 weights (static numbers below say it cannot buy much).

RESTART BLOCK (2026-10-13 late; branch `readmix`, NOT merged, NOT pushed; every item below is committed)
STATE, item by item (T = has tests in tests/test_readmix.py unless said; "default" = what block_in_solve does now):
- MediaPipe mesh -> GNM correspondence: DONE (src/hifipushie/mp_gnm.json + mpread.py; T). "## Step 1".
- Both detectors on scanned heads' photos + the region mix: DONE, default ON (mpread.ENABLED / MIX: eye contours, mouth
  corners, lip seam, vermilion border, nasal bridge; ADDED to the differential anchors; dense floors raised to the
  real-photo errors: face_ruler.DENSE_REGION_SIG). "## Step 2", "## The mix". Measured gain on the two scanned heads:
  none clear (within chain-to-chain noise, "## Validation").
- Nose: CAUSE found (nothing reads its width; both detectors see a photographed nose 1.6-2.6 mm wider than a rendered one).
  (a) nostril-opening read: built, T, OFF (face_ruler.NOSTRIL: one head's validation, an offset known from that head only);
  (b) the differential nose-base anchors' photo-vs-render width (LM_NOSE_WIDE 1.65 mm, from groundtruth's two heads) taken
  out: ON for views not flagged "render" (calibrated on the same two heads it was then run on: not an independent test).
  NOT built: alar-edge read, 3/4 nose silhouette, the fallback-blend item (below). "## The nose".
- Distance / lens / crop: lens_info (EXIF x zoom, crop refused, "frame" for a crop), known-lens distance prior 7 % on the
  whole move (default), DISTANCE / STRONG PERSPECTIVE / INFERRED lines, distance_cost, the brief's line: DONE, T.
  LENS_PINS (focal pinned, scale = distance): built, T, OFF: it REGRESSED h112 (face 2.02-2.15 -> 2.45-2.67): cause not
  found: the first thing to debug (face_ruler.cam_moved(lens=True) + _cam_columns' rot[2] column). "## Distance".
- lens_mm convention bug: FIXED in the reply (face_ruler.lens_mm is on the diagonal now), T. likeness.lens_mm and
  humanfit_map's 70 mm prior (LENS, on the width) NOT touched.
- Hair edge (one-sided) + per-view outline counts / NO OUTLINE warning: DONE, default ON, unit-tested; not validated on a
  hair-covered head with truth. "## Hair-edge read".
- Per-view expression: NOT made safe, OFF. Built: solve(expr_prior=), the blendshape calibration (corr/mp_expr.json);
  missing: ARKit -> expression-column map, the neutral / smiling pair test (groundtruth's gt_exs_A00 vs sc_a_A00; target
  from its notes: mouth, nose base and jaw within 0.5-1 mm; a smile is +3.4 / +2.9 / +3.3 mm today). "## Per-view expression".
- Iris colour: DONE, in skin_from_reference's default groups, T (tests/test_skin_read.py). Sets a muted brown on Tess's
  hazel eyes: defensible, not green. "## Iris colour".
- Guide: blockin_guide.md section 3b + the block_in_solve entry rewritten (cameras as priors, the bound, detectors, distance,
  hair edge); skin_guide.md's eyeballs line. server.block_in_solve has dense / detector / hair_edge parameters.
- FALLBACK BLEND (the coordinator's last item: the pooled class mean is wider-nosed than a given class: "white" -1.67 mm of
  nose_width against the pooled mean): NOT STARTED. Plan: blockin.data()["eth_means"]; the solve's prior centre is
  `prior_off` (blockin.solve_step: c0 - identity(root)): a blend = 3 more columns (class mean differences) with a weak
  prior, or block_in_start(ethnicity={class: weight}); measure (a) pooled (b) right (c) wrong class on synthetic heads
  drawn from one class (denselm's gen2 sampler draws by class) and the HSRD subjects. For denselm: its training identities
  were drawn evenly from the four classes (gen.py / gen2.py), so the network's shrinkage is toward the POOLED mean.
- The WILD benchmark, the distance marginalisation, several casual pictures a person: NOT built (plans in "## Distance").
NEXT (ordered): 1 read the final chains below into "## Validation" if the table is not there yet; 2 debug LENS_PINS on
rm_h112_L00 (ablation: `gch.sh x lenspin=1 nosebias=0 -- rm_h112_L00 rm_h112_X 4 truth=gt_h112_AT cameras=free` against
lenspin=0); 3 the fallback blend; 4 the wild benchmark; 5 alar-edge read; 6 expression gate; 7 merge decision: the
defaults changed here (mesh reads, hair edge, nose-base width, dense floors, iris) have NO measured gain on scans yet and
no regression on the known-head benchmark: say so when proposing the merge.
HOW TO RERUN (all under /mnt/data/hifipushie/readmix; env.sh sets HIFIPUSHIE_HOME = main's workspace,
HIFIPUSHIE_GROUNDTRUTH = readmix/gt (links into groundtruth's data + our own out/), PYTHONPATH incl. the groundtruth
worktree's spikes):
- correspondence: `/mnt/data/hifipushie/facerefs_venv/bin/python spikes/readmix/mpdet.py corr/mp_data.npz <denselm data_s1 dirs>`;
  `./run.sh spikes/readmix/mpcorr.py proj | learn | expr` -> corr/proj.npz, corr/mp_gnm.json (copy to src/hifipushie/), corr/mp_expr.json.
- detectors on scans: `./run.sh spikes/readmix/gmix.py HSR0040-Body-023 HSR0112-Body-018` -> logs + out/gmix_*.png;
  tiles `spikes/readmix/nosetile.py <tag>`, `nostril_eval.py h40 h112 lps`, `cmp.py <model>` (one solve's reads, not applied).
- scan chains: `./gch.sh <log> <switches> -- <start> <prefix> <n> truth=gt_<k>_AT cameras=free [dense=1]` (switches of
  spikes/readmix/rchain.py: mp he nos lens lenspin nosebias camfreeze distfreeze expr); starts rm_h40_L00 / rm_h112_L00
  (mkl.py: the lens told on the diagonal); records gt/out/chains/<prefix>.json, logs logs/<log>.log (7 SHAPE lines = a
  6-call chain done). Summary: `./run.sh $G/spikes/groundtruth/gsum.py <tag> label=<prefix> ..`.
- known heads: `./sch.sh <log> <switches> -- sc_<h>_A00 rm_sc_<h>_<tag> 3 truth=sc_<h>_AT refit=1 cameras=free` -> sc/out/.
- Tess: `./tess.sh` (rm_TF01..08 from sc_T00), tiles `./tour.sh <model>` -> tour/<model>/.
- iris: `./heavy.sh 8 spikes/readmix/iris2.py sc_TN06 rm_iris1`, then `iris.py rm_iris1 rm_iris2 out/x.png`.
- tests: one file a process, `./tests.sh tests/test_readmix.py` (also test_skin_read, test_solvecams, test_refread,
  test_nativedefault, test_denselm, test_face_ruler, test_solvereads, test_chinread: all passed on a08edb1 or later).
WHAT A FRESH AGENT WOULD GET WRONG: (1) groundtruth's gt_<k>_AL00 "told lens" sets tell f / width x 36: use rm_<k>_L00;
(2) bin/slot is not FIFO: a job can wait 40 min behind others' xargs queues; never `pkill -f <pattern>` / `pgrep -f` with
a pattern that is in your own command line (it kills your shell: exit 144); (3) the "truth" vermilion border of a
scan-fitted GNM is ~1.5 mm off the photo's lip edge and vertex numbers under ~1.3 mm are inside the truth's slack;
(4) chain-to-chain noise on one scanned head is ~0.3 mm of face rms and ~1 mm of a width: do not read single chains;
(5) LM_NOSE_WIDE is skipped only for views flagged "render": the solvecams benchmark's pictures are NOT flagged, so its
noses would come out ~1.6 mm narrow now (the sc/out records here were run BEFORE that change);
(6) rm_h40_N / P / Q / h112_P / Q chains were run on INTERMEDIATE code (lens pinned, or anchors dropped): the final
defaults are rm_<k>_F (no dense), _Fd (dense), _Fn (nostril on, h40).
RUNNING when this was written: `xargs -a q7.txt -P 2 -L 1 ./gch.sh` (rm_h40_Fd, rm_h112_Fd, rm_h40_Fn; logs/h40_Fd.log ..;
done = 7 "SHAPE" lines each). Finished: rm_h40_F, rm_h112_F, rm_TF08 (Tess, final defaults; tiles not made yet).

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
Sigma x sqrt(n / 16) (NEFF) and a 0.6 px floor. TRIED: leaving the same detector's differential inner anchors (17-67) out
where these are read (the same evidence): h40's mouth width +0.6 -> +2.3 mm (102 anchors at ~1 mm replaced by reads that count
as 16): the anchors STAY (face_ruler.MP_DROPS_ANCHORS = False), the mesh's reads are added. Dense: every region at max(render, real-photo) error, NEFF 80 as before. The traced lip
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

## Distance (Joe: "anything more specific we need to do about the distance problem"; the coordinator's four items)
WHAT WAS WRONG: (1) with a lens told, the solve still let the camera run (prior 15 % front, 40 % with dense: familynative's
phone pictures 0.65 x / 1.6 x / 3 x their EXIF distance; here +7 % of focal on h40); (2) the scale freedom changed the
FOCAL LENGTH, so "known lens" was not kept; (3) nothing said what an unknown distance costs; (4) groundtruth's told-lens
sets used another convention (f / width x 36 against lens_prior's f / diagonal x 43.27: 39 % off on a portrait crop).
1. KNOWN LENS = KNOWN DISTANCE (BUILT, default: face_ruler.LENS_PINS, lens_info, cam_moved(lens=True)). A view with a
   known lens keeps its focal length; its scale freedom moves the camera (d = focal x head size / pixels); the free
   distance / lens trade does not exist for it (its column is computed per read by finite differences: 1 % nearer is
   not a pure magnification). lens_info: the view's lens_mm, else EXIF FocalLengthIn35mmFilm x DigitalZoomRatio; a picture
   whose pixel aspect is not the EXIF's PixelXDimension : PixelYDimension is CROPPED: its lens is refused and said (a
   resize keeps it); block_in_start's lens prior uses the same function. NOT DONE: FocalLength + sensor size (needs a
   sensor table), portrait-mode crops that keep the aspect (not detectable from EXIF alone).
   MEASURED on the two scanned heads, the lens told in the right convention (rm_<k>_L00, block_in_start's own fit,
   distance error against the rig's cameras, front / 44 deg / profile): h112 +1.1 / -1.1 / -0.5 %; h40 -7.3 / -8.2 / -9.4 %
   = this man's head is 6.3 % larger than the class mean the size hold keeps: the head's size error IS the distance
   error (size = "iris" would read it: not run). After six calls under the old prior scheme the front camera's FOCAL had
   run +7.0 / +8.2 % on h40 to make up for it (dense on / old reads); with the lens pinned it cannot (final-default chains
   rm_<k>_P / Pd: see the validation table). The phone-distance renders (groundtruth's gphone sets): not in the workspace
   when this was written: NOT measured.
2. NO LENS KNOWN: (a) the dense network's near / far output: the pilot weights have none: NOT built; (b, c) BUILT:
   face_ruler.distance_lines: a DISTANCE line per front / 3-4 view in every reply: from the lens, or "NOT KNOWN: it stands
   at x m (a 70 mm portrait assumed): a 20 % error shows as a mm of cheekbone and b mm of jaw width ... a side view is /
   is not in the set". NOT built: a wider sigma on the perspective-sensitive measures (the number is reported instead).
3. SENSITIVITY (spikes/readmix/distsens.py; geometry on GNM's class means, the picture's scale kept at the eyes' plane; a
   +20 % distance error as mm of apparent width):
   | true distance | nose against the ears' plane | alar | mouth | cheekbone | jaw (gonial) | ear to ear |
   |---|---|---|---|---|---|---|
   | 0.3 m | x1.50 | +0.26 | +0.27 | -3.98 | -2.37 | -6.21 |
   | 0.4 | x1.36 | +0.19 | +0.20 | -3.28 | -1.90 | -5.29 |
   | 0.5 | x1.28 | +0.15 | +0.16 | -2.78 | -1.58 | -4.58 |
   | 0.7 | x1.20 | +0.11 | +0.11 | -2.13 | -1.18 | -3.61 |
   | 1.0 | x1.14 | +0.07 | +0.08 | -1.57 | -0.86 | -2.72 |
   | 1.5 | x1.09 | +0.05 | +0.05 | -1.09 | -0.59 | -1.93 |
   | 2.0 | x1.07 | +0.04 | +0.04 | -0.84 | -0.45 | -1.49 |
   | 3.0 | x1.04 | +0.02 | +0.03 | -0.57 | -0.30 | -1.03 |
   (a camera believed at HALF its distance: cheekbone +19 mm at 0.3 m, +8.7 at 1 m, +4.8 at 2 m.) So: beyond ~1.5 m a
   distance error hardly matters; close up it is the deep widths (cheekbones, jaw, ears) that go, NOT the nose's own
   width (it lies near the eyes' plane: 0.3 mm). The wide nose is not a distance fault (and the chains agree: above).
   NOT measured on the scans by re-rendering at 0.3-2 m (no time; the geometry is exact for a pinhole).
   WARNINGS: STRONG PERSPECTIVE when a front camera stands under 0.6 m (in the solve's reply: distance_lines); the
   reference brief has a distance line (likeness_brief.DISTANCE; test). block_in_start itself does not warn yet.
4. GENERATED REFERENCES: one calibration only: Tess's generated head shots, solved with the readmix defaults (rm_TN08):
   front 1.06 m = 113 mm eq., 3/4 1.15 m = 114 mm, "profile" 0.98 m = 93 mm (each weakly read: +7 / +20 / +3 % from the
   start). Stored as humanfit_map.GENERATED_LENS = 105 mm +- 20 % for views flagged {"generated": true}; nothing sets that
   flag yet (NEXT: the brief's own shots should carry it). The held-out line's notes were not read for this.

### After Joe's "we can't count on good pictures out in the wild" (the coordinator's reorder: the NO-LENS case is primary)
BUILT: face_ruler.distance_inferred: when a front / 3-4 view has no known lens, the widths that run ACROSS the face's depth
(cheekbone_width, skull_width, jaw_width, gonial_width) are listed INFERRED with a +- in mm = what the apparent width
changes by if the camera stood anywhere from half to twice its place (DIST_RANGE), in the reply as a WARNING and in
solve["inferred"]; the STRONG PERSPECTIVE warning under 0.6 m. Measures at one depth (eye spacing, mouth, lids, lips, the
nose's own width) are not listed: geometry says they do not depend on it (0.3 mm at 0.3 m).
NOT BUILT (NEXT, in the order I would do them):
1. the sigma of the reads themselves widened by their distance-dependence (today the uncertainty is REPORTED, the solve
   still fits one distance): per read d(read)/d(log distance) is already a column (the camera's distance freedom): giving
   that freedom a prior as wide as the range (log-uniform 0.25-3 m is sd ~0.7 in log) IS the marginalisation, but
   solvecams measured what it costs on a head still far from the person (the column soaks up shape: a true camera drifted
   +28 %); it needs the cameras-first rounds to hold identity and the wild benchmark below to judge.
2. distance estimated from the picture: the perspective cues exist in the solve only as that column; the dense network's
   near / far head is in denselm's coming weights, not the pilot's; picture type as a prior (a face filling a tall phone
   frame): not built.
3. THE WILD BENCHMARK (not run: no slot time left today; every piece exists): groundtruth's rast.py draws the Lee
   Perry-Smith scan through any camera (distance 0.3 / 0.5 / 1 / 2 m, crops, light), the HSRD photos can be stripped and
   cropped (hsrd.head_view), gexpr.py makes a smiling front; conditions: no metadata, random crop + resize, one front only,
   front + one off-angle at a stated-wrong angle, selfie distance, a slight smile, hair over the outline (the tied-hair
   head g of solvecams; a loose groom needs a dressed stage), uneven light. Score: nose / lips / jaw / face against the
   scan AND whether |error| <= the stated +- for every measure distance_inferred lists (coverage), with EXIF and without.
4. several casual pictures of one person, each with its own unknown distance: the solve already gives every view its own
   camera; a second front picture needs views keyed by picture instead of by kind (reference_views keys reads by "front" /
   "3q" / "profile": two fronts would share camera columns: solvereads' note): a real change, not done.

## Hair-edge read (step 5; face_ruler._hair_edge_obs, type "hairedge"; ON by default)
Built as familynative proposed: the parser's skin | hair boundary read like an outline, only where it lies at least 0.5 mm
OUTSIDE the model's outline (the face reaches at least as far as the skin the picture shows), hair on the far side
checked twice, the head's own skin from the chin up without ears and scalp; sigma 0.8 mm; front and 3/4 views. Per-view
outline counts and a NO OUTLINE warning per view (under 20 reads) are in every reply (the old warning counted the total).
VALIDATION: a unit test on a drawn picture (skin 3 mm wider than the model on one side, 4 mm narrower on the other: reads
only on the wider side, 2-4 mm); on Tess (hair tied back, a fresh native start) it gives 37 / 61 / 0 / 4 / 14 / 0 / 3 / 13
reads over eight calls (the temples: where the class-mean start is narrower than her skin) and the solved head's tiles show
no change against main's. NOT validated against truth under LOOSE hair: there is no hair-covered head with known shape
here (the family sets are another line's): the first thing to run in the wild benchmark.

## Per-view expression (step 6): NOT made safe; OFF (as before)
- WHY IT FAILED BEFORE (solvereads, denselm, read again): expression and identity are not separable from landmarks when
  nothing independent says which is which; eight coefficients at sd 0.35 are a cheaper explanation than 170 identity
  components for ANY mouth misfit, so on a neutral picture the term took identity (mouth_width +4.4 mm on the null).
- WHAT IS BUILT TOWARD THE FIX: (a) solve(expr_prior={picture: {class: (mean, sd)}}): each picture's coefficients under
  their own prior, so a picture that READS neutral can be pinned (sd 0.01-0.03: the null cannot leak; tested on a toy
  system) and one that reads a smile gets a centre and a width; (b) the independent read to set it: MediaPipe's blendshape
  scores calibrated on 6,060 renders with known ARKit-named weights (mpcorr.py expr): mouthSmile true = 1.03 x score + 0.13,
  residual sd 0.21, a neutral face scores under 0.13 in 98 % of pictures; jawOpen and eyeBlink also usable; eyeSquint NOT
  (corr 0.21: a neutral face scores 0.41), so a SQUINT cannot be gated this way.
- WHAT IS MISSING: the map from an ARKit weight to face_ruler's expression columns (the sampler's "happy" prototype is not
  ARKit's mouthSmile; denselm's arkit_expr.npz, the ARKit shapes solved on GNM's basis, lives on its branch) and the test
  the brief asks for (the same known head from a neutral and from a slightly smiling front: lips within 0.5 mm):
  groundtruth built that pair (gexpr.py: gt_exs_A00 / sc_a_A00) and its chains were still running. Until both exist the
  term stays off: wiring an unvalidated gate into the default path is how the last two attempts went wrong.

## Validation (numbers COMPUTED; tiles LOOKED AT where said). The verdict first: the nose and lips did NOT get measurably nearer the scans.
(A) THE TWO SCANNED HEADS (HSRD rig photos, set A = front / 44 deg / profile; groundtruth's gsum.py; logs/gsum_h40.log, gsum_h112.log).
"main" = groundtruth's chains on main's code (8 calls, no lens: the cameras end 58-75 % near); "lens, old reads" = main's
reads from the correct-lens start rm_<k>_L00 (6 calls); "readmix" = this branch's defaults from the same start (rm_<k>_F,
6 calls: mesh reads + anchors, hair edge, nose-base width taken out, lens prior 7 %, no dense). One chain each: chain-to-
chain noise is ~0.3 mm of face rms and ~1 mm of a width.
| | h40 main | h40 lens, old reads | h40 readmix | h112 main | h112 lens, old reads | h112 readmix |
|---|---|---|---|---|---|---|
| scan surface, NOSE mean / p90 mm | 0.89 / 1.69 | 1.49 / 3.43 | 1.34 / 2.93 | 0.98 / 1.95 | 1.02 / 2.07 | 1.07 / 2.10 |
| scan surface, LIPS | 0.88 / 1.85 | 1.07 / 2.34 | 0.86 / 1.83 | 1.31 / 2.34 | 1.13 / 1.91 | 1.27 / 2.09 |
| scan surface, FACE | 0.89 / 1.78 | 1.12 / 2.44 | 1.01 / 2.17 | 1.44 / 2.94 | 1.32 / 2.76 | 1.43 / 2.99 |
| vertex face / lower face rms (vs the direct fit) | 2.01 / 2.90 | 2.64 / 3.74 | 2.55 / 3.88 | 2.41 / 3.62 | 2.08-2.15 / 2.26-2.33 | 2.36 / 2.95 |
| nose_base_width, solved - truth | +3.9 | +5.3 | +4.2 (rm_h40_F call 6: +4.7) | +2.7 | +1.9 .. +2.2 | +1.5 |
| alar_width | +0.7 | +2.6 | +2.6 | +0.3 | +1.6 | +1.1 |
| tip_radius_h (- = sharper than the truth) | -2.8 | -1.5 | -1.0 | -3.9 | -3.7 | -3.6 |
| mouth_width | -0.4 | +0.6 | +1.7 | +3.3 | -0.0 | +1.0 |
| upper / lower vermilion (mid) | -0.3 / +0.6 | +0.3 / +1.4 | +0.3 / +1.0 | +1.2 / +0.8 | +0.4 / +0.3 | +0.6 / +0.1 |
| front camera: pitch deg, distance % | -2.5, -60 | -3.4, +1 | -2.3, -6 | -4.4, -58 | -0.7 .. -1.8, -1 .. +4 | -2.2, +2 |
| profile camera: pitch deg, distance % | -5.1, -75 | +15.2, -9 | +12.6, -9 | +17.6, -74 | | +0.9, -1 |
READ BLUNTLY: (1) the nose's base stays 1.5-4.7 mm wide: the calibrated anchor width took ~0.7 mm off h112 and nothing
reliable off h40; h40's nose against the scan is WORSE than main's (1.34 against 0.89): main's wrong-distance solve
happened to sit nearer. (2) lips: within noise. (3) what the right lens buys is the CAMERAS (distance -60 % -> within 6 %;
h112's profile pitch +17.6 -> +0.9 deg) and h112's lower face (3.62 -> 2.3-2.95); h40's profile camera still runs 12-15 deg
in pitch. (4) the wide tip Joe saw is not here: both heads' tips come out SHARPER than the truth (radius -1 .. -3.9 mm).
With the nostril read on (h40 only, intermediate code): see logs/h40_Fn.log / RESTART.
(B) KNOWN HEADS (solvecams' a-d, set A, starts fitted / true with the front pitched 8 deg, 3 calls; before = its suites c
(no dense) and d; after = sc/out/rm_sc_*; run BEFORE the nose-base width change):
| | before | after |
|---|---|---|
| face / lower face rms, mean of 8 chains (no dense) | 1.79 / 2.01 | 1.80 / 2.01 |
| jaw width between the two starts, per head a-d | 5.1 1.4 3.6 0.5 | 2.1 3.4 0.8 0.5 |
| dense, fitted start: head a face / low | 1.44 / 1.68 | 1.72 / 1.69 |
| dense: head b | 1.55 / 2.51 | 1.61 / 2.28 |
No regression without dense; with dense head a's face is 0.3 mm worse (the dense read now counts for less: its floors are
the real-photo errors, and on our own renders it was better than that).
(C) TESS (fresh native start sc_T00, 8 calls): LOOKED AT, one tile at a time (out/tess_nose_v0.png, tess_mouth_v0.png:
photo | clay | overlay | raking; before = sc_TN06 on main, after = rm_TN08 on an intermediate state of this branch: mesh
reads without the anchors, no nose-base width): NOSE: no visible change; both clay noses lie on hers, a little boxier at
the wings with larger nostril openings than hers. MOUTH: no visible change; the lips lie on hers in both. rm_TF08 (the
final defaults) is solved; its tiles were NOT made or looked at.

## Held-out HSRD subjects (2026-10-14; hscore.py; vertex measures after errmap's similarity; truth = the pose's Part 1
## IDENTITY fit: the photo's own resting expression is NOT in it: lip heights / mouth width carry it where a subject's scan
## fit has a lower-face expression; 4 calls from the told-lens pooled start; COMPUTED)
| subject | chain | face / low rms | nose base | alar | tip radius h | nose proj. | mouth width | upper / lower vermilion |
|---|---|---|---|---|---|---|---|---|
| h23 (m) | start | 2.79 / 4.05 | -1.0 | +1.8 | -1.8 | -3.9 | -0.9 | +2.6 / +2.5 |
| h23 | before (main's reads) | 2.56 / 3.68 | -0.9 | +0.1 | -1.6 | -1.6 | +0.0 | +4.0 / +4.2 |
| h23 | readmix, nose correction 0 | 2.19 / 2.74 | +0.6 | +1.7 | -1.7 | -1.6 | +0.8 | +3.7 / +4.0 |
| h23 | readmix, nose correction 1.65 | 2.20 / 2.80 | -0.9 | +0.8 | -1.5 | -1.8 | +0.1 | +3.5 / +4.1 |
| h27 (f) | start | 5.13 / 3.72 | +5.5 | +3.7 | +0.6 | -2.8 | +2.4 | +2.5 / +1.3 |
| h27 | before | 4.57 / 3.55 | +1.3 | +1.1 | -0.3 | -1.2 | +1.8 | +3.1 / +2.7 |
| h27 | readmix, 0 | 4.80 / 3.49 | +1.4 | +1.1 | -0.5 | -1.6 | +2.0 | +3.2 / +2.8 |
| h27 | readmix, 1.65 | 4.70 / 3.64 | -0.8 | -0.2 | -0.7 | -1.4 | +1.4 | +3.0 / +2.6 |
| h102 (f) | start | 3.67 / 4.79 | -6.1 | -3.8 | -3.2 | +0.1 | -8.8 | -1.5 / -3.0 |
| h102 | before | 3.10 / 4.72 | +0.1 | +2.0 | -1.3 | -1.0 | +7.0 | +6.7 / +8.6 |
| h102 | readmix, 0 | 2.50 / 3.61 | +0.6 | +1.7 | -0.6 | -1.6 | +5.4 | +5.9 / +8.2 |
| h102 | readmix, 1.65 | 2.62 / 3.95 | -1.5 | -0.4 | -0.9 | -2.0 | +4.5 | +6.3 / +8.2 |
READ: (1) the readmix reads (mesh, hair edge, lens prior) improve the face / lower face on two of three held-out heads
(h23 2.56 / 3.68 -> 2.19 / 2.74; h102 3.10 / 4.72 -> 2.50 / 3.61; h27 a little worse in face rms, 4.57 -> 4.80: her hair
lies on the cheeks). (2) on these heads the solved NOSE BASE is within +-1.4 mm without any correction: the wide nose
of the two calibration heads does not generalise, and the 1.65 mm correction overshoots (0.87 -> 1.07 mean |error|): OFF.
(3) the LIPS come out 3-8 mm too TALL against the identity fit and h102's mouth +5 mm wide: her photo's mouth scores
mouthSmile 0.48 and her scan fit carries a lower-face expression: the expression item's real case.
(4) The tall lips are NOT the photos' expressions: the scan fits' own expression changes the lip heights by under 1.5 mm
(and the other way on h102: -1.0 / -1.5). Main's reads give the same +3-8 mm: a lip-border read bias (the traced border /
MediaPipe's border read the COLOUR edge, GNM's border vertices are the form: groundtruth found the colour edge 1.5 mm off
on another head) as large as the lips themselves on dark, full lips. NEXT for the lips: the border as paint, and the
lip reads' sigma / bias measured against these scans before they move identity.

## The alar-edge read and the fallback classes on the held-out subjects (2026-10-14; COMPUTED; one chain each, 4 calls)
| subject | chain | face / low | nose base | alar | mouth width | upper / lower vermilion |
|---|---|---|---|---|---|---|
| h23 | readmix (no nose correction) | 2.19 / 2.74 | +0.6 | +1.7 | +0.8 | +3.7 / +4.0 |
| h23 | + ALAR read | 2.25 / 2.93 | -0.9 | +0.4 | +0.2 | +3.6 / +4.0 |
| h23 | start: wrong class (black) | 2.40 / 3.04 | +1.0 | +1.6 | +1.0 | +3.7 / +3.8 |
| h27 | readmix | 4.80 / 3.49 | +1.4 | +1.1 | +2.0 | +3.2 / +2.8 |
| h27 | + ALAR | 4.74 / 3.11 | +0.9 | +0.7 | +2.2 | +3.1 / +2.7 |
| h27 | start: white | 4.67 / 3.08 | +0.9 | +0.9 | +2.3 | +3.2 / +2.6 |
| h27 | start: black | 4.70 / 3.27 | +1.8 | +1.6 | +2.7 | +3.1 / +2.5 |
| h102 | readmix | 2.50 / 3.61 | +0.6 | +1.7 | +5.4 | +5.9 / +8.2 |
| h102 | + ALAR | 2.17 / 3.03 | -0.8 | +0.4 | +2.2 | +5.3 / +7.6 |
| h102 | start: oracle blend (= black) | 2.85 / 4.18 | +1.1 | +2.5 | +6.2 | +6.6 / +9.1 |
| h102 | start: wrong class (white) | 2.49 / 3.57 | -0.3 | +0.6 | +5.7 | +6.2 / +8.5 |
ALAR: ON by default (alar width mean |error| 1.5 -> 0.5 mm; lower face better on two of three). Its at-truth bias: "## The
nose" + face_ruler.ALAR_BIAS (train subjects only).
FALLBACK: after four calls the start's class moves the nose base by under 1 mm and the mouth by under 1 mm; a WRONG class
cost at most 0.4 mm of nose base here; the oracle blend (the simplex blend nearest the true identity) was no better than
the pooled mean on h102. Static numbers agree: the classes' means differ by 1-3 mm in nose / mouth width, people differ from
the nearest one by 3-8 mm, and the distance from a true identity to the pooled mean and to the nearest class mean differs
by under 0.2 of 11-21 (sd units). So: the blend is given by the caller (block_in_start(ethnicity={class: weight}): a
shape parameter, said GIVEN / INFERRED in the reply); SOLVING it as 3 more dimensions is NOT built: it could move the prior
centre by about one class difference (~1 mm) and the reads already decide these measures. For denselm: its training
identities were drawn evenly from the four classes, so its shrinkage is toward the POOLED mean.
Oracle blend on the other two (pooled -> oracle blend, alar read off): h23 nose base +0.6 -> +0.3, alar +1.7 -> +1.2, mouth
+0.8 -> +0.4; h27 +1.4 -> +0.3, +1.1 -> +0.3, +2.0 -> +1.6; face rms 0.1 mm worse on both. Even the BEST possible fallback
centre buys 0.3-1.1 mm of nose width and costs nothing elsewhere; a wrong class costs up to 0.4. Worth giving when known.

## Per-picture expression, expression="lower" (2026-10-14; built, NOT safe, OFF)
Leak test (solvecams' known head a; truth = its NEUTRAL identity; the same set with a neutral front / with the front shot
again with GNM's happy x0.3: groundtruth's gexpr.py pictures; 4 calls; nosebias 0, alar read off; COMPUTED):
| front picture, mode | calls | face / low rms | jaw width | mouth width | nose base | alar | upper / lower vermilion |
|---|---|---|---|---|---|---|---|
| neutral, off | 4 | 2.65 / 1.89 | +2.0 | +0.7 | -0.1 | -0.4 | +0.0 / -0.0 |
| neutral, lower | 4 | 2.27 / 1.34 | +1.5 | +1.9 | +2.4 | +1.3 | +0.7 / +0.6 |
| smiling, off | 4 | 2.64 / 2.01 | +3.9 | +4.0 | +3.4 | +1.3 | +0.8 / +1.0 |
| smiling, lower | 4 | 2.64 / 1.81 | +2.5 | +3.0 | +2.6 | +1.2 | +0.8 / +1.0 |
LEAK (smiling - neutral): off: mouth +3.3, nose base +3.5, jaw +1.9 mm; lower: +1.1 / +0.2 / +1.0, but only because the
NEUTRAL solve got worse with the term (mouth +0.7 -> +1.9, nose base -0.1 -> +2.4): against the truth the smiling solve
moved only 1 mm (mouth +4.0 -> +3.0, nose base +3.4 -> +2.6). Held-out real check (alar read on): h23 (neutral photo)
did not acquire an expression (face 2.25 -> 2.11, every measure within 0.6 mm); h102 (her photo scores mouthSmile 0.48)
went WRONG: nose base -0.8 -> -6.4, mouth +2.2 -> -5.3, face 2.17 -> 3.17: the free mouth expression took the identity's
place. Not safe: OFF. What it needs, as solvereads and denselm found: evidence that tells expression from identity (a
second picture of the same face with another expression, or the picture's own expression read independently: MediaPipe's
smile score does not see a slight smile (0.024 for happy x0.3) and its scale on clay is nonlinear (smilecal.py)).

## TALL LIPS (2026-10-14; the coordinator: "upper lip about twice the photo's height" on a family head)
WHICH READS SET LIP HEIGHT: the traced vermilion borders (type "lip": blockin_lips.photo_evidence, the COLOUR edge, sigma
0.3 mm: the strongest), MediaPipe's border / seam points (type "mp"), the differential anchors lm 48-67 (type "landmark");
dense is off by default. MEASURED AT THE TRUE HEAD (spikes/readmix/lipbias.py; the scan-fitted identity through the rig's
cameras, front view; seven TRAINING subjects; picture minus model, vertical mm, + = lower; mean (sd over subjects)):
| read | upper centre | upper bow | upper corners | seam | lower centre | lower bow | lower corners |
|---|---|---|---|---|---|---|---|
| traced border (lip) | -2.39 (2.36) | -1.26 (1.75) | -0.69 (0.73) | - | +3.86 (2.15) | +2.74 (1.92) | +0.76 (0.92) |
| MediaPipe mesh (mp) | -1.37 (1.32) | -0.98 (1.30) | +0.12 (0.93) | +1.1 (0.6) | +3.47 (1.92) | +3.27 (1.47) | +1.82 (1.02) |
| anchors (landmark) | -2.27 (1.67) | -2.04 (1.49) | -0.78 (0.92) | +0.3 (0.5) | +2.75 (2.17) | +2.44 (1.96) | +1.02 (1.34) |
Every read sees the photographed lips TALLER than the scan-fitted head's border rows, most at the middle: the colour edge
of a real lip lies above (upper) / below (lower) GNM's border vertex row, and our render's lips look thinner to the
detectors than photographed ones. WHICH TRUTH: the scan's FORM (the fit's border rows) for what the solve fits; the
picture's colour edge for the PAINT (the vermilion as a texture line: for projskin). So each read's mean offset per border
position / point is taken out of a PHOTO's reads (face_ruler.LIP_PHOTO_BIAS, lip_photo_bias.json; not for views flagged
"render"). At the truth on the three HELD-OUT subjects the corrected reads are within -1.4..+0 mm on average (per subject
sd 1-2.7: per-person scatter remains).
HELD-OUT, solved (4 calls, told-lens pooled start, alar read on; ONE chain per cell). Vertex measures against the scan's
identity fit (a 1-4 mm floor on rms: groundtruth's two-scan finding):
| subject | chain | face / low rms | upper / lower vermilion height | mouth width | nose base |
|---|---|---|---|---|---|
| h23 | main's reads | 2.56 / 3.68 | +4.0 / +4.2 | +0.0 | -0.9 |
| h23 | readmix | 2.25 / 2.93 | +3.6 / +4.0 | +0.2 | -0.9 |
| h23 | + lip correction | 2.05 / 2.26 | +1.6 / +1.2 | +0.7 | +0.8 |
| h27 | main's reads | 4.57 / 3.55 | +3.1 / +2.7 | +1.8 | +1.3 |
| h27 | readmix | 4.74 / 3.11 | +3.1 / +2.7 | +2.2 | +0.9 |
| h27 | + lip correction | 4.66 / 3.07 | +0.5 / -0.8 | +1.9 | +0.8 |
| h102 | main's reads | 3.10 / 4.72 | +6.7 / +8.6 | +7.0 | +0.1 |
| h102 | readmix | 2.17 / 3.03 | +5.3 / +7.6 | +2.2 | -0.8 |
| h102 | + lip correction | 1.81 / 2.49 | +2.8 / +3.9 | +1.0 | +0.3 |
Against the SCAN'S SURFACE (spikes/readmix/hsurf.py: the solved identity with the scan's own expression, laid on the fit by
a similarity; mean |d| (mean signed, + = outside the scan), mm):
| subject | chain | lips | nose | chin | cheeks | face |
|---|---|---|---|---|---|---|
| h23 | main / readmix / + lip corr. | 1.07 / 1.06 / 1.03 | 1.05 / 0.92 / 1.05 | 1.19 / 1.03 / 1.14 | 1.18 / 1.19 / 0.95 | 1.20 / 1.17 / 1.16 |
| h27 | | 0.99 / 0.69 / 0.80 | 1.26 / 1.18 / 1.15 | 1.15 / 1.38 / 1.32 | 2.09 / 1.95 / 1.82 | 1.74 / 1.71 / 1.63 |
| h102 | | 2.73 / 1.60 / 1.76 | 1.06 / 0.93 / 0.89 | 3.16 / 1.29 / 2.00 | 1.57 / 1.13 / 1.01 | 1.54 / 1.08 / 1.05 |
VERDICT: the lip HEIGHTS come down by 2-4 mm on all three (mean |error| of the six heights 4.4 -> 1.8 mm) and the vertex
face / lower face improve on all three; on the scan SURFACE the lips are within noise (1.06 / 0.69 / 1.60 -> 1.03 / 0.80
/ 1.76) and h102's chin is worse (1.29 -> 2.00): the surface does not confirm the vertex gain for the lips. ON by default
(LIP_PHOTO_BIAS), flagged: single chains, three heads.
TEST NOTE: test_nativedefault's neck assertion: first relaxed on intermediate code where the prior ended 5.1 mm from ANSUR's
mean and the free solve 2.4 (a real ordering failure then); on the final code the ordering holds (held / prior / free 0.18 /
0.18 / 0.48 mm in the test; 0.5 / 3.5 / 11.5 mm on the full tess set against main's 1.3 / 14.6 / 21.7): restored to the
strict ordering with a 1e-5 tie tolerance. It hides nothing now.
