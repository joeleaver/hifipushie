# STATE: fit_round6 (Garrett jacket v2 + shirt: layer order at the neck) -- 2026-10-19. NO SIMS.

STATE: step 1 + 2 done (cause found, re-fit, table); renders + blind review next (step 4).
NEXT: render $FR6/check (collar.py under capped), sheet.py, review.sh front then three; then the notch's 3D closure
(P-G-C 29 deg vs 67 flat, gap 13 mm: the collar end closes onto the lapel point at the "seat" phase).
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

## Files
$FR6 = /mnt/data/hifipushie/dress_garrett/fit_round6/ (run.sh = this worktree). harness.py <tag> (code-keyed cache),
layers.py <asm|shirt pkl> (layer stack by angle x height), shirt.py <tag> [K=V] (the shirt alone), clear.py (flat
clearance rows), endrot.py <harness log> (P-G-C per phase), collar.py (MEASURE_ONLY=1), cmp.py, through.py (round 5).
