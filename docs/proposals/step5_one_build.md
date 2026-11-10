# Step 5, one build: ties, folds and what holds what (proposal, 2026-11-10, for Joe's approval)

## Why
Joe (2026-11-10): "I'm very concerned about 'open' and 'closed' states being their own thing in the code. I'm worried
that means our process is overspecific, also, why should it matter?"

It shouldn't matter. The worn state is only which closure pairs are tied and how far each fold is turned. The code
instead picks a different pipeline for each case it has met. That is why both approved drafts are refused at step 5.

## What the code does now
- `GarmentBuild.run` (chain_garment.py:1441) picks one of four hand-built pipelines: draped, stand collar, "open with a
  band", or closed. Anything else is refused ("open wear needs a band and a front closure").
- `planned_wear` (chain_plan.py:60-90) turns step 2's closure states into a wear mode through `BAND_WEAR`. It refuses
  every combination nobody built: a wholly open front, a front fastened partly under a closed band, any other closure
  left open.
- Roles pick stages: the first "roll" fold makes its piece a collar FALL, and a FALL needs a BAND under it
  (chain_roles.py:135-145).
  - The jacket's lapel roll is a roll fold on the front, so the front is read as a collar fall.
  - The hussar's collar canvas reads as a fall with no roll, and is refused.
- The open pipeline (`build_open`) is fifteen calls in a hand-tuned order: the fall built twice, the soft cloth solved
  three times, extra holds added after one fault. Each was a patch for a fault seen on the shirt.
- The soft start has three alternatives behind flags (torso rings, the SDF block-in, flat-then-sew).
- chain_garment.py is 1879 lines.
- Step 2's bends are prose ("lapel turned back along the roll line from the gorge to the break..."). No build can act
  on them. Only the collar spread is a number.

## What the pattern already says (the jacket's approved step 4, declarations.json)
- `closures`: `front_closure` buttons, front.L over front.R, pairs `[hole1, btn1]`, `[hole2, btn2]`.
- `folds`: `lapel_roll` on front, line lapelBreakPoint -> shoulderRoll, a roll; two pressed sleeve hems.
- `stiff`: canvas, collar, undercollar. `seams`: every seam, with its two edges.

That is everything a build needs, and none of it is shirt-specific. Only the builder is.

## Proposal: one build, three generic inputs, no modes
1. **TIES** (closures). Step 2 lists, for each closure in the draft, the pairs that are fastened.
   - `front_closure: []` is open, all pairs is closed, `[btn2]` is partly. No "open", "closed" or "partly" words in the
     code.
   - A tie holds two pattern points together: a layer apart where the closure laps, at the zip gap where it meets edge
     to edge. The chain net already keeps closures out of the sewn nodes ("closures are wear, not seams"), so a tie is
     one more constraint in the same projection.
2. **FOLDS** (bends). Every fold the draft declares (roll, press, turn-back) is a crease along its own line on its
   piece.
   - Step 2 gives each fold its turn as numbers: the angle, how far along its line the turn runs (to the break point,
     a pattern point), and what the turned part lies on.
   - A shirt collar's roll, a lapel's roll, a turned-back cuff and a rolled sleeve are then one thing. Prose bends
     become a row on the photo to check against, never the bend itself.
3. **WHAT HOLDS WHAT** (the order). Pieces are built in the order they are held, read from the pattern's construction,
   never from role names:
   - Stiff pieces first. Each rests on what is under it, the body or a piece already built (chain_rest's rule, for
     every stiff piece).
   - Then soft pieces, sewn to what is built, ties made.
   - Every edge that is neither sewn nor tied is a FREE EDGE. It starts hanging from its held neighbours down onto
     what is under it (chain_drape's free-cloth rule, for every garment). An open jacket front, a shirt hem, collar
     points and a cloak hem are all free edges.
   - Folds then turn to their planned angles, lengths exact throughout.

   ONE soft start, chosen by measuring the three candidates on the test garments. The other two are deleted.

What goes: wear and state in the code, `BAND_WEAR`, `planned_wear`'s refusals, `build_open`, `band_open`,
`fasten_from`, `build_stand`, the separate drape pipeline, role-dispatched stages. Roles stay only as what the
STRUCTURE rows measure (a collar's clearance, a front's straightness), never as what picks a pipeline.

Refusals that stay are the pattern's own faults, each with its step to go back to:
- a tie whose points can't meet within their cut lengths (step 4);
- a fold whose line isn't on its piece (step 4);
- a free chain more than 2 % off its cut (step 5's start);
- a seam that won't close (step 4).

## How step 2 changes
- `state.<closure>` becomes `ties.<closure>: [pair names]`.
- `bends` become numbers on the draft's folds (`turn_deg`, `to: <pattern point>`, `lies_on`), each with its reference
  trace as the row that checks it.
- Approved plans migrate mechanically for ties (open -> [], closed -> all, fastened_from k -> from k). Bends written as
  prose can't migrate: the jacket's and the hussar's step 2 are rerun (blind), approved again, and carried forward.

## Proof (the gate for the redesign)
- The same build, with no branch on a garment, a state or a role, makes:
  - the shirt (closed band and fall; open collar);
  - the hussar (stand collar, closed, edge to edge);
  - the suit jacket (notch collar, lapels rolled to the break, open front).
- A test fails if `run` branches on wear, state or role.
- The shirt must read no worse than today on the length gate and its structure rows (its old result kept as the control).
  Until it does, the old path stays on a branch, never as a fallback in the tool.
- Then blind trials s5-2 (jacket) and the hussar's step 5, judged beside the reference as before.

## Runs (one deliverable each, about 90 min; tests per slice, one suite at the end)
| # | Run | Size |
|---|---|---|
| R1 | Ties: step 2 `ties`, the migration, ties in the projection; `planned_wear`'s state logic deleted | S |
| R2 | Folds as numbers: step 2 `turn_deg` / `to` / `lies_on` on draft folds, validated against the draft's fold lines; one crease turn for every fold kind | M |
| R3 | One build order from what holds what; the free-edge rule for every garment; the four pipelines deleted; chain_garment.py split to about 500-line files | L |
| R4 | One soft start, measured on the three garments; the other two deleted | M |
| R5 | Shirt control comparison; then s5-2 jacket, hussar step 5 (blind) | trials |

## Open questions for Joe
1. Rerun step 2 for both garments (needed for numeric bends): fine to revoke their step-2 approvals when R2 lands?
2. Is the free-edge rule enough for an open front before the sim, or should step 5 hold the open fronts where the
   plan's row puts them (the photo's fronts 111 / 123 / 177 px apart) and leave the rest to the hang?
3. R3 is large. Split it into smaller blind-tested slices, or one tooling run with the shirt control as its gate?
