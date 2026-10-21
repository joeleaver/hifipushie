# STATE: dress_garrett_shirt (Garrett's shirt on its own, then under the round-26 jacket) -- 2026-10-20, shirt round 6

QUESTION (Joe 2026-10-20): "will all the lessons we learned on the jacket carry over and it won't take 30 rounds?"
Round 1: process carried, geometry didn't. Round 2: lessons made general (C103-C108). Round 3: base fit STUCK (C110).
Round 4: neck split (C113, opt-in), first-button rule (C114, off in v6). Round 5: CULL FIRST (C115), refused at preflight.
Round 6: NECKLINE FLAT CHECK (C116): hypothesis "the neckline is short for its neck" is WRONG. No code changed.
Jacket thread: docs/state/dress_garrett_fit.md (read-only here).
STATE (round 6, numbers in cloth.md "shirt round 6"): Simon got the BARE tape neck 406.5 mm (square, 2 cm up); flat
neckline 444.2 (front 125.4 + yoke 193.5 + front 125.3), stand neck edge 443.6. Book collar = neck + 10-15 mm (417-422):
ours is 22-27 mm LONGER. ANSUR base ring 430.8: ours +13.4 (the book's ease at the base). Seam strain on the form start:
front.R +1.4, yoke +4.3 (p50 -0.3, a few segments to 41 %), front.L -1.4 %. Seat: neck seam points at hps, CB 7.5 mm
under the base ring's CB. Over faces (whole 6.50 %): only 9 % within 15 mm of the neck seam; the YOKE is 31 % over,
median 39 mm off the seam, |x| 62-124, stretched along its DEPTH front-to-back over the shoulder (pattern |v| 0.93).
=> the start strain is a SHOULDER fault (yoke depth / shoulder seam position / slope over the trapezius), not neck girth.
Start over-limit unchanged: seen part 5.85 / 5.76 %, whole 6.50 % (preflight 3 %). No arrangement, no renders.
NEXT: (1) coordinator call: next hypothesis = the yoke's depth vs the body's HPS-over-shoulder length (flat: yoke depth +
front shoulder drop vs the body's surface length over the trapezius at |x| 60-125, front and back of the crest; and where
the shoulder seam sits vs the crest) -- the parked HPS research is the same question; (2) refit the jacket over THIS shirt
before any dressed render (the poke patches, round 5); (3) then arrange (seen5.py), first button, dress + review.

## Big reads (concept | r1 f1b | r2 f2b | r3 f3a | r4 r4b | r5 d5 (v6 fit, unarranged))
- V bottom below HPS: 60 | ~70-80 | 74 | 74 | 62.4 PASS | not re-read (v6 = r4b's neck).
- Collar points apart: 147 | 53 | 57 | 57 | 45 | ~45 FAIL (not arranged); below HPS 50-61 | 78 | 84.5 | 84.5 | 82 | ~82.
- First fastened button: 83 | 124 | 123 | 123 | 64 | v6 rule off (Simon even split, ~123) FAIL.
- Start over-limit (preflight 3 %): - | - | 10.1 % | 8.1 % | 7.2 % | seen part 5.85 / 5.76 % FAIL (r6: unchanged).
- Neckline flat (r6): 444.2 vs bare neck 406.5 + 10-15 (book) / base ring 430.8 + ease: LONG, PASS (not the fault).
- Cuff past jacket sleeve (17-23): - | - | - | - | - | 13.1 p50 (5.5-25) FAIL, both arms.
- Collar above jacket collar (11-23): CB 7.3, side 8.1 FAIL (unarranged).

## Spec sh_garrett v6 (spacing off; v5 no longer builds: "fold open neck.R ... 32 mm inside", round 4's roll revert).
Tests: 21 clothing files 301 passed, 2 skipped, 3 xfailed, exit 0.

## Commands (round 6 probes: shirt_round6/run.sh neck6.py | over6.py [form pkl]: flat vs worn neckline, over faces vs
the seam + stretch direction. $S = /mnt/data/hifipushie/dress_garrett/shirt_round5; run.sh runs THIS worktree's code)
VERSION=6 [HOLD=pieces] RUNNER=bin/capped ./run.sh seen5.py <tag> [submit] (fit cached form_v6.pkl -> seen part ->
pins: collar points 147 apart 55 below HPS, band ends + cfNeck out 20 mm -> job + preflight; submit runs local ZOZO);
probe_pre.py <tag> (over faces per piece, self pairs); RULE=margin|visibility ./run.sh dress5.py <tag> (asm + cuff /
collar measures); RUNNER=bin/capped ./run.sh render_d5.py $S/asm_<tag>.pkl <tag> wholefront,upper_front,collar,cuff.
