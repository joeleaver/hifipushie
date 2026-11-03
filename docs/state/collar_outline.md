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
## F8 (C324-C326; chain_bend.py, HOME f8): rigid then bend; trousers SEW FAIL (inseam hem 95, CF 29 mm); waistband lap fixed (BV 29). Detail: git history (60ca2d12).
## F9 (2026-11-03, C327-C330; garment_blockin.py, blockin_map.py, HOME /mnt/data/hifipushie/f9, scripts f9/scripts)
- Step 2 `blockin` (data): ease knots, cones, cut planes, seam planes (+ within), region seeds -> body SDF offset, meshed
  (6 mm, taubin), cut exactly along each seam plane: regions + seam lines. Outline vs the reference: T15 on its silhouette.
  Body marks may now be u-only ([u, null]). Trousers block-in: f9/scripts/plan_blockin.json; look f9/blockin_look.png.
- Step 4 `blockin_map.check`: region flattened (LSCM), piece mapped by its seam ends (arc length) + harmonic inside;
  rows map:<seam> (pattern vs line, max(25 mm, 5 %)) + area:<piece> (area, median stretch along / across).
- Step 5 `blockin_map.start`: hooked in soft_start, OPT-IN HIFIPUSHIE_BLOCKIN_START=1 (job sets build.blockin from the plan). NOT RUN on a build.
- Trousers: outline leg_R / leg_L FAIL p95 46 / 40 mm (hem: the concept's legs ~20 % shorter than garrett's; fork).
  Map: side +62, inseam +113, CF -71, CB +28 mm; waist front PASS, back UNMEASURED (bug: back waist line missing).
  Reconciled (f9/scripts/crotch_rec.py): body x=0 from waist_z = 617 mm; the block-in's fork sits 61 mm under the body's
  crotch (the leg cones + smooth union fill the thigh notch): its 737 mm is the block-in's fault. Design ~640: the
  pattern's 695 is ~55 mm long (mostly CB), not 130-200.
- Tests: tests/test_blockin.py (4: cylinder regions + seam lines, matching piece ~0 distortion, too-long piece by seam,
  start seams closed); test_garment_plan + test_structure_outline pass. No build, no render, no draft fix.
## F10 (2026-11-03, C331-C334; HOME /mnt/data/hifipushie/f10, scripts f10/scripts: redraft.py, style.py, tape.py, build.py)
- Block-in: fork ceiling (mirrored shapes kept FORK_GAP off x=0 below crotch_z); back-waist line = data (side seam plane
  ran above the waist). Seam planes from the classic trouser block's balance (y -0.025), source in the data. Plan step 2 has it.
- Map F9 -> fixed block-in -> redraft: side +62 -> +62 -> -1; inseam +113 -> +73 -> +9; CF -71 -> -42 -> -19; CB +28 ->
  +48 -> 0; waist back UNMEASURED -> +13 -> +20; areas -3/+7 -> P. PASS. Draft (f10/scripts/design_f10.mjs): hem 65 up,
  crotch ext front seat/11 back seat/10, back rise 15, waist +7 mm/quarter, band lap marks [btn, btn2.m].
- Start default when the plan has a blockin; job key includes it; ring sits on the block-in's seam line (BV unchanged:
  only plans with a blockin change, and their key has it).
- Build: START PASS (length INFO 32 % worst link at front.R hemIn: the map's distortion, median ~1.00); CHAINS: length
  0.002 PASS, wrapped 15-23 mm PASS, held_length 19.3 % FAIL at front.L:cfWaist (the lapped band holds the two CF waist
  ends a layer apart; the crotch seam is sewn to the waist). Surfaces / end gates not reached: no calibration.
- Look f10/f10_vs_concept.png: legs straight to the shoe top as the concept; hips render patchy at 6-9 mm stand-off.
NEXT: (a) the fly: crotch seam stops under the waist (draft edge crotch>cfFly + free fly edge; the block-in needs a
`dz` on plane heights - not supported - and a non-sewn region cut at the fly), or the over's CF not lifted; (b) build
through SURFACES to the end gates, then calibrate inside / holes / sewn; (c) start_length 32 % at the hem corner.
