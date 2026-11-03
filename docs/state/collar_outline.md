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
## F5 (2026-11-03, C314-C316; chain_stages.py, tests/test_chain_stages.py; HOME /mnt/data/hifipushie/f5)
Joe: "we're simulating too early ... There's no reason for pants that bad to get simmed." The soft build is gated where each
stage ends (soft_net hooks), cheapest first; a FAIL ends the job `stage_failed: start|chains|surfaces` (rows, back-to step,
change, look = stage.pkl rendered: the start / the chains ALONE / the lay on the body, tapes red); look_chain shows it;
the record marks step 5 (start, chains) or 6 (surfaces) failed. Limits: round = widest gap <= 90 deg round each sided
girth loop; mirror <= GAP (start) / 2x(GAP+LAYER) p50 (chains); sewn (to a built stiff part) p90 <= 1/4 of that edge;
inside share (> GAP deep) <= 0.1; length / held_length MAX_FREE_PCT; wrapped (chains moved p90 <= smallest loop radius);
holes share of faces past (1+SHEAR_LIMIT)^2 area <= 0.01; soft_cloth_smooth (C286) read on the lay.
- TROUSERS (f5/ws): first caught at START (20 s, not 517 s): mirror:front 122 / back 191 mm (the .R tube = the .L's
  mirror turned 180 deg: its front piece at the back; F4's "right front never wrapped") -> FIX .R starts as the .L's
  mirror (chain_stages.mirror_starts). Then sewn: 245-264 mm vs 50 -> FIXES: body_ring's direction checked by its left
  piece's x (it ran the band the wrong way: each leg sewn over the other leg; tubes count as left pieces); a tube sewn to a
  built band turns to face its seam (165 deg for the legs: front.L had started at the back) and eases onto it down to its
  nearest loop (piece_start.turn_to_seams). Now START fails only inside:back.L/.R 0.18 (seat, 35-105 mm deep: F4 NEXT b)
  and in report mode CHAINS held_length 3736 %: front.L's waist seam to the band is REVERSED in the draft (its CF corner
  merged at the band's side, beside back.L's side corner: an 8 mm link 306 mm long) = a STEP 4 fault, untouched.
  Crumple: the LAY already rough (soft_cloth_smooth 2.54 on the lay, holes 5-15 %) with these chains: the solve didn't make it.
  Look: f5/ws/garrett/chain/trousers_closed/stage_start_{front,side,back}_*.png (legs round each leg; the top twisted).
- HUSSAR (f5/hussar, wear open, report mode): start fails sewn:back 29 vs 23 mm (a 92 mm neck edge); chains length 14.3 %
  + held 39.8 % (= its known F3 end refusal, now at the chain stage); surfaces holes 3-8 %, rough 1.8. NOT a clean control.
- UNVERIFIED: holes / sewn / inside limits never seen on a build that passes the end gates (may refuse a good one);
  no hang run; the trousers never reached the end gates.
NEXT: (a) step 4: the trousers' front.L/.R waist seam direction (redraft f4/scripts/design_f4.mjs; a pattern_check row:
a seam's ends meet the seams at its corners); (b) the seat start (inside:back 0.18): the part above the highest loop on
the torso loop's half the piece names; (c) calibrate holes / sewn / inside on a build that passes (the t8 shirt) BEFORE
trusting them; then rebuild trousers to the end gates and judge front + side beside concept_v8_front_apose.png.
