# STATE: step 5 rewritten (docs/proposals/step5_rewrite.md, approved 2026-11-11)

Step 5 = ONE solve with nothing held: lengths given, only bends chosen. Runs N1 (solver) -> N2 (seed from tapes, plies /
layers as constraints) -> N3 (the build on the jacket, old stages deleted) -> N4 (shirt, hussar) -> T (blind trials).

## Current best (N1 + N1b + N1c, branch n1c-speed)
- `chain_solve.py` (spec in its docstring): `solve(net, X0, body, ties, folds, pulls, stiffness)` -> (X, report). NOT
  wired into GarmentBuild (N3). `chain_solve_terms.py` (terms, report), `chain_solve_gn.py` (the LM pass, `Factor`).
- Method: projective dynamics (W_LINK 0.03; 200 passes, then PD_STIFFEN x10, x100 at 100 each) -> Levenberg-Marquardt on
  the whole energy (rejected steps halved + retracted, stop at LM_DROP 0.1 %) -> fast projection over every point.
- Factors: CHOLMOD (scikit-sparse 0.5.1 on the system libsuitesparse), METIS, supernodal, ONE BLAS/OpenMP thread
  (threadpoolctl), analysed once per solve and refactored per pass. The Jacobian keeps inactive at-most rows as zeros,
  so the LM pattern is fixed (Factor.values raises if it ever changes). No splu left in chain_solve*.
- _Near.REACH 1 mm (was 1 cm): only which points are asked again; same result to the bit.

## Numbers (machine shared: load 40-70 on 24 cores from another session's full test run)
- tests/test_chain_solve.py: 9 pass (~10-20 s) at their numbers: stiff strip pull max 1.52 mm / mean 0.27, width
  1.04 mm; fold 0.001 deg off, halves 8.8 deg; tube 0 inside; ties 0.0 mm; pulls 102.9 mm reported, links 0.0 %.
- Per factor (fresh LM matrix, /mnt/data/hifipushie/n1c/fac6k*.log, fac24k.log): 6k splu 1.0-2.7 s vs CHOLMOD 0.13-0.44
  (1 thread; 4 threads 1-10 s); 24k splu 18.5-31.8 s vs CHOLMOD metis 0.64-1.83 (amd 1.9-3.0, nesdis 1.0-2.9), analysis
  2.1 s once. LM pass at 24k (lm_parts.py): factor+solve 1.23, residuals+J 0.45, values 0.19, JtJ 0.13, trial 0.27.
- Bench 6k: 19.5-28 s (N1b 63.5). 24k (b24k_v3.log): 69.4 s at load 68->55, pd 34.5, lm 30.1 (12 factors), project
  0.3, links 0.0 %, 0 inside (N1b: 601 s at load 135, lm 516). Slow test 24k: 61.7 s at load ~40 (limit 150).

## Open faults (ranked)
1. 24k is ~1 min only under load ~40-60; PD (400 passes, ~85 ms each: push-out queries, targets, solve) is half.
2. stiffness 40 (5x canvas) converges badly (pulls 14 mm). Realistic max is 8.
3. Curved fold rows: row_rows pulls a row towards straight (weak). 4. No self-contact (N2: plies / layers).

## Coarse step-5 mesh: NOT done (not small); the plan for N3
- Spacing is set in cloth.build (cloth.py ~7529-7553: h = g["resolution"] 0.01 default, coarse 0.02, mesh(Bp, hs, fw)),
  reached through chain_garment.load (~line 301, place_only) with pattern_form.form_refine (FORM_REFINE_LAPEL / SHIRT:
  h 2-6 mm near collar, fronts) and RING_H re-meshing of stiff rings (chain_garment.py ~306).
- Step 6 reads the SAME mesh: Build.X per vertex; SURFACES = chain_net.fill (Laplace fill over the pattern F from the
  chain vertices) in chain_soft.py ~462 / chain_fall.py ~190; gate chain_stages.gate_surfaces. No fine mesh exists.
- Plan (N3, which replaces cloth.build(place_only) with cloth.pieces() + mesh() anyway): mesh twice from one pieces()
  (step 5 at ~2 cm with fold rows and rolls still refined; step 6 at the resolution); map each fine vertex to its coarse
  triangle in the same piece by uv (barycentric), X_fine = interpolated; seams agree when both sides are sampled by arc
  fraction (check cloth.mesh's shared seam arcs); then chain_net.project on the fine links, then fill / threads.
  Test: a tube solved coarse, filled fine: links exact, seams closed, nothing inside.

## Decisions in force
- No held / fixed / pinned set, no role names, no wear state in chain_solve* (tests 8, 9 enforce).
- Pulls are soft; hard terms win and the soft residual is reported. One factor route (CHOLMOD), no fallback.

## Dead ends
- PD with stiff springs; LM alone from flat; pushing points out after each LM step; contact rows in PD's matrix; CG
  preconditioned by a stale factor; chord steps; lower LM link weights; node-level ND orderings (N1b, C426).
- CHOLMOD with OpenBLAS's default 4 threads on a loaded box (threads spin: 1-10 s a factor at 6k). PD 100 first passes
  (LM +5 factors, dearer than the passes saved).

Run: `uv run pytest -q tests/test_chain_solve.py`; bench `uv run python tests/chain_solve_bench.py [scale] [--log]`;
logs and scripts /mnt/data/hifipushie/n1c/ (fac_bench, pd_bench, pd_sweep, lm_parts, reach). Ledger C426, C429.

NEXT: N2 (seed from tapes; plies / layers as constraints). If 24k must be faster: PD's push-out query (candidate
triangles cached per point) and LM as SQP (step in the links' tangent + projection: ~3 factors); coarse mesh in N3.
