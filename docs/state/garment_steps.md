# STATE: garment steps -> the process every garment follows (agreed with Joe, 2026-11-02)

Joe: "I don't want to do another agent run until we've got tooling and process in place for all [the] steps. Then I want
to take the steps one at a time, iterating until we're good at each one." "I don't want to keep building specific
drafters. Agents should have enough general intelligence to build a fresh pattern using FreeSewing, based on 3d
measurements of the model." "we don't know what measurements we need until we see the clothing and discern what seams
there are." "What about a 'parts' step, where we inventory what needs to be built, what's occluded, etc? And should we
identify the style and make a styling strategy early? ... why build the shirt closed and then style it open, if we only
need it open?"
Every step has: an input, an output, ONE tool, a gate (measured against something named; each FAIL says what to change
AND which step to go back to), and a look (the step's own result beside the reference, never a later step's). A step
consumes only the approved output of the step before it. Every step is iterated on TWO garments together (the shirt and
the hussar jacket), so no tool quietly becomes a shirt tool.

| # | Step | Output | Tool today | Gate today | Missing |
|---|---|---|---|---|---|
| 0 | Read the reference | what the garment is: kind, cloth (thickness, stiffness, weight, colour, print, grain), fit (ease) | `garment_from_reference`: fixed choices (collar type, buttons, pockets, cloth, colour) | none | the reading for any garment; cloth as numbers the build and sim use |
| 1 | Parts inventory | every piece and detail: seen / occluded / inferred (and from what convention), how far each must be built (full / simplified / left out: a shirt body under a closed jacket), the layer order | none | none | the whole step; its look: the inventory drawn over the reference, occluded parts marked |
| 2 | Style plan | the ONE worn state to build (open / closed, collar spread, rolled sleeves, tucked), as bends and targets; the pose; which rows the photo judges | only wear="open"/"closed" on the build | none | the whole step. The state is built directly (no build closed then styled open); styling is bends, lengths never change |
| 3 | Measure | every measurement steps 1-2 call for: body ones in 3D by name, style ones as proportions off the reference | `tailor.measure`: a fixed FreeSewing list inside design_garment | none | measurement BY NAME as a tool; its look: the tape lines on the body |
| 4 | Draft | flat pattern + what FreeSewing can't draw: seam pairs, stiff pieces, folds (incl. style folds: a rolled cuff), closures | `design_garment`: PUBLISHED designs (Simon) through per-design glue | `pattern_check` (flat gate) | an agent-written FreeSewing design extending a block (brian, bent...); the declarations; ONE general converter; general pattern_check rows (every seam has a partner of its length, every inventoried piece cut); a pattern brought in, graded to the body |
| 5 | Chains in 3D, in the planned state | the pattern's edges as exact-length chains; stiff parts first; only bends chosen; resting on the body OR the garment under it (layering) | `chain_garment` BAND, FALL, RINGS, SOFT NETWORK, PLACKETS | a free chain > 2 % off its cut is refused | roles beyond a shirt; the band built in its closure's own state (run 3: always closed, the likely cause of the points held together + the front.R stretch); layering; a look at the chains alone: DONE F5 (stage gates start / chains / surfaces, chain_stages.py) |
| 6 | Surfaces, checked | the garment surface | `chain_garment` SURFACES | STRUCTURE (`chain_structure`): shirt rows, several targets INFERRED | rows from steps 0-2 for any garment (construction + the style plan's targets); a row for rough / crumpled cloth |
| 7 | Details and trims | solid details (buttons, frog knots, zip pulls) as geometry AT the pattern's marks, riding the cloth | T10 | every inventoried detail placed | WHERE is decided once, at step 4 (marks on the pattern, as a pattern maker marks button placement); fastening acts at step 5 (the marks tied); step 7 makes only the geometry; cloth details (pockets, tabs, epaulettes) are pattern pieces at step 4; a trim that stiffens its edge declares that at step 4 |
| 7a | Look and approve before the sim | the built, detailed garment beside the reference (structure only, no folds), blind review, approval | look_chain shows the build; approve | the structure gate's PASS only | the approval itself before the hang: REQUIRED internally (every development run: nothing is hung that wasn't approved built), OPTIONAL for agents in the shipped tool (a setting) |
| 8 | Sim | folds only: soft cloth under gravity (ZOZO), stiff parts and the plan's state held | `chain_garment` HANG after the structure PASS | lengths after the hang | threads past the cap in the answer and the gate (open wear: 1 in 5 faces) |
| 9 | Look and approve | the garment beside the reference, blind review, approval | look_chain, review_view, approve | blind look | one sheet per garment from the step-0 reference |
| 10 | Export | game mesh, retopology, skinned to the character's rig | none for chain garments | budgets | the whole step |
Known for iteration: steps 5-6: plackets: the front edge kinks between buttons, fronts meet 0.86, open plackets ragged (Joe saw it on the T14 shirt; rows placket_straight + closure_front FAIL); the build mesh's irregular border strip (test: rows
following the outline; are the ragged plackets from it?). Step 8: open wear hung with 1 in 5 faces past the thread cap.
ORDER: tooling for every step first; then the steps one at a time, shirt + hussar together, each iterated until good.
## Tooling runs (one deliverable each, in order; "minimal" = the step works end to end for any garment, not yet good)
| # | Run | Steps | Size | Needs |
|---|---|---|---|---|
| T1 | Garment record: one file per garment holding each step's output, its status and approval; a FAIL's "back to step N"; one look sheet per garment from the step-0 reference | all, 9 | S | DONE (C281) |
| T2 | Pre-sim approval (required internally, a setting for agents) + threads past the cap in the hang's answer and gate | 7a, 8 | S | DONE (C282) |
| T3 | Measure by name: girth at a level, arc between landmarks, surface length, the landmark list; tape lines drawn as its look | 3 | S-M | DONE (C283) |
| T4 | Reading, parts inventory, style plan: tools that write them into the record, validate them, and draw them over the reference (occluded / inferred marked) | 0, 1, 2 | M | DONE (C284) |
| T5 | Agent-written FreeSewing: the agent's design (extending a block) run in Node; its declarations (seam pairs, stiff pieces, folds, closures); one general converter; pattern_check rows general. Proof: a shirt drafted fresh from brian, no Simon glue | 4 | L | T3, T4 |
| T6 | Structure rows from the record: targets from the reading + style plan, never INFERRED shirt rows; a crumpled-cloth row | 6 | M | T4 |
| T7 | Chains in the planned state: the band in its closure's own state; build straight into the style plan | 5 | M | T4, T6 |
| T8 | Chain roles beyond a shirt: stand collar, panels with tails / cutaway, waistband, zip | 5 | L | T5 |
| T9 | Layering: chains rest on the garment underneath | 5 | M | T7 |
| T10 | Details and trims: buttons, braid, frogging, tabs on the surface, following it through the sim | 7 | M-L | T7 |
| T11 | Export: chain garment -> game mesh, retopology, skinned to the rig | 10 | L | T10 |
| T12 | Layering, VISIBLE-ONLY by default (Joe 2026-11-02): the under garment's hidden pieces omitted, its visible parts (collar, cuffs, tails, an open V) fitted inside the over garment's openings and held there; the over garment on the body + the under cloth's thickness + its built stiff / solid parts; no joint hang. Full compression + joint hang only when the plan asks (the over garment comes off at runtime, a close-up) | 1, 2, 5, 8 | M | T9 |
| T13 | Draped garments (cloak, cape, hood): the gate split: fitted parts judged at the build, the fall judged on the hang; the head in the body for a hood | 6, 8 | M | T12 |
| T14 | Appearance: materials, colour variation, stitching, worn leather, a ragged hem, restrained weathering from the story, painted on the pattern's UVs | new, before 9 | M-L | T11 |
| T15 | Outline vs reference: step 2 traces the reference's key edges (hem, collar top, front edges, cutaway) as lines on the photo; step 4 checks flat edges against them, step 6 compares the build's outline in that view (mm, where, which pattern edge to redraw). Joe: "It still doesn't have any of these curves right": ratios passed an arc for a stepped notch | 2, 4, 6 | M | T5b |
Test garments: the shirt, the hussar jacket, the RANGER outfit (/mnt/data/hifipushie/refs/ranger/front.png; layering 4-5
deep; leather goods = stiff-leather pieces from patterns; boots out of the garment route for now), Garrett's outfit (t8).

DONE: T1-T15, F1-F10, s0-fix landed (C281-C335): record, approvals, body_tape, garment_plan, draft_pattern + flat gates (shape,
seam_ends, body_lengths), structure + outline rows, stage gates (chain_stages), details, export, appearance, SDF block-in.
DRIFT FOUND (Joe 2026-11-03): from F4 the build placed WHOLE pieces then corrected them (F4 start, F7/F8 flat+sew, F9/F10
block-in map) instead of steps 5-6 as agreed: chains at exact lengths first, surfaces filled between. Rebuild 5-6 as agreed.
METHOD NOW (Joe 2026-11-03): one STEP per blind trial (/mnt/data/hifipushie/trials/s<step>-<n>/: hp client pinned to main),
judged with Joe beside the reference, fixed, rerun, then the next step; tests run once when a step is declared done.
STEP 0 APPROVED, hussar (Joe 2026-11-03): s0-7, trials/s0-7/ws (C336-C342). STEP 1: s1-1..s1-4 -> C343-C346; s1-5 good,
a sleeve cap sewn in two seams -> C347 (one seam per edge unless stacked layers). NEXT: blind s1-6; clean -> Joe approves.
