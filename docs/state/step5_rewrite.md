# STATE: step 5 rewritten (docs/proposals/step5_rewrite.md; CHAINS ONLY; N2d: ROLLED PANELS, BENDS)

Step 5 lays out the CHAINS (boundary + fold rows + lines across), lengths given, only bends chosen, nothing held.
Step 6 fills surfaces between them. Runs N1 (solver) -> N2 (plies) -> N2b (chains only) -> N2c (assemble) -> N2d (this).

## Current code
- `chain_seams.join_seams(M, stiff, bend)`: a sparse seam becomes one chain end to end (each side split at the other's
  arc fractions between consecutive sew pairs, matched points sewn). carry_rows: any per-vertex array onto new points.
- `chain_lay_net.chain_network` (N2b): chains + Delaunay lines over the chain points.
- `chain_panels.Panels(cnet, plan, skip)`: each piece's flat, split at its planned fold rows (a fold's rows turn one way;
  a strip of row points between two rows is its own panel), mapped by roll (cylinder: axis angle, curvature) + rigid
  motion: 8 numbers a panel, isometric by construction. Hinges between panels sharing a row: one angle (plan's turn).
  fit_start(Xs): each panel's numbers fitted to a start.
- `chain_assemble`: Fit (least_squares, FD Jacobian with sparsity) over all panels' numbers: seams (residual = gap),
  hinge rows + turn, ties, stiff roll weight; assemble (+ skeleton keep-out, start pull), dress (+ body one-sided,
  girth pulls), close (ONE chain_net.project), reads (seam gaps per seam, hinge turns, roll radii).
- `chain_lay` now only reads (node_links, measures, fold_rows, tie_pairs); `chain_settle` only skeleton, girth_pulls,
  pull_report. N2c's ARAP placement, growing-body settle, test_chain_assemble and spikes/n2c_jacket deleted.
- Proof: `spikes/n2d_jacket.py <out> <loaded.pkl> <start X0.npy>`, render `spikes/n2c_render.py <run> <pkl> <ref> X.npy
  quick`. ws /mnt/data/hifipushie/n2d/ws; start = N2 run1 X0.npy (the old tapes start, per pattern vertex).

## Numbers (jacket run3, /mnt/data/hifipushie/n2d/run3, load 105-130)
- 28 panels, 224 unknowns; canvas.L/R bound on their host. Seams joined: 2 runs, 24 points added. Start fit rms 23 mm.
- Assemble 216 s (150 evals, not converged): gaps max 44 mm (back/front ~ sleeve_top: caps carry ease), torso side
  seams 6-27 mm, collar ~ undercollar 22, darts (front ~ front) 15. Hinges: lapel 83-95 of 85, hems 72-84 of 90,
  collar fall -156 / +157 of 90 (its two rows turn opposite ways: sign bug).
- Dress 155 s: gaps up to 48 mm, 59 points inside; tapes 60-280 mm off (sleeve .R on biceps 275: the right sleeve is
  not on the right arm).
- Close 72 s: moved median 8 / p95 32 / max 49 mm; links median 0.09 %, p99 10 %, max 22 % (did NOT close: 30 loops).
- Links inside a panel are exact (chord vs arc only); links_pct across a hinge reads the hinge gap (598 % on a 2 mm link).
- Renders run2/X_asm_quick_sheet.png (best: jacket-shaped, hem reached, sleeves down the arms but flat),
  run3/X_asm_quick_sheet.png + X_quick_sheet.png: FAIL, the whole garment drifts left and twists off its start, a
  sleeve hangs inside the torso, collar tilted. run4 (W_START 0.2): see its report.json.

## Open faults (ranked)
1. Global drift / twist in assembly: the skeleton keep-out (35 mm) doesn't hold which way round; the start pull is
   the only anchor. Try: keep-out at the thin body (grown 0.3) not the skeleton; more starts; fewer evals.
2. Collar fall's two hinges turn opposite ways; lapel / hem turns read differently by measures (face normals across
   Delaunay faces spanning panels) than by hinge_read.
3. Sleeve caps vs armholes 40-60 mm: a cylinder can't take a cap's ease; cones (apex in the flat) for caps and darts.
4. FD Jacobian: 32 colour groups x 80 ms; analytic Jacobian would make 5-10 starts affordable.
5. Edge tapes (collar's neck edge on the neckline) not pulled yet; girth pulls only.

Run: `uv run pytest -q tests/test_chain_panels.py tests/test_chain_lay.py tests/test_chain_solve.py tests/test_chain_plies.py`.
Ledger C426-C433, C435, C438.

NEXT: N2d-2: fix the assembly's anchor (thin-body keep-out, several starts) and the collar hinge sign on the jacket,
render the assembled panels alone until the jacket stands the right way round; then cones for caps / darts.
