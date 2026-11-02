# STATE: chain garment -> garments built from the pattern's outline (library + tools since 2026-11-01)

Joe: "This is how we should build clothes, right here." "that should be the only path available to the agent for starting
clothing." "We need to get to a point where a blind agent can build a great-lookin piece of clothing without tons of
iterations or manual feedback."

## What exists
- `chain_net.py` (general core) and `chain_garment.py` (roles, stages, ZOZO job, worker, render_views): docstrings are the spec.
- Tools: `chain_garment(name, garment, wear, opening, wait=50, rebuild=False)` is a JOB (chain-first, C275): refusals at once;
  else it starts the worker (bin/capped, build under resources.heavy BUILD_GB 8) and answers its stage within wait (<= 280 s).
  Same-argument calls poll, never start a second worker (key = body + this garment + wear); a finished job answers with its
  numbers; a changed pattern starts anew; rebuild=True starts over; a dead worker reads "failed"; every answer names its next
  call. `look_chain(name, garment, wear, focus, size, reference, save)` unchanged.
- `server.GATED_CLOTH` hides the old routes (HIFIPUSHIE_LEGACY_CLOTH=1 restores). Tests: tests/test_chain_garment.py (stub-worker
  job tests). Dev: /mnt/data/hifipushie/chain_garment/, /mnt/data/hifipushie/chain_first/. Ledger C259-C275.

## Default shirt: gate + first real tool run (chain-run1, 2026-11-02)
- Gate: cf_shirt (wf_simon body, main checkout workspace) PASS_WAIVED, 388 s: every row PASS except cuff WAIVED (the two
  folds_ab/refs collar close-ups don't show a cuff). Refs read with garment_from_reference (choices: shirt_collar, buttons,
  pockets none, layering none, cotton_shirting, colour #dfe7f4; saved workspace/cf_shirt/cloth_refs.json), passed refs=.
- Fixed (C278): collar fall cut for a WORN cover (cloth.collar_options: stand + 10 + 2 x 4 roll + 2 turn; KB collarWidth 1.45
  removed): worn cover 3.1 -> 9.6 mm; flat dim fall_cover now reads the same definition as the gate row; stand 441.2 =
  neckline 441.2 after the walk. garment_from_reference names pattern_check refs= next; "#rrggbb" colour answers read.
  chain_garment's length refusal names the nearest pattern point.
- CLOSED: REFUSED by the tool after the build: front.R's front edge (placketOuterFold, 6-42 mm below placketTopOut / the
  neck) +2.3..2.7 % vs MAX_FREE_PCT 2.0. Not caused by the collar fix: an A/B with the old fall (model cf_old, worker run
  directly) refused at 2.337 % on the same line. Not fixed. Build views: workspace/cf_shirt/chain/shirt_closed/.
- OPEN: built and hung through the tool (5 polls, ~20 min at load 20-66). Chains free worst 0.217 %; threads p99 5.93 %,
  max 56 %, 4774 / 25458 faces past the cap (the answer doesn't flag it); hang moved p50 9.8 mm, drop -7.5 mm.
  Views (beside front_open_collar): /mnt/data/hifipushie/chain_run1/look_open_{neck,whole}_{front,three,side,back}.png.
- Verdict (open, beside the reference): reads as a regular shirt at full figure; the neck is poor. 1. the collar stands as
  a crumpled funnel round the neck: the points don't fall onto the collarbones (ref: flat leaves, points ~1.7 neck widths
  apart); 2. the plackets are ragged and torn-looking at the throat, the V narrow; 3. threads past the cap (stretch) in
  1 in 5 faces; 4. front.L's placket hangs apart at the hem; 5. coarse soft mesh, cuffs flare (known).

## Known limits (ranked, before this run)
1. Open: shoulder cloth rides over the collar leaves; collar stands high; plackets ragged at the throat. Closed milder.
2. Free cloth rises 7-8 mm on average in the hang (not understood). 3. Stiff chains not exact after surfaces. 4. Cuffs
flare (cut 183 mm vs forearm 200 mm). 5. Soft mesh 20 mm, coarse. 6. No export.

STATE: branch chain-run1 (6cbf64f6..). NEXT: find why the closed build stretches front.R's front edge below the neck (the
French front's fold line vs the band end / button 1 when closed; same on the old collar), fix it in the draft or the
build (never MAX_FREE_PCT), rerun chain_garment wear closed through the tool, look_chain beside folds_ab/refs; then the
open collar funnel and the threads past cap.
