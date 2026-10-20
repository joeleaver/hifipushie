# STATE: dress_garrett_shirt (Garrett's shirt on its own, then under the round-26 jacket) -- 2026-10-20, shirt round 2

QUESTION (Joe 2026-10-20): "will all the lessons we learned on the jacket carry over and it won't take 30 rounds?"
Round 1: the process carried, the geometry didn't (jacket-only code). Round 2: lessons become GENERAL code first, then
the shirt. Jacket thread: docs/state/dress_garrett_fit.md (read-only here: the jacket is not changed by this thread).
STATE: steps 1-3 done (C103-C105, tests/test_garment_reads.py). Gate g2b FAILS on one flat row the new collar rule
found: collar_cover 2.3 mm (fall 49 vs stand 36.6 + roll 4 + turn 2.1; 5-25). Form reads (LATER at the gate): V 74
below HPS (45-75 ok), points 53 apart (127-167), first fastened button 124 (68-98), collar closed (spread).
NEXT: step 3b collarWidth 1.3 -> ~1.5 (fall ~56, cover ~10); step 4 colour (own-colour game-light render, stripe);
step 5 arranged open collar (arrange_garment); step 6 tucked / yoke / shoulders / placket / cuffs; step 7 renders.

## Big reads (concept, m1_ref.py at 1.147 mm/px; HPS = the body's hps.L)
- Front: closed, top button undone, 2nd done (83 mm below camera HPS). V bottom 60 below camera HPS. Collar points
  147 mm apart (73 / 73 off CF), 50-61 below the camera HPS. Tucked under a belt (belt top 498 below HPS).
- Colour LIT 173/169/167 #ada9a7 (R-B 6), shadow 158/154/152. Stripe not resolved (INFERRED pitch 2-3 mm, <= 4 %).
- Cuff 17-23 past the jacket sleeve; stand shows 11-23 above the jacket collar; placket 29 mm; buttons 88 apart.

## How the gates read it now (general code: src/hifipushie/garment_reads.py)
- workspace/checklists/garrett_shirt.json items with "read" + "range"/"equals"/"ref_rgb" + "on" = gate rows (C103).
- pattern gate: flat items judged; fit items shown (LATER) with the gate's own form reading; collar rules (C105).
- fit_garment's fit record: fit items judged on garment_reads.big_reads (C104); unread worn big reads UNMEASURED.

## Commands ($S = /mnt/data/hifipushie/dress_garrett/shirt_round2; run.sh runs THIS worktree's code)
RUNNER=/mnt/data/hifipushie/bin/capped ./run.sh gate2.py <tag> [save] [nojacket] -> gate_<tag>.json;
upd_checklist2.py (checklist machine targets). Round 1 scripts: ../shirt_round1 (fit3.py, render3.py, rev1.sh).
