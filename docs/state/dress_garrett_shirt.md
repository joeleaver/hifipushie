# STATE: dress_garrett_shirt (Garrett's shirt on its own, then under the round-26 jacket) -- 2026-10-20, shirt round 2

QUESTION (Joe 2026-10-20): "will all the lessons we learned on the jacket carry over and it won't take 30 rounds?"
Round 1: the process carried, the geometry didn't (jacket-only code). Round 2 made the lessons GENERAL code (C103-C108)
then used them. Jacket thread: docs/state/dress_garrett_fit.md (read-only here).
STATE: round 2 stopped at the fit. Gate g2c PASS (collarWidth 1.5: cover 9.9). Fit f2b FAILS its own fit (C85):
collar points 57 apart (127-167), 84.5 below HPS (35-76), collar closed (spread), first fastened button 123 (68-98),
strain p99 17.2 drawn (yoke 34, back 29). PASS: front closed, V 74, tuck 6.0, collar button open, colour lit
+4.6/+4.7/+3.9 vs the concept (R-B 6.7). Arrangement a1 refused at preflight (the tucked start over-strained).
Blind review rev_f2b FAIL 6 MAJOR (round 1: 13). Jacket over the shirt NOT run (C85).
NEXT: (1) yoke / back strain first (the arrangement can't start over it): yoke 34 % was there untucked (round 1);
measure the yoke vs the shoulder slope before any lever; (2) tuck blend: the 30 mm fade reads as a peplum ring -> pull
only below the line + hide, or a longer fade; (3) then arrange the collar (arr2.py; neck pieces unheld); (4) Simon
button placement (first button 123 vs 83: its placket button options); (5) render4 diag column bug (mesh dropped when
the tuck culls faces) + the colour box on a shirt-only concept patch; (6) set the shirt's "stripe" and judge it.

## Big reads (concept | r1 f1b | r2 f2b)
- V bottom below HPS: 60 cam | ~70-80 | 74 PASS. Front: closed | closed | closed PASS. Collar button: open | open | open.
- Collar points apart: 147 | 53 | 57 FAIL; below HPS: 50-61 cam | 78 | 84.5 FAIL; state spread | closed | closed.
- First fastened button: 83 | 124 | 123 FAIL. Tuck stand-off: tucked | 12.6 (waist) | 6.0 PASS.
- Colour lit: 173/169/167 | 158/160/157 (clay rig) | 178/174/171 own colour, game light PASS. Strain p99: | 11.3 | 17.2.

## Gates now (general code)
- workspace/checklists/garrett_shirt.json items with "read" + "range"/"equals"/"ref_rgb" + "on" = gate rows (C103);
  garment key "checklist" binds them. Worn big reads on the form fit (C104). Fold family (C106) on every declared fold.

## Commands ($S = /mnt/data/hifipushie/dress_garrett/shirt_round2; run.sh runs THIS worktree's code)
RUNNER=bin/capped ./run.sh gate2.py <tag> [nojacket]; fit4.py <tag> (SHIRT_PATCH=json SAVE=1 RECORD=0) ->
asm_<tag>.pkl; arr2.py <tag> [pins k=v] (local ZOZO; do not wrap); render4.py <asm> <tag>; rev2.sh <tag>.
