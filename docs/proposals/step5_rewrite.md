# Step 5, rewritten: lay out the chains where they were measured (proposal 2026-11-11; cut to chains only 2026-11-12)

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

## What step 5 is (the spec; cut to CHAINS ONLY with Joe, 2026-11-12)
Joe (2026-11-12): "I feel like we're doing too much in this one step. I thought all this step was supposed to do was lay
out the chains." N1-N2 had widened step 5 into a whole-cloth solve (24k surface points, interiors mapped onto the body,
contact over every point, plies as surfaces); that is step 6's job and was the cause of both the speed problem and N2's
torn start. Step 5 lays out the CHAINS; step 6 fills the surfaces between them (chain_net's Laplace fill).

Input: the approved flat pattern (pieces, seams, stiff pieces, folds, closures), step 2's plan (ties, fold turns, what each
fold lies on), step 3's tapes and step 4's tapes per piece and per edge, the body.
The network: CHAINS ONLY. Every piece's boundary edge and every fold / roll line is a chain of links at their cut;
sewn edges share one chain; a few LINES across each piece (rulings between its chains: exact on stiff pieces, at most
their flat length on soft) keep the chains apart. No interior points. A jacket is a few hundred to ~2k points.
Output: every chain point in 3D such that:
1. every link is at its cut length (hard; nothing is ever held against it);
2. every seam is closed (one shared chain) and every planned tie made;
3. every fold line turned as planned, lying on what the plan says;
4. no chain point inside the body (or inside the garment it lies on);
5. each chain lies where the body was measured for it (its tapes pull, never pin);
6. stiff pieces keep their flat shape (their lines exact, high bending), soft pieces bend freely.
A follower (facing, undercollar, lining) is chains too: its edges sewn to the host's share the host's chain; its free
edges stay on the host's inner side.

When those can't all hold, the build names which and where, and which step it goes back to: a seam whose two sides can't
meet (step 4: the pattern), a tape a chain can't lie on (step 3 or 4), a tie that can't close (step 4). Never a held
length.

## The build (one algorithm, no roles, no wear states; ASSEMBLE THEN DRESS, N2c 2026-11-12)
Joe (2026-11-12): "in real life, the pieces would get assembled _before_ they get put on the body"; "Why do seams have to
gradually close using a solver at all?" They don't: every seam is one shared chain from the start; only bends are chosen.
1. **Assemble** (chain_lay.lay, no body: a thin frame, the body shrunk to its skeleton, for which way round). The piece
   with an edge on a tape first (that edge laid along its tape by its own arc), then always the piece sewn to most placed
   nodes: its sewn nodes stay put (one chain); the rest of its flat goes off them along and across the placed line, across
   CONTINUING the surface already sewn there (a follower lies back on it), then bent as rigidly as possible (ARAP). Its
   planned folds and roll lines are turned as it is sewn (pressed while the garment is made).
2. **Close loops with bends**: one projection over the nodes, links exact, lines across exact (interfaced) or at most,
   out of the frame. A loop still open, or a seam whose two sides are cut to different lengths, is NAMED with its gap
   (back to step 4), never stretched.
3. **Dress** (chain_settle.settle): the body grows inside the assembled garment (each vertex from its skeleton point out
   to its place, in stages); at each stage chain_solve, links hard, seams one chain, contact, bending, folds, the taped
   edge's and the girth tapes' pulls, followers as a term. Seams never reopen: there is nothing to reopen.
4. **Report** links off cut at every stage, loops closed or named, folds off, points inside, tapes mm.
5. (Step 6, not here) surfaces filled between the solved chains.

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
| N1 | The solver (done: no held set, CHOLMOD) | done |
| N2 | Plies as a term; a whole-surface seed (done; the seed FAILED: the step was too big, see the spec) | done |
| N2b | The chain network (boundary + fold chains + lines across, no interior); chains laid on their tapes and walked from their seams; one solve; the jacket's chains rendered alone beside the reference | M |
| N2c | Assemble then dress: seams one chain from the start, loops closed by bends, the body grown inside | M |
| N3 | Step 6 fills surfaces between the solved chains; the new build wired into GarmentBuild; the old stages and the whole-surface seed deleted | L |
| N4 | Shirt and hussar: steps 3 and 4 redone with tapes, built by the same code | M |
| T | Blind step-5 trials, the jacket first | trials |
