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

## T7 (2026-11-02, C287; chain_plan.py): built straight into the plan's state. Its proof (cf_shirt shirt_open, HOME
/mnt/data/hifipushie/t7/ws) is still REFUSED (free 49.1 %: the open fronts' placket fold at the hem); rows and NEXT: git
history of this page (commit 80eb32ef) and cloth.md.

## T8 (2026-11-02, C289; chain_roles.py): roles from any pattern (fall, band, stand, rings, tubes of one or more
pieces, panels, lapped / zip fronts). Hussar proof (HOME /mnt/data/hifipushie/t8): STRUCTURE FAIL at the stand's
CF (dives to a V), sheet t8/sheet_b2.png; its rows and NEXT: git history of this page (commit 8c603bda).

## T9 + T12 (2026-11-02): layering (C292, C294; chain_layers.py, chain_press.py, tests/test_chain_layers.py)
Step 1 `over: [...]` (validated); step 2 `layers` {mode: visible (default) | full, why}. ORDER: the under's steps 1 + 4 and
a build (not approved); its fit after the over's build; both approved at the over's 7a (dev: HIFIPUSHIE_LAYER_UNDER=built).
COLLIDER: body + the under's THICKNESS where its soft cloth covers (room()) + its stiff parts' and details' real stand-off
(T9 inflated over the whole loose shirt). FIT (chain_press, in the gate): the under's last solve, chains first, with the
over's inner side as an outer limit where it covers; stiff parts stay; visible mode drops cloth hidden beyond 30 mm of the
seen, holds the cut edge, advises step 1 `build` per piece; <over job>/under_<u>.pkl. GATE: links the under's build held
broken past MAX_FREE_PCT, then the over inside the fit: refused by name.
Proof (HOME /mnt/data/hifipushie/t12/ws): REFUSED as gated (the shirt build's fault: 40.4 % off at 41 links);
numbers and sheets: git history of this page (commit 8c603bda), t12/sheet_b1_*.png.
LEFT: full mode's joint hang (merge both write_job arrays, plain body, self_collision, split, finish_hang each); seen
parts riding the over's hang; an open collar laid OUTSIDE a lapel needs a plan field (piece `layer` vs the over's).
NEXT: an approved shirt build (T7's NEXT), rebuild the pair; if the stand still breaks, the shirt collar `build: omit`
under a closed stand (the advice) or the stand eased over it in the draft.

## T13 (2026-11-02, C297, C299; chain_drape.py, tests/test_chain_drape.py): draped garments (cloak, cape, hood)
ROLE: step 1 piece `hang: draped` + `held: [edges]`; a draped piece with no held edge is held by its seam to one (a hood);
step 2 `drape {piece: {falls: down|up}}`. BUILD (build_drape, wholly draped garments only): the held line a rigid ring of
its cut at the lowest neck height it fits (rest_ring), points at exact CHORDS, ends shut at CF; a held line sewn to itself
refused (check_held_sewn); free cloth starts on clear paths from its nearest held point; soft_net with the body as floor.
GATE SPLIT: hang kinds (drape_hem_height, drape_hem_spread, drape_front_back, hood_opening, hood_depth) on="hang": LATER at
the build, judged by chain_drape.hang_check (FAIL = hang_rows_failed); build rules drape_start_clear, drape_held_exact,
clasp; hang rule hood_on_head.
PROOF T13b (HOME /mnt/data/hifipushie/t13b/ws; dev t13b/dev build.py job.py render.py paths_ab.py; design t13b/designs):
the path search was NOT slow (0-0.15 s per held point; vectorised, same answers); the build is 1400-1700 s in soft_net's
mesh rounds (project's splu, ~107k constraints, 35.8k-vertex net). Fixed: T13's draft sewed hood.R:neck reversed (CF end
and CB one point: held 1343 %, clasp 142 mm; the flat gate can't see it: refused now, draft fixed in the copy); held
links by the clasp 2.8 % short (arc steps): chords now (real ring 0.0 %, clasp 2.4 mm). JOB BUILD (before the chord fix):
clasp PASS 4.0 mm, held FAIL 2.83, start_clear FAIL 4.3 mm, threads max 1115 %: refused, NO HANG, no draped rows.
LOOK (t13b/sheet_build_all.png, sheet_build_hood.png): the cloak starts spread over the arms like a poncho to the hip, its
lower half crumpled; the hood shrink-wraps the skull (no peak, no depth). A rebuild with chords runs: cloak_closed/status.json.
NEXT: (a) drape_start_clear can't pass: range 6 mm > the floor both cloth and held line rest at (GAP 4.5 mm): coordinator
decides the read or the range (no silent waive). (b) start shape: paths nearer vertical below the shoulders, the hem's
fullness folded not crammed; the hood started at its depth. (c) soft_net speed for big drapes. Then hang, rows, render.
