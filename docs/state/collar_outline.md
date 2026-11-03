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
## F1 (2026-11-02, C307-C309; chain_loops.py, tests/test_chain_loops.py): t8's own drafts crashed the build (Simon's
'bottomMid' in cloth.place; self.sb used with no band stage). Now: the neck wrap's edge is the piece's seam
(cloth._neck_edge_ref); band attributes only after their stage; refusals from helper modules reach the job as refusals.
CENTRE RINGS (body_ring): a waistband at its seam's height round the torso at its closed length (marks at CF, tail lapped);
a belt (sewn to nothing) where the torso first takes its length nearest the waist; short ones refused with how much
longer. HALF / SIDELESS PIECES refused by name (sided_faults), all draft faults in one answer.
STAND: its top edge was 20 mm of one ear (loop() stopped at a corner; "farthest from the seam"): now the border less the
end edges, ordered by foot; upright = heights within 30 deg of vertical by their own height. HELD LINKS counted (stiff
own links exact, gathered never longer); gate_lengths refuses them past MAX_FREE_PCT.
RESULTS (HOME /mnt/data/hifipushie/f1/ws = t8 copy; f1/hussar = r-hussar copy; logs f1/job_*.log): t8 shirt REFUSED
(front half, sleeve with no side, fall without roll); trousers REFUSED (front, back halves); belt REFUSED (809 mm vs
the torso's narrowest 787 + 25 gap). Hussar r2 (unchanged): BUILT 150 s, stand rise min 60 / CB 81 deg, top 531.5 = cut,
collar_rise 31.3 -> 74.6 (want 76.5-93.5), collar_top p95 11.5 -> 10.4, collar_front_R 11.8 -> 9.8, zip_line PASS;
REFUSED by the new held read: collar edge 39.8 % at collar:rightTopIn (the END edges: not in the stand's solve).
Sheet f1/hussar/sheet_f1_neck.png: the stand STANDS (upright, CB standing); vs reference too tall at the fronts, CF ends
touching at the top with a teardrop gap below, seam crumpled.
UNVERIFIED: a waistband / belt on a real body (synthetic only: t8's are refused first); trousers' LEGS (no leg axis:
LimbAxis reads arms only; panels below the crotch wrap the torso rings); the half-piece rule's 10 % centring on other drafts.
NEXT: (a) the stand's END edges in its solve (tried as chains neck end -> top end: fought the ends-meet rows; read
which corner pair holds); then rebuild r2 and judge the fronts; (b) leg axes for trousers; (c) F2 / step 4: refuse
`mirror: true` without a pair, and declarations whose pieces the body wears twice, before the flat gate passes.
