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

## Default shirt vs pattern_check (chain-first)
- A fresh design_garment {kind shirt, from simon} on wf_simon's body (model cf_shirt, workspace of the main checkout) FAILED
  flat_pattern on two defaults: fit slim taken for a regular draft (chest +14.7 %, waist +23.1 %), S12 stand 436.8 vs 441.2.
  Fixed in the draft (garment_kb simon default_fit regular; cloth_designs simon "match" of stand + collar after truing): flat
  read now seams all ok (stand 437.9 vs 441.2 before the walk moved after truing; re-read after the move not done) and ease in band.
- The FULL gate on the fixed default ran to the end (3834 s wall at load ~90): FAIL, 8 of 44 rows blocking. seams and
  flat_pattern now PASS. Blocking: FAIL collar_fall_cover (stand cb 27.0, ends 27.9 / 30.8, fall cb 40.2, roll above seam 4.0,
  turn 2.06 mm; the row's target text was cut off in the log, so the failing number is not identified yet) and UNMEASURED collar,
  front_closure, cuff, pockets, layering, fabric, colour (no reference reading given: refs=). Log: /mnt/data/hifipushie/chain_first/gate1.log.

## Not done (this run's deliverable is NOT met)
- chain_garment never ran end to end through the tool: no PASS record yet, so no closed / open job, no look_chain, no renders.
- The job path is tested only with a stub worker; the real worker under the job was not run.

## Known limits (ranked, from the last proof on wf_simon, worker run directly)
1. Open: shoulder cloth rides over the collar leaves; collar stands high; plackets ragged at the throat. Closed milder.
2. Free cloth rises 7-8 mm on average in the hang (not understood). 3. Stiff chains not exact after surfaces (collar fold line
7.7 % closed / 16.3 % open). 4. Cuffs flare (cut 183 mm vs forearm 200 mm). 5. Soft mesh 20 mm, coarse. 6. No export.

STATE: job + default-shirt fixes on branch chain-first (44a641ad, e1dc20f0). NEXT: read collar_fall_cover's target (cloth_check) and fix that default in the draft; decide with Joe whether the 7
reference rows need a refs reading or should not block a default; then, on a PASS, run
chain_garment wear closed then open through the tool on cf_shirt (one hang each), look_chain beside folds_ab/refs; if not, fix
the next failing default row in the draft. Run the gate when the machine is less loaded (load 90 starves the capped slice).
