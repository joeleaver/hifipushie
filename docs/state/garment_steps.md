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

Known from runs 1-3 (kept for when each step comes up): step 5, run 3 (archive/chain-run3, not landed): the band resting
on the high points fixed the collar's tilt (9.6 -> 24 deg); the band is built closed though the pattern's button is
open. Step 8: open wear hung with 1 in 5 faces past the thread cap.

ORDER: tooling and process for every step first (no agent iteration runs until then); then the steps one at a time,
shirt + hussar jacket together, each iterated until good.

## Tooling runs (one deliverable each, in order; "minimal" = the step works end to end for any garment, not yet good)
| # | Run | Steps | Size | Needs |
|---|---|---|---|---|
| T1 | Garment record: one file per garment holding each step's output, its status and approval; a FAIL's "back to step N"; one look sheet per garment from the step-0 reference | all, 9 | S | DONE (C281) |
| T2 | Pre-sim approval (required internally, a setting for agents) + threads past the cap in the hang's answer and gate | 7a, 8 | S | T1 |
| T3 | Measure by name: girth at a level, arc between landmarks, surface length, the landmark list; tape lines drawn as its look | 3 | S-M | T1 |
| T4 | Reading, parts inventory, style plan: tools that write them into the record, validate them, and draw them over the reference (occluded / inferred marked) | 0, 1, 2 | M | T1 |
| T5 | Agent-written FreeSewing: the agent's design (extending a block) run in Node; its declarations (seam pairs, stiff pieces, folds, closures); one general converter; pattern_check rows general. Proof: a shirt drafted fresh from brian, no Simon glue | 4 | L | T3, T4 |
| T6 | Structure rows from the record: targets from the reading + style plan, never INFERRED shirt rows; a crumpled-cloth row | 6 | M | T4 |
| T7 | Chains in the planned state: the band in its closure's own state; build straight into the style plan | 5 | M | T4, T6 |
| T8 | Chain roles beyond a shirt: stand collar, panels with tails / cutaway, waistband, zip | 5 | L | T5 |
| T9 | Layering: chains rest on the garment underneath | 5 | M | T7 |
| T10 | Details and trims: buttons, braid, frogging, tabs on the surface, following it through the sim | 7 | M-L | T7 |
| T11 | Export: chain garment -> game mesh, retopology, skinned to the rig | 10 | L | T10 |
About 11-14 runs at the run budget. The shirt and the hussar jacket are the test garments of every run from T4 on.

T1 DONE (2026-11-02, branch t1-record, C281): `garment_record.py` (STEPS = the one step list), file
workspace/<model>/garments/<garment>.json (+ <garment>/ for looks and sheet.png); tool garment_record(name, garment,
sheet) in the cloth group. Writers: pattern_check -> 4 (gate rows, flat sheet as look); chain_garment's worker -> 5, 6
(structure rows), 8 (hang); look_chain (focus None) -> 6's look (build) / 9 (hung). Approval only through bin/approve:
`approve add garment <model>.<garment>.<step> <record>#<digest> <sheet> joe|coordinator` (the answer prints it); held
while the digest holds. 7a: required unless HIFIPUSHIE_PRESIM_APPROVAL=optional; steps needing approval: 7a, 9 (STEPS'
approval column). Gaps: steps 0-3, 7, 7a, 10 have no writer yet, so on today's garments pattern_check / chain_garment
answer "record: ... refused: step 3 (measure) is not ready" (the tools still run); T2 must stop the hang before 7a.
Unverified: a real build / hang writing the record (tests stub them); the sheet on real looks.

NEXT: T2 (pre-sim approval in chain_garment: no hang until the record's 7a is ready; threads past the cap).
