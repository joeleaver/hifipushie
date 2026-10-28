# STATE: hang, round 2 (the fit hangs from its supports; threads hard) -- 2026-10-28, ledger C244

GOAL (Joe 2026-10-27: "We're still getting wings on the side ... that and the disconnected sleeves are the main
things"): a HANG step in the default fit: cloth hangs from its supports under its weight, rests on the body only where
it touches it from above; nothing drawn into hollows. Threads hard (C235).
PASS (default path): C242 gates (wings <= 20, sleeve top gap <= 10, apex <= 8, hollow <= 10 mm) on hoodie t6, tee t5,
shirt t7, jacket gc_garrett; threads past cap p99 <= 1 %; inside ~0; fit tests no new failures.

STATUS: gates PASS on all four; threads PASS on three (jacket 3.84 %, base 7.0); TWO NEW TEST FAILURES (the hang KATs,
below). Branch worktree-agent-aa9989e1d90fd4ff9, merged with threads-hard (C243, BUILD 21) -> BUILD 22.

THE STEP (pattern_form, HANG_ON_FORM: on for every on_form fit; garment "hang": false opts out; assemble() direct keeps
HANG_FIELD off): seat onto body facing well up only (HANG_SEAT_UP 0.5), NO let-go (HANG_FROM_SEAT), the weight (HANG_G
0.3, 200 rounds) against hard contact; supports = contact on body with n_z > HANG_UP 0.5, anchored where they came to
rest (HANG_ANCHOR, HANG_HOLD 1000); shoulder point unpinned (HANG_FREE_SHOULDER); lengths 10x the weight's pull
(HANG_STIFF, from round HANG_STIFF_FROM 0); 10 hard sweeps a round; refactor when 50+ supports change. STYLE_HARD: the
wear's styling ends threads-hard (hard_threads), not for a garment over another. hang_reads.HANG_STEP True (rows are the
pattern's, PATTERN_FIX). Read fixes: sleeve stations go round the arm; wings below the armhole bottom; knit band caps
reported vs the drafted pattern. Each with its evidence in the code comments.

MEASURED on merged code (/mnt/data/hifipushie/hang2/results.jsonl tags *_m1 vs *_base; wings / sleeve top / apex /
hollow mm, past cap %, fit s):
  hoodie 46 F / 16.5 F / 10.8 F / 0, 16.2, 470   ->  1.5 / 8.9 / 7.3 / 0, 0.67, 105
  tee    8.5 / 13.5 F / 3.4 / 0, 0.76, 218        ->  6.5 / 5.8 / 3.0 / 0, 0.10, 63
  shirt  29.5 F / 7.5 / 4.5 / 33 F, 5.2, 418      ->  18.5 / 3.8 / 4.1 / 6.3, 0.22, 277 (styled)
  jacket 9.5 / 8.1 / 6.0 / 17.4 F, 7.0, 872       ->  10.5 / 7.6 / 6.7 / 0, 3.84 F (fit 1.81), 912 (incl. the shirt)
  inside: hoodie 0, tee 0, shirt 4 (0.7 mm), jacket 3 (1.1 mm).
RENDERS (base top row, hung bottom; /mnt/data/hifipushie/hang2/renders/{hoodie,tee,shirt,jacket}_ab.png), my look:
wings gone, sleeves hang on the arms, hems clear the legs and seat, the jacket's back no longer under the seat. NEW
faults: shirt / tee / hoodie fronts read the chest (the shirt also the abs, its back the seat) through the cloth: the
weight's tension draws them taut; hoodie shoulder points still poke (under the gate); jacket lapels less defined,
shirt show-through specks on the jacket (as before).

TRADE-OFFS / OPEN (numbers, nothing loosened):
1. tests/test_pattern_form.py test_hang_sheet_falls_plumb FAILS: the towel started 30 deg tilted ends 22 mm off plumb,
   hems 35-46 mm high (needs <= 12 / 10). Cause: the local-global solve with stiff lengths also holds directions (big
   rotations go HANG_STIFF x slower) and anchors keep where the cloth first landed. Settings that pass its geometry (no
   anchors, stiff 1, refactor always, 30 sweeps: 5-7 mm, hems +-3) leave the hoodie 6.7 % past cap (hd_k1). A stiffness
   ramp (HANG_STIFF_FROM 0.5 / 0.8) took the tilt to 4 mm but left the hems 15-38 mm high. Not solved.
2. test_hang_sleeve_tube FAILS on threads only: p99 2.0 % = the hard cap (FIT_THREAD_CAP) vs its pre-C235 1.5 %; the
   geometry passes (top gap 3.0, bottom 47-68 mm). Coordinator: restate to the cap, or keep.
3. Jacket threads past cap 3.84 % (styling: fronts / flaps / stand); its fit 1.81 (stand 25 %). hard_threads on it made
   it worse (no layer rules: 36 inside, apex 8.4), so STYLE_HARD skips layered garments.
4. Chest / seat read through the hung fronts: next lever the weight vs bending (HANG_G 0.3 was the least that hung the
   tee's sleeve on the arm: 0.1 left 10-11 mm).
5. Hoodie rib cuffs read 13 % past cap (all-face p99 passes).
TESTS (/mnt/data/hifipushie/hang2/tests_d1.log): 99 passed, 3 xfailed, 5 failed = the 3 known fold KATs + the 2 above.
NEXT (coordinator): decide 1-2 before merging; then a blind trial on the hung fit.
