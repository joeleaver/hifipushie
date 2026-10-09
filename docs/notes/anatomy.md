# hifipushie notes: anatomy

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

- `anatomy.py`: modelling lore by joint type instead of a kit per body part (`spec["anatomy"] = {}` opts in; per-joint
  overrides). Limb roots are found from the skeleton (side chains of 2+ bones: next to a centre hub, or the chain's
  inner end). Each gets a cap (one bowed, flattened bone over the joint's outer side: separate heads read as lumps),
  and, beside the body (limb runs back along the body's axis: arms), pec/lat sheets ending on the limb's inner side
  (the pit's folds); leaving the body's end (legs, a quadruped's legs), a round bowed mass behind (glute, triceps) and
  no front sheet. The joint's bones slim to 0.8 r there. Sheet origins are seated by a ray from inside the torso
  (`_exit`; from outside the fox's glute landed on its tail). Expands after kits, before strokes (`expand_mirror`,
  `fit`, `paint`). Tried on troll, goblin (arms moved clear of the belly: `goblin_anat`), fox (`*_bare` / `*_anat`).
  Hinges (every joint inside a limb chain): a small crisp bony point on the extensor side (rest bend projected onto
  the front-back plane: an arm hanging out from the body bends sideways, which isn't flexion), bones slimmed 0.9.
  Each limb's bones become one group (join 0.15 x the thinnest hinge), blended into the body once: one by one they
  swelled all round every joint. `spec._compile` gives every group member the group's first blend/join: the
  evaluator culls per chunk, so a group with mixed blends blended differently chunk to chunk (dotted seams).
  Digit fans (the kits' `<kit>_f<n>_<k>` / `_th_` chains): knuckles on the back (the palm side is where the digits
  curl), webs between neighbours, a pad before the roots, a thenar pad. `kits._digit` now makes one bone per phalanx
  (hard min): three short segments per phalanx left a ring at each boundary, and a join blend swelled there instead.

