# STATE: step 5 rewritten (docs/proposals/step5_rewrite.md; CHAINS ONLY; N2f: COLLAR START, EXACT TURNS)

Step 5 lays out the CHAINS (boundary + fold rows + lines across), lengths given, only bends chosen, nothing held.
Step 6 fills surfaces between them. Runs N1 -> N2 -> N2b -> N2c -> N2d (rolled panels) -> N2e (live start) -> N2f (this).

## The 98 mm (N2f item 1): (a) a step-5 bug
- The 642 mm "neck edge" was the collar's outline read on a BROKEN loop: the chain network's faces aren't a clean disk
  and the pattern collar's outline is pinched at a tip (one vertex of degree 4); a greedy walk lost the neck points.
- Fixed: the edge is now 452.5 mm (cbN > hps 88 + hps > cc > notch 139, x 2) on the 544 mm neckline: it fits. The tape is right.

## Current code
- `chain_net.Network.loop`: an Euler circuit of the boundary edges (a pinch walked whole, that vertex twice; test).
  `chain_lay_net.chain_network` keeps each piece's PATTERN outline (`cnet.outlines`); cnet.loop returns it.
- `panel_start._edge`: edge points ordered along the outline; arc length along it from the centre-line crossing
  nearer the edge (a centre piece) or the end nearer x = 0 (a sided piece), never across a gap between declared arcs.
  A centre piece's halves go to the side of the already-started pieces they are sewn to (edge-taped pieces start
  last); winding only if sewn to nothing started (the winding rule crossed every collar seam).
- `chain_panels.Panels.resolve(TH)`: a hinge RULES its turned panel: rigid motion = base's frame at the row's middle
  turned by the plan's angle; only the roll (phi, kappa, g) stays free (`free_cols`, `ancestors`). A fold whose plan
  `lies_on` another piece is not ruled (its turn stays a W_TURN residual). `fit_start` and `Fit.solve` return
  resolved numbers; the Jacobian's sparsity follows the ruling chain. `hinge_read` uses central differences.
- Proof: `spikes/n2e_jacket.py <out> <loaded.pkl> [start] [iters]`; render `spikes/n2c_render.py <run> <pkl> <ref>
  X.npy quick`. ws /mnt/data/hifipushie/n2f (loaded.pkl in /mnt/data/hifipushie/n2/mine).

## Numbers (jacket, /mnt/data/hifipushie/n2f/run1; 28 panels; 80 evals x 2 starts, ~6.5 min each)
- Start alone (n2f/s0/X_start_quick_sheet.png): collar + undercollar ring the neck, ends down to the notch, no knot;
  start panel fit rms 15 mm (N2e 53). Start seams collar-to-torso still 93-121 mm (torso rolled at chest radius).
- Assemble: cost 0.460 / 0.511 (spin 0 kept). Hinges: all 14 at plan exactly (lapels 85 / 85, hems 90 / 90, collar
  fall 90 / 90). Gaps mean 25-30 mm (max 40-62: collar ~ undercollar 62, back ~ sleeve 58, front ~ undercollar 50);
  hinge rows meet only at their middle: sleeve-hem rows 24 mean / 45 max mm apart. Inside 686 points.
- Dress: cost 0.558; inside 278; gaps front ~ undercollar 33 / 65 mm.
- Tapes after close: fronts 180-350 mm off (chest / waist / hips), facings 190-400, sides 70-215. FAIL.
- Close: moved median 19.5 / p95 51 / max 90 mm (target p95 < 10); links median 1.9 %, p99 46 %, max 71 % (target 2 %).
- Judged beside the reference (run1/X_quick_sheet.png): FAIL. The collar is a flat band ringing the neck base, with no
  visible roll or fall. The fronts stand open and flared, not lying to the side seams. In side view the body leans
  ~30 deg forward like a cape. Sleeves are splayed panels, not tubes on the arms. The hem flares.

## Open faults (ranked)
1. The assembly loses the start: the tapes pull at W_TAPE 0.3 and the fronts end 200-350 mm off theirs. The torso
   tilts forward round the collar. Raise the tapes or hold the start's centres harder, and recheck from the good start.
2. Hinge rows meet only at their middle (each panel rolls its own way): tie the turned panel's curvature to its
   base's along the row, or read the row's gap as the fold's error.
3. Sleeves: caps not on armholes (gaps 40-58 mm); cones still untested on the jacket.
4. Speed: FD Jacobian (~4.5 s an eval); analytic per panel not done.
5. The torso's neck points start at chest radius (start seams to the collar ~100 mm).

Run: `uv run pytest -q tests/test_chain_panels.py tests/test_chain_lay.py tests/test_chain_solve.py tests/test_chain_plies.py`.
Ledger C426-C433, C435, C438, C440, C444.

NEXT: N2g: keep the start through assembly (tape weight / start pull from the fixed start, one start), then tie hinge
rows' curvature; judge X_asm beside the reference before dressing.
