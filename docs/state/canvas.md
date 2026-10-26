# STATE: canvas (canvas / interfacing BENDING STIFFNESS; the jacket with no workaround holds) -- 2026-10-25 (s8)

GOAL (Joe): canvassed pieces keep their shape by STIFFNESS so the workaround holds go. No sim, no rented GPU.
Concept SLIM-CUT, worn open, falls straight (workspace/garrett_v20/concept_v8_front_apose.png). Rules: threads first
(C195); supports, not holds (C190); styling ends with smooth + pull down; current garments are not a baseline.
Sessions: s1 78507629; s2-s8 claude/canvas2-8 ($S8 /mnt/data/hifipushie/canvas/s8; history cloth.md "canvas stiffness
session 8"). Ledger C190-C208.
DEFAULT (C205 + C206): interfaced garments fitted keyed, shirt floor from relax1, no plumb hold, styled on the shirt's
own cloth; the FIT sews patch stitch lines (C206 FIT_STITCH, on). d2 = $S8/fit_d2.pkl / asm_d2.pkl (repro.py d2).
S8 FINDINGS:
- (e) FIXED (C206): flap stitch gaps in the fit 10-58 -> <= 0.66 mm; styled flaps 10.4 / 9.7 -> 6.2 / 4.2 %; the
  flaps render as clean rectangles on their lines (check/cmp_d2_d1_wholefront.png).
- (a) CAUSE FOUND, FIX NOT DONE: not a fold (no front hinge past 90 deg, hingeprobe.py). The styling's threads-first
  ALTERNATION (bending round, 2 bending-free solves, cap, one-sided floor) walks the free canvassed fronts 24-65 mm
  forward (exp1 b1 / b12). C207 STYLE_TF_PD (opt-in GP_TF_PD=1 + GP_STYLE_BEND=1; threads band + shear lock as the
  local step): the FIRST relax holds the breaks (p7: 62 / 67); the FULL styling still tears (p8 threads p99 44 %,
  front.L 73 %).
- (b) C208 FIT_MADE_FLOOR (opt-in): poke 1152 -> 278 but collar threads 22.5 -> 35 % (m1). A trade-off (P29):
  suspect the jacket collar's draft is too small round the neck to ride over the shirt collar.
- Housekeeping done: cloth_tools / cloth_construction / cloth_design say open = styling, a sim = wrinkle source.
RUNS (concept edge 450/550/650 71/78/94, hem+30 482, front len 748; threads = pooled p99 (fronts; collar)):
| d1 (s7 default) | 66-46 / 80-67 / 106-93 | 498 | 729 | 6.46 (4-5; 15.2) |
| d2 (C206, DEFAULT) | 52-50 / 65-72 / 90-105 | 471 | 735 | 7.64 (4.0; 22.5) |
| m1 (d2 + C208 + UNDER_MADE) | 58-50 / 73-73 / 102-107 | 477 | 723 | 13.29 (4.8; 35.1) |
| p8 (d2 fit, C207 styling) | 87-102 / 75-91 / 94-105 | 468 | 725 | 44.2 (60; 23.4) |
LOOK d2: same jacket as d1 apart from the flaps: V too wide / deep, lapels narrow, gorge tabs, cutaway fronts.
No blind review (edge rows not within +-8 mm).
SUITE (18 files): 314 passed, 4 xfailed, PYTEST_EXIT 0 ($S8/suite.log). First run 1 red ($S8/suite_r1.log): FIT_STITCH sewed
  wf_simon's button stitches (threads 6.5 -> 7.4 %); fit_sew now closes PATCH stitches only (the jacket: all 10 are).
NEXT (in order; scripts in $S8: exp1.py <fit> <tag> <N | ops.json[:N]>, style.py <fit> <tag>, rd.sh <tag>, post.sh
<tag> + sheet.py <tag>c <out>, repro.py <tag>):
1. (a) Find the op that tears under C207: copy s6/perop.py, run per op on fit_d2 with GP_STYLE_BEND=1 GP_TF_PD=1,
   threads per piece after each op. Suspect grips (slide / turn / pull fixed sets): under the PD local step a gripped
   face's neighbours get only the band, no pull toward a rotation; try SHEAR_STIFF higher only on faces touching a
   fixed vertex, or the old local step inside grip ops. Goal: full styling threads <= d2's 7.6 with breaks held.
   Then a KAT: a canvassed curved panel (rest = moulded) free on a sphere floor keeps its place in a relax.
2. (b) Measure the jacket collar's neck-edge length vs the shirt collar's outer ring at CB (seamlen.py / collen.py in
   s6); if short, fix the draft, then FIT_MADE_FLOOR on.
3. (c) flare / hem 471 vs 482 / length 735 vs 748; (d) bulge; (f) C200's KAT.
4. Looks when something changes visibly (wholefront, upper_front, side; concept | new | d2 clay + diag); blind review
   at +-8 mm of 71 / 78 / 94.
