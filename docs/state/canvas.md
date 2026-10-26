# STATE: canvas (canvas / interfacing BENDING STIFFNESS; the jacket with no workaround holds) -- 2026-10-26 (s13)

GOAL (Joe): canvassed pieces keep their shape by STIFFNESS so the workaround holds go. No sim, no rented GPU.
Concept SLIM-CUT, worn open, falls straight (workspace/garrett_v20/concept_v8_front_apose.png). Rules: threads first
(C195); supports, not holds (C190); styling ends with smooth + pull down; current garments are not a baseline.
Sessions: s1 78507629; s2-s13 claude/canvas2-13 ($S13 /mnt/data/hifipushie/canvas/s13; history cloth.md "canvas
stiffness session 13"). Ledger C190-C222.
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
NEXT: (1) blind review once the edge rows are within +-8 (edge 450 L 61 / R 49 vs 71).
  (2) front length 725 vs 748, edge 450 L 59 / R 50 vs 71, 650 103 vs 94 (the lower front kicked forward, C217).
  (3) the opening at the break: our roll meets CF ~45-48 off vs the concept's ~55-64. (4) s11: R turn asymmetry.
  No blind review yet (edge 450 outside +-8).
