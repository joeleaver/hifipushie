# STATE: step 5 rewritten (docs/proposals/step5_rewrite.md, approved 2026-11-11)

Step 5 = ONE solve with nothing held: lengths given, only bends chosen. Runs N1 (solver) -> N2 (seed from tapes, plies /
layers as constraints) -> N3 (the build on the jacket, old stages deleted) -> N4 (shirt, hussar) -> T (blind trials).

## Current best (N1 + N1b + N1c solver; N2 seed + plies term, branch of agent N2)
- `chain_solve.py`: `solve(net, X0, body, ties, folds, pulls, stiffness, plies=...)` -> (X, report); PD (200 passes, x10,
  x100) -> LM (CHOLMOD, analysed once, 1 BLAS thread) -> fast projection. NOT wired into GarmentBuild (N3).
- `chain_solve_plies.py` (N2): plies / floating layers / inside pieces as a TERM: p - q(host bary) = d n, n the host's
  RING normal (area-weighted vertex normals of the host triangle's nodes; a triangle's own normal flipped host corners),
  d = k LAYER on the host's inner side. PD target re-read per pass; LM with the normal lagged. Flat map: own uv when in
  the host's frame or sewn along one line (an affine fit on a line collapses the piece), else affine from sewn pairs.
- `chain_seed.py` (N2): `seed(net, body, wear)` -> {X0, pulls, folds, ties, plies, reads}. Refuses untaped pieces;
  edge tapes laid by piece_start.lay_on_tape (interior offset across the edge, side away from its partners); other
  pieces mapped between their loops (radius profiles round the loops' axis) and their highest path (flat height = arc
  down it), walked round the ring by flat x from an origin (centre line front / back, or the path) either way: first
  pick = lies nearest its own paths, then sweeps adding seam distance. Followers bound + seeded on hosts. Folds: plan
  turn split over the draft's rows, way = draft sign x uv winding x the piece's out sign. Ties: apply_tie pairs.
- Proof driver: `spikes/n2_seed_jacket.py <out> <loaded.pkl>`, renders `spikes/n2_render.py`. Scratch ws
  /mnt/data/hifipushie/n2/ws (copy of p2-proof), loaded.pkl in /mnt/data/hifipushie/n2/mine (load_garment is 50 s).

## Numbers
- tests/test_chain_plies.py 3 pass (facing on a panel turned 170 deg: 0 crossed, < 1 mm; two-layer collar on a neck:
  0 crossed, max < LAYER, mean < 1 mm, nothing inside); tests/test_chain_solve.py 9 pass.
- JACKET (run1, /mnt/data/hifipushie/n2/run1, report.json): seed 14 s, seed seams 56-99 mm per piece (fronts 99,
  undercollar 88). Solve 160 s (pd 35, lm 75, project 46) at load 46 -> 63. Links worst 1021 % (collar), 1915 of 3031
  over 2 %; edges worst 606 %; folds median off 3-77 deg (lapels 51-77, collar 8-10, hems 3-45); 0 ties (plan: none
  fastened); 328 inside (deepest 38 mm, sleeve_top.R); pulls mean 18-43 mm; plies crossed 44-264, max 27-53 mm.
- Render X_all_sheet.png / X_neck_sheet.png beside the reference: FAILS. Fronts stop at the chest (no wrap to the
  side), sleeves torn off the armholes (gap at the upper arm), collar stands straight up the neck (no fall), lapels
  crumpled in place (no clean turn), hem uneven. Not better than P2 on any of its three faults.

## Open faults (ranked)
1. The seed's seams are 6-10 cm open: the solve's sewn nodes start at their mean, tearing every piece. A seed must
   have seams CLOSED by construction (lay pieces seam-first from the edge tapes / neighbours), not pick among 6 guesses.
2. Ring mapping: flat x is not arc from the centre line on every piece (the side, the sleeves' origin); shoulders above
   the top loop are an extrapolated cylinder (no shoulder slope); sleeves start without their cap on the armhole.
3. One solve can't recover a 1000 % seed (LM stalls at 2.4e6 E). PD needs more passes or a seed within ~30 %.
4. Fold way sign is a hypothesis (lapel +, hem - came out opposite, as intended); unverified on the render.

## Decisions in force
- No held / fixed / pinned set, no role names, no wear state in chain_solve* or chain_seed (tests 8, 9 enforce for
  chain_solve). Pulls soft; hard terms win. One factor route (CHOLMOD). Followers are a term, never copies.

## Dead ends
- PD with stiff springs; LM alone from flat; contact rows in PD; stale-factor CG; chord steps (N1b, C426). A ply term
  on the triangle's own normal (flips corners); full normal derivative in LM (no help). Seam-only origin choice (C431).

Run: `uv run pytest -q tests/test_chain_solve.py tests/test_chain_plies.py`. Ledger C426, C429, C431.

NEXT: N2b: a seed with seams closed by construction (pieces laid outward from the edge-taped neckline and along their
sewn neighbours, lengths kept), shoulders on the body surface; prove links < 30 % at seed, then the one solve.
