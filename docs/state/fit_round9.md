# STATE: fit_round9 (Garrett jacket FRONT: opening, roll line, V, buttons) -- 2026-10-19. NO SIMS.

STATE: HANDOVER. Candidate r9h = break_y 0.425 + R13 buttons + worn_open {break 0.064, cfHem 0.096} + WORN_EDGE: every
front-edge / roll-line / button row PASSES (were all FAIL), but the open edge slid the side seams out: hem 580 mm wide
in the front view (concept 478, closed R6 437): a NEW silhouette fault. Not made the model default (WORN_EDGE opt-in).
Blind reviews FAIL wholefront / front / three.
NEXT: (1) open the fronts WITHOUT the side slide: the front must hang forward off the hips (y), not wrap and slide (x).
EDGE_FREE 0.08 -> 0.2 changed nothing (r9f); the cause is isometry + seat pull; try holding the side seams (side.*
x pinned at their closed-fit x) or a stand-off target for the edge (y). (2) The lapel face is a narrow strip: lapel
outer at 250 mm 86 vs 106, V at 200 209 vs 237; reviewers: "no turned lapel face on the chest" -> draft lapel width at
the break end / roll. (3) The waist pinch (341-358 vs 401): silhouette, block / suppression. (4) Pockets (queued).

## The concept's front is OPEN (re-read; the brief and the blind reviewer said fastened: DISPUTED)
Zoom c_break.png: buttons on the wearer's R front (569 / 552 px), the empty buttonholes on the L front edge ~130 mm
across, shirt + belt continuous between them. refread front_state open / buttons_done 0 (high). The V the eye reads is
the LAPELS' OUTER EDGES converging to the break; below it the fronts hang open and diverge to the cutaway. If Joe wants
it fastened, that is a design change (closures state + worn_open removed).

## What was wrong (m9.py, front view)
- FORM: only ONE vertex (front.L:break) held open (worn_open 64 mm): the roll line beside it relaxed to 34 mm off CF,
  below the break the free front returned closed (edge 18 mm off CF at 560-600 vs the concept's 74-90).
- PATTERN: break 27 mm low (flat 0.455 -> top button 426 below HPS vs 399); op_buttons' fixed 90 mm spacing had
  replaced R13. Overlap R12 20 mm OK; closure open, nothing fastened on the form (fastened(M,"worn_open") = []).

## Checklist (m9.py; tol edges 15, roll 12, V 25, lapel outer 15, break / buttons 15, waist 16, hem 24)
| item | concept L/R | R6 | R8 | r9old | r9e (WORN_EDGE) | R9 = r9h |
| edge_below_450/550/650 | 71/66, 78/72, 94/85 | 33,19,17 F | 30,12,9 F | 33,19,17 F | 23,15,11 F | 57/58, 74/75, 86/86 P |
| opening_half_150/250/350 | 69/70, 64/57, 59/43 | 53,39,34 F | 52,38,33 F | 53,39,34 F | 79 P, 71 F, 66 F | 72/68, 59/57, 51/50 P |
| v_width_200 | 237 | 179 F | 178 F | 175 F | 225 P | 209 F |
| lapel_outer_150 / 250 | 127/134, 112/100 | 108, 71 F | 107, 71 F | 108, 71 F | 130 P, 95 F | 124/119 F, 88/84 F |
| break_below_hps (lapel's lowest) | 386 | 381 P | 388 P | 381 P | 356 F | 362/353 F |
| button1 / button2 | 399 / 518 | 426 F / 506 F | 429 F / 505 P | 426 F / 519 P | 390 P / 495 F | 404 P / 514 P |
| waist / hem sweep / length | 401 / 478 / 752 | 341 F / 437 F / 754 P | 344 F / 421 F | 341 F / 437 F | 341 F / (bad read) | 358 F / ~580 F / 758 P |
(m9's hem_sweep reads 41 on open fronts: the jacket back shows through the opening at CF; rowruns.py: -285..293.)
Round 8's items on r9h (m7): lapel_point 95/93 P, notch_inner 81/76 P (were F), lapel_width 61/57 F, notch_mouth
12/6 F, shirt_point_spread 62 F, shirt_point_below 76/75 F, collar_top_side 33/34 F, collar_front_rise +3 F.

## LOOK (check/, blind, one view each): all FAIL
wholefront: MAJOR "doesn't close / no buttons" (disputed, above), lapels not a turned face on the chest, waist pinch +
hem flare (peplum), no cutaway quarters, pockets missing; MINOR a jag in both edges at the break. front / three: the
jacket collar a funnel, no notch, lapels thin strips, shirt collar a band (collar stage: untouched this round).

## Code (this round)
op_buttons spacing_frac (R13), jacket_ops sets 0.30; cloth_check.big_first (C52) + front_state / buttons_done stage 1;
test_big_reads_before_details.

## Files
$FR9 = /mnt/data/hifipushie/dress_garrett/fit_round9/ (run.sh = this worktree): m9.py, fr9.py (BREAK_Y, WORN env),
harness9.py (code + SPEC keyed cache; flat table first), chain1.sh, asm_{r9old,r9a,r9e,r9h,r9f}.pkl, front_<tag>.png
label views, cmp_front_r9.png, render9.py, review9.sh, check/{wholefront,front,three}.png (ref | clay | diag),
review_{wholefront,front,three}.log, c_*.png concept crops with grids.
r9h: WORN='{"break": 0.064, "cfHem": 0.096}' run.sh harness9.py r9h base WORN_EDGE=true
