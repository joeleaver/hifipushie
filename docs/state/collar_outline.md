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
## F6 (2026-11-03, C317-C320; HOME /mnt/data/hifipushie/f6, scripts f6/scripts)
- Flat gate rows (step 4, draft_pattern): `seam_ends` (draft_seam_ends.py): a seam's edges run the same way by the
  centre line (cf* / cb* / nape, a fold's x = 0), the side (side* / sd*), a vertical edge's top; FAIL names the swap
  ("a>b" -> "b>a"). Fails t8 trousers' front waist (both sides) and T13b's original hood.R neck (f6/t13b_rev, neck_r
  "cbNeck>neckR" as C301 tells it); passes the hussar, the T13b shirt / hussar / fixed cloak. ALSO FAILS t8's shirt
  (collar_stand:cb>sh vs back:hps>cbNeck; collar_fall:cb>fe vs collar_stand:ft>cbt) and t8's jacket (front:hem>split vs
  side_back:split>anchor, by up / down): unchecked in a build. `body_lengths` (draft_body_lengths.py): girths step 1
  names on seams summed round vs girth + step 0 fit ease (FAIL short); lengths INFO only (step 1 says where a length
  comes FROM). Trousers waist 819 vs 789 PASS; nothing step 1 names measures the crotch curve (waistToUpperLeg is a rise).
- Trousers redrafted (draft_pattern, front:waist "sideWaist>cfWaist"): seam_ends PASS. START rows PASS but inside:back
  0.104 (prov.); CHAINS held 3736 -> 420 %, length 183 %, wrapped .R 35.3 vs 34.6 mm. f6/stages_r1..r3.log.
- Per-stage lengths (chain_stages.length_reads, every stage; START `start_length:chains` PROVISIONAL): the START
  stretches, later stages don't add it: start worst 1063 %, back edges p90 42 % (max 1883); chains 183 % / p90 44 %;
  surfaces the same. The plain tube lay alone (f6/scripts/start_probe.py) reads 1699 %, back p90 34 %: rows wrapped round
  the loops' axis at each flat row's width are not the flat. turn_to_seams adds 8-19 points of p90.
- The pattern goes round the body (f6/scripts/girth_probe.py, flat widths at depth below the side waist): crotch level
  both legs 1032 mm vs seat 960 + 60; upperLeg one leg 647 vs 538 + 70. So the seat stretch is the START, not the draft.
- Not done: no isometric lay; no build reached the end gates (no render, no judge); inside / holes / sewn / start_length
  NOT calibrated (no passing build).
NEXT: (a) the START laid from the flat, isometric by construction. Geometry found: a straight crease across a piece is
exact only where it is a geodesic of BOTH patches it joins (a circle square to a cylinder's axis is; on a cone it is
not), so leg cylinder + torso cylinder of different axes / radii can't share a horizontal crease exactly. Options: each
piece on ONE cylinder / cone (exact; seams then gap: read the gaps at START = the start seam check) and let CHAINS bend
them shut, or a crease along a ruling. Measure start_length ~0 first; then (b) START seam gaps (refuse a gap the
pattern can't close, by seam + measurement); (c) calibrate the provisional rows on the first build that passes;
(d) step 3: a crotch-length tape (front waist through the crotch to back waist) so body_lengths can check the curve.
