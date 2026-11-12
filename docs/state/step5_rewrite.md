# STATE: step 5 rewritten (docs/proposals/step5_rewrite.md; CHAINS ONLY; N2e: ROLLED PANELS, LIVE START, CONES)

Step 5 lays out the CHAINS (boundary + fold rows + lines across), lengths given, only bends chosen, nothing held.
Step 6 fills surfaces between them. Runs N1 -> N2 -> N2b -> N2c -> N2d (rolled panels) -> N2e (this).

## Current code
- `chain_seams.join_seams`: a sparse seam one chain end to end; N2e: a seam whose one side runs along several pieces
  (an armhole against front + side + back) is matched through the sewn junction (`_b_paths`, test). The jacket's seams
  are already dense (every armhole / neckline point sewn): only 2 runs, 24 points added; nothing was open there.
- `panel_start.starts(cnet, keep, body, skip, spin)` (N2e, new): every chain point's start from its piece's OWN tapes,
  live (no saved X0): girth-taped pieces rolled round the line through their loops (radius by height + GAP, grain up,
  top at the top of their length paths, centred at their paths' angle; paths on the line give no angle: the piece faces
  -Y and pieces sharing those loops spread round the line, `spin` turns them); edge-taped pieces (collar, undercollar)
  laid on their tape from the centre line, the rest of the flat standing up from its nearest edge point; no tape:
  refused. Returns the edge points' pulls to their tape.
- `chain_panels.Panels`: 9 numbers a panel: rigid motion, roll axis angle, curvature, TAPER g (a cone; g -> 0 the
  cylinder; apex clipped off the panel; starts at g = 1e-3 so the finite differences see it). Hinge way = draft sign x
  winding x the row's handedness (mirrored pieces' mirrored rows turn the same way: test).
- `chain_assemble`: keep = skeleton segments OR the body's contact (thin body: no point deeper than THIN 20 mm);
  `assemble(..., pulls)`: girth + edge tapes as residuals; dress / close as N2d.
- `chain_lay._fold_turns`: a fold's turn is the SUM of its rows' face medians (it read a 2-row fold at half).
- Proof `spikes/n2e_jacket.py <out> <loaded.pkl> [start] [iters]` (2 starts: spin 0 / pi), render
  `spikes/n2c_render.py <run> <pkl> <ref> X_asm.npy quick` (skips nan points), folds `spikes/n2e_folds.py <run> <pkl>`.
  ws /mnt/data/hifipushie/n2e/ws.

## Numbers (jacket run2, /mnt/data/hifipushie/n2e/run2; 28 panels, 252 unknowns, load ~80-110)
- Start (s0/X_start_quick_sheet.png): torso round the body at the right heights, fronts at the front, sleeves down the
  arms: RIGHT. Collar / undercollar: a tangle at the neck (panel fit rms 53 mm over the whole start; collar edge 642 mm
  on a 544 mm neckline tape from the centre). That tangle is the run's undoing.
- Assemble (80 evals x 2 starts, 239 / 351 s): costs 0.380 / 0.518 (spread 36 %, spin 0 kept). FAIL: the torso is
  pulled into a tent up to the collar knot (X_asm_quick_sheet.png), gaps 30-64 mm (back ~ front 64, armholes 40-58,
  necklines 48-54), tapes 100-390 mm off, 1485 points under the skin (within THIN).
- Hinges (assembled): lapels 3-40 of 85, sleeve hems 50-58 of 90, undersleeve 41-94, collar fall 0 of 90: W_TURN 0.05
  loses to everything else. Hinge read = angle between the panels' normals (within 2 deg): the hinge axis / normal are
  right; the old 17-48 deg face read was a 2-row fold's per-row median against the whole turn (fixed, test).
- Dress: gaps up to 61 mm, 425 inside. Close: moved median 22 / p95 53 / max 87 mm; links p99 31 %, max 49 %. FAIL.
- Not passed: no item of the step-5 numbers. Better than N2d: the live start (torso, sleeves); worse: the collar.

## Open faults (ranked)
1. Edge-laid start: the collar's neck edge laid on the neckline tape tangles (check the edge's ordering along the
   outline, its centre point and which half goes to +X; the collar edge is longer than the tape's half).
2. Turn weight: hinges reach 0-60 % of plan; raise W_TURN or make the turn exact (the turned panel's rotation from
   the base's numbers + one angle: fewer unknowns, no turn residual).
3. Tapes 100-400 mm off after assembly: tape weight 0.3 vs seams 1.0 on a bad collar; recheck once 1 is fixed.
4. Speed: FD Jacobian still (~3 s an eval at load 100); analytic per panel not done.
5. Cones untested on the jacket's caps (gaps there unchanged); the synthetic cap closes (test).

Run: `uv run pytest -q tests/test_chain_panels.py tests/test_chain_lay.py tests/test_chain_solve.py tests/test_chain_plies.py`.
Ledger C426-C433, C435, C438, C440.

NEXT: N2f: fix the edge-laid collar start (render the start alone until the collar rings the neck), make each hinge's
turn exact by construction, then rerun run2's two starts and judge X_asm beside the reference.
