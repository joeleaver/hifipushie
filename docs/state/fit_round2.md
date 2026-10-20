# STATE: fit_round2 (Garrett jacket v2 + shirt on the virtual dress form, collar fixes) -- 2026-10-19. NO SIMS.

STATE: 1 done (fall fold line + gate test). 2-4 not started.
NEXT: step 2, the gate WITH refs ($FR2/fit.py, refs = /mnt/data/hifipushie/dress_garrett/refread/garrett_concept_refs_v2.json).
Files: $FR2 = /mnt/data/hifipushie/dress_garrett/fit_round2/ (run.sh runs THIS worktree's code; flat.py). Round 1: $FR1 =
../fit_round1 (fr1.py spec reused). History: docs/notes/cloth.md "fit round 2".

## Steps
1. Fall fold line: DONE. pattern_jacket.op_collar_two_piece adds fold "collar roll" (roll, 10 deg, r 4 mm, strength 0.6) on
   the fall, 4 mm above its seam on the stand (FALL_FOLD, R16), across both halves; wrap turn "at" moved to the same line.
   Flat: stand CB 24.5 / fall 57 (+5 % roll = 60): 30 / 70 (R16). Gate check already existed (garment_design "fold"
   evidence -> flat_pattern FAIL); test added (C41). flat_pattern now PASS, all 10 tailor rows PASS.
2. Gate with refs: -
3. Fit + re-measure + one cause at a time: -
4. Collar check + blind review: -

## Known open (not this round)
form_validated() False (settle parked: cape KAT) -> form rows INFO. Shirt chestEase / waistEase don't move its measured
chest / waist (round 1).
