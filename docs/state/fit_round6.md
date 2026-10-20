# STATE: fit_round6 (Garrett jacket v2 + shirt: layer order at the neck) -- 2026-10-19. NO SIMS.

STATE: HANDOVER. Layer order at the neck FIXED (it was a stale harness cache, C49): back clean, through 454 -> 119.
Blind review still FAIL front + three: collar front ends flare off the neck ("cape" / "funnel"), no notch / lapel read,
lapels ~half the reference width, shirt collar a tall band not a spread collar, collar rides to the jaw (side).
NEXT (one at a time, measure first): (a) the collar's FRONT half stands off the neck: stand gap 18 / 28 mm at 60-120 deg
(target 2-5; CB now 3) -> find the phase (add a stand-gap-by-angle line to the harness TRACE); (b) notch targets
disagree: 3D gap 20-40 vs front-view mouth 2-10 (ours 14 / 13.5-15.8): settle from the concept before tuning;
(c) DESCRIBE gaps the review names: lapel width (ours ~half), shirt collar spread / points over the jacket, collar
height on the neck (fall top 45 mm over HPS; shirt shows 4 / 3.4 mm, target 10-15). Queued (not started): notch
height checklist item; draft every visible part.
Coordinator decision (round 5's question): PRESS_UNFOLDED stays ON by default (tailoring practice, KAT proves it, no
chain of faults).

## Step 1: why the shirt collar sat outside the jacket stand -- A STALE CACHE (C49)
Measured each suspect before changing anything:
- flat layer clearance, neck row (cloth_check.layer_clearance_rows, clear.py): jacket stand neck edge 491.2 mm over the
  shirt's 452.8 + 2 pi x 3 -> PASS, margin +19.6 mm. Not the cause.
- the form's neck-point lift over the under layer (_pins): neck points 0.1-0.3 mm off target. Not the cause.
- the shirt collar's own size / fit (shirt.py: the shirt alone on the form, current code): fall 3.3-4.1 mm off its own
  stand at every angle, stand 2.8 / 3.6 / 5.9 mm off the neck at 0-90 deg. Sound at the back. (Its front ends stand
  15-36 mm off the neck at 90-180 deg: the open neck, not the layering.)
- THE CAUSE: the harness's inputs.pkl (made in round 4 at 20:21, before C46 BASE_ACROSS_SEAM landed) held a shirt
  assembled by the old code: its fall 9-17 mm off its stand (shirt.py with BASE_ACROSS_SEAM=false reproduces round 5's
  shirt numbers exactly: 3.5/4.1/6.3/21.4/23.7/26.7). Rounds 4-5 fitted and measured the jacket over that shirt. The
  gate path (on_form) builds the shirt fresh, so it never had the fault.
- Fix: fit_round6/harness.py keys its cache by a hash of pattern_form + cloth + folds source and the overrides
  (inputs_<hash>.pkl). Known answer: tests/test_pattern_form.py test_nested_collars_keep_their_layer_order (an outer
  two-piece collar over an inner on a neck cylinder: 0 outer vertices > 0.5 mm inside; inner fall 4.3 mm off its stand).
  codified.md C49. No pattern or tool change was needed.

## Step 2: table (round 5 = stale shirt | round 6 = fresh; asm_fresh.pkl)
| item | R5 | R6 | target |
| fall top over HPS (CB) | 41.1 | 44.9 | ~stand top |
| collar turn CB / 30 / 60 / 90 | 163/163-164/143-158/88-110 | 176/172-176/169-170/155-158 | ~170 |
| fold_turned lapels / collar | 171/166/144 | 167/166/152 | 165-180 |
| notch step L open/depth, R | 0/0, 8.2/6.3 FAIL | 13.5/20.1, 15.8/12.6 (open too wide) | open 2-10, depth 10-26 |
| notch gap / angle (3D) | 39.5/89.3 | 14.0/4.4 FAIL | 20-40 / 60-90 |
| P-G-C at the gorge (let_go) | 114 | 29 | 67 (flat) |
| stand gap to neck CB / 30 / 60 / 90 | 13/17/25/35 | 3.1/6.3/18.4/28.0 | 2-5 |
| stand to shirt CB / 30 / 60 / 90 | -2.8/-3.7/2.8/10.2 | 0.1/1.1/7.6/13.5 | >= 0 |
| collar end to gorge | 13.8 | 8.6 | ~0 |
| shirt collar shows back / side | 18.4/15.0 | 4.0/3.4 FAIL | 10-15 |
| jacket inside shirt: all | 454 | 119 | 0 |
|   collar fall / stand | 253 / 62 (3.3 mm deep) | 38 / 14 (0.6 mm) | 0 |
|   lapel + gorge (front above HPS-5cm) | 63 | 5 | 0 |
|   body (below HPS-5cm + back yoke) | 76 | 62 | 0 |
| L gorge flap through its base (let_go) | 56/67 | 0/67 | 0 |
| pressed_cells | 290 | (on) | >0 |

## Step 3: the collar end's rotation (endrot.py on the harness NOTCH trace)
Round 5's 114 deg (C inward of G) was the stale shirt too: fresh, P-G-C at let_go is 29 deg, C.x 126 > G.x 116 (the
end points outward again). Phases: turn_flaps 133 -> seat 22 -> let_go 29: SEAT closes the end onto the lapel point
(|PC| 24 -> 13 mm). Flat is 67. Not changed this round (the notch targets disagree, NEXT b).

## Step 4: renders + blind review (check/, review_front.log, review_three.log)
My read before the review: back is clean (no scallops, a thin even shirt line); the fall is turned and lies; but at the
front the collar ends flare out toward the shoulders as thin wings, no notch, narrow lapels, shirt collar small and
crumpled at its points, side view collar up to the jaw, a white shirt fleck through the R shoulder. FAIL, agrees with
the reviewer. front FAIL: collar flares at both shoulders, no notch / lapel, gap jacket collar to shirt collar at the
sides, shirt points crumpled, shirt band high and tight. three FAIL: no lapel, no notch, L collar a funnel, shirt collar
a band, sides don't match, lapels half width (diag), holes lower left (OTHER STAGES: body through-count 62).

## Files
$FR6 = /mnt/data/hifipushie/dress_garrett/fit_round6/ (run.sh = this worktree). harness.py <tag> (code-keyed cache),
layers.py <asm|shirt pkl> (layer stack by angle x height), shirt.py <tag> [K=V] (the shirt alone), clear.py (flat
clearance rows), endrot.py <harness log> (P-G-C per phase), collar.py (MEASURE_ONLY=1), cmp.py, through.py (round 5).
