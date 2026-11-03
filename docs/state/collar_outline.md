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

## T13 (2026-11-02, C297; chain_drape.py, tests/test_chain_drape.py): draped garments (cloak, cape, hood)
ROLE: step 1 piece `hang: draped` + `held: [edges]` (the draft's edge names built on the body); a draped piece with no held
edge is held by its seam to one (a hood on the cloak's neck); step 2 `drape {piece: {falls: down|up}}` (hood worn up).
BUILD (build_drape, wholly draped garments only; fitted + draped refused by name): the held line rested as a rigid ring of
its cut length at the lowest height round the neck it fits (chain_rest.rest_ring), ends shut at CF (clasp); free cloth
starts on clear paths from its nearest held point (out + down / up, then straight), ends fanned; soft_net projects with
the body as floor; the held line pinned in the hang (hold_mask). BODY: the collider is already the whole
body incl. the head (wf_simon z to 1.78 m; no hair: the head alone).
GATE SPLIT: structure_rows hang kinds (drape_hem_height of stature, drape_hem_spread of shoulder_width, drape_front_back,
hood_opening / hood_depth of neck_width) carry on="hang": LATER at the build (record: waits_for_hang), judged after the hang
(chain_drape.hang_check -> status hang_structure; FAIL = stage hang_rows_failed). Build rules: drape_start_clear,
drape_held_exact, closure clasp via drape_clasp_state; hang rule hood_on_head. A row `judged` on the wrong stage, a hang row
with no draped piece falling that way, drape on a fitted piece: refused by garment_plan with the list.
PROOF (HOME /mnt/data/hifipushie/t13/ws, dev scripts t13/dev, design t13/designs/cloak.mjs + cloak_decl.json): steps 0-4
through the tools: half-circle cloak (neck 370.5 + 80 mm, r2 1365 mm) + two-piece hood; flat gate PASS (3 seams 0 off).
Build: three fixes on the way (ring caught on the chin / inside the chest: now rested rigidly); the last build (old start
search, t13/dev/build2.log) had not finished at the budget: the path search is a python loop per held vertex (~400
candidates x a Contact query each): UNVERIFIED: build numbers, structure rows, 7a, hang, draped rows, render.
NEXT: vectorise _paths (all candidates in one query), finish the build (dev/build.py), then the job (dev/job.py, dev
HIFIPUSHIE_PRESIM_APPROVAL=optional), render the hang beside refs/ranger/front.png; the capelet as a second draped piece.
