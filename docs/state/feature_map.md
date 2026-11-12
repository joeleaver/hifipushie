# The feature map (a sculpt read from its reference pictures): STATE 2026-11-12
Branch `feature-map` (worktree .claude/worktrees/feature-map), from main c3288704. Not pushed, not landed; bin/suite
NOT run (tests/test_featuremap.py, toolsets, find_jobs, skill_file pass). Ledger C434 (recheck the number).
For Baynard Racing's sculpting-from-references project (`baynard-racing/workspace/scraps/SCULPT_PROJECT.md`): two
racers were judged on their outline with nothing inside it made. Joe's rulings: reference PICTURES only (no
generated mesh as input); every trial by a blind Opus 5.5 medium agent with the page alone.

## What the tools hold (module docstrings are the spec; the sculptor's page is guide(topic="features"))
- `read_reference` (refread.py): a sheet cut into views; front / back / side / side_r get a far camera at the
  sheet's scale in matched.py's format (<model>/cameras/<view>.json: look_matched, feature_tiles, fit_matched work
  from a turnaround view; checked pixel-aligned). Per view: numbered PATCHES (cut along steps in brightness and
  colour, joined by colour plus the line between: a plain subject has patches too) and FORM LINES.
- `mark_features` (featuremap.py): kind mass / form / paint + on, join, separate, authority, inferred, says,
  elements; marks per view (patches, box, ellipse, polygon, line, lists, minus, mirror; null clears) kept as masks.
  Owes: UNMARKED (> 2 %, hatched, boxes listed), DISAGREE, SIDE, DEPTH, ON.
- `feature_report` (featuresee.py, featurerays.py, featurealign.py): the whole outline per picture, then per
  feature and view NOT MADE / HIDDEN / OFF / right / IN ITS MASS / CAN'T MEASURE. An added shape's footprint is the
  skin it OWNS (nearest own surface at the hit; a shell part whole); a cut's or stroke's is what changes when it
  leaves the EXPANDED spec. A model not built from the map is first laid under the flat views (scale, ground, a
  side view's centre; reported). Kept between calls: 108 s cold, 4 s when only marks or links change.
- `build_masses` (masses.py): a marked mass becomes a shape from its marks: ball (+ socket), drum, flap, trunk,
  tube. The built elements are linked in the map; the model then lives in the map's frame.
- guide.md: stage 0 = the map; blockout gate = every mass made and right; stage 3 = every form made. Every save
  of a model with a map prints how much of it no element makes.

## Proof, and where it stops (trial files: /mnt/data/hifipushie/featuremap/; notes: baynard SCULPT_PROJECT.md 11-12)
- tests/test_featuremap.py (8; ~1 min): a figure draws its own turnaround; the true model all right; planted
  faults each found; its masses rebuilt from the marks alone land on the picture (ball, drum, flap, socket, tube).
- MAP, blind: Scraps 46 features in 8 rounds (Joe: "it looks pretty good to me"); the troll 58 in 7.
- MEASURE, blind, the troll told to be the true model (2de593ca): 7 -> 31 right of 37 in six report rounds, 19
  min; the six left explained (2 px warts, a 3 mm crease, a buckle that is a layer of a shell, one own mark).
- BUILD, blind, the troll (d77063f9): 8 rounds, outlines 93-95 %, volume overlap with the true troll 0.80,
  surface median 9 mm off (troll3/score.py). Scraps (08024656): 8 rounds, outlines 85-90 %, by eye a lumpy toy,
  cruder than the old hand-typed sculpt in head, horns and limbs (baynard picture 09). NOT a pass.

## Open faults, worst first
1. The block-in is too crude to gate: marks typed as rough polygons (ribbed trunks), a trunk can't be narrower
   in front than behind, a flap lies in its broad view's plane, a tube's curl out of both views is lost,
   `authority` changes no build. NEXT below.
2. No forms yet (sockets, brows, lips, fringes: where a character's read lives). A form a mass's own shape makes
   is ["="], unmeasured; there is no FORM measure.
3. A perspective picture's camera comes from fit_concept_camera (the MODEL's outline): circular on a rough
   model. Solve it from the map's own features. Not built.
4. Shell parts are owned whole (a buckle = the whole belt); a garment over two legs has no kind.
5. matched.mask_of lost a white tuft against a light background (read_reference says check, takes mask=).
6. featuresee.py is ~570 lines: footprints wants its own module.

## Decisions in force, and dead ends
- Pictures in, nothing else; trials by a blind Opus 5.5 medium agent; the builder fixes the tool, never coaches;
  what a subject's features are is the sculptor's judgement per subject (the page names no subject).
- Dead: a mass measured with everything on it (a head's mark would hold its ears); a change counted from a share
  of the feature's own largest, to drop halos (it moved small features' centres).

## Commands
- Trials: `FM_OUT=<dir> /mnt/data/hifipushie/featuremap/fm <tool> '<json>'` (`fm` points at frozen1 = c34ad512:
  repoint PYTHONPATH first). Troll re-measure: troll/recheck.py (the agent's map: troll/features_as_the_agent_left_them).
- `PYTHONPATH=src ../../../.venv/bin/python -m pytest -m "" tests/test_featuremap.py`
NEXT: marks cut from the figure's own outline (a seed point and cut lines), smoothed trunk profiles, tilted
flaps, authority in builds; the blind Scraps build again; then forms laid on the masses from marks in a view.
