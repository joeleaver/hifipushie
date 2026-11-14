# STATE: step 5 rewritten (docs/proposals/step5_rewrite.md; CHAINS ONLY; N2j: LINES ACROSS ARE REAL CHAINS)

Step 5 lays out the CHAINS (boundary + fold rows + lines across), lengths given, only bends chosen, nothing held.
Step 6 fills surfaces between them. Runs N1 -> N2 -> ... -> N2i -> N2j (this; stopped at the call budget, jacket unproven).

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

## Jacket (n2j/run1, INCOMPLETE: killed at the budget after stage 2 of 3 + sewn)
- Points 5,920 (4,588 nodes; N2i 4,326 / 2,994). Setup 62 s. Load ~80-98.
- Unsewn stages are WORSE than N2i: stage 2 links over 2 % 300 of 7,755, max 36 % (N2i 0, max 0.02 %); seams still
  98 mm apart at the sleeve caps (N2i 38-40 mm). Pieces can no longer squash, and that is how N2i's seams met: the
  continuation now asks the hard terms for what they can't give; the final step leaves links off. Not diagnosed: which
  kind of link is off (script /tmp/.../scratchpad/n2j/lk.py not run) and the sewn solve's numbers.
- N2i's baseline measured (scratchpad meas.py on n2i/run1): face edges > 15 % short 5-45 % per piece; outline wave
  (50 mm window, minus the flat outline's) 0.9-1.0 % back, 2.7-2.9 % fronts, 4.4-6 % sleeves, 7.3-8.2 % collars;
  sleeve_top.L fold row wave 22 %.

## Open faults (ranked)
1. The jacket with exact lines: seams don't close in the unsewn stages (sleeve caps 98 mm) and links stay off.
   Read which links (kind, piece) are off at X_stage2; try the sewn solve straight from the start, or a looser SPACING
   on caps; the cap ease may simply need the sleeve to bulge (a cone panel at the start).
2. Collar fall (undercollar has no roll row: step 4), sleeves thin, facing crossing CF (from N2i, unchanged).

Run: `uv run pytest -q tests/test_chain_lines.py tests/test_chain_solve.py tests/test_chain_lay.py tests/test_chain_panels.py`.
Ledger C426-C433, C435, C438, C440, C444, C446, C448, C457, C462.

NEXT: N2j-b: finish the jacket proof with exact lines: diagnose why the unsewn stages leave links 36 % off (lk.py on
n2j/run1/X_stage2.npy), get the sewn solve to TOL, then measure squash + wave (meas.py) vs N2i and render.
