# Step 5, rewritten: lay the pattern where it was measured, solve every length (proposal, 2026-11-11)

## Why
Joe (2026-11-11): "Dunno why we're getting anything 2569% over its chain length though, that means we're trying to do
something we shouldn't be trying to do ... We keep tripping over old code, old assumptions."

A survey of the step-5 code (every stage `GarmentBuild.run` reaches) found:
- **Lengths are never solved where they matter.** Each stage places its piece by a RULE and then HOLDS it. The projection
  skips every link with both ends held (chain_net.py:382,388), so a link between two rule-placed points is only read out
  afterwards: 2569 %, 13415 %. In a step whose whole idea is "lengths given, only bends chosen", that can't be allowed.
- **Positions come from rules, not measurements.** Necks are ellipses from landmarks, tilted to clear the throat;
  bands swung 55 degrees; panels hung from the hps on a torso hull; tubes round joint axes; rings slid along a limb in
  5 mm steps; a fall started 35 degrees down then replaced by a half-circle rule; plackets on a grid search pivoting at
  CF. Most are shirt fixes (T7, F1-F10) with their constants. Step 4's `edge_tapes` was not read until P2.
- **Roles still pick stages.** band / fall / stand / ring / placket / tube / panel decide which rule runs. The pattern
  already says the same through its seams, stiff pieces, folds, closures and now tapes.
- **Three soft starts and a drape pipeline** still exist (rings + hull, the SDF block-in, flat-then-sew; chain_drape).
- **`cloth.build(place_only=True)`** runs the old sim's ~1,090-line `place()`, settle, rest shape, collider and
  hanger, twice when rings exist; step 5 reads only the flat mesh, the pieces and the body from it.

Of ~8,000 lines, about 2,400 do the job (the link network and its projection, ties, folds, plies and layers, tapes);
~2,100 are role and shirt stages, ~1,400 alternative starts, ~450 the drape branch.

## What step 5 is (the spec)
Input: the approved flat pattern (pieces, seams, stiff pieces, folds, closures), step 2's plan (which pairs are tied,
how far each fold turns, what it lies on), step 3's tapes and step 4's tapes per piece and per edge, the body.
Output: every point of every piece in 3D such that:
1. **every link is at its cut length** (the hard constraint; nothing is ever held against it);
2. every seam is closed and every planned tie made;
3. every fold is turned as planned and lies on what the plan says;
4. nothing is inside the body;
5. each piece lies where the body was measured for it (its tapes are where it is pulled towards, never pins);
6. stiff pieces keep their flat shape (high bending stiffness), soft pieces may bend freely.

When those can't all hold, the build says which and where, and which step it goes back to: a length that can't reach
(step 4: the pattern), a tape the piece can't lie on (step 3 or 4), a tie that can't close (step 4). Never a held
length.

## The build (one algorithm, no roles, no wear states)
1. **Seed from tapes.** Each edge step 4 names on a tape is laid along it by arc length; each piece's interior is
   mapped onto the body surface between its taped edges and lines (its tapes' girth loops and length paths). A piece
   with no tape is refused (P2's rule).
2. **Merge.** Sewn points become one node; tied pairs become one constraint each.
3. **Solve once, everything free.** One projection over all links (hard, at their cut), seams, ties, body contact
   (inequality), bending (stiff pieces high), fold turns (each fold line's dihedral towards its planned angle), with
   the tapes as soft pulls. No held set. Plies and floating layers follow their host as constraints in the same solve,
   not as copied positions.
4. **Report** the residual per link, tie and fold, named by piece, edge and step.

## What stays, what goes
- Stays (reworked where needed): chain_net's Network and projection (without the held mask), closure_ties,
  fold_bends, chain_holds' reading of plies / layers / inside (as constraints), piece_start's tapes (seed only),
  chain_crease's fold-line geometry, draft_tapes, the stage gates (start / chains / surfaces) on the new stages.
- From cloth.py: `pieces()` and `mesh()` only; `place()` and the rest leave the step-5 path.
- Goes: chain_band, chain_fall, chain_stiff, chain_loops, chain_rest, stand_ring, the role reading that picks
  stages (read_roles beyond what the gates measure), TorsoRings, LimbAxis and the panel fallbacks, the plackets stage,
  the blockin / sew starts for step 5, chain_drape (draped pieces are free edges under the same solve), held masks.

## Proof (the gate for the rewrite)
- The same build, with no branch on a garment, role or worn state, makes the suit jacket (open, notch collar, lapels
  rolled to the break), the hussar (closed, stand collar, edge to edge) and the shirt (closed band and fall), each
  drafted with tapes (P3's redo of their steps 3 and 4).
- Every link within 2 % of its cut after the solve on all three; any that isn't is named as the pattern's or a tape's.
- A test fails if the build holds any point, or branches on a role name or a wear state.
- Then blind trials of step 5 on each, judged beside the reference.

## Runs (one deliverable each)
| # | Run | Size |
|---|---|---|
| N1 | The solver: one projection with no held set (links hard, contact, bending, ties, folds, tape pulls); unit tests on synthetic strips, tubes, a stiff collar on a soft neckline | M |
| N2 | Seed from tapes (edges on tapes, interiors mapped between) and plies / layers as constraints; the jacket's start | M |
| N3 | The new build end to end on the jacket (scratch copy with tapes), gates on its stages; then the old stages deleted (`chain_band`, `chain_fall`, ..., `place()` from the step-5 path) | L |
| N4 | Shirt and hussar: steps 3 and 4 redone with tapes (P3), built by the same code, read against their old results | M |
| T | Blind step-5 trials, the jacket first | trials |
