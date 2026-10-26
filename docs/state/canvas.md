# STATE: canvas (canvas / interfacing BENDING STIFFNESS; the jacket with no workaround holds) -- 2026-10-25 (s10)

GOAL (Joe): canvassed pieces keep their shape by STIFFNESS so the workaround holds go. No sim, no rented GPU.
Concept SLIM-CUT, worn open, falls straight (workspace/garrett_v20/concept_v8_front_apose.png). Rules: threads first
(C195); supports, not holds (C190); styling ends with smooth + pull down; current garments are not a baseline.
Sessions: s1 78507629; s2-s10 claude/canvas2-10 ($S10 /mnt/data/hifipushie/canvas/s10; history cloth.md "canvas
stiffness session 10"). Ledger C190-C213.
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
NEXT (in order; scripts in $S10: perop9 / opcol9 / yaw10 / lean10 / sm10 / cap9 / repro.py / post.sh / sheet.py):
1. The fronts close in every styling solve because nothing holds an open front open (no gravity in relax / smooth /
   pull; ARAP relaxes the form's opening). Find the support: hang the fronts from the shoulders in the first relax
   (hang over the whole front, not only below the break) or the stiff styling's bending rest at the FIT shape for the
   lapel + chest canvas only; read the break per op (target 64 held) and yaw10 (lapel facing front).
2. With the break held, re-run u2 (shirt collar floor + C209) and read the lapel / hem / side bulge; if the side bulge
   persists, it is the stiff styling's (pd10 had it too): per-op side profile (fwd33) to name the op.
3. Gorge tabs + stand flare at 110 deg: the lapel roll pulling the stand top out; measure the roll line's 3D path from
   the break to CB against the neck before any draft change; R30 only with the fall drafted from a straightened roll.
4. Hem (456-477 vs 482) and 650 edge after 1-2.
