# STATE: fit_round7 (Garrett jacket v2 + shirt: the collar's front, measured) -- 2026-10-19. NO SIMS.

STATE: HANDOVER. Step 1 done (8 measured DESCRIBE items, all FAIL on R6 where the render fails). Step 2 done: the
jacket collar's front stand-off is the SHIRT COLLAR under it (no shirt: 5 / 12 mm at 60 / 90 deg vs 18 / 28). Behind it:
the form never spread the shirt's OPEN collar (points 48 mm apart, concept 146). Fixed in the tool (OPEN_SPREAD, C50,
KAT) but OPT-IN: the jacket over the spread shirt got worse (19 / 36 mm, through 119 -> 368, torn shirt in the renders).
Blind review R7 (spread on): front FAIL, three FAIL.
NEXT: (a) make the jacket collar lie over a spread shirt collar: the shirt's made pieces under the jacket need pressing
(cloth.pressed keeps them as they lie) or the jacket stand/fall must be fitted with the shirt collar as a soft layer;
measure stand gap + through per phase with OPEN_SPREAD=true before changing anything. (b) the spread itself is
asymmetric (points x +59 / -41): band_init stands the shirt collar asymmetrically (points x 69 / -115) before the turn.
(c) then the worst draft item: lapel_point / notch_inner height and lapel width (not started; trace to the rule).
Queued, not started: draft every visible part (plackets, flaps, welt lips, cuff plackets, buttons as marks).

## Step 1: DESCRIBE items (m7.py; concept picks in $FR7/ref_notch_zoom.png, 1.125 mm/px, HPS (700,350)/(560,350))
Notch targets settled: the FRONT VIEW governs (C47, the concept is a front view). notch_mouth_front = the projected
lapel-point -> collar-end distance (= notch_step mouth_mm), concept 31 mm; notch_step open (gap pixels along the mouth)
2-10 and depth 10-26 stay. The 3D gap (20-40) is the same tip distance unprojected (>= the mouth): INFO only.
| item | concept | tol | R6 L/R | R7 (spread) L/R |
| lapel_point_below_hps | 91 | 79-103 | 103.0/96.4 F | 73.6/93.2 F |
| notch_inner_below_hps (cfNeck) | 70 | 55-85 | 86.4/78.4 F | 50.7/72.6 F |
| lapel_width_front (tip to roll row) | 72 | 62-85 | 65.1/59.2 F | 60.6/56.2 F |
| notch_mouth_front | 31 | 21-41 | 13.5/15.8 F | 32.9/23.7 P |
| shirt_point_spread | 146 | 126-166 | 48 F | 101 F |
| shirt_point_below_hps | 93 | 78-108 | 77.1/74.7 F | 90.8/88.7 P |
| collar_top_side_over_hps | 13 | 3-23 | 31.3/31.5 F | 23.6/30.1 F |
| collar_front_rise_over_hps | -20 | -60-0 | -15.1/+1.9 F | none/+4.4 F |
Caveat: lapel width reads 80-90 % of the concept here, the reviewers say "half": the roll-row line may not be the
visible fold; check with a front-view silhouette read before drafting from it.

## Step 2: the phase (harness STAND trace, median stand gap to the body per 30 deg; 0 = CB)
| run | band_init 60/90 | seat 60/90 | let_go 60/90 |
| base (R6) | 7.9/15.6 | 11.3/21.3 | 18.4/28.0 |
| PRESS_UNFOLDED=false | 8.1/15.8 | 12.6/19.7 | 18.1/26.4 (not it) |
| NOUNDER (no shirt) | -0.5/7.3 | 1.3/7.3 | 4.9/11.9 (THE SHIRT) |
| OPEN_SPREAD on | 3.8/14.0 | 6.2/14.0 | 19.4/36.3 |
The stand rides the fronts' neckline (standlean.py: neck seam 16/20 mm off = stand neck edge). Shirt alone (shirt7.py):
placement (sim rule spread) points 150 apart -> relax1 98 -> band_init re-stands a ring (194, above HPS) -> turn_flaps
folds the ends to CF (46) -> let_go 48; its stand 25-36 mm off the neck at 120-180 deg.

## R7 table (asm_sp = spread on | asm_base = R6 repeated, same cache key 5ec837f48cb4)
| item | R6 | R7 sp | target |
| fall top over HPS (CB) | 44.9 | 41.1 | ~stand top |
| stand to neck CB/30/60/90/120 | 3.1/6.3/18.4/28.0 | 4.9/6.8/19.4/36.3/47.9 | 2-5 |
| stand to shirt same | 0.1/1.1/7.6/13.5 | 0.6/-0.9/3.2/8.9/11.9 | >= 0 |
| shirt collar shows back/side | 4.0/3.4 | 0.4/-1.2 | 10-15 |
| fold_turned lapels/collar | 167/166/152 | 168/165/136 | 165-180 |
| notch_step open/depth L, R | 13.5/20.1, 15.8/12.6 | 32.6/40, 22.4/40 | 2-10 / 10-26 |
| jacket inside shirt | 122 | 368 | 0 |

## Renders + blind review ($FR7/check, review_front.log, review_three.log): R7 = spread on
My read first: WORSE than R6. Shirt collar torn through the jacket collar both sides, white flecks through the jacket,
collar asymmetric, still no notch, lapels narrow, jacket collar still stands up the neck (three view). front FAIL (no
notch, fragmented coil collar, shirt collar barely there, chest island); three FAIL (popped funnel collar to the jaw,
no notch, lapels half width, shirt and jacket collars through each other, shirt opening a slot, points folded in).

## Files
$FR7 = /mnt/data/hifipushie/dress_garrett/fit_round7/ (run.sh = this worktree). harness.py <tag> [K=V] (code-keyed cache,
+ STAND trace; NOUNDER=1 env), m7.py <asm.pkl> (the new items), shirt7.py <tag> [K=V] (shirt alone, traced),
standlean.py, strain.py, slices.py <asm> <png> (horizontal sections), collar.py (MEASURE_ONLY=1), sheet.py, review.sh.
