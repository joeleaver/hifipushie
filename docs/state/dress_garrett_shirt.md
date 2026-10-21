# STATE: dress_garrett_shirt (Garrett's shirt on its own, then under the round-26 jacket) -- 2026-10-21, shirt round 9

QUESTION (Joe 2026-10-20): "will all the lessons we learned on the jacket carry over and it won't take 30 rounds?"
Rounds 1-7: process carried, geometry didn't (C103-C117). Round 8: gate PASS, arrangement ran, first button + V pass;
collar spread stuck (C120). Jacket thread: docs/state/dress_garrett_fit.md (read-only here).
ROUND 9 (notes cloth.md "shirt round 9"; $S/notes_s*.md):
- "Fall turned 123 of 180" was the READ (C121): fold_turn judged turn against the ANGLE, took angle 0 as unset, read
  mean normals. In section: shirt collar 162-167 PASS; jacket collar 175 (normals said 13). C119 closed (stand = base).
- The funnel is the DRAFT first (C122): the fall was a straight band, 115 mm short of its landing path. cloth.spring_fall
  springs any stand + fall collar's fall to that path (568.9 vs 567.5); gate row collar_fall_spring; flat KAT.
- ...and the FORM second: sprung form k9a still hangs as a tube (edge 9 mm out at the sides, r8 4.5; gaps 6-15 mm):
  folds.apply turns the flap rigidly about the roll, the extra length ripples. Two levers' worth of evidence: measure /
  change the form's turn next, not the draft.
- Torn corners (Joe, a8c; C123): collar_corner_reads FAILs a8c (right band end 31 %, fall's right sewn end 22 %, right
  point 10 %), PASSes the form (<= 6.7 %). Cause: single-vertex arrangement pins on the right. Row collar_corners.
NEXT: (1) the form lays the turned fall onto what is under it (stand, then body / shoulders), KAT: stand + sprung fall
on a cylinder neck WITH shoulders, fall >= 170 over the stand, edge on the shoulders; (2) arrangement with pins spread
over a patch, no band-end pins (collar_corners PASS); (3) renders shirt alone, tuck line masked (render9.py TUCK) +
point close-ups per side; reviews; (4) jacket refit. Gate g9b predates the fold_turn_allowance curved-line fix: rerun.

## Big reads (concept | r8 s8c (arranged, keep) | r9 k9a (sprung, closed form, unarranged))
- V bottom below HPS: 60 | 74.1 PASS (band 45-75) | closed (not arranged)
- Collar points apart: 147 | 87.5 FAIL | 33.0 (closed). Below HPS 50-61: 82 | 65.8 PASS | 81.3 (closed)
- First fastened button: 83 | 77.3 PASS | -
- Collar turn over the stand (in section, C121): 180 +- 35 | 162 PASS | (row on k9a: see f_k9a.log)
- Fall outer edge vs landing path (flat): >= need - 6 | 453.8 vs 568.9 FAIL | 568.9 vs 567.5 PASS
- Fall edge out from the neck seam at the sides (form): on the shoulders | 4.5 mm | 9.0 mm (still a tube)
- Collar corners strain max (C123): <= 10 % | 31.0 FAIL (right band end) | form <= 6.7 (k8b); k9a not read
- Cuff past jacket sleeve (17-23) / collar above jacket collar (11-23): not run

## Jacket r26g fold rows (C121 changes reads only): collar roll 13.4 "PASS vs 10" -> 174.9 PASS vs 170; lapels 112 / 128
FAIL vs "15" -> 158 / 163 PASS vs 165. Draft op skipped for the jacket (collar_two_piece solves its own). j_*.log.

## Tests: 22 files (21 clothing + test_measure_defs, bin/capped): 292 passed, 8 skipped, 4 xfailed, exit 0 (tests_r9.log).

## Commands ($S = /mnt/data/hifipushie/dress_garrett/shirt_round9; run.sh runs THIS worktree's code; PREPATH=$S/base/src
for the base commit's code). q3 flat spring; q4 fold rows validated; q5/q5b where the fall's edge lies; q6 jacket turn
3 ways; q8/q9 collar corners; jrows jacket rows; gate9 / fit9 (form_k9a.pkl) / seen9 / reads9 / render9 (tuck mask).
