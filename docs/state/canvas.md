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
- FIX (C219 + draft): gc_garrett v7 = lapel break_y 0.425 -> 0.44 + roll_converge 0.08 (folds "converge": the roll's
  rows close onto the line at the break). bc44 (= the new default): face 59 / 47 / 32 / 18 / 8 (R 61 / 50 / 36 / 20 / 10),
  ends 366 / 376, break vertex 376 / 385, lapel pt 94-101, outer 150 125-126, V200 218, edge 450 57 / 50, 550 70 / 70,
  650 95 / 101, hem 481, len 729, threads p99 5.75 (d2 7.64). Gate PASS_WAIVED (3dfe339c, the default's waivers, no new
  row). LOOK (check/cmp_bc44_d2_*): lapels run to the break, V longer, L / R even; >= d2 -> DEFAULT (spec v7). No blind
  review (edge 450 -14 / -21 outside +-8). break_y 0.45 broke the collar's placement (not chased).
  NOTE: the spec's shirt carries a stray key "source_probe" (probe_garrett 2026-10-22) that fails cloth.validate: v7 was
  saved checked=False after validating the edit with that key dropped; main's code ignores roll_converge until merged.
SUITE s12 (18 files, spec v7): 319 passed, 4 xfailed, PYTEST_EXIT 0 ($S12/suite.log).
NEXT: (1) the face from 250 down is still 7-17 mm narrow (300: 18-20 vs 27-37): the lapel taper (width at the point 81,
  belly 10 @ 0.4) vs the concept's straighter, wider lower lapel; try belly_at lower / more belly on the form, read with
  lapel_face_reads. (2) The faces read flat: the concept's edge line is a shadow at the lapel's thickness / lift off the
  forepart (render RTHICK lapel 2.2 mm): read the lapel's stand-off at its outer edge. (3) Front length 729 vs 748 and
  edge 450 57 / 50 vs 71. (4) s11's NEXT: R turn asymmetry, the first relax, a support at the roll line.
