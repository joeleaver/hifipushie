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
- `feature_report` (featuresee.py, featurerays.py): the whole outline per picture, then per feature and view NOT
  MADE / HIDDEN / OFF / right / IN ITS MASS / CAN'T MEASURE. Flat views are first laid on the model (scale, ground,
  a side view's centre line; reported). Footprint = pixels whose first surface changes when the feature's elements
  leave the EXPANDED spec, inside those shapes' bounds, where the front surface is one of its own parts; the
  pieces at the mark are compared. Compiled ray march (numba; numpy fallback). The last report is kept.
- guide.md: stage 0 = the map; blockout gate = every mass made and right; stage 3 = every form made. Every save
  of a model with a map prints how much of it no element makes.

## Proof, and where it stops
- tests/test_featuremap.py (7; ~1 min): a figure draws its own turnaround; the true model all right; not made,
  moved 3 cm, half size, buried, built 4 cm back and 2 cm low, a line with no form: each found.
- Blind trial 1, Scraps (/mnt/data/hifipushie/featuremap/scraps/): 46 features (19 mass, 22 form, 5 paint), 8 map
  rounds, 52 calls, 41 min, nothing owed. The old sculpt (a copy): 4 right, 27 off, 1 hidden, 9 NOT MADE (muzzle,
  ear hollows, horn rings, beard fringe, can ribs and coil, teats).
- Blind trial 1, the troll drawn as its own turnaround (/mnt/data/hifipushie/featuremap/troll/): 58 features, 7
  rounds, nothing owed. KNOWN ANSWER FAILED: the true model scored 2 right of 57. After the fixes (the sheet's
  height and ground, a side view's centre, shells, slivers, halos, scatters, names), the same map on 87c2e81b:
  13 right, 43 off, 1 not made, outlines 98 %. Looked at a dozen of the off rows: most are the agent's
  retro-mapping (a lip mark given the whole jaw blob, an eye mark the hidden eyeball, a torso mark with the
  shoulders' elements); some are still the measure (below).

## Open faults, worst first
1. NOT PROVEN: an OFF row can't be trusted without looking. A blended shape taken out still changes its
   neighbours' skin inside its own bounds (a shin reaching into the foot: the leg reads 158 % tall). Try OWNERSHIP
   for added shapes (a pixel is the shape's whose own surface is nearest at the hit), keeping removal for cuts and
   strokes. Then trial 2: a fresh agent works the report until each row is right or explained.
2. A perspective picture's camera comes from fit_concept_camera, i.e. the MODEL's outline: circular on a rough
   model (Scraps: IoU 0.82). Solve it from the map's own features. Not built.
3. Slow: a 57-feature report is 6-12 min on a loaded machine; no progress line.
4. Marking is typed 2D numbers where patches don't follow a feature; the new line-bounded patches are untried by
   an agent. matched.mask_of lost a white tuft against a light background (read_reference says check, takes mask=).
5. No FORM measure (the model's form lines against the picture's): a form made by its mass's shape is ["="], unmeasured.
6. featuresee.py is 540 lines: align_flat wants its own module.

## Decisions in force
- Pictures in, nothing else; trials by a blind Opus 5.5 medium agent; the builder fixes the tool, never coaches.
- What a subject's features are is the sculptor's judgement per subject; the page names no subject.

## Dead ends
- A mass measured with everything on it (a head's mark would hold its ears): "what is seen of the thing itself".
- A change counted from a share of the feature's own largest (to drop halos): moved small features' centres.

## Commands
- Trials: `FM_OUT=<dir> /mnt/data/hifipushie/featuremap/fm <tool> '<json>'` (home .../featuremap/home; `fm` points
  at frozen1 = c34ad512: repoint PYTHONPATH first). Builder's troll re-measure: troll/recheck.py (the agent's map
  is kept in troll/features_as_the_agent_left_them).
- `PYTHONPATH=src ../../../.venv/bin/python -m pytest -m "" tests/test_featuremap.py`

NEXT: open fault 1 (ownership, then trial 2 on the troll). Then run 2: masses from their outlines (a feature marked
in two flat views becomes a shape: axis and widths from the marks, roundness and join stated), with fault 2.
