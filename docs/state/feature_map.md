# The feature map (a sculpt read from its reference pictures): STATE 2026-11-12
Branch `feature-map` (worktree .claude/worktrees/feature-map), from main c3288704. Not pushed, not landed; bin/suite
NOT run (tests/test_featuremap.py, masslines, toolsets, find_jobs, skill_file pass). Ledger C434, b, c (renumber).
For Baynard Racing's sculpting from references (`baynard-racing/workspace/scraps/SCULPT_PROJECT.md`). Joe's rulings:
reference PICTURES only (no generated mesh as input); every trial by a blind Opus 5.5 medium agent, page alone.

## What the tools hold (module docstrings are the spec; the sculptor's page is guide(topic="features"))
- `read_reference` (refread.py): a sheet cut into views; front / back / side / side_r get a far camera at the
  sheet's scale in matched.py's format (<model>/cameras/<view>.json). Per view: numbered PATCHES (cut along steps
  in brightness and colour: a plain subject has them too), FORM LINES, and the outline's labelled NOTCHES.
- `mark_features` (featuremap.py): kind mass / form / paint + on, join, separate, authority, inferred, says,
  elements; marks per view (piece + cuts between notches, patches, box, ellipse, polygon, line, minus, mirror)
  kept as masks. Owes: UNMARKED (> 2 %, hatched, boxes listed), DISAGREE, SIDE, DEPTH, ON.
- `feature_report` (featuresee.py, featurerays.py, featurealign.py): the whole outline per picture, then per
  feature and view NOT MADE / HIDDEN / OFF / right / IN ITS MASS / CAN'T MEASURE. An added shape's footprint is the
  skin it OWNS (nearest own surface at the hit; a shell part whole); a cut's or stroke's is what changes when it
  leaves the EXPANDED spec. A model not built from the map is first laid under the flat views. Kept between calls.
- `build_masses` (masses.py, masslines.py): a marked mass becomes a shape from its marks: ball (+ socket), drum,
  flap, trunk, tube. A tube follows its mark's own MIDDLE LINE with its thickness read across it; an end cut from
  another mass runs on under it. The built elements are linked in the map; the model lives in the map's frame.
- `build_forms` (forms.py): a marked form becomes a stroke on the mass it is on, laid from the view it was marked
  in: raise / sink along the mark's middle line, rim round a ring, a line as a ridge or groove; "view": "all";
  band: one stroke round the bone of the tube it is on.
- guide.md: stage 0 = the map; blockout gate = every mass made and right; stage 3 = every form made. Every save
  of a model with a map prints how much of it no element makes.

## Proof, and where it stops (trial files: /mnt/data/hifipushie/featuremap/; notes: baynard SCULPT_PROJECT.md 11-13)
- tests/test_featuremap.py (10; ~1 min) and tests/test_masslines.py (7): a figure draws its own turnaround; the
  true model all right; planted faults each found; its masses rebuilt from the marks and forms laid from them land
  on the picture; a slanted limb, a cut end, a curl, a lump, a foreshortened lean, each with a known answer.
- MAP, blind: Scraps 46 features in 8 rounds (Joe: "it looks pretty good to me"); the troll 58 in 7. MEASURE,
  blind, the troll told to be the true model (2de593ca): 7 -> 31 right of 37 in six report rounds.
- BUILD, blind: the troll (d77063f9) 8 rounds, outlines 93-95 %, volume overlap with the true troll 0.80, surface
  median 9 mm off (troll3/score.py). Scraps: (08024656) typed polygons, a lumpy toy; (4e634f13) pieces cut by
  notches, fat arms (the tube's fault, C434b); (76bc7660) 7 rounds, 16 of 19 right, outlines 89 / 92 / 87 %.

## Open faults, worst first
1. NO LIKENESS YET, and no gate picture. Four blind Scraps block-ins gave four different heads (baynard pictures
   9-12): one trunk is a box; split into skull, face, muzzle, jaw (trial 7, 2c15150b, scraps9/out) it is a
   long-nosed tapir, and the split body got a shoulder shelf. Parts land in the right place and size in 8 rounds;
   the SHAPE of what the flat views hide (a head behind its horns, ears, eyes) does not converge in one pass.
   Missing: the loop after the first pass (same-view tiles per feature + a blind reviewer naming the worst fault,
   each round: feature_tiles and bin/review exist, the trials did not offer them), and the perspective picture.
2. A perspective picture's camera comes from fit_concept_camera (the MODEL's outline): circular on a rough
   model. Solve it from the map's own features. Not built: the 3/4 painting has never constrained anything.
3. From trial 7: a cut end of a trunk or flap should run on under its neighbour as a tube's does (stacked trunks
   groove; a flap floats); a flap can't be turned about the upright; a horn has no taper or curl handle. Bands,
   lumps per piece and the forms fixes after trial 6 are tested but not yet used by a blind agent. Shell parts
   are owned whole; notches are sparse where a join has no pinch; featuresee.py is ~690 lines (split it).

## Decisions in force, and dead ends
- Pictures in, nothing else; trials by a blind Opus 5.5 medium agent; the builder fixes the tool, never coaches;
  what a subject's features are is the sculptor's judgement per subject (the page names no subject). Dead: a
  mass measured with everything on it; halos dropped by a share of the feature's largest change.

## Commands
- Trials: `FM_OUT=<dir> /mnt/data/hifipushie/featuremap/fm <tool> '<json>'` (this worktree's src; freeze a copy per
  trial: `git archive HEAD src | tar -x -C frozenN`). scraps5/rebuild.py, scraps5/lines.py: trial 4 rebuilt, lines drawn.
- `PYTHONPATH=src ../../../.venv/bin/python -m pytest -m "" tests/test_featuremap.py tests/test_masslines.py`
NEXT: the likeness loop (tiles + blind review each round) on the third block-in; the painting's camera. Then Puddles.
