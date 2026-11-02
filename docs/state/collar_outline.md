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

## T8 (2026-11-02): roles from any pattern (C289; chain_roles.py, tests/test_chain_roles.py)
Roles from construction + the DECLARED role (draft_pattern pieces.<n>.role -> M["roles"]): FALL (roll fold) / BAND (stiff,
under the fall) / STAND (stiff, on the neckline, no fall: build_stand, the band ring with its own top edge) / a stiff
"collar_fall" with no roll refused by name / RINGS / TUBE of one self-sewn piece or several limb-role pieces sewn together
(two-piece sleeve) / PANELS (half backs = the back; hem = the outline) / FRONT lapped, or ZIP edge to edge (pairs made
along the declared edges, ZIP_GAP, no layer). cf_shirt's roles read the same (t7 built.pkl; scripts/shirt_roles.py).
Hussar (HOME /mnt/data/hifipushie/t8, wf_simon:hussar): collar declared role collar_stand (steps 1-4 redone through the
tools, T6's style plan); the stand ring read the neckline 11 % short round the neck base + GAP (384 vs ~427 mm) ->
redrafted with brian collarEase 0.16 (430 mm); flat gate PASS. Build (job hussar_open, 65-83 s): NO length refusal (free
worst 0.0 %, stand 430.6/430.5 mm, rise 75.7 deg), STRUCTURE FAIL: collar_height 0.055 (0.14-0.20), collar_upright 72.7
(76.5-93.5), closure_front part / meets 0.862 (>= 0.9), soft_cloth_smooth 2.39 (<= 1); PASS cutaway_drop 0.14, closure_collar
open, hem_level_lr 3.9 mm. Sheet: /mnt/data/hifipushie/t8/sheet_b2.png. By eye: stand upright round back and sides but dives to
a V at CF (ring rests tipped 17 deg front-down: the eased ring drops in front); zip edges meet; cutaway right way but rounded;
sleeves two-piece, follow the arm to the wrist; back hem rolls into a ledge; boxy vs the fitted reference.
NEXT: the stand's front: hold the stand's CF ends at the fronts' neckline (not the ring's rest tilt) or raise the fronts'
neck on the pattern; the back-hem ledge (soft network fill, same as T7's hem); where the zip parts (14 % of its length).
Dev: /mnt/data/hifipushie/t8/scripts/{redraft,redraft2,stage_check,chain,reads,render}.py.

## T9 + T12 (2026-11-02): layering (C292, C294; chain_layers.py, chain_press.py, tests/test_chain_layers.py)
Step 1 `over: [...]` (validated); step 2 `layers` {mode: visible (default) | full, why}. ORDER: the under's steps 1 + 4 and
a build (not approved); its fit after the over's build; both approved at the over's 7a (dev: HIFIPUSHIE_LAYER_UNDER=built).
COLLIDER: body + the under's THICKNESS where its soft cloth covers (room()) + its stiff parts' and details' real stand-off
(T9 inflated over the whole loose shirt). FIT (chain_press, in the gate): the under's last solve, chains first, with the
over's inner side as an outer limit where it covers; stiff parts stay; visible mode drops cloth hidden beyond 30 mm of the
seen, holds the cut edge, advises step 1 `build` per piece; <over job>/under_<u>.pkl. GATE: links the under's build held
broken past MAX_FREE_PCT, then the over inside the fit: refused by name.
Proof (HOME /mnt/data/hifipushie/t12/ws; shirt = T7's REFUSED build, own free worst 49 %): 1 build (1135 s) REFUSED: shirt
40.4 % off at 41 links its build held, 1224 points left outside the limit (waist / chest). Jacket rows T12 / T8 / T9:
collar_height .084/.055/.096, upright 64.6/72.7/62.5, front_meets .77/.862/.718, smooth 2.05/2.39/3.93, cutaway
.109 FAIL/.14/.181, hem_lr 8.5/3.9/3.8 mm; jacket free worst 34.9 % at back.L cbNeck (T8 0.0): the shirt's stiff open
collar pushes the stand. Shirt: sleeves 99.5 % hidden (85 % pressed, in 8-9 mm), yoke / stand / collar 99 % hidden (collar
inside the stand), cuffs 72-77 % seen, fronts / back 61-67 % kept. Sheets /mnt/data/hifipushie/t12/sheet_b1_{pair,neck,
jacket_vs_t8}.png. By eye: jacket alone = T8's (a little broader at the neck): no inflation; shirt pokes through at chest /
shoulder blades and its tails are a lumpy skirt with a ragged cut: the shirt build's fault, as gated.
LEFT: full mode's joint hang (merge both write_job arrays, plain body, self_collision, split, finish_hang each); seen
parts riding the over's hang; an open collar laid OUTSIDE a lapel needs a plan field (piece `layer` vs the over's).
NEXT: an approved shirt build (T7's NEXT), rebuild the pair; if the stand still breaks, the shirt collar `build: omit`
under a closed stand (the advice) or the stand eased over it in the draft.
