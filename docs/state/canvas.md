# STATE: canvas (canvas / interfacing BENDING STIFFNESS; the jacket with no workaround holds) -- 2026-10-25 (s12)

GOAL (Joe): canvassed pieces keep their shape by STIFFNESS so the workaround holds go. No sim, no rented GPU.
Concept SLIM-CUT, worn open, falls straight (workspace/garrett_v20/concept_v8_front_apose.png). Rules: threads first
(C195); supports, not holds (C190); styling ends with smooth + pull down; current garments are not a baseline.
Sessions: s1 78507629; s2-s12 claude/canvas2-12 ($S12 /mnt/data/hifipushie/canvas/s12; history cloth.md "canvas
stiffness session 12"). Ledger C190-C218.
DEFAULT (C205 + C206): interfaced garments fitted keyed, shirt floor from relax1, no plumb hold, styled on the shirt's
own cloth WITHOUT bending (= s8's d2), the FIT sews patch stitches. C209's RULE is on wherever the one solve runs (the
threads' term >= the stiff cloth's median bending, STYLE_TF_PD_MEM 1); the STIFF STYLING itself is OPT-IN
(GP_STYLE_BEND=1, or =garment: canvassed garments only) until a render beats d2 beside the concept (coordinator
2026-10-25: e2's reads are worse than d2's). e3 = repo default on fit_d2 = d2 (cmp_e3_d2.log).
EARLIER (cloth.md s10 / s11): C211 shirt collar = the jacket collar's support (holds only with GP_STYLE_BEND=garment);
C212 the styling closes the break 64 -> 47 / 41; C214-C216 opt-in pressed levers (p5d: level with d2, not default);
C217 weight closes the front. s11 per-op: the first relax closes 9, the R TURN closes R while L opens.
S12 (the lapel FACE, C218; concept traced, face12.py, ovl_*.png):
| rows below HPS | 150 | 200 | 250 | 300 | 350 | face ends |
| concept L / R  | 62 / 62 | 51 / 53 | 39 / 44 | 27 / 37 | 14 / 25 | 386 (break) |
| d2             | 61 / 61 | 49 / 49 | 33 / 34 | 17 / 18 | 0 / 0 | 330 / 336 |
- The width at 150 matches; the LOWER lapel is missing: the worn break 365-370 vs 386 (buttons 379 / 496 vs 399 / 518;
  flat break_y 0.425 dates from fit round 9) and the roll's 15.5 mm band eats the lapel's last 35-42 mm above the break.
  Not the yaw (1-3 mm), not the draft's width. garment_reads.lapel_face_reads (in big_reads) + KATs.
NEXT (s12, in flight): b45 = break_y 0.425 -> 0.45 (repro12.py, fit + default styling) -> face / table reads + looks;
then the roll band near the break (rows taper to the break?), pattern_check / test_tailoring / Tess's coat on any draft
change; s11's NEXT (R turn asymmetry, first relax, a support at the roll) after.
