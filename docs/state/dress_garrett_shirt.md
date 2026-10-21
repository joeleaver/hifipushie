# STATE: dress_garrett_shirt (Garrett's shirt on its own, then under the round-26 jacket) -- 2026-10-21, shirt round 8

QUESTION (Joe 2026-10-20): "will all the lessons we learned on the jacket carry over and it won't take 30 rounds?"
Rounds 1-7: process carried, geometry didn't; C103-C117 (seen part first C115, neckline flat C116, chord slope C117).
Round 8: gate PASS on the chord draft (C118: collar roll 6 mm), start_over 0.06 (coordinator; jacket's rule), the
ARRANGEMENT RAN; first button + V now pass (roll drafted from the V); the collar SPREAD is stuck (C120), reviews FAIL.
Jacket thread: docs/state/dress_garrett_fit.md (read-only here).
STATE (round 8, numbers in cloth.md "shirt round 8"): sh_garrett v8 (v7 collar roll 6 mm + collarWidth 1.61; v8
first button 0.047 below cfNeck, under front's open-neck roll button1 + 30). Gate PASS (no waivers). Form fit p99 11.4.
Seen job s8c: start over-limit 5.20 % (yoke 433, front.L 233, back 168, front.R 135 faces) with zozo start_over 0.06
(job_settings.json carries the reason); the seen job's extra over the form (969 vs 754) is the START CLEAN-UP (moves
<= 5 mm), not pins or cut. Arranged keep=True ("placed by hand", springback <= 2 mm). Local ZOZO only: $0.
Collar: the made fall rests as placed, turned 123 of 180 deg on the form: it flares up like a funnel; pins stop 24-34
mm short; band-end pins 20 -> 35 mm moved the points 86.4 -> 87.5 (dead). fold_on_base unvalidated on a two-piece
collar (C119: reads 0.8 "through" on the known-good closed start too).
Reviews (a8c, shirt alone): collar FAIL (stands straight up, points tiny, wide shallow V, puffy fronts); wholefront FAIL
(collar funnel; boxy; the composite drew the tucked cloth: render fault). Step 4 (jacket refit + dressed) NOT run.
NEXT: (1) the open made collar from the CONSTRUCTION: the form builds stand + fall open and turned (fall on the stand,
fold_turn ~180, points out), then the arrangement only settles it (C120); (2) fix fold_on_base for a flap on another
piece (C119) and validate it on the closed start first; (3) render composites without the cloth below the tuck line;
(4) then jacket refit over this shirt (B) and the dressed renders + cuff / collar-above measures.

## Big reads (concept | r4 r4b | r7 (chord, unarranged) | r8 s8c (arranged, keep))
- V bottom below HPS: 60 | 62.4 | 62.1 (form) | 74.1 PASS (band 45-75).
- Collar points apart: 147 | 45 | 47.8 | 87.5 FAIL. Below HPS 50-61: 82 | not arranged | 65.8 PASS (band 35-76).
- First fastened button: 83 | 64 | 111 | 77.3 PASS (band 68-98).
- Start over-limit: - | 7.2 % | seen 5.03 % | seen 5.20 % (start_over 0.06, local limit, past 0).
- Fall cover over the stand (flat): 10-15 Aldrich | - | 9.9 | 10.0 PASS; fold_turn_allowance collar 4.2 -> 6.3 PASS.
- Fold family on the arranged collar: twist 6.1 PASS; turn 122.8 (declared fold-over 180) ; on_base unvalidated.
- Cuff past jacket sleeve (17-23) / collar above jacket collar (11-23): not re-measured (step 4 not run; r5 13.1 / 7-8).

## Spec sh_garrett v8. Code this round: cloth_designs.json simon collar roll offset 0.006 (C118). Main merged (measure
audit: definition_holds keep the shirt's old values; none lifted). Tests (21 files + test_measure_defs, bin/capped): 321 passed, 4 skipped, 4 xfailed, exit 0.

## Commands ($S = /mnt/data/hifipushie/dress_garrett/shirt_round8; run.sh runs THIS worktree's code)
./run.sh gate8.py <tag> -> gate_<tag>.json (rows.py prints it); RUNNER=bin/capped ./run.sh fit8.py <tag> -> form_<tag>.pkl
+ the fit record; FORM=<pkl> BAND_OUT=.. KEEP=1 RUNNER=bin/capped ./run.sh seen8.py <tag> [submit] (seen part + pins +
start_over 0.06 + over-limit by region; submit: local ZOZO -> arranged_<tag>.npz); FORM=<pkl> ./run.sh reads8.py <tag>
(big reads + fold rows); RUNNER=bin/capped ./run.sh render8.py <seen tag> <tag> [views] (JACKET=<asm pkl> dressed).
Renders: $S/check/{wholefront,collar,placket}_a8c.png (ref | clay | diag | own); reviews rev_collar_a8c, rev_whole_a8c.
