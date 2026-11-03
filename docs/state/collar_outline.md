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
## T7 (2026-11-02, C287; chain_plan.py): built straight into the plan's state. Its proof (cf_shirt shirt_open, HOME
/mnt/data/hifipushie/t7/ws) is still REFUSED (free 49.1 %: the open fronts' placket fold at the hem); rows and NEXT: git
history of this page (commit 80eb32ef) and cloth.md.
## T8 (2026-11-02, C289; chain_roles.py): roles from any pattern (fall, band, stand, rings, tubes of one or more
pieces, panels, lapped / zip fronts). Hussar proof (HOME /mnt/data/hifipushie/t8): STRUCTURE FAIL at the stand's
CF (dives to a V), sheet t8/sheet_b2.png; its rows and NEXT: git history of this page (commit 8c603bda).
## T9 + T12 + T12b (2026-11-02, C292, C294, C296): layering (chain_layers, chain_press, chain_hidden): the over garment on
the body + the under's thickness; hidden under pieces omitted, kept stiff parts push, the kept cloth pressed inside. Proof
/mnt/data/hifipushie/t12b/ws: STILL REFUSED (jacket inside the kept shirt at 13 points). Detail + NEXT: git history (merge of t12b-hidden).
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
## F3 (2026-11-02, C310-C311; draft_pairs.py, chain_roles._end_edges; HOME /mnt/data/hifipushie/f3/{ws,hussar}, logs f3/job_*.log)
- PAIRS: `pieces.<n>.pair: true` = cut 2 (n.L + n.R, seams per side); step 4 refuses half / sideless pieces with that
  declaration. t8 shirt / trousers as drafted: refused at step 4 by name;
  redeclared (`mirror` -> `pair`, scripts f3/scripts/pairs.py): both DRAFT, flat gates PASS (shirt 9 pieces 16 seams,
  trousers 5 pieces 10 seams). A folded piece's own closure closes edge / mark to its mirror (t8 waistband was 0 mm).
- BUILDS: shirt REFUSED by name (collar_fall: a fall with no roll fold: a real draft fault, t8's agent declared none).
  Trousers: past the waistband; result in f3/job_trousers_4.log (see report). Belt untouched (809 vs 787 + 25: draft fault).
- STAND ENDS: end edges solved at their cut (hussar r2: 45.7 / 47.7 mm = cut; stand rise min 59.9 / CB 80.7 deg, top
  531.6 = cut 531.5). STILL REFUSED 39.8 % at collar:rightTopIn: a link of the TOP edge's steep end run (flat x 235 -> 221,
  y 12 -> 46), exact after the stand stage, stretched LATER (stiff_last / soft_net / a projection). Structure FAIL rows incl.
  collar_upright, outline:collar_top, collar_front_R/L. Render: f3/hussar/sheet_f3_neck.png.
- LEGS / GENERAL START (coordinator, from Joe: no leg list; every piece starts where its own measurements were taken):
  NOT DONE. Found: step 3 keeps numbers only; tailor.measure keeps loops for the upper body, none for legs (_leg_girths
  slices and drops them) and no paths for lengths (inseam, waistToFloor); t8's trouser draft used only waist + seat
  (draft.json "measurements"); its step-1 seams name inseam / waistToFloor / waistToUpperLeg / waist; chain_roles reads
  the leg pieces as torso PANELS (no tube: they close through the crotch).
NEXT: (a) the general start: tailor keeps every girth's loop and every length's path (legs too); step 4 saves each part's
measurement list (pattern_parts config); a tube = pieces closed on themselves along a length path (side + inseam), started
round the loops on that path, panels between the tapes their edges follow; LimbAxis only as the named fallback.
(b) find the later stage that stretches the stand's top end run (dump X after each stage on f3/hussar), hold it there.
(c) shape_cap prints each sleeve twice.
