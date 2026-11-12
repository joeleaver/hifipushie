# The feature map (a sculpt read from its reference pictures): STATE 2026-11-12

Branch `feature-map` (worktree .claude/worktrees/feature-map), from main c3288704. Not pushed, not landed; the
coordinator lands (bin/suite has NOT been run on it; the targeted tests pass). Ledger C434 (recheck the number).
Asked for by Baynard Racing's "sculpting from references" project: `baynard-racing/workspace/scraps/SCULPT_PROJECT.md`
(diagnosis: two racers judged on their outline, nothing inside it made; Joe's ruling: reference PICTURES only, no
generated mesh as input; every trial by a blind Opus 5.5 medium agent).

## What the tools hold now (module docstrings are the spec; the sculptor's page is guide(topic="features"))
- `read_reference` (refread.py): a sheet cut into views; "front" / "back" / "side" / "side_r" get a far camera at
  the sheet's scale, saved as <model>/cameras/<view>.json in matched.py's format, so look_matched / feature_tiles /
  fit_matched / look(camera={"fitted": view}) work from a turnaround view (checked: look_matched is pixel-aligned).
  Per view: numbered colour PATCHES (Felzenszwalb, then neighbours joined by colour step) and FORM LINES.
- `mark_features` (featuremap.py): features = kind mass / form / paint + on, join, separate, authority, inferred,
  says, elements; marks per view (patches, box, ellipse, polygon, line, minus, mirror; null clears) stored as
  masks. Owes: UNMARKED (> 2 %, hatched, boxes listed), DISAGREE (flat views' heights), SIDE, DEPTH, ON.
- `feature_report` (featuresee.py): per feature and view NOT MADE / HIDDEN / OFF / right / IN ITS MASS / CAN'T
  MEASURE. A footprint = pixels whose first surface changes when the feature's elements leave the EXPANDED spec
  (strokes' and kits' pieces, mirrored twins, cuts folded into their target all nameable), where nothing stands
  in front; a mass goes with the forms on it, not the masses on it; the mark loses the masses on it too.
- guide.md: stage 0 = the feature map; the blockout gate = every mass made and right; stage 3 = every form made.

## Proof
- tests/test_featuremap.py (7; 6 in the slow tier, ~3 min): a figure draws its own turnaround; cameras recovered
  within 2.5 px; the true model all right; not made, moved 3 cm, half size, buried, a line with no form: each found.
- Blind trial, Scraps (frozen at c34ad512; /mnt/data/hifipushie/featuremap/scraps/out, calls.jsonl): 46 features
  (19 mass, 22 form, 5 paint) over front / side / back / concept, 8 map-changing rounds, 52 calls, 41 min, nothing
  owed. The old sculpt (a copy, scraps_fm) against it, re-measured on 7b07b882: see NEXT's numbers.
- Blind trial, the troll (examples/troll.json drawn as its own turnaround): see below.

## Open faults, worst first
1. A perspective picture's camera still comes from fit_concept_camera, i.e. from the MODEL's silhouette: circular
   on a rough model (Scraps: IoU 0.82). The map has the same features in the flat views and in the picture:
   solve the camera from those points instead. Not built.
2. feature_report takes 3-6 min on a 40-feature model (two field evaluations per feature, four views of rays).
   No progress line. Cache the whole-model depth per version; batch the rays.
3. Marking is still typing 2D numbers where patches don't follow a feature (shaded masses, edges): the Scraps
   agent wrote generator scripts for its boxes and polygons. A click-a-point -> the region there, or patches that
   follow form lines, would cut it.
4. A form made by its mass's own shape is not measured (["="], judged on its tile). A FORM measure (the model's
   form lines against the picture's inside the mark) is not built.
5. matched.mask_of lost a white tuft and a horn tip against a light background on Scraps' concept: read_reference
   says to check the cut-out and takes mask=, but can't repair it.
6. Patches: 5-10 s a view; `_absorb` and the numbering loop over patches one by one.

## Decisions in force
- Pictures in, nothing else. A generated mesh is never an input or a target here (Joe, 2026-11-12).
- Every trial of these tools is run by a blind Opus 5.5 medium agent with the page alone; the builder checks
  afterwards and fixes the tool or the page, never coaches (Joe, 2026-11-12).
- What a subject's features are is the sculptor's judgement, made per subject; the page names no subject.

## Commands
- Trials: `FM_OUT=<dir> /mnt/data/hifipushie/featuremap/fm <tool> '<json>'` (home /mnt/data/hifipushie/featuremap/home;
  edit `fm` to point PYTHONPATH at the worktree or a frozen copy). Test shape: /mnt/data/hifipushie/featuremap/troll/.
- `PYTHONPATH=src ../../../.venv/bin/python -m pytest -m "" tests/test_featuremap.py`

NEXT: run 2 = masses from their outlines (a feature marked in two flat views becomes a shape: axis and widths from
the marks, roundness and join stated), on the troll first, by a blind agent; with it open faults 1 and 2.
