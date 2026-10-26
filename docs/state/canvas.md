# STATE: canvas (canvas / interfacing BENDING STIFFNESS; the jacket with no workaround holds) -- 2026-10-25 (s11)

GOAL (Joe): canvassed pieces keep their shape by STIFFNESS so the workaround holds go. No sim, no rented GPU.
Concept SLIM-CUT, worn open, falls straight (workspace/garrett_v20/concept_v8_front_apose.png). Rules: threads first
(C195); supports, not holds (C190); styling ends with smooth + pull down; current garments are not a baseline.
Sessions: s1 78507629; s2-s11 claude/canvas2-11 ($S11 /mnt/data/hifipushie/canvas/s11; history cloth.md "canvas
stiffness session 11"). Ledger C190-C214.
DEFAULT (C205 + C206): interfaced garments fitted keyed, shirt floor from relax1, no plumb hold, styled on the shirt's
own cloth WITHOUT bending (= s8's d2), the FIT sews patch stitches. C209's RULE is on wherever the one solve runs (the
threads' term >= the stiff cloth's median bending, STYLE_TF_PD_MEM 1); the STIFF STYLING itself is OPT-IN
(GP_STYLE_BEND=1, or =garment: canvassed garments only) until a render beats d2 beside the concept (coordinator
2026-10-25: e2's reads are worse than d2's). e3 = repo default on fit_d2 = d2 (cmp_e3_d2.log).
S10 FINDINGS (no default changed, no code changed):
- Shirt collar at the back (C211): the styling's first relax, TURN and hem pull + relax drag the unsupported collar ring
  forward / down (stand top at CB r 77.7 -> 68.6, 389 shirt verts over). The shirt collar is its support: GP_UNDER_MADE
  =1 alone tears the collar at CB in the pull (35.7 %); with GP_STYLE_BEND=garment (C209) it holds (u2: collar 13.8 /
  stand 13.2 %, shirt poke 84 vs d2 1152). The fix exists but only with the stiff styling, which loses elsewhere.
- Lapel (C212): the FIT is right (roll 150 73, break 64); the STYLING closes the break 64 -> 47 / 41 (relax -11,
  smooth -4, pull -4; the slide refused at step 0) and turns the lapel faces 11-26 deg sideways (r32 0). Stiff styling
  holds the relax only. "Break high" = the flap's last row; the break vertex sits 365-370 (concept 386).
- Stand at the side (C213): the draft's top = neck CB..notch (0 %), but the side flare (+12 mm out at 110 deg) is where
  the top is already short: the lapel roll pulls it. R30 cone-lean prototype parked ($S10/stand_lean_r30.patch: breaks
  the fall's spread solve + the gc_garrett build).
RUNS (concept edge 450/550/650 71/78/94, hem+30 482, len 748, lapel 150 127-134, V 237):
| d2 (default) | 52-50 / 65-72 / 90-105 | 470 | 735 | lapel 122 V 209 | threads 7.64, shirt poke 1152 |
| u1 (UNDER_MADE) | 60-50 / 76-74 / 109-110 | 477 | 722 | 126/122 V 215 | 11.35 (collar 25.2), poke 349 |
| u2 (UNDER_MADE + STYLE_BEND=garment) | 58-60 / 88-68 / 107-66 | 456 | 728 | 116/115 V 195 | 8.31, poke 84 |
LOOK u2 vs d2 ($S10/check/cmp_u2_d2_*.png): collar better; lapels a touch narrower, hem asymmetric, side view bulges
at the pocket and tucks in at the hem (d2 straighter). u2 does not earn the default. No blind review.

S11 FINDINGS (no default changed; three OPT-IN levers, all off = d2 exactly):
- The stiff styling's bending rest already WAS the fit's shape. New: C214 SMOOTH_PRESSED (GP_SMOOTH_PRESSED=1; KAT),
  C215 SMOOTH_HAND (GP_SMOOTH_HAND=4: the smooth takes ripples, not the wrap), C216 PRESSED_REST (GP_PRESSED_REST=1:
  canvassed faces' rotation targets rest on the fit's pressed triangle). C217: the weight (GP_STYLE_HANG=1) CLOSES
  the front (p3 48 / 30): dropped.
- Best: p5d (all three, no bending): break 56 / 45 (d2 47 / 41, fit 64), threads 5.97, hem 486, lapel faces front
  (yaw +4), shirt poke 583; but length 724 (748), edge 650 107-109 (94), lapel 122 / 120 (127-134). LOOK: level with
  d2, not better (check/cmp_p5d_d2_*.png). Stiff styling (p4) loses the lower front again (650 72 / 70, hem 450).
- Per op (p5d): the first relax still closes 9, the R TURN closes R 2 while L opens 9, smooth -4, pull -3.
NEXT (in order; scripts in $S11: go*.sh, perop9, sm11 / smw11 (re-run a captured op), rd.sh, yaw10, post.sh, sheet.py):
1. The R turn: turn L opens the break +9, R closes it -2 (p5d; the same in every run). Read turn's R grip / axis
   (front.R:break..sideF.b) against L's on the fit: an asymmetric input, before any new lever.
2. The first relax (-9 even pressed): per-face read of which faces spring back (canvas vs plain lower front); a
   support at the roll line (the lapel's roll held by its pressing against the chest), not weight (C217).
3. Lapel 120-122 vs 127-134 is NOT the break alone (p5d break +9, lapel unchanged): read the lapel's outer edge vs the
   roll (lapel29) on fit_d2 vs p5d: the flap's width itself.
4. If 1-3 reach break ~60 and length / 650 hold: p5d family as the default candidate (shirt photo / trace rows and Tess's
   coat must pass: SMOOTH_HAND touches every smooth, the pressing touches fused pieces at share 0.37).
SUITE s11 (18 files): 316 passed, 4 xfailed, PYTEST_EXIT 0 ($S11/suite.log); flags off = d2 (max 0.00004 mm, asm_e0).
