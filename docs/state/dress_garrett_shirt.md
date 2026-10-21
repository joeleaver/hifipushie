# STATE: dress_garrett_shirt (Garrett's shirt on its own, then under the round-26 jacket) -- 2026-10-20, shirt round 5

QUESTION (Joe 2026-10-20): "will all the lessons we learned on the jacket carry over and it won't take 30 rounds?"
Round 1: process carried, geometry didn't. Round 2: lessons made general (C103-C108). Round 3: base fit STUCK (C110).
Round 4: neck split (C113, opt-in), first-button rule (C114, off in v6). Round 5: CULL FIRST (C115), approach change.
Jacket thread: docs/state/dress_garrett_fit.md (read-only here).
STATE: step 1 BUILT (general, KAT, C115): cloth_release.from_form(cover=<over garment as worn>, res=) arranges only the
SEEN part (cloth_layers.seen_part: visibility rule = the end state's cut + 30 mm, or the round-24 margin rule; made
pieces whole when in view; below the tuck line dropped; cut edge PINNED, job "cutIdx"). Step 2 REFUSED at the
unloosened preflight: kept-start over-limit 5.85 % (margin) / 5.76 % (visibility) vs 3 % (whole shirt 6.6 %). The
over cloth is the yoke + front tops 0-20 mm below HPS, |x| 55-140, AT the visible neckline: culling can't remove it.
Stop-loss hit (2 levers). Steps 3 not run (no spread). Step 4: dressed renders of the UNARRANGED v6 shirt under r26k:
NOT forwardable: large shirt patches poke through the jacket chest / shoulders (r26k was fitted over an older shirt;
the v6 shirt stands proud of it there, > PIERCE_CULL 15 mm), collar standing closed. Blind reviews not run on them.
NEXT: (1) the neck/shoulder start strain is the fit's (C110 relax1 yoke; C113): the remaining fault, not culling;
coordinator call on HPS landmark research (parked) vs a seen-part relax on the form (cut edge pinned) as the fix;
(2) refit the jacket over THIS shirt (or a layer-order pass) before any dressed render: the poke patches;
(3) then arrange (seen5.py, pins below), re-read first button (step 3), dress + review.

## Big reads (concept | r1 f1b | r2 f2b | r3 f3a | r4 r4b | r5 d5 (v6 fit, unarranged))
- V bottom below HPS: 60 | ~70-80 | 74 | 74 | 62.4 PASS | not re-read (v6 = r4b's neck).
- Collar points apart: 147 | 53 | 57 | 57 | 45 | ~45 FAIL (not arranged); below HPS 50-61 | 78 | 84.5 | 84.5 | 82 | ~82.
- First fastened button: 83 | 124 | 123 | 123 | 64 | v6 rule off (Simon even split, ~123) FAIL.
- Start over-limit (preflight 3 %): - | - | 10.1 % | 8.1 % | 7.2 % | seen part 5.85 / 5.76 % FAIL.
- Cuff past jacket sleeve (17-23): - | - | - | - | - | 13.1 p50 (5.5-25) FAIL, both arms.
- Collar above jacket collar (11-23): CB 7.3, side 8.1 FAIL (unarranged).

## Spec sh_garrett v6 (spacing off; v5 no longer builds: "fold open neck.R ... 32 mm inside", round 4's roll revert).
Tests: 21 clothing files 301 passed, 2 skipped, 3 xfailed, exit 0.

## Commands ($S = /mnt/data/hifipushie/dress_garrett/shirt_round5; run.sh runs THIS worktree's code)
VERSION=6 [HOLD=pieces] RUNNER=bin/capped ./run.sh seen5.py <tag> [submit] (fit cached form_v6.pkl -> seen part ->
pins: collar points 147 apart 55 below HPS, band ends + cfNeck out 20 mm -> job + preflight; submit runs local ZOZO);
probe_pre.py <tag> (over faces per piece, self pairs); RULE=margin|visibility ./run.sh dress5.py <tag> (asm + cuff /
collar measures); RUNNER=bin/capped ./run.sh render_d5.py $S/asm_<tag>.pkl <tag> wholefront,upper_front,collar,cuff.
