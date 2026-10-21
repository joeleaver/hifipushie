# STATE: dress_garrett_shirt (Garrett's shirt on its own, then under the round-26 jacket) -- 2026-10-21, shirt round 9

QUESTION (Joe 2026-10-20): "will all the lessons we learned on the jacket carry over and it won't take 30 rounds?"
Rounds 1-7: process carried, geometry didn't; C103-C117. Round 8: gate PASS (C118), arrangement ran, first button +
V pass; collar spread stuck (C120). Jacket thread: docs/state/dress_garrett_fit.md (read-only here).
ROUND 9 step 1 (measure first, M12; notes cloth.md "shirt round 9"):
- The "fall turned 123 of 180" was the READ, not the cloth (C121): fold_turn compared turn to the declared ANGLE, took
  angle 0 (folded right over) as unset, and read mean normals (cancel round a wrapped fold). In section the shirt
  collar is turned 162-167 (PASS); the jacket collar 175 (normals said 13). Fixed + KAT; C119 closed (stand as base).
- The funnel is the DRAFT: the fall is a straight band (outer 453.8 vs sewn 441.9 mm); turned down over the stand its
  edge must land on the shoulders / chest: path 568.9 mm (garment_reads.fall_spring_reads). 115 mm short: it hangs as
  a tube 4-6 mm out from the neck seam, never reaching the shoulders.
NEXT: step 2: spring the fall in the draft (any stand + fall collar: slash-and-spread to its landing path), KAT on a
cylinder neck with shoulders (fall >= 170 over the stand, edge on the shoulders), gate row; then Garrett closed, open.

## Big reads (concept | r8 s8c (arranged, keep) | r9)
- V bottom below HPS: 60 | 74.1 PASS (band 45-75) | -
- Collar points apart: 147 | 87.5 FAIL | -. Below HPS 50-61: 82 | 65.8 PASS (band 35-76) | -
- First fastened button: 83 | 77.3 PASS (band 68-98) | -
- Collar turn over the stand (in section, C121): full fold 180 +- 35 | 162 PASS (round 8 reported 123: the read) | -
- Fall outer edge vs landing path (flat): >= need - 6 | 453.8 vs 568.9 (-115) | -
- Fall edge out from the neck seam at the sides (form): on the shoulders | 4.5 mm (a tube) | -
- Cuff past jacket sleeve (17-23) / collar above jacket collar (11-23): r5 13.1 / 7-8 | not run | -

## Jacket r26g fold rows (C121 changes the reads only; module behaviour unchanged): collar roll turn 13.4 "PASS vs 10"
(old) -> 174.9 PASS vs 170; lapels 112 / 128 FAIL vs "15" (old) -> 158 / 163 PASS vs 165. j_before.log / j_after*.log.

## Code this round: fold_checks declared_turn / turn_achieved / narrow_base; pattern_form.flap_through_base (base
across the seam); garment_reads.collar_pieces / fall_spring_reads; tests/test_fold_checks.py (convention + KAT).

## Commands ($S = /mnt/data/hifipushie/dress_garrett/shirt_round9; run.sh runs THIS worktree's code; PREPATH=$S/base/src
runs the base commit's code for before-reads)
./run.sh q3.py (flat spring), q4.py (fold rows validated: KAT + planted + r8), q5.py (where the fall's edge lies),
q6.py (jacket turn three ways), jrows.py (jacket r26g fold rows + spring reads). Round 8 scripts in shirt_round8/.
