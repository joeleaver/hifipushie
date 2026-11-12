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
1. SPEED, the blocker for N3: 24k points ~974 s before N1b; see N1b below.
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

## N1b (branch n1b-speed, run 2, stopped at budget; deliverable NOT met)
- Kept: PD_STIFFEN stages (links/edges x10, x100 after the 400 passes): LM starts at E ~1 (1.5k) / 30 (6k), not 6e3 /
  1.6e5. LM: rejected steps halved along their direction (no refactor), trial steps retracted onto the lengths
  (gn.retract, 6 Jacobi PBD sweeps), stop at LM_DROP 0.1 % gain, a round stops when the projection leaves E within 1 %.
  rep["lm_factors"] counts factors. Tests all pass at their numbers (stiff strip pull max 1.52 mm vs 1.50; width 1.04).
- Bench (machine load 60-140 on 24 cores from other jobs: walls ~3-4x inflated, compare factor counts): 1.5k ~11+4
  factors, 6k 13 factors (was 60+ passes, 2 caps). 24k: see the run log /mnt/data/hifipushie/n1b/b24k_v3.log.
- Dead ends (measured): contact rows in PD's matrix (isotropic rows stick nodes where they touch: LM start E 10-25x
  UP); CG preconditioned by a stale LM factor (26 of 29 passes no convergence in 40); chord steps with the last factor
  (zigzag, step 1 / 1/16, no fewer factors); lower LM link weights (LM stalls); node-level / geometric ND orderings
  (no better than SuperLU MMD: 24k factor 3.4-4.2 s, fill 27M); CHOLMOD via ctypes on the system libcholmod.so.5
  (works, scripts /mnt/data/hifipushie/n1b/chol_ctypes.py, but 16 s a factor under load vs splu 10.6).
- WHY still slow: LM needs ~13 factors at 6k (it crawls: a penalty LM on stiff links), each ~4 s at 24k unloaded.
  Ways out: a constrained step (SQP on the links / projection inside each pass) so LM needs ~3 factors; or a fast
  Cholesky (scikit-sparse needs libsuitesparse-dev headers: Joe's call); measure on an idle machine.

Run: `uv run pytest -q tests/test_chain_solve.py`; bench `uv run python tests/chain_solve_bench.py [scale] [--log]`.

NEXT: N1b run 3 on an idle machine: time 24k with the kept changes, then LM as SQP (soft step in the links' tangent +
projection) to cut factors to ~3; only then N2 (seed from tapes; plies / layers as constraints).
