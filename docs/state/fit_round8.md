# STATE: fit_round8 (Garrett jacket v2 + shirt: two layers that touch) -- 2026-10-19. NO SIMS.

STATE: HANDOVER. Two layer orders prototyped on the form (pattern_form.layered_fit, assemble(over=), C51, KAT
test_nested_tubes_inner_pressed_under). outer_first WINS on numbers but NOT over round 6 on through-count: kept OPT-IN,
OPEN_SPREAD stays opt-in. Blind review (outer_first + spread): front FAIL, three FAIL (shirt collar a crumpled ruffle).
NEXT: (a) the shirt collar under the jacket gorge: it is an ARAP made piece pushed through the jacket's stacked gorge
(fall + stand + lapel) -> 1084 collar / stand edges past 30 %; give made pieces under a ceiling a yield (their cells
bend at the contact) or lay the shirt collar on the jacket's collar stand as its "base" (C46 rule across layers).
(b) the shirt can't spread because the jacket's V is too narrow: concept shirt point 71 mm off CF lies inside the
concept's V (roll line ~75 mm off CF there); ours is covered by the lapel (roll row x 33-66 mm), so the spread pins
under the lapel are dropped and the points stay 103 apart. That is the draft / swing (roll line position), queued item.
(c) then the draft values (notch / lapel-point height, lapel width) traced to their tailoring rules.

## A vs B (harness8.py, OPEN_SPREAD on except R6; through both ways by region in m8_<tag>.json)
| run | neck gap CB/30/60/90 | jacket in shirt (collar/fronts) | shirt out of jacket (collar) | shirt pts | shows b/s | roll turn | s |
| R6 base, no spread | 3.1/6.3/18.4/28.0 | 119 (52/23) | 147 (76) | 48 | 4.0/3.4 | 152 | 24 |
| R7 base, spread | 4.9/6.8/19.4/36.3 | 368 (139/178) | 442 (334) | 101 | 0.4/-1.2 | 136 | 24 |
| B outer_first | 2.9/5.3/8.3/14.9 | 252 (90/132) | 139 (101) | 103 | 5.6/3.8 | 141 | 39 |
| A joint (2 rounds) | 3.5/5.5/9.7/35.3 | 203 (66/85) | 117 (69) | 102 | n/a | 132 | 99 |
KAT (two tubes, inner r+20 under outer r+10): outer_first through 0, inner max 8.7 < outer 9.9, outer kept 10.0 mm;
joint through 0 but the outer inflated to 20.1 mm (stretch p99 17.5 %): FAILS. Shirt torn in both on Garrett (p99 57 / 51 %).

## Checklist (m7.py, R8 = outer_first + spread)
| item | concept | tol | R6 L/R | R7 L/R | R8 L/R |
| lapel_point_below_hps | 91 | 79-103 | 103.0/96.4 F | 73.6/93.2 F | 106.1/103.1 F |
| notch_inner_below_hps | 70 | 55-85 | 86.4/78.4 F | 50.7/72.6 F | 87.7/84.5 F |
| lapel_width_front | 72 | 62-85 | 65.1/59.2 F | 60.6/56.2 F | 67.3/61.8 F |
| notch_mouth_front | 31 | 21-41 | 13.5/15.8 F | 32.9/23.7 P | 15.0/17.1 F |
| shirt_point_spread | 146 | 126-166 | 48 F | 101 F | 103 F |
| shirt_point_below_hps | 93 | 78-108 | 77.1/74.7 F | 90.8/88.7 P | 90.2/87.4 P |
| collar_top_side_over_hps | 13 | 3-23 | 31.3/31.5 F | 23.6/30.1 F | 27.5/27.0 F |
| collar_front_rise_over_hps | -20 | -60-0 | -15.1/+1.9 F | none/+4.4 F | -37.7/-44.2 P |
Lapel width vs the front silhouette (m8.py: z-buffered front view, the L lapel's turned faces, visible width on the
row of the tip): R6 62, R7 63, R8 62 mm vs the concept's 71 (tip to roll line, horizontal). AGREES with m7 (~85 %): the
lapel is not half width in plan; the reviewers' "half / missing" is the lapel not READING (no crisp turned edge, a wedge
that narrows to nothing above the tip, sil_<tag>.png), plus the opening's parallel edges (no V).

## Files
$FR8 = /mnt/data/hifipushie/dress_garrett/fit_round8/ (run.sh = this worktree): harness8.py <tag> base|joint|outer
[K=V] (placed inputs cached by code, C49), m8.py (through by region + silhouette), st8.py (shirt strain by piece),
m7.py, collar.py (renders), sheet.py, review.sh, chain1.sh / chain2.sh, kat2.log. check/{front,three}.png ref | clay |
diag; {side,back,top}.png clay | diag; review_front.log, review_three.log.
