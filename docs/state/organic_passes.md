# Organic characters by the artist's passes: STATE 2026-11-14

Branch `hands` (worktree .claude/worktrees/hands, from main 94f97701), 5 commits, NOT pushed, NOT landed, `bin/suite`
NOT run (targeted tests only: tests/test_reshape.py, test_beside.py, the front-door and registry tests: 27 pass).

## Rules in force (Joe, 2026-11-14; each is a memory file too)
- Model with intent, never by numbers: a result is judged by a critical eye and by intent (an arm is an arm, riggable).
  Never lead with overlap. Reading a shape off a mesh or off pictures is not the goal.
- Artist first, not tool first: a process or a vocabulary is derived from what working artists do (looked up), never
  from the tools that exist. The pass order: reference, whole-figure blockout, merge, big forms, medium, fine, retopo, rig.
- The user is an LLM with only the MCP, and it judges its own work. Tests: a blind Claude Opus 5.5 medium agent with
  nothing but its assignment. The process must end up in the guide, not in a trial page.
- A comparison is a list of questions: an agent departs from the concept on purpose (a pose for the rig).

## What the branch holds
- `fuse(name, a, b, fill | width)` (reshape.py, spec._fuse): two masses joined first, smooth by fill, then blended in
  once; width solves the fill from the waist. BUILD_VERSION 30 (a fused mass's reach covers its fill).
- `grab(name, of, view, at, to, radius)` (deform kind "grab", spec._grabs): the move brush as a warp of named masses
  from a flat ruled view; mirrored; at most half its radius.
- `look_beside(name, views, ignore)` (beside.py): per flat reference view, from the field in seconds: reference |
  model with the reference's outline and inside lines in red | difference, worst places numbered; the text gives each
  place's grab call and the reference's inside lines the model has no line near. Every save points to it.

## Blind trials (Opus 5.5 medium; /mnt/data/hifipushie/drawing_board/trials/<id>/: ASSIGNMENT.md, out/report.md or log.md)
| id | tools | result (coordinator's eye) | calls | the agent's own verdict |
|---|---|---|---|---|
| bs1, bs2 | none (a written build sheet) | set aside: the page copied hifipushie's primitives | 10, 17 | - |
| p1 | main | teddy bear: round ears, two balls, noodle arms | 41 | right: named those three |
| p2 | + fuse, grab | bean with paddle ears; outline 0.91 and reads worse | ~50 | right: "one bean" |
| p3 | + look_beside, page judged on masses reading | reads as the character at blockout level; ears flat discs, neck a pinch, no chin | 40 | right: named those three |
The agents' self-judgement was right three times out of three at whole-figure level. p2 -> p3 changed the tool AND one
line of the page, so the gain is not attributable to one of them.

## Open faults, by evidence (trials that hit them)
1. A deliberate departure (arm pose) is ranked as the biggest difference every round (p1, p2, p3): no "on purpose".
2. No way to aim a mass by a direction ("face forward, tip out and down"): ears came out horns, paddles, discs (p1-p3;
   gap 2 of 2026-11-04).
3. The fuse is the same all round: tight = bean, loose = snowman; the concept is smooth behind, jowl in front (p2, p3).
   Three masses in one fuse share a fill and inflate.
4. `grab` was never used by a blind agent (p2, p3): unproven in blind hands. They retype the spec.
5. Nothing compares from the painting's angle with an overlay; its camera fit came out mirrored once (p3). No flat-view
   number shows "the head reads as its own mass" (p2, p3).
6. Flat faces and hoof blocks want a cut (Joe: booleans); cuts exist only as spec keys documented for props.
7. The marks route (mark_features, build_masses) costs too many calls: skipped in all three.

## Dead ends (this thread)
- A loft read off the generated goat: bodies and limbs only, helmet for a head, joins fail; a copy, not modelling.
- The build sheet as a parts list with fixed kinds, moves and join finishes: modelled on the existing tools.
- A pass defined as "proportion and silhouette": invites outline matching (C450 again).
- Counting recorded review "ties": 8 of 9 were judge_ab failing to read shortened region names (task card filed).

## Where things are
- Record index: memory `organic-from-concept-record`; workspace/drawing_board/form_changes_asked.md (ten form changes
  asked for across the Braynard record) and the extraction files beside it.
- Pictures: workspace/drawing_board/p3_vs_p2_vs_p1.png, p2_vs_p1_vs_concept.png, p1_blockin_vs_concept.png.
- Trial tool command: trials/<id>/tool + call.py (an MCP client into an empty HIFIPUSHIE_HOME; p2, p3 run the branch).

NEXT: build 1 (on purpose, recorded with a reason and left out of the ranking), 2 (aim by direction) and 3 (the fuse's
sides), rerun blind as p4 on the same page; then the cut. Before landing: bin/suite, a ledger row, CLAUDE.md's thread
line (the file is 12 bytes under its 8 KB limit: something has to go), and the passes moved from the trial page
into the guide.
