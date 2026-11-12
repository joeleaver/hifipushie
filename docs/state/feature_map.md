# The feature map (a sculpt read from its reference pictures): STATE 2026-11-12
Branch `feature-map` (worktree .claude/worktrees/feature-map), from main c3288704. Not pushed, not landed; bin/suite
NOT run (tests/test_featuremap.py, masslines, toolsets, find_jobs, skill_file pass). Ledger C434, C434b (renumber).
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
  A PIECE is cut off the figure by cuts between labelled NOTCHES (a cut that parts nothing is refused). Owes:
  UNMARKED (> 2 %, hatched, boxes listed), DISAGREE, SIDE, DEPTH, ON.
- `feature_report` (featuresee.py, featurerays.py, featurealign.py): the whole outline per picture, then per
  feature and view NOT MADE / HIDDEN / OFF / right / IN ITS MASS / CAN'T MEASURE. An added shape's footprint is the
  skin it OWNS (nearest own surface at the hit; a shell part whole); a cut's or stroke's is what changes when it
  leaves the EXPANDED spec. A model not built from the map is first laid under the flat views (scale, ground, a
  side view's centre; reported). Kept between calls: 108 s cold, 4 s when only marks or links change.
- `build_masses` (masses.py, masslines.py): a marked mass becomes a shape from its marks: ball (+ socket), drum,
  flap, trunk, tube. A tube follows its mark's own MIDDLE LINE with its thickness read across it; an end cut from
  another mass runs on under it. The built elements are linked in the map; the model lives in the map's frame.
- guide.md: stage 0 = the map; blockout gate = every mass made and right; stage 3 = every form made. Every save
  of a model with a map prints how much of it no element makes.

## Proof, and where it stops (trial files: /mnt/data/hifipushie/featuremap/; notes: baynard SCULPT_PROJECT.md 11-13)
- tests/test_featuremap.py (9; ~1 min) and tests/test_masslines.py (6): a figure draws its own turnaround; the
  true model all right; planted faults each found; its masses rebuilt from the marks land on the picture; a
  slanted limb, a cut end, a curl, a lump lying over a mass, each with a known answer.
- MAP, blind: Scraps 46 features in 8 rounds (Joe: "it looks pretty good to me"); the troll 58 in 7. MEASURE,
  blind, the troll told to be the true model (2de593ca): 7 -> 31 right of 37 in six report rounds.
- BUILD, blind: the troll (d77063f9) 8 rounds, outlines 93-95 %, volume overlap with the true troll 0.80, surface
  median 9 mm off (troll3/score.py). Scraps twice, 8 rounds each: (08024656) typed polygons, a lumpy toy; (4e634f13)
  pieces cut by notches, 14 of 19 masses right, outlines 86 / 91 / 84 %, the best profile yet but a slab head, fat
  arms and lump horns from the front (baynard picture 10). NOT a pass either time. The limb faults were the
  tube's (C434b); rebuilt on the agent's own marks (home/scraps_four) arms and legs follow their marks.

## Open faults, worst first
1. No forms yet (sockets, brows, lips, fringes: where a character's read lives; a head whose front outline is all
   cuts is a slab until they exist). A form a mass's own shape makes is ["="], unmeasured; no FORM measure. NEXT.
2. A blind build on the new tube has not been run. A horn's splay needs a front mark that is long (a box added to
   sink its root made it a lump: the page now says not to); a trunk can't be narrower in front than behind.
3. A perspective picture's camera comes from fit_concept_camera (the MODEL's outline): circular on a rough
   model. Solve it from the map's own features. Not built. feature_tiles was not in the trial's tool list.
4. Shell parts are owned whole (a buckle = the whole belt); a garment over two legs has no kind.
5. Notches are sparse where a join has no pinch (those cuts are ruler pixels); featuresee.py is ~670 lines.

## Decisions in force, and dead ends
- Pictures in, nothing else; trials by a blind Opus 5.5 medium agent; the builder fixes the tool, never coaches;
  what a subject's features are is the sculptor's judgement per subject (the page names no subject).
- Dead: a mass measured with everything on it; halos dropped by a share of the feature's largest change.

## Commands
- Trials: `FM_OUT=<dir> /mnt/data/hifipushie/featuremap/fm <tool> '<json>'` (this worktree's src; freeze a copy per
  trial: `git archive HEAD src | tar -x -C frozenN`). scraps5/rebuild.py, scraps5/lines.py: trial 4 rebuilt, lines drawn.
- `PYTHONPATH=src ../../../.venv/bin/python -m pytest -m "" tests/test_featuremap.py tests/test_masslines.py`
NEXT: forms laid on the masses from marks in a view (a mark's footprint projected from that view's camera onto
the mass, raised or sunk), with a known-answer test; then one blind Scraps build of masses and forms together.
