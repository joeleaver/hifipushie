# STATE: dress_garrett_shirt (Garrett's shirt on its own, then under the round-26 jacket) -- 2026-10-20, shirt round 1

QUESTION (Joe 2026-10-20): "another pass on the shirt ... the color isn't right ... will all the lessons we learned on
the jacket carry over and it won't take 30 rounds?" Round 1 = that test. Jacket thread: docs/state/dress_garrett_fit.md
(read-only here: the jacket is not changed by this thread).
STATE: round 1 stopped at step 3. Flat gate PASS (g1a); fit alone FAILS: f1b (OPEN_SPREAD off, kept) strain p99
11.3 (yoke 34.7), waist stand-off 12.6, collar points 53 mm apart vs 147, V closes ~70 below camera HPS vs 60; f1a
(OPEN_SPREAD on) tore the collar (p99 149-182 %): DEAD. Blind review rev_f1b FAIL (13 MAJOR). Step 4 NOT run (C85).
Colour: lit 158/160/157 vs concept 173/169/167 (cool, dark) under the clay rig; the old harness drew #c9ccd2.
NEXT: (1) the collar: fall turned down on its fold + points out (cfNeck moved with the stand ends, or an arranged
open collar C81) -- the biggest read; (2) placket lap twisted into an X under the V (diag); (3) yoke strain 34.7 %;
(4) tuck as a design key (gap); (5) colour on a game-light render; then step 4 with r26k.

## Big reads (concept, m1_ref.py at 1.147 mm/px; anchors: image CF = button line x 626, neck = stand top at side)
- Front: closed, top button undone, 2nd done (83 mm below camera HPS). V bottom 109 below the stand top at the side
  (60 below camera HPS). Collar points 147 mm apart (73 / 73 off CF), 98-109 below the stand top.
- Colour LIT (painted sRGB, 60-90th lum pct) 173/169/167 #ada9a7, shadow 158/154/152. Stripe NOT resolved at the
  concept's scale (contrast < 1 %): INFERRED pitch 2-3 mm, contrast <= 4 %.
- Cuff shows 17-23 mm past the jacket sleeve. Tuck: belt top 498 below camera HPS.
- Details: shirt shows 11-23 mm above the jacket collar at the sides; box placket 29 mm, buttons 88 mm apart.

## Method (the loop that works, Joe 2026-10-20)
describe -> flat gate (big first, C52) -> fit ALONE on the form worn as designed (OPEN_SPREAD C50, LAP_LAYER C82,
tucked) with its own fit record (C85) -> ref | clay | diag + colour render, blind one-view reviews -> only then the
r26k jacket over it (B cull) and the shirt judged where it shows.

## Commands ($S = /mnt/data/hifipushie/dress_garrett/shirt_round1; run.sh runs THIS worktree's code)
$S/run.sh m1_ref.py (concept reads); gate1.py <tag> (MCP pattern_check); RUNNER=bin/capped ./run.sh fit3.py <tag>
[K=V pf overrides; RECORD=0] -> asm_<tag>.pkl; render3.py <abs asm> <tag>; strain.py; colour.py; rev1.sh <tag>.
