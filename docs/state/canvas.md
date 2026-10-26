# STATE: canvas (canvas / interfacing BENDING STIFFNESS; the jacket with no workaround holds) -- 2026-10-26 (s16)

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
| oL17 (PF_OPEN_LAP=0 + length_bonus 0.17) | 49 ; 49 | 68 ; 67 | 101 ; 98 | 747 | 478 | 42 ; 43 | 4.31 |
- C223: R/L asymmetry is the FIT (relax1 leaves L 30 past CF, R 9; the swing turns L further; slide / turn then fire on
  L only). OPEN_LAP False (PF_OPEN_LAP=0, OPT-IN, KAT test_worn_open_unfastened_front_has_no_lap) evens the fit; relax1's
  seed not found. Even, both sides land at R's values: r20's better L was an accident.
- C224: length is the draft: length_bonus is metres; 0.17 -> 747 (opt-in candidate oL17; LOOK level with r20, the V
  at the waist narrower: check/cmp_oL17_o0b_r20_*.png). The edge rows follow the break, which the STYLING closes
  (fit 64 -> first relax -11, smooth -4, pull -5 -> 42-53). Stiff styling (GP_STYLE_BEND) holds it but fronts 10-14 %,
  no hang (o0b): wrong model.
- Collar-end "fold": the collar fall's end (run_off) stands 6-13 mm off the lapel (cend14.py), R tilted more; lift cause open.
S15 (claude/canvas15): stiff styling threads-first: C225 caps bound stretch only; C226 thread weight per face. b2L (oL17
  fit + GP_STYLE_BEND=1): every edge row within +-8 of the concept, but the lapels ripple along the roll, threads 8.33.
S16 (claude/canvas16; $S16 /mnt/data/hifipushie/canvas/s16; notes cloth.md "canvas stiffness session 16"):
- Cause of the ripple: the stiff styling is at rest at the fit (PD threads target = current map in band, shear weight
  SHEAR_STIFF 0.011, bending rest = the fit's crumples); the default styling's relax / smooth remove them.
- C228 GP_BEND_REST_PRESS=1 (OPT-IN): bending rest = the canvassed pieces smoothed bending-free first. C229 GP_TF_BLEED=1
  (OPT-IN, no use on the jacket: collar strain rides on shear). C227: review gate no longer refuses diag crops.
| run (raster L ; R) | edge 450 | 550 | 650 | len | hem | break | thr p99 | stand / collar | lapel rough / shear |
| concept | 71 | 78 | 94 | 748 | 482 | 386 | | | |
| r20 (v10 DEFAULT) | 61 ; 49 | 74 ; 67 | 98 ; 97 | 728 | 486 | 374 | 5.55 | 8.7 / 11.0 | 0.23 / 1.7 |
| b2L | 68 ; 76 | 78 ; 84 | 94 ; 99 | 745 | 477 | 366 | 8.33 | 18.4 / 15.0 | 1.14 / 12.7 |
| e7 = b2L + PRESS (best) | 72 ; 69 | 80 ; 76 | 99 ; 98 | 744 | 477 | 370 | 7.98 | 9.0 / 17.0 | 0.18 / 2.8 |
  e7 = s14/fit_oL17.pkl styled with GP_STYLE_BEND=1 GP_BEND_REST_PRESS=1 ($S16/asm_e7.pkl, asm_e7c.pkl). LOOK
  (check/cmp_eevee_e7_b2L_r20_upper_front.png): lapels clean like r20, V straight and even like b2L. Lapel face = r20's.
- Not default: collar threads 17 % (r20 11), threads p99 7.98 vs 5.55, pocket flaps stand off (side), the lower front
  bulges forward below the pocket, R collar end crumple (all). Blind review not run (reviewer weekly limit).
- Dead ends s16: faired rest (high-pass of the fit; crumples as sharp as the roll); high-pass of the press move (rest
  strained 12-21 %); press as the styling START (break closes 64 -> 44); SHEAR_FREE in the PD step, uniform or per face
  (collar 5 % but forepart crumples, hem 510-524; reverted); bleed alone (collar 19 %).
NEXT: (1) the collar shears 6 -> 40 deg in the stiff styling's first relax (pcop16.py): find what drives it (bending
  rest vs the stand's hold vs the floor) and fix there; that is the collar's 17 %. (2) lower front bulge + flaps standing
  off in the side view under the stiff styling (flaps bw 8: interfaced, rest = fit). (3) blind review of e7 vs r20
  (review command in $S16/review_e7.log's notes). (4) collar ends (cend14) worse on e7 L (13.6 mm). Then the default.
SUITE s16: see $S16/suite.log.
