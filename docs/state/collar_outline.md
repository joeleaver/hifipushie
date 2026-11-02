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
- Rows: from the record's step 2 (structure_rows.py, T6 C286); run 2's INFERRED shirt rows and its cf_shirt tables
  are superseded (git history; T6's rows on run 2's builds: /mnt/data/hifipushie/t6/structure_t6.json).

## T7 (2026-11-02): built straight into the plan's state (C287; chain_plan.py)
The tool takes wear from the record's step 2 (cf_shirt: front closed, band open, spread 1.7 nw); an open band is built open
(button_start -> band_open -> fall -> soft). Fixed this run: the first fastened button is HELD through the soft cloth (it drifted
10 mm down / 14 mm out, the fronts' neck-to-button ran 12.6 mm past cut); a placket strip is everything its crease folds + BL
(a fixed-height strip tore the front edge +59 % under a steep crease). BUILD_VERSION 24. Test: test_open_build_holds_the_first_button.
Proof build (HOME /mnt/data/hifipushie/t7/ws, job cf_shirt/chain/shirt_open) STILL REFUSED: free worst 58.9 -> 49.1 %, now the
fronts' placket FOLD LINE at the hem (uv y -0.75..-0.79, 20 mm from cfHem, both fronts; built/cut 747/713 mm). Front edge
58.9 -> 37.8 / 33.0 -> 15.7 %; fall 6.0 -> 2.7 %; collar_edges 45 -> 22 % (the 2nd roll fold row at the points: 1.6 mm links,
<0.5 mm, held, not gated). Hem cause NOT found: made in the FIRST soft_net of the open flow (closed flow on the same pattern:
1.2-2.1 %); the hem point stops at z 780 whatever its start (756 or 770), not held, not tied, not sewn, not under the fall, 30 mm
off the body. Hanging the panels from the built band (soft_start dz) made it worse (65 %): reverted. Next suspect: net.lines()
across the hem, or a node of the held band/button dragging a line. Dev: /mnt/data/hifipushie/t7/stages5.py <open|closed>
(first soft solve, ~3.5 min, prints the hem fold + what pins it), look_hem.py, render.py, sheet_fix1_{neck,whole}.png.
Rows (T6 open on run 2 -> T7): collar_points_apart PASS 1.56 -> FAIL 1.535 (target 1.55-1.85, plan's), collar_tilt 22.5 FAIL ->
33.3 PASS, collar_leaves_lie 27.1 -> 28.9 FAIL, placket_straight 25.6 -> 30.8 FAIL, closure_front part -> part FAIL, front_meets
0.802 -> 0.863 FAIL, hem_level_lr 15.1 FAIL -> 3.1 PASS, soft_cloth_smooth 3.8 -> 4.32 FAIL, v_depth 0.30 PASS -> 0.494 FAIL,
closure_band open PASS. By eye: the points spread like the reference, but the fronts fold out as ragged lapels to a deep V,
the leaves stand off the shoulders, a tail hangs at the CF hem.

STATE: branch t7-state, targeted tests pass (test_chain_garment/structure/garment_record/toolsets); bin/suite not run (one at the
end of the tooling list). NEXT: find what holds the open fronts' hem in the first soft_net (stages5.py open vs closed; then
rebuild with start.py 0 rebuild, HIFIPUSHIE_ASSETS=/home/joe/dev/hifipushie/workspace/_templates); then the V (first button
held at its cut distance reads 0.49 nw vs 0.26-0.38: check the plan's button vs button_start) and the leaves lying.
