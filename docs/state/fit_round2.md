# STATE: fit_round2 (Garrett jacket v2 + shirt on the virtual dress form, collar fixes) -- 2026-10-19. NO SIMS.

STATE: 1 done (fall fold line, gate test, R16/R15 rules from practice, two-piece flat readers). 2 running (gate with refs).
NEXT: when $FR2/fit.log shows both gates PASS: $FR2/collar.py (measures + check PNGs), then fix one cause at a time.
Files: $FR2 = /mnt/data/hifipushie/dress_garrett/fit_round2/ (run.sh runs THIS worktree's code; fr2.py = fr1 spec + env
overrides; flat.py, sweep.py flat probes; fit.py gate + form -> asm.pkl, gate.json; waive.json; collar.py). Round 1: $FR1 =
../fit_round1. History: docs/notes/cloth.md "fit round 2".

## Steps
1. Fall fold line: DONE. pattern_jacket.op_collar_two_piece adds fold "collar roll" (roll 10 deg, r 4 mm, strength 0.6) 4 mm
   over the fall's seam on the stand (FALL_FOLD), across both halves. Gate refusal existed (garment_design "fold"
   evidence -> flat_pattern FAIL); test added (C41).
1b. Gate with refs showed UNMEASURED collar_stand / collar_fall / notch: no flat reader for a TWO-PIECE collar (tool).
   Added cloth_check.collar_draft_two_piece + _notch_flat_two_piece. They then read fall - stand 27.5 (want 6-15) and
   notch gap 61 (want 20-40): R16 was Jaeger's 18 % x 30/70. Coordinator agreed to change it. R16 now gives stand 25-30
   from the roll line (neck/16, clamped), fall = stand + 10; R15 fall end 0.5 x CB. Garrett flat: stand 28.3 (piece 24.3
   = round 1's "~25", which was the piece), fall 40.5, f-s 12.1, notch 35.2 mm / 66.6 deg, tailor rows 10/10. Necks
   405 / 450 / 522 all in target (test, C42).
2. Gate with refs + waive.json (shirt pockets, jacket vent: not in the front-only concept; no vent is drafted): running.
3. Fit + re-measure + one cause at a time: -
4. Collar check + blind review: -

## Known open (not this round)
form_validated() False (settle parked: cape KAT) -> form rows INFO. Shirt chestEase / waistEase don't move its measured
chest / waist (round 1). The jacket has no back vent (R24 not drafted).
