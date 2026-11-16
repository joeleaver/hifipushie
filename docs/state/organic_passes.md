# Organic characters by the artist's passes: STATE 2026-11-15

On main since the merge "Merge hands" (2026-11-15; ledger C477). Trials so far ran one page on one concept (a pig).

## Current best
- p7 and its repeat p8 (same page, same commit 18dd7e85; blind Opus 5.5 medium; 39 and 52 calls): both read as the
  character from every side: flat-fronted snout (trim), folded ears (flap), pear body, hooves their own part. p7 is
  the cleaner (one grab); p8 has the better ears and 10 grab calls that left a belly crease and a chin lump. Both:
  head small against the body, no clean jaw. /mnt/data/hifipushie/drawing_board/trials/p7, p8 (page, out/, home/).
- Earlier: p1 teddy bear (no new tools); p2 bean (+ fuse, grab); p3 reads at blockout level (+ look_beside); p4 worse
  (bugs in fuse and grab); p5 clean, teddy ears (bugs fixed); p6 ears fold, duck face, lumps (+ flap, trim, carve).
- p9 (organic-eye: proportions, grab limits; 44 calls): no grab at all, a clean surface, head the dominant mass;
  ears loop up as arches, a crease at the neck from the front, no hooves made.
- Ears: flap is a thick lump (two oval cones) with its top folded, judged with look_beside focus. e5, e6 (blind,
  ear-only, after the fold_at fix): folded pig ears from every side, closest yet. Slab, masked strokes: dead ends.
- The agent's own whole-figure verdict was right nine times of nine. Runs differ most in how much they grab.

## Decisions in force (Joe, 2026-11-14 / 15; each is a memory file too)
- Model with intent, never by numbers: judged by a critical eye and by intent (an arm is an arm, riggable). Never
  lead with overlap. Reading a shape off a mesh or off pictures is not the goal.
- Artist first, not tool first: a process or a vocabulary comes from what working artists do (looked up).
  Pass order: reference, whole-figure blockout, merge, big forms, medium, fine, retopo, rig.
- The user is an LLM with only the MCP, and it judges its own work. The test: a blind Claude Opus 5.5 medium agent
  with nothing but its assignment page. The blockout's acts are in guide(topic="blockout").
- A comparison is a list of questions: an agent departs from the concept on purpose (a pose for the rig).
- Before any agent: get_usage, and ask Joe past ~70%. A running trial pins its checkout: no source edits under it.

## The tools (reshape.py, beside.py, beside_painting.py: the docstrings are the spec)
- fuse (masses into one, own fill and sides), grab (a ball of clay round the hold; mirrored, and says so), flap (a
  folded ear from root / over / tip: writes a sheet), trim (a line in a flat view cuts a flat face), carve (a mass
  as a cutter), blob `aim` by direction.
- look_beside: each flat view and the painting's own angle (fit_concept_camera once): outline over the painting,
  the painting's lines over the model, places as questions, on purpose with a reason, pieces that float.

## Open faults, by evidence (trials that hit them)
1. Proportions (organic-eye): p9 read them and its head and body came within ~2 cm. A missing mass (a jaw) still
   shows nowhere. 2. Grabs: p9 made none and no dents; one run.
3. The model can't be put in the painting's pose for the comparison: the arms are recorded on purpose instead.
4. Relative paths resolve in the server's folder: read_reference (p5, p6, p7), look's and look_beside's save.
5. Wasted calls: guides (10 of 39 in p7, 14 of 52 in p8), read_reference's patch table, fuse by width topping out.
6. A sheet (the flap's shape) is the slow part of a build: 5 s with two ears, 0.3 s without.
7. carve is untested in blind hands (a mouth is the next pass); what is "its own piece" is left to the agent; the
   marks route (mark_features, build_masses) costs too many calls and is skipped by every agent.

## Dead ends
- A loft read off a generated mesh: a copy, not modelling. A build sheet with fixed kinds and joins: modelled on the
  existing tools. A pass defined as "proportion and silhouette": invites outline matching (C450).
- Scaling a grabbed mass's field by the grab's stretch, all over or only where it bends: bulges and rings in a fuse.
- A grab through its view's whole depth: a shelf across a face, a trench across a back, saddlebags on flanks.
- A fuse's side switching at the fuse's middle (a ridge). A fuse's fill widening every neighbour's reach (18 s builds).
- A ready-made grab call on every listed difference: agents ran them and the clay got worse (p5, p6).
- A blade for a folded ear (the guide said so for five trials). Counting review "ties" (judge_ab misread regions).

## Where things are
- Trials: /mnt/data/hifipushie/drawing_board/trials/<id>/ (tool + call.py: an MCP client into an empty
  HIFIPUSHIE_HOME; point REPO in call.py and tool at the checkout under test). Scratch rebuilds: trials/hands_scratch/.
- Pictures sent to Joe: workspace/drawing_board/ (p7_vs_p6_vs_p5.png, p7_painting_view.png, earlier sheets).
- Record index of the older organic routes: memory `organic-from-concept-record`.

NEXT (ask Joe): land ear-pad (bin/suite); then the same blockout page on a second concept (Scraps).
