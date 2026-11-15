# Organic characters by the artist's passes: STATE 2026-11-15 (p7)

Branch `hands` (worktree .claude/worktrees/hands, from main 94f97701), 15 commits, NOT pushed, NOT landed,
`bin/suite` NOT run (targeted tests only: tests/test_reshape.py, test_beside.py, the front-door, registry and
find-job tests: 58 pass).

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
  A fuse's fill widens the reach of its own members only (spec._set_reach).
- `grab(name, of, view, at, to, radius)` (deform kind "grab", spec._grabs): the move brush as a warp of named masses
  from a flat ruled view: a BALL of clay round the point taken hold of (its depth found on the view's ray), not the
  view's whole depth; mirrored, and the answer says so; at most half its radius. Its field is not scaled: the
  steepness rides on Prim.lip and the mesher widens its band near that primitive only (BUILD_VERSION 33).
- `flap(name, mass, root, over, tip, width, ...)`: a folded ear, comb or tongue from three points read off the
  pictures. It writes the existing "sheet" shape (sheet.py); says when its root floats and which views show it broad.
- `trim(name, of, view, a, b, off, soft)` (spec["trims"], spec._trims, sdf.sd_csg): the clay of the named masses on
  one side of a line drawn in a flat view is cut away flat, in world space after any grab; mirrored.
- `carve(name, cutter, of)`: a mass becomes a cutter of the named masses (the spec's "op": "subtract" + "targets").
- Blob `aim` ({"long", "flat"} as words or vectors) instead of `rot`.
- `look_beside(name, views, ignore, on_purpose)` (beside.py): per flat reference view, from the field in seconds:
  reference | model with the reference's outline and inside lines in red | difference, worst places numbered; a
  place asks about the mass first and offers a grab last (radius at least a third of the mass); a difference
  recorded on purpose is shown pale and left out; pieces that touch nothing are listed (FLOATS).
- look_beside's view "painting" (beside_painting.py): with the painting's camera fitted (fit_concept_camera, any
  label), the painting with the model's outline over it | the model, parts tinted, with the painting's outline and
  form lines | the add / remove map; places by the painting's pixel, mass and direction in the figure's words; which
  side of the figure the camera stands on; on purpose by pixel.

## Blind trials (Opus 5.5 medium; /mnt/data/hifipushie/drawing_board/trials/<id>/: ASSIGNMENT.md, out/log.md)
| id | tools | result (coordinator's eye) | calls | the agent's own verdict |
|---|---|---|---|---|
| bs1, bs2 | none (a written build sheet) | set aside: the page copied hifipushie's primitives | 10, 17 | - |
| p1 | main | teddy bear: round ears, two balls, noodle arms | 41 | right: named those three |
| p2 | + fuse, grab | bean with paddle ears; outline 0.91 and reads worse | ~50 | right: "one bean" |
| p3 | + look_beside, page judged on masses reading | reads as the character at blockout level; ears flat discs, neck a pinch, no chin | 40 | right |
| p4 | + on purpose, aim, fuse sides | worse than p3: jaw ledge, ridge up the side, thin paddle ears (one floating), boxy head. Ledge, ridge and a back bulge were bugs in fuse and grab | ~54 | right |
| p5 | p4's, bugs fixed (31d164c3); same page | best so far: head and body one mass, creased in front and smooth behind, eyes and hooves their own pieces, clean from every side. Ears are teddy flaps, head too big for the body, snout a soft lump | 41 | right: named those three |
| p6 | + flap, trim, carve (3bf5ed20); same page | not better than p5 as a figure: the ears FOLD for the first time and the belly is the widest mass, but the face is a bill with a shelf under it, and it made no eyes or hooves. Never called trim or carve | 62 | right: "a generic bean creature rather than this pig" |
| p7 | + the painting view, the p6 fixes (18dd7e85); same page | BEST: reads as the pig from every side. Flat-fronted snout (trim), folded ears, pear body, chunky arms close to the body, dark hooves with flat soles, tail nub, clean surface. Head a little small and round for the painting, no jaw or jowl, ears thin | 39, 6 rounds | right: named those three |
The agents' self-judgement was right seven times out of seven at whole-figure level. One run each, and runs differ
as much as tools do (p5 made eyes and hooves, p6 none): p7 has to be repeated before it counts. p7 used flap x5, trim
x2 (snout face, soles), fuse, one grab (kept), the painting view every round, two records on purpose in it.
Pictures: workspace/drawing_board/p7_vs_p6_vs_p5.png, p7_painting_view.png, p6_vs_p5.png, p5_vs_p4_vs_p3.png.

## Open faults, by evidence (trials that hit them)
1. Nothing shows the balance of the masses inside the outline (p7: "a 1.8 cm strip" while the head was visibly too
   small; asked for reference and model at one height with each mass's height and width as a part of the whole), nor
   a mass that is missing (the jaw: the inside-lines list said "a line 50 cm long"; asked for a section down the
   centre line). The inside-lines list has told no agent anything (p4, p7).
2. Outline matching: p2, p5, p6 piled clay for overlap; p7 did not (one run). The wording is the only guard.
3. The model can't be put in the painting's pose for the comparison: p5, p6, p7 recorded the arms as on purpose.
4. Relative paths: read_reference (p5, p6, p7: one wasted call each), look's save wants a .png, look_beside's a
   folder; all resolve in the server's folder.
5. read_reference's colour-patch table is noise at blockout scale (p7). Guides cost 10 of 39 calls (p7).
6. fuse by width tops out until the masses overlap more: said, but costs a call (p6, p7).
7. A sheet (the flap's shape) is the slow part of a build: 5 s with two ears, 0.3 s without.
8. carve is untested in blind hands (a mouth belongs to the next pass). What is "its own piece" is left to the agent.
9. The marks route (mark_features, build_masses) costs too many calls: skipped in all seven.

## Dead ends (this thread)
- A loft read off the generated goat: bodies and limbs only, helmet for a head, joins fail; a copy, not modelling.
- The build sheet as a parts list with fixed kinds, moves and join finishes: modelled on the existing tools.
- A pass defined as "proportion and silhouette": invites outline matching (C450 again).
- Counting recorded review "ties": 8 of 9 were judge_ab failing to read shortened region names (task card filed).
- Dividing a grabbed mass's field by the grab's stretch, all over (a bulge 30 cm away, p4) or only where it bends (rings
  round a dent, p5): any scaling changes how the mass blends with unbent neighbours.
- A fuse's side that switches at the fuse's middle (a ridge up the figure, p4).
- A grab through the whole depth of its view: a chin pull is a shelf across the face, a push on a back a trench, a
  flank pull a saddlebag (p5, p6).
- A fuse's fill counted for every neighbour's reach: an ear beside a fused head and body was evaluated over the
  whole figure (18 s builds).
- A ready-made grab call on every listed difference: agents ran them and the clay got worse (p5, p6).

## Where things are
- Record index: memory `organic-from-concept-record`; workspace/drawing_board/form_changes_asked.md and the files beside it.
- Trial tool command: trials/<id>/tool + call.py (an MCP client into an empty HIFIPUSHIE_HOME; p2 to p5 run the branch).
- Scratch rebuilds: trials/hands_scratch/ (home_p4, home_p5, p4_fixed.png, p5_v6_fixed.png).

NEXT (ask Joe before any agent; check get_usage): land the branch (bin/suite, a ledger row, CLAUDE.md's thread line:
the file is at its 8 KB limit, and the passes moved from the trial page into the guide). Then repeat p7 unchanged,
and run the same page on Scraps the goat (a transfer test: nothing here may be Puddles-shaped). Then a page for the
big-forms pass from p7's blockout (jaw, jowls, the head's size), where carve, grab and fault 1 belong.
