# Organic characters by the artist's passes: STATE 2026-11-14 (evening)

Branch `hands` (worktree .claude/worktrees/hands, from main 94f97701), 10 commits with this one, NOT pushed, NOT landed, `bin/suite`
NOT run (targeted tests only: tests/test_reshape.py, test_beside.py, the front-door and registry tests: 36 pass).

## Rules in force (Joe, 2026-11-14; each is a memory file too)
- Model with intent, never by numbers: a result is judged by a critical eye and by intent (an arm is an arm, riggable).
  Never lead with overlap. Reading a shape off a mesh or off pictures is not the goal.
- Artist first, not tool first: a process or a vocabulary is derived from what working artists do (looked up), never
  from the tools that exist. The pass order: reference, whole-figure blockout, merge, big forms, medium, fine, retopo, rig.
- The user is an LLM with only the MCP, and it judges its own work. Tests: a blind Claude Opus 5.5 medium agent with
  nothing but its assignment. The process must end up in the guide, not in a trial page.
- A comparison is a list of questions: an agent departs from the concept on purpose (a pose for the rig).
- Usage: check get_usage before every agent launch and ask Joe past ~70% (p5 was launched at 80% unasked: don't).
- A running trial pins the worktree: no source edits there until it reports.

## What the branch holds
- `fuse(name, a, b, fill | width, sides)` (reshape.py, spec._fuse): masses joined first, each by its own fill and
  sides (a side eases from the fuse's middle to that side's face), then blended in once; width solves the fill.
- `grab(name, of, view, at, to, radius)` (deform kind "grab", spec._grabs): the move brush as a warp of named masses
  from a flat ruled view, through the view's whole depth; mirrored; at most half its radius. Its field is NOT scaled:
  the steepness rides on Prim.lip and the mesher's band (BUILD_VERSION 32).
- Blob `aim` ({"long", "flat"} as words or vectors) instead of `rot`.
- `look_beside(name, views, ignore, on_purpose)` (beside.py): per flat reference view, from the field in seconds:
  reference | model with the reference's outline and inside lines in red | difference, worst places numbered; each
  place's grab call; a difference recorded on purpose (with a reason, kept in features/on_purpose.json) is shown
  pale and left out of the list and the overlap. Every save points to it.

## Blind trials (Opus 5.5 medium; /mnt/data/hifipushie/drawing_board/trials/<id>/: ASSIGNMENT.md, out/log.md)
| id | tools | result (coordinator's eye) | calls | the agent's own verdict |
|---|---|---|---|---|
| bs1, bs2 | none (a written build sheet) | set aside: the page copied hifipushie's primitives | 10, 17 | - |
| p1 | main | teddy bear: round ears, two balls, noodle arms | 41 | right: named those three |
| p2 | + fuse, grab | bean with paddle ears; outline 0.91 and reads worse | ~50 | right: "one bean" |
| p3 | + look_beside, page judged on masses reading | reads as the character at blockout level; ears flat discs, neck a pinch, no chin | 40 | right |
| p4 | + on purpose, aim, fuse sides | worse than p3: jaw ledge, ridge up the side, thin paddle ears (one floating), boxy head. Ledge, ridge and a back bulge were bugs in fuse and grab | ~54 | right |
| p5 | p4's, bugs fixed (31d164c3); same page | best so far: head and body one mass, creased in front and smooth behind, eyes and hooves their own pieces, clean from every side. Ears are teddy flaps, head too big for the body, snout a soft lump | 41 | right: named those three |
The agents' self-judgement was right five times out of five at whole-figure level. One run each: p4 -> p5 changed
only the bug fixes, so p4's drop was mostly the bugs. Pictures: workspace/drawing_board/p5_vs_p4_vs_p3.png.

## Open faults, by evidence (trials that hit them)
1. Ears are wrong in all five (horns, paddles, discs, paddles, teddy flaps). p5 spent four rounds on the ear's direction
   and "could not predict how a direction would look". A blade can't be a thick flap that rises from a root and folds
   over with a hanging tip: that wants to be one act.
2. look_beside prescribes outline matching: p5 made its two suggested grabs, the overlap rose to 95 / 92 / 96 and the clay
   got worse; it took them off ("the numbers rewarded what was really a regression"). The rings were the grab bug
   (fixed, b38deb87), but a 7 cm grab from the side still cuts a trench across the whole back. Decide: the eye says
   what KIND of difference a place is (a free end short, a join tight, a mass wide) and stops handing out a grab per
   place, or its radius gets a floor from the mass's size. Only its wording was changed so far.
3. The painting's angle: side by side only, no difference list, one-colour clay so parts vanish (p3, p4, p5). p5 also
   asked for the arms shown in the concept's pose for the comparison only.
4. Flat fronts and soles want a cut (snout, hooves: p3, p4, p5; Joe: booleans). Looked up: sculptors trim from a view
   (everything one side of a line, through the depth) and carve with a shape (live boolean). The spec's csg `cuts`
   (sdf.sd_csg) can carry both; no tool yet.
5. Nothing flags form inside the outline: the jaw shelf was caught only by turning the model small (p4, p5).
6. A piece that floats is not flagged (p4's ear).
7. A tool's `save` with a relative path lands in the server's folder, not the caller's (p5 wrote into the worktree);
   read_reference needs absolute paths.
8. The marks route (mark_features, build_masses) costs too many calls: skipped in all five.

## Dead ends (this thread)
- A loft read off the generated goat: bodies and limbs only, helmet for a head, joins fail; a copy, not modelling.
- The build sheet as a parts list with fixed kinds, moves and join finishes: modelled on the existing tools.
- A pass defined as "proportion and silhouette": invites outline matching (C450 again).
- Counting recorded review "ties": 8 of 9 were judge_ab failing to read shortened region names (task card filed).
- Dividing a grabbed mass's field by the grab's stretch, all over (a bulge 30 cm away, p4) or only where it bends (rings
  round a dent, p5): any scaling changes how the mass blends with unbent neighbours.
- A fuse's side that switches at the fuse's middle (a ridge up the figure, p4).

## Where things are
- Record index: memory `organic-from-concept-record`; workspace/drawing_board/form_changes_asked.md and the files beside it.
- Trial tool command: trials/<id>/tool + call.py (an MCP client into an empty HIFIPUSHIE_HOME; p2 to p5 run the branch).
- Scratch rebuilds: trials/hands_scratch/ (home_p4, home_p5, p4_fixed.png, p5_v6_fixed.png).

NEXT (ask Joe first: usage was at 80% of the week): build 1 (the ear flap) and 4 (the cut: trim from a view, carve with
a shape), settle 2, then one blind rerun on the same page. Before landing: bin/suite, a ledger row, CLAUDE.md's thread
line (the file is at its 8 KB limit: something has to go), and the passes moved from the trial page into the guide.
