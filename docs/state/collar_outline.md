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
## T15 (2026-11-02, C299; structure_outline.py + _look, tests/test_structure_outline.py): OUTLINE vs REFERENCE
Step 2 `traces` [{id, what (structure_outline.KINDS: hem, front_edge, collar_top, collar_front, neckline, sleeve_end,
outline), view, points [[u,v]..] px, corners [indices], source}] + `body_marks` [{view, at: {hps.L: [u,v], waist_z: ..}}];
garment_plan refuses each fault by name and draws the traces (cyan) on step 2's look. Step 6: chain_structure.check adds
rows `outline:<id>`: the build projected along the view; the edge = border loops of the kind's pieces (facing the camera
for hem / fronts), points with a perpendicular foot inside the trace, within 60 deg of it, within the cap; both ways, the
shape after the best shift + the shift; corners: the build turns >= 50 % of the traced turn within tol. tol = 3 px x
mm/px + the border edge; p95 <= tol, max <= 2 tol, shift <= 2 tol + marks residual. SCALE: fit from the body marks (the
body is the ruler); step 0's scale only for a one-mark view, NOTE when off > 5 % (hussar: 1.17 vs 1.062 = +10 %: with it
the zip PASS case fails by 34 mm at its lower end). FAIL backs to step 4 with the pattern edge (declarations; an
undeclared edge named by the draft points it lies between). look_chain draws the sheet when step 2 has traces.
PROOF (copy HOME /mnt/data/hifipushie/t15, T8's build, no new build; scripts t15/scripts/traces.py, check.py, gate.py):
hem FAIL p95 32.5 / max 38.2 mm (tol 11.0), 4 of 4 corners lost (nearest built 25-38 mm), shift 88 mm down (the build
~9 cm short by the body), worst at the notch's step corner -> front.L:cutaway; collar_top FAIL 8.7 / 12.7 (tol 4.8: built
narrower, domed); collar_front R / L FAIL 11.8 / 6.3 (top corners low and inside: collar:tr-br end edge); zip_line PASS
4.2 / 4.9; cutaway_drop still PASSes beside the hem FAIL. Sheet: t15/wf_simon/chain/hussar_open/hussar_open_outline_v0.png.
STEP 4 NEEDS (after T5b): traces whose edge lies flat in the view (a hem, a CF edge) checked on the FLAT pattern before
any build: the declared edge (piece:edge) drawn in mm vs the trace (same compare(), placed by the edge's end points).
UNVERIFIED: side / back views (only front used); a trace through a tube's silhouette (sleeves, a side outline: not a
border edge); the job's answer text with outline rows (rows checked via chain_structure.check, not a new job).
- r-nico (2026-11-02): the hang (zozo_hang.run) runs through the machine's configured route when one is set (localconf HIFIPUSHIE_HANG_REMOTE, local config outside the repo; default local), holding no local slot; its gate there is the job's own structure PASS + 7a (chain_gate.json, written by the worker); exit 9 = not available -> runs here, said in one line (status hang_ran). drape_start_clear reads the start before soft_net (C302).
NEXT: step 4's flat check; redraw the hussar's cutaway (CF step out, then the tails) + the stand's front ends, rebuild.
