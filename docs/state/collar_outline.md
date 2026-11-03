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
- Rows: from the record's step 2 (structure_rows.py, T6 C286); run 2's INFERRED shirt rows superseded (git history).
## T7 (C287; chain_plan.py): built straight into the plan's state; its shirt proof refused (placket fold at the hem): git history 80eb32ef.
## T8 (2026-11-02, C289; chain_roles.py): roles from any pattern (fall, band, stand, rings, tubes of one or more
pieces, panels, lapped / zip fronts). Hussar proof (HOME /mnt/data/hifipushie/t8): STRUCTURE FAIL at the stand's
CF (dives to a V), sheet t8/sheet_b2.png; its rows and NEXT: git history of this page (commit 8c603bda).
## T9 + T12 + T12b (C292, C294, C296): layering (chain_layers, chain_press, chain_hidden); proof t12b/ws STILL REFUSED. Detail: git history (merge of t12b-hidden).
## T13 (C297, C301; chain_drape.py): draped garments (cloak, cape, hood), gate split build / hang. Proof t13b/ws NOT HUNG
(poncho-like crumpled build, soft_net 1400-1700 s). Its NEXT (start before soft_net, start shape, speed): git history (739936ca).
## T15 (2026-11-02, C299; structure_outline.py): OUTLINE vs REFERENCE rows `outline:<id>` from step 2's traces (kinds hem,
front_edge, collar_top, collar_front, neckline, sleeve_end, outline) + body_marks (the body is the ruler); FAIL backs to step
4 with the pattern edge. Detail + proof numbers: git history of this page (commit 1308bfa2) and the module docstring.
UNVERIFIED there: side / back views; traces through a tube's silhouette. r-nico: the hang runs on the configured route (C302).
## F1 (C307-C309; chain_loops.py): own drafts build or are refused by name; centre rings; the stand's top = border less
end edges, upright by its own height; held links counted. Detail: git history (9ba6032a).
## F3 (C310-C311; draft_pairs.py, chain_roles._end_edges): pairs declared at step 4 (`pair: true`), stand end edges in its
solve; hussar stand STILL REFUSED 39.8 % at collar:rightTopIn (stretched after the stand stage). Detail: git history (c036b645).
## F4 (C312-C313; tape_geom.py, piece_start.py): tapes keep where they ran; pieces start round their own loops / between
their tapes (FALLBACK named). Proof f4/ws trousers REFUSED (front.R never round its leg). Detail: git history (b5a64c64).
## F5 (C314-C316; chain_stages.py): START / CHAINS / SURFACES gated, stop at the first FAIL. Detail: git history (f5903839).
## F6 (C317-C320; HOME f6): flat gate rows seam_ends + body_lengths; per-stage length reads; the START stretched (trousers
1063 %), the pattern goes round (crotch 1032 vs seat 960 + 60). Detail: git history (73a264bf).
## F7 (2026-11-03, C321-C323; chain_sew.py, HOME /mnt/data/hifipushie/f7, scripts f7/scripts, logs f7/*.log)
- FLAT THEN SEW is the soft start (GarmentBuild.soft_start -> chain_sew.flat_then_sew; b.sew_start=False = the old lay).
  The old lay is only a GUIDE (region from piece_measurements). ARRANGE: each piece flat on ONE cylinder (a tube group
  shares its measured axis; a panel upright through the body); which way round + facing chosen so its seams meet
  the cloth already placed (stiff parts, earlier pieces), never on top of a piece of its tube; radius = the least
  keeping <= 5 % of points within STANDOFF of the body; .R = the .L's mirror. SEW: each round every sewn pair may come at
  most PULL (8 mm) nearer, then the lengths alone (chains exact, mesh edges <= flat) to convergence; the lengths win over
  the body floor. Stops when every pair is within 0.3 mm (groups snapped to their mean) or the summed gap stalls.
- Gates: new stages ARRANGE (arrange_length: stretch vs MAX_FREE_PCT) and SEW (sew_length; sew:<seam> gap vs SEW_TOL
  2 mm, back to step 4, named with the points + measurement list). START's start_length is a VERDICT now.
- Trousers (f7/ws): ARRANGE 0.02 % (R 165 mm), gaps 97-327 mm. SEW: lengths held all the way (worst +0.07 %), but
  STALLED at round 66 / 17 min: inseam hem 93 mm, CF 53, side waist 38/28, CB 27, band 5-23 mm. START on it:
  start_length 48.9 % (open gaps), round FAIL at the ankles. f7/sew_r2.log. The pattern goes round (F6), so the
  STALL is probably the sew, not the pattern (the row says so: UNPROVEN). Hussar ARRANGE (f7/hussar copy): 0.0 %;
  front R 482 / back 330 mm (far out), collar~front gap 383 mm; not sewn.
- Not done: no trousers build past SEW, no render, no hussar build, provisional rows NOT calibrated (no passing build).
  Tests: test_chain_sew (arrange reads 0; sewn seam closes with lengths held; a seam that can't close refused by name);
  test_chain_stages's guide-lay tests set sew_start False. Targeted tests 54 pass.
NEXT: (a) make the sew close: the quasi-static pull stalls where pieces must slide round the body / cone in at the
ankle (try: pull each pair toward its midpoint with the PIECE rigidly first (a rigid step per piece per round), then
bend; or a cone lay for a tube whose rows narrow (a flat onto a cone is exact too); and speed (17 min: fewer lengths
iters, lines_across instead of every mesh edge)). Prove first on f7/scripts/arrange_probe.py ... sew (stall vs close),
then build.py through the gates + render beside concept_v8_front_apose.png; then the hussar (panels laid far out:
check the radius rule for panels); (b) calibrate inside / holes / sewn on the first build to pass; (c) crotch tape (F6 d).
