# Matched views (concept camera, feature tiles, join report): STATE 2026-11-06

Branch matched-view (worktree .claude/worktrees/matched-view), from main a27f5551. Asked for by Baynard Racing
(Puddles the pig, gap 31 in baynard-racing/workspace/puddles/hifipushie_gaps.md; prototypes camfit / camrender /
joinsee in baynard-racing/workspace/tools/). Not pushed; coordinator lands. Ledger C396; gates.md LOOK bullet.

## What the tools hold now
- `matched.py` (docstring = spec): `mask_of` (alpha, a given mask, or a border flood across soft gradients only:
  eats a soft floor shadow, keeps grey hooves), `fit_camera` (az / el / roll / f_px / aim, IoU of splatted surface
  samples vs the mask; bbox-set starts over az -60..60 x el 0/10/25, Nelder-Mead, 2x polish; each az sign fitted
  apart and a close call saved as "mirror"), `render` (blender_matched.py: Cycles clay, area lights in the camera's
  frame scaled to the model, dim lighting world, light backdrop for camera rays), `pair`, `feature_box` (the BUILT
  surface on the named elements, projected; prim bounds were 3x too big), `tiles`, `look_camera`.
- `joins.py`: seam / footprint ratio along + across, sections (up = toward the part), WARN 0.75; "a,b" = one piece.
- server: `fit_concept_camera`, `look_matched`, `feature_tiles`, `join_report` (group "concept"); put_model /
  edit_model `joins=[...]`; look `camera={"fitted": label}`. Cameras in <model>/cameras/<label>.json.
- Conventions: az as render.VIEWS (+ = toward the creature's left, +X). The prototype's az had the other sign.

## Proof on Puddles (pud2 v83, concept art/racers/puddles/concept.webp)
- Auto mask vs Joe's hand mask: IoU 0.967. Fit (auto mask): az -25.8 el +5.7, IoU 0.925, mirror az +26 at 0.912
  flagged; hand mask: az -20.5 el +7.4, IoU 0.939 (prototype: 19 / 8.5 / 0.933). ~14 s fit, ~17 s render.
- Six tiles (ears, arms, face, legs) -> bin/review: ran, FAIL, ~20 MAJOR form faults (arm elbow kink, snout ball,
  mouth dish, hoof slippers ...). Files: workspace/pud2/cameras/ (concept_pair.png, concept_tiles/review/review.md).
- Joins: ear alone 1.02 (its root counts as body); ear+earroot 0.59 (the old "v83 0.58"); arm 0.50 (a 22 cm
  footprint: hangs within 2.5 cm of the torso); tail 0.70.

## Open / next
- Mirror ambiguity is real on symmetric figures (0.925 vs 0.912): flagged, not solved. An interior cue (eyes, snout
  from a part-coloured pass vs the concept) could break the tie.
- Auto mask misses a hard contact shadow between feet; pass mask= for busy backgrounds.
- The join ratio reads "joined along its base" for ears / tails; for free-hanging limbs a high ratio is the fault.
- tests/test_toolsets.py::test_short_descriptions_point_at_the_guide fails on main too (body_tape 740 > 700).

NEXT: coordinator lands matched-view (suite), then Baynard's Puddles session uses look_matched + feature_tiles
every round.
