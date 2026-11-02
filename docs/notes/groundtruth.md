# groundtruth (2026-10-13, "groundtruth" agent, branch `groundtruth`, worktree .claude/worktrees/groundtruth, from main 94516bf)
Joe: "what's our confidence that we're pushing the GNM mesh correctly with the dense data we have?" Every accuracy number
so far came from benchmark heads that are GNM heads rendered by us. This thread measures against REAL heads whose shape is
known: scans. PART 1 = the CEILING (GNM fitted to the scan in 3D, no pictures); PART 2 = the PIPELINE (block_in_start +
block_in_solve from pictures of that head through known cameras: our renders of a scan, and a scan rig's REAL photos).
Scratch DURABLE in /mnt/data/hifipushie/groundtruth ($HIFIPUSHIE_GROUNDTRUTH): env.sh, run.sh <script> (light slot),
heavy.sh <gb> <script>, q.sh <queue file> [parallel], lps/ + hsrd100/ (the downloads, licence texts beside them), work/<tag>/
(working copies, fits, registrations), pics/ (reference pictures), out/ (tables, chain records, logs). Scripts
spikes/groundtruth (bench.sh reruns everything; fetch.sh + sources.json = where the data comes from). Models gt_* (main's
workspace). Sheets workspace/human_renders/gt_*. Nothing of the datasets, and no picture of the scanned people, is in git.

STATE (2026-10-13; Parts 1 and 2 DONE, the HSRD-100 real-photo set being pulled; branch `groundtruth`, NOT merged, NOT
pushed; no solver default changed): **on real anatomy GNM's ceiling is 0.4-0.6 mm (face mean; 0.8-1.0 p90); our
picture solve ends at 0.9-1.7 mm (1.8-3.6 p90), best 0.87-1.05 on real photos with the lens told and the distance
held; the gap is mostly ours: widths and size that no read measures (they stay at the class mean: jaw +5-8 mm on a
narrow-jawed head, the nose's base +2-5 mm on both real-photo heads), the lower face, and cameras (distance never
found; the profile camera's pitch 15-18 deg off without dense).** GNM cannot make folds (nasolabial, marionette,
jowl break, hooded lids, neck bands): that is the fold layer's job, 0.2-0.4 mm of the ceiling. The dense network is
3-4 mm off on real photos (1.4-2.0 on our renders) and reads faces WIDE there; MediaPipe's differential anchors do too.
NEXT (for the coordinator / Joe; none done here): (1) a read of the nose's width in the picture itself (readmix
started one) and nose / lip landmarks trained or tuned on photographs: the HSRD set below gives ~400 labelled real
head photos of 10 people; (2) when a picture's lens is known: dense ON with the distance held to 5 % as a bound on the
whole move (face 2.1 -> 1.6-1.7 mm at phone distance, 0.95 -> 0.87 on real photos); never the 40 % prior; (3) the lens
NUMBER: lens_mm is read on the diagonal (EXIF), the reply's CAMERA lines and the 70 mm prior count on the width (x1.39
on a 3:4 portrait): one convention; (4) expression in the solve from the first call (a slight smile = +3.5 mm of mouth
width as identity; neither expression="view" nor expression_step recovers it); (5) widths: the jaw / gonial / skull
widths and the head's size need a read or an honest "not measured" in the reply; (6) bin/slot starves a serial job
while xargs queues refill every freed slot (24 min waiting for one step): a FIFO ticket; (7) rerun this benchmark
after any solver change: spikes/groundtruth/bench.sh (Part 1 ~15 min a scan, Part 2 ~1 h a scan at three chains at once).
PULL FINISHED 2026-10-13 16:00: 29 poses, 6.6 GB, nothing running; the RESTART notes below are kept for a re-pull.
RESTART (checkpoint 2026-10-13 14:15; written for an agent that starts cold, possibly after a pull was cut off mid-download):
- DONE and committed: Parts 1 and 2, the nose / lips / phone / expression section, both sheets, the set's code and
  loader. Nothing of Parts 1-2 is in flight. All numbers are in this file; chain records in
  /mnt/data/hifipushie/groundtruth/out/chains/*.json, scores out/scores/, tables out/*.md.
- THE PULL (the only thing running): /mnt/data/hifipushie/groundtruth/hsrd100. A pose is COMPLETE when
  hsrd100/<subject>/<pose>/summary.json exists (written last). Complete and verified (`hsrdset.py check` passed on
  the first 10; label sheets looked at for HSR0040-023, HSR0042-018, HSR0027-053): the 10 neutral poses
  HSR0040-Body-023, HSR0112-Body-018, HSR0023-Body-054, HSR0042-Body-018, HSR0161-Body-015, HSR0081-Body-054,
  HSR0027-Body-053, HSR0015-Body-023, HSR0102-Body-052, HSR0028-Body-062, + HSR0042-Body-045 (swim cap),
  HSR0040-Body-027, HSR0112-Body-023. IN FLIGHT at the checkpoint: HSR0023-Body-046. REMAINING, in order (the list
  is spikes/groundtruth/hsrd_poses.txt): HSR0161-Body-009, HSR0081-Body-010, HSR0027-Body-004, HSR0015-Body-070,
  HSR0102-Body-019, HSR0028-Body-016, HSR0040-Body-012, HSR0112-Body-074, HSR0023-Body-052, HSR0042-Body-008,
  HSR0161-Body-007, HSR0081-Body-033, HSR0027-Body-029, HSR0015-Body-009, HSR0102-Body-048, HSR0028-Body-021.
- RUNNING NOW: `pull_all.sh pull2.txt` (PID 1144258 at the checkpoint; one line per finished pose in
  /mnt/data/hifipushie/groundtruth/out/pull_all2.log, a log per pose in out/pull/<pose>.log). It is ALIVE if
  `pgrep -f "hsrd_pull.sh HSR"` prints a PID; FINISHED when pull_all2.log has 20 lines; DIED if neither. rc=0 "done
  <pose>" = good; rc=1 = that pose failed (read its log's last lines), the loop goes on; rc=3 = stopped: under 60 GB free.
- RESUME (safe to run at any time; refuses to start while a pull is alive):
  `cd /home/joe/dev/hifipushie/.claude/worktrees/groundtruth && nohup spikes/groundtruth/hsrd_resume.sh > /dev/null 2>&1 &`
  It walks hsrd_poses.txt: complete poses are skipped, a pose directory without summary.json is removed and redone,
  a half-downloaded archive is continued (curl -C -) and tested (unzip -t; a corrupt one: delete
  hsrd100/dl/<pose> and resume again), the unpacked files and working copy of a cut-off run are thrown away,
  originals are deleted after each pose, index.json is rewritten after EVERY pose (hsrd_index.py; the table lands in
  out/hsrd_set.md). Lines per pose: out/pull_resume.log. Then: `uv run python spikes/groundtruth/hsrdset.py check`,
  `uv run python spikes/groundtruth/hsrd_vary.py` (what the poses vary: table for this file), update the set's
  section below, commit, tell the coordinator the final size.
- BUDGET: the set is 5.1 GB at 13 poses (0.2-0.5 GB a pose; 30 poses ~11 GB of the 40 GB allowed); transient 1.5-2 GB
  a pose; /mnt/data had 116 GB free at the checkpoint (the pull stops itself under 60).
- WHAT A FRESH AGENT WOULD GET WRONG: (1) the scan is NOT in the rig calibration's frame: never project a scan into
  a photo without T_scan_to_rig (cameras.json; register.py measures it); (2) run every python step with the
  environment of /mnt/data/hifipushie/groundtruth/env.sh (PYTHONPATH incl. spikes/chinread for errmap;
  HIFIPUSHIE_ASSETS); the pull does this itself; (3) do NOT run the pull's steps through bin/slot: a serial job
  starves there (hsrd_pull.sh runs them capped, one at a time, single thread); (4) never `pkill -f <pattern>` /
  `pgrep -f` with a pattern that is also in your own command line: it kills or matches your own shell (it cost this
  session several queues); kill by PID; (5) mask files are named <photo>.mask.png OR <photo>.JPG.mask.png; photos are
  stored as the camera was mounted (heads sideways: roll_deg), the .xmp calibration is for those raw pixels (EXIF
  orientation must NOT be applied); (6) `vis` in labels.npz is geometric: use Pose.good() (visible AND on measured
  skin); (7) lens_mm for the solve is the EXIF (diagonal) number, not the width number the replies print; (8) the
  private photo sets and the held-out Garrett set are other agents'; tess_a1 / garrett_a1 are never written; nothing
  of HSRD or the Lee Perry-Smith pictures goes into git.

## Licences, attribution, what was downloaded (verified 2026-10-13 from the sources' own files; spikes/groundtruth/sources.json)
- **Lee Perry-Smith head** ("Infinite, 3D Head Scan by Lee Perry-Smith", Infinite Realities / triplegangers). Licence:
  **CC BY 3.0 Unported**, read in `Infinite-Scan_License.txt` INSIDE the archive from Morgan McGuire's Computer Graphics
  Archive (casual-effects.com/data: lpshead.zip, 43.6 MB, sha256 cc683bb0...b619ca; its info.js says "CC BY 3.0", "(c) I-R
  Entertainment Ltd.") and in three.js's copy (LeePerrySmith_License.txt, same words). Commercial use allowed with
  attribution. REQUIRED ATTRIBUTION wherever a result made with it is shown: "Infinite, 3D Head Scan by Lee Perry-Smith
  (www.triplegangers.com, www.ir-ltd.net), CC BY 3.0; from Morgan McGuire's Computer Graphics Archive". What it is: ONE
  man's head and shoulders, an 8,842-quad ZBrush level + colour map + 16-bit displacement (we do not apply the
  displacement: pores and fine wrinkles; Catmull-Clark x2 = 141k quads is our working copy). Shaved head (the scalp is
  skin: the only one of our scans with a skull), EYES CLOSED, mouth closed, an inner mouth bag / nostrils in the mesh
  (masked by normals). Units undocumented; they behave as metres (exocanthion distance 92.6 mm, similarity to GNM's
  landmarks 0.990).
- **HSRD-100** (Digital Reality Lab, huggingface.co/datasets/digitalrealitylab/HSRD-100). Licence: **CC BY 4.0**: the
  dataset card's YAML (`license: cc-by-4.0`) and its License section ("Commercial use allowed", "Modification allowed",
  "Attribution required"); "All participants provided informed consent"; each person_meta.json has "license": "Commercial".
  No separate licence file exists in the repository; the card (saved: hsrd100/README_dataset_card_2026-10-13.md) IS the
  licence statement. The card also lists as out of scope: biometric identification, medical diagnosis, surveillance
  (advice of the card, not a licence term): we measure a shape model against the scan and identify nobody.
  REQUIRED ATTRIBUTION: "HSRD-100: 100 High-Quality 3D Human Scans Dataset, Digital Reality Lab, 2025,
  https://huggingface.co/datasets/digitalrealitylab/HSRD-100, CC BY 4.0". TAKEN: 4.2 GB of 246 GB: two poses,
  HSR0040-Body-023 (man, 50, "crossed arms, relaxed standing", sweater) and HSR0112-Body-018 (woman, 60, "hand in pocket,
  relaxed standing", sweater), each: Scan-LOD0.zip (1M triangles, 16k texture, vertex colours), RealityCapture.zip,
  Photos.zip (112 photos + masks + .xmp calibration) + the two metadata files (sha256 in sources.json). Chosen from the
  ten people's previews for short hair, no hat / glasses / beard, an upright standing pose. /mnt/data had 129 GB free
  before, 119 GB after everything.
- Nothing else was downloaded or used (no NoW, FaceScape, H3DS, Headspace, DAD-3DHeads, Multiface, NeRSemble, FLAME, BFM).
- The scanned people are real: these notes speak of the model's fit, never of the person.

## What the HSRD rig is (looked at: out/cams2_*.png, out/register_*.png, out/pics_h40.png / pics_h112.png)
- 112 Nikon D7500 (5568 x 3712, 60 mm lens = 90 mm equivalent; a few 6000 x 4000), studio flash, a white cyclorama with
  the rig's own stands, cameras and a banner behind the head. The subject stands in the middle, ~2.1-2.6 m from every camera.
- There ARE dedicated head cameras: 40-50 photos a pose see the head, about half of them through a longer setting
  (166 mm equivalent in the .xmp): **the face is ~1,500 px wide (10-11 px / mm), on the others ~900 px (6 px / mm)**.
  For the pipeline we resample to 3.5 px / mm (1152 x 1536), so the photos are 2-3x better than what we feed it.
  Lighting: soft, frontal-ish, even; skin texture, stubble, brows, lashes all sharp. Expression: neutral, mouth closed,
  eyes open (gaze at a camera or slightly off). Hair: short on both (the forehead's top and, on the woman, most of the
  ears are covered). Collars: a crew-neck sweater up to the neck's base (man), a V-neck (woman): the jaw line is free.
- Each photo's .xmp is a RealityCapture calibration (rotation, position, 35 mm focal length, principal point, brown3
  radial distortion; spikes/groundtruth/hsrd.py reads it). **The exported scan is NOT in that frame** (found by laying
  the scan on the photos: turned 27.6 / 135.4 deg about the vertical and moved 6-21 cm: the scan was re-oriented for
  delivery). register.py measures the rigid transform: detector landmarks triangulated through the calibration for a
  first guess (2.2 mm), then the dataset's own foreground MASKS of 24 head cameras against the scan's silhouette (2D
  point-to-line Gauss-Newton): silhouette rms 1.33 mm (man) / 2.59 mm (woman; median 0.6 mm both: the tail is hair
  fuzz). So a true camera is known to ~1 mm / well under a degree at the head.
- A head picture for the pipeline (hsrd.head_view): the photo undistorted and re-projected by a pure rotation about the
  camera's centre onto the head (an exact pinhole picture, principal point in the middle, upright for the head), 3.5 px
  / mm. Seen from 2.3 m this is a **230-280 mm-equivalent** picture: far longer than the pipeline's 70 mm prior.
- Some cameras are mounted on their side and some see the head at the photo's very edge (the woman stands off-centre):
  gmk.py picks cameras whose photo holds the whole head; for the woman three were picked by eye (`cams=`).

## PART 1: the ceiling (spikes/groundtruth/fit3d.py; everything COMPUTED; LOOKED AT: gt_01_ceiling.png and the three
## gt_01_ceiling_<scan>_p1b3_features.png, 15 feature tiles a scan)
Method: the scan is carried into GNM's frame by a similarity from anatomical points (align0.py: the 68 standard
landmarks marked by the detector on a front picture of the scan drawn by us, each carried back onto the surface by the
depth buffer; the inner 51 + the chin point; I checked the marks on out/align0_*.png), then pose + GNM's 170 head
identity components (+ optionally blockin's expression nuisance: 20 lower-face + 6 + 6 eye-region components, and the
sampler's two wink prototypes for a scan with shut eyes) are solved on TWO-SIDED point-to-plane distances (GNM's fit
vertices -> scan; a 1.5 mm sampling of the scan's skin -> GNM), correspondences found again each round, Huber 3 mm.
Masked: hair and cloth (a colour model of the scan's own skin + surface roughness; brows and stubble stay), the
eyeballs, the mouth's inside, the ears' backs, the scan's inner surfaces, GNM's neck. Weights: the data count as 2,000
independent reads at 1 mm (about a three-view picture solve's information), the identity prior N(class mean, 1) x1 or
x0.25. "b3" = every component bounded at +-3 sd as block_in_solve does (cmax): **p1b3 is "the Part 1 fit"** used as the
truth identity in Part 2. The distance is exact point-to-triangle, both directions pooled
(tests/test_groundtruth.py: 5 synthetic cases).

#### lps: mean / p90 mm by region (two-sided, the scan's skin)

| region | p1b3 | p0.25b3 | p1eb3 | p0.25eb3 | p1 | p1e | p1esb3 |
|---|---|---|---|---|---|---|---|
| forehead | 0.52 / 0.97 | 0.47 / 0.92 | 0.47 / 0.87 | 0.41 / 0.80 | 0.51 / 0.94 | 0.46 / 0.82 | 0.36 / 0.67 |
| brow | 0.44 / 0.86 | 0.41 / 0.76 | 0.42 / 0.74 | 0.34 / 0.66 | 0.47 / 0.78 | 0.50 / 0.71 | 0.33 / 0.57 |
| eye sockets | 1.51 / 2.49 | 1.81 / 2.86 | 1.16 / 1.05 | 1.40 / 1.19 | 1.54 / 2.47 | 1.07 / 1.05 | 2.18 / 13.63 |
| nose | 0.37 / 0.58 | 0.36 / 0.57 | 0.39 / 0.60 | 0.37 / 0.55 | 0.35 / 0.56 | 0.38 / 0.60 | 0.30 / 0.54 |
| cheeks | 0.35 / 0.69 | 0.35 / 0.68 | 0.50 / 0.53 | 0.43 / 0.51 | 0.35 / 0.68 | 0.50 / 0.53 | 0.49 / 0.50 |
| lips | 0.31 / 0.65 | 0.29 / 0.60 | 0.23 / 0.51 | 0.23 / 0.48 | 0.30 / 0.62 | 0.23 / 0.50 | 0.20 / 0.44 |
| chin | 0.31 / 0.56 | 0.28 / 0.60 | 0.21 / 0.40 | 0.22 / 0.39 | 0.30 / 0.52 | 0.20 / 0.41 | 0.16 / 0.32 |
| jaw line | 0.40 / 0.74 | 0.35 / 0.64 | 0.39 / 0.77 | 0.31 / 0.60 | 0.40 / 0.74 | 0.40 / 0.75 | 0.29 / 0.57 |
| under-chin | 1.95 / 4.59 | 1.41 / 2.89 | 2.48 / 5.61 | 1.52 / 3.91 | 1.88 / 4.15 | 2.49 / 5.52 | 2.11 / 5.05 |
| ears | 1.04 / 2.17 | 1.00 / 2.02 | 1.02 / 2.09 | 0.98 / 1.99 | 1.04 / 2.15 | 1.02 / 2.05 | 0.80 / 1.66 |
| temples | 0.52 / 1.07 | 0.43 / 0.91 | 0.50 / 1.09 | 0.41 / 0.88 | 0.53 / 1.09 | 0.51 / 1.08 | 0.37 / 0.79 |
| scalp | 0.62 / 1.30 | 0.56 / 1.19 | 0.61 / 1.25 | 0.55 / 1.14 | 0.60 / 1.27 | 0.60 / 1.23 | 0.48 / 1.10 |
| face | 0.57 / 0.82 | 0.60 / 0.77 | 0.51 / 0.71 | 0.52 / 0.64 | 0.57 / 0.78 | 0.50 / 0.69 | 0.66 / 0.61 |
| share of GNM face verts compared | 93 % | 93 % | 95 % | 95 % | 93 % | 95 % | 96 % |
| distance from class mean: norm (max sd) | 18.9 (3.0) | 24.5 (3.0) | 17.7 (3.0) | 23.5 (3.0) | 19.1 (4.4) | 17.9 (4.1) | 16.5 (3.0) |
| scan scale | 0.9904 | 0.9904 | 0.9904 | 0.9904 | 0.9904 | 0.9904 | 0.8137 |

measures of p1b3 (mm): jaw_width 108.7, gonial_width 124.3, chin_width 63.9, cheekbone_width 131.2, skull_width 163.5, pupils_apart 63.0, nose_width 32.9, mouth_width 47.8, chin_length 37.4, nose_length 50.7
the sex's class mean laid on p1b3 by a similarity: scale 0.984 (the fitted head is -1.6 % the class mean's size); class mean: jaw_width 119.9, gonial_width 135.4, chin_width 67.0, cheekbone_width 138.6, skull_width 157.0, pupils_apart 63.4

#### HSR0040-Body-023: mean / p90 mm by region (two-sided, the scan's skin)

| region | p1b3 | p0.25b3 | p1eb3 | p0.25eb3 | p1 | p1e | p1esb3 |
|---|---|---|---|---|---|---|---|
| forehead | 0.36 / 0.75 | 0.31 / 0.69 | 0.37 / 0.76 | 0.33 / 0.64 | 0.35 / 0.75 | 0.36 / 0.75 | 0.28 / 0.59 |
| brow | 0.62 / 1.37 | 0.59 / 1.27 | 0.58 / 1.27 | 0.57 / 1.23 | 0.62 / 1.36 | 0.57 / 1.26 | 0.42 / 0.88 |
| eye sockets | 0.54 / 1.14 | 0.52 / 1.08 | 0.52 / 1.10 | 0.50 / 1.05 | 0.53 / 1.14 | 0.52 / 1.11 | 0.43 / 0.86 |
| nose | 0.39 / 0.82 | 0.38 / 0.78 | 0.38 / 0.80 | 0.36 / 0.75 | 0.39 / 0.82 | 0.38 / 0.81 | 0.30 / 0.59 |
| cheeks | 0.39 / 0.81 | 0.33 / 0.71 | 0.37 / 0.77 | 0.32 / 0.65 | 0.39 / 0.81 | 0.37 / 0.76 | 0.27 / 0.56 |
| lips | 0.48 / 0.97 | 0.43 / 0.89 | 0.37 / 0.75 | 0.36 / 0.74 | 0.47 / 0.96 | 0.36 / 0.74 | 0.28 / 0.56 |
| chin | 0.40 / 0.81 | 0.35 / 0.68 | 0.35 / 0.69 | 0.32 / 0.64 | 0.39 / 0.81 | 0.35 / 0.68 | 0.25 / 0.50 |
| jaw line | 0.34 / 0.78 | 0.33 / 0.71 | 0.33 / 0.77 | 0.32 / 0.69 | 0.34 / 0.77 | 0.33 / 0.78 | 0.26 / 0.58 |
| under-chin | 0.27 / 0.71 | 0.27 / 0.69 | 0.35 / 1.22 | 0.33 / 0.94 | 0.25 / 0.85 | 0.31 / 1.03 | 0.25 / 0.57 |
| ears | 0.88 / 1.80 | 0.83 / 1.79 | 0.88 / 1.84 | 0.81 / 1.74 | 0.89 / 1.84 | 0.88 / 1.82 | 0.66 / 1.43 |
| temples | 0.53 / 1.01 | 0.45 / 0.90 | 0.54 / 1.02 | 0.46 / 0.90 | 0.53 / 1.00 | 0.54 / 0.99 | 0.37 / 0.75 |
| scalp | 0.42 / 0.86 | 0.37 / 0.87 | 0.55 / 1.06 | 0.45 / 0.94 | 0.42 / 0.85 | 0.57 / 1.04 | 0.48 / 0.91 |
| face | 0.45 / 0.95 | 0.42 / 0.87 | 0.42 / 0.88 | 0.40 / 0.82 | 0.45 / 0.94 | 0.42 / 0.88 | 0.32 / 0.65 |
| share of GNM face verts compared | 93 % | 93 % | 93 % | 93 % | 93 % | 93 % | 93 % |
| distance from class mean: norm (max sd) | 15.7 (3.0) | 21.7 (3.0) | 14.5 (3.0) | 20.6 (3.0) | 15.8 (4.1) | 14.6 (4.0) | 14.9 (3.0) |
| scan scale | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.7564 |

measures of p1b3 (mm): jaw_width 130.8, gonial_width 151.7, chin_width 70.7, cheekbone_width 148.2, skull_width 177.4, pupils_apart 66.0, nose_width 33.8, mouth_width 53.9, chin_length 38.2, nose_length 53.4
the sex's class mean laid on p1b3 by a similarity: scale 1.068 (the fitted head is +6.8 % the class mean's size); class mean: jaw_width 119.9, gonial_width 135.4, chin_width 67.0, cheekbone_width 138.6, skull_width 157.0, pupils_apart 63.4

#### HSR0112-Body-018: mean / p90 mm by region (two-sided, the scan's skin)

| region | p1b3 | p0.25b3 | p1eb3 | p0.25eb3 | p1 | p1e | p1esb3 |
|---|---|---|---|---|---|---|---|
| forehead | 0.31 / 0.74 | 0.28 / 0.64 | 0.30 / 0.70 | 0.27 / 0.59 | 0.31 / 0.76 | 0.30 / 0.70 | 0.25 / 0.61 |
| brow | 0.44 / 0.95 | 0.43 / 0.91 | 0.42 / 0.85 | 0.41 / 0.88 | 0.44 / 0.94 | 0.42 / 0.86 | 0.34 / 0.72 |
| eye sockets | 0.40 / 0.79 | 0.37 / 0.72 | 0.36 / 0.71 | 0.33 / 0.65 | 0.40 / 0.79 | 0.36 / 0.71 | 0.33 / 0.66 |
| nose | 0.42 / 0.86 | 0.38 / 0.78 | 0.39 / 0.80 | 0.35 / 0.73 | 0.42 / 0.87 | 0.39 / 0.80 | 0.29 / 0.57 |
| cheeks | 0.42 / 0.95 | 0.36 / 0.83 | 0.40 / 0.91 | 0.33 / 0.75 | 0.42 / 0.95 | 0.40 / 0.91 | 0.33 / 0.70 |
| lips | 0.35 / 0.73 | 0.30 / 0.62 | 0.35 / 0.72 | 0.31 / 0.65 | 0.35 / 0.72 | 0.35 / 0.72 | 0.28 / 0.58 |
| chin | 0.36 / 0.75 | 0.36 / 0.71 | 0.34 / 0.71 | 0.33 / 0.69 | 0.36 / 0.76 | 0.34 / 0.71 | 0.26 / 0.53 |
| jaw line | 0.38 / 0.80 | 0.34 / 0.73 | 0.37 / 0.74 | 0.32 / 0.65 | 0.38 / 0.80 | 0.37 / 0.75 | 0.33 / 0.67 |
| under-chin | 0.27 / 0.45 | 0.24 / 0.42 | 0.23 / 0.45 | 0.31 / 0.55 | 0.24 / 0.41 | 0.23 / 0.46 | 0.29 / 0.55 |
| ears | 0.64 / 1.37 | 0.52 / 1.10 | 0.62 / 1.21 | 0.46 / 0.99 | 0.65 / 1.37 | 0.61 / 1.18 | 0.49 / 1.02 |
| temples | 0.29 / 0.59 | 0.25 / 0.49 | 0.28 / 0.57 | 0.26 / 0.50 | 0.28 / 0.57 | 0.28 / 0.57 | 0.23 / 0.51 |
| scalp | - | - | - | - | - | - | - |
| face | 0.39 / 0.83 | 0.36 / 0.74 | 0.37 / 0.77 | 0.33 / 0.69 | 0.39 / 0.82 | 0.37 / 0.77 | 0.31 / 0.64 |
| share of GNM face verts compared | 90 % | 90 % | 90 % | 90 % | 90 % | 90 % | 88 % |
| distance from class mean: norm (max sd) | 15.4 (3.0) | 21.3 (3.0) | 14.3 (3.0) | 20.3 (3.0) | 15.4 (3.6) | 14.3 (3.1) | 15.5 (3.0) |
| scan scale | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.7800 |

measures of p1b3 (mm): jaw_width 105.6, gonial_width 117.0, chin_width 64.9, cheekbone_width 132.3, skull_width 153.7, pupils_apart 58.8, nose_width 29.7, mouth_width 47.6, chin_length 30.4, nose_length 54.2
the sex's class mean laid on p1b3 by a similarity: scale 0.954 (the fitted head is -4.6 % the class mean's size); class mean: jaw_width 115.4, gonial_width 129.9, chin_width 64.3, cheekbone_width 136.4, skull_width 153.3, pupils_apart 62.0

Read of the numbers:
- **GNM's ceiling on these three real heads is 0.4-0.6 mm mean, 0.8-1.0 mm p90 over the face.** Every identity-carrying
  region (forehead, nose, cheeks, lips, chin, jaw line) is at 0.3-0.5 mm mean. The prior at x0.25 and the expression
  nuisance each buy 0.02-0.06 mm; removing the 3 sd bound buys nothing (the unbounded fits go to 3.6-4.4 sd on a few
  components for the same distance).
- The price is in the prior: the fits stand 15-19 from the class mean in identity norm with several components AT the
  3 sd bound (x0.25: 21-25). A typical N(0, 1) draw of 170 components has norm 13; the block-in's solved heads end at
  12-15. Real heads are not "near the mean plus a little".
- Exceptions: the Lee Perry-Smith head's eye sockets (1.5 mm: the lids are shut; with the wink directions 1.2) and its
  under-chin (2 mm mean, 4.6 p90: his throat's fold under the jaw), ears everywhere (0.6-1.0 mean, 1.4-2.2 p90: the
  inner relief), his scalp (0.6 / 1.3: a patch 2-3 mm proud at the back of the crown that the bound does not let GNM make).
- SIZE: the scans have real scale (HSRD in metres: statures 1.87 / 1.70 m in shoes against 180 / 165 cm stated; the LPS
  head's units behave as metres). The fitted heads are -1.6 % (LPS), +6.8 % (HSR0040) and -4.6 % (HSR0112, a woman
  against the female mean) of their sex's class mean: **GNM's size is right for real heads.** But with the scan's
  scale left FREE the fit drifts to 0.76-0.81 at the same prior cost and the same relative distance: GNM's identity
  prior does not pin a head's size (which is why pictures cannot either: every camera's distance is free).

### What GNM cannot make (LOOKED AT, tile by tile, scan beside the direct fit)
- FOLDS and BREAKS, all of them. Nasolabial folds come out as a shallow groove (the fold's wall is 1-2 mm of red / blue
  stripe on both HSRD heads); marionette lines, the vertical lines above the upper lip, crow's feet, the throat's bands
  are gone; the jowl and the pre-jowl notch are smoothed into one taut jaw line; the fold under the chin is filled.
- HOODED upper lids: the scan's lid skin hangs over the crease to the lashes; GNM gives an open, standard lid with a
  clean crease. Eye bags are flattened. Shut lids need the expression directions (the identity cannot shut an eye).
- Hair's own thickness: brows stand 0.5-1 mm proud on the scans (not skin; GNM has none), stubble is under the noise.
- The ear's inner relief (helix rim, antihelix, concha) is 1-2 mm off in places although the ear's size, angle and
  outline are right. Asymmetry is followed only a little (one cheek +3 mm on HSR0112).
- Net effect on a 50- and a 60-year-old: the same bone structure, ~25 years younger. This is the job of the fold
  layer (skin_folds) and of expression, not of identity.
- What it DOES make, to the eye and to the numbers: the nose (profile line, tip, wings, nostrils from below), the lips'
  outline and fullness, the chin's shape, the jaw's width and angle, cheekbones, the forehead's slope.

## PART 2: the pipeline on real heads with known shape (gmk.py, gchain.py, gscore.py, gsum.py; COMPUTED unless said;
## LOOKED AT: the reference pictures out/pics_*.png, gt_02_pipeline.png and the three gt_02_pipeline_<scan>_features.png)
Set-up, the same for every head: the truth model gt_<k>_T = a GNM-native block-in start with the Part 1 fit's identity;
pictures 1152 x 1536 at 3.5 px / mm through TRUE cameras; set A = front, ~45, ~90 (72 / 90 views carry 8 "clicks" =
the truth's landmarks through the true camera +-2 px, as the solvecams benchmark; the rest the detector's points);
block_in_start(sex, the person's age, native, cameras fitted) then block_in_solve x8, cameras "free", dense off and on
(pilot network hm18). Two starts: block_in_start's own cameras ("start fitted") and the TRUE cameras with the front
one pitched +8 deg. Scores of the 8th call:
- against the SCAN: the head laid on the scan by its own best pose AND scale (so size and placement are forgiven:
  shape only), two-sided surface distance by region, as Part 1;
- against the Part 1 fit: errmap (GNM vertex to vertex after a similarity) and the measures. NOTE the truth identity is
  itself only pinned ACROSS the surface: two Part 1 variants of one scan differ by 0.6-1.3 mm in errmap's face rms,
  1-3.7 mm in jaw_width, 0.6-1.4 mm in the nose's base width. Vertex-to-vertex numbers under ~1.3 mm and width errors
  under ~2 mm are inside that; the surface distance has no such floor (the ceiling's own 0.4-0.6 mm).

### 2a. The Lee Perry-Smith head: our own pictures of the scan (textured, two lights, a plain grey backdrop: rast.py;
### 85 mm, 0.78 m; f / q45 / s90 with the benchmark's jitter). His eyes are SHUT: the solve still made 8 "iris" reads of
### nothing, so the chains below ran with the iris reads switched off (noiris; with them on the numbers are the same
### to 0.05 mm: out/sum_lps.md)
#### lps: against the SCAN's surface, mean / p90 mm (each head laid on the scan by its own best pose and scale)

| region | class mean | ceiling (Part 1) | off | on | off, true cams +8 pitch | on, true cams +8 pitch |
|---|---|---|---|---|---|---|
| forehead | 2.56 / 4.36 | 0.52 / 0.98 | 1.30 / 2.78 | 1.07 / 2.28 | 1.10 / 2.27 | 1.10 / 2.32 |
| brow | 1.80 / 2.95 | 0.44 / 0.86 | 0.86 / 1.82 | 1.00 / 2.07 | 0.77 / 1.82 | 1.02 / 2.00 |
| eye sockets | 2.07 / 3.69 | 1.52 / 2.46 | 1.94 / 3.00 | 3.35 / 8.21 | 2.12 / 3.45 | 3.34 / 8.29 |
| nose | 1.27 / 2.46 | 0.37 / 0.59 | 1.76 / 2.73 | 1.08 / 2.21 | 1.59 / 2.53 | 1.18 / 2.43 |
| cheeks | 2.25 / 4.83 | 0.35 / 0.69 | 1.06 / 2.09 | 1.12 / 2.19 | 1.07 / 2.11 | 1.12 / 2.23 |
| lips | 1.59 / 3.56 | 0.31 / 0.65 | 1.52 / 2.61 | 0.65 / 1.36 | 1.37 / 2.34 | 0.65 / 1.36 |
| chin | 1.17 / 2.45 | 0.31 / 0.55 | 2.02 / 3.64 | 1.83 / 3.19 | 2.15 / 3.75 | 1.98 / 3.41 |
| jaw line | 5.93 / 8.23 | 0.40 / 0.74 | 2.87 / 3.95 | 4.05 / 5.56 | 2.58 / 3.79 | 3.94 / 5.45 |
| under-chin | 4.08 / 4.56 | 1.95 / 4.60 | 2.82 / 4.50 | 1.92 / 2.79 | 1.76 / 3.15 | 2.99 / 4.34 |
| ears | 3.57 / 6.52 | 1.05 / 2.19 | 3.36 / 7.01 | 3.87 / 7.81 | 3.51 / 7.66 | 3.94 / 7.97 |
| temples | 5.16 / 7.17 | 0.52 / 1.08 | 3.73 / 5.07 | 3.41 / 5.07 | 3.39 / 4.84 | 3.35 / 5.02 |
| scalp | 1.30 / 3.14 | 0.61 / 1.28 | 3.93 / 13.89 | 1.40 / 3.20 | 4.11 / 14.33 | 1.43 / 3.32 |
| face | 2.23 / 4.92 | 0.57 / 0.82 | 1.62 / 3.01 | 1.71 / 3.56 | 1.56 / 2.80 | 1.73 / 3.56 |
| scan scale to fit (1 = the head has the real size) | 0.953 | 1.000 | 0.998 | 0.966 | 0.999 | 0.965 |

#### lps: against the Part 1 direct fit (GNM vertex to vertex after a similarity: errmap), and the acceptance measures (solved - fit, mm)

| chain | calls | face rms | lower face rms | size % | jaw_width | gonial_width | chin_width | cheekbone_width | distance from the fit (identity norm) |
|---|---|---|---|---|---|---|---|---|---|
| start (class mean) | 0 | 2.85 | 3.56 | +1.6 | +9.3 | +8.9 | +2.0 | +5.2 | 18.9 |
| off | 8 | 3.65 (best call 3.38) | 6.32 | +1.9 | +6.6 | +8.6 | +0.1 | +3.4 | 21.3 |
| on | 8 | 2.33 (best call 2.33) | 3.32 | +1.5 | +8.1 | +6.4 | +1.3 | +2.3 | 19.4 |
| off, true cams +8 pitch | 8 | 3.51 (best call 3.42) | 5.87 | +1.9 | +4.8 | +6.9 | +0.7 | +2.8 | 21.4 |
| on, true cams +8 pitch | 8 | 2.36 (best call 2.36) | 3.45 | +1.6 | +8.4 | +6.1 | +1.9 | +2.3 | 19.4 |

#### lps: recovered cameras against the true ones (last call): yaw / pitch / roll deg, distance %, picture scale %

| chain | f | q45 | s90 |
|---|---|---|---|
| off | +0.1 / -3.3 / +0.1, dist +8 %, scale -7.4 % | +1.5 / +7.3 / -1.4, dist +31 %, scale -2.4 % | +5.1 / -17.8 / -3.0, dist -5 %, scale +5.0 % |
| on | +0.2 / +0.8 / -0.2, dist +54 %, scale -5.2 % | +0.5 / +2.1 / -1.3, dist +153 %, scale -2.4 % | +2.5 / +0.4 / -1.1, dist +72 %, scale -0.1 % |
| off, true cams +8 pitch | +0.4 / -3.9 / +0.0, dist +26 %, scale -6.7 % | +0.4 / +6.0 / -1.9, dist +37 %, scale -3.7 % | +5.5 / -15.3 / -3.1, dist +4 %, scale +2.1 % |
| on, true cams +8 pitch | +0.3 / +0.8 / -0.2, dist +82 %, scale -5.6 % | +0.5 / +2.1 / -1.6, dist +152 %, scale -2.3 % | +2.5 / +0.3 / -1.6, dist +67 %, scale -0.1 % |
| start (as given to the solve of the first chain) | -1.5 / +0.4 / -0.6, dist -10 %, scale -6.0 % | -9.1 / +5.3 / +1.2, dist -13 %, scale -5.5 % | -2.7 / -1.1 / +0.2, dist -15 %, scale -3.2 % |

#### lps: nose and lips, signed (solved - Part 1 fit, mm; the solved head scaled onto the fit)

| measure | truth mm | class mean - truth | off - truth | on - truth | off, true cams +8 pitch - truth | on, true cams +8 pitch - truth |
|---|---|---|---|---|---|---|
| alar_width | 41.0 | +3.6 | +0.3 | +0.5 | -0.3 | +0.7 |
| nose_base_width | 32.9 | +2.6 | -1.1 | -0.7 | -2.2 | -0.6 |
| tip_width | 18.4 | +1.0 | -0.5 | -0.2 | -0.9 | +0.3 |
| tip_radius_h | 10.3 | +0.8 | -1.0 | -0.4 | -1.3 | -0.0 |
| tip_radius_v | 9.8 | +1.4 | +0.5 | +0.7 | +0.3 | +0.9 |
| nose_length | 50.7 | -0.4 | +0.3 | -0.1 | +0.5 | -0.2 |
| nose_projection | 15.0 | -1.0 | -1.8 | -1.2 | -1.9 | -1.3 |
| nostril_show | 13.4 | +0.8 | +0.5 | +0.5 | +1.0 | +0.6 |
| mouth_width | 47.8 | +5.3 | +0.2 | +1.4 | -0.1 | +1.3 |
| upper_vermilion_mid | 4.6 | +0.5 | +1.2 | +1.5 | +1.1 | +1.5 |
| upper_vermilion_quarter | 6.2 | +0.3 | +1.0 | +1.6 | +0.9 | +1.7 |
| lower_vermilion_mid | 6.4 | +0.7 | +1.9 | +1.8 | +2.0 | +1.9 |
| lower_vermilion_quarter | 5.7 | +1.3 | +1.9 | +1.6 | +2.0 | +1.7 |
| cupid_bow | 0.8 | -0.2 | -0.4 | -0.6 | -0.3 | -0.5 |
| seam_curve | 2.0 | -0.6 | +0.3 | +1.3 | +0.3 | +1.3 |

### 2b. HSRD-100: REAL photos (each rig camera's head view; the pictures show the rig behind the head, so the outline
### comes from the face parser, not the plain-backdrop reader). The cameras used: HSR0040: A05 (turn 0.4), B04 (44.0),
### BC01 (87.7); HSR0112: A05 (4.7), B04 (49.5), B03 (90.8); all level within 4 deg, 2.1-2.5 m away, i.e. 230-270 mm
### by the width convention. "lens told" = the same with each picture's lens_mm given (see "The lens number" below:
### these two columns were told a lens 39 % too long; the corrected runs are in the phone section's table)
#### HSR0040-Body-023: against the SCAN's surface, mean / p90 mm (each head laid on the scan by its own best pose and scale)

| region | class mean | ceiling (Part 1) | off, start fitted | on, start fitted | off, true cams +8 pitch | on, true cams +8 pitch | off, lens told x1.39 | on, lens told x1.39 |
|---|---|---|---|---|---|---|---|---|
| forehead | 1.53 / 2.69 | 0.36 / 0.76 | 0.89 / 1.68 | 0.72 / 1.39 | 0.91 / 1.64 | 0.69 / 1.38 | 0.62 / 1.27 | 0.76 / 1.46 |
| brow | 1.04 / 2.13 | 0.62 / 1.35 | 0.99 / 2.08 | 0.97 / 1.88 | 1.12 / 2.15 | 0.89 / 1.81 | 0.87 / 1.76 | 1.03 / 2.06 |
| eye sockets | 1.26 / 2.53 | 0.54 / 1.13 | 0.80 / 1.75 | 1.10 / 2.40 | 1.25 / 2.40 | 1.01 / 2.13 | 1.12 / 2.30 | 1.20 / 2.48 |
| nose | 1.82 / 3.29 | 0.39 / 0.81 | 0.89 / 1.69 | 0.92 / 2.05 | 1.21 / 2.57 | 0.93 / 2.12 | 1.16 / 2.70 | 0.97 / 2.18 |
| cheeks | 1.22 / 2.81 | 0.39 / 0.80 | 0.97 / 1.87 | 0.98 / 2.00 | 1.33 / 2.91 | 0.98 / 2.01 | 1.24 / 2.70 | 1.00 / 2.00 |
| lips | 0.73 / 1.47 | 0.48 / 0.96 | 0.88 / 1.85 | 0.68 / 1.38 | 1.27 / 2.62 | 0.67 / 1.35 | 1.17 / 2.43 | 0.66 / 1.31 |
| chin | 1.02 / 2.07 | 0.39 / 0.81 | 0.81 / 1.58 | 1.10 / 1.78 | 1.00 / 1.92 | 1.18 / 1.92 | 0.72 / 1.67 | 1.27 / 2.01 |
| jaw line | 1.47 / 3.06 | 0.34 / 0.76 | 0.83 / 1.48 | 1.11 / 2.01 | 1.47 / 2.58 | 1.21 / 2.44 | 1.27 / 2.52 | 1.17 / 2.29 |
| under-chin | 4.85 / 7.91 | 0.25 / 0.64 | 1.14 / 2.89 | 0.96 / 1.29 | 3.74 / 6.32 | 0.71 / 1.08 | 1.73 / 4.02 | 0.81 / 1.45 |
| ears | 3.96 / 7.46 | 0.89 / 1.85 | 2.31 / 4.84 | 3.35 / 7.10 | 2.77 / 5.53 | 3.46 / 6.78 | 2.81 / 5.50 | 3.43 / 6.78 |
| temples | 1.97 / 3.93 | 0.52 / 0.97 | 1.02 / 1.87 | 1.19 / 2.24 | 1.75 / 3.61 | 1.51 / 3.26 | 1.41 / 3.17 | 1.36 / 2.73 |
| scalp | 2.31 / 3.00 | 0.40 / 0.85 | 0.85 / 1.93 | 0.82 / 1.82 | 1.24 / 2.02 | 0.76 / 1.62 | 0.94 / 1.64 | 0.62 / 1.46 |
| face | 1.27 / 2.63 | 0.45 / 0.95 | 0.89 / 1.78 | 0.95 / 1.95 | 1.24 / 2.54 | 0.95 / 1.96 | 1.08 / 2.38 | 1.01 / 2.06 |
| scan scale to fit (1 = the head has the real size) | 0.903 | 0.999 | 0.947 | 0.922 | 0.917 | 0.921 | 0.915 | 0.914 |

#### HSR0040-Body-023: against the Part 1 direct fit (GNM vertex to vertex after a similarity: errmap), and the acceptance measures (solved - fit, mm)

| chain | calls | face rms | lower face rms | size % | jaw_width | gonial_width | chin_width | cheekbone_width | distance from the fit (identity norm) |
|---|---|---|---|---|---|---|---|---|---|
| start (class mean) | 0 | 3.01 | 4.05 | -6.3 | -2.8 | -7.2 | +0.8 | -0.3 | 15.7 |
| off, start fitted | 8 | 2.01 (best call 2.01) | 2.90 | -6.3 | +2.0 | +3.8 | -2.4 | +1.0 | 15.7 |
| on, start fitted | 8 | 2.39 (best call 2.34) | 3.94 | -6.2 | -3.4 | -4.9 | +0.1 | +0.6 | 16.7 |
| off, true cams +8 pitch | 8 | 2.52 (best call 2.27) | 3.72 | -6.1 | -3.0 | -1.4 | -5.7 | -3.7 | 15.6 |
| on, true cams +8 pitch | 8 | 2.31 (best call 2.31) | 3.99 | -6.1 | -1.7 | -4.6 | +0.3 | +0.0 | 15.8 |
| off, lens told x1.39 | 8 | 2.50 (best call 2.43) | 3.79 | -6.3 | -0.8 | +0.2 | -5.3 | -2.3 | 15.8 |
| on, lens told x1.39 | 8 | 2.52 (best call 2.39) | 4.22 | -6.2 | -3.8 | -6.2 | +0.2 | -0.6 | 16.6 |

#### HSR0040-Body-023: recovered cameras against the true ones (last call): yaw / pitch / roll deg, distance %, picture scale %

| chain | f | q45 | s90 |
|---|---|---|---|
| off, start fitted | +1.3 / -2.5 / -0.6, dist -60 %, scale +7.4 % | -0.4 / +0.9 / -0.5, dist -74 %, scale +7.1 % | -3.9 / -5.1 / -2.1, dist -75 %, scale +7.5 % |
| on, start fitted | +1.4 / -1.6 / -0.7, dist +11 %, scale +8.6 % | -2.6 / +1.1 / -0.9, dist -67 %, scale +6.0 % | +3.5 / +1.9 / -1.2, dist -29 %, scale +6.5 % |
| off, true cams +8 pitch | +1.6 / -2.1 / -0.5, dist +12 %, scale +6.0 % | +0.2 / -1.1 / +0.1, dist -15 %, scale +6.2 % | +6.7 / +6.7 / +0.1, dist +1 %, scale +10.1 % |
| on, true cams +8 pitch | +1.3 / -1.4 / -0.8, dist +94 %, scale +8.2 % | -2.1 / +1.7 / -1.0, dist -66 %, scale +5.8 % | +4.2 / +1.6 / -1.5, dist +29 %, scale +6.1 % |
| off, lens told x1.39 | +1.5 / -2.4 / -0.6, dist +42 %, scale +7.0 % | +1.2 / -0.5 / -0.0, dist +16 %, scale +7.4 % | +12.3 / +8.9 / +0.5, dist +26 %, scale +10.9 % |
| on, lens told x1.39 | +1.3 / -0.8 / -0.7, dist +130 %, scale +8.4 % | -2.5 / +1.4 / -1.2, dist -63 %, scale +6.5 % | +4.3 / +1.3 / -1.4, dist +77 %, scale +6.8 % |
| start (as given to the solve of the first chain) | +0.1 / -1.6 / -0.7, dist -74 %, scale +7.0 % | +1.2 / +1.6 / -2.1, dist -74 %, scale +5.9 % | -2.5 / +5.3 / -3.0, dist -75 %, scale +7.3 % |

#### HSR0040-Body-023: nose and lips, signed (solved - Part 1 fit, mm; the solved head scaled onto the fit)

| measure | truth mm | class mean - truth | off, start fitted - truth | on, start fitted - truth | off, true cams +8 pitch - truth | on, true cams +8 pitch - truth | off, lens told x1.39 - truth | on, lens told x1.39 - truth |
|---|---|---|---|---|---|---|---|---|
| alar_width | 43.2 | +5.2 | +0.7 | +2.8 | +1.0 | +3.0 | +1.1 | +2.9 |
| nose_base_width | 33.8 | +4.7 | +3.9 | +5.0 | +3.3 | +4.9 | +3.5 | +4.9 |
| tip_width | 20.5 | -0.3 | -1.1 | -1.9 | -1.0 | -1.6 | -0.9 | -1.7 |
| tip_radius_h | 18.4 | -6.4 | -2.8 | -7.3 | -3.0 | -7.0 | -3.1 | -7.1 |
| tip_radius_v | 10.7 | +1.5 | -0.3 | -0.7 | +0.4 | -0.5 | +0.6 | -0.7 |
| nose_length | 53.4 | +1.3 | -0.3 | -0.8 | +1.7 | -0.7 | +1.8 | -0.8 |
| nose_projection | 17.9 | -2.7 | -1.0 | -0.8 | -0.5 | -0.9 | -1.2 | -0.7 |
| nostril_show | 15.3 | +0.2 | +1.7 | +0.2 | +2.7 | +0.5 | +2.6 | +0.3 |
| mouth_width | 53.9 | +3.8 | -0.4 | +0.9 | +1.0 | +0.7 | +0.9 | +0.1 |
| upper_vermilion_mid | 4.5 | +1.0 | -0.3 | +0.5 | +0.3 | +0.5 | +0.4 | +0.6 |
| upper_vermilion_quarter | 5.9 | +1.2 | -0.3 | +0.6 | +0.2 | +0.7 | +0.3 | +0.7 |
| lower_vermilion_mid | 6.1 | +1.6 | +0.6 | +0.4 | +1.2 | +0.5 | +1.4 | +0.7 |
| lower_vermilion_quarter | 6.1 | +1.5 | +0.6 | +0.2 | +1.2 | +0.3 | +1.4 | +0.5 |
| cupid_bow | 1.3 | -0.5 | -0.1 | -0.3 | -0.2 | -0.3 | -0.2 | -0.3 |
| seam_curve | 1.0 | +0.5 | -0.4 | -0.1 | -0.7 | +0.1 | -0.8 | +0.2 |

#### HSR0112-Body-018: against the SCAN's surface, mean / p90 mm (each head laid on the scan by its own best pose and scale)

| region | class mean | ceiling (Part 1) | off, start fitted | on, start fitted | off, true cams +8 pitch | on, true cams +8 pitch | off, lens told x1.39 | on, lens told x1.39 |
|---|---|---|---|---|---|---|---|---|
| forehead | 1.03 / 1.80 | 0.30 / 0.73 | 0.65 / 1.25 | 0.47 / 1.02 | 1.62 / 2.84 | 0.58 / 1.22 | 1.20 / 2.33 | 0.48 / 1.04 |
| brow | 0.94 / 1.88 | 0.44 / 0.95 | 1.32 / 2.50 | 0.75 / 1.63 | 1.73 / 3.05 | 0.94 / 1.86 | 1.26 / 2.24 | 0.82 / 1.66 |
| eye sockets | 1.57 / 2.79 | 0.40 / 0.80 | 0.97 / 1.99 | 0.85 / 1.81 | 1.16 / 2.33 | 0.86 / 1.76 | 1.01 / 2.17 | 0.85 / 1.75 |
| nose | 2.10 / 4.68 | 0.42 / 0.87 | 0.98 / 1.95 | 0.84 / 1.69 | 1.28 / 2.41 | 0.86 / 1.82 | 1.09 / 2.16 | 0.82 / 1.77 |
| cheeks | 1.56 / 3.53 | 0.42 / 0.95 | 2.09 / 4.08 | 1.79 / 3.61 | 2.13 / 4.04 | 1.39 / 2.93 | 1.80 / 3.62 | 1.45 / 3.00 |
| lips | 1.43 / 2.70 | 0.35 / 0.72 | 1.31 / 2.34 | 1.57 / 2.72 | 1.26 / 2.04 | 1.35 / 2.22 | 1.11 / 1.86 | 1.19 / 2.02 |
| chin | 1.85 / 3.28 | 0.36 / 0.75 | 1.68 / 2.91 | 1.40 / 2.34 | 1.32 / 2.36 | 1.26 / 2.24 | 1.63 / 2.91 | 1.53 / 2.73 |
| jaw line | 3.01 / 4.62 | 0.38 / 0.81 | 2.14 / 4.54 | 0.85 / 1.96 | 2.45 / 4.60 | 0.67 / 1.46 | 2.40 / 4.07 | 0.71 / 1.50 |
| under-chin | 2.66 / 5.54 | 0.27 / 0.45 | 1.94 / 2.96 | 2.95 / 5.94 | 1.82 / 2.50 | 2.67 / 5.65 | 1.91 / 2.58 | 3.08 / 5.71 |
| ears | 1.57 / 2.86 | 0.63 / 1.36 | 1.87 / 3.76 | 1.49 / 3.36 | 1.86 / 4.01 | 1.53 / 3.11 | 1.94 / 4.06 | 1.75 / 3.40 |
| temples | 0.72 / 1.38 | 0.28 / 0.57 | 2.61 / 3.10 | 0.58 / 1.00 | 3.38 / 3.87 | 0.82 / 1.31 | 3.64 / 4.11 | 0.93 / 1.39 |
| scalp | - | - | - | - | - | - | - | - |
| face | 1.68 / 3.62 | 0.39 / 0.82 | 1.44 / 2.94 | 1.16 / 2.49 | 1.61 / 3.19 | 1.05 / 2.13 | 1.42 / 3.00 | 1.04 / 2.18 |
| scan scale to fit (1 = the head has the real size) | 1.020 | 1.000 | 1.011 | 1.013 | 1.000 | 1.014 | 1.005 | 1.009 |

#### HSR0112-Body-018: against the Part 1 direct fit (GNM vertex to vertex after a similarity: errmap), and the acceptance measures (solved - fit, mm)

| chain | calls | face rms | lower face rms | size % | jaw_width | gonial_width | chin_width | cheekbone_width | distance from the fit (identity norm) |
|---|---|---|---|---|---|---|---|---|---|
| start (class mean) | 0 | 3.64 | 3.64 | +4.8 | +4.5 | +6.9 | -3.6 | -2.1 | 15.4 |
| off, start fitted | 8 | 2.41 (best call 2.30) | 3.62 | +4.7 | +1.2 | -0.3 | -6.7 | -6.7 | 16.7 |
| on, start fitted | 8 | 2.38 (best call 2.26) | 3.03 | +4.6 | +2.8 | +1.1 | -2.2 | -2.1 | 16.1 |
| off, true cams +8 pitch | 8 | 2.61 (best call 2.29) | 3.16 | +4.7 | +1.9 | +0.1 | -4.9 | -8.1 | 15.5 |
| on, true cams +8 pitch | 8 | 2.20 (best call 2.15) | 2.51 | +4.6 | +0.6 | -0.5 | -1.7 | -2.0 | 15.5 |
| off, lens told x1.39 | 8 | 2.31 (best call 2.31) | 2.79 | +4.7 | +2.0 | -0.6 | -3.8 | -7.7 | 15.0 |
| on, lens told x1.39 | 8 | 2.22 (best call 2.20) | 2.66 | +4.6 | -0.9 | -1.9 | -2.9 | -2.6 | 15.0 |

#### HSR0112-Body-018: recovered cameras against the true ones (last call): yaw / pitch / roll deg, distance %, picture scale %

| chain | f | q45 | s90 |
|---|---|---|---|
| off, start fitted | -0.2 / -4.4 / +0.1, dist -58 %, scale -0.6 % | -3.7 / +1.8 / -0.3, dist -68 %, scale -3.4 % | -5.5 / +17.6 / -0.7, dist -74 %, scale +0.3 % |
| on, start fitted | -0.4 / -0.9 / +0.1, dist -34 %, scale -0.9 % | -3.1 / +2.3 / +0.2, dist -47 %, scale -3.1 % | +0.2 / +3.1 / -1.6, dist -22 %, scale -2.6 % |
| off, true cams +8 pitch | -0.4 / -2.5 / +0.1, dist +3 %, scale -1.3 % | -1.9 / -1.3 / -0.0, dist +1 %, scale -2.6 % | -2.3 / -5.3 / -0.3, dist +0 %, scale -1.9 % |
| on, true cams +8 pitch | -0.5 / -0.5 / +0.2, dist +1 %, scale -1.2 % | -2.2 / +1.7 / -0.1, dist -7 %, scale -2.6 % | +1.2 / +2.8 / -0.9, dist +51 %, scale -2.6 % |
| off, lens told x1.39 | -0.4 / -2.2 / +0.3, dist +37 %, scale -1.9 % | -1.0 / -0.3 / -0.6, dist +36 %, scale -3.0 % | -1.4 / +0.9 / -1.5, dist +38 %, scale -3.6 % |
| on, lens told x1.39 | -0.4 / -0.4 / +0.1, dist +31 %, scale -1.4 % | -2.5 / +1.7 / -0.1, dist -13 %, scale -3.0 % | +0.9 / +2.9 / -1.2, dist +86 %, scale -2.9 % |
| start (as given to the solve of the first chain) | +3.0 / +2.3 / +0.2, dist -69 %, scale -2.4 % | -0.6 / +2.4 / +2.4, dist -71 %, scale -1.5 % | -11.2 / +2.8 / -4.4, dist -74 %, scale -1.9 % |

#### HSR0112-Body-018: nose and lips, signed (solved - Part 1 fit, mm; the solved head scaled onto the fit)

| measure | truth mm | class mean - truth | off, start fitted - truth | on, start fitted - truth | off, true cams +8 pitch - truth | on, true cams +8 pitch - truth | off, lens told x1.39 - truth | on, lens told x1.39 - truth |
|---|---|---|---|---|---|---|---|---|
| alar_width | 41.0 | +1.2 | +0.3 | +1.4 | +1.3 | +1.7 | +1.2 | +1.6 |
| nose_base_width | 29.7 | +3.0 | +2.7 | +2.8 | +2.1 | +2.5 | +2.0 | +2.5 |
| tip_width | 18.9 | +0.1 | -3.3 | -2.3 | -3.7 | -2.2 | -3.3 | -1.7 |
| tip_radius_h | 11.8 | -1.3 | -3.9 | -2.8 | -4.0 | -2.6 | -3.6 | -2.2 |
| tip_radius_v | 12.9 | -2.8 | -2.0 | -0.8 | -1.2 | -0.8 | -1.8 | -0.8 |
| nose_length | 54.2 | -6.4 | +0.5 | -0.2 | +1.8 | -0.0 | +1.7 | -0.3 |
| nose_projection | 16.1 | -3.3 | -0.5 | -0.4 | -0.0 | -0.0 | +0.8 | +0.1 |
| nostril_show | 14.6 | -1.2 | +1.6 | +1.7 | +1.8 | +1.4 | +2.2 | +1.1 |
| mouth_width | 47.6 | +2.1 | +3.3 | +3.1 | -0.2 | +0.4 | +0.1 | +0.7 |
| upper_vermilion_mid | 2.5 | +2.5 | +1.2 | +1.3 | +0.5 | +0.7 | +0.5 | +0.7 |
| upper_vermilion_quarter | 3.5 | +3.0 | +1.7 | +1.8 | +0.7 | +1.1 | +0.8 | +1.1 |
| lower_vermilion_mid | 3.6 | +3.2 | +0.8 | +0.6 | +0.3 | +0.1 | +0.2 | +0.2 |
| lower_vermilion_quarter | 3.7 | +2.9 | +0.8 | +0.7 | +0.3 | +0.1 | +0.2 | +0.2 |
| cupid_bow | 1.0 | -0.5 | -0.4 | -0.3 | -0.2 | -0.2 | -0.2 | -0.2 |
| seam_curve | 0.8 | +0.7 | +0.7 | +0.8 | -0.3 | +0.4 | -0.1 | +0.4 |

### What the numbers say (Part 2)
| face, mean / p90 mm against the scan | class mean (the start) | dense off | dense on | ceiling |
|---|---|---|---|---|
| Lee Perry-Smith (our renders) | 2.23 / 4.92 | 1.62 / 3.01 | 1.71 / 3.56 | 0.57 / 0.82 |
| HSR0040 (real photos) | 1.27 / 2.63 | 0.89 / 1.78 | 0.95 / 1.95 | 0.45 / 0.95 |
| HSR0112 (real photos) | 1.68 / 3.62 | 1.44 / 2.94 | 1.16 / 2.49 | 0.39 / 0.82 |
- **The picture solve ends at 0.9-1.7 mm mean (1.8-3.6 mm p90) on real anatomy; the ceiling is 0.4-0.6 (0.8-1.0).** It
  closes 20-45 % of the way from the class mean to the ceiling. Dense helps one head of three (HSR0112: 1.44 -> 1.16),
  is neutral on the others by this measure; by errmap it helps the LPS head (3.65 -> 2.33) and HSR0112's lower face.
- WHERE the gap is (regions, dense on, LPS / HSR0040 / HSR0112): jaw line 4.05 / 1.11 / 0.85, chin 1.83 / 1.10 / 1.40,
  cheeks 1.12 / 0.98 / 1.79, lips 0.65 / 0.68 / 1.57, nose 1.08 / 0.92 / 0.84, forehead 1.07 / 0.72 / 0.47, ears 3.9 /
  3.4 / 1.5, temples 3.4 / 1.2 / 0.6. The inner face (nose, lips, eye sockets with open eyes) is at 0.7-1.1 mm = about
  twice the ceiling; WIDTHS and the lower face carry the rest.
- WIDTHS ARE NOT READ. The LPS head has a narrow jaw (108.7 mm against the class mean's 119.9): every chain leaves
  it +5 to +8 mm wide (gonial +6 to +9), dense or not, from either start. HSR0040's head is 6.8 % larger than the mean:
  every chain leaves it at the mean's size (-6.2 %; the cameras' scale takes it, +6-8 %): size is HELD by design. The
  two starts agree with each other (below), so this is a BIAS, not noise: the head goes to the average where no read
  measures a width.
- errmap against the Part 1 fit does NOT fall the way it does on the GNM-native benchmark (1.3-1.5 mm there): 2.0-2.5
  mm on the HSRD heads from 3.0-3.6, and on the LPS head dense off it RISES (2.85 -> 3.65; lower face 3.56 -> 6.3, jaw
  angle 10 mm) while the surface distance falls (2.23 -> 1.62): the solved head lies closer to the scan's surface but
  its vertices have slid along it, and its profile camera has run off (below).
- The solvecams ACCEPTANCE measures on real heads (solved - Part 1 fit, mm; start fitted / true cameras +8 pitch):

| head | dense | jaw_width | gonial_width | chin_width | spread between the two starts (jaw / gonial / chin) | face rms | lower face rms |
|---|---|---|---|---|---|---|---|
| LPS | off | +6.6 / +4.8 | +8.6 / +6.9 | +0.1 / +0.7 | 1.8 / 1.7 / 0.6 | 3.65 / 3.51 | 6.32 / 5.87 |
| LPS | on | +8.1 / +8.4 | +6.4 / +6.1 | +1.3 / +1.9 | 0.3 / 0.3 / 0.6 | 2.33 / 2.36 | 3.32 / 3.45 |
| HSR0040 | off | +2.0 / -3.0 | +3.8 / -1.4 | -2.4 / -5.7 | 5.0 / 5.2 / 3.3 | 2.01 / 2.52 | 2.90 / 3.72 |
| HSR0040 | on | -3.4 / -1.7 | -4.9 / -4.6 | +0.1 / +0.3 | 1.7 / 0.3 / 0.2 | 2.39 / 2.31 | 3.94 / 3.99 |
| HSR0112 | off | +1.2 / +1.9 | -0.3 / +0.1 | -6.7 / -4.9 | 0.7 / 0.4 / 1.8 | 2.41 / 2.61 | 3.62 / 3.16 |
| HSR0112 | on | +2.8 / +0.6 | +1.1 / -0.5 | -2.2 / -1.7 | 2.2 / 1.6 / 0.5 | 2.38 / 2.20 | 3.03 / 2.51 |
  Repeatability (the spread) is met with dense on (0.2-2.2 mm) as on the synthetic benchmark; accuracy is not (face
  2.2-2.4, lower face 2.5-4.0 against the benchmark's 1.3 / 1.8), and half of that is the truth's own vertex ambiguity.
- CAMERAS against the truth (the first real-photo camera truth we have; tables above):
  - block_in_start's fit on REAL photos: yaw within 0.1-3.0 deg on front and 45 views, -2.5 / -11.2 deg on the
    profiles (8 clicks); pitch 1.6-5.3 deg; DISTANCE -69 to -75 %: the 70 mm prior against a head cropped out of a
    photo taken 2.3 m away. A crop of a full-figure photo is always a long lens: tell it (below).
  - dense OFF, 8 calls: the front stays within 4.4 deg, the 45 view within 4 (LPS: +6-7 of pitch); the PROFILE
    camera's pitch runs off: -15 / -18 deg (LPS, both starts), +17.6 (HSR0112), -5 / +7 (HSR0040), with 2-7 deg of yaw: the same on our renders and on real photos. This
    is the "outlines do not pin the profile camera" of solvecams, three times larger on real heads; the head pays in
    the jaw angle and the back of the skull.
  - dense ON: every rotation within 4.2 deg of yaw and 3.1 deg of pitch on all three heads, from both starts.
    The front camera's +8 deg start error comes back to within 1.4 deg (off: 2.1-3.9 past it). DISTANCE is not found by
    either: dense on it wanders -67 .. +190 % (its prior is 40 %), dense off it stays where it started.
  - picture scale ends +6-9 % on HSR0040 (the head held 6 % small), -7 .. +5 % on the others.

### The dense network on REAL photos (glm.py; out/dense_<k>.png LOOKED AT for HSR0040: truth red, network green)
Truth = the Part 1 fit (identity + expression) through each TRUE camera. CAVEAT, measured on the LPS head (OUR render
of real geometry: no photo gap at all): the same comparison gives 2.6-3.8 mm there, with 4-6 mm on the forehead and
9-12 on the bare scalp: that is the truth SLIDING on featureless skin (a surface fit pins a vertex across the surface,
not along it) plus real geometry the network never saw; edges are pinned: nose 1.5, mouth 1.6, lips 1.8, eyes 2.0.
#### HSR0040-Body-023: dense network vs the projected Part 1 fit, mean mm (landmarks the solve would USE: sigma <= 3.0 mm; in brackets: every landmark the camera sees)

| region | f | q23 | q45 | s72 | s90 | fu |
|---|---|---|---|---|---|---|
| brows | 2.4 (2.4) | 2.7 (2.7) | 1.6 (1.6) | 2.8 (2.8) | 5.8 (6.0) | 3.5 (3.5) |
| cheeks | 5.6 (6.5) | 4.1 (4.1) | 3.0 (3.3) | 3.0 (2.9) | 4.3 (4.2) | 3.8 (3.8) |
| chin | 6.3 (6.4) | 5.3 (5.3) | 2.9 (3.3) | 1.1 (1.1) | - (2.7) | 7.7 (7.7) |
| ears | - (16.0) | - (3.5) | - (2.0) | - (2.5) | - (2.8) | - (1.6) |
| eyes | 2.9 (2.9) | 2.1 (2.1) | 2.2 (2.2) | 2.0 (2.0) | 3.8 (3.8) | 2.2 (2.2) |
| forehead | 6.4 (6.4) | 4.8 (4.8) | 2.8 (2.8) | 3.3 (3.1) | - (7.3) | 5.1 (5.1) |
| lids | 3.3 (3.3) | 2.7 (2.7) | 3.5 (3.5) | 2.3 (2.3) | 3.1 (3.1) | 3.1 (3.1) |
| lips | 2.0 (2.0) | 3.3 (3.3) | 2.3 (2.4) | 1.6 (1.6) | 3.7 (3.0) | 1.8 (1.8) |
| mouth | 2.6 (2.6) | 3.0 (3.0) | 2.5 (2.6) | 2.2 (2.2) | 3.2 (3.5) | 3.3 (3.3) |
| nose | 3.3 (3.3) | 3.2 (3.2) | 3.7 (3.7) | 3.1 (3.1) | 4.4 (4.4) | 2.9 (2.9) |
| scalp_neck | - (12.5) | 7.4 (8.7) | - (8.3) | - (8.9) | - (10.8) | 2.6 (9.0) |
| ALL | 4.1 (5.4) | 3.6 (4.0) | 2.6 (3.4) | 2.5 (3.5) | 4.1 (5.8) | 3.5 (4.1) |
| share used | 82 % | 92 % | 75 % | 74 % | 29 % | 89 % |
| error / the network's own sigma (1 = honest) | 1.5 | 1.5 | 0.9 | 0.9 | 1.3 | 1.4 |
| mean offset x, y mm | +0.7, +2.5 | +0.9, +0.4 | +1.1, +0.9 | +1.0, +0.4 | -1.9, +2.1 | +0.1, +0.7 |

HSR0040-Body-023: the network's WIDTHS and HEIGHTS against the truth, front-ish views (network - truth, mm; widths = the widest 40 % of mirror pairs)

| view | region | truth width | network - truth | all pairs | truth height | network - truth |
|---|---|---|---|---|---|---|
| f | nose | 31.9 | +1.9 | +0.6 | 50.8 | +0.3 |
| f | lips | 42.4 | +3.0 | +1.0 | 16.1 | -2.4 |
| f | mouth | 64.7 | +2.5 | +1.3 | 56.5 | +2.7 |
| f | eyes | 104.1 | +4.7 | +2.5 | 35.4 | +4.4 |
| f | chin | 54.9 | -0.8 | -0.6 | 27.4 | +3.1 |
| f | cheeks | 147.7 | +5.1 | +4.7 | 104.3 | +5.3 |
| q23 | nose | 29.3 | +2.8 | +1.4 | 50.5 | +2.1 |
| q23 | lips | 36.2 | +2.4 | +1.0 | 16.0 | -3.4 |
| q23 | mouth | 60.1 | +3.9 | +2.3 | 56.4 | +3.2 |
| q23 | eyes | 99.5 | +3.5 | +2.2 | 35.9 | +4.4 |
| q23 | chin | 42.4 | +0.1 | -0.0 | 27.5 | +2.9 |
| q23 | cheeks | 116.1 | +8.7 | +6.8 | 104.3 | +3.8 |
| fu | nose | 24.8 | +2.1 | +1.0 | 51.7 | +3.4 |
| fu | lips | 40.3 | +3.5 | +1.6 | 16.0 | -1.4 |
| fu | mouth | 61.3 | +3.7 | +2.3 | 57.1 | +7.5 |
| fu | eyes | 97.5 | +3.3 | +2.4 | 36.7 | +3.9 |
| fu | chin | 38.9 | -1.4 | -0.6 | 26.5 | +4.4 |
| fu | cheeks | 114.0 | +8.0 | +6.2 | 108.1 | +8.3 |

#### HSR0112-Body-018: dense network vs the projected Part 1 fit, mean mm (landmarks the solve would USE: sigma <= 3.0 mm; in brackets: every landmark the camera sees)

| region | f | q23 | q45 | s72 | s90 | fu |
|---|---|---|---|---|---|---|
| brows | 3.4 (3.4) | 2.3 (2.3) | 3.0 (3.0) | 3.2 (3.2) | 3.4 (3.4) | 2.8 (2.8) |
| cheeks | 3.7 (3.7) | 3.3 (3.3) | 5.2 (5.2) | 6.3 (5.5) | 5.5 (5.3) | 3.4 (3.4) |
| chin | 3.5 (3.5) | 3.8 (3.8) | 5.6 (5.6) | - (7.9) | 6.3 (6.9) | 2.1 (2.1) |
| ears | - (4.8) | 4.1 (4.4) | 7.8 (8.2) | - (8.8) | - (7.3) | - (5.8) |
| eyes | 5.1 (5.1) | 3.2 (3.2) | 4.7 (4.7) | 4.5 (4.5) | 4.0 (4.0) | 4.5 (4.5) |
| forehead | 3.4 (3.4) | 2.4 (2.4) | 4.1 (4.1) | 4.9 (4.3) | 5.2 (5.2) | 3.0 (3.0) |
| lids | 4.0 (4.0) | 2.3 (2.3) | 3.7 (3.7) | 2.4 (2.4) | - | 4.3 (4.3) |
| lips | 3.1 (3.1) | 3.2 (3.2) | 3.6 (3.6) | 2.4 (2.3) | 2.0 (2.0) | 2.9 (2.9) |
| mouth | 2.9 (2.9) | 2.7 (2.7) | 4.1 (4.1) | 3.0 (4.1) | 2.7 (2.7) | 2.1 (2.1) |
| nose | 2.8 (2.8) | 3.0 (3.0) | 3.7 (3.7) | 6.0 (6.0) | 2.6 (2.6) | 2.0 (2.0) |
| scalp_neck | 3.9 (5.0) | 3.3 (4.8) | 6.7 (8.8) | - (6.8) | - (8.9) | 3.3 (3.6) |
| ALL | 3.6 (3.7) | 3.1 (3.2) | 4.5 (5.0) | 4.7 (5.2) | 4.1 (5.5) | 3.0 (3.2) |
| share used | 91 % | 97 % | 91 % | 52 % | 62 % | 87 % |
| error / the network's own sigma (1 = honest) | 1.6 | 1.5 | 1.8 | 1.6 | 1.3 | 1.2 |
| mean offset x, y mm | +0.9, +1.1 | +1.0, +1.0 | +2.0, +1.7 | +2.7, +2.6 | +2.9, +1.2 | -0.5, +0.8 |

HSR0112-Body-018: the network's WIDTHS and HEIGHTS against the truth, front-ish views (network - truth, mm; widths = the widest 40 % of mirror pairs)

| view | region | truth width | network - truth | all pairs | truth height | network - truth |
|---|---|---|---|---|---|---|
| f | nose | 27.6 | +2.6 | +1.2 | 51.2 | -3.6 |
| f | lips | 36.2 | +2.9 | +1.7 | 13.5 | -2.1 |
| f | mouth | 56.7 | +0.5 | +0.4 | 46.8 | -0.9 |
| f | eyes | 87.7 | +9.4 | +7.4 | 31.6 | +5.5 |
| f | chin | 48.7 | -4.4 | -2.5 | 18.0 | +1.5 |
| f | cheeks | 110.7 | +7.1 | +4.0 | 88.6 | -1.4 |
| q23 | nose | 20.6 | +1.1 | +0.3 | 50.1 | -3.5 |
| q23 | lips | 32.2 | +4.9 | +3.1 | 13.6 | -3.6 |
| q23 | mouth | 50.7 | +2.9 | +2.1 | 46.3 | +0.6 |
| q23 | eyes | 81.2 | +4.1 | +4.0 | 32.8 | +2.6 |
| q23 | chin | 43.7 | -2.5 | -1.6 | 19.1 | +3.4 |
| q23 | cheeks | 92.0 | +4.9 | +2.8 | 89.4 | +1.3 |
| fu | nose | 27.2 | +2.2 | +1.0 | 52.0 | -3.4 |
| fu | lips | 35.8 | +3.9 | +2.5 | 13.8 | -2.9 |
| fu | mouth | 56.0 | +1.6 | +1.1 | 47.3 | -1.1 |
| fu | eyes | 85.3 | +7.8 | +6.3 | 34.0 | +4.2 |
| fu | chin | 57.5 | -3.2 | -3.0 | 18.0 | +0.0 |
| fu | cheeks | 105.9 | +6.6 | +4.2 | 94.3 | -1.4 |

#### lps: dense network vs the projected Part 1 fit, mean mm (landmarks the solve would USE: sigma <= 3.0 mm; in brackets: every landmark the camera sees)

| region | f | q23 | q45 | s72 | s90 | fu |
|---|---|---|---|---|---|---|
| brows | 4.6 (4.6) | 4.5 (4.5) | 3.6 (3.6) | 3.2 (3.2) | 3.1 (3.1) | 4.5 (4.5) |
| cheeks | 2.7 (2.7) | 3.6 (3.6) | 4.5 (4.5) | 3.3 (3.3) | 3.3 (3.3) | 2.7 (2.7) |
| chin | 3.6 (3.6) | 3.2 (3.2) | 1.5 (1.5) | 1.4 (1.4) | 2.0 (2.0) | 2.9 (2.9) |
| ears | 1.6 (1.6) | 2.7 (2.7) | 2.8 (2.8) | 2.3 (2.5) | 2.7 (2.6) | 1.6 (1.6) |
| eyes | 1.9 (1.9) | 2.2 (2.2) | 2.2 (2.2) | 1.8 (1.8) | 2.1 (2.1) | 2.2 (2.2) |
| forehead | 5.3 (5.3) | 5.5 (5.5) | 4.0 (4.0) | 3.9 (3.9) | 3.9 (3.9) | 5.8 (5.8) |
| lids | - | - | - | - | - | - |
| lips | 1.8 (1.8) | 1.8 (1.8) | 2.7 (2.7) | 2.3 (2.3) | 2.4 (2.4) | 1.7 (1.7) |
| mouth | 1.7 (1.7) | 1.4 (1.4) | 1.7 (1.7) | 1.4 (1.4) | 1.6 (1.6) | 1.6 (1.6) |
| nose | 1.5 (1.5) | 1.5 (1.5) | 1.3 (1.3) | 1.5 (1.5) | 1.5 (1.5) | 1.6 (1.6) |
| scalp_neck | 9.2 (9.2) | 12.0 (12.0) | 9.2 (10.9) | 5.1 (9.8) | 5.5 (10.9) | 9.6 (9.6) |
| ALL | 3.4 (3.4) | 3.8 (3.8) | 3.4 (3.9) | 2.6 (3.8) | 2.8 (4.6) | 3.5 (3.5) |
| share used | 100 % | 100 % | 96 % | 83 % | 78 % | 100 % |
| error / the network's own sigma (1 = honest) | 2.1 | 2.3 | 1.6 | 1.1 | 1.1 | 2.3 |
| mean offset x, y mm | -0.5, +0.3 | -0.0, -0.1 | +0.1, -0.1 | +0.8, -0.0 | +0.4, -0.1 | -0.4, +0.5 |

lps: the network's WIDTHS and HEIGHTS against the truth, front-ish views (network - truth, mm; widths = the widest 40 % of mirror pairs)

| view | region | truth width | network - truth | all pairs | truth height | network - truth |
|---|---|---|---|---|---|---|
| f | nose | 30.5 | -0.1 | -0.2 | 48.2 | -2.2 |
| f | lips | 35.3 | -1.3 | -1.4 | 17.9 | -4.0 |
| f | mouth | 55.9 | -3.1 | -2.4 | 53.7 | -1.6 |
| f | eyes | 92.3 | -0.8 | -0.4 | 32.5 | -3.2 |
| f | chin | 48.4 | -1.5 | -1.4 | 27.3 | -2.5 |
| f | cheeks | 118.7 | +2.6 | +0.7 | 101.9 | -5.7 |
| q23 | nose | 21.1 | -0.5 | -0.5 | 46.8 | -2.6 |
| q23 | lips | 30.8 | -1.3 | -1.2 | 17.9 | -4.0 |
| q23 | mouth | 50.9 | -2.4 | -1.9 | 53.2 | -1.2 |
| q23 | eyes | 84.2 | +1.6 | +1.5 | 30.8 | -3.7 |
| q23 | chin | 43.2 | -1.0 | -0.9 | 28.1 | -1.9 |
| q23 | cheeks | 94.6 | +4.4 | +1.9 | 100.4 | -6.5 |
| fu | nose | 31.5 | -0.3 | -0.2 | 50.3 | -2.0 |
| fu | lips | 35.2 | -1.2 | -1.4 | 17.2 | -3.6 |
| fu | mouth | 55.9 | -3.1 | -2.5 | 53.6 | -1.4 |
| fu | eyes | 92.3 | -0.4 | -0.2 | 29.8 | -1.9 |
| fu | chin | 48.5 | -1.2 | -1.3 | 23.6 | -2.3 |
| fu | cheeks | 115.9 | +3.6 | +0.9 | 99.0 | -5.6 |
- REAL photos, landmarks the solve would use: **2.5-4.1 mm mean (HSR0040), 3.0-4.7 mm (HSR0112)**; on edges: nose
  2.8-3.7 (front and 45), lips 2.0-3.6, mouth 2.5-4.1, eyes 2.1-5.1, lids 2.3-4.0. Against the LPS render's edges
  (1.5-2.0) the real-photo increment is about +1 to +1.5 mm; against the network's own synthetic benchmark (1.4-2.0
  mm, fitter_whitepaper.md) it is double. Its own sigma is 1.2-1.8x too sure on HSR0112's photos, 0.9-1.5x on HSR0040's (2.1-2.3x on the LPS front renders).
- It is NOT random: on HSR0040's front it puts the whole chin 6 mm high (it answers a shorter lower face: his is long)
  and pulls the cheeks' and forehead's edges in; on both real heads the mirror-pair WIDTHS come out wide: eyes +4.7 /
  +9.4 mm, cheeks +5.1 / +7.1, lips +3.0 / +2.9, **nose +1.9 / +2.6 mm** (front views; q23: +2.8 / +1.1), while the lip
  region's height is 2-4 mm short. On the LPS render the same widths are -0.1 (nose), -1.3 (lips), -0.8 (eyes).
- So on real photos the network is the average's proportions laid over the person, wider than the person in the
  middle of the face. This is the first sim-to-real number: budget ~3 mm, not 1.5.

## Nose, lips, phone distance (the coordinator's additions, from Joe's read of two phone-photo heads: nose "a little
## too wide and too rounded from the front", one lip shape wrong)
Measures: spikes/groundtruth/noselip.py, on fixed template vertices / the 68 landmarks, the solved head scaled onto the
truth, signed solved - truth; the tables' last block under each head above. The truth's own uncertainty there: 0.6-1.4
mm on the nose's base width, 0.1-0.8 on the tip width, 0.3-0.8 on a vermilion height (Part 1 variants against each other).

### 1. Is there a bias?
| solved - truth, mm (dense off / on; start fitted) | LPS (our renders) | HSR0040 (real photos) | HSR0112 (real photos) | the class mean's own error |
|---|---|---|---|---|
| nose base width (sills, lm 31-35) | -1.5 / -0.4 | **+3.9 / +5.0** | **+2.7 / +2.8** | +2.6 / +4.7 / +3.0 |
| alar width (wings) | -0.1 / +0.7 | +0.7 / **+2.8** | +0.3 / +1.4 | +3.6 / +5.2 / +1.2 |
| tip width | -0.8 / +0.1 | -1.1 / -1.9 | -3.3 / -2.3 | +1.0 / -0.3 / +0.1 |
| tip radius, horizontal (+ = rounder) | -1.2 / -0.1 | -2.8 / -7.3 | -3.9 / -2.8 | +0.8 / -6.4 / -1.3 |
| nose projection | -2.2 / -1.2 | -1.0 / -0.8 | -0.5 / -0.4 | -1.0 / -2.7 / -3.3 |
| mouth width | +0.3 / +1.1 | -0.4 / +0.9 | +3.3 / +3.1 | +5.3 / +3.8 / +2.1 |
| upper vermilion, midline | +1.2 / +1.4 | -0.3 / +0.5 | +1.2 / +1.3 | +0.5 / +1.0 / +2.5 |
| lower vermilion, midline | +1.8 / +1.9 | +0.6 / +0.4 | +0.8 / +0.6 | +0.7 / +1.6 / +3.2 |
- **YES for the nose's WIDTH at the base, on real photos only: +2 to +5 mm on both HSRD heads, in all 18 chains
  (dense off and on, both starts, lens untold / told x1.39 / told right / distance held; range +2.0 .. +5.3), i.e. the solve leaves 65-105 % of the class mean's error in
  place; with dense on the wings are +1.4 / +2.8 too.** On our own renders of a real nose (LPS) the width comes out
  right (-1.5 / -0.4). The tip is NOT rounder or wider on these heads (it comes out 1-3 mm narrow and sharper); the
  nose is 0.4-2.5 mm short of its projection everywhere. So "too wide from the front": measured, real-photo-specific;
  "too rounded": not reproduced on these two noses from 2.3 m (but see the phone distance below).
- LIPS: toward FULLER than the person, +0.4 to +1.9 mm on a vermilion height in 11 of 12 cells, on renders and photos
  alike; the two thin-lipped heads (LPS 4.6 / 6.4 mm, HSR0112 2.5 / 3.6) keep +1.2-1.9 and +0.6-1.3. Cupid's bow is
  0.1-0.5 mm flat in every chain. Mouth width is read well when the cameras are right (within 1.6 mm from the true
  start), HSR0112 start-fitted +3.2.
### Which read sets the nose's width, and what do the detectors say there?
- The solve's own report (MOVED WITH NO READ / "carried by"): nose_width is carried by **"landmark front" = the
  DIFFERENTIAL detector anchors** (MediaPipe on the picture minus MediaPipe on our clay render of the model: 51 points,
  1.0-1.5 mm, correlated), read share 0.68-0.79; with dense on the network's nose landmarks join (floor 1.2 mm). There
  is NO read of the wings' edge, the nostrils or the alar crease themselves: the outline reads only the tip's
  projection and upturn in the profile ("carried by outline profile").
- BOTH detectors are wide on a real nose and right on our render of one (measured AT THE TRUTH, front pictures):
lps: detector on the picture - detector on the truth's render, mm (front-ish views)

| measure | f (on the render: mm) |
|---|---|
| nose base width (31-35) | -0.1 (22.9) |
| mouth width (48-54) | -3.0 (46.2) |
| eyes outer (36-45) | +1.6 (86.6) |
| eyes inner (39-42) | +0.1 (33.3) |
| jaw width (4-12) | +2.4 (105.6) |
| chin width (6-10) | +2.0 (60.8) |
| upper lip height (51-62) | +1.1 (4.4) |
| lower lip height (66-57) | +2.4 (6.3) |
| nose length (27-33) | +3.6 (42.7) |
| philtrum (33-51) | -3.3 (19.6) |
| chin height (57-8) | +0.2 (38.4) |

h40: detector on the picture - detector on the truth's render, mm (front-ish views)

| measure | f (on the render: mm) |
|---|---|
| nose base width (31-35) | +1.7 (24.7) |
| mouth width (48-54) | -1.7 (55.0) |
| eyes outer (36-45) | -2.4 (94.5) |
| eyes inner (39-42) | +0.5 (34.1) |
| jaw width (4-12) | +1.8 (132.1) |
| chin width (6-10) | +3.0 (72.0) |
| upper lip height (51-62) | +0.3 (5.3) |
| lower lip height (66-57) | -0.1 (7.3) |
| nose length (27-33) | +1.9 (50.7) |
| philtrum (33-51) | -1.8 (23.1) |
| chin height (57-8) | +2.7 (42.0) |

h112: detector on the picture - detector on the truth's render, mm (front-ish views)

| measure | f (on the render: mm) |
|---|---|
| nose base width (31-35) | +1.6 (23.7) |
| mouth width (48-54) | +0.3 (46.6) |
| eyes outer (36-45) | +1.4 (81.0) |
| eyes inner (39-42) | +0.1 (31.4) |
| jaw width (4-12) | -3.1 (107.4) |
| chin width (6-10) | -1.9 (59.4) |
| upper lip height (51-62) | +1.0 (2.6) |
| lower lip height (66-57) | +0.5 (3.7) |
| nose length (27-33) | +3.1 (49.0) |
| philtrum (33-51) | -0.5 (18.2) |
| chin height (57-8) | -0.1 (35.5) |
  MediaPipe's differential read asks for a nose base +1.7 / +1.6 mm wider than the true head's on the two real
  photos and -0.1 on the LPS render; the dense network's nose pairs +1.9 / +2.6 on the photos, -0.1 on the render.
  A sim-to-real gap in BOTH readers: our clay / dressed renders of a nose do not look to a detector like a photograph
  of the same nose (no alar shadow, nostril rim, skin-tone edge), so "the same detector on both" does not cancel.
  The same table shows the lips: MediaPipe's differential lip heights are +1.1 / +2.4 mm on the LPS render and
  +0.3..+1.0 on the photos: the fuller lips above; and its jaw / chin widths are off by 2-4 mm with either sign.

### 2. Phone distance (gphone.py, fixlens.py, gphtab.py; the Lee Perry-Smith scan drawn by us, eyes shut -> iris reads
### off; pictures LOOKED AT: out/pics_ph.png)
The scan through a wide camera at 0.30 m and 0.40 m (1728 x 2304, f = 1152 px: 3.8 / 2.9 px per mm at the head; the
nose plainly enlarged, the ears half hidden from the front) and from 1.75 m through the lens that frames the head the
same (1152 x 1536); front / 45 / 90 each. (a) lens told, dense off; (b) lens told, dense on (distance prior 40 %);
(c) dense on, the distance prior tightened to 5 % (face_ruler.PHOTO_CAM_DIST_DENSE). 6 calls each.

**The lens number (found on the way, and it matters for every "lens told" run).** A view's `lens_mm` is read as EXIF's
FocalLengthIn35mmFilm = on the frame's DIAGONAL (humanfit_map.lens_prior: f_px = mm / 43.27 x diagonal). The UNTOLD
prior (70 mm), the benchmark's "85 mm" and face_ruler.lens_mm (the CAMERA lines of every solve reply: "a 70 -> 84 mm
lens") count on the picture's WIDTH (f_px = mm / 36 x width). On a 3:4 portrait the two differ by x1.387. I first told
the width number: every such start stood 37-49 % too far. Those runs are kept below as "lens x1.39" (a wrong-distance
experiment for free); "lens RIGHT" = the diagonal number (17.3 mm for these pictures; 138 mm for the 1.75 m set, whose
right-lens chains were not run: at that distance the x1.39 runs are already as good as the 0.78 m ones). The HSRD
head views are 180-190 mm in EXIF terms (250-280 by width). NEXT: make the reply's lens the EXIF number, or say which.
| chain | calls | distance f / 45 / 90 % (start -> end) | face / nose / lips / jaw line mm to the scan | nose_base_width | alar_width | tip_width | tip_radius_h | nose_projection | mouth_width | upper_vermilion_mid | lower_vermilion_mid | jaw_width |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.30 m, lens RIGHT, (a) dense off | 6 | +9 / +4 / +2 -> +41 / +21 / +5 | 2.09 / 1.93 / 1.32 / 2.58 | -1.0 | -1.3 | +0.9 | +0.6 | -0.5 | +1.6 | +0.9 | +1.6 | +0.5 |
| 0.30 m, lens right, (b) dense on | 6 | +9 / +4 / +2 -> +39 / +50 / +50 | 2.18 / 1.17 / 0.84 / 6.06 | -1.4 | -0.7 | +1.1 | +0.8 | -1.9 | +1.0 | +1.5 | +2.0 | +7.0 |
| 0.30 m, lens right, (c) dense on, distance 5 % | 6 | +9 / +4 / +2 -> +19 / +12 / +18 | 1.72 / 1.09 / 0.66 / 5.54 | -1.5 | -1.3 | +0.9 | +0.8 | -2.0 | +1.0 | +1.5 | +1.8 | +9.2 |
| 0.30 m, lens x1.39, (a) | 6 | +49 / +42 / +37 -> +32 / +53 / +45 | 2.12 / 2.42 / 1.13 / 2.08 | -1.5 | -1.6 | +0.8 | +0.5 | -0.3 | +1.6 | +0.7 | +1.9 | -2.3 |
| 0.30 m, lens x1.39, (b) | 6 | +49 / +42 / +37 -> +27 / +32 / +58 | 2.37 / 1.30 / 0.78 / 6.62 | -1.5 | -1.2 | +1.2 | +0.8 | -2.6 | +1.9 | +1.3 | +1.9 | +6.1 |
| 0.30 m, lens x1.39, (c) | 6 | +49 / +42 / +37 -> +47 / +41 / +43 | 2.26 / 1.32 / 0.85 / 5.70 | -1.6 | -1.0 | +1.3 | +0.9 | -2.4 | +1.3 | +1.4 | +2.2 | +4.8 |
| 0.40 m, lens RIGHT, (a) dense off | 6 | +9 / +4 / +2 -> +31 / +35 / +7 | 2.07 / 2.05 / 1.35 / 3.45 | -0.6 | -0.9 | +0.6 | +0.3 | -0.5 | +0.9 | +1.0 | +1.9 | +4.8 |
| 0.40 m, lens right, (b) dense on | 6 | +9 / +4 / +2 -> +83 / +52 / +48 | 2.09 / 1.22 / 0.76 / 4.76 | -1.1 | -1.3 | +1.0 | +0.8 | -1.8 | +1.4 | +1.6 | +2.0 | +6.3 |
| 0.40 m, lens right, (c) dense on, distance 5 % | 6 | +9 / +4 / +2 -> +18 / +12 / +15 | 1.59 / 1.04 / 0.57 / 4.85 | -1.4 | -1.8 | +0.5 | +0.4 | -1.8 | +1.0 | +1.6 | +1.8 | +9.7 |
| 0.40 m, lens x1.39, (a) | 6 | +49 / +42 / +38 -> +66 / +73 / +45 | 2.69 / 2.10 / 1.45 / 5.64 | -0.6 | -1.0 | -0.0 | -0.3 | -0.1 | +1.7 | +0.8 | +1.9 | +4.7 |
| 0.40 m, lens x1.39, (b) | 6 | +49 / +42 / +38 -> +76 / +64 / +58 | 2.11 / 1.23 / 0.73 / 5.21 | -1.4 | -1.6 | +0.6 | +0.4 | -2.0 | +1.2 | +1.4 | +1.8 | +5.6 |
| 0.40 m, lens x1.39, (c) | 6 | +49 / +42 / +38 -> +57 / +46 / +41 | 2.05 / 1.20 / 0.69 / 4.62 | -1.0 | -1.1 | +0.8 | +0.6 | -1.7 | +1.4 | +1.6 | +1.9 | +6.5 |
| 1.75 m, lens x1.39, (a) | 6 | +47 / +43 / +40 -> +49 / +53 / +41 | 1.52 / 1.34 / 0.64 / 2.36 | -0.7 | +0.7 | +0.1 | -0.5 | -1.8 | -0.2 | +1.4 | +1.8 | +8.8 |
| 1.75 m, lens x1.39, (b) | 6 | +47 / +43 / +40 -> +116 / +187 / +102 | 1.44 / 1.03 / 0.48 / 3.15 | +0.3 | +0.7 | +0.0 | -0.2 | -1.7 | +1.2 | +1.9 | +1.4 | +8.9 |
| 1.75 m, lens x1.39, (c) | 6 | +47 / +43 / +40 -> +48 / +47 / +42 | 1.45 / 1.00 / 0.51 / 3.45 | +0.3 | +0.7 | -0.0 | -0.2 | -1.7 | +1.3 | +1.9 | +1.3 | +11.2 |
| 0.78 m, 85 mm, lens NOT told, dense off | 8 | -10 / -13 / -15 -> +8 / +31 / -5 | 1.62 / 1.76 / 1.52 / 2.87 | -1.1 | +0.3 | -0.5 | -1.0 | -1.8 | +0.2 | +1.2 | +1.9 | +6.6 |
| 0.78 m, lens not told, dense on | 8 | -10 / -13 / -15 -> +54 / +153 / +72 | 1.71 / 1.08 / 0.65 / 4.05 | -0.7 | +0.5 | -0.2 | -0.4 | -1.2 | +1.4 | +1.5 | +1.8 | +8.1 |
| (the class mean, the start) | 0 | | | +2.6 | +3.6 | +1.0 | +0.8 | -1.0 | +5.3 | +0.5 | +0.7 | |
Read of it (COMPUTED; "truth" = the Part 1 fit; a real nose on our renders, so no photo gap in these rows):
- **The solve does not keep a told distance.** From a start 2-9 % off, dense off ends +21-41 % (front, 45), dense on
  +39-83 % (its prior is 40 %), and with the prior at 5 % still +12-19 % after six calls (the prior is on the whole
  move, but a 5 % sd lets 3 sd through when the reads push). In every phone run the cameras end FARTHER than they
  were: with the head near the class mean a far camera explains the picture better than the true perspective does.
- **A phone-distance picture costs the nose's tip about 1 mm of width and 0.8 mm of roundness, whatever the lens
  setting**: tip width +0.5 .. +1.3 mm and tip radius +0.4 .. +0.9 mm in the eight dense runs at 0.30 / 0.40 m
  (against -0.5 .. +0.1 and -1.0 .. -0.2 from 0.78 / 1.75 m); the wings 0.7-1.8 mm NARROW (the nose's projection is
  1.7-2.6 mm short, but it is 1.2-1.8 short from far too). So "too rounded from the front" IS reproduced at phone distance (a blunter, wider tip), and it is tied to the DISTANCE, not to the wrong lens number: the right lens with the tight prior
  still gives +0.9 / +0.8 at 0.30 m and +0.5 / +0.4 at 0.40 m, where the cameras still end 12-19 % far.
- The WHOLE face at phone distance is no better than the class mean unless the distance is held: face mean to the
  scan 2.1-2.7 mm for (a) / (b) at either lens number (the class mean: 2.23), **1.72 / 1.59 mm with the right lens and
  the 5 % prior**, 1.45 from 1.75 m. The jaw line is 4.6-6.6 mm in every dense phone run (the ears and the jaw's
  angle are hidden or foreshortened at 0.3 m; nothing reads the width; LPS's jaw is 11 mm narrower than the mean).
- A lens told 39 % too long does not by itself widen the nose: its rows equal the right-lens rows to 0.7 mm, because
  the solve drifts to the same far cameras from either start.
- **Which default when EXIF gives the lens: dense on with the distance held tight (5 % or less, and as a bound on the
  whole move since the start), never the 40 % prior.** Face 2.18 -> 1.72 (0.30 m), 2.09 -> 1.59 (0.40 m), no loss at
  1.75 m (1.44 -> 1.45). The private-photo run's drift (0.26 m against 0.39, 0.47 against 0.28) is this.
- On the REAL photos (HSRD; lens told in the EXIF convention, 6 calls):
HSR0040-Body-023 (2.3 m; EXIF-equivalent 185-188 mm):

| chain | calls | distance f / 45 / 90 % (start -> end) | face / nose / lips / jaw line mm to the scan | nose_base_width | alar_width | tip_width | tip_radius_h | nose_projection | mouth_width | upper_vermilion_mid | lower_vermilion_mid | jaw_width |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| lens NOT told (70 mm prior), dense off | 8 | -74 / -74 / -75 -> -60 / -74 / -75 | 0.89 / 0.89 / 0.88 / 0.83 | +3.9 | +0.7 | -1.1 | -2.8 | -1.0 | -0.4 | -0.3 | +0.6 | +2.0 |
| lens not told, dense on | 8 | -74 / -74 / -75 -> +11 / -67 / -29 | 0.95 / 0.92 / 0.68 / 1.11 | +5.0 | +2.8 | -1.9 | -7.3 | -0.8 | +0.9 | +0.5 | +0.4 | -3.4 |
| lens RIGHT, (a) dense off | 6 | -7 / -8 / -9 -> +1 / -17 / -9 | 1.12 / 1.49 / 1.07 / 1.31 | +5.3 | +2.6 | +0.7 | -1.5 | -1.2 | +0.6 | +0.3 | +1.4 | -2.4 |
| lens right, (b) dense on | 6 | -7 / -8 / -9 -> +101 / -67 / +19 | 0.99 / 0.94 / 0.64 / 1.22 | +4.6 | +2.8 | -1.4 | -6.8 | -0.8 | +0.2 | +0.4 | +0.5 | -2.4 |
| lens right, (c) dense on, distance 5 % | 6 | -7 / -8 / -9 -> -4 / -11 / -8 | 0.87 / 0.86 / 0.60 / 0.87 | +4.4 | +2.5 | -2.0 | -7.3 | -0.9 | +0.7 | +0.4 | +0.4 | -2.7 |
| lens x1.39, dense off | 8 | +28 / +27 / +25 -> +42 / +16 / +26 | 1.08 / 1.16 / 1.17 / 1.27 | +3.5 | +1.1 | -0.9 | -3.1 | -1.2 | +0.9 | +0.4 | +1.4 | -0.8 |
| lens x1.39, dense on | 8 | +28 / +27 / +25 -> +130 / -63 / +77 | 1.01 / 0.97 / 0.66 / 1.17 | +4.9 | +2.9 | -1.7 | -7.1 | -0.7 | +0.1 | +0.6 | +0.7 | -3.8 |
| (the class mean, the start) | 0 | | | +4.7 | +5.2 | -0.3 | -6.4 | -2.7 | +3.8 | +1.0 | +1.6 | |

HSR0112-Body-018 (2.1-2.5 m):

| chain | calls | distance f / 45 / 90 % (start -> end) | face / nose / lips / jaw line mm to the scan | nose_base_width | alar_width | tip_width | tip_radius_h | nose_projection | mouth_width | upper_vermilion_mid | lower_vermilion_mid | jaw_width |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| lens NOT told (70 mm prior), dense off | 8 | -69 / -71 / -74 -> -58 / -68 / -74 | 1.44 / 0.98 / 1.31 / 2.14 | +2.7 | +0.3 | -3.3 | -3.9 | -0.5 | +3.3 | +1.2 | +0.8 | +1.2 |
| lens not told, dense on | 8 | -69 / -71 / -74 -> -34 / -47 / -22 | 1.16 / 0.84 / 1.57 / 0.85 | +2.8 | +1.4 | -2.3 | -2.8 | -0.4 | +3.1 | +1.3 | +0.6 | +2.8 |
| lens RIGHT, (a) dense off | 6 | +1 / -1 / -0 -> -1 / +1 / -0 | 1.32 / 1.02 / 1.13 / 2.11 | +2.2 | +1.6 | -3.4 | -3.7 | +1.2 | -0.0 | +0.4 | +0.3 | +2.8 |
| lens right, (b) dense on | 6 | +1 / -1 / -0 -> +6 / -27 / +41 | 1.05 / 0.85 / 1.26 / 0.72 | +2.6 | +1.8 | -1.9 | -2.4 | -0.0 | +0.8 | +0.7 | +0.2 | +0.1 |
| lens right, (c) dense on, distance 5 % | 6 | +1 / -1 / -0 -> +1 / -2 / +0 | 1.05 / 0.84 / 1.19 / 0.78 | +2.8 | +1.8 | -1.8 | -2.3 | -0.0 | +0.9 | +0.7 | +0.2 | +0.8 |
| lens x1.39, dense off | 8 | +40 / +37 / +38 -> +37 / +36 / +38 | 1.42 / 1.09 / 1.11 / 2.40 | +2.0 | +1.2 | -3.3 | -3.6 | +0.8 | +0.1 | +0.5 | +0.2 | +2.0 |
| lens x1.39, dense on | 8 | +40 / +37 / +38 -> +31 / -13 / +86 | 1.04 / 0.82 / 1.19 / 0.71 | +2.5 | +1.6 | -1.7 | -2.2 | +0.1 | +0.7 | +0.7 | +0.2 | -0.9 |
| (the class mean, the start) | 0 | | | +3.0 | +1.2 | +0.1 | -1.3 | -3.3 | +2.1 | +2.5 | +3.2 | |
  With the lens told RIGHT the start stands within 9 % of the true distance (untold: -69 .. -75 %). Dense on with the
  40 % prior then walks it to -67 .. +101 %; the 5 % prior holds it (-11 .. +1 %) and gives the best real-photo
  heads of this study: **face 0.87 mm (HSR0040) and 1.05 mm (HSR0112) to the scan** (untold + dense: 0.95 / 1.16;
  ceiling 0.45 / 0.39). Dense OFF with the right lens is no better than untold (1.12 / 1.32 against 0.89 / 1.44).
  The nose's base stays +4.4 / +2.8 mm wide whatever the lens: not a distance effect at 2.3 m.
- HSRD's own distance, for comparison: 2.1-2.6 m (180-190 mm EXIF-equivalent after the cut): no phone perspective
  in that set; its nose bias is the readers' (section 1), not distance.

### 3. Expression (gexpr.py, gexsum.py; a KNOWN GNM benchmark head, solvecams' head a, since a scan cannot smile:
### its front shot again on the same stage through the same true camera with GNM's "happy" prototype x0.3: a slight
### closed-mouth smile, LOOKED AT: out/ex_pics.png; set A with that front; 4 calls; truth = the NEUTRAL identity)
#### expression test (known GNM head a; truth = its NEUTRAL identity): against the truth, mm

| chain | calls | face rms | lower face rms | chin | jaw_width | mouth_width | what the solve said of lips / lids | fitted expression (front view) |
|---|---|---|---|---|---|---|---|---|
| neutral front, off | 4 | 2.65 | 1.63 | 1.31 | +0.1 | +0.7 | - | - |
| neutral front, on | 4 | 1.44 | 1.64 | 1.24 | +1.5 | +1.0 | - | - |
| smiling front, off | 4 | 2.93 | 2.07 | 1.69 | +3.3 | +3.4 | - | - |
| smiling front, on | 4 | 1.62 | 1.78 | 1.44 | +1.2 | +3.6 | NOISIER than assumed (the head that fits best leaves these reads scattered; their sigma was raised by): landmark 3q x1.7, lip front x1.8 | - |
| smiling front, off, expression=view | 4 | 2.72 | 2.07 | 2.23 | -0.2 | +4.7 | - |  solve: {"3q": {"compress_face": [-0.102, 0.095], "surprise": [0.37, 0.128], "squint": [0.351, 0.207], "lips_roll_in": [-0.189, 0.07], "corners_down": [-0.035, 0.223],  |
| smiling front, off: 4 calls, expression_step, 2 calls | 2 | 2.90 | 2.00 | 1.63 | +2.6 | +3.4 | - | lower_face_region_008 +1.03, lower_face_region_005 -0.97, lower_face_region_016 +0.82, lower_face_region_009 +0.64 |
| start (class mean) | 0 | 1.42 | 2.09 | 1.39 | -1.0 | -0.0 | | |

#### expression test: nose and lips, signed (solved - true identity, mm)

| measure | truth mm | class mean - truth | neutral front, off - truth | neutral front, on - truth | smiling front, off - truth | smiling front, on - truth | smiling front, off, expression=view - truth | smiling front, off: 4 calls, expression_step, 2 calls - truth |
|---|---|---|---|---|---|---|---|---|
| alar_width | 45.8 | -1.1 | +0.2 | +0.4 | +0.7 | +1.4 | +1.7 | +0.9 |
| nose_base_width | 37.9 | -2.3 | +1.3 | +0.2 | +2.9 | +1.6 | +3.9 | +3.3 |
| tip_width | 20.5 | -1.1 | -0.4 | -0.4 | -0.9 | -0.2 | -0.2 | -0.6 |
| tip_radius_h | 12.2 | -1.1 | -0.0 | -0.4 | -0.8 | -0.4 | -0.1 | -0.5 |
| tip_radius_v | 12.4 | -1.2 | +1.5 | -0.2 | +1.6 | -0.1 | +1.3 | +1.3 |
| nose_length | 50.6 | -0.1 | +2.6 | -0.6 | +1.8 | -1.0 | +1.6 | +1.7 |
| nose_projection | 13.7 | +0.3 | -0.4 | -0.8 | -0.7 | -0.8 | -0.3 | -0.7 |
| nostril_show | 14.4 | -0.1 | +2.6 | -0.0 | +2.6 | -0.3 | +2.1 | +2.5 |
| mouth_width | 53.3 | -0.0 | +0.7 | +1.0 | +3.4 | +3.6 | +4.7 | +3.4 |
| upper_vermilion_mid | 5.1 | -0.0 | +0.0 | +0.1 | +0.9 | +0.8 | +1.1 | +0.9 |
| upper_vermilion_quarter | 6.4 | +0.1 | -0.2 | +0.1 | +0.7 | +0.8 | +0.8 | +0.6 |
| lower_vermilion_mid | 7.5 | -0.3 | -0.1 | -0.4 | +1.4 | +0.9 | +1.1 | +1.3 |
| lower_vermilion_quarter | 7.5 | -0.5 | +0.1 | -0.5 | +1.5 | +0.8 | +1.2 | +1.5 |
| cupid_bow | 0.8 | -0.1 | +0.0 | -0.1 | +0.1 | -0.1 | -0.1 | +0.1 |
| seam_curve | 0.5 | +0.9 | -0.7 | +0.5 | -1.3 | -0.1 | -0.8 | -1.3 |
- **An identity-only solve reads a slight smile as the person**: mouth width +3.4 / +3.6 mm (neutral front: +0.7 /
  +1.0), every vermilion height +0.7 to +1.5 mm (neutral: within 0.5), the lip seam's curve -1.3 (off), the nose's
  base +2.9 / +1.6 (neutral +1.3 / +0.2: a smile spreads the wings, and that too becomes identity), jaw_width +3.3
  (off). The whole-face rms hardly shows it (lower face 1.63 -> 2.07 off, 1.64 -> 1.78 on): it is a LOCAL error in
  exactly the features a likeness is judged by.
- Dense on did not down-weight the smile away here (lip front x1.8 only): the smile is slight and consistent with a
  wider-mouthed person, so nothing looks inconsistent; the mouth is simply wrong by 3.6 mm. (Joe's selfie had lip /
  lid reads down-weighted x4-6.5: there the mouth came from the prior instead; either way the lips are not the person's.)
- The solve's own nuisance (solve_step(expression="view"): the sampler's 8 expression classes free per view) does NOT
  recover it: mouth width +4.7, nose base +3.9. It finds happy +0.18 +-0.09 on the front (true 0.30) but also
  surprise -0.33, squint -0.22, lips_roll_in +0.23 there, and surprise +0.37, squint +0.35 on the NEUTRAL 45 view:
  eight whole-face classes per view are too free and not the right shape for "a little smile".
- blockin.expression_step after four identity calls (20 lower-face components fitted on that view, then two more
  calls reading it WITH its expression): the last row: mouth width +3.4, nose base +3.3, vermilion +0.9 / +1.3: nothing
  recovered (it fitted components of +-1 sd to a head that had already taken the smile into its identity, and its own
  table says targets WENT OUT). To separate a smile from a mouth, expression has to be in the solve from the FIRST
  call, as a few lower-face components per view under a tight prior, with at least one neutral view anchoring the
  identity: not built here. Measure only; no solver default changed.

### The plain answer: is the wide, round nose the network, the camera distance, or the prior?
- WIDE (the base and wings, +2 to +5 mm on both real-photo heads): **the READS, both of them, on real photographs.**
  MediaPipe's differential anchors and the dense network each see a photographed nose 1.6-2.6 mm wider than they see
  the same nose in our renders, and nothing else in the solve looks at the nose's width; what is left is the class
  mean, whose nose is 3-5 mm wider than these two people's. On our own renders of a real nose the same solve gets the
  width right to 1.5 mm, so it is not the prior and not GNM (ceiling 0.4 mm). Fix on our side: a read of the nose
  itself in the PICTURE (the alar edge / the nostril openings from the front; readmix has begun one), and a network
  trained on noses that look photographed; until then nose_width from detector points alone should be reported as
  weak, not as read.
- ROUND (a blunt, wide tip): **the camera DISTANCE at phone range.** About +1 mm of tip width and +0.8 mm of tip
  radius at 0.30-0.40 m against none from 0.8-2.3 m, on a known nose, with every lens setting, because the solve
  walks every phone camera 12-80 % too far and then explains the enlarged nose as shape. Holding a known distance
  tight halves it at 0.40 m (not at 0.30 m) and takes the whole face from 2.1-2.2 to 1.6-1.7 mm.
- LIPS: fuller than the person by 0.4-1.9 mm on renders and photos alike (the detector anchors read our render's lip
  tint against a photo's vermilion: +1 to +2.4 mm at the truth), cupid's bow 0.1-0.5 mm flat everywhere, and ANY
  expression in a picture goes into the lips' shape (+3.5 mm of mouth width from a slight smile). The prior matters
  only where the reads are dropped.

## The HSRD-100 real-photo set (Joe: "Yes, pull the data set"; 2026-10-13; hsrd_pull.sh, hsrd_export.py, hsrd_index.py,
## hsrdset.py = the loader). FOR THE denselm, readmix AND projskin AGENTS: this is where it is and how to load it.
WHERE: /mnt/data/hifipushie/groundtruth/hsrd100 ($HIFIPUSHIE_GROUNDTRUTH/hsrd100). NOT in git; no photo or scan of
these people may go into the repo or a pushed sheet. CC BY 4.0: `hsrdset.index()["attribution"]` must accompany
anything shown outside (the text is in index.json; licence copy LICENSE_CC-BY-4.0.txt beside it).
LOAD: `sys.path.insert(0, "spikes/groundtruth"); import hsrdset as H` (numpy + PIL only; the docstring is the manual):
`H.index()`, `H.poses("train" | "heldout" | None)`, `P = H.Pose(pose)`, `P.photos(az=(-30, 30))`, `P.image(cam)`,
`P.labels(cam, "dl3" | "lm68" | "mp")` -> (xy in the cut's pixels, visible, fit quality mm), `P.camera(cam)` (f, cx,
cy, brown3 k, R, C in the rig's frame; az / el / distance round the head; px per mm; roll), `P.project(cam, X_rig)`,
`P.scan()` / `P.scan(decimated=True)` / `P.texture()`, `P.to_rig(V_scan)`, `P.fit()`. `python
spikes/groundtruth/hsrdset.py check` walks every pose; `... sheet <pose> <out.png>` draws the labels on six photos.
LAYOUT per pose, hsrd100/<subject>/<pose>/:
- photos/<cam>.jpg: every rig photo that holds the WHOLE head (31-48 a pose), cut to a head-and-shoulders box at the
  photo's OWN resolution (no resampling), **JPEG quality 95, 4:4:4** (one re-encode of the rig's JPEG; not lossless:
  a lossless cut would have been ~4x the size). masks/<cam>.png: the dataset's own foreground mask, the same cut.
- cameras.json: per photo the cut's box in the original, intrinsics FOR THE CUT (f px, cx, cy; brown3 k1..k3 on x =
  X / Z), R / C in the rig's frame (the .xmp calibration's), where the camera stands round the head (az + = the
  subject's left; el; metres), px per mm at the head, the head's roll in the photo (the files are stored as the camera
  was mounted: many heads lie on their side: rotate by roll_deg, or use P.camera(cam)["roll_deg"]); T_scan_to_rig (the
  transform measured by register.py on the dataset's masks, its silhouette rms) and the head's own frame in the rig.
- scan_head.npz: the LOD0 scan's top 0.42 m (head, neck, shoulders; ~150k vertices): V (scan frame, metres), F, C
  (vertex colours), FUV (per-corner uv into scan_head_texture.png), skin (per vertex: not hair / cloth, by colour and
  roughness). scan_head_texture.png: the 16k texture cut to the head's texels (bounding box, the rest black).
  scan_head_dec.npz: vertex clustering at 2.5 mm.
- fit.json: the Part 1 direct GNM fits: "identity" (p1b3: the 170 components, the similarity scan -> GNM world, the
  region table, the mm measures) and "identity_expression" (p1eb3: + blockin's expression nuisance); "flag" when the
  identity fit's face mean is over 1 mm.
- labels.npz: for each landmark set and photo, pixels IN THE CUT through the distortion (<set>_xy), TRUE visibility
  (<set>_vis: the point is the first surface along its ray against the WHOLE scan within 0.75 m of the head: hair,
  hats, collars, a hand or a phone held to the face all occlude; 4 mm tolerance; and inside the cut), a label quality
  (<set>_q, mm: the identity + expression fit's distance to the scan's surface at that point: **a label is only as
  good as the fit there**; nan = no skin under it: hair / cloth over it, or an eyeball / teeth / tongue vertex whose
  place is the model's, not measured), <set>_form (vermilion-border labels: the geometry knows the lip's FORM, not
  its COLOUR edge: do not train or score a colour-edge reader on them), <set>_X (the points in the rig's frame),
  dl3_region / mp_region / mp_id. Sets: "dl3" = denselm's v3 set of 756 GNM vertices (copied from branch
  worktree-agent-a2e75a7e571826c88 @ 67548ea into hsrd100/landmark_sets/denselm_v3.npz), "lm68" = GNM's 68 standard,
  "mp" = readmix's MediaPipe -> GNM surface points (468; hsrd100/landmark_sets/mp_gnm.json from readmix @ e53688d).
  REMEMBER what Part 2 found: a surface fit pins a GNM vertex ACROSS the skin (0.3-0.5 mm), not ALONG it. On edges
  (lids, nostrils, lip seam, jaw line, ear rim) the labels are good to ~1 mm; on smooth skin (cheek, forehead) a label
  may sit 1-3 mm along the surface from where a renderer's vertex would: weight by region, not only by <set>_q.
- person_meta.json / pose_meta.json (the dataset's), SHA256SUMS (of the original archives), register_check.png,
  summary.json. Top level: index.json (subjects: age and sex as the dataset gives them, the split; poses with their
  summaries; sources' sha256), LICENSE_CC-BY-4.0.txt, README_dataset_card_2026-10-13.md, landmark_sets/.
SPLIT (by SUBJECT, fixed once, in index.json; never change it): HELD OUT = HSR0023 (man, 62), HSR0027 (woman, 41),
HSR0102 (woman, 22); TRAIN-CANDIDATE = HSR0040 (m 50), HSR0042 (m 24), HSR0081 (m 25), HSR0161 (m 64), HSR0015 (f 23),
HSR0028 (f 21), HSR0112 (f 60). Anything tuned on the train side must be scored on the held-out people only.
WHAT WAS NOT KEPT: the RealityCapture project (never needed: the .xmp files carry the calibration), the 5M-polygon
scan and LOD1 / LOD2, the photos that do not hold the whole head, the body below the shoulders. Originals are deleted
after each pose (their sha256 is in index.json and each pose's SHA256SUMS; hsrd_pull.sh <person> <pose> fetches one again).
10 subjects, 29 poses, 1003 photos, 6.82 GB
| pose | subject (sex, age, split) | the dataset's words | head photos (front / 3q / profile / rear) | face px (median, range) | fit: face mean / p90 mm (+ expression) | registration rms mm |
|---|---|---|---|---|---|---|
| HSR0015-Body-023 | HSR0015 (F, 23, train) | Standing, Walking; Sweater; head: None | 31 (10 / 5 / 3 / 13) | 884 (572-1753) | 1.18 / 2.62 (1.10) FLAG | 2.58 |
| HSR0015-Body-070 | HSR0015 (F, 23, train) | Standing, Taking a selfie; Tank top; head: Hairband | 27 (7 / 5 / 3 / 12) | 868 (571-1634) | 0.68 / 1.12 (0.60) | 3.50 |
| HSR0023-Body-046 | HSR0023 (M, 62, heldout) | Standing, Looking at mobile phone; Polo shirt; head: None | 32 (8 / 6 / 6 / 12) | 914 (593-1618) | 0.45 / 0.95 (0.40) | 2.40 |
| HSR0023-Body-052 | HSR0023 (M, 62, heldout) | Standing, Talking on a mobile phone; Polo shirt; head: None | 44 (9 / 13 / 8 / 14) | 942 (570-1736) | 0.41 / 0.86 (0.36) | 4.35 |
| HSR0023-Body-054 | HSR0023 (M, 62, heldout) | Standing, Relaxed standing; Polo shirt; head: None | 31 (6 / 7 / 6 / 12) | 910 (575-1695) | 0.38 / 0.77 (0.34) | 1.66 |
| HSR0027-Body-004 | HSR0027 (F, 41, heldout) | Standing, Relaxed standing; Puffer jacket; head: Beanie | 35 (10 / 7 / 6 / 12) | 931 (585-1775) | 1.19 / 3.06 (1.04) FLAG | 2.21 |
| HSR0027-Body-029 | HSR0027 (F, 41, heldout) | Standing, Taking a photo; Hoodie; head: None | 48 (11 / 14 / 10 / 13) | 961 (566-1767) | 1.31 / 3.22 (1.16) FLAG | 3.86 |
| HSR0027-Body-053 | HSR0027 (F, 41, heldout) | Walking, Pulling a suitcase; T-shirt; head: None | 35 (7 / 8 / 6 / 14) | 924 (589-1805) | 0.88 / 2.26 (0.84) | 6.52 |
| HSR0028-Body-016 | HSR0028 (F, 21, train) | Standing, Holding an umbrella; Coat; head: Beanie | 41 (12 / 7 / 10 / 12) | 942 (575-1741) | 0.30 / 0.60 (0.26) | 2.26 |
| HSR0028-Body-021 | HSR0028 (F, 21, train) | Standing, Looking at mobile phone; Sweater; head: None | 34 (10 / 5 / 6 / 13) | 922 (594-1671) | 1.00 / 1.18 (0.98) | 2.13 |
| HSR0028-Body-062 | HSR0028 (F, 21, train) | Standing, Pointing; Button-up shirt; head: None | 33 (8 / 6 / 7 / 12) | 931 (585-1778) | 0.62 / 1.37 (0.56) | 1.79 |
| HSR0040-Body-012 | HSR0040 (M, 50, train) | Standing, Talking on a mobile phone; Jacket; head: None | 32 (7 / 8 / 3 / 14) | 909 (777-1711) | 0.57 / 1.14 (0.52) | 3.29 |
| HSR0040-Body-023 | HSR0040 (M, 50, train) | Crossed Arms, Relaxed standing; Sweater; head: None | 48 (10 / 9 / 13 / 16) | 918 (634-1698) | 0.45 / 0.95 (0.42) | 1.33 |
| HSR0040-Body-027 | HSR0040 (M, 50, train) | Standing, Looking at mobile phone; Sweater; head: None | 48 (12 / 8 / 12 / 16) | 914 (541-1706) | 0.58 / 1.24 (0.45) | 1.41 |
| HSR0042-Body-008 | HSR0042 (M, 24, train) | Standing, Talking on a mobile phone; Jacket; head: Beanie | 30 (7 / 6 / 4 / 13) | 886 (582-1745) | 0.59 / 0.96 (0.53) | 2.63 |
| HSR0042-Body-018 | HSR0042 (M, 24, train) | Standing, Relaxed standing; Sweater; head: None | 32 (7 / 5 / 7 / 13) | 908 (569-1730) | 0.37 / 0.76 (0.33) | 2.86 |
| HSR0042-Body-045 | HSR0042 (M, 24, train) | Standing, Relaxed standing; None; head: Swimcap | 28 (6 / 6 / 3 / 13) | 889 (582-1767) | 0.36 / 0.74 (0.30) | 0.53 |
| HSR0081-Body-020 | HSR0081 (M, 25, train) | Walking, Walking; Button-up shirt; head: None | 27 (6 / 5 / 4 / 12) | 924 (684-1626) | 0.32 / 0.67 (0.28) | 3.87 |
| HSR0081-Body-033 | HSR0081 (M, 25, train) | Standing, Pointing; Button-up shirt; head: None | 27 (9 / 6 / 4 / 8) | 897 (520-1431) | 0.31 / 0.64 (0.28) | 3.78 |
| HSR0081-Body-054 | HSR0081 (M, 25, train) | Hands on hips, Relaxed standing; T-shirt; head: None | 29 (9 / 5 / 6 / 9) | 913 (522-1788) | 0.43 / 0.75 (0.41) | 2.88 |
| HSR0102-Body-019 | HSR0102 (F, 22, heldout) | Standing, Looking at mobile phone; Sweater; head: Hairband | 35 (5 / 7 / 12 / 11) | 928 (576-1750) | 0.36 / 0.74 (0.32) | 3.39 |
| HSR0102-Body-048 | HSR0102 (F, 22, heldout) | Standing, Waving; T-shirt; head: Hairband | 44 (6 / 15 / 8 / 15) | 942 (553-1739) | 0.48 / 0.97 (0.34) | 3.67 |
| HSR0102-Body-052 | HSR0102 (F, 22, heldout) | Hands behind back, Relaxed standing; T-shirt; head: Hairband | 33 (6 / 7 / 10 / 10) | 903 (561-1668) | 0.31 / 0.62 (0.28) | 2.66 |
| HSR0112-Body-018 | HSR0112 (F, 60, train) | Hand in pocket, Relaxed standing; Sweater; head: None | 30 (8 / 5 / 4 / 13) | 923 (580-1765) | 0.39 / 0.83 (0.37) | 2.59 |
| HSR0112-Body-023 | HSR0112 (F, 60, train) | Standing, Talking on a mobile phone; Sweater; head: None | 36 (9 / 7 / 6 / 14) | 939 (574-1748) | 0.40 / 0.83 (0.37) | 3.12 |
| HSR0112-Body-074 | HSR0112 (F, 60, train) | Standing, Looking at mobile phone; Dress; head: None | 25 (4 / 7 / 3 / 11) | 923 (583-1654) | 0.54 / 1.16 (0.50) | 3.93 |
| HSR0161-Body-007 | HSR0161 (M, 64, train) | Standing, Looking at mobile phone; Zip-up hoodie; head: Bucket hat | 39 (6 / 11 / 11 / 11) | 911 (558-1692) | 1.22 / 2.27 (1.41) FLAG | 3.19 |
| HSR0161-Body-009 | HSR0161 (M, 64, train) | Standing, Talking on a mobile phone; Zip-up hoodie; head: Bucket hat | 33 (8 / 9 / 5 / 11) | 931 (520-1669) | 0.71 / 1.52 (0.61) | 3.84 |
| HSR0161-Body-015 | HSR0161 (M, 64, train) | Standing, Holding a jacket; Sweater; head: Bucket hat | 36 (7 / 5 / 15 / 9) | 914 (643-1707) | 0.48 / 0.94 (0.40) | 3.59 |

Read of the set (the 10 subjects' most neutral standing pose; table above from hsrd_index.py; label sheets LOOKED AT
for HSR0040, HSR0042, HSR0027: out/set_*.png):
- 338 head photos of 10 people, 2.25 GB (200-350 MB a pose). By where the camera stands: front (|az| < 30) 78, three-
  quarter (30-70) 62, profile (70-115) 77, rear 121. The face is 880-930 px wide in the median photo, 520-1800 over
  all (the rig has two settings: ~6 and ~11 px / mm). Photos with at least 100 GOOD dl3 labels (visible, on measured
  skin within 1.5 mm): 222; good labels per photo: front 453, three-quarter 393, profile 233, rear 27 (of 756).
- Fit quality (identity; face mean / p90): 0.31-0.62 / 0.62-1.37 mm on eight subjects; **HSR0015 1.18 / 2.62 (FLAG)**
  and HSR0027 0.88 / 2.26: both have long hair lying on the cheeks and jaw; the mask's edge at hair on skin leaves
  2-4 mm on the "cheeks" / "jaw line" rows (20 % of the jaw line compared) while nose, lips and chin are at 0.4-0.6
  like the others. Use <set>_q per label there, not the pose's mean. Registration (scan -> rig, silhouette rms):
  1.3-3.6 mm, HSR0027 6.5 (long loose hair is not the same shape in mask and scan; the median is 1.5 mm and the
  labels sit on her features in the sheet).
- LOOKED AT and worth knowing: some REAR photos show other people behind the subject (operators at the rig's edge):
  one more reason nothing of this goes into git or a shared sheet uncropped. HSR0161 wears a bucket hat in every
  pose of the dataset (forehead and skull never seen); HSR0102 a hairband; HSR0042 has a swim-cap pose (pulled as a
  second pose: the only skull besides the Lee Perry-Smith head).
- WHAT THIS SET CAN AND CANNOT BE USED FOR. It CAN: validate detectors and the solve on real photographs with a
  metric answer (camera truth to ~1 mm / a fraction of a degree, surface truth to the scan's own noise, labels to
  0.3-0.6 mm across the surface on measured skin); measure a reader's BIAS on real skin (the wide nose, the fuller
  lips: both were found with two of these people); give real fold geometry (nasolabial, marionette, jowl, hooded
  lids, neck bands on the 41-64 year-olds: the scan heads and textures) to the fold / texture work. It CANNOT make a
  landmark network general: it is TEN identities (five men, five women, 21-64, four ethnic groups by the dataset's
  words), one studio, one flash set-up, a white cyc with the rig behind, every expression neutral or near it, mouths
  closed, eyes open, street clothes, hair as it came, cameras at 2.1-2.6 m only (no phone perspective), many heads
  sideways in the frame. Fine-tuning on seven of them would teach the look of THIS studio as much as real skin; as a
  small real-photo term mixed into synthetic training, or to calibrate sigmas and biases, with the three held-out
  people for scoring, it is useful. Labels along smooth skin are softer than they look (see above). The poses beyond
  the neutral one add head turns relative to the body and occluders (phones, hats, hands), not new faces.

### What the further poses vary on the head (hsrd_vary.py, from the set itself; COMPUTED)
| subject | pose (the dataset's words; head accessory) | head turn / nod in the rig, deg | expression norm (largest) | good dl3 labels in the best front photo | fit face mean mm | identity vs the first pose: errmap face mm, jaw / nose-base width mm |
|---|---|---|---|---|---|---|
| HSR0015 | HSR0015-Body-023: Standing, Walking; None | -106 / +10 | 7.97 (lower_face_region_014 -3.75) | 429 | 1.18 | - |
| HSR0015 | HSR0015-Body-070: Standing, Taking a selfie; Hairband | -99 / +6 | 4.00 (lower_face_region_014 -1.76) | 467 | 0.68 | 4.61, -3.5 / +0.9 |
| HSR0023 | HSR0023-Body-046: Standing, Looking at mobile phone; None | +85 / +19 | 3.08 (lower_face_region_010 +1.10) | 495 | 0.45 | - |
| HSR0023 | HSR0023-Body-052: Standing, Talking on a mobile phone; None | +58 / -9 | 3.12 (left_eye_region_001 -1.49) | 472 | 0.41 | 2.34, +1.8 / +1.7 |
| HSR0023 | HSR0023-Body-054: Standing, Relaxed standing; None | +84 / -1 | 2.52 (right_eye_region_004 -0.89) | 508 | 0.38 | 1.66, -0.6 / +1.4 |
| HSR0027 | HSR0027-Body-004: Standing, Relaxed standing; Beanie | +119 / +1 | 6.76 (left_eye_region_004 -4.02) | 447 | 1.19 | - |
| HSR0027 | HSR0027-Body-029: Standing, Taking a photo; None | +152 / +6 | 5.01 (right_eye_region_004 +3.14) | 424 | 1.31 | 7.02, +16.8 / +0.7 |
| HSR0027 | HSR0027-Body-053: Walking, Pulling a suitcase; None | +121 / -3 | 4.84 (right_eye_region_004 +2.66) | 428 | 0.88 | 6.53, +14.2 / +1.3 |
| HSR0028 | HSR0028-Body-016: Standing, Holding an umbrella; Beanie | -101 / +1 | 2.53 (lower_face_region_012 +1.41) | 476 | 0.30 | - |
| HSR0028 | HSR0028-Body-021: Standing, Looking at mobile phone; None | -82 / +27 | 9.73 (lower_face_region_012 +5.97) | 441 | 1.00 | 3.54, -2.3 / -0.8 |
| HSR0028 | HSR0028-Body-062: Standing, Pointing; None | -72 / -7 | 3.80 (lower_face_region_012 +2.46) | 476 | 0.62 | 1.61, +4.3 / +0.6 |
| HSR0040 | HSR0040-Body-023: Crossed Arms, Relaxed standing; None | -24 / -0 | 2.54 (lower_face_region_018 -1.43) | 515 | 0.45 | - |
| HSR0040 | HSR0040-Body-012: Standing, Talking on a mobile phone; None | -41 / +2 | 3.00 (lower_face_region_006 +1.22) | 483 | 0.57 | 1.21, -0.5 / +0.2 |
| HSR0040 | HSR0040-Body-027: Standing, Looking at mobile phone; None | -14 / +15 | 5.39 (right_eye_region_001 -2.10) | 495 | 0.58 | 2.61, +4.9 / +1.3 |
| HSR0042 | HSR0042-Body-008: Standing, Talking on a mobile phone; Beanie | -99 / +20 | 3.53 (left_eye_region_003 -1.22) | 457 | 0.59 | - |
| HSR0042 | HSR0042-Body-018: Standing, Relaxed standing; None | -102 / -4 | 2.99 (lower_face_region_013 -1.12) | 519 | 0.37 | 2.33, -0.8 / +1.1 |
| HSR0042 | HSR0042-Body-045: Standing, Relaxed standing; Swimcap | -99 / +1 | 3.21 (lower_face_region_010 -1.30) | 511 | 0.36 | 2.83, -4.2 / +1.6 |
| HSR0081 | HSR0081-Body-020: Walking, Walking; None | -57 / +10 | 2.52 (lower_face_region_016 +0.92) | 497 | 0.32 | - |
| HSR0081 | HSR0081-Body-033: Standing, Pointing; None | -23 / +6 | 2.54 (lower_face_region_010 +0.83) | 507 | 0.31 | 1.74, +6.4 / +1.8 |
| HSR0081 | HSR0081-Body-054: Hands on hips, Relaxed standing; None | -14 / +6 | 2.46 (right_eye_region_003 -1.06) | 495 | 0.43 | 1.97, +1.8 / +0.4 |
| HSR0102 | HSR0102-Body-019: Standing, Looking at mobile phone; Hairband | +129 / +35 | 3.51 (lower_face_region_004 -1.38) | 498 | 0.36 | - |
| HSR0102 | HSR0102-Body-048: Standing, Waving; Hairband | +106 / -6 | 4.28 (lower_face_region_004 -2.02) | 475 | 0.48 | 3.77, -4.2 / +4.7 |
| HSR0102 | HSR0102-Body-052: Hands behind back, Relaxed standing; Hairband | +134 / +5 | 2.90 (lower_face_region_008 +1.22) | 490 | 0.31 | 3.09, -8.0 / +0.9 |
| HSR0112 | HSR0112-Body-018: Hand in pocket, Relaxed standing; None | -126 / +1 | 2.52 (lower_face_region_015 -1.14) | 477 | 0.39 | - |
| HSR0112 | HSR0112-Body-023: Standing, Talking on a mobile phone; None | -110 / +1 | 2.85 (lower_face_region_015 -1.25) | 479 | 0.40 | 1.18, -1.2 / +1.3 |
| HSR0112 | HSR0112-Body-074: Standing, Looking at mobile phone; None | -145 / +40 | 4.45 (lower_face_region_011 -1.58) | 467 | 0.54 | 2.42, +1.2 / -2.5 |
| HSR0161 | HSR0161-Body-007: Standing, Looking at mobile phone; Bucket hat | +164 / +32 | 11.53 (lower_face_region_018 -5.26) | 392 | 1.22 | - |
| HSR0161 | HSR0161-Body-009: Standing, Talking on a mobile phone; Bucket hat | -141 / -23 | 5.16 (right_eye_region_003 -2.28) | 455 | 0.71 | 9.46, -0.5 / +15.0 |
| HSR0161 | HSR0161-Body-015: Standing, Holding a jacket; Bucket hat | +163 / -5 | 3.95 (lower_face_region_008 -1.94) | 478 | 0.48 | 8.99, +3.6 / +13.2 |
FINAL (2026-10-13 16:00): 29 poses of 10 subjects, 1,003 head photos (front 230, three-quarter 214, profile 201,
rear 358), **6.6 GB on disk** (hsrd100/; budget 40 GB; /mnt/data 110 GB free after). Unavailable (the direct fit
found no skin: the landmark start on the scan went wrong; both are a phone / selfie pose under a hat):
HSR0081-Body-010, HSR0015-Body-009; replaced by HSR0081-Body-020, HSR0015 keeps two poses. HSR0102-Body-019's
archive was truncated by the usage-limit cut-off and pulled again (fine). `hsrdset.py check` passes on all 29.
FLAGGED fits (face mean > 1 mm; hair or a hat over cheeks / jaw / forehead, nose / lips / chin still 0.4-0.6 mm):
HSR0015-Body-023 (1.18), HSR0027-Body-004 (beanie, 1.19), HSR0027-Body-029 (1.31), HSR0161-Body-007 (1.22): use the
per-label quality there.
- The head's NOD between poses spans -23 .. +40 deg (looking at a phone, taking a selfie / photo, waving) and its TURN
  in the rig 3-60 deg: a further pose gives every camera a new angle on the same face. Expressions stay near neutral
  (expression norm 2.5-5); the exception is HSR0028-Body-021 (looking down at a phone: 9.7, a lower-face component at
  6 sd: the mouth / chin compressed by the bent neck). Hats (beanie, bucket hat, swim cap), a hairband, a phone at the
  ear or in front of the face change WHICH labels are visible, not the face.
- The same person's two scans give direct-fit identities **1.2-4.6 mm apart (errmap face; median 2.6)** between
  poses whose fits are clean, and 6.5-9.5 mm where one of them is a flagged / hat pose (HSR0027, HSR0161; jaw +14-17
  mm or nose +13-15 mm "apart": that is the fit pulled by hair or a brim, not the person). Each fit lies 0.3-0.7 mm
  from its own scan. So the Part 2 vertex-to-vertex error against "the Part 1 fit" has a floor of 1-4 mm that is the
  truth's own, a 2-5 mm jaw_width error on a real head is inside what a second scan disagrees by, and posture moves
  the soft tissue (+4.9 mm of jaw on the nodded HSR0040 pose); surface distance to the scan stays the measure to trust.
- So: two or three poses a subject are enough for landmark work; more poses buy camera angles, occluders and this
  repeatability measurement, not new faces.

## How these sets should be used from now on
- A STANDING BENCHMARK: `spikes/groundtruth/bench.sh part1|part2|all [tags]` reruns everything from the downloads
  (fetch.sh) to the tables and both sheets; tests/test_groundtruth.py guards the distance measure. Rerun Part 2 after
  any change to the solve, the readers or the dense network, and read FOUR numbers per head against the tables here:
  face mean to the scan (dense off / on), jaw_width error, the nose's base width error, the profile camera's pitch.
  The synthetic benchmark (solvecams) stays the place for repeatability; this one is the place for BIAS: the wide
  nose, the fuller lips, the held size, the unread jaw were all invisible on GNM-made heads.
- The Lee Perry-Smith head is the only scan with a bare skull and the only one we may draw from any camera (phone
  distance, any light): use it for camera / perspective questions. Its shut eyes switch off iris, limbus and lid
  reads: never judge the eye region on it. It is ONE narrow-jawed man.
- HSRD-100 is the real-photo side: the photos ARE good enough to matter (10 px / mm on the head cameras, even light,
  sharp skin); what they lack is variety of camera distance, expression and light. The other subjects WERE worth
  pulling (done: ten people, the ceiling holds on all); further poses add head turns and occluders, not identities.
- For a likeness test of the whole pipeline on a real person, the right-lens + dense + distance-held chain on
  HSR0040 / HSR0112 (0.87 / 1.05 mm) is the current best number to beat; the ceiling is 0.45 / 0.39.
- Pictures of the scanned people stay in workspace/ and /mnt/data; every public use of a result needs the two
  attribution lines (sources.json).

