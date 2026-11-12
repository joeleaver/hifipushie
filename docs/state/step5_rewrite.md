# STATE: step 5 rewritten (docs/proposals/step5_rewrite.md, approved 2026-11-11)

Step 5 = ONE solve with nothing held: lengths given, only bends chosen. Runs N1 (solver) -> N2 (seed from tapes, plies /
layers as constraints) -> N3 (the build on the jacket, old stages deleted) -> N4 (shirt, hussar) -> T (blind trials).

## Current best (N1, branch n1-solver)
- `src/hifipushie/chain_solve.py` (spec in its docstring): `solve(net, X0, body, ties, folds, pulls, stiffness)`
  -> (X, report). NOT wired into GarmentBuild (N3). `chain_solve_terms.py` (terms off the Network, the report),
  `chain_solve_gn.py` (the LM pass).
- Method: quasi-static projective dynamics (constant matrix, factored once; LOW spring weights, W_LINK 0.03, because
  PD springs lock rotations) -> Levenberg-Marquardt on the whole energy (rotations linearised every pass; exact
  dihedral gradient for folds; contact a residual) -> fast projection over every point (links exact, edges exact /
  at most, ties, contact). Deterministic; no held set exists (a test parses the module for one).
- Bending: per-vertex affine stencils from the flat (X_i - sum w_j X_j: zero for any rigid placement, linear); fold-row
  vertices bend only across the row (row_rows keeps the line itself from kinking).
- Report: links (% off the cut, worst piece, over 2 %), edges, ties (mm), folds (deg off), pulls (mm), contact
  (inside, under gap, deepest), hard_ok.

## Numbers (tests/test_chain_solve.py, 9 tests, ~11 s)
- strip 30 % stretched -> links 0.0 %; compressed 50 % -> 0.0 %, order kept, no face over.
- stiff strip (stiffness 8) on a neckline arc -> links 0.0003 %, pull max 1.5 mm / mean 0.26, width lines straight
  (median 0, free corners curl ~1.1 mm).
- tube of two pieces round a cylinder -> links 0.0003 %, 0 inside; fold to 170 -> 0.001 deg off, halves 8.8 deg apart
  (10 planned); tie at LAYER -> 0.0 mm; pulls 2x the strip apart -> links 0.0 %, pulls reported 108 mm.

## Open faults (ranked)
1. SPEED, the blocker for N3: a 6k-point tube round a cylinder solves right (links 0.0 %, 0 inside) in 152 s (PD 400
   passes + LM 21 passes ~120 s); 24k points did not finish in ~25 min (killed). The LM pass refactors a 3n x 3n system
   per pass (and per rejected step); the contact query (~40 us a point) dominates PD on a body-hugging garment (_Near
   caches it by the 1-Lipschitz bound). Next: LM by preconditioned CG (or LM on nodes x 3 with a block solve), fewer
   LM passes (stop on the hard residual), profile the 24k case first.
2. stiffness 40 (5x canvas) converges badly (pulls 14 mm): PD stops early, LM crawls. Realistic max is 8.
3. Curved fold rows: row_rows pulls a row towards straight (weak); fine for straight rows only.
4. No self-contact (two plies may cross); N2 adds plies / layers as constraints.

## Decisions in force
- No held / fixed / pinned set, no role names, no wear state in chain_solve* (tests 8, 9 enforce).
- Pulls are soft; hard terms win and the soft residual is reported (test 7).

## Dead ends
- PD with stiff springs (W_LINK 1e3): 27 mm off pulls, folds curl. LM alone from flat: crawls (stiff links vs big
  rotation). Pushing points out of the body after each LM step: undoes lengths (E 0.3 -> 7e4).
- splu without SymmetricMode on the LM matrix: 2.7 s a factor at 1.5k points.

## Commands
`uv run pytest -q tests/test_chain_solve.py`

NEXT: make the solve fast at 24k points (open fault 1; profile first), then N2 (seed from tapes: edges on their tapes by arc length, interiors mapped between; plies / layers as constraints
in chain_solve), then time chain_solve on the jacket's real ~24k-point seed.
