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

## T9 (2026-11-02): layering (C292; chain_layers.py, tests/test_chain_layers.py)
Declared: step 1's `over: ["shirt"]` (garment_plan: a garment of the model with a record, not itself, no loop). ORDER, at
the call: each under garment's build with its step 6 done and 7a ready, else refused by name + next (dev setting
HIFIPUSHIE_LAYER_UNDER=built: any saved build, flagged UNAPPROVED). Its build id is in the job key. COLLIDER: the body
INFLATED over the under garment (its hung result, else its build) + its details.pkl solids, gap = its cloth thickness +
ZOZO's reach (buttons: reach); one closed surface, so torso rings, contact, structure gate and ZOZO all read it. One way:
the shirt never moves. GATE: over-garment points inside it refused by piece / level / girth to add, before the lengths.
Build 1 (nearest of body and the shirt's own open surface) crumpled the jacket into a bolero: replaced.
Proof (HOME /mnt/data/hifipushie/t9/ws, cf_shirt: T10's shirt + T8's hussar, same body; shirt UNAPPROVED, its own build
refused): build 2 (199 s) REFUSED: collar (the stand) inside the shirt at 1508 points, 11.4 mm deep at the neck (the
shirt's open collar stands 20-50 mm off the neck; a 430 mm stand can't go round it); fronts/backs 26-40 points <= 11 mm
at the neck/armpit (pulled in by the stand). Closest to the buttons 3.6 mm (none inside). Rows vs T8 body alone:
collar_height 0.096 (0.055), collar_upright 62.5 (72.7), front_meets 0.718 (0.862), soft_cloth_smooth 3.93 (2.39); same
PASS (cutaway 0.181, hem 3.8 mm). Sheets /mnt/data/hifipushie/t9/sheet_b2_{whole,neck}.png: jacket outside the shirt
everywhere, shirt collar hidden in the stand, but the stand flares out and dips at CF; boxy; shirt tails below the hem.
NEXT: an approved shirt first (T7's NEXT); then the stand's ease over the shirt collar (collarEase from the shirt's neck
standoff) or the shirt's collar tucked; a hang over the layered collider is unverified.
