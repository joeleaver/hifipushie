# STATE: chain garment -> garments built from the pattern's outline (library + tools since 2026-11-01)

Joe: "This is how we should build clothes, right here." "that should be the only path available to the agent for starting
clothing." "We need to get to a point where a blind agent can build a great-lookin piece of clothing without tons of
iterations or manual feedback." 2026-11-02: "We need a pre-sim judge of the structure." (C279: judge the build, not the hang)

## What exists
- `chain_net.py` (general core), `chain_garment.py` (roles, stages, job worker, render_views), `chain_structure.py` (the
  pre-sim STRUCTURE gate): docstrings are the spec. THE ORDER now has 7. STRUCTURE before 8. HANG.
- Tools: `chain_garment(name, garment, wear, opening, wait=50, rebuild=False, waive=None)` is a JOB (C275): refusals at once;
  else a bin/capped worker builds (resources.heavy 8 GB), writes built.pkl (now with the body's `at`), runs
  chain_structure.check on the BUILD, then the length gate. A length refusal is answered first (structure rows beside it);
  a structure FAIL ends "structure_failed": the answer lists each failing row (value, target, source, change:) and names
  look_chain + the waive call. The hang runs only on PASS / PASS_WAIVED (waive={row id: why}, part of the job key: it rebuilds).
  `look_chain` shows the BUILD until the structure passed and the hang ended (says "shown: the BUILD (before any hang)").
- Rows (garment_reads.collar_reads / front_reads + chain_structure extras, through checklist_rows stage "build", verdict by
  cloth_check.verdict): collar_wear (only if the reading answers collar_state), collar_under_jaw >= 20 mm, collar_tilt 21-41 deg
  (refs README 31), collar_points_drop 86-128 mm (README 107), collar_points_spread (open: OPEN_SPREAD +-20 %; closed: 0.6-1.1
  neck widths, INFERRED), collar_leaves_lie p90 <= 10 mm, collar_turned; front_meets >= 0.9, front_edge_straight <= 10 mm;
  open: v_depth 0.16-0.48 nw (README), v_straight 0.3-0.7; hem_level_lr <= 10 mm, hem_level_fb -40..0 mm; sleeve_length 0-40 mm
  past the wrist, cuff_ease 20-50 mm. Sources: cloth_refs.json, the folds_ab/refs README numbers, or INFERRED kind defaults
  (named in each row). The reading (cloth_refs.json) answers no structure item for cf_shirt: every target is a kind default.
- Tests: tests/test_chain_garment.py (stub-worker: FAIL stops before the hang, PASS hangs + waiver reaches the check, real rows /
  waiver on stub readings, the answer + look_chain shows the build). Dev: /mnt/data/hifipushie/chain_run2/ (run_check.py,
  body_at.json, structure_cf_shirt.json, renders build_{closed,open}_{whole,neck}_*.png, sheets sheet_*.png).

## cf_shirt builds (existing built.pkl, main checkout; no new build, no hang)
| row | closed | open |
|---|---|---|
| collar_under_jaw (mm) | FAIL 12.9 | PASS 41.3 |
| collar_tilt (deg) | FAIL 9.6 | PASS 22.5 (edge) |
| collar_points_spread (nw) | FAIL 0.34 (42 mm) | PASS 1.56 |
| collar_leaves_lie (p90 mm) | FAIL 14.7 | FAIL 27.1 |
| collar_points_drop / collar_turned | PASS 114.8 / -10.3 | PASS 116.5 / -12.8 |
| front_meets (share) | FAIL 0.825 | FAIL 0.802 |
| front_edge_straight (mm) | FAIL 40.2 | FAIL 40.2 |
| v_depth / v_straight | - | PASS 0.29 / 0.45 |
| hem_level_lr / hem_level_fb (mm) | FAIL 15.1 / FAIL +15.7 (back higher) | same |
| sleeve_length (mm past wrist) | FAIL -8.3 | same |
| cuff_ease (mm) | PASS 41.7 | same |
Judged by eye beside folds_ab/refs (sheets above): closed = the collar a level tube to the jaw, points together, leaves standing
off; open = a leaf stands off as a wing; both: the front edge kinks between buttons, the front hem droops at CF and is
uneven L/R. Every one has a failing row. GAPS (visible, no row): 1. the soft cloth in the build is rough / crumpled (sleeves,
side seams); 2. the open plackets look ragged at the throat; 3. the hem_level_fb and cuff targets are INFERRED conventions
(not read off the reference); 4. waiving rebuilds (no resume from built.pkl). Not run: the worker end to end on a real build.

STATE: branch chain-run2, bin/suite exit 0 (fast tier). NEXT (run 3): fix what the rows flag, starting with the closed front.R
stretch (the length refusal: placketOuterFold 6-42 mm below the neck, +2.3..2.7 % vs 2.0; never MAX_FREE_PCT) and the closed
collar (under_jaw, tilt, spread, leaves: the BAND stage stands the band upright, the FALL keeps the leaves turned in); then
front_meets / front_edge_straight / hem rows; rerun chain_garment wear closed through the tool and read its structure rows
before any hang; add rows for gaps 1-2.
