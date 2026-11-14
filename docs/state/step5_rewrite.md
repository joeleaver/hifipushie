# STATE: step 5 rewritten (docs/proposals/step5_rewrite.md; CHAINS ONLY; N2i: ONE FOLD RULE, MERIT FINAL STEP)

Step 5 lays out the CHAINS (boundary + fold rows + lines across), lengths given, only bends chosen, nothing held.
Step 6 fills surfaces between them. Runs N1 -> N2 -> ... -> N2h -> N2i (this).

## Current code
- `panel_start.starts`: each piece placed from its own tapes; `_ways`: a girth piece rolls the way its seams say.
- `chain_lay.outside(net, X, contact)`: which side of F is each piece's outside (away from the body), read at the START.
  `chain_lay.fold_way(fd, out)`: THE fold-direction rule (N2i, C456): the draft's turn (+ onto the outside, - under) x
  out. The draft's flap sign never enters. Used by `fold_rows` (solve folds), `Panels(cnet, plan, skip, out)` hinges
  (x the flat's winding) and `measures(..., out)` (each fold's measured way vs the plan's way).
- `chain_panels.Panels` + `fit_start`: rolled panels; the driver still starts every hinge unturned (turn 0).
- chain_solve: cloth bending (N2h); lines across AT MOST their flat length for every piece, plus a SOFT cost on a line
  shorter than flat x its ends' interfacing (W_SHORT, chain_solve_gn "short"): EXACT_INTERFACED is gone.
- `chain_solve_final.step`: restore, then a TRUST REGION on one merit (soft energy + NU x |violation|^2, radius by
  actual / predicted drop, up to 50 mm), stop at a relative drop < 1e-4, restore once. Report: `final_converged` (merit
  settled) and `final_hard` (per round: worst link fraction, ties, depth, holds at TOL 1e-4) apart.
- Proof: `spikes/n2i_jacket.py <out> <loaded.pkl>` (was n2h_jacket); render `spikes/n2c_render.py <run> <pkl> <ref>
  X.npy quick`. ws /mnt/data/hifipushie/n2i (loaded.pkl in /mnt/data/hifipushie/n2/mine).

## Numbers (jacket, n2i/run1; load 142 -> 47; X_quick_sheet.png, crops crop_n2i.png vs crop_n2h.png)
- Sewn links max 0.078 % (0 over 2 %). Per side 260 over 2 %, max 20 % (seam truing / cap ease, as N2h).
- Smoothness: median 3.25 deg, p99 60, zigzags 73 (N2h 54).
- Folds, all 7 turned OUTWARD as the draft asks (angle 0 = onto the outside): collar fall 183 / 180, lapels 168 and
  168 / 170, sleeve hems 177-182 / 180. N2h: lapel R and one hem per sleeve turned inward.
- The V: roll lines run from the break at the centre front (z 1.19 m) to neck ends 77 mm (L) and 68 mm (R) off the
  centre line (N2h 52 / 34): the opening between the turned lapels is ~145 mm at the neck, closing at the break.
- Inside 0. Tapes: front chest 37 mm mean / 67 max (as N2h).
- Final step: passes 200+109 (stage 0), 93+90, 84+84, 84+84 (sewn): only stage 0's first round hit the cap. The hard
  terms did NOT hold to 1e-4 after the last restore (that run reported converged False for every solve; the split
  report was added after it). Wall 505 s (N2h 773; sewn 58 s, N2h 271).
- Beside the reference (quick line drawing, see-through): torso wraps, lapel lines splay from the neck towards a point
  at the break, but it does not yet read as an open jacket; the facing chains still wander across the centre front.
  Collar: still a small ring at the neck base, no fall over the back. Sleeves: thin, caps not round, wrist loops.

## Open faults (ranked)
1. Collar fall: the plan / draft give the roll line ONLY on the collar (collar_roll, 180); the undercollar (sewn to it
   along its outer edges, and the collar's host) has no roll row, so it stays flat-ish and holds the collar to a ring.
   The fall needs the same roll line drafted on the undercollar (step 4) or the undercollar bent by the collar's.
2. Hard terms short of 1e-4 after the final restore (sewn links max 7.8e-4): RESTORE passes run out near contact.
3. Sleeves thin / caps not round; sleeve hems drafted angle 0 (cuffs turned back onto the outside), a jacket's are
   usually 360 (under): step 4's call, check against the reference.
4. Facing chains cross the centre front above the break (merge jump facing ~ front up to 119 mm).
5. Not judged on Blender tubes (the quick drawing only).

Run: `uv run pytest -q tests/test_chain_smooth.py tests/test_chain_solve.py tests/test_chain_panels.py tests/test_chain_lay.py tests/test_chain_plies.py`.
Ledger C426-C433, C435, C438, C440, C444, C446, C448, C456.

NEXT: N2j: the undercollar's roll line (step 4 draft) so the collar falls; the final restore reaching 1e-4; render
Blender tubes and judge the V and collar beside the reference.
