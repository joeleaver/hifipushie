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
## T13 (2026-11-02, C297, C301; chain_drape.py, tests/test_chain_drape.py): draped garments (cloak, cape, hood)
step 1 `hang: draped` + `held: [edges]` (a hood held by its seam), step 2 `drape {piece: {falls}}`. BUILD (build_drape): the
held line a rigid ring of its cut at the neck, points at exact chords, clasp shut; a held line sewn to itself refused; free
cloth on clear paths from the held line; soft_net (body as floor). GATE SPLIT: hang kinds (hem height / spread, front/back,
hood opening / depth) judged after the hang (hang_check); build rules start_clear, held_exact, clasp; hang rule hood_on_head.
T13b proof (HOME /mnt/data/hifipushie/t13b/ws; sheets t13b/sheet_build_{all,hood}.png): NOT HUNG. The build spreads over
the arms like a poncho to the hip, crumpled; the hood shrink-wraps the skull. Build 1400-1700 s in soft_net (splu, 107k
constraints), not the path search. NEXT: (a) drape_start_clear reads after soft_net (4.5 mm floor) against a 6 mm limit:
read the free cloth's start BEFORE soft_net (the limit stays); (b) start shape: paths near-vertical below the shoulders,
the hem's fullness folded, the hood started at its depth; (c) soft_net speed; then hang, rows, render.
## T15 (2026-11-02, C299; structure_outline.py): OUTLINE vs REFERENCE rows `outline:<id>` from step 2's traces (kinds hem,
front_edge, collar_top, collar_front, neckline, sleeve_end, outline) + body_marks (the body is the ruler); FAIL backs to step
4 with the pattern edge. Detail + proof numbers: git history of this page (commit 1308bfa2) and the module docstring.
UNVERIFIED there: side / back views; traces through a tube's silhouette. r-nico: the hang runs on the configured route (C302).
## F1 (C307-C309; chain_loops.py): own drafts build or are refused by name; centre rings; the stand's top = border less
end edges, upright by its own height; held links counted. Detail: git history (9ba6032a).
## F3 (C310-C311; draft_pairs.py, chain_roles._end_edges): pairs declared at step 4 (`pair: true`), stand end edges in its
solve; hussar stand STILL REFUSED 39.8 % at collar:rightTopIn (stretched after the stand stage). Detail: git history (c036b645).
## F4 (2026-11-02, C312-C313; tape_geom.py, piece_start.py, tests/test_piece_start.py; HOME /mnt/data/hifipushie/f4)
- TAPE: step 3 rows keep WHERE: a girth its `loop`, a length its `path` (metres, 0.1 mm, <= 64 pts). tailor keeps the leg
  loops (upperLeg, knee, calf, ankle, heel); `waistTo*` / inseam / height / shoulderTo* get paths (tape_geom).
- STEP 4: output.piece_measurements {piece: names} = step 1's seam body names on its edges + its draft part's own list.
- START (piece_start): TUBE = soft pieces of one side closed round by their own seams (self-sewn, or 2 separate seams)
  whose girth loops lie on their side and a length path of theirs runs along them -> MeasuredAxis through the loops'
  centres, run on to its paths' ends. PANEL: top at the top of the length path spanning it (+-20 %), else hung from the
  hps. Neither: the old start, "FALLBACK: ..." in reads.starts and the answer ("start <piece>: ..."). Nothing names a limb.
- PROOF (t8 trousers, f4/ws; redraft scripts/design_f4.mjs: front / back take waistTo*, inseam, upperLeg, knee, ankle;
  pairs from f3): step 3 PASS with loops / paths, draft PASS (10 seams 0 off). Build (job_trousers_1.log, 517 s): starts
  "tube round its own measurements: loops ankle, knee, upperLeg, along inseam, waistToFloor..." per side, waistband at its
  seam's height z 1070 (closed 853 / loop 820 mm). REFUSED: front.L near cfSeat 90 % off its cut; chains worst 3738 %
  (back.L / waistband edge), front.R 2087 %. Sheet f4/sheet_trousers.png: two legs, the waist at the band, the model's
  LEFT leg round its leg; the RIGHT thigh bare (front.R not round it), cloth crumpled. NOT a pass.
- SLEEVE (t8 shirt redrafted as is, scripts/sleeve_check.py): sleeve.L "tube round its own measurements: loops biceps,
  wrist, along shoulderToWrist", 40 mm mean from the old joint-axis start; fronts / back panels (first rule had grouped
  front.L + sleeve.L via the armhole's biceps: fixed, C313). Hussar (f4/hussar) names step-1 names step 3 never took
  (armscye_girth...), its design no measurements: FALLBACK, start unchanged (0 mm). F3's job_trousers_4: failed (its worktree removed), no result.
NEXT: (a) the .R tube's start: dump soft_start X per piece for f4/ws trousers (scripts/start_check.py: x ranges are
mirror-symmetric at the start, so the fault is later: _mirror / sewn roots averaging the crotch seam's two legs, or the
.R phase sign in tube_group_points); fix, rebuild, re-render. (b) the two tubes overlap +-45 mm above the crotch: start
the part above the crotch on the half of the torso loop (seat / waist) the piece names. (c) F3 (b), (c) still open.
