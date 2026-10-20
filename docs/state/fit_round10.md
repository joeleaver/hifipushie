# STATE: fit_round10 (Garrett jacket: silhouette big to small, then sleeves, lapel face) -- 2026-10-19. NO SIMS.

STATE: step 1a DONE (open fronts without the side slide). Candidate r10c = r9h + OPEN_HOLD (opt-in) + the plumb hang:
hem 492 (concept 478, r9h 574 F) P; side seams at the hem back to the closed fit's (x 210/221, r9h 288/293); every
front-edge / roll-line / button row still passes. Waist 343 vs 401 F.
NEXT: step 1b the waist: the form keeps lengths at the waist (horizontal edges 1.00), so the pinch is the DRAFT
(waist ease R8 14 %, an hourglass) vs the concept's near-straight torso; then step 2 sleeves, 3 lapel face, 4 renders.

## Causes (step 1a)
- r9h opened the fronts by the edge alone (WORN_EDGE): an isometric front can only do that by sliding round the body,
  the side seams 70 mm out at the hem (a peplum). A real open front hangs from its seams: pivots at the break, falls.
- Form rule (pattern_form.open_seam_holds, OPEN_HOLD): a worn-open piece's seams to OTHER pieces below its break are
  held where the CLOSED fit puts them (a second assemble with worn_open=None); pieces with a fastened closure are
  left alone (the shirt: held, it went into the body). worn_open_edge: below the lowest worn-open point the free edge
  hangs plumb (x = that point's offset + the draft's own run-out: a cutaway), OPEN_HANG with OPEN_HOLD; not on
  buttoned pieces (hung, the shirt opened to the belt).
- Known answer test_open_front_hangs_without_moving_its_side_seams (open tube on a cylinder): hold -> side seams 0.0 mm,
  edge below the break 50 mm off CF, y -161 (bridges forward); without: side 11 mm, edge back to CF.

## Table (m10.py, front view; m9's hem_sweep was a bad read: now the torso's OUTER width, sleeves apart)
| item | concept | r9h | r10b (hold) | r10c (hold+hang) | r10d (break only) |
| edge_below_450/550/650 | 71/66, 78/72, 94/85 | 57, 74, 86 P | same P | 57/58, 75, 86 P | 64, 64, 64 (650 F) |
| opening_half_150/250/350 | 69/70, 64/57, 59/43 | P | P | P | 250, 350 F |
| v_width_200 | 237 | 209 F | 208 F | 208 F | 225 P |
| lapel_outer_150 / 250 | 127/134, 112/100 | 124/119, 88/84 F | F | 120/116, 87/84 F | 125/121, 97/96 P |
| waist / hem / length | 401 / 478 / 752 | 358 F / 574 F / 758 | 343 F / 458 P | 343 F / 492 P / 759 P | 323 F / 431 F |
| side seam hem x (closed 217) | - | 288/293 | 210/221 | 210/221 | 209/208 |

## Files
$FR10 = /mnt/data/hifipushie/dress_garrett/fit_round10/ (run.sh = this worktree): harness10.py (fr9 spec; code+spec
keyed cache, C49), m10.py (m9 + side seam rows + outer silhouette), thru.py (shirt through jacket), waist.py (slices:
widths, stand-off by direction, horizontal edge ratio), chain1.sh / chain2.sh, asm_r10{a,b,c,d}.pkl, front_<tag>.png,
cmp_front_r10a.png, cmp_front_r10bcd.png. r10c: WORN='{"break": 0.064, "cfHem": 0.096}' run.sh harness10.py r10c base
WORN_EDGE=true OPEN_HOLD=true
Garrett's checklist (outside the repo): /mnt/data/hifipushie/dress_garrett/fit_round10/checklist_r10.md (R10 column).
