# judge: one validated way to judge a game asset (2026-10-19, "judge" tooling agent, branch judge-tool)

Why (gates.md "Process rules (2026-10-19)"): rounds were wasted on UNVALIDATED measures and inconsistent judging: uvs
read upside down (trimesh already flips glTF uvs), AgX vs PBR Neutral renders compared, a preview drawing cards
half-sided, a photo hair mask dropping highlights, hair judged against the strand groom instead of the photo, reviewer
labels swapped, a fast proxy rendering a different pose than the batch. `bin/judge` re-validates itself every run and
REFUSES to report when a check fails (exit 5).

## Commands (bin/judge; /mnt/data/hifipushie/bin/judge points at it)
- `judge shots <glb> [--head <approved head model>] [--tag t] [--swap mesh=<glb>] [--force]`
  The standard shots (judge.SHOTS) rendered by blender_game.py (the GLB re-imported, materials from its shading
  notes, drawn as the engine draws it, RGBA), cached per GLB content in /mnt/data/hifipushie/judge/runs/<tag>_<hash>/
  (renders/, crops/, crops.json, audit.json, checks.json). Takes resources.heavy (JUDGE_GB, default 8) + bin/capped
  (GPU lock). ~1-2 min of Blender for a hero character (18 renders), plus the heavy-slot queue (4-7 min on 2026-10-19).
  `--swap hair=<hair glb>` replaces a part by another GLB's meshes in the same world frame (hair builds tried on the
  character; importer materials, so swap BOTH sides of a comparison).
- `judge report <glb|run> [--ref <glb|run>] [--head <model>] [--only eyes,mouth]`: the measures table, vs the ref
  build (same cameras, same boxes) and vs the photo crops (photo-lit face features).
- `judge ab <old> <new> <out> [--ref <glb|run>] [--head <model>] [--only ...] [--dry]`: blind trios (ref | X | Y) of
  the same crops + two CONTROL trios (the reference itself as a candidate, once as old, once as new; named like crops
  `<crop>_b` / `<crop>_c`, order shuffled). Runs bin/review-ab; `--dry` (or review-ab failing) writes
  <out>/review/{trio_*.png, key.json, prompt.md} for a FRESH blind subagent (give it prompt.md only), then
  `judge score <out>/review` applies the key. A review whose controls don't pick the reference is REFUSED.
- `judge approved <stage> <piece>`: approve get, as judge sees it.

## Shots, lights, crops
- g1m / g3m: front / three_quarter / side / back, 1920x1080, vfov 59 (gates.md game distance), game rig; crops at
  NATIVE pixels, 384x512 (1 m, head) and 320x512 (3 m, centred 0.15 m over the hips: feet cut).
- face: front + three_quarter, 1024^2 at 0.6 m, fov 30: under the game rig AND, with --head, under each view's
  skin_read.photo_light (the light the head was approved in; view "Standard"). Feature crops eyes / brows / nose /
  mouth / hairline cut by MediaPipe landmarks (likeness.detect): centre = mean of fixed landmark ids, size x the
  outer-canthus distance (judge.FEATURES), resized to 384 max. The photo crops use the PHOTO's own landmarks with the
  same recipe, so both show the same part of the face. A box leaving the frame by > 15 % is an error, not a crop.
- crown (top, back_quarter on HeadTop_End), nape (back on Neck), collar (front, 3/4 on Neck), cuffs (front on LeftHand):
  512^2 at 0.45-0.6 m, game rig. blender_game gained the view "top".
- Render-vs-render comparisons reuse the REFERENCE run's boxes (the same pixels compared).

