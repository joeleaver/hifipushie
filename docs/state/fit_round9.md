# STATE: fit_round9 (Garrett jacket FRONT: opening, roll line, V, buttons) -- 2026-10-19. NO SIMS.

STATE: steps 1-2 done (DESCRIBE + flat), step 3 (fit levers) running.
NEXT: chain1 results -> pick the default -> renders (whole front + front + three) -> blind reviews.

## The concept's front is OPEN (re-read; the brief said fastened)
Zoom c_break.png: buttons on the wearer's R front (x 569 / 552 px), the empty buttonholes on the L front edge ~120 mm
across, shirt + belt between them. refread front_state "open", buttons_done 0 (high) agree. The V the eye reads is the
LAPELS' OUTER EDGES converging to the break, and the fronts hang OPEN below it, diverging to the cutaway.

## What was wrong (round 6 / 8 geometry, m9.py front view; fresh = R6, outer2 = R8)
- FORM: only ONE vertex (front.L:break) is held open (worn_open 64 mm); the roll line beside it relaxed back to 34 mm
  off CF, and below the break the free front returned to the closed position (edge 18 mm off CF at 560-600 mm below
  HPS vs the concept's 74-90). WORN_EDGE (holds the swung edge) existed but was opt-in.
- PATTERN: the break 27 mm low on the form (flat 0.455 -> top button 426 below HPS vs the concept's 399), and op_buttons'
  fixed 90 mm spacing had replaced R13 (second button 30 % of break -> hem). Overlap R12 20 mm: OK. Closure "open",
  nothing fastened on the form (fasten "worn_open"): OK.
- NOT in scope, flagged: the silhouette (waist 341 vs 401, hem sweep 437 vs 478 in the front view).

## Checklist (m9.py; tol: edges 15, roll 12, V 25, lapel outer 15, break/buttons 15)
| item | concept L/R | R6 | R8 |
| edge_below_450 / 550 / 650 | 71/66, 78/72, 94/85 | 33/32 F, 19/18 F, 17/15 F | 30/30 F, 12/14 F, 9/12 F |
| opening_half_150 / 250 / 350 | 69/70, 64/57, 59/43 | 53/57 F, 39/42 F, 34/36 F | 52/56 F, 38/40 F, 33/35 F |
| v_width_200 | 237 | 179 F | 178 F |
| lapel_outer_150 / 250 | 127/134, 112/100 | 108/110 F, 71/73 F | 107/110 F, 71/72 F |
| break_below_hps | 386 | 381/377 P | 388/383 P |
| button1 / button2 below HPS | 399, 518 | 426 F, 506 F | 429 F, 505 P |
| waist_width / hem_sweep / front length | 401, 478, 752 | 341 F, 437 F, 754 P | 344 F, 421 F, 755 P |

## Code (this round)
- op_buttons spacing_frac (R13), jacket_ops sets 0.30; cloth_check.big_first (C52): gate rows big to small, detail rows
  BLOCKED while a big read fails; front_state / buttons_done restaged 1 (big reads). Test: test_big_reads_before_details.

## Files
$FR9 = /mnt/data/hifipushie/dress_garrett/fit_round9/ (run.sh = this worktree): m9.py (front items, concept + ours),
fr9.py (spec: BREAK_Y, WORN), harness9.py (code + SPEC keyed cache, flat table before the fit), chain1.sh, edge9.py,
c_*.png concept crops with grids, cmp_front_r6_r8.png, add_items.py (checklist items).
