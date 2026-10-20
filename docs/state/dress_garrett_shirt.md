# STATE: dress_garrett_shirt (Garrett's shirt on its own, then under the round-26 jacket) -- 2026-10-20, shirt round 1

QUESTION (Joe 2026-10-20): "another pass on the shirt ... the color isn't right ... will all the lessons we learned on
the jacket carry over and it won't take 30 rounds?" Round 1 = that test. Jacket thread: docs/state/dress_garrett_fit.md
(read-only here: the jacket is not changed by this thread).
STATE: step 1 DESCRIBE done (checklist workspace/checklists/garrett_shirt.json: 10 items "Joe 2026-10-20 shirt pass").
NEXT: step 2 flat pattern gate on model sh_garrett (fr24's shirt), big reads first.

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
$S/run.sh m1_ref.py (concept reads -> ref_reads.json); upd_checklist.py (checklist items).
