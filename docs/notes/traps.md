# Traps: symptom -> real cause -> what to check first

Each of these cost at least one round (often a session) on Tess or Garrett. Before you trust a measure or a diagnosis,
check this list. Rule behind all of them (gates.md "MEASURE FIRST"): a measure must reproduce a known case (the
reference against itself, a planted fault) before it drives a change. Ledger: docs/notes/codified.md.

## Measuring and pictures

**UVs read upside down.** Symptom: a probe says the texture under a feature is wrong (r70: "inner paint overlay" blamed
for the nostril blotch). Cause: the probe flipped v. trimesh's GLB texcoords are already v-up; `1 - uv` reads the
mirrored row. asset.rasterize's PNG row 0 is the TOP (uv v = 1 - (y + .5) / size). Check first: probe a texel you can
see (a painted marker, the iris) and confirm it lands where the render shows it, before reading any other texel.

**AgX vs PBR Neutral compared as a colour bug.** Symptom: "skin reads grey", lips / brows off by several L*, the export
"darker than the stage". Cause: the two renders used different view transforms (AgX rolls lit skin toward grey; the
skin looks, glTF viewers and blender_game's default use Khronos PBR Neutral). Check first: both images' view transform
and light (asset.GAME_LIGHT). Never compare an AgX render with a Neutral one; re-render the old one.

**Proxy render in a different pose than the batch.** Symptom: the fast proxy says a lever is dead or a lip "drapes on the
crowns", the batch disagrees. Cause (r46-r47): fastproxy's smile had mouthUpperUp .5 + mouthLowerDown .3 + squints; the
batch rendered mouthSmile 1 + cheekSquint 1. Check first: print the pose weights both sides read; they must come from
the same shots file. Then calibrate the proxy on one batch frame before using it.

**Photo hair mask errors.** Symptom: hair colour / coverage numbers say "too dark" or "bald temple" while the eye says
otherwise. Cause: the segmentation mask dropped the photo's highlights (lit strands classed as skin / background) or
took skin at the hairline, so the photo side of the measure is wrong. Check first: overlay the mask on the photo crop
and look at its edge and highlights; run the measure on the photo against itself.

**Half-sided hair preview.** Symptom: the preview looks full, the export looks thin / see-through from some angles, or
triangle counts look half of what ships. Cause: the preview drew cards two-sided while the export duplicates back faces
as their own triangles (hair.BACK_FACES) with a single-sided material; the preview hid the duplicate back faces, so
it neither showed the engine's look nor the drawn count. Check first: judge hair in the re-imported GLB with backface
culling on, as an engine draws it; count drawn triangles from the GLB index buffer.

**Judging hair against the groom instead of the photo (and the reverse).** Symptom: hair-card MAJOR counts swing 19 -> 29
between rounds; faults that card changes can't move. Cause: one review mixed two questions. Cards (a conversion) are
judged against their SOURCE groom render at the same camera / light; the groom is judged against the photo in its own
stage. A photo-vs fault the groom also has goes to the groom's stage. Check first: what is the reference column of this
review, and which stage owns this fault?

**A measure that doesn't measure the visible fault.** Symptom: every checklist row passes and it still reads wrong (G56r
"bristly crew cut"); or a proxy angle says 20 deg where the render shows 56 (laygeo). Cause: the item measures something
nearby (a silhouette band, the camera-facing slope). Check first: crop the region the eye complains about and confirm
the measure's box is on it; add the missing item before changing the model.

**Dead lever.** Symptom: a parameter changes and the measured row doesn't move (sheen, lid_shade, a coat sheen in a
batch). Cause: plumbing: an opaque layer later in the stack, a cached attribute, a wrapper replacing the object after
the patch, the env var not read in that process. Check first: two values of the lever on the cheap path; diff the
job.json; print the layer order (skin: order.py).

**Same-name cache hit.** Symptom: an edited sculpt / file changes nothing. Cause: the cache keys by file name. Check
first: write the edit under a new name.

## Reviews

**Reviewer with swapped labels.** Symptom: a blind A/B verdict that contradicts the tiles (the "new" faults described are
visibly on the old one); or a reviewer that puts the left eye's lashes on the right. Cause: the reviewer mixed X / Y or
image sides. Check first: map each named fault back to its tile using key.json and look; if they don't match the
description, rerun the review.

**One-result reviews vary 2 -> 5 MAJORs.** Symptom: a change "fixed three MAJORs", the next run of the same build finds
them again. Cause: separate reviewers / sittings are not comparable; the count is noise at that scale. Check first: decide
keep / revert only with bin/review-ab (both candidates, same tiles, one sitting). Counts from different reviewers are
never compared.

**Review refused but counted as 0 MAJORs.** Symptom: four heads "pass" with 0 MAJORs on the same afternoon (skin r8).
Cause: the review CLI didn't run (rate limit before 13:00 MT) and a downstream count read the empty file as zero. Now
bin/review and bin/review-ab exit 4 and write "REVIEW FAILED". Check first: exit code 4 / no VERDICT line = no review;
use a fresh blind subagent on the same tiles and key.

