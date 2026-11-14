# STATE: step 5 rewritten (docs/proposals/step5_rewrite.md; CHAINS ONLY; N2j: LINES ACROSS ARE REAL CHAINS)

Step 5 lays out the CHAINS (boundary + fold rows + lines across), lengths given, only bends chosen, nothing held.
Step 6 fills surfaces between them. Runs N1 -> ... -> N2j -> D1 (diagnosis: the pattern is consistent, contact makes the stretch).

## Current code
- `chain_lines.lines` (N2j, new): per piece a LATTICE along / across the grain every SPACING 30 mm; each lattice line cut
  into the intervals the outline and fold rows leave; interior points = lattice points MARGIN 0.4 x S clear of outline /
  rows; ends snapped to the nearest chain point (SNAP 0.6 S); any link > SPLIT 1.25 S gets its own evenly spaced points
  (a single straight link held a strip end flat). `walk(cnet, kind)` the lines in order; `wave(P, window)` waviness.
- `chain_lay_net.chain_network`: the lines are chains (chain_kind 2 along grain, 3 across), links EXACT (appended after
  the pattern's links); lattice points keep -1, stiff / bend from the nearest pattern vertex. Faces: Delaunay over all
  points, still the bending stencils / ply hosts; face edges stay AT MOST flat (removing them scalloped a pulled edge
  0.7 mm between line ends: cloth doesn't stretch). W_SHORT (N2i's soft shortening term) deleted.
- panel_start.starts maps keep >= 0 only; chain_settle.girth_pulls reads the pattern's chains only (kind < 2);
  chain_assemble.links_pct: max / p99 over pattern chains, lines_max apart (a 30 mm link is a chord of a rolled panel).
- Proof script `spikes/n2j_jacket.py <out> <loaded.pkl> [measure]` (renamed from n2i); render `spikes/n2c_render.py
  <run> <pkl> <ref> X.npy quick [lines]` (lines across drawn only with `lines`). ws /mnt/data/hifipushie/n2j/ws.

## Tests (synthetic, tests/test_chain_lines.py, all pass)
- soft strip round a cylinder: every line across arc = flat (to 1e-4), chord 0.81 of flat (curved), long edges wave 0.
- strip pulled into 80 % of its width: bulges, a single hump 28 mm high, arcs exact (N2i-style lines would narrow).
- stiff strip pulled onto a curve: lines across straight (chord > 0.99 of flat).
- tests/test_chain_*.py + test_codified: 156 passed. The old full-mesh stiff-strip test (W_SHORT's) removed.

## D1 diagnosis (2026-11-14, spikes/d1_where.py; out /mnt/data/hifipushie/d1/out): WHERE the stretch comes from
N2j's sewn network solved straight from N2j's panel start (n2j/run1 cnet.pkl, X_start.npy), terms added one at a time.
| run | links > 2 % of 6,437 | worst | s |
|---|---|---|---|
| solver check: 1 piece / 2 sewn pieces, 5 mm noise | 0 / 0 | 0.01 % | 15 / 23 |
| E1 pattern alone (no body, tapes, fold targets, plies) | 0 | 1.65 % | 661 |
| E1 + fold targets (collar fall -83 / -87 of -90 deg) | 0 | 1.89 % | 630 |
| E4 E1 + plies (canvas on fronts, mean 2.2 mm) | 0 | 0.63 % | 1225 |
| E5 E4 + body contact | 354 (edges 222, across 80, along 52) | 44 % | 650 |
| N2j full (+ tapes, folds, ties; continuation) | 1,224 | 82 % | 1407 |
E2 / E3 not run: E1 has no stretch to remove and the collar group folds clean. Verdict: NOT the pattern, NOT the
declarations, NOT the solver's links: CONTACT makes the stretch (tapes add more). Evidence: L / R unequal on a mirrored
garment (sleeve_top.L 61 vs .R 41, back.R 59 vs .L 39), 243 of 400 stretched-link ends off the body, 13 points still
21 mm inside; the start has 1,749 points up to 51 mm inside the body and the solve pushes each point out on its own.
Pattern's one real contradiction: EASE, 130 of 754 seam links differ > 2 % between their sides (caps 5 %, elbow
locally 29 %, collar to front 18 %), hidden by the merged link at the mean. Sew pairs are in order on every seam.
E6 straight from the start (no continuation) not run: killed at the budget; the N2j row is the full-terms reference.

## Open faults (ranked)
1. Contact: a start outside the body (no point inside) and contact that keeps a piece whole (not per-point push-out);
   then check E5 again. Is the pattern big enough for the body (girths + GAP vs the cut) is unmeasured: do it first.
2. Ease as a declaration: a seam's longer side must give up its extra length somewhere (gathered / shrunk), not hidden.
3. Collar fall, sleeves thin, facing crossing CF (from N2i, unchanged).

Run: `uv run pytest -q tests/test_chain_lines.py tests/test_chain_solve.py tests/test_chain_lay.py tests/test_chain_panels.py`.
Ledger C426-C433, C435, C438, C440, C444, C446, C448, C457, C462, C465.

NEXT: D2: measure the pattern's girths against the body's (+ GAP); then a start with no point inside the body and
rerun E5 (d1_where.py E5): links must stay under 2 % with contact before tapes come back.
