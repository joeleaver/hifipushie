# STATE: garment steps -> the process every garment follows (draft for Joe, 2026-11-02)

Joe: "I don't want to do another agent run until we've got tooling and process in place for all 6 steps. Then I want to
take the steps one at a time, iterating until we're good at each one." "I don't want to keep building specific drafters.
Agents should have enough general intelligence to build a fresh pattern using FreeSewing, based on 3d measurements of the
model." "we don't know what measurements we need until we see the clothing and discern what seams there are."

Every step has: an input, an output, ONE tool, a gate (measured against something named, each FAIL saying what to
change), and a look (the step's own result beside the reference, never a later step's). A step consumes only the
approved output of the step before it.

| # | Step | Output | Tool today | Gate today | Missing |
|---|---|---|---|---|---|
| 0 | Read the construction from the reference | pieces, seams (which edge to which), closures, stiff parts, fit (ease), style lengths as proportions | `garment_from_reference`: picks from fixed choices (collar type, buttons, pockets, cloth, colour) | none on the reading itself | the reading as construction, for any garment; a look: the reading drawn over the reference |
| 1 | Pattern: have one, or draft one | flat pattern + what FreeSewing can't draw: seam pairs, stiff pieces, folds, closures | `design_garment` runs a PUBLISHED FreeSewing design (Simon) through per-design glue (garment_kb recipes, Simon's collar rule) | `pattern_check` (flat gate: seams, lengths, refs rows) | an agent-written FreeSewing design (extending a block: brian, bent...) run in Node; the agent's seam / stiffness / fold / closure declarations; ONE general converter; pattern_check's rows general (every seam has a partner of its length, every piece in the reading is cut). A pattern brought in from outside |
| 2 | Measure | every measurement the draft asks for: body ones taken in 3D, style ones read off the reference | `tailor.measure`: a fixed FreeSewing list, inside design_garment | none of its own | measurement BY NAME on demand (girth at a level, arc between landmarks, surface length), as a tool; the tape lines drawn on the body as its look |
| 3 | Chains for every seam, fitted in 3D | the pattern's edges as exact-length chains on the body; stiff parts first, only bends chosen | `chain_garment` stages BAND, FALL, RINGS, SOFT NETWORK, PLACKETS | lengths: a free chain > 2 % off its cut is refused by name | roles beyond a shirt (refused by name today: stand collars, tails, waistbands, zips, braid); a look at the chains alone |
| 4 | Surfaces from the chains, check the fit | the garment surface | `chain_garment` SURFACES | STRUCTURE (`chain_structure`, run 2): collar, front, V, hem, sleeve rows vs the reference | rows from the step-0 reading for any garment (today shirt rows, several targets INFERRED); a row for rough / crumpled cloth |
| 5 | Style | how it is worn: open / closed, tucked, rolled sleeves, collar up... | only open / closed wear inside the build | none | the styling step and its tool (garment_pull, the old route's, is gated off); a gate: the styled garment vs the reference, no thread past its cap |
| 6 | Sim the rest | soft cloth hung under gravity (ZOZO), stiff parts held | `chain_garment` HANG, after the structure PASS | lengths after the hang; threads past the cap measured but not in the answer | the threads-past-cap reading in the answer and the gate; the hang judged only as folds on an approved structure |

Known from runs 1-3 (kept for when each step comes up):
- Step 3, run 3 (archive/chain-run3, not landed): the band resting on the high points fixed the collar's tilt (9.6 -> 24
  deg); the band is always built closed though the pattern says its button is open: the likely cause of the points held
  together AND the front.R stretch under the collar's end.
- Step 6: open wear hung with 1 in 5 faces past the thread cap.

ORDER (agreed before any agent run): tooling for 0, 1, 2 and 5 (the missing steps), then the steps one at a time, each
iterated on the shirt until good, then the jacket through the same steps.

NEXT: Joe agrees this page; then the tooling briefs, one deliverable each.