## Self-checks (all must pass, every run)
- uv_orientation: ~40 probe points per textured mesh (triangle centroids on textured spots, glTF-local): base colour
  read OUR way (judge.texel_at on raw glTF uv: row = v*H, top-left origin) vs Blender's way (closest point on the
  imported mesh, its loop uvs, image.pixels). Pass: median diff < 0.02, 90 % < 0.06, AND the v-flipped read must be
  clearly worse (else the probe can't tell; rc2n: 0.0000 vs flipped 0.099).
- triangles: drawn (Blender loop triangles) == GLB triangles - explicit back faces - degenerate, per mesh.
- sidedness: every material culls back faces exactly when the engine would (glTF doubleSided false), EXCEPT meshes
  with explicit back faces, drawn two-sided (see the finding below).
- render_state: every render's view transform, look, exposure, lights (energy / angle / colour / rotation) and world
  are recorded (audit.json); one state per light set; compared crops must carry identical state hashes, else refuse.
- measures: on every reference crop, the reference against itself gives 0 on every measure, and a planted dark blot
  (gaussian, -25 L*, 6 % of the crop) is found: spot > 1 L*, L50 not up, worst spot within 8 % of where it was put.

## Measures (per crop, inside the subject's alpha; x - ref)
L10 / L50 / L90 (L* percentiles), C50 (chroma median), blotch (std of the mid-scale L* band-pass, 1.2-5 % of the crop),
spot (largest local band-pass L* difference: a blotch / sticker / rim; "worst@" = where), edge (mean |Sobel x - Sobel
ref| / mean ref, inside both subjects off their borders), sharp (signed: p99 edge strength ratio - 1; + = harder,
a decal or rim; - = smudged), outline (1 - IoU of the alphas).

## Findings while building (2026-10-19)
- **blender_game's merge_vertices drops every explicit back face** (Blender holds one face per vertex set): rc2n hair
  24,520 -> 14,110 triangles drawn, Garrett hair shells 13,068 -> 11,184 (and 1-2 cloth triangles). Unmerged, Blender
  still drops them (they reuse the front's vertex indices). The game renders survived only because blender_game draws
  everything two-sided; an engine-faithful cull would have drawn the cards half-sided. judge counts them
  (glb_merged_faces) and draws such meshes two-sided.
- The hair in rc2n is NOT doubleSided in the GLB (explicit back faces instead); only lashes are doubleSided.
- Photo-lit renders read +5..+17 L* brighter than Tess's photo crops (skin_read.photo_light "measured": False, EV 0):
  run skin_read's exposure read before trusting vs_photo L* deltas; the shape / edge measures are unaffected.

## Proof (runs in /mnt/data/hifipushie/judge/runs)
- Tess rc2t vs rc2n (ref), --head tp_k19: all checks pass. MOUTH sharp +0.07..+0.48 (photo-lit 3/4 +0.47, front
  +0.48): the lip "sticker" (hard decal) of rc2t. BROWS L50 -0.6..-3.0, sharp -0.02..-0.10 (darker, softer: "brows
  smudged"). Blind A/B vs the photo (ab/rc2n_rc2t): controls passed; the reviewer's descriptions match the key (rc2t
  = "clean / crisp-edged airbrushed lips", "soft, blurry brows"); this reviewer preferred rc2t 3-0 against the PHOTO
  (the earlier 1-3 loss was against the approved stage render: different reference, not comparable).
- Garrett v8 with --swap hair = sh3d vs sh4T (ref), --head gp_h6c: HAIRLINE sharp +0.22..+0.98, spot 8.5-13.9 L*,
  blotch up; worst@ lands on the black hairline rim (checked by eye on the 3/4 photo-lit crop). Crown / nape L50
  +5..+8 (sh3d paler there).

## Left / next
- The APPROVED head's render as a reference: approve get gives a workspace model (tp_k19, gp_h6c), not a GLB; judge
  renders GLBs only. Next: `judge shots --model <name>` through a head-only export (asset.export_asset, cached in
  judge/approved/), or blender_scene's stage render at judge's cameras with the same state record.
- Pose: shots are at rest (A-pose). Expression / pose sets (blender_game "shapes" / "turns") are not in SHOTS yet.
- Photo exposure: vs_photo L* needs skin_read's measured EV (see above).
- Profile face crops: MediaPipe is unreliable at 90 deg; profile is only in g1m / g3m.
- review-ab itself has no control trios: judge adds them as items; run `judge ab` without --dry after 13:00 MT.
- LODs: run `judge shots <asset>_LOD<n>.glb` (the report json is found by the LOD rule in blender_game).
