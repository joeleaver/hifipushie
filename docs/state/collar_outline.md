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

## T9 + T12 + T12b (2026-11-02): layering (C292, C294, C296; chain_layers, chain_press, chain_hidden, test_chain_layers)
Step 1 `over: [...]`; step 2 `layers` {mode: visible (default) | full, why}. ORDER (visible, chain_hidden.build_over, C296):
(a) the over garment on the body + the under's cloth THICKNESS only; (b) visibility on that build (an under point is hidden
where the over covers it); (c) pieces hidden >= 98 % OMITTED for real, the rest trimmed to seen + 30 mm; (d) only kept stiff
parts + seen solid details push: the over is RE-SOLVED from (a) (held points moved out) if one reaches it, then the trim
read again (omissions kept); (e) the kept parts pressed inside (8 rounds; only STIFF points held: the build's last solve
held its far cloth too, T12's poke-through) and the cut moved onto the 30 mm level line of a smoothed field, smoothed,
held inside the cover. Full mode keeps T12's order. The inside gate reads only the kept cloth. Record: reads.hidden
{omitted + why, the garment_plan "parts" call with `build: omit` per piece}; T12's advice only for full mode.
Proof (/mnt/data/hifipushie/t12b/ws, shirt = T7's refused build; 2 builds, the 2nd 171 s): omitted yoke, sleeves, stand,
collar (100 % hidden); kept back 34 %, fronts 39-42 %, cuffs 75-78 %; pushing: cuffs (364 faces) + front / cuff buttons:
re-solved (1649 held points out). Jacket free worst 1.097 % (T12 34.9, T8 0.0). Rows T12b / T12 / T8: collar_height
.070/.084/.055, upright 70.7/64.6/72.7, front_meets .862/.77/.862, smooth 2.85/2.05/2.39, cutaway .105 FAIL/.109/.14 PASS,
hem_lr 3.6/8.5/3.9 mm. Shirt fit (regate on build 2's jacket with the retrim, dev/regate.py): lengths PASS (kept worst
1.8 %, 0 broken; before retrim 3.6 %, 4 links at the V top), 0 points outside the limit, cut 251 points 100 % inside the
cover, rough p95 5.8 -> 2.0 mm (edge 9.7). STILL REFUSED: the jacket inside the shirt's kept cloth at 13 points (7 armpit
front.L 9.8 mm; 6 high hip back.L 20 mm: the shirt tails' flare wrapping the jacket's hem rim). Sheets
/mnt/data/hifipushie/t12b/sheet_b2_{pair,neck,jacket_vs_t8}.png: no shirt through the jacket, no shirt collar, cut unseen;
the tails below the hem a wide lumpy skirt with a ragged hem (the shirt build's own shape); jacket alone ~ T8's. LEFT:
full mode's joint hang; an open collar laid OUTSIDE a lapel needs a plan field (piece `layer`). NEXT: the 13 inside points (seen tails: press the seen cloth under the over's hem rim, or the inside read skips the rim
within the over's thickness); then an approved shirt build (T7's NEXT) and the pair rebuilt.