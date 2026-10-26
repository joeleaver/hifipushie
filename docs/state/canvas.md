# STATE: canvas (canvas / interfacing BENDING STIFFNESS; the jacket with no workaround holds) -- 2026-10-26 (s14)

GOAL (Joe): canvassed pieces keep their shape by STIFFNESS so the workaround holds go. No sim, no rented GPU.
Concept SLIM-CUT, worn open, falls straight (workspace/garrett_v20/concept_v8_front_apose.png). Rules: threads first
(C195); supports, not holds (C190); styling ends with smooth + pull down; current garments are not a baseline.
Sessions: s1 78507629; s2-s14 claude/canvas2-14 ($S14 /mnt/data/hifipushie/canvas/s14; history cloth.md "canvas
stiffness session 14"). Ledger C190-C224.
DEFAULT (C205 + C206): interfaced garments fitted keyed, shirt floor from relax1, no plumb hold, styled on the shirt's
own cloth WITHOUT bending (= s8's d2), the FIT sews patch stitches. C209's RULE is on wherever the one solve runs; the
STIFF STYLING is OPT-IN (GP_STYLE_BEND=1 / =garment). C211-C217 (s10 / s11): opt-in pressed levers, findings.
S12: C218 lapel FACE read (garment_reads.lapel_face_reads); C219 roll_converge; v7 = break_y 0.44 + roll_converge 0.08.
S13 (spec v10 = DEFAULT r20 = v9 b20 + collar run_off; v8 = shirt `source_probe` -> `probe_source`, saves checked again):
| face below HPS | 150 | 200 | 250 | 300 | 350 | break | edge 450/550/650 | hem | len | thr p99 |
| concept L ; R | 62 ; 62 | 51 ; 53 | 39 ; 44 | 27 ; 37 | 14 ; 25 | 386 | 71/78/94 | 482 | 748 | |
| bc44 (v7) | 59 ; 60 | 47 ; 49 | 32 ; 35 | 18 ; 18 | 7 ; 9 | 365/375 | 57-50/70-70/95-101 | 481 | 729 | 5.75 |
| b20 (v9) | 63 ; 63 | 54 ; 54 | 42 ; 44 | 31 ; 32 | 18 ; 20 | 376/379 | 59-50/73-69/103-103 | 480 | 725 | 6.39 |
| r20 (v10) | 62 ; 62 | 54 ; 53 | 41 ; 43 | 28 ; 29 | 17 ; 18 | 374/376 | 61-49/74-67/98-97 | 486 | 728 | 5.55 |
- C220: the lower lapel was lost in the DRAFT (flat13.py: straight break -> point edge + belly 10 @ 0.4 = 18 mm 40 mm
  above the break; flat / 3D / worn agree; roll costs ~10 more). Lapel belly 0.02 @ 0.2 -> DEFAULT (LOOK
  check/cmp_b20_b18_bc44_*.png, ovl_b20.png; gate PASS_WAIVED 30c40cc66aaf2cc57ba1). b18 (18 @ 0.25) / b22 (22 @ 0.15)
  in the notes. KAT test_tailoring::test_a_low_lapel_belly_keeps_the_lower_lapel_wide.
- C221: "painted-on" lapel = the workbench clay light. lift13.py: outer edge 4-6 mm off the forepart (b20 similar);
  the same geometry in EEVEE (render13.py RTEX=1) shows the edge + stand like the concept. No geometry change.
- C222: notch tabs = the gate's waived row collar_stand_end (stand 14.2 mm at the end carries it as a tab). collar
  run_off true (R28, opt-in since round 19) -> the end lies flat, clean notch (check/notch_r20.png); collar_stand_end
  PASS; gate PASS_WAIVED 09456467b628eb573deb -> DEFAULT v10 (LOOK check/cmp_r20_b20_bc44_*.png).
S14 (no default change; v10 = r20 stays): causes per stage (repro14.py prints every fit phase + styling op per side).
| run (raster, L ; R) | edge 450 | 550 | 650 | len | hem | break x | thr p99 |
| concept | 71 | 78 | 94 | 748 | 482 | 64 | |
| r20 (v10) | 61 ; 49 | 74 ; 67 | 98 ; 97 | 728 | 486 | 53 ; 41 | 5.55 |
| oL17 (PF_OPEN_LAP=0 + length_bonus 0.17) | 49 ; 49 | 68 ; 67 | 101 ; 98 | 747 | 478 | 42 ; 43 | 4.31 |
- C223: R/L asymmetry is the FIT (relax1 leaves L 30 past CF, R 9; the swing turns L further; slide / turn then fire on
  L only). OPEN_LAP False (PF_OPEN_LAP=0, OPT-IN, KAT test_worn_open_unfastened_front_has_no_lap) evens the fit; relax1's
  seed not found. Even, both sides land at R's values: r20's better L was an accident.
- C224: length is the draft: length_bonus is metres; 0.17 -> 747 (opt-in candidate oL17; LOOK level with r20, the V
  at the waist narrower: check/cmp_oL17_o0b_r20_*.png). The edge rows follow the break, which the STYLING closes
  (fit 64 -> first relax -11, smooth -4, pull -5 -> 42-53). Stiff styling (GP_STYLE_BEND) holds it but fronts 10-14 %,
  no hang (o0b): wrong model.
- Collar-end "fold": the collar fall's end (run_off) stands 6-13 mm off the lapel (cend14.py), R tilted more; lift cause open.
NEXT: (1) the break's spring-back in the styling (fit 64 -> 42-53): find what the fit's pinned open shape stores that
  the styling's first relax releases (threads first: compare the fit's and the style relax's energies on the chest /
  lapel cells), so the break stays ~64 with the fronts still hanging; then re-run oL17 (even + right length) and judge.
  (2) relax1's L / R seed (L 30 / R 9 past CF with laps off). (3) collar end lift 6-13 mm. (4) blind review once the
  edge rows are within +-8. (5) shirt collar at the back. SUITE s14 (18 files): 321 passed, 4 xfailed, PYTEST_EXIT 0 ($S14/suite.log).
