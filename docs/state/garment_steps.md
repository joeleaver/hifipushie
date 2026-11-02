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
| 5 | Chains in 3D, in the planned state | the pattern's edges as exact-length chains; stiff parts first; only bends chosen; resting on the body OR the garment under it (layering) | `chain_garment` BAND, FALL, RINGS, SOFT NETWORK, PLACKETS | a free chain > 2 % off its cut is refused | roles beyond a shirt; the band built in its closure's own state (run 3: always closed, the likely cause of the points held together + the front.R stretch); layering; a look at the chains alone |
| 6 | Surfaces, checked | the garment surface | `chain_garment` SURFACES | STRUCTURE (`chain_structure`): shirt rows, several targets INFERRED | rows from steps 0-2 for any garment (construction + the style plan's targets); a row for rough / crumpled cloth |
| 7 | Details and trims | buttons, braid, frogging, zips, tabs, pockets on the surface, following it | none (chain garments) | none | the whole step |
| 7a | Look and approve before the sim | the built, detailed garment beside the reference (structure only, no folds), blind review, approval | look_chain shows the build; approve | the structure gate's PASS only | the approval itself before the hang: REQUIRED internally (every development run: nothing is hung that wasn't approved built), OPTIONAL for agents in the shipped tool (a setting) |
| 8 | Sim | folds only: soft cloth under gravity (ZOZO), stiff parts and the plan's state held | `chain_garment` HANG after the structure PASS | lengths after the hang | threads past the cap in the answer and the gate (open wear: 1 in 5 faces) |
| 9 | Look and approve | the garment beside the reference, blind review, approval | look_chain, review_view, approve | blind look | one sheet per garment from the step-0 reference |
| 10 | Export | game mesh, retopology, skinned to the character's rig | none for chain garments | budgets | the whole step |

Known (runs 1-3): step 5: archive/chain-run3: band resting on the high points fixed the collar's tilt (9.6 -> 24 deg); the
band is built closed though its button is open. Step 8: open wear hung with 1 in 5 faces past the thread cap.
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
About 11-14 runs at the run budget. The shirt and the hussar jacket are the test garments of every run from T4 on.
T1 DONE (2026-11-02, t1-record, C281): garment_record.py (STEPS = the one step list); workspace/<model>/garments/<garment>.json;
tool garment_record(name, garment, sheet). Writers: pattern_check -> 4; chain worker -> 5, 6 (structure), 8; look_chain -> 6's look, 9.
Approval: `approve add garment <model>.<garment>.<step> <record>#<digest> <sheet> joe|coordinator`; needed on 7a (unless
HIFIPUSHIE_PRESIM_APPROVAL=optional) and 9. Steps 0-3, 7, 7a, 10 have no writer yet: today's tools answer "record: refused".
T2 (C282): chain_presim.py: the job stops at awaiting_approval; approval / a waiver resume from built.pkl; step 8 FAILs on
faces past the cap (back to 5). Unverified on a real build. T3 (C283): body_tape(name, measurements, garment): girth / arc /
length / height / FreeSewing names, landmark list; equals tailor.measure on wf_simon + dg_garrett. T4 (C284):
garment_plan(name, garment, step read|parts|style, plan): shirt + hussar read (/mnt/data/hifipushie/t4/). Open: step 3
needs step 1's measurement list; measurement names not checked against body_tape's landmarks; worn-over-another-garment.

NEXT: T5 + T6 in parallel (Joe: the list runs without stops; targeted tests per run, one suite at the end).
