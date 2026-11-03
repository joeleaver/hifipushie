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
## F7 (C321-C323; chain_sew.py, HOME f7): flat then sew (ARRANGE exact 0.02 %, SEW stalled 17 min). Opt-in: HIFIPUSHIE_SEW_START=1 / build.sew_start.
## F8 (2026-11-03, C324-C326; chain_bend.py, HOME /mnt/data/hifipushie/f8, scripts f8/scripts, logs f8/*.log)
- chain_sew.sew = chain_bend.rigid (each soft piece a solid: 6 numbers, least squares, body a soft barrier; exact) ->
  chain_bend.bend (Verlet + colour-batched Gauss-Seidel lengths + ramped pull + body push; stops closed / stalled <1 %
  over 150 passes; worst_pct read every pass, the pull halves past HOLD_PCT) -> ONE exact chain_net.project (closed
  pairs joined in it). gate_sew reads rigid + bend.
- Trousers (f8/sewrun.log): laid gaps 97-327 mm -> RIGID 47-107 (rms 196 -> 49, 9 s, 0.02 %) -> BEND stalled 1251
  passes / 185 s at 5-29 mm (worst transient 5 %) -> project exact (0.02 %) but reopens: inseam hem 95-97, CF 29,
  CB 18, side 11-12, band 5-9 mm. SEW FAIL; the sew start STAYS OPT-IN. A free pull (no hold, f8/fast_c.log) closes
  all but CF (32 mm) with 34 % transient stretch.
- Findings: (1) waistband built 13 % past its cut at its lap (body_ring's radial lap): FIXED (C325, BUILD_VERSION 29).
  (2) PATTERN FAULT: crotch CF 299 + CB 396 = 695 mm vs the body ~480-563 + ~15 stand-off: 130-200 mm TOO LONG (low,
  baggy crotch; f8/scripts/crotch.py). (3) Topology: each leg's crotch extension laid through the inner thigh (4.5 % of
  cloth inside, 48 mm deep): the CF can't close. Not fixed: the next run starts from an SDF block-in, already sewn.
- Not done: no trousers build past SEW, no render, no hussar, provisional rows NOT calibrated (no passing build).
  Tests: test_chain_bend (4: colours, rigid closes with zero stretch, bend closes a tube within HOLD_PCT, stall stops),
  test_chain_loops lap test; targeted chain tests pass.
NEXT: (a) the SDF block-in start (pieces already sewn round the body) removes the through-the-thigh lay; run chain_bend
on it. (b) the inseam hem reopens 24 -> 95 mm in the projection: read the ankle round row against the hem width
(pattern?) before the solver. (c) add crossSeam / crossSeamFront to body_tape (a length path between the legs) and a
body_lengths row: the crotch is 130-200 mm long. (d) calibrate inside / holes / sewn on the first build to pass.
