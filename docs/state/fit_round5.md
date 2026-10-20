# STATE: fit_round5 (Garrett jacket v2 + shirt: the notch) -- 2026-10-19. NO SIMS.

STATE: HANDOVER. Step 1 found three causes, fixed one in the tool (C48, KAT), which moves nothing on Garrett.
notch_step still FAILS (L 0/0, R 8.2/6.3). Blind review FAIL front + three (no notch, fat collar tube, shirt collar).
NEXT (one at a time, re-measure each): (a) L lapel's gorge corner goes THROUGH its own base at relax1 / turn_flaps
(flapside: 66/67 vertices within 30 mm of cfNeck, med -6.9 mm; R +14) and never recovers (let_go 56/67, -2.5): with no
shirt under it 10/67 -> the shirt's L collar under the lapel crumples it before the turn. Fix where the shirt meets the
jacket at the neck (layer order: the shirt collar must sit INSIDE the jacket stand; ring_hug to_shirt -2.5 / -3.8 at
the back = the jacket stand is inside the shirt). (b) the collar end rotates off the lapel: angle at cfNeck P / C 114 deg
on the form vs 67 flat (L); C (endOuter) lies INWARD of G (x 83 < 96): the fall's end points at CF, not at the shoulder.
(c) DESCRIBE gap: the reference notch sits "just below the collarbone" (reviewer, both views); ours is at the neck side
(lapelPoint 25 mm from cfNeck, ~65 mm below HPS in 3D). Measure notch height on the concept and add a checklist item.
Files: $FR5 = /mnt/data/hifipushie/dress_garrett/fit_round5/ (run.sh = this worktree; inputs.pkl -> round 4's).
harness.py <tag> (env NOUNDER=1: no shirt) -> asm_<tag>.pkl + TRACE / NOTCH / FLAP per phase. flat.py (notch_flat),
wedge.py <asm> <tag> [margin] (front-view piece-ID raster around the notch -> wedge_<side>_<tag>.png), gorge.py,
column.py, flapside.py, through.py (shirt-through by piece, any round's pickle), info.py, cmp.py (measure tables),
collar.py (MEASURE_ONLY=1 skips renders), sheet.py, review.sh <view>. Round 5 result: asm_press2.pkl.

## Step 1: the notch, causes in order checked
- FLAT: fine. notch_flat L/R gap 36.5 mm, angle 66.9 deg (target 20-40 / 60-90). Not the pattern.
- PRESSED SEAM: never applied: pressed_cells 0. The rule read flap <-> flap; the two-piece collar's STAND (no fold)
  sits between the lapel's gorge and the fall. Fixed in general (C48, PRESS_UNFOLDED): 290 cells; the lay puts the
  stand end on the lapel's continuation, the relax undoes it (cfTop y -58 laid -> -77 let_go). Every row within 2 mm.
- SEATING: front view (wedge_L_r4wide.png): no collar visible below the shoulder line on L; the gorge, stand end and
  collar end lie BEHIND the front's base (front.L base at uv (80,-112) 22 mm in front of G). Cause (a) above.

## Step 2: the fat roll (measured, not changed)
Collar section +-90 deg turned 88 / 110 (target ~170): at the neck sides the fall stands half open; stand gap to the
neck 25 (60-90 deg) / 35 mm (90-120). The ridge is the stand + half-turned fall standing off the neck, ~25-35 mm deep in
silhouette, vs a stack of ~4 layers x THICK 1.5 = ~6 mm. Same as round 4: no change this round.

## Step 3: shirt through the jacket 265 -> 365 -> 447 (through.py: jacket vertices inside the shirt)
Growth is all the collar FALL above HPS-5 cm: 88 (r1) -> 208 (r3: 144 + 64 flap) -> 245 (r4) -> 252 (r5). r1: fall
unturned. r3: the fall's outer edge cut to its on-body need (spread 43 -> 17 deg, C44) pulls it tight round the neck.
r4: BASE_ACROSS_SEAM draws the fall down onto the stand (C46). Under it at the back sits the shirt collar, OUTSIDE the
jacket stand (ring_hug to_shirt -2.5 / -3.8 mm at 0-60 deg in every round): the fall is pulled through it = the white
scallops. Cause is the layer order at the neck, not the fall; not fixed (same root as NEXT a).

## Table (round 1 | round 3 | round 4 | round 5 | target)
| fall top over HPS (CB) | 71 | 51.8 | 40.1 | 41.1 | ~stand top |
| collar turn CB / 30 / 60 / 90 | - | 161/151-163/131-149/88-112 | 161/162-163/142-158/86-107 | 163/163-164/143-158/88-110 | ~170 |
| fold_turned lapels / collar | | 171/167/NaN | 171/166/142 | 171/166/144 | 165-180 |
| notch step L open/depth, R | - | 0.3/0, 12.3/9.6 | 0.3/0, 9.8/7.6 | 0/0, 8.2/6.3 FAIL | open 2-10, depth 10-26 |
| notch gap / angle (3D) | 57/74 | 26.5/61.4 | 41.2/92.6 | 39.5/89.3 | 20-40 / 60-90 |
| notch flat gap / angle | | | | 36.5/66.9 PASS | 20-40 / 60-90 |
| stand gap to neck CB -> front | 15-34 | 6/10/24/38 | 14/18/25/35 | 13/17/25/35 | 2-5 |
| collar end to gorge | 15 | 14.9 | 14.1 | 13.8 | ~0 |
| shirt collar shows back / side | -11/-8 | 7.7/6.2 | 19.4/15.8 | 18.4/15.0 | 10-15 |
| shirt through jacket (verts) | 265 | 365 | 447 | 454 | 0 |
| pressed_cells | | | 0 | 290 | >0 |

## Known open
Renders: $FR5/check/{front,three}.png (ref | clay | diag), {side,back,top}.png (clay | diag; no reference). Review
FAIL both (review_front.log, review_three.log): no notch, collar tube to jaw height, shirt collar oversized / asymmetric,
shards at the L lapel edge. form_validated() False. PRESS_UNFOLDED default ON (revert: False).