**Whole-head sheets hide feature faults.** Symptom: eleven expression rounds and no review ever said "grimace" or "lips
not touching the teeth"; a coordinator missed a notched chin on a 6240 px sheet. Cause: the face was ~150 px, the mouth
~40 px in the reviewed frame. Check first: single-feature tiles, ref | result, aligned on that feature, >= ~400 px
(spikes/tour/tour.py, blockin.focus). Full sheets are for Joe only.

**Agents over-rate their own renders.** Symptom: "reads as a disc golfer at a glance", "seam at rest: clean", "scale
plainly right" on work Joe calls bad. Cause: the author judges what its sheet was built to prove. Check first: look at
the pairs before reading any caption; the blind reviewer sees no claims; numbers come after the look.

## Pipeline and pieces

**Skin threads silently reshaping an approved head (drift).** Symptom: "how did Garrett end up so far from his approved
face?" Cause: the export took the skin thread's "current best" model, which carried head GEOMETRY edits (lid_fold
overhang 1-3 mm, eye bags 1.3 mm, cheek flatten 1.1 mm); then the export's crease line, the game rig's hard key and
the 59 deg game lens added more. Check first: the export's head must equal the approved head (approve get head ...;
asset.approved_head on the export branch); folds over 1 mm (asset.FOLD_FORM_MAX_MM) are head form. Every RC sheet
shows the approved head's render beside the build at the same camera and light.

**LOD0 hair "helmet".** Symptom: LOD0 hair far sparser than the hair thread's hero tier. Cause: hair.export.tier unset,
so LOD0 was cut to the old EXPORT_CARDS budget. asset.hair_tier_default now takes the role's tier and warns. Check
first: the export log line "hair: LOD0 card tier ...".

**`hair_clumps.FILL` is not the arch fill.** Symptom: setting FILL=1 "for the crown fill" changes the atlas packing.
Cause: FILL is the bake's packing share (0.82); the crown fill under the arch is ARCH_FILL (default 1 already). Check
first: grep the constant's comment before setting a module constant by env.

**Per-character env leaking into the next export.** Symptom: Garrett's export smiles Tess's fitted smile. Cause:
HP_SMILE_FIT / HP_JAW_FIT / HP_SHAPE_SCULPT are environment globals that apply to whatever head is exported. Check
first: the export log's env_fits WARNINGs; start each character's export from a clean env.

**Merges deleting another thread's code.** Symptom: a fix that landed is gone after an integration merge; a test that
passed starts failing on main. Cause: resolving conflicts by taking one side wholesale (or a squash built from a stale
branch) drops the other thread's functions / constants. Check first: after a merge, diff the list of top-level defs
and constants against both parents; run both threads' tests.

**A shared change that sets off a chain of faults.** Symptom: each fix exposes the next fault (Garrett's jacket HPS: a
dozen sessions). Cause: a load-bearing default changed. Check first: after two failed fixes, restore the last good
default and make the new behaviour opt-in.

## Machine

**OOM from undeclared memory.** Symptom: the desktop freezes or an export dies with exit 137. Cause: a job ran outside
resources.heavy or declared less than it uses (v7e: an export sharing the slice with Tess's). Check first: declare the
real peak (exports 24 GB), run under bin/capped; exit 137 = killed for memory: find the cause, don't raise the cap.

**Desktop freezes during renders.** Cause: concurrent GPU renders on the shared iGPU (CPU / memory look fine). Renders
take the GPU lock via bin/capped; check render sizes match the judged detail.

**Per-pixel noise in tests.** Symptom: a test fails on one machine or one run and passes on the next. Cause: renders and
float pipelines differ by a pixel / 1e-16 between runs and GPUs. Check first: compare statistics with tolerances
(means, quantiles, counts in a box), never exact pixels.

**Wrong PID for a background job.** Symptom: "the job is alive" when it died, or a kill misses. Cause: `setsid ... & echo
$!` records setsid's parent. Check first: pgrep -f <script> for the real PID; kill only PIDs you started.

## A closed thin slab decimated as one mesh (2026-10-19, Garrett collars)
Symptom: collars / lapels in the GLB show flat facets with their back face out; the frozen drape is clean.
Cause: made pieces ship as closed ~1 mm slabs (front, back, rim); decimation error (mm) >> slab thickness, so the two
sides cross. Check first: back-face pixels (clay, backs red) before vs after decimation. Fix: decimate one sheet and
rebuild the back from it (cloth.EXPORT_MADE_SHEETS, lods.LOD_MADE_SHEETS).

## A misread note became a pattern default (2026-10-19, Garrett jacket neckline)
Symptom: many collar sessions tuning the drape; collar stands off the neck whatever the sim does.
Cause: jacket neckline widen 0.018 / back 0.035 added from a misread "lie low and flat" note; every later session tuned
on a wrong neckline. Check first: measure the pattern against the collar checklist (cloth_checklist.json) before any
drape work; pattern parameters carry their source.

## A swapped / tried-on part that never replaced the old one (2026-10-19, garment-game proof)
Symptom: polygon-shaped blotches on a tried-on part at every LOD, still there under flat emission; the proof lost 0-14.
Cause: judge --swap keyed by the OBJECT name matched no mesh and was ignored; v8's jacket was drawn inside ours.
Check first: a GE_FLATID render (each object its own colour) or the run's object list. Now refused (blender_game swap).
Same family as a hair lever matching 0 cards (r46g): any selector that matches nothing must raise.
